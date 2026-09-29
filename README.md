# SkyGuard AI — SIH26073 Engine

## Status

The data step (`src/prepare_data.py`), the fault injector (`src/skyguard_inject.py`), and
the tiered anomaly-detection benchmark (`src/run_step2.py`: T0-T3 features, LightGBM
fusion model, root-cause classifier, isotonic calibration, SHAP explanations, and
T2/T3-blended imputation) have all been run. `outputs/metrics.json` and
`outputs/benchmark_report.md` are real results from this pipeline, not placeholders.

Current benchmark (default 15-station set, 5-fold grouped-by-station CV, fold mean ± std;
regenerate with `make bench`). **Not like-for-like with earlier numbers:** the station set, the
evaluation definitions (F7 gap rule, F3 pre-detectable rows, native gaps excluded) and the injector
changed across fix/slow-faults and fix/detectability; see `SESSION-LOG.md` for each step.

| Metric | Mean | Std |
|---|---:|---:|
| Fusion model F1 (binary fault/no-fault, threshold 0.5) | 0.698 | 0.037 |
| Fusion model F1 at the training-fold threshold (alerts <= 2 % of clean training steps) | 0.699 | 0.040 |
| AUC-PR | 0.752 | 0.048 |
| Macro-F1 across F1-F9 (fold mean) | 0.597 | 0.037 |
| WMO-rules (T0-only, incl. gap rule) baseline F1 | 0.416 | 0.036 |
| Isolation Forest baseline F1 | 0.449 | 0.040 |
| "Always fault" trivial baseline F1 | 0.142 | 0.011 |
| ECE, raw probabilities | 0.083 | 0.009 |
| ECE, after isotonic calibration | 0.025 | 0.005 |

Scoring latency (row-by-row, fold 0's test set, n=500): p50 1.48 ms, p95 1.96 ms.

False alarms per 1,000 observations inside protected windows (P(fault)>=0.5, native-gap rows
excluded): heatwave_a 3.7/1000 (2,421 obs), biparjoy_a 3.2/1000 (308 obs), monsoon_c 0.0/1000 (311 obs).
These windows sit far from any injected event, so they never see the post-event spillover of the
causal rolling features; do not read them as the general false-alarm rate. Alerts per 1,000 clean
steps (outside events, protected windows and native gaps): 22.9
at 0.5 and 23.3 at the training-fold threshold (target 20; not met on test folds).

The coherent-event gate (spec section 8) is implemented but NOT applied: it cut fault recall
0.681 -> 0.620 while lowering heatwave false alarms only
3.7 -> 2.9 per 1,000 (revert rule).

Dataset: 131,520 station-times across 15 stations, 9,976 labelled fault
observations, 3,105 rows inside protected windows.

**Healthy-period baseline.** Every T1, T2 and T3 residual is centred and scaled by that
station-variable's own mean and std on the clean base (never neighbours', labels or injected
values) before the causal slow-signal features are computed (rolling means 8/24/56, level change,
least-squares slope 24/56, two-sided CUSUM k=0.5, h=5 with reset). T2 is a pure cross-variable
LightGBM quantile model (no own lags or rolling stats of the target).

**Injector (event-count sampling).** Minimum events per class across the 12 stations
(F1 60, F2 40, F3 24, F4 30, F5 30, F6 30, F7 30, F8 60, F9 30; the code uses slightly
higher counts, each class on all 12 stations). Events never overlap each other or protected windows.
Durations (1 step = 3 h): F2 4-24, F3 56-112, F4 8-80, F5 4-80, F9 1-16 steps. Faulty coverage
must be 4-8% with no class above 30% of labelled rows (both tested).
**Documented deviation:** F3 drift lasts 7-14 days, shorter than the spec's 7-45 days, so 24
drift events fit in the coverage budget.

**Evaluation definitions (fix/detectability).**
- F3 drift rows count as a fault (training positive and scored row) only from the first step where
  the injected error reaches the tolerance (0.5 °C, 5 % RH, 0.5 hPa). Earlier rows are
  "pre-detectable": sample weight 0 in training, excluded from row-level scoring, kept in the event
  table. F3 event detection counts flags from the tolerance crossing onward; delay is reported from
  the tolerance crossing and from the PRD crossing (1 °C, 5 % RH, 1 hPa).
- A missing expected timestamp is a comms fault whatever its cause, and the label file cannot
  separate injected from native gaps. A deterministic T0 gap rule flags every missing timestamp
  as F7. F7 recall is measured on injected gaps and is 1.0 by construction; native-gap rows are
  excluded from all row-level scoring (including the F7 precision denominator), from the
  clean-step alert rate and from protected-window false-alarm rates.
- The F3 injector magnitude now follows spec section 6 (0.5-3 °C, 3-15 % RH, 0.5-3 hPa; T and RH
  mainly, P 10 %). RH drift was 0.5-3 % before, below spec and below the RH noise floor.

**Folds.** Default `GroupKFold` station assignment was kept: every test fold holds at least 4 events of
every class and every training set at least 18 (per-fold counts and station lists are in
`outputs/metrics.json` under `fold_test_events` and in `outputs/benchmark_report.md`). No reassignment was needed.

**What's still weak:** macro-F1 (~0.60) is far under the spec's 0.90 target. F3 drift F1 is
~0.20 (class-correct event recall 0.48): most spec drifts sit near the T3 noise floor. F4 offset F1
~0.21 and F9 ~0.30. F1 spikes are explained by T0 rules (step flag), not T1, in 91 % of alerts.
F7's ~0.95 F1 rests on excluding native gaps from scoring (precision 0.014 if they count as
negatives). Clean-step alert rate (~23 per 1,000) stays above the 2 % target even at the
training-fold threshold. Alert witness sentences can cite a large 24-step slow-signal mean that
is spillover from a nearby injected sentinel. See `SESSION-LOG.md` and `outputs/benchmark_report.md`.

