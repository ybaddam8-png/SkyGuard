from __future__ import annotations
from pathlib import Path
import json
import numpy as np
import pandas as pd
from meteostat import Hourly

ROOT = Path(__file__).resolve().parents[1]
START = pd.Timestamp('2023-01-01 00:00:00', tz='UTC')
END = pd.Timestamp('2025-12-31 23:00:00', tz='UTC')
HOURLY_GRID = pd.date_range(START, END, freq='h')

STATIONS = [
    # cluster (a): six highest-coverage candidates with a connected relaxed-neighbour graph
    dict(station_id='42181', name='New Delhi / Palam', lat=28.5667, lon=77.1167, elevation_m=220.0, cluster='a'),
    dict(station_id='42182', name='New Delhi / Safdarjung', lat=28.5833, lon=77.2000, elevation_m=211.0, cluster='a'),
    dict(station_id='42348', name='Jaipur / Sanganer', lat=26.8167, lon=75.8000, elevation_m=385.0, cluster='a'),
    dict(station_id='42170', name='Churu', lat=28.2500, lon=74.9167, elevation_m=290.0, cluster='a'),
    dict(station_id='42103', name='Ambala', lat=30.3833, lon=76.7667, elevation_m=271.0, cluster='a'),
    dict(station_id='42131', name='Hissar', lat=29.1667, lon=75.7333, elevation_m=216.0, cluster='a'),
    # cluster (c): all six candidates passing the >=50% synoptic complete-triplet threshold
    dict(station_id='43003', name='Bombay / Santacruz', lat=19.1167, lon=72.8500, elevation_m=8.0, cluster='c'),
    dict(station_id='43014', name='Aurangabad Chikalthan Aerodrome', lat=19.8500, lon=75.4000, elevation_m=582.0, cluster='c'),
    dict(station_id='43063', name='Poona', lat=18.5333, lon=73.8500, elevation_m=555.0, cluster='c'),
    dict(station_id='43110', name='Ratnagiri', lat=16.9833, lon=73.3333, elevation_m=75.0, cluster='c'),
    dict(station_id='42921', name='Nasik', lat=20.0000, lon=73.7833, elevation_m=598.0, cluster='c'),
    dict(station_id='43117', name='Sholapur', lat=17.6667, lon=75.9000, elevation_m=477.0, cluster='c'),
]
VARS = ['temp_c', 'mslp_hpa', 'rh_pct']
RAW_VARS = ['temp', 'pres', 'rhum']


def hav_km(lat1, lon1, lat2, lon2):
    r = 6371.0088
    p1, p2 = np.radians([lat1, lat2])
    dp, dl = np.radians(lat2 - lat1), np.radians(lon2 - lon1)
    a = np.sin(dp / 2) ** 2 + np.cos(p1) * np.cos(p2) * np.sin(dl / 2) ** 2
    return float(2 * r * np.arcsin(np.sqrt(a)))


def native_interval(deltas):
    d = pd.Series(deltas).dropna()
    d = d[d > 0].round().astype(int)
    if d.empty:
        return 'unknown', None, 0.0
    counts = d.value_counts()
    mode = int(counts.index[0])
    share = float(counts.iloc[0] / len(d))
    if mode == 1 and share >= 0.75:
        label = 'hourly'
    elif mode == 3 and share >= 0.75:
        label = '3-hourly'
    else:
        label = 'mixed'
    return label, mode, share


meta = pd.DataFrame(STATIONS)
meta['cadence_min'] = 60
meta['source'] = 'Meteostat Python 1.7.6 Hourly, model=False, no interpolation'
meta['pressure_source'] = 'sea-level pressure (station pressure not available from source)'
meta['period_start'] = START.isoformat()
meta['period_end'] = END.isoformat()

