# SkyGuard AI benchmark report

## Run configuration

- 3-hourly cadence; 1 step = 3 h; lags 1/2/4/8; rolling windows 1/8.
- Grouped 5-fold cross-validation by station; mean and standard deviation reported.
- LightGBM models capped at 200 trees; LSTM and edge skipped under free-plan scope.
- Faults injected outside cluster-specific protected windows; native source gaps are not F7 labels.

## Data and injector

- Injected rows: 105,216; labelled fault observations: 7,413; stations: 12; protected rows: 2,184.
- Label counts: {'weather': 97803, 'F3': 1976, 'F5': 1483, 'F4': 1481, 'F6': 1104, 'F2': 796, 'F9': 271, 'F7': 162, 'F8': 70, 'F1': 70}.
- Injector samples by event count (min per class: F1 60, F2 40, F3 24, F4 30, F5 30, F6 30, F7 30, F8 60, F9 30; spread over >=8 stations). Durations in steps (1 step = 3 h): F1/F8 1, F2 4–24, F3 56–112, F4 8–80, F5 4–80, F6 4–80, F7 1–8, F9 1–16.
- **Documented deviation:** F3 drift lasts 7–14 days (56–112 steps), shorter than the spec's 7–45 days, so 24 drift events fit in the coverage budget. F9 is back to spec (1–16 steps = 1–48 h). F3 final error follows spec section 6: 0.5–3 °C, 3–15 % RH, 0.5–3 hPa, variable T 45 % / RH 45 % / P 10 % (RH was 0.5–3 % before fix/detectability).
- Root-cause head is trained only on injector-labelled rows plus protected-window weather rows (spec section 8); a row receives a root cause only if the binary head flags it (P(fault) >= 0.5), otherwise "weather".

## Metrics (fold mean ± std)

| Metric | Mean | Std | |
|---|---:|---:|
| precision | 0.6975 | 0.0659 |
| recall | 0.6937 | 0.0603 |
| f1 | 0.6941 | 0.0527 |
| macro_f1 | 0.5852 | 0.0413 |
| t0_f1 | 0.4914 | 0.0597 |
| iforest_f1 | 0.4272 | 0.0897 |
| trivial_f1 | 0.1268 | 0.0096 |
| ece_raw | 0.0639 | 0.0123 |
| ece_calibrated | 0.0247 | 0.0056 |
| no_T1_f1 | 0.6558 | 0.0467 |
| no_T2_f1 | 0.6846 | 0.0645 |
| no_T3_f1 | 0.6812 | 0.0575 |

## Per-class root-cause F1 (OOF)

| Class | Precision | Recall | F1 |
|---|---:|---:|---:|
| F1 | 0.3711 | 0.5143 | 0.4311 |
| F2 | 0.6123 | 0.6985 | 0.6526 |
| F3 | 0.2246 | 0.1198 | 0.1563 |
| F4 | 0.3068 | 0.2782 | 0.2918 |
| F5 | 0.7144 | 0.8705 | 0.7848 |
| F6 | 0.9089 | 0.9393 | 0.9238 |
| F7 | 0.9877 | 1.0000 | 0.9938 |
| F8 | 0.8507 | 0.8143 | 0.8321 |
| F9 | 0.2398 | 0.1956 | 0.2154 |

Macro-F1 across F1–F9 (OOF): **0.5869**.

## Scoring latency

