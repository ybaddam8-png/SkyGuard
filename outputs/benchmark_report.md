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
| precision | 0.7055 | 0.0485 |
| recall | 0.6852 | 0.0606 |
| f1 | 0.6939 | 0.0443 |
| macro_f1 | 0.5770 | 0.0248 |
| t0_f1 | 0.4914 | 0.0597 |
| iforest_f1 | 0.4295 | 0.0874 |
| trivial_f1 | 0.1268 | 0.0096 |
| ece_raw | 0.0583 | 0.0128 |
| ece_calibrated | 0.0249 | 0.0047 |
| no_T1_f1 | 0.6545 | 0.0352 |
| no_T2_f1 | 0.6846 | 0.0541 |
| no_T3_f1 | 0.6775 | 0.0493 |

## Per-class root-cause F1 (OOF)

| Class | Precision | Recall | F1 |
|---|---:|---:|---:|
| F1 | 0.4021 | 0.5571 | 0.4671 |
| F2 | 0.6122 | 0.6784 | 0.6436 |
| F3 | 0.2100 | 0.0968 | 0.1325 |
| F4 | 0.3020 | 0.2559 | 0.2770 |
| F5 | 0.7172 | 0.8651 | 0.7842 |
| F6 | 0.9093 | 0.9357 | 0.9223 |
| F7 | 0.9877 | 1.0000 | 0.9938 |
| F8 | 0.8406 | 0.8286 | 0.8345 |
| F9 | 0.2019 | 0.1550 | 0.1754 |

Macro-F1 across F1–F9 (OOF): **0.5812**.

## Scoring latency

- p50: 1.422 ms; p95: 2.171 ms (timed row-by-row on fold 0's test set, n=500).

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
| F1 | 70 | 70 | 0.971 | 0.557 | 0.0 |
| F2 | 60 | 60 | 0.950 | 0.950 | 9.0 |
| F3 | 24 | 21 | 0.619 | 0.143 | 21.0 |
| F4 | 36 | 36 | 0.694 | 0.556 | 12.0 |
| F5 | 36 | 36 | 1.000 | 1.000 | 0.0 |
| F6 | 30 | 30 | 1.000 | 0.967 | 0.0 |
| F7 | 36 | 36 | 1.000 | 1.000 | 0.0 |
| F8 | 70 | 70 | 1.000 | 0.829 | 0.0 |
| F9 | 36 | 36 | 0.944 | 0.389 | 3.0 |

F3 median delay from PRD crossing: 3.0 h over 12 detected events that reach the PRD threshold.

## Detectability curve (recall by SNR bin, full model)

| Class | SNR bin | Events | Event recall (any class) | Event recall (class correct) | Row recall (any class) | Row recall (class correct) |
|---|---|---:|---:|---:|---:|---:|
| F3 | <1 | 1 | 1.000 | 0.000 | 0.034 | 0.000 |
| F3 | 1-2 | 7 | 0.286 | 0.143 | 0.448 | 0.184 |
| F3 | 2-4 | 12 | 0.750 | 0.167 | 0.243 | 0.090 |
| F3 | >4 | 1 | 1.000 | 0.000 | 0.027 | 0.000 |
| F3 | >=3 | 5 | 0.600 | 0.000 | 0.050 | 0.000 |
| F4 | <1 | 1 | 0.000 | 0.000 | 0.000 | 0.000 |
| F4 | 1-2 | 9 | 0.667 | 0.556 | 0.157 | 0.099 |
| F4 | 2-4 | 13 | 0.615 | 0.385 | 0.292 | 0.207 |
| F4 | >4 | 13 | 0.846 | 0.769 | 0.496 | 0.451 |
| F4 | >=3 | 19 | 0.842 | 0.684 | 0.387 | 0.329 |
| F5 | <1 | 0 | n/a | n/a | n/a | n/a |
| F5 | 1-2 | 0 | n/a | n/a | n/a | n/a |
| F5 | 2-4 | 0 | n/a | n/a | n/a | n/a |
| F5 | >4 | 36 | 1.000 | 1.000 | 0.955 | 0.865 |
| F5 | >=3 | 36 | 1.000 | 1.000 | 0.955 | 0.865 |

Healthy T3 noise floor (median over stations; 3 sigma of the 56-step mean): temp_c 1.92; mslp_hpa 1.61; rh_pct 13.39.

| Variant | Alerts | Alerts / 1,000 clean steps (outside events, protected windows and native gaps) | Share of alerts inside an injected event |
|---|---:|---:|---:|
| full | 6,226 | 21.60 | 0.707 |
| no_T1 | 5,976 | 23.22 | 0.671 |
| no_T2 | 6,204 | 22.00 | 0.700 |
| no_T3 | 6,501 | 24.62 | 0.679 |

## Ablation (tier columns removed, heads retrained)

| Tier removed | Paired per-fold F1 diff (full − ablated) | Mean | Std | Folds ablated >= full |
|---|---|---:|---:|---:|
| no_T1 | +0.0075, +0.0376, +0.0396, +0.0664, +0.0459 | +0.0394 | 0.0212 | 0/5 |
| no_T2 | +0.0177, +0.0252, +0.0049, -0.0076, +0.0064 | +0.0093 | 0.0126 | 1/5 |
| no_T3 | +0.0348, +0.0143, +0.0457, +0.0139, -0.0267 | +0.0164 | 0.0277 | 1/5 |

| Variant | F1 | F2 | F3 | F4 | F5 | F6 | F7 | F8 | F9 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| full F1 | 0.467 | 0.644 | 0.132 | 0.277 | 0.784 | 0.922 | 0.994 | 0.835 | 0.175 |
| no_T1 F1 | 0.487 | 0.636 | 0.011 | 0.196 | 0.764 | 0.925 | 0.997 | 0.837 | 0.163 |
| no_T2 F1 | 0.425 | 0.614 | 0.161 | 0.277 | 0.768 | 0.912 | 0.997 | 0.845 | 0.158 |
| no_T3 F1 | 0.548 | 0.666 | 0.151 | 0.200 | 0.787 | 0.906 | 0.994 | 0.873 | 0.215 |
| full event recall | 0.971 | 0.950 | 0.619 | 0.694 | 1.000 | 1.000 | 1.000 | 1.000 | 0.944 |
| no_T1 event recall | 0.971 | 0.950 | 0.476 | 0.611 | 1.000 | 1.000 | 1.000 | 0.986 | 0.944 |
| no_T2 event recall | 0.971 | 0.950 | 0.619 | 0.694 | 1.000 | 1.000 | 1.000 | 1.000 | 0.889 |
| no_T3 event recall | 0.971 | 0.950 | 0.714 | 0.722 | 1.000 | 1.000 | 1.000 | 1.000 | 0.944 |
| full class-correct event recall | 0.557 | 0.950 | 0.143 | 0.556 | 1.000 | 0.967 | 1.000 | 0.829 | 0.389 |
| no_T1 class-correct event recall | 0.557 | 0.917 | 0.048 | 0.444 | 1.000 | 0.933 | 1.000 | 0.843 | 0.306 |
| no_T2 class-correct event recall | 0.529 | 0.933 | 0.190 | 0.500 | 1.000 | 1.000 | 1.000 | 0.857 | 0.361 |
| no_T3 class-correct event recall | 0.614 | 0.950 | 0.238 | 0.556 | 1.000 | 0.967 | 1.000 | 0.886 | 0.444 |

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
