# SkyGuard AI benchmark report

## Run configuration

- 3-hourly cadence; 1 step = 3 h; lags 1/2/4/8; rolling windows 1/8.
- Grouped 5-fold cross-validation by station; mean and standard deviation reported.
- LightGBM models capped at 200 trees; LSTM and edge skipped under free-plan scope.
- Faults injected outside cluster-specific protected windows; native source gaps are not F7 labels.

## Data and injector

- Injected rows: 105,216; labelled fault observations: 7,065; stations: 12; protected rows: 2,184.
- Label counts: {'weather': 98151, 'F3': 1887, 'F5': 1488, 'F4': 1372, 'F6': 933, 'F2': 836, 'F9': 262, 'F7': 147, 'F1': 70, 'F8': 70}.
- Injector samples by event count (min per class: F1 60, F2 40, F3 24, F4 30, F5 30, F6 30, F7 30, F8 60, F9 30; spread over >=8 stations). Durations in steps (1 step = 3 h): F1/F8 1, F2 4–24, F3 56–112, F4 8–80, F5 4–80, F6 4–80, F7 1–8, F9 1–16.
- **Documented deviation:** F3 drift lasts 7–14 days (56–112 steps), shorter than the spec's 7–45 days, so 24 drift events fit in the coverage budget. F9 is back to spec (1–16 steps = 1–48 h).
- Root-cause head is trained only on injector-labelled rows plus protected-window weather rows (spec section 8); a row receives a root cause only if the binary head flags it (P(fault) >= 0.5), otherwise "weather".

## Metrics (fold mean ± std)

| Metric | Mean | Std | |
|---|---:|---:|
| precision | 0.4748 | 0.0884 |
| recall | 0.5009 | 0.0660 |
| f1 | 0.4838 | 0.0662 |
| macro_f1 | 0.4396 | 0.0303 |
| t0_f1 | 0.4125 | 0.0632 |
| iforest_f1 | 0.2298 | 0.0535 |
| trivial_f1 | 0.1262 | 0.0060 |
| ece_raw | 0.1269 | 0.0142 |
| ece_calibrated | 0.0434 | 0.0089 |
| no_T1_f1 | 0.4567 | 0.0765 |
| no_T2_f1 | 0.4753 | 0.0670 |
| no_T3_f1 | 0.4741 | 0.0511 |

## Per-class root-cause F1 (OOF)

| Class | Precision | Recall | F1 |
|---|---:|---:|---:|
| F1 | 0.4352 | 0.6714 | 0.5281 |
| F2 | 0.6405 | 0.6627 | 0.6514 |
| F3 | 0.0150 | 0.0164 | 0.0157 |
| F4 | 0.0639 | 0.0583 | 0.0610 |
| F5 | 0.7098 | 0.7628 | 0.7353 |
| F6 | 0.8309 | 0.9057 | 0.8667 |
| F7 | 0.0702 | 0.1973 | 0.1036 |
| F8 | 0.6867 | 0.8143 | 0.7451 |
| F9 | 0.1946 | 0.1908 | 0.1927 |

Macro-F1 across F1–F9 (OOF): **0.4333**.

## Scoring latency

- p50: 0.949 ms; p95: 1.215 ms (timed row-by-row on fold 0's test set, n=500).

## False alarms in protected windows (P(fault) >= 0.5)

| Window | Observations | False alarms / 1,000 |
|---|---:|---:|
| heatwave_a | 1,632 | 11.03 |
| biparjoy_a | 210 | 4.76 |
| monsoon_c | 342 | 78.95 |

## Event-level detection (alongside row-level metrics)

An event counts as detected if any row inside it has P(fault) >= 0.5. Delay = hours from event start to first flagged row (detected events only).

| Class | Events | Recall | Recall (class correct) | Median delay (h) |
|---|---:|---:|---:|---:|
| F1 | 70 | 0.971 | 0.671 | 0.0 |
| F2 | 60 | 0.983 | 0.933 | 12.0 |
| F3 | 24 | 0.792 | 0.250 | 81.0 |
| F4 | 36 | 0.694 | 0.417 | 18.0 |
| F5 | 36 | 1.000 | 0.972 | 0.0 |
| F6 | 30 | 1.000 | 1.000 | 0.0 |
| F7 | 36 | 0.250 | 0.250 | 3.0 |
| F8 | 70 | 0.986 | 0.814 | 0.0 |
| F9 | 36 | 0.806 | 0.417 | 3.0 |

| Variant | Alerts | Alerts / 1,000 steps outside events and protected windows | Share of alerts inside an injected event |
|---|---:|---:|---:|
| full | 7,846 | 44.13 | 0.454 |
| no_T1 | 7,796 | 45.58 | 0.433 |
| no_T2 | 7,991 | 45.99 | 0.444 |
| no_T3 | 8,675 | 51.07 | 0.427 |

## Ablation (tier columns removed, heads retrained)

| Tier removed | Paired per-fold F1 diff (full − ablated) | Mean | Std | Folds ablated >= full |
|---|---|---:|---:|---:|
| no_T1 | +0.0094, +0.0145, +0.0268, +0.0235, +0.0615 | +0.0272 | 0.0204 | 0/5 |
| no_T2 | +0.0035, -0.0068, +0.0180, +0.0134, +0.0147 | +0.0086 | 0.0101 | 1/5 |
| no_T3 | -0.0100, +0.0019, +0.0863, -0.0204, -0.0091 | +0.0097 | 0.0435 | 3/5 |

| Variant | F1 | F2 | F3 | F4 | F5 | F6 | F7 | F8 | F9 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| full F1 | 0.528 | 0.651 | 0.016 | 0.061 | 0.735 | 0.867 | 0.104 | 0.745 | 0.193 |
| no_T1 F1 | 0.604 | 0.643 | 0.002 | 0.045 | 0.727 | 0.869 | 0.114 | 0.784 | 0.130 |
| no_T2 F1 | 0.452 | 0.630 | 0.018 | 0.068 | 0.722 | 0.854 | 0.133 | 0.748 | 0.166 |
| no_T3 F1 | 0.453 | 0.646 | 0.032 | 0.058 | 0.721 | 0.859 | 0.105 | 0.734 | 0.171 |
| full event recall | 0.971 | 0.983 | 0.792 | 0.694 | 1.000 | 1.000 | 0.250 | 0.986 | 0.806 |
| no_T1 event recall | 0.971 | 0.983 | 0.542 | 0.528 | 1.000 | 1.000 | 0.306 | 0.971 | 0.778 |
| no_T2 event recall | 0.971 | 0.983 | 0.708 | 0.722 | 1.000 | 1.000 | 0.333 | 0.986 | 0.806 |
| no_T3 event recall | 0.971 | 0.983 | 0.750 | 0.667 | 1.000 | 1.000 | 0.361 | 0.986 | 0.833 |

## Fold event counts

Min/max test events per class across folds: {'F1': [11, 18], 'F2': [10, 15], 'F3': [4, 6], 'F4': [6, 9], 'F5': [6, 9], 'F6': [5, 8], 'F7': [6, 9], 'F8': [12, 17], 'F9': [6, 9]}. Min train events per class: {'F1': 52, 'F2': 45, 'F3': 18, 'F4': 27, 'F5': 27, 'F6': 22, 'F7': 27, 'F8': 53, 'F9': 27}. Fold stations (GroupKFold default assignment, no reassignment needed): {'1': ['42131', '42921', '43117'], '2': ['42103', '42348', '43110'], '3': ['42182', '43063'], '4': ['42181', '43014'], '5': ['42170', '43003']}.

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
