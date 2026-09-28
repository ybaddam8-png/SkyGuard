# SkyGuard AI benchmark report

## Run configuration

- 3-hourly cadence; 1 step = 3 h; lags 1/2/4/8; rolling windows 1/8.
- Grouped 5-fold cross-validation by station; mean and standard deviation reported.
- LightGBM models capped at 200 trees; LSTM and edge skipped under free-plan scope.
- Faults injected outside cluster-specific protected windows; native source gaps are not F7 labels.

## Data and injector

- Injected rows: 105,216; labelled fault observations: 4,548; stations: 12; protected rows: 2,184.
- Label counts: {'weather': 100759, 'F7': 807, 'F6': 779, 'F2': 777, 'F4': 461, 'F5': 346, 'F8': 336, 'F9': 334, 'F3': 318, 'F1': 299}.
- F2 duration: 4–24 steps (12–72 h); F5: 4–80 steps (12 h–10 days); F7: 1–8 steps.

## Metrics (fold mean ± std)

| Metric | Mean | Std | |
|---|---:|---:|
| precision | 0.4868 | 0.1494 |
| recall | 0.6873 | 0.0988 |
| f1 | 0.5645 | 0.1307 |
| t0_f1 | 0.3969 | 0.0895 |
| iforest_f1 | 0.2391 | 0.1231 |
| no_T1_f1 | 0.3940 | 0.1062 |
| no_T2_f1 | 0.2388 | 0.1059 |
| no_T3_f1 | 0.2462 | 0.0719 |

## Per-class root-cause F1 (OOF)

| Class | Precision | Recall | F1 |
|---|---:|---:|---:|
| F1 | 0.5423 | 0.8796 | 0.6709 |
| F2 | 0.8179 | 0.6010 | 0.6929 |
| F3 | 0.0000 | 0.0000 | 0.0000 |
| F4 | 0.0000 | 0.0000 | 0.0000 |
| F5 | 0.0000 | 0.0000 | 0.0000 |
| F6 | 0.9589 | 0.8395 | 0.8953 |
| F7 | 0.3425 | 0.8017 | 0.4800 |
| F8 | 0.9682 | 0.9970 | 0.9824 |
| F9 | 0.0000 | 0.0000 | 0.0000 |

Macro-F1 across F1–F9: **0.4135**.

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
