import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from skyguard_inject import inject_faults, VARS, CLASSES, DURATION_STEPS  # noqa: E402

REQUIRED_MIN_EVENTS = {'F1': 60, 'F2': 40, 'F3': 24, 'F4': 30, 'F5': 30, 'F6': 30, 'F7': 30, 'F8': 60, 'F9': 30}

BOUNDS = {'temp_c': (-80.0, 60.0), 'mslp_hpa': (870.0, 1085.0), 'rh_pct': (0.0, 100.0)}


@pytest.fixture(scope='module')
def clean_and_protected():
    clean = pd.read_parquet(ROOT / 'data/clean/observations_clean.parquet').sort_values(['station_id', 'time_utc']).reset_index(drop=True)
    clean['station_id'] = clean.station_id.astype(str)
    clean['time_utc'] = pd.to_datetime(clean.time_utc, utc=True)
    windows = [
        ('heatwave_a', 'a', pd.Timestamp('2024-05-16T18:30Z'), pd.Timestamp('2024-06-19T18:29:59Z')),
        ('biparjoy_a', 'a', pd.Timestamp('2023-06-16T18:00Z'), pd.Timestamp('2023-06-21T00:00Z')),
        ('monsoon_c', 'c', pd.Timestamp('2024-07-23T00:00Z'), pd.Timestamp('2024-07-30T00:00Z')),
    ]
    protected = np.zeros(len(clean), bool)
    for _, c, a, b in windows:
        protected |= (clean.cluster == c) & clean.time_utc.between(a, b, inclusive='both')
    return clean, protected


def test_overall_prevalence_in_4_to_8_percent(clean_and_protected):
    clean, protected = clean_and_protected
    inj, labels = inject_faults(clean, protected, seed=42)
    faulty = (inj.injected_faults != '').sum()
    pct = faulty / len(clean)
    assert 0.04 <= pct <= 0.08, f'faulty coverage {pct:.4f} outside 4-8% band'


def test_no_class_exceeds_30_percent_of_faulty_rows(clean_and_protected):
    clean, protected = clean_and_protected
    _, labels = inject_faults(clean, protected, seed=42)
    shares = labels['class'].value_counts(normalize=True)
    assert shares.max() < 0.30, f'class share too high: {shares.to_dict()}'
    assert set(labels['class'].unique()) <= set(CLASSES)


def test_protected_windows_untouched(clean_and_protected):
    clean, protected = clean_and_protected
    inj, _ = inject_faults(clean, protected, seed=42)
    assert (inj.loc[protected, 'injected_faults'] == '').all()


def test_seed_42_reproducible(clean_and_protected):
    clean, protected = clean_and_protected
    inj1, labels1 = inject_faults(clean, protected, seed=42)
    inj2, labels2 = inject_faults(clean, protected, seed=42)
    pd.testing.assert_frame_equal(inj1, inj2)
    pd.testing.assert_frame_equal(labels1, labels2)


def test_bounds_hold_except_f1_f8(clean_and_protected):
    clean, protected = clean_and_protected
    inj, _ = inject_faults(clean, protected, seed=42)
    for v, (lo, hi) in BOUNDS.items():
        out_of_range = inj[(inj[v] < lo) | (inj[v] > hi)]
        offending = out_of_range[~out_of_range.injected_faults.str.contains('F1;|F8;')]
        assert len(offending) == 0, f'{v} left range without F1/F8: {len(offending)} rows'


def test_f6_pins_exactly(clean_and_protected):
    # only check rows where F6 is the sole fault applied - a later stacked fault
    # (e.g. F7 dropout) is allowed to overwrite F6's pin, same as any other overlap.
    clean, protected = clean_and_protected
    inj, labels = inject_faults(clean, protected, seed=42)
    f6 = labels[labels['class'] == 'F6']
    checked = 0
    for _, r in f6.iterrows():
        row = inj[(inj.station_id == r.station_id) & (inj.time_utc == r.time_utc)]
        if row.empty or row.iloc[0]['injected_faults'] != 'F6;':
            continue
        val = row.iloc[0][r.variable]
        if r.variable == 'rh_pct':
            assert val in (100.0, 0.0)
        else:
            assert val == 60.0
        checked += 1
    assert checked > 0




def _events(labels):
    return labels.drop_duplicates(['station_id', 'variable', 'class', 'start', 'end'])


def test_minimum_events_and_station_spread(clean_and_protected):
    clean, protected = clean_and_protected
    _, labels = inject_faults(clean, protected, seed=42)
    ev = _events(labels)
    for cls, need in REQUIRED_MIN_EVENTS.items():
        sub = ev[ev['class'] == cls]
        assert len(sub) >= need, f'{cls}: {len(sub)} events < {need}'
        assert sub.station_id.nunique() >= 8, f'{cls}: only {sub.station_id.nunique()} stations'


def test_event_durations_within_spec(clean_and_protected):
    clean, protected = clean_and_protected
    _, labels = inject_faults(clean, protected, seed=42)
    ev = _events(labels)
    steps = ((ev['end'] - ev['start']).dt.total_seconds() / 10800).round() + 1
    for cls, (lo, hi) in DURATION_STEPS.items():
        s = steps[ev['class'] == cls]
        assert s.min() >= lo and s.max() <= hi, f'{cls} durations {s.min()}-{s.max()} outside {lo}-{hi}'