raw_by_station = {}
fetch_log = []
for s in STATIONS:
    # model=False excludes Meteostat model/MOSMIX fill. No interpolate() is called.
    raw = Hourly(
        s['station_id'],
        START.to_pydatetime().replace(tzinfo=None),
        END.to_pydatetime().replace(tzinfo=None),
        model=False,
    ).fetch()
    raw.index = pd.to_datetime(raw.index, utc=True)
    raw = raw.rename(columns={'temp': 'temp_c', 'pres': 'mslp_hpa', 'rhum': 'rh_pct'})
    raw = raw[[c for c in VARS if c in raw.columns]].sort_index()
    complete = raw[VARS].notna().all(axis=1)
    any_value = raw[VARS].notna().any(axis=1)
    interval_label, modal_hours, modal_share = native_interval(raw.index.to_series().diff().dt.total_seconds() / 3600)
    raw_by_station[s['station_id']] = raw
    fetch_log.append({
        'station_id': s['station_id'], 'name': s['name'], 'cluster': s['cluster'],
        'raw_rows_returned': int(len(raw)), 'real_complete_rows': int(complete.sum()),
        'real_any_value_rows': int(any_value.sum()), 'expected_hourly_rows': int(len(HOURLY_GRID)),
        'real_hourly_coverage_pct': round(100 * complete.reindex(HOURLY_GRID).fillna(False).mean(), 4),
        'real_any_hourly_coverage_pct': round(100 * any_value.reindex(HOURLY_GRID).fillna(False).mean(), 4),
        'native_reporting_interval': interval_label, 'modal_interval_hours': modal_hours,
        'modal_interval_share_pct': round(100 * modal_share, 4),
        'first_raw_observation': None if raw.empty else raw.index.min().isoformat(),
        'last_raw_observation': None if raw.empty else raw.index.max().isoformat(),
    })

# Decision rule is applied to complete real T/P/RH triplets on the hourly grid.
real_hourly_shares = [x['real_hourly_coverage_pct'] for x in fetch_log]
hourly_qualified = sum(x >= 80.0 for x in real_hourly_shares)
chosen_cadence = 'hourly' if hourly_qualified >= 8 else '3-hourly'
if chosen_cadence == 'hourly':
    EXPECTED = HOURLY_GRID
    cadence_hours = 1
else:
    EXPECTED = pd.date_range(START, END, freq='3h')
    cadence_hours = 3

frames = []
rows = []
for s in STATIONS:
    raw = raw_by_station[s['station_id']]
    out = raw.reindex(EXPECTED)
    out.index.name = 'time_utc'
    out = out.reset_index()
    out.insert(0, 'station_id', s['station_id'])
    out['cluster'] = s['cluster']
    frames.append(out)
    d = out.set_index('time_utc')
    complete = d[VARS].notna().all(axis=1)
    any_value = d[VARS].notna().any(axis=1)
    raw_complete = raw[VARS].notna().all(axis=1)
    raw_any = raw[VARS].notna().any(axis=1)
    interval_label, modal_hours, modal_share = native_interval(raw.index.to_series().diff().dt.total_seconds() / 3600)
    rows.append({
        'station_id': s['station_id'], 'name': s['name'], 'cluster': s['cluster'],
        'expected_hourly_rows': len(HOURLY_GRID), 'expected_rows_at_chosen_cadence': len(EXPECTED),
        'rows_written': len(out), 'real_observation_rows_at_chosen_cadence': int(complete.sum()),
        'real_observation_share_at_chosen_cadence_pct': round(100 * complete.mean(), 4),
        'real_any_variable_share_at_chosen_cadence_pct': round(100 * any_value.mean(), 4),
        'real_hourly_complete_triplet_share_pct': round(100 * raw_complete.reindex(HOURLY_GRID).fillna(False).mean(), 4),
        'real_hourly_any_variable_share_pct': round(100 * raw_any.reindex(HOURLY_GRID).fillna(False).mean(), 4),
        'native_reporting_interval': interval_label, 'modal_interval_hours': modal_hours,
        'modal_interval_share_pct': round(100 * modal_share, 4),
        'temp_synoptic_coverage_pct': round(100 * d.temp_c.notna().mean(), 4),
        'mslp_synoptic_coverage_pct': round(100 * d.mslp_hpa.notna().mean(), 4),
        'rh_synoptic_coverage_pct': round(100 * d.rh_pct.notna().mean(), 4),
        'complete_triplet_synoptic_coverage_pct': round(100 * complete.mean(), 4),
        'temp_missing_pct': round(100 * d.temp_c.isna().mean(), 4),
        'mslp_missing_pct': round(100 * d.mslp_hpa.isna().mean(), 4),
        'rh_missing_pct': round(100 * d.rh_pct.isna().mean(), 4),
        'any_variable_missing_pct': round(100 * d[VARS].isna().any(axis=1).mean(), 4),
    })

