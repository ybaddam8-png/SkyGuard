"""F-10 health diagnosis on the out-of-fold scored stream (run after make bench).

Compares the F-10 terms on clean stretches and injected-fault stretches, reports the healthy-period
std of the EWMA bias against the spec tolerance, and runs the acceptance test: H on 30-day windows
that end on an injected persistent bias (F3/F4) vs clean 30-day windows, for tau = spec and tau_eff.
Writes outputs/health_diagnosis.json.
"""
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.metrics import roc_auc_score

sys.path.insert(0, str(Path(__file__).resolve().parent))
from health import TOL, ewma, f10_series, tau_eff

ROOT = Path(__file__).resolve().parents[1]
VARS = list(TOL)
d = pd.read_parquet(ROOT / 'outputs/scored_stream.parquet', columns=['station_id', 'time_utc', 'p_fault'] + VARS + [f'r3_{v}' for v in VARS] + [f'r3c_{v}' for v in VARS])
d['time_utc'] = d.time_utc.dt.tz_convert(None)
lab = pd.read_parquet(ROOT / 'data/bench/labels.parquet')
lab['station_id'] = lab.station_id.astype(str)
for c in ('time_utc', 'start', 'end'):
    lab[c] = pd.to_datetime(lab[c], utc=True).dt.tz_convert(None)
lab_any = set(zip(lab.station_id, lab.time_utc))
lab_var = {v: set(zip(lab.station_id[lab.variable.isin([v, 'all'])], lab.time_utc[lab.variable.isin([v, 'all'])])) for v in VARS}
events = lab[lab['class'].isin(['F3', 'F4'])].groupby(['station_id', 'variable', 'class', 'start'], as_index=False).end.first()

diag, sdb, wins = [], [], []
for sid, g in d.groupby('station_id', sort=True):
    g = g.sort_values('time_utc')
    times = pd.DatetimeIndex(g.time_utc)
    alert = (g.p_fault >= .5).to_numpy()
    inj_any = np.array([(sid, t) in lab_any for t in g.time_utc])
    # 30-day look-back counts of injected rows and alerts, to classify each step's window
    look = pd.DataFrame({'i': inj_any.astype(float)}, index=times)
    inj30 = look.i.rolling('30D').sum().to_numpy()
    for v in VARS:
        r, rc = g[f'r3_{v}'].to_numpy(), g[f'r3c_{v}'].to_numpy()
        obs = g[v].notna().to_numpy()
        if not (~np.isnan(rc)).sum() > 1:
            continue
        sref = float(np.nanstd(rc, ddof=1))
        b_h = ewma(rc)[~np.isnan(rc)]
        te = tau_eff(v, rc)
        sdb.append({'s': sid, 'v': v, 'sd_b_healthy': float(np.std(b_h, ddof=1)), 'tau': TOL[v], 'tau_eff': te})
        al30 = pd.DataFrame({'a': (alert & obs).astype(float)}, index=times).a.rolling('30D').sum().to_numpy()
        inj_v = np.array([(sid, t) in lab_var[v] for t in g.time_utc])
        ok = ~np.isnan(r)
        F = {k: f10_series(r, alert, obs, times, sref, tau) for k, tau in (('spec', TOL[v]), ('eff', te))}
        clean_rows = ok & (inj30 == 0) & (al30 == 0)
        inj_rows = ok & inj_v
        for name, m in (('clean (no injected fault, no alert in 30 d)', clean_rows), ('injected fault on this variable', inj_rows)):
            if m.sum() < 20:
                continue
            f = F['spec'][m]
            diag.append({'stretch': name, 's': sid, 'v': v, '|b|/tau': float(np.median(np.abs(f.b) / TOL[v])), 'f30': float(np.median(f.f30)),
                         'var_ratio': float(np.nanmedian(f.ratio)), 'H_spec': float(np.median(f.H)), 'H_eff': float(np.median(F['eff'][m].H)),
                         'share_H0_spec': float((f.H <= 0).mean())})
        # acceptance windows: 30-day windows ending at the last observed step of each F3/F4 event on this variable ...
        for e in events[(events.station_id == sid) & (events.variable == v)].itertuples():
            idx = np.flatnonzero(ok & (g.time_utc.to_numpy() <= np.datetime64(e.end)) & (g.time_utc.to_numpy() >= np.datetime64(e.start)))
            if len(idx):
                wins.append({'kind': 'bias', 'cls': e._3, 's': sid, 'v': v, 'H_spec': float(F['spec'].H.iloc[idx[-1]]), 'H_eff': float(F['eff'].H.iloc[idx[-1]])})
        # ... and non-overlapping clean 30-day windows (no injected fault on the station; alerts allowed, they are the clean false alarms)
        last_end = None
        for j in np.flatnonzero(ok):
            t = times[j]
            if last_end is not None and t - last_end < pd.Timedelta(days=30):
                continue
            if inj30[j] == 0 and F['spec'].n30.iloc[j] >= 40 and t - times[0] >= pd.Timedelta(days=30):
                wins.append({'kind': 'clean', 'cls': None, 's': sid, 'v': v, 'H_spec': float(F['spec'].H.iloc[j]), 'H_eff': float(F['eff'].H.iloc[j]), 'no_alert': bool(al30[j] == 0)})
                last_end = t

diag, sdb, wins = pd.DataFrame(diag), pd.DataFrame(sdb), pd.DataFrame(wins)
out = {'terms_by_stretch': diag.groupby('stretch')[['|b|/tau', 'f30', 'var_ratio', 'H_spec', 'H_eff', 'share_H0_spec']].median().round(3).reset_index().to_dict('records'),
       'ewma_bias_healthy_std': sdb.assign(ratio=sdb.sd_b_healthy / sdb.tau).groupby('v').agg(median_sd_b=('sd_b_healthy', 'median'), tau=('tau', 'first'), median_sd_b_over_tau=('ratio', 'median'),
                                                                                           share_3sd_above_tau=('ratio', lambda x: float((3 * x > 1).mean())), median_tau_eff=('tau_eff', 'median')).round(3).reset_index().to_dict('records'),
       'acceptance': {}}
y = (wins.kind == 'bias').to_numpy()
for k in ('spec', 'eff'):
    c = wins[~y]
    per_sv = c.groupby(['s', 'v'])[f'H_{k}'].median()
    out['acceptance'][k] = {'auc_roc': round(float(roc_auc_score(y, 100 - wins[f'H_{k}'])), 3), 'n_bias_windows': int(y.sum()), 'n_clean_windows': int((~y).sum()),
                            'median_H_bias': round(float(wins[y][f'H_{k}'].median()), 1), 'median_H_clean': round(float(c[f'H_{k}'].median()), 1),
                            'share_clean_windows_H80': round(float((c[f'H_{k}'] >= 80).mean()), 3), 'share_clean_station_vars_H80': round(float((per_sv >= 80).mean()), 3),
                            'auc_roc_clean_no_alert_only': round(float(roc_auc_score(np.r_[np.ones(y.sum()), np.zeros(int(c.no_alert.sum()))], 100 - np.r_[wins[y][f'H_{k}'], c[c.no_alert][f'H_{k}']])), 3)}
    for cls in ('F3', 'F4'):
        m = (wins.cls == cls) | ~y
        out['acceptance'][k][f'auc_roc_{cls}'] = round(float(roc_auc_score(y[m], 100 - wins[m][f'H_{k}'])), 3)
(ROOT / 'outputs/health_diagnosis.json').write_text(json.dumps(out, indent=1))
print(json.dumps(out, indent=1))
