# SkyGuard AI benchmark report

## Run configuration

- 3-hourly cadence; 1 step = 3 h; lags 1/2/4/8; rolling windows 1/8.
- Grouped 5-fold cross-validation by station; mean and standard deviation reported.
- LightGBM models capped at 200 trees; LSTM and edge skipped under free-plan scope.
- Faults injected outside cluster-specific protected windows; native source gaps are not F7 labels.

## Data and injector

- Injected rows: 105,216; labelled fault observations: 4,499; stations: 12; protected rows: 2,184.
- Label counts: {'weather': 100803, 'F7': 807, 'F2': 777, 'F6': 735, 'F4': 461, 'F5': 346, 'F8': 337, 'F9': 329, 'F3': 318, 'F1': 303}.
- F2 duration: 4–24 steps (12–72 h); F5: 4–80 steps (12 h–10 days); F7: 1–8 steps.

## Metrics (fold mean ± std)

| Metric | Mean | Std | |
|---|---:|---:|
| precision | 0.5122 | 0.1458 |
| recall | 0.6954 | 0.0549 |
| f1 | 0.5838 | 0.1127 |
| macro_f1 | 0.4106 | 0.0261 |
| t0_f1 | 0.3895 | 0.0320 |
| iforest_f1 | 0.2919 | 0.1115 |
| trivial_f1 | 0.0795 | 0.0092 |
| ece_raw | 0.0757 | 0.0139 |
| ece_calibrated | 0.0181 | 0.0085 |
| no_T1_f1 | 0.5772 | 0.0896 |
| no_T2_f1 | 0.5900 | 0.1065 |
| no_T3_f1 | 0.5771 | 0.0962 |

## Per-class root-cause F1 (OOF)

| Class | Precision | Recall | F1 |
|---|---:|---:|---:|
| F1 | 0.5521 | 0.8746 | 0.6769 |
| F2 | 0.7897 | 0.5894 | 0.6750 |
| F3 | 0.0000 | 0.0000 | 0.0000 |
| F4 | 0.0000 | 0.0000 | 0.0000 |
| F5 | 0.0000 | 0.0000 | 0.0000 |
| F6 | 0.9681 | 0.8245 | 0.8905 |
| F7 | 0.3280 | 0.7943 | 0.4643 |
| F8 | 0.8292 | 0.9941 | 0.9042 |
| F9 | 0.1047 | 0.0274 | 0.0434 |

Macro-F1 across F1–F9 (OOF): **0.4060**.

## Scoring latency

- p50: 0.937 ms; p95: 1.154 ms (timed row-by-row on fold 0's test set, n=500).

## False alarms in protected windows (P(fault) >= 0.5)

| Window | Observations | False alarms / 1,000 |
|---|---:|---:|
| heatwave_a | 1,632 | 11.64 |
| biparjoy_a | 210 | 4.76 |
| monsoon_c | 342 | 87.72 |

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