obs = pd.concat(frames, ignore_index=True).sort_values(['station_id', 'time_utc']).reset_index(drop=True)
obs.to_parquet(ROOT / 'data/clean/observations_clean.parquet', index=False)
meta['cadence_min'] = cadence_hours * 60
meta['chosen_cadence'] = chosen_cadence
summary = pd.DataFrame(rows)
summary.to_csv(ROOT / 'data/clean/missingness_by_station.csv', index=False)
meta = meta.merge(summary[['station_id', 'native_reporting_interval', 'temp_synoptic_coverage_pct', 'mslp_synoptic_coverage_pct', 'rh_synoptic_coverage_pct', 'complete_triplet_synoptic_coverage_pct']], on='station_id', how='left')
meta['low_coverage'] = meta['complete_triplet_synoptic_coverage_pct'] < 50.0
meta.to_csv(ROOT / 'stations.csv', index=False)

neigh = []
for i, a in enumerate(STATIONS):
    for j, b in enumerate(STATIONS):
        if i >= j or a['cluster'] != b['cluster']:
            continue
        dist = hav_km(a['lat'], a['lon'], b['lat'], b['lon'])
        elev = abs(a['elevation_m'] - b['elevation_m'])
        if dist <= 200 and elev <= 500:
            neigh.append({'cluster': a['cluster'], 'station_a': a['station_id'], 'station_b': b['station_id'], 'distance_km': round(dist, 1), 'elevation_diff_m': round(elev, 1)})

summary_payload = {
    'period_start': START.isoformat(), 'period_end': END.isoformat(),
    'source': 'Meteostat Python 1.7.6', 'model_data_enabled': False,
    'interpolation_applied': False,
    'pressure_field': 'mslp_hpa',
    'pressure_definition': 'sea-level pressure (station pressure not available from source)',
    'chosen_cadence': chosen_cadence, 'cadence_hours': cadence_hours,
    'neighbour_rule': 'distance <= 200 km and elevation difference <= 500 m',
    'hourly_coverage_decision': {'stations_at_or_above_80_pct': hourly_qualified, 'required': 8, 'kept_hourly': chosen_cadence == 'hourly'},
    'station_count': int(len(STATIONS)), 'stations_per_cluster': {str(k): int(v) for k, v in meta.groupby('cluster').size().items()},
    'expected_rows_total': int(len(obs)),
    'complete_real_observation_rows_total': int(obs[VARS].notna().all(axis=1).sum()),
    'any_value_rows_total': int(obs[VARS].notna().any(axis=1).sum()),
    'any_variable_missing_pct_total': round(100 * obs[VARS].isna().any(axis=1).mean(), 4),
    'temp_missing_pct_total': round(100 * obs.temp_c.isna().mean(), 4),
    'mslp_missing_pct_total': round(100 * obs.mslp_hpa.isna().mean(), 4),
    'rh_missing_pct_total': round(100 * obs.rh_pct.isna().mean(), 4),
    'strict_neighbour_pairs': neigh, 'fetch_log': fetch_log,
}
with open(ROOT / 'data/clean/data_summary.json', 'w') as f:
    json.dump(summary_payload, f, indent=2, default=lambda obj: obj.item() if isinstance(obj, np.generic) else str(obj))
print(summary.to_string(index=False))
print('\nCHOSEN CADENCE:', chosen_cadence, 'stations >=80% hourly:', hourly_qualified)
print('ROWS:', len(obs), 'strict neighbour pairs:', len(neigh))
