# SkyGuard AI — SIH26073 Engine

## Status

The data step (`src/prepare_data.py`), the fault injector (`src/skyguard_inject.py`), and
the tiered anomaly-detection benchmark (`src/run_step2.py`: T0-T3 features, LightGBM
fusion model, root-cause classifier, isotonic calibration, SHAP explanations, and
T2/T3-blended imputation) have all been run. `outputs/metrics.json` and
`outputs/benchmark_report.md` are real results from this pipeline, not placeholders.

Current benchmark (5-fold grouped-by-station CV, fold mean ± std; regenerate with
`make bench`). **These numbers come from the event-count injector and are not
like-for-like comparable to earlier README numbers (F1 0.584, macro-F1 0.411), which came
from the old coverage-budget injector that produced too few slow-fault events.**

| Metric | Mean | Std |
|---|---:|---:|
| Fusion model F1 (binary fault/no-fault) | 0.484 | 0.066 |
| Macro-F1 across F1-F9 (fold mean) | 0.440 | 0.030 |
| WMO-rules (T0-only) baseline F1 | 0.413 | 0.063 |
| Isolation Forest baseline F1 | 0.230 | 0.054 |
| "Always fault" trivial baseline F1 | 0.126 | 0.006 |
| ECE, raw probabilities | 0.127 | 0.014 |
| ECE, after isotonic calibration | 0.043 | 0.009 |

