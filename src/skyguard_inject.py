"""Fault injector for SkyGuard's benchmark. Spec: SkyGuard_SIH26073_Engine_Spec.md section 6.

Injects 9 fault classes (F1-F9) sampled by EVENT COUNT (a per-class minimum, spread across
at least MIN_STATIONS stations) so every class is measurable under grouped-station CV.
Events never overlap each other or a protected window. Total faulty coverage must land in
4-8% of station-times with no class above 30% of faulty rows (checked in tests). Only F1
(gross spike) and F8 (sentinel/bit corruption) may leave the physical plausible range;
every other class is clipped back into range after being applied.

Durations (3-hourly cadence, 1 step = 3 h): F3 drift is 56-112 steps (7-14 days), shorter
than the spec's 7-45 days so that 24 drift events fit in the coverage budget (documented
deviation). F9 is 1-16 steps (spec 1-48 h).
"""
from __future__ import annotations
import numpy as np
import pandas as pd

VARS = ['temp_c', 'mslp_hpa', 'rh_pct']
CLASSES = ['F1', 'F2', 'F3', 'F4', 'F5', 'F6', 'F7', 'F8', 'F9']
BOUNDS = {'temp_c': (-80.0, 60.0), 'mslp_hpa': (870.0, 1085.0), 'rh_pct': (0.0, 100.0)}
# requested minimums: F1 60, F2 40, F3 24, F4 30, F5 30, F6 30, F7 30, F8 60, F9 30
MIN_EVENTS = {'F1': 70, 'F2': 60, 'F3': 24, 'F4': 36, 'F5': 36, 'F6': 30, 'F7': 36, 'F8': 70, 'F9': 36}
MIN_STATIONS = 8
DURATION_STEPS = {'F1': (1, 1), 'F2': (4, 24), 'F3': (56, 112), 'F4': (8, 80), 'F5': (4, 80),
                  'F6': (4, 80), 'F7': (1, 8), 'F8': (1, 1), 'F9': (1, 16)}
PLACEMENT_ORDER = ['F3', 'F4', 'F5', 'F6', 'F2', 'F9', 'F7', 'F1', 'F8']  # long events first
GAP_STEPS = 2  # minimum clean steps between events


def _clip_if_needed(cls, var, value):
    if cls in ('F1', 'F8'):
        return value
    lo, hi = BOUNDS[var]
    return min(max(value, lo), hi)


def _place(rng, cls, order, e, station_groups, occupied):
    """Pick (station, start, n) for one event with no overlap; cycles stations so a class spreads out."""
    lo, hi = DURATION_STEPS[cls]
    for k in range(len(order)):
        sid = order[(e + k) % len(order)]
        g, eligible = station_groups[sid]
        occ = occupied[sid]
        for _ in range(200):
            n = int(rng.integers(lo, hi + 1))
            st = int(rng.choice(eligible))
            if st + n > len(g) or occ[max(0, st - GAP_STEPS):st + n + GAP_STEPS].any():
                continue
            occ[st:st + n] = True
            return sid, st, n
    raise RuntimeError(f'could not place {cls} event')


def inject_faults(base, protected, seed=42):
    rng = np.random.default_rng(seed)
    d = base.copy()
    d['injected_faults'] = ''
    labels = []

    station_groups = {}
    occupied = {}
    for sid, g0 in d.groupby('station_id', sort=False):
        g = g0.reset_index()
        prot_g = protected[g['index'].to_numpy()]
        eligible = np.flatnonzero((~prot_g) & g[VARS].notna().all(axis=1).to_numpy())
        if len(eligible) >= 30:
            station_groups[sid] = (g, eligible)
            occupied[sid] = prot_g.copy()
    if not station_groups:
        return d, pd.DataFrame(labels)
    station_ids = list(station_groups.keys())

    for cls in PLACEMENT_ORDER:
        order = []
        for e in range(MIN_EVENTS[cls]):
            if e % len(station_ids) == 0:
                order = list(rng.permutation(station_ids))
            sid, st, n = _place(rng, cls, order, e % len(station_ids), station_groups, occupied)
            g, _ = station_groups[sid]
            if cls == 'F1':
                var = rng.choice(VARS); mag = float(rng.uniform(3, 15)); sign = rng.choice([-1, 1])
                sigma = float(g.loc[max(0, st - 24):min(len(g) - 1, st + 24), var].std() or 1)
            elif cls == 'F2':
                var = rng.choice(VARS); mag = 0
            elif cls == 'F3':
                var = rng.choice(['temp_c', 'rh_pct', 'mslp_hpa']); mag = float(rng.uniform(0.5, 3.0)) * rng.choice([-1, 1])
            elif cls == 'F4':
                var = rng.choice(VARS)
                mag = float(rng.uniform({'temp_c': .5, 'rh_pct': 3, 'mslp_hpa': .5}[var], {'temp_c': 4, 'rh_pct': 15, 'mslp_hpa': 5}[var])) * rng.choice([-1, 1])
            elif cls == 'F5':
                var = rng.choice(VARS); mag = float(rng.uniform(1.5, 5))
            elif cls == 'F6':
                var = rng.choice(['temp_c', 'rh_pct'])
                mag = (100.0 if rng.random() < .5 else 0.0) if var == 'rh_pct' else 60.0
            elif cls == 'F7':
                var = 'all'; mag = 0
            elif cls == 'F8':
                var = rng.choice(VARS); mag = 0
            else:  # F9
                var = rng.choice(VARS); mag = 0
            for j in range(st, st + n):
                row = int(g.iloc[j]['index']); t = d.at[row, 'time_utc']
                if cls != 'F7' and var != 'all' and pd.isna(d.at[row, var]):
                    continue
                if cls == 'F1':
                    d.at[row, var] = _clip_if_needed(cls, var, float(d.at[row, var]) + sign * mag * sigma)
                elif cls == 'F2':
                    d.at[row, var] = _clip_if_needed(cls, var, float(d.iloc[int(g.iloc[st]['index'])][var]))
                elif cls == 'F3':
                    d.at[row, var] = _clip_if_needed(cls, var, float(d.at[row, var]) + mag * (j - st) / max(1, n - 1))
                elif cls == 'F4':
                    d.at[row, var] = _clip_if_needed(cls, var, float(d.at[row, var]) + mag)
                elif cls == 'F5':
                    d.at[row, var] = _clip_if_needed(cls, var, float(d.at[row, var]) + rng.normal(0, mag * float(g[var].std() or 1)))
                elif cls == 'F6':
                    d.at[row, var] = mag
                elif cls == 'F7':
                    d.loc[row, VARS] = np.nan
                elif cls == 'F8':
                    d.at[row, var] = -9999.0 if rng.random() < .5 else 0.0
                elif cls == 'F9':
                    other = g[(g.time_utc.dt.hour == g.iloc[j].time_utc.hour) & (g.index != j) & g[var].notna()]
                    if len(other):
                        d.at[row, var] = _clip_if_needed(cls, var, float(other.iloc[rng.integers(len(other))][var]))
                d.at[row, 'injected_faults'] = str(d.at[row, 'injected_faults']) + cls + ';'
                labels.append({'station_id': sid, 'time_utc': t, 'variable': var, 'class': cls,
                                'start': g.iloc[st].time_utc, 'end': g.iloc[min(len(g) - 1, st + n - 1)].time_utc,
                                'magnitude': float(abs(mag))})

    return d, pd.DataFrame(labels)
