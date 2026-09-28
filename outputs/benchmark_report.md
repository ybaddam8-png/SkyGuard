# SkyGuard AI benchmark report

## Run configuration

- 3-hourly cadence; 1 step = 3 h; lags 1/2/4/8; rolling windows 1/8.
- Grouped 5-fold cross-validation by station; mean and standard deviation reported.
- LightGBM models capped at 200 trees; LSTM and edge skipped under free-plan scope.
- Faults injected outside cluster-specific protected windows; native source gaps are not F7 labels.

## Data and injector

- Injected rows: 105,216; labelled fault observations: 133,252; stations: 12; protected rows: 2,184.
- Label counts: {'weather': 35552, 'F3': 29643, 'F9': 15892, 'F6': 7594, 'F5': 7149, 'F4': 6885, 'F2': 1751, 'F7': 421, 'F8': 194, 'F1': 135}.
- F2 duration: 4–24 steps (12–72 h); F5: 4–80 steps (12 h–10 days); F7: 1–8 steps.

## Metrics (fold mean ± std)

| Metric | Mean | Std | |
|---|---:|---:|
| precision | 0.9105 | 0.0172 |
| recall | 0.8214 | 0.0212 |
| f1 | 0.8635 | 0.0157 |
| t0_f1 | 0.5592 | 0.0323 |
| iforest_f1 | 0.0548 | 0.0142 |
| no_T1_f1 | 0.8159 | 0.0186 |
| no_T2_f1 | 0.7164 | 0.0227 |
| no_T3_f1 | 0.7496 | 0.0321 |

## Per-class root-cause F1 (OOF)

| Class | Precision | Recall | F1 |
|---|---:|---:|---:|
| F1 | 0.2584 | 0.1704 | 0.2054 |
| F2 | 0.5570 | 0.6836 | 0.6138 |
| F3 | 0.5985 | 0.5340 | 0.5644 |
| F4 | 0.1674 | 0.1984 | 0.1816 |
| F5 | 0.6506 | 0.7948 | 0.7155 |
| F6 | 0.8064 | 0.9293 | 0.8635 |
| F7 | 0.0867 | 0.4869 | 0.1472 |
| F8 | 0.7841 | 0.9175 | 0.8456 |
| F9 | 0.6543 | 0.6907 | 0.6720 |

Macro-F1 across F1–F9: **0.5343**.

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
