# SkyGuard AI benchmark report

## Run configuration

- 3-hourly cadence; 1 step = 3 h; lags 1/2/4/8; rolling windows 1/8.
- Grouped 5-fold cross-validation by station; mean and standard deviation reported.
- LightGBM models capped at 200 trees; LSTM and edge skipped under free-plan scope.
- Faults injected outside cluster-specific protected windows; native source gaps are not F7 labels.

## Data and injector

- Injected rows: 131,520; labelled fault observations: 9,976; stations: 15; protected rows: 3,105.
- Label counts: {'weather': 121544, 'F3': 2408, 'F4': 2156, 'F5': 1911, 'F6': 1617, 'F2': 1132, 'F9': 357, 'F7': 219, 'F1': 88, 'F8': 88}.
- Injector samples by event count (min per class: F1 60, F2 40, F3 24, F4 30, F5 30, F6 30, F7 30, F8 60, F9 30; spread over >=8 stations). Durations in steps (1 step = 3 h): F1/F8 1, F2 4–24, F3 56–112, F4 8–80, F5 4–80, F6 4–80, F7 1–8, F9 1–16.
- **Documented deviation:** F3 drift lasts 7–14 days (56–112 steps), shorter than the spec's 7–45 days, so 24 drift events fit in the coverage budget. F9 is back to spec (1–16 steps = 1–48 h). F3 final error follows spec section 6: 0.5–3 °C, 3–15 % RH, 0.5–3 hPa, variable T 45 % / RH 45 % / P 10 % (RH was 0.5–3 % before fix/detectability).
- Root-cause head is trained only on injector-labelled rows plus protected-window weather rows (spec section 8); a row receives a root cause only if the binary head flags it (P(fault) >= 0.5), otherwise "weather".

## Metrics (fold mean ± std)

| Metric | Mean | Std | |
|---|---:|---:|
| precision | 0.7174 | 0.0387 |
| recall | 0.6810 | 0.0491 |
| f1 | 0.6980 | 0.0373 |
| macro_f1 | 0.5969 | 0.0375 |
| t0_f1 | 0.4157 | 0.0363 |
| iforest_f1 | 0.4491 | 0.0396 |
| trivial_f1 | 0.1417 | 0.0106 |
| ece_raw | 0.0825 | 0.0090 |
| ece_calibrated | 0.0248 | 0.0047 |
| no_T1_f1 | 0.6470 | 0.0340 |
| no_T2_f1 | 0.6839 | 0.0314 |
| no_T3_f1 | 0.6678 | 0.0526 |

## Per-class root-cause F1 (OOF)

| Class | Precision | Recall | F1 |
|---|---:|---:|---:|
| F1 | 0.4048 | 0.5795 | 0.4766 |
| F2 | 0.7060 | 0.7447 | 0.7248 |
| F3 | 0.2578 | 0.1597 | 0.1972 |
| F4 | 0.2502 | 0.1776 | 0.2078 |
| F5 | 0.7202 | 0.8713 | 0.7885 |
| F6 | 0.9244 | 0.9450 | 0.9346 |
| F7 | 0.8958 | 1.0000 | 0.9451 |
| F8 | 0.7222 | 0.8864 | 0.7959 |
| F9 | 0.3311 | 0.2745 | 0.3002 |

Macro-F1 across F1–F9 (OOF): **0.5967**.

## Scoring latency