- p50: 1.302 ms; p95: 1.638 ms (timed row-by-row on fold 0's test set, n=500).

## False alarms in protected windows (P(fault) >= 0.5)

| Window | Observations | False alarms / 1,000 |
|---|---:|---:|
| heatwave_a | 1,609 | 1.86 |
| biparjoy_a | 209 | 0.00 |
| monsoon_c | 311 | 0.00 |

## Evaluation definitions

- **F3 pre-detectable rows.** A drift row counts as a fault (training positive and scored row) only from the first step where the injected error reaches the tolerance (0.5 °C, 5 % RH, 0.5 hPa). Earlier rows (1,108) get sample weight 0 and are excluded from row-level scoring; the event stays in the event table. F3 event detection only counts flags from the tolerance crossing onward. Delay is reported from the tolerance crossing and from the PRD crossing (1 °C, 5 % RH, 1 hPa); a negative PRD delay means the drift was flagged before it reached the PRD threshold.
- **F7 and native gaps.** A missing expected timestamp is a comms fault whatever its cause, and the label file cannot separate injected from native gaps. A deterministic T0 gap rule flags every missing timestamp as F7 (P(fault) = 1). F7 recall is measured on injected gaps; the 11,219 native-gap rows are excluded from all row-level scoring (so from the F7 precision denominator), from the clean-step alert rate and from the protected-window false-alarm rates. F7 recall is therefore 1.0 by construction and says nothing about the learned model.
- **SNR.** F3/F4: injected magnitude / std of the 56-step mean of the station-variable healthy T3 residual. F5: injected noise std / 1-step std of the healthy T3 residual.

## Event-level detection (alongside row-level metrics)

An event counts as detected if any row inside its detectable window has P(fault) >= 0.5. Delay = hours from the start of the detectable window to the first flagged row (detected events only).

| Class | Events | Detectable | Recall | Recall (class correct) | Median delay (h) |
|---|---:|---:|---:|---:|---:|
| F1 | 70 | 70 | 0.986 | 0.514 | 0.0 |
| F2 | 60 | 60 | 0.950 | 0.950 | 9.0 |
| F3 | 24 | 21 | 0.714 | 0.286 | 15.0 |
| F4 | 36 | 36 | 0.722 | 0.556 | 10.5 |
| F5 | 36 | 36 | 1.000 | 0.972 | 0.0 |
| F6 | 30 | 30 | 1.000 | 0.967 | 0.0 |
| F7 | 36 | 36 | 1.000 | 1.000 | 0.0 |
| F8 | 70 | 70 | 1.000 | 0.814 | 0.0 |
| F9 | 36 | 36 | 0.944 | 0.417 | 3.0 |

F3 median delay from PRD crossing: 4.5 h over 14 detected events that reach the PRD threshold.

## Detectability curve (recall by SNR bin, full model)

| Class | SNR bin | Events | Event recall (any class) | Event recall (class correct) | Row recall (any class) | Row recall (class correct) |
|---|---|---:|---:|---:|---:|---:|
| F3 | <1 | 1 | 1.000 | 0.000 | 0.034 | 0.000 |
| F3 | 1-2 | 7 | 0.429 | 0.429 | 0.454 | 0.239 |
| F3 | 2-4 | 12 | 0.833 | 0.250 | 0.246 | 0.108 |
| F3 | >4 | 1 | 1.000 | 0.000 | 0.187 | 0.000 |
| F3 | >=3 | 5 | 0.800 | 0.200 | 0.120 | 0.004 |
| F4 | <1 | 1 | 0.000 | 0.000 | 0.000 | 0.000 |
| F4 | 1-2 | 9 | 0.667 | 0.556 | 0.207 | 0.157 |
| F4 | 2-4 | 13 | 0.615 | 0.385 | 0.286 | 0.195 |
| F4 | >4 | 13 | 0.923 | 0.769 | 0.526 | 0.498 |
| F4 | >=3 | 19 | 0.895 | 0.684 | 0.408 | 0.353 |
| F5 | <1 | 0 | n/a | n/a | n/a | n/a |
| F5 | 1-2 | 0 | n/a | n/a | n/a | n/a |
| F5 | 2-4 | 0 | n/a | n/a | n/a | n/a |
| F5 | >4 | 36 | 1.000 | 0.972 | 0.958 | 0.871 |
| F5 | >=3 | 36 | 1.000 | 0.972 | 0.958 | 0.871 |

Healthy T3 noise floor (median over stations; 3 sigma of the 56-step mean): temp_c 1.92; mslp_hpa 1.61; rh_pct 13.39.

| Variant | Alerts | Alerts / 1,000 clean steps (outside events, protected windows and native gaps) | Share of alerts inside an injected event |
|---|---:|---:|---:|
| full | 6,420 | 23.29 | 0.693 |
| no_T1 | 6,233 | 25.24 | 0.658 |
| no_T2 | 6,540 | 24.81 | 0.679 |
| no_T3 | 6,835 | 26.75 | 0.669 |

## Ablation (tier columns removed, heads retrained)

| Tier removed | Paired per-fold F1 diff (full − ablated) | Mean | Std | Folds ablated >= full |
|---|---|---:|---:|---:|
| no_T1 | -0.0030, +0.0456, +0.0407, +0.0898, +0.0184 | +0.0383 | 0.0347 | 1/5 |
| no_T2 | +0.0292, +0.0125, -0.0037, +0.0028, +0.0065 | +0.0095 | 0.0125 | 1/5 |
| no_T3 | +0.0357, +0.0060, +0.0329, +0.0237, -0.0339 | +0.0129 | 0.0286 | 1/5 |

| Variant | F1 | F2 | F3 | F4 | F5 | F6 | F7 | F8 | F9 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| full F1 | 0.431 | 0.653 | 0.156 | 0.292 | 0.785 | 0.924 | 0.994 | 0.832 | 0.215 |
| no_T1 F1 | 0.473 | 0.659 | 0.013 | 0.238 | 0.771 | 0.928 | 0.994 | 0.853 | 0.206 |
| no_T2 F1 | 0.465 | 0.651 | 0.171 | 0.291 | 0.776 | 0.917 | 0.997 | 0.843 | 0.164 |
| no_T3 F1 | 0.541 | 0.692 | 0.186 | 0.237 | 0.789 | 0.930 | 0.994 | 0.886 | 0.221 |
| full event recall | 0.986 | 0.950 | 0.714 | 0.722 | 1.000 | 1.000 | 1.000 | 1.000 | 0.944 |
| no_T1 event recall | 0.986 | 0.950 | 0.476 | 0.611 | 1.000 | 1.000 | 1.000 | 1.000 | 0.972 |
| no_T2 event recall | 0.971 | 0.950 | 0.762 | 0.694 | 1.000 | 1.000 | 1.000 | 1.000 | 0.861 |
| no_T3 event recall | 0.971 | 0.950 | 0.762 | 0.778 | 1.000 | 1.000 | 1.000 | 1.000 | 0.944 |
| full class-correct event recall | 0.514 | 0.950 | 0.286 | 0.556 | 0.972 | 0.967 | 1.000 | 0.814 | 0.417 |
| no_T1 class-correct event recall | 0.557 | 0.950 | 0.143 | 0.500 | 0.972 | 0.933 | 1.000 | 0.829 | 0.417 |
| no_T2 class-correct event recall | 0.529 | 0.950 | 0.286 | 0.583 | 1.000 | 0.967 | 1.000 | 0.843 | 0.361 |
| no_T3 class-correct event recall | 0.571 | 0.950 | 0.381 | 0.722 | 1.000 | 1.000 | 1.000 | 0.886 | 0.528 |

## Calendar shortcut check and placebo windows

Fusion heads exclude ['hour_sin', 'hour_cos', 'doy_sin', 'doy_cos', 'temp_c_clim_mu', 'mslp_hpa_clim_mu', 'rh_pct_clim_mu']. The with-calendar binary head is refit per fold for comparison only. Placebo windows = each protected window shifted +182 days, in both clusters (faults occur there).

| Window | Obs | Clean alerts/1,000 (no calendar) | Clean alerts/1,000 (with calendar) | Fault rows | Fault-row recall (no calendar) | Fault-row recall (with calendar) |
|---|---:|---:|---:|---:|---:|---:|
| biparjoy_a | 209 | 0.00 | 0.00 | 0 | n/a | n/a |
| heatwave_a | 1,609 | 1.86 | 1.86 | 0 | n/a | n/a |
| monsoon_c | 311 | 0.00 | 0.00 | 0 | n/a | n/a |
| placebo_biparjoy_a_a | 208 | 9.62 | 9.62 | 0 | n/a | n/a |
| placebo_biparjoy_a_c | 210 | 20.27 | 13.51 | 62 | 0.548 | 0.403 |
| placebo_heatwave_a_a | 1,442 | 16.83 | 13.90 | 75 | 0.493 | 0.347 |
| placebo_heatwave_a_c | 1,442 | 22.10 | 14.21 | 110 | 0.718 | 0.745 |
| placebo_monsoon_c_a | 337 | 3.36 | 3.36 | 33 | 0.242 | 0.364 |
| placebo_monsoon_c_c | 331 | 12.35 | 9.26 | 7 | 0.000 | 0.000 |
| all_other_clean | 80,844 | 23.58 | 22.01 |  | n/a | n/a |

## Natural extremes on clean rows (test folds, fold mean ± std, alerts per 1,000)

Per-station top 0.5 % temp, bottom 0.5 % MSLP, top/bottom 0.5 % 3-step change in any variable; rows with no injected fault and no native gap. Tier columns show the rate when that tier is removed (which tier drives extreme alerts).

| Group | Rows | No calendar (default) | With calendar | Ratio to clean (default) | No T1 | No T2 | No T3 |
|---|---:|---:|---:|---:|---:|---:|---:|
| temp_top0.5pct | 519 | 7.4 ± 10.3 | 8.9 | 0.33 | 13.2 | 10.6 | 12.1 |
| mslp_bottom0.5pct | 487 | 13.5 ± 13.3 | 14.2 | 0.60 | 14.0 | 12.3 | 18.2 |
| change3_top0.5pct_any_var | 1,308 | 54.7 ± 21.0 | 45.4 | 2.44 | 62.1 | 46.0 | 63.0 |
| change3_bottom0.5pct_any_var | 1,372 | 44.8 ± 17.7 | 40.6 | 1.99 | 50.8 | 46.9 | 52.5 |
| any_extreme | 3,311 | 40.0 ± 13.0 | 35.1 | 1.78 | 45.7 | 37.3 | 47.6 |
| all_clean | 86,585 | 22.5 ± 8.1 | 21.0 | 1.00 | 25.1 | 23.8 | 26.0 |

## Fold event counts

Min/max test events per class across folds: {'F1': [11, 18], 'F2': [10, 15], 'F3': [4, 6], 'F4': [6, 9], 'F5': [6, 9], 'F6': [4, 8], 'F7': [6, 9], 'F8': [12, 18], 'F9': [6, 9]}. Min train events per class: {'F1': 52, 'F2': 45, 'F3': 18, 'F4': 27, 'F5': 27, 'F6': 22, 'F7': 27, 'F8': 52, 'F9': 27}. Fold stations (GroupKFold default assignment, no reassignment needed): {'1': ['42131', '42921', '43117'], '2': ['42103', '42348', '43110'], '3': ['42182', '43063'], '4': ['42181', '43014'], '5': ['42170', '43003']}.

## Neighbour policy

Primary links use 200 km / 500 m. Stations with fewer than two primary neighbours use sparse links widened to 300 km / 800 m and a 0.7 T3 confidence multiplier. A station with zero links makes T3 abstain and fusion treats T3 as missing.

## Honest limitations

The benchmark is an injected-data estimate over a small 12-station network with substantial native gaps. Results below specification targets, if any, are reported without tuning them away.

## Figures

- `outputs/figures/per_class_f1.png`
- `outputs/figures/ablation.png`
- `outputs/figures/confusion_matrix.png`
- `outputs/figures/example_fault_spans.png`
- `outputs/figures/heatwave_no_injection.png`
