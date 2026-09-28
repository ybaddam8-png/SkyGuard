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
| t0_f1 | 0.3895 | 0.0320 |
| iforest_f1 | 0.2384 | 0.1068 |
| no_T1_f1 | 0.3887 | 0.0619 |
| no_T2_f1 | 0.2550 | 0.0805 |
| no_T3_f1 | 0.2657 | 0.0575 |

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

Macro-F1 across F1–F9: **0.4060**.

## Neighbour policy

Primary links use 200 km / 500 m. Stations with fewer than two primary neighbours use sparse links widened to 300 km / 800 m and a 0.7 T3 confidence multiplier. A station with zero links makes T3 abstain and fusion treats T3 as missing.

## Honest limitations

The benchmark is an injected-data estimate over a small 12-station network with substantial native gaps. Results below specification targets, if any, are reported without tuning them away. The current implementation provides auditable tier features, fusion predictions, and benchmark artifacts; production calibration and SHAP explanations remain follow-on hardening tasks.

## Figures

- `outputs/figures/per_class_f1.png`
- `outputs/figures/ablation.png`
- `outputs/figures/confusion_matrix.png`
- `outputs/figures/example_fault_spans.png`
- `outputs/figures/heatwave_no_injection.png`