- p50: 1.621 ms; p95: 2.023 ms (timed row-by-row on fold 0's test set, n=500).

## False alarms in protected windows (P(fault) >= 0.5)

| Window | Observations | False alarms / 1,000 |
|---|---:|---:|
| heatwave_a | 2,421 | 3.72 |
| biparjoy_a | 308 | 3.25 |
| monsoon_c | 311 | 0.00 |

## Evaluation definitions

- **F3 pre-detectable rows.** A drift row counts as a fault (training positive and scored row) only from the first step where the injected error reaches the tolerance (0.5 °C, 5 % RH, 0.5 hPa). Earlier rows (1,218) get sample weight 0 and are excluded from row-level scoring; the event stays in the event table. F3 event detection only counts flags from the tolerance crossing onward. Delay is reported from the tolerance crossing and from the PRD crossing (1 °C, 5 % RH, 1 hPa); a negative PRD delay means the drift was flagged before it reached the PRD threshold.
- **F7 and native gaps.** A missing expected timestamp is a comms fault whatever its cause, and the label file cannot separate injected from native gaps. A deterministic T0 gap rule flags every missing timestamp as F7 (P(fault) = 1). F7 recall is measured on injected gaps; the 15,215 native-gap rows are excluded from all row-level scoring (so from the F7 precision denominator), from the clean-step alert rate and from the protected-window false-alarm rates. F7 recall is therefore 1.0 by construction and says nothing about the learned model.
- **SNR.** Detectability tables use MEAN-ERROR SNR: F3 = mean injected error over the event (about half the final magnitude for a ramp) / std of the 56-step mean of the station-variable healthy T3 residual; F4 = offset / same std. A second table uses final-magnitude SNR for F3. F5: injected noise std / 1-step std of the healthy T3 residual.

## Event-level detection (alongside row-level metrics)

An event counts as detected if any row inside its detectable window has P(fault) >= 0.5. Delay = hours from the start of the detectable window to the first flagged row (detected events only).

| Class | Events | Detectable | Recall | Recall (class correct) | Median delay (h) |
|---|---:|---:|---:|---:|---:|
| F1 | 88 | 88 | 0.989 | 0.580 | 0.0 |
| F2 | 75 | 75 | 0.973 | 0.973 | 9.0 |
| F3 | 30 | 29 | 0.828 | 0.483 | 13.5 |
| F4 | 45 | 45 | 0.800 | 0.689 | 12.0 |
| F5 | 45 | 45 | 1.000 | 1.000 | 0.0 |
| F6 | 38 | 38 | 1.000 | 1.000 | 0.0 |
| F7 | 45 | 45 | 1.000 | 1.000 | 0.0 |
| F8 | 88 | 88 | 0.989 | 0.886 | 0.0 |
| F9 | 45 | 45 | 0.867 | 0.600 | 0.0 |

F3 median delay from PRD crossing: 9.0 h over 19 detected events that reach the PRD threshold.

## Detectability curve (recall by MEAN-ERROR SNR bin, full model)

| Class | SNR bin | Events | Event recall (any class) | Event recall (class correct) | Row recall (any class) | Row recall (class correct) |
|---|---|---:|---:|---:|---:|---:|
| F3 | <1 | 15 | 0.733 | 0.400 | 0.162 | 0.095 |
| F3 | 1-2 | 11 | 1.000 | 0.727 | 0.414 | 0.264 |
| F3 | 2-4 | 2 | 0.500 | 0.000 | 0.008 | 0.000 |
| F3 | >4 | 1 | 1.000 | 0.000 | 0.571 | 0.000 |
| F3 | >=3 | 1 | 1.000 | 0.000 | 0.571 | 0.000 |
| F4 | <1 | 7 | 0.857 | 0.714 | 0.463 | 0.298 |
| F4 | 1-2 | 10 | 0.500 | 0.500 | 0.193 | 0.091 |
| F4 | 2-4 | 17 | 0.882 | 0.706 | 0.284 | 0.119 |
| F4 | >4 | 11 | 0.909 | 0.818 | 0.378 | 0.294 |
| F4 | >=3 | 18 | 0.944 | 0.778 | 0.443 | 0.234 |
| F5 | <1 | 0 | n/a | n/a | n/a | n/a |
| F5 | 1-2 | 0 | n/a | n/a | n/a | n/a |
| F5 | 2-4 | 1 | 1.000 | 1.000 | 0.973 | 0.811 |
| F5 | >4 | 44 | 1.000 | 1.000 | 0.957 | 0.873 |
| F5 | >=3 | 45 | 1.000 | 1.000 | 0.957 | 0.871 |

### Same, F3 by FINAL-MAGNITUDE SNR

| Class | SNR bin | Events | Event recall (any class) | Event recall (class correct) | Row recall (any class) | Row recall (class correct) |
|---|---|---:|---:|---:|---:|---:|
| F3 | <1 | 0 | n/a | n/a | n/a | n/a |
| F3 | 1-2 | 15 | 0.733 | 0.400 | 0.162 | 0.095 |
| F3 | 2-4 | 11 | 1.000 | 0.727 | 0.414 | 0.264 |
| F3 | >4 | 3 | 0.667 | 0.000 | 0.130 | 0.000 |
| F3 | >=3 | 7 | 0.857 | 0.571 | 0.380 | 0.241 |

Healthy T3 noise floor (median over stations; 3 sigma of the 56-step mean): temp_c 1.91; mslp_hpa 1.51; rh_pct 13.40.

| Variant | Alerts | Alerts / 1,000 clean steps (outside events, protected windows and native gaps) | Share of alerts inside an injected event |
|---|---:|---:|---:|
| full | 8,526 | 22.87 | 0.722 |
| no_T1 | 7,914 | 24.07 | 0.684 |
| no_T2 | 8,672 | 24.78 | 0.704 |
| no_T3 | 9,202 | 29.29 | 0.669 |

## Ablation (tier columns removed, heads retrained)

| Tier removed | Paired per-fold F1 diff (full − ablated) | Mean | Std | Folds ablated >= full |
|---|---|---:|---:|---:|
| no_T1 | +0.0498, +0.0481, +0.0536, +0.0603, +0.0428 | +0.0509 | 0.0065 | 0/5 |
| no_T2 | +0.0081, +0.0084, +0.0066, +0.0253, +0.0217 | +0.0140 | 0.0088 | 0/5 |
| no_T3 | +0.0457, +0.0512, -0.0083, +0.0297, +0.0326 | +0.0302 | 0.0233 | 1/5 |

| Variant | F1 | F2 | F3 | F4 | F5 | F6 | F7 | F8 | F9 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| full F1 | 0.477 | 0.725 | 0.197 | 0.208 | 0.789 | 0.935 | 0.945 | 0.796 | 0.300 |
| no_T1 F1 | 0.571 | 0.722 | 0.016 | 0.128 | 0.784 | 0.938 | 0.947 | 0.778 | 0.295 |
| no_T2 F1 | 0.454 | 0.724 | 0.196 | 0.224 | 0.802 | 0.929 | 0.945 | 0.819 | 0.216 |
| no_T3 F1 | 0.471 | 0.720 | 0.219 | 0.168 | 0.796 | 0.929 | 0.947 | 0.824 | 0.289 |
| full event recall | 0.989 | 0.973 | 0.828 | 0.800 | 1.000 | 1.000 | 1.000 | 0.989 | 0.867 |
| no_T1 event recall | 0.989 | 0.960 | 0.517 | 0.689 | 1.000 | 1.000 | 1.000 | 0.989 | 0.867 |
| no_T2 event recall | 0.989 | 0.973 | 0.793 | 0.778 | 1.000 | 1.000 | 1.000 | 1.000 | 0.911 |
| no_T3 event recall | 0.989 | 0.973 | 0.828 | 0.667 | 1.000 | 1.000 | 1.000 | 0.989 | 0.889 |
| full class-correct event recall | 0.580 | 0.973 | 0.483 | 0.689 | 1.000 | 1.000 | 1.000 | 0.886 | 0.600 |
| no_T1 class-correct event recall | 0.614 | 0.960 | 0.172 | 0.600 | 0.978 | 0.974 | 1.000 | 0.818 | 0.578 |
| no_T2 class-correct event recall | 0.557 | 0.960 | 0.483 | 0.644 | 0.978 | 0.974 | 1.000 | 0.875 | 0.467 |
| no_T3 class-correct event recall | 0.591 | 0.960 | 0.586 | 0.556 | 1.000 | 1.000 | 1.000 | 0.875 | 0.511 |

## Baselines on the current benchmark (same evaluation definitions, fold mean ± std)

All rows below are scored on the same rows: pre-detectable F3 rows and native gaps excluded.

| Detector | Binary F1 |
|---|---:|
| Fusion (with F7 gap rule) | 0.6980 ± 0.0373 |
| Fusion without the F7 gap rule | 0.6980 ± 0.0373 |
| WMO rules only (T0, incl. gap rule) | 0.4157 ± 0.0363 |
| WMO rules only (T0, no gap rule) | 0.4009 ± 0.0371 |
| Isolation Forest (contamination = training-fold prevalence) | 0.4491 ± 0.0396 |
| Always fault | 0.1417 ± 0.0106 |

| F7 | Injected-gap recall | Precision (native gaps excluded) | Precision (native gaps counted as negatives) | Native-gap rows called F7 |
|---|---:|---:|---:|---:|
| with_gap_rule | 1.000 | 0.896 | 0.014 | 15,215 / 15,215 |
| without_gap_rule | 1.000 | 0.896 | 0.014 | 15,215 / 15,215 |

## Calendar shortcut check and placebo windows

Fusion heads exclude ['hour_sin', 'hour_cos', 'doy_sin', 'doy_cos', 'temp_c_clim_mu', 'mslp_hpa_clim_mu', 'rh_pct_clim_mu']. The with-calendar binary head is refit per fold for comparison only. Placebo windows = each protected window shifted +182 days, in both clusters (faults occur there).

| Window | Obs | Clean alerts/1,000 (no calendar) | Clean alerts/1,000 (with calendar) | Fault rows | Fault-row recall (no calendar) | Fault-row recall (with calendar) |
|---|---:|---:|---:|---:|---:|---:|
| biparjoy_a | 308 | 3.25 | 3.25 | 0 | n/a | n/a |
| heatwave_a | 2,421 | 3.72 | 5.78 | 0 | n/a | n/a |
| monsoon_c | 311 | 0.00 | 3.22 | 0 | n/a | n/a |
| placebo_biparjoy_a_a | 307 | 7.52 | 11.28 | 38 | 0.684 | 0.658 |
| placebo_biparjoy_a_c | 210 | 41.24 | 36.08 | 15 | 1.000 | 1.000 |
| placebo_heatwave_a_a | 2,125 | 12.60 | 14.11 | 118 | 0.441 | 0.449 |
| placebo_heatwave_a_c | 1,442 | 29.48 | 27.27 | 85 | 0.918 | 0.918 |
| placebo_monsoon_c_a | 501 | 4.52 | 4.52 | 59 | 0.492 | 0.492 |
| placebo_monsoon_c_c | 331 | 19.74 | 13.16 | 27 | 0.407 | 0.370 |
| all_other_clean | 98,746 | 23.08 | 21.17 |  | n/a | n/a |

## Natural extremes on clean rows (test folds, fold mean ± std, alerts per 1,000)

Per-station top 0.5 % temp, bottom 0.5 % MSLP, top/bottom 0.5 % 3-step change in any variable; rows with no injected fault and no native gap. Tier columns show the rate when that tier is removed (which tier drives extreme alerts).

| Group | Rows | No calendar (default) | With calendar | Ratio to clean (default) | No T1 | No T2 | No T3 |
|---|---:|---:|---:|---:|---:|---:|---:|
| temp_top0.5pct | 635 | 14.1 ± 16.7 | 18.6 | 0.63 | 20.5 | 17.1 | 35.7 |
| mslp_bottom0.5pct | 585 | 22.5 ± 18.3 | 24.4 | 1.00 | 34.7 | 24.0 | 44.8 |
| change3_top0.5pct_any_var | 1,572 | 53.7 ± 13.6 | 55.3 | 2.39 | 58.4 | 55.9 | 88.4 |
| change3_bottom0.5pct_any_var | 1,619 | 57.5 ± 16.7 | 53.4 | 2.56 | 51.1 | 62.1 | 72.3 |
| any_extreme | 3,963 | 45.5 ± 11.5 | 45.8 | 2.02 | 46.8 | 48.0 | 68.9 |
| all_clean | 106,333 | 22.5 ± 5.8 | 20.7 | 1.00 | 23.5 | 24.3 | 29.0 |

## Fold event counts

Min/max test events per class across folds: {'F1': [17, 18], 'F2': [15, 15], 'F3': [6, 6], 'F4': [9, 9], 'F5': [9, 9], 'F6': [7, 9], 'F7': [9, 9], 'F8': [17, 18], 'F9': [9, 9]}. Min train events per class: {'F1': 70, 'F2': 60, 'F3': 24, 'F4': 36, 'F5': 36, 'F6': 29, 'F7': 36, 'F8': 70, 'F9': 36}. Fold stations (GroupKFold default assignment, no reassignment needed): {'1': ['42170', '42921', '43117'], '2': ['42131', '42348', '43110'], '3': ['42111', '42189', '43063'], '4': ['42103', '42182', '43014'], '5': ['42101', '42181', '43003']}.

## Neighbour policy

Primary links use 200 km / 500 m. Stations with fewer than two primary neighbours use sparse links widened to 300 km / 800 m and a 0.7 T3 confidence multiplier. A station with zero links makes T3 abstain and fusion treats T3 as missing.

## Honest limitations

The benchmark is an injected-data estimate over a small station network (15 stations) with substantial native gaps. Results below specification targets, if any, are reported without tuning them away.

## Figures

- `outputs/figures/per_class_f1.png`
- `outputs/figures/ablation.png`
- `outputs/figures/confusion_matrix.png`
- `outputs/figures/example_fault_spans.png`
- `outputs/figures/heatwave_no_injection.png`