Scope:

- Default benchmark: 15 stations (fix/detectability Stage D; was 12): 9 in cluster **(a)**
  Delhi-NCR/Rajasthan and 6 in cluster **(c)** Maharashtra, all with complete-triplet synoptic
  coverage >= 50 % (`in_default_set` in `stations.csv`). `stations.csv` keeps 20 rows: cluster (c)
  had only 6 candidates at >= 50 %, so the 35 % fallback added 5 `low_coverage` stations (43157
  Kolhapur, 43002 Bombay/Juhu, 43001 Dahanu, 43109 Harnai, 43057 Bombay/Colaba). They are an opt-in
  comparison only (`SKYGUARD_ALL_STATIONS=1`, see "Station-set comparison"). Selection is automatic
  from `data/clean/candidate_synoptic_coverage.csv` in `src/prepare_data.py`. Re-fetched data for
  the original 12 stations is identical to the previous fetch. Cadence is pinned to 3-hourly
  (config). Injector event counts scale with station count; per-class minimums are unchanged.
- Cluster (b), edge tier, and LSTM baseline are excluded.
- Future LightGBM models use at most **200 trees**.
- Evaluation uses grouped **5-fold cross-validation by station**.
- Current pipeline cadence is **3-hourly synoptic time**: 00, 03, ..., 21 UTC.

## Station-set comparison

Default benchmark = 15 stations (the 12 original plus 3 new stations with complete-triplet synoptic coverage >= 50 %).
The 20-station set adds the 5 `low_coverage` stations of cluster (c) (35 % floor) and is opt-in: `SKYGUARD_ALL_STATIONS=1 make bench`
writes to `outputs/all_stations/` and `data/bench/all_stations/`. The default was fixed in advance on two grounds: the 35 % floor was
a fallback, and the 15-station binary F1 is within 0.03 of the 12-station Stage C result. **Caveat:** the two sets differ by exactly
the 5 low-coverage stations, but the grouped fold assignment and the injected events (counts scale with station count) also shift,
so differences are not only a station-quality effect. Numbers below are copied from the two `metrics.json` files.

| Metric | 15 stations (default) | 20 stations |
|---|---:|---:|
| Binary F1 | 0.698 ± 0.037 | 0.651 ± 0.027 |
| Precision | 0.717 ± 0.039 | 0.629 ± 0.069 |
| Recall | 0.681 ± 0.049 | 0.682 ± 0.041 |
| Macro-F1 (OOF) | 0.597 | 0.592 |
| Alerts / 1,000 clean steps | 22.87 | 33.28 |
| False alarms / 1,000, heatwave_a | 3.72 (2,421 obs) | 9.09 (2,421 obs) |
| False alarms / 1,000, biparjoy_a | 3.25 (308 obs) | 6.49 (308 obs) |
| False alarms / 1,000, monsoon_c | 0.00 (311 obs) | 20.04 (449 obs) |
| Labelled fault rows | 9,976 | 10,942 |

| Class | F1, 15 stations | F1, 20 stations | Class-correct event recall, 15 | Class-correct event recall, 20 |
|---|---:|---:|---:|---:|
| F1 | 0.477 | 0.558 | 0.580 | 0.573 |
| F2 | 0.725 | 0.580 | 0.973 | 0.890 |
| F3 | 0.197 | 0.164 | 0.483 | 0.487 |
| F4 | 0.208 | 0.300 | 0.689 | 0.733 |
| F5 | 0.789 | 0.758 | 1.000 | 0.967 |
| F6 | 0.935 | 0.944 | 1.000 | 1.000 |
| F7 | 0.945 | 0.975 | 1.000 | 1.000 |
| F8 | 0.796 | 0.797 | 0.886 | 0.821 |
| F9 | 0.300 | 0.255 | 0.600 | 0.600 |

Ablation (paired per-fold binary F1 difference, full minus tier removed):

| Tier removed | 15 stations (per fold; mean; folds ablated >= full) | 20 stations |
|---|---|---|
| no_T1 | +0.050, +0.048, +0.054, +0.060, +0.043; +0.051; 0/5 | +0.014, +0.081, +0.091, +0.046, +0.117; +0.070; 0/5 |
| no_T2 | +0.008, +0.008, +0.007, +0.025, +0.022; +0.014; 0/5 | +0.008, +0.028, +0.008, +0.017, +0.020; +0.016; 0/5 |
| no_T3 | +0.046, +0.051, -0.008, +0.030, +0.033; +0.030; 1/5 | +0.048, +0.041, +0.040, +0.044, +0.029; +0.040; 0/5 |

Neighbour count per station (links used by T3; 12 stations = before Stage D):

| Station | 12 stations | 15 stations | 20 stations |
|---|---:|---:|---:|
| 42181 | 2 | 2 | 2 |
| 42348 | 4 | 4 | 4 |
| 42182 | 2 | 2 | 2 |
| 42170 | 2 | 2 | 2 |
| 42101 | - | 3 | 3 |
| 42189 | - | 3 | 3 |
| 42103 | 4 | 3 | 3 |
| 42111 | - | 2 | 2 |
| 42131 | 4 | 5 | 5 |
| 43003 | 4 | 4 | 4 |
| 43014 | 4 | 4 | 7 |
| 43063 | 2 | 2 | 2 |
| 43110 | 3 | 3 | 3 |
| 42921 | 2 | 2 | 2 |
| 43117 | 3 | 3 | 5 |
| 43157 | - | - | 5 |
| 43002 | - | - | 4 |
| 43001 | - | - | 3 |
| 43109 | - | - | 4 |
| 43057 | - | - | 4 |

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
