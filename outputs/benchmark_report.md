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
| precision | 0.6111 | 0.0690 |
| recall | 0.6393 | 0.0838 |
| f1 | 0.6210 | 0.0563 |
| macro_f1 | 0.5435 | 0.0382 |
| t0_f1 | 0.4734 | 0.0614 |
| iforest_f1 | 0.3939 | 0.0991 |
| trivial_f1 | 0.1268 | 0.0096 |
| ece_raw | 0.0966 | 0.0150 |
| ece_calibrated | 0.0316 | 0.0063 |
| no_T1_f1 | 0.6065 | 0.0586 |
| no_T2_f1 | 0.6139 | 0.0646 |
| no_T3_f1 | 0.6043 | 0.0509 |

## Per-class root-cause F1 (OOF)

| Class | Precision | Recall | F1 |
|---|---:|---:|---:|
| F1 | 0.3153 | 0.5000 | 0.3867 |
| F2 | 0.5751 | 0.6683 | 0.6182 |
| F3 | 0.1109 | 0.0622 | 0.0797 |
| F4 | 0.1431 | 0.1445 | 0.1438 |
| F5 | 0.6620 | 0.8294 | 0.7363 |
| F6 | 0.8874 | 0.8995 | 0.8934 |
| F7 | 0.9938 | 1.0000 | 0.9969 |
| F8 | 0.8472 | 0.8714 | 0.8592 |
| F9 | 0.1885 | 0.1697 | 0.1786 |

Macro-F1 across F1–F9 (OOF): **0.5437**.

## Scoring latency