Scoring latency (row-by-row, fold 0's test set, n=500): p50 0.95 ms, p95 1.21 ms.

False alarms per 1,000 observations inside protected windows (P(fault)>=0.5, should be
low since these windows are never fault-injected): heatwave_a 11.0/1000 (1,632 obs),
biparjoy_a 4.8/1000 (210 obs), monsoon_c 78.9/1000 (342 obs).

Dataset: 105,216 station-times across 12 stations, 7,065 labelled fault
observations, 2,184 rows inside protected windows.

**Injector (event-count sampling).** Minimum events per class across the 12 stations
(F1 60, F2 40, F3 24, F4 30, F5 30, F6 30, F7 30, F8 60, F9 30; the code uses slightly
higher counts, each class on all 12 stations). Events never overlap each other or protected windows.
Durations (1 step = 3 h): F2 4-24, F3 56-112, F4 8-80, F5 4-80, F9 1-16 steps. Faulty coverage
must be 4-8% with no class above 30% of labelled rows (both tested).
**Documented deviation:** F3 drift lasts 7-14 days, shorter than the spec's 7-45 days, so 24
drift events fit in the coverage budget.

**Folds.** Default `GroupKFold` station assignment was kept: every test fold holds at least 4 events of
every class and every training set at least 18 (per-fold counts and station lists are in
`outputs/metrics.json` under `fold_test_events` and in `outputs/benchmark_report.md`). No reassignment was needed.

**What's still weak:** macro-F1 across the 9 fault classes is well under the spec's 0.90 target
and F3 (drift) and F4 (offset) stay near zero row-level F1 even with adequate event counts;
see `outputs/benchmark_report.md` (event-level recall, per-class ablation) and `SESSION-LOG.md`.
The `monsoon_c` false-alarm rate is high relative to the other two windows and it is the smallest window.

Scope:

- 12 stations: 6 in cluster **(a)** Delhi-NCR/Rajasthan and 6 in cluster **(c)** Maharashtra.
- Cluster (b), edge tier, and LSTM baseline are excluded.
- Future LightGBM models use at most **200 trees**.
- Evaluation uses grouped **5-fold cross-validation by station**.
- Current pipeline cadence is **3-hourly synoptic time**: 00, 03, ..., 21 UTC.

## Retrieval and pressure

Meteostat Python 1.7.6 was queried with `model=False`. No `interpolate()` call, forward-fill, or aggregation was used. Only source observations at exact synoptic timestamps are retained.

Meteostat's `pres` parameter is **Air Pressure (MSL)**, not station pressure. It is retained without conversion and renamed:

> `mslp_hpa`: sea-level pressure (station pressure not available from source)

Sources:

- [Meteostat Python hourly API](https://dev.meteostat.net/python/api/meteostat.hourly)
- [Meteostat meteorological parameters](https://dev.meteostat.net/parameters)
- [Meteostat interpolation documentation](https://dev.meteostat.net/python/interpolation)

## Candidate scan and selection

The full Meteostat station catalog was scanned for Indian stations within 250 km of the Delhi and Pune reference points: **32 Delhi-area candidates** and **29 Pune-area candidates**. The scan included airports/ICAO stations and WMO/synoptic stations. Every candidate was fetched with `model=False` for 2023–2025 and ranked by complete-triplet coverage on the 3-hourly UTC grid.

Selection rule:

- Keep candidates with complete-triplet synoptic coverage **≥50%**.
- Target 5–6 stations per cluster.
- Drop Matheran as requested.
- Use relaxed neighbour eligibility of **distance ≤200 km and elevation difference ≤500 m**.
- No selected station is marked `low_coverage`; the fallback floor of 35% was not needed.

The complete 61-candidate ranking is in [`candidate_synoptic_coverage.csv`](data/clean/candidate_synoptic_coverage.csv).

## Final station quality at synoptic hours

Coverage denominators are the exact 8 synoptic hours per day from 2023-01-01 through 2025-12-31: **8,768 timestamps per station**. Per-variable coverage counts non-null source observations at those exact timestamps; complete-triplet coverage requires all `temp_c`, `mslp_hpa`, and `rh_pct` to be present.

| Cluster | ID | Station | Type | Distance (km) | Native interval | Temp % | MSLP % | RH % | Complete triplet % | Low coverage |
|---|---:|---|---|---:|---|---:|---:|---:|---:|---|
| a | 42181 | New Delhi / Palam | airport/ICAO | 10.30 | hourly | 99.6578 | 99.6008 | 99.6578 | 99.6008 | no |
| a | 42182 | New Delhi / Safdarjung | airport/ICAO | 3.13 | 3-hourly | 85.3330 | 85.3216 | 85.2760 | 85.2418 | no |
| a | 42348 | Jaipur / Sanganer | airport/ICAO | 242.95 | hourly | 99.5324 | 99.5096 | 99.5096 | 99.4868 | no |
| a | 42170 | Churu | WMO | 227.79 | 3-hourly | 85.2760 | 85.1391 | 85.2076 | 85.0707 | no |
| a | 42103 | Ambala | WMO | 204.69 | 3-hourly | 84.7400 | 84.5005 | 84.6943 | 84.3978 | no |
| a | 42131 | Hissar | airport/ICAO | 156.53 | 3-hourly | 83.1889 | 83.0178 | 83.1318 | 82.8809 | no |
| c | 43003 | Bombay / Santacruz | airport/ICAO | 125.31 | hourly | 99.9088 | 99.8974 | 99.9088 | 99.8974 | no |
| c | 43014 | Aurangabad Chikalthan Aerodrome | airport/ICAO | 219.15 | mixed | 97.4339 | 97.3198 | 97.4224 | 97.2970 | no |
| c | 43063 | Poona | WMO | 1.82 | 3-hourly | 85.6182 | 85.5839 | 85.5497 | 85.3901 | no |
| c | 43110 | Ratnagiri | WMO | 179.75 | 3-hourly | 84.3978 | 84.3864 | 84.3864 | 84.3636 | no |
| c | 42921 | Nasik | WMO | 164.77 | 3-hourly | 84.0214 | 83.9644 | 83.9758 | 83.8846 | no |
| c | 43117 | Sholapur | airport/ICAO | 235.57 | 3-hourly | 82.5160 | 82.5502 | 82.5046 | 82.4703 | no |

The final dataset has **105,216 station-times** (12 × 8,768). The 50% complete-triplet threshold is met by every selected station.

## Neighbour list for final stations

Eligibility is **≤200 km and ≤500 m elevation difference**, within the same cluster and final station set. An empty list is valid: the spatial tier must use its sparse-neighbour fallback and lower confidence rather than crash.

| Station | Cluster | Eligible final neighbours |
|---|---|---|
| 42181 New Delhi / Palam | a | 42182 Safdarjung; 42131 Hissar |
| 42182 New Delhi / Safdarjung | a | 42181 Palam; 42131 Hissar |
| 42348 Jaipur / Sanganer | a | 42170 Churu |
| 42170 Churu | a | 42348 Jaipur; 42131 Hissar |
| 42103 Ambala | a | 42131 Hissar |
| 42131 Hissar | a | 42181 Palam; 42182 Safdarjung; 42170 Churu; 42103 Ambala |
| 43003 Bombay / Santacruz | c | none under 200 km/500 m in final set; sparse fallback |
| 43014 Aurangabad Chikalthan Aerodrome | c | 42921 Nasik |
| 43063 Poona | c | 43110 Ratnagiri; 42921 Nasik |
| 43110 Ratnagiri | c | 43063 Poona |
| 42921 Nasik | c | 43014 Aurangabad; 43063 Poona |
| 43117 Sholapur | c | none under 200 km/500 m in final set; sparse fallback |

The two isolated Maharashtra stations remain because they pass the requested 50% coverage rule and are among the six passing Pune-area candidates. Their T3 confidence will be reduced when the engine runs.

## Protected windows — final list, cluster-specific

Fault injection must be blocked only for stations in the corresponding cluster:

| Window | Cluster | UTC interval | Final stations covered | Complete-triplet coverage |
|---|---|---|---:|---|
| `heatwave_a` | a | 2024-05-16 18:30:00Z through 2024-06-19 18:29:59Z | 6/6 | recorded in `protected_window_coverage.csv` |
| `biparjoy_a` | a | 2023-06-16 18:00:00Z inclusive through 2023-06-21 00:00:00Z exclusive | 6/6 | recorded in `protected_window_coverage.csv` |
| `monsoon_c` | c | 2024-07-23 00:00:00Z inclusive through 2024-07-30 00:00:00Z exclusive | 6/6 | recorded in `protected_window_coverage.csv` |

Sources:

1. [IMD, 30 May 2024](https://internal.imd.gov.in/press_release/20240603_pr_3037.pdf) and [PIB, 30 May 2024](https://www.pib.gov.in/PressReleasePage.aspx?PRID=2022186) — northwest heatwave timing and peak Rajasthan conditions.
2. [IMD, 4 June 2024](https://internal.imd.gov.in/press_release/20240604_pr_3038.pdf) and [IMD, 6 June 2024](https://internal.imd.gov.in/press_release/20240606_pr_3041.pdf) — residual and renewed northwest heatwave conditions.
3. [IMD, 17 June 2023](https://internal.imd.gov.in/press_release/20230617_pr_2387.pdf), [18 June 2023](https://internal.imd.gov.in/press_release/20230618_pr_2389.pdf), and [27 June 2023](https://internal.imd.gov.in/press_release/20230627_pr_2398.pdf) — Biparjoy remnants and Rajasthan rainfall.
4. [IMD, 23 July 2024](https://internal.imd.gov.in/press_release/20240723_pr_3109.pdf) and [25 July 2024](https://internal.imd.gov.in/press_release/20240725_pr_3112.pdf) — peak Konkan/Madhya Maharashtra rainfall.

Native gaps are not F7 faults. Future labels will keep source-availability gaps separate from rows deliberately deleted by the injector as F7 dropouts.

## Outputs

- `stations.csv` — final metadata, synoptic coverage, and `low_coverage` flag.
- `data/clean/observations_clean.parquet` — observation-only, 3-hourly clean data.
- `data/clean/missingness_by_station.csv` — per-station quality metrics.
- `data/clean/candidate_synoptic_coverage.csv` — ranked scan of all 61 candidates.
- `data/clean/protected_window_coverage.csv` — final cluster-specific window audit.
- `data/clean/data_summary.json` — machine-readable configuration and totals.
- `reports/data_step_report.md` — concise final report.

## Reproduce

Set up the environment once (uses [uv](https://github.com/astral-sh/uv)):

```bash
uv venv .venv --python 3.11
source .venv/bin/activate
uv pip install -r requirements.txt
```

Then, from the repo root:

```bash
make all    # prepare_data.py (only if data/clean/observations_clean.parquet is missing),
            # then run_step2.py, then pytest
make bench  # just re-run the injector + benchmark (src/run_step2.py)
make test   # just the injector test suite (tests/test_injector.py)
```

The full `make all` run (data step already cached + benchmark + tests) takes about
3.5 minutes on a 12-station, 105k-row dataset. `data/clean/observations_clean.parquet`
is checked in, so `prepare_data.py` (which re-fetches from Meteostat) does not normally
re-run; delete that file if you want to force a refetch.

Outputs regenerated by `make bench`: `outputs/metrics.json`, `outputs/benchmark_report.md`,
`outputs/figures/*.png`, `outputs/alerts_examples.json`, `outputs/scored_stream.parquet`,
`outputs/scored_stream_sample.json`, and `data/bench/{labels,observations_injected}.parquet`.
