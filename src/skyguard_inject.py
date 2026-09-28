"""Fault injector for SkyGuard's benchmark. Spec: SkyGuard_SIH26073_Engine_Spec.md section 6.

Injects 9 fault classes (F1-F9) into a fraction of station-time. Target overall
coverage is 3-5% of rows (spec:137, config `injector.rate: 0.03`), with no single
class exceeding 30% of faulty rows.
"""
from __future__ import annotations
import numpy as np
import pandas as pd

VARS = ['temp_c', 'mslp_hpa', 'rh_pct']
CLASSES = ['F1', 'F2', 'F3', 'F4', 'F5', 'F6', 'F7', 'F8', 'F9']
CLASS_BUDGET_CAP = 0.28  # keep every class comfortably under the 30% requirement
TARGET_RATE_RANGE = (0.032, 0.045)  # tuned so realistic event-length overshoot lands the
                                     # final overall coverage inside the required 3-5% band


def _class_budgets(rng, budget_rows):
    shares = rng.dirichlet(np.ones(len(CLASSES)) * 5)
    excess = 0.0
    for i in range(len(shares)):
        if shares[i] > CLASS_BUDGET_CAP:
            excess += shares[i] - CLASS_BUDGET_CAP
            shares[i] = CLASS_BUDGET_CAP
    if excess > 0:
        under = [i for i in range(len(shares)) if shares[i] < CLASS_BUDGET_CAP]
        shares[under] += excess / len(under)
    return {cls: max(1, int(round(shares[i] * budget_rows))) for i, cls in enumerate(CLASSES)}


def inject_faults(base, protected, seed=42):
    rng = np.random.default_rng(seed)
    d = base.copy()
    d['injected_faults'] = ''
    labels = []

    station_groups = {}
    for sid, g0 in d.groupby('station_id', sort=False):
        g = g0.reset_index()
        eligible = np.flatnonzero((~protected[g['index'].to_numpy()]) & g[VARS].notna().all(axis=1).to_numpy())
        if len(eligible) >= 30:
            station_groups[sid] = (g, eligible)
    if not station_groups:
        return d, pd.DataFrame(labels)
    station_ids = list(station_groups.keys())
    station_weights = np.array([len(station_groups[s][1]) for s in station_ids], dtype=float)
    station_weights /= station_weights.sum()

    total_rows = len(d)
    target_pct = rng.uniform(*TARGET_RATE_RANGE)
    budget_rows = round(total_rows * target_pct)
    class_budget = _class_budgets(rng, budget_rows)

    for cls in CLASSES:
        budget = class_budget[cls]
        done = 0
        attempts = 0
        max_attempts = budget * 25 + 500
        while done < budget and attempts < max_attempts:
            attempts += 1
            sid = rng.choice(station_ids, p=station_weights)
            g, eligible = station_groups[sid]
            st = int(rng.choice(eligible))
            if cls == 'F1':
                n = 1; var = rng.choice(VARS); mag = float(rng.uniform(3, 15)); sign = rng.choice([-1, 1])
                sigma = float(g.loc[max(0, st - 24):min(len(g) - 1, st + 24), var].std() or 1); idx = [st]
            elif cls == 'F2':
                n = int(rng.integers(4, 25)); var = rng.choice(VARS); idx = list(range(st, min(st + n, len(g)))); mag = 0
            elif cls == 'F3':
                n = int(rng.integers(56, 361)); var = rng.choice(['temp_c', 'rh_pct', 'mslp_hpa'])
                idx = list(range(st, min(st + n, len(g)))); mag = float(rng.uniform(0.5, 3.0)) * rng.choice([-1, 1])
            elif cls == 'F4':
                n = int(rng.integers(8, 81)); var = rng.choice(VARS); idx = list(range(st, min(st + n, len(g))))
                mag = float(rng.uniform({'temp_c': .5, 'rh_pct': 3, 'mslp_hpa': .5}[var], {'temp_c': 4, 'rh_pct': 15, 'mslp_hpa': 5}[var])) * rng.choice([-1, 1])
            elif cls == 'F5':
                n = int(rng.integers(4, 81)); var = rng.choice(VARS); idx = list(range(st, min(st + n, len(g)))); mag = float(rng.uniform(1.5, 5))
            elif cls == 'F6':
                n = int(rng.integers(4, 81)); var = rng.choice(['temp_c', 'rh_pct']); idx = list(range(st, min(st + n, len(g))))
                mag = 100.0 if var == 'rh_pct' else 60.0
            elif cls == 'F7':
                n = int(rng.integers(1, 9)); var = 'all'; idx = list(range(st, min(st + n, len(g)))); mag = 0
            elif cls == 'F8':
                n = 1; var = rng.choice(VARS); idx = [st]; mag = 0
            else:  # F9
                n = int(rng.integers(8, 161)); var = rng.choice(VARS); idx = list(range(st, min(st + n, len(g)))); mag = 0
            if len(idx) < 1:
                continue
            added = 0
            for j in idx:
                row = int(g.iloc[j]['index']); t = d.at[row, 'time_utc']
                if protected[row]:
                    continue
                if cls != 'F7' and var != 'all' and pd.isna(d.at[row, var]):
                    continue
                if cls == 'F1':
                    d.at[row, var] = float(d.at[row, var]) + sign * mag * sigma
                elif cls == 'F2':
                    d.at[row, var] = float(d.iloc[int(g.iloc[st]['index'])][var])
                elif cls == 'F3':
                    d.at[row, var] = float(d.at[row, var]) + mag * (j - st) / max(1, n - 1)
                elif cls == 'F4':
                    d.at[row, var] = float(d.at[row, var]) + mag
                elif cls == 'F5':
                    d.at[row, var] = float(d.at[row, var]) + rng.normal(0, mag * float(g[var].std() or 1))
                elif cls == 'F6':
                    d.at[row, var] = mag
                elif cls == 'F7':
                    d.loc[row, VARS] = np.nan
                elif cls == 'F8':
                    d.at[row, var] = -9999.0 if rng.random() < .5 else 0.0
                elif cls == 'F9':
                    other = g[(g.time_utc.dt.hour == g.iloc[j].time_utc.hour) & (g.index != j) & g[var].notna()]
                    if len(other):
                        d.at[row, var] = float(other.iloc[rng.integers(len(other))][var])
                d.at[row, 'injected_faults'] = str(d.at[row, 'injected_faults']) + cls + ';'
                labels.append({'station_id': sid, 'time_utc': t, 'variable': var, 'class': cls,
                                'start': g.iloc[st].time_utc, 'end': g.iloc[min(len(g) - 1, st + n - 1)].time_utc,
                                'magnitude': float(abs(mag))})
                added += 1
            done += added
        class_budget[cls] = done  # record actual achieved, for diagnostics

    return d, pd.DataFrame(labels)