- p50: 1.087 ms; p95: 1.404 ms (timed row-by-row on fold 0's test set, n=500).

## False alarms in protected windows (P(fault) >= 0.5)

| Window | Observations | False alarms / 1,000 |
|---|---:|---:|
| heatwave_a | 1,609 | 1.24 |
| biparjoy_a | 209 | 4.78 |
| monsoon_c | 311 | 3.22 |

## Evaluation definitions

- **F3 pre-detectable rows.** A drift row counts as a fault (training positive and scored row) only from the first step where the injected error reaches the tolerance (0.5 °C, 5 % RH, 0.5 hPa). Earlier rows (1,108) get sample weight 0 and are excluded from row-level scoring; the event stays in the event table. F3 event detection only counts flags from the tolerance crossing onward. Delay is reported from the tolerance crossing and from the PRD crossing (1 °C, 5 % RH, 1 hPa); a negative PRD delay means the drift was flagged before it reached the PRD threshold.
- **F7 and native gaps.** A missing expected timestamp is a comms fault whatever its cause, and the label file cannot separate injected from native gaps. A deterministic T0 gap rule flags every missing timestamp as F7 (P(fault) = 1). F7 recall is measured on injected gaps; the 11,219 native-gap rows are excluded from all row-level scoring (so from the F7 precision denominator), from the clean-step alert rate and from the protected-window false-alarm rates. F7 recall is therefore 1.0 by construction and says nothing about the learned model.
- **SNR.** F3/F4: injected magnitude / std of the 56-step mean of the station-variable healthy T3 residual. F5: injected noise std / 1-step std of the healthy T3 residual.

## Event-level detection (alongside row-level metrics)

An event counts as detected if any row inside its detectable window has P(fault) >= 0.5. Delay = hours from the start of the detectable window to the first flagged row (detected events only).

| Class | Events | Detectable | Recall | Recall (class correct) | Median delay (h) |
|---|---:|---:|---:|---:|---:|
| F1 | 70 | 70 | 0.957 | 0.500 | 0.0 |
| F2 | 60 | 60 | 0.950 | 0.933 | 12.0 |
| F3 | 24 | 21 | 0.619 | 0.429 | 21.0 |
| F4 | 36 | 36 | 0.639 | 0.444 | 24.0 |
| F5 | 36 | 36 | 1.000 | 1.000 | 0.0 |
| F6 | 30 | 30 | 1.000 | 1.000 | 0.0 |
| F7 | 36 | 36 | 1.000 | 1.000 | 0.0 |
| F8 | 70 | 70 | 1.000 | 0.871 | 0.0 |
| F9 | 36 | 36 | 0.889 | 0.472 | 3.0 |

F3 median delay from PRD crossing: 6.0 h over 13 detected events that reach the PRD threshold.

## Detectability curve (recall by SNR bin, full model)

| Class | SNR bin | Events | Event recall (any class) | Event recall (class correct) | Row recall (any class) | Row recall (class correct) |
|---|---|---:|---:|---:|---:|---:|
| F3 | <1 | 1 | 0.000 | 0.000 | 0.000 | 0.000 |
| F3 | 1-2 | 7 | 0.429 | 0.429 | 0.245 | 0.184 |
| F3 | 2-4 | 12 | 0.750 | 0.417 | 0.173 | 0.038 |
| F3 | >4 | 1 | 1.000 | 1.000 | 0.053 | 0.013 |
| F3 | >=3 | 5 | 0.600 | 0.600 | 0.054 | 0.012 |
| F4 | <1 | 1 | 0.000 | 0.000 | 0.000 | 0.000 |
| F4 | 1-2 | 9 | 0.444 | 0.222 | 0.065 | 0.028 |
| F4 | 2-4 | 13 | 0.692 | 0.462 | 0.185 | 0.122 |
| F4 | >4 | 13 | 0.769 | 0.615 | 0.316 | 0.267 |
| F4 | >=3 | 19 | 0.789 | 0.579 | 0.203 | 0.162 |
| F5 | <1 | 0 | n/a | n/a | n/a | n/a |
| F5 | 1-2 | 0 | n/a | n/a | n/a | n/a |
| F5 | 2-4 | 0 | n/a | n/a | n/a | n/a |
| F5 | >4 | 36 | 1.000 | 1.000 | 0.947 | 0.830 |
| F5 | >=3 | 36 | 1.000 | 1.000 | 0.947 | 0.830 |

Healthy T3 noise floor (median over stations; 3 sigma of the 56-step mean): temp_c 1.92; mslp_hpa 1.61; rh_pct 13.39.

| Variant | Alerts | Alerts / 1,000 clean steps (outside events, protected windows and native gaps) | Share of alerts inside an injected event |
|---|---:|---:|---:|
| full | 6,734 | 30.97 | 0.611 |
| no_T1 | 6,336 | 29.99 | 0.600 |
| no_T2 | 6,912 | 32.81 | 0.598 |
| no_T3 | 6,753 | 31.92 | 0.600 |

## Ablation (tier columns removed, heads retrained)

| Tier removed | Paired per-fold F1 diff (full − ablated) | Mean | Std | Folds ablated >= full |
|---|---|---:|---:|---:|
| no_T1 | -0.0053, +0.0313, +0.0112, +0.0365, -0.0010 | +0.0146 | 0.0188 | 2/5 |
| no_T2 | +0.0179, -0.0003, -0.0101, +0.0091, +0.0192 | +0.0072 | 0.0124 | 2/5 |
| no_T3 | +0.0284, +0.0139, +0.0546, +0.0356, -0.0490 | +0.0167 | 0.0395 | 1/5 |

| Variant | F1 | F2 | F3 | F4 | F5 | F6 | F7 | F8 | F9 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| full F1 | 0.387 | 0.618 | 0.080 | 0.144 | 0.736 | 0.893 | 0.997 | 0.859 | 0.179 |
| no_T1 F1 | 0.369 | 0.612 | 0.012 | 0.099 | 0.744 | 0.899 | 0.997 | 0.857 | 0.112 |
| no_T2 F1 | 0.322 | 0.597 | 0.067 | 0.140 | 0.717 | 0.893 | 0.997 | 0.841 | 0.127 |
| no_T3 F1 | 0.384 | 0.668 | 0.094 | 0.030 | 0.728 | 0.888 | 0.997 | 0.855 | 0.188 |
| full event recall | 0.957 | 0.950 | 0.619 | 0.639 | 1.000 | 1.000 | 1.000 | 1.000 | 0.889 |
| no_T1 event recall | 0.957 | 0.950 | 0.429 | 0.500 | 1.000 | 1.000 | 1.000 | 1.000 | 0.889 |
| no_T2 event recall | 0.957 | 0.950 | 0.714 | 0.583 | 1.000 | 1.000 | 1.000 | 1.000 | 0.917 |
| no_T3 event recall | 0.943 | 0.950 | 0.810 | 0.528 | 1.000 | 1.000 | 1.000 | 1.000 | 0.833 |
| full class-correct event recall | 0.500 | 0.933 | 0.429 | 0.444 | 1.000 | 1.000 | 1.000 | 0.871 | 0.472 |
| no_T1 class-correct event recall | 0.443 | 0.900 | 0.143 | 0.333 | 1.000 | 0.967 | 1.000 | 0.857 | 0.333 |
| no_T2 class-correct event recall | 0.400 | 0.950 | 0.381 | 0.389 | 1.000 | 0.967 | 1.000 | 0.871 | 0.417 |
| no_T3 class-correct event recall | 0.471 | 0.950 | 0.238 | 0.250 | 1.000 | 0.900 | 1.000 | 0.843 | 0.528 |

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
