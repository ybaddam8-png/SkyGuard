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
| precision | 0.7223 | 0.0418 |
| recall | 0.6937 | 0.0590 |
| f1 | 0.7069 | 0.0440 |
| macro_f1 | 0.5995 | 0.0514 |
| t0_f1 | 0.4914 | 0.0597 |
| iforest_f1 | 0.4306 | 0.0800 |
| trivial_f1 | 0.1268 | 0.0096 |
| ece_raw | 0.0599 | 0.0103 |
| ece_calibrated | 0.0231 | 0.0053 |
| no_T1_f1 | 0.6559 | 0.0400 |
| no_T2_f1 | 0.6965 | 0.0605 |
| no_T3_f1 | 0.6775 | 0.0490 |

## Per-class root-cause F1 (OOF)

| Class | Precision | Recall | F1 |
|---|---:|---:|---:|
| F1 | 0.4318 | 0.5429 | 0.4810 |
| F2 | 0.6288 | 0.6960 | 0.6607 |
| F3 | 0.2500 | 0.1313 | 0.1722 |
| F4 | 0.3698 | 0.2897 | 0.3249 |
| F5 | 0.7300 | 0.8786 | 0.7974 |
| F6 | 0.9157 | 0.9447 | 0.9300 |
| F7 | 0.9817 | 1.0000 | 0.9908 |
| F8 | 0.8551 | 0.8429 | 0.8489 |
| F9 | 0.2611 | 0.1956 | 0.2236 |

Macro-F1 across F1–F9 (OOF): **0.6033**.

## Scoring latency

- p50: 1.424 ms; p95: 1.888 ms (timed row-by-row on fold 0's test set, n=500).

## False alarms in protected windows (P(fault) >= 0.5)

| Window | Observations | False alarms / 1,000 |
|---|---:|---:|
| heatwave_a | 1,609 | 0.62 |
| biparjoy_a | 209 | 0.00 |
| monsoon_c | 311 | 0.00 |

## Evaluation definitions

- **F3 pre-detectable rows.** A drift row counts as a fault (training positive and scored row) only from the first step where the injected error reaches the tolerance (0.5 °C, 5 % RH, 0.5 hPa). Earlier rows (1,108) get sample weight 0 and are excluded from row-level scoring; the event stays in the event table. F3 event detection only counts flags from the tolerance crossing onward. Delay is reported from the tolerance crossing and from the PRD crossing (1 °C, 5 % RH, 1 hPa); a negative PRD delay means the drift was flagged before it reached the PRD threshold.
- **F7 and native gaps.** A missing expected timestamp is a comms fault whatever its cause, and the label file cannot separate injected from native gaps. A deterministic T0 gap rule flags every missing timestamp as F7 (P(fault) = 1). F7 recall is measured on injected gaps; the 11,219 native-gap rows are excluded from all row-level scoring (so from the F7 precision denominator), from the clean-step alert rate and from the protected-window false-alarm rates. F7 recall is therefore 1.0 by construction and says nothing about the learned model.
- **SNR.** Detectability tables use MEAN-ERROR SNR: F3 = mean injected error over the event (about half the final magnitude for a ramp) / std of the 56-step mean of the station-variable healthy T3 residual; F4 = offset / same std. A second table uses final-magnitude SNR for F3. F5: injected noise std / 1-step std of the healthy T3 residual.

## Event-level detection (alongside row-level metrics)

An event counts as detected if any row inside its detectable window has P(fault) >= 0.5. Delay = hours from the start of the detectable window to the first flagged row (detected events only).

| Class | Events | Detectable | Recall | Recall (class correct) | Median delay (h) |
|---|---:|---:|---:|---:|---:|
| F1 | 70 | 70 | 0.971 | 0.543 | 0.0 |
| F2 | 60 | 60 | 0.950 | 0.950 | 9.0 |
| F3 | 24 | 21 | 0.619 | 0.238 | 15.0 |
| F4 | 36 | 36 | 0.667 | 0.611 | 9.0 |
| F5 | 36 | 36 | 1.000 | 0.972 | 0.0 |
| F6 | 30 | 30 | 1.000 | 0.967 | 0.0 |
| F7 | 36 | 36 | 1.000 | 1.000 | 0.0 |
| F8 | 70 | 70 | 1.000 | 0.843 | 0.0 |
| F9 | 36 | 36 | 0.944 | 0.444 | 3.0 |

F3 median delay from PRD crossing: 6.0 h over 13 detected events that reach the PRD threshold.

## Detectability curve (recall by MEAN-ERROR SNR bin, full model)

| Class | SNR bin | Events | Event recall (any class) | Event recall (class correct) | Row recall (any class) | Row recall (class correct) |
|---|---|---:|---:|---:|---:|---:|
| F3 | <1 | 8 | 0.375 | 0.375 | 0.385 | 0.198 |
| F3 | 1-2 | 12 | 0.833 | 0.167 | 0.250 | 0.126 |
| F3 | 2-4 | 1 | 0.000 | 0.000 | 0.000 | 0.000 |
| F3 | >4 | 0 | n/a | n/a | n/a | n/a |
| F3 | >=3 | 1 | 0.000 | 0.000 | 0.000 | 0.000 |
| F4 | <1 | 1 | 0.000 | 0.000 | 0.000 | 0.000 |
| F4 | 1-2 | 9 | 0.778 | 0.667 | 0.253 | 0.173 |
| F4 | 2-4 | 13 | 0.538 | 0.462 | 0.292 | 0.214 |
| F4 | >4 | 13 | 0.769 | 0.769 | 0.534 | 0.496 |
| F4 | >=3 | 19 | 0.737 | 0.684 | 0.415 | 0.360 |
| F5 | <1 | 0 | n/a | n/a | n/a | n/a |
| F5 | 1-2 | 0 | n/a | n/a | n/a | n/a |
| F5 | 2-4 | 0 | n/a | n/a | n/a | n/a |
| F5 | >4 | 36 | 1.000 | 0.972 | 0.956 | 0.879 |
| F5 | >=3 | 36 | 1.000 | 0.972 | 0.956 | 0.879 |

### Same, F3 by FINAL-MAGNITUDE SNR

| Class | SNR bin | Events | Event recall (any class) | Event recall (class correct) | Row recall (any class) | Row recall (class correct) |
|---|---|---:|---:|---:|---:|---:|
| F3 | <1 | 1 | 0.000 | 0.000 | 0.000 | 0.000 |
| F3 | 1-2 | 7 | 0.429 | 0.429 | 0.454 | 0.233 |
| F3 | 2-4 | 12 | 0.833 | 0.167 | 0.250 | 0.126 |
| F3 | >4 | 1 | 0.000 | 0.000 | 0.000 | 0.000 |
| F3 | >=3 | 5 | 0.400 | 0.000 | 0.050 | 0.000 |

Healthy T3 noise floor (median over stations; 3 sigma of the 56-step mean): temp_c 1.92; mslp_hpa 1.61; rh_pct 13.39.

| Variant | Alerts | Alerts / 1,000 clean steps (outside events, protected windows and native gaps) | Share of alerts inside an injected event |
|---|---:|---:|---:|
| full | 6,132 | 20.09 | 0.723 |
| no_T1 | 6,098 | 24.18 | 0.665 |
| no_T2 | 6,319 | 22.07 | 0.705 |
| no_T3 | 6,826 | 26.93 | 0.666 |

## Ablation (tier columns removed, heads retrained)

| Tier removed | Paired per-fold F1 diff (full − ablated) | Mean | Std | Folds ablated >= full |
|---|---|---:|---:|---:|
| no_T1 | +0.0246, +0.0550, +0.0541, +0.0829, +0.0380 | +0.0509 | 0.0218 | 0/5 |
| no_T2 | +0.0295, +0.0198, -0.0130, -0.0026, +0.0179 | +0.0103 | 0.0175 | 2/5 |
| no_T3 | +0.0420, +0.0319, +0.0641, +0.0368, -0.0278 | +0.0294 | 0.0343 | 1/5 |

| Variant | F1 | F2 | F3 | F4 | F5 | F6 | F7 | F8 | F9 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| full F1 | 0.481 | 0.661 | 0.172 | 0.325 | 0.797 | 0.930 | 0.991 | 0.849 | 0.224 |
| no_T1 F1 | 0.443 | 0.671 | 0.006 | 0.228 | 0.774 | 0.934 | 0.997 | 0.837 | 0.208 |
| no_T2 F1 | 0.493 | 0.666 | 0.174 | 0.319 | 0.795 | 0.923 | 0.997 | 0.847 | 0.164 |
| no_T3 F1 | 0.486 | 0.681 | 0.164 | 0.240 | 0.792 | 0.929 | 0.994 | 0.886 | 0.205 |
| full event recall | 0.971 | 0.950 | 0.619 | 0.667 | 1.000 | 1.000 | 1.000 | 1.000 | 0.944 |
| no_T1 event recall | 0.971 | 0.950 | 0.476 | 0.667 | 1.000 | 1.000 | 1.000 | 1.000 | 0.972 |
| no_T2 event recall | 0.971 | 0.950 | 0.667 | 0.750 | 1.000 | 1.000 | 1.000 | 1.000 | 0.917 |
| no_T3 event recall | 0.971 | 0.950 | 0.857 | 0.806 | 1.000 | 1.000 | 1.000 | 1.000 | 0.944 |
| full class-correct event recall | 0.543 | 0.950 | 0.238 | 0.611 | 0.972 | 0.967 | 1.000 | 0.843 | 0.444 |
| no_T1 class-correct event recall | 0.500 | 0.950 | 0.095 | 0.556 | 0.972 | 0.933 | 1.000 | 0.843 | 0.389 |
| no_T2 class-correct event recall | 0.514 | 0.950 | 0.333 | 0.611 | 1.000 | 0.967 | 1.000 | 0.871 | 0.361 |
| no_T3 class-correct event recall | 0.500 | 0.950 | 0.429 | 0.750 | 1.000 | 0.967 | 1.000 | 0.886 | 0.472 |

## Baselines on the current benchmark (same evaluation definitions, fold mean ± std)

All rows below are scored on the same rows: pre-detectable F3 rows and native gaps excluded.

| Detector | Binary F1 |
|---|---:|
| Fusion (with F7 gap rule) | 0.7069 ± 0.0440 |
| Fusion without the F7 gap rule | 0.7069 ± 0.0440 |
| WMO rules only (T0, incl. gap rule) | 0.4914 ± 0.0597 |
| WMO rules only (T0, no gap rule) | 0.4735 ± 0.0614 |
| Isolation Forest (contamination = training-fold prevalence) | 0.4306 ± 0.0800 |
| Always fault | 0.1268 ± 0.0096 |

| F7 | Injected-gap recall | Precision (native gaps excluded) | Precision (native gaps counted as negatives) | Native-gap rows called F7 |
|---|---:|---:|---:|---:|
| with_gap_rule | 1.000 | 0.988 | 0.014 | 11,219 / 11,219 |
| without_gap_rule | 1.000 | 0.988 | 0.014 | 11,219 / 11,219 |

## Calendar shortcut check and placebo windows

Fusion heads exclude ['hour_sin', 'hour_cos', 'doy_sin', 'doy_cos', 'temp_c_clim_mu', 'mslp_hpa_clim_mu', 'rh_pct_clim_mu']. The with-calendar binary head is refit per fold for comparison only. Placebo windows = each protected window shifted +182 days, in both clusters (faults occur there).

| Window | Obs | Clean alerts/1,000 (no calendar) | Clean alerts/1,000 (with calendar) | Fault rows | Fault-row recall (no calendar) | Fault-row recall (with calendar) |
|---|---:|---:|---:|---:|---:|---:|
| biparjoy_a | 209 | 0.00 | 0.00 | 0 | n/a | n/a |
| heatwave_a | 1,609 | 0.62 | 1.86 | 0 | n/a | n/a |
| monsoon_c | 311 | 0.00 | 0.00 | 0 | n/a | n/a |
| placebo_biparjoy_a_a | 208 | 9.62 | 9.62 | 0 | n/a | n/a |
| placebo_biparjoy_a_c | 210 | 6.76 | 6.76 | 62 | 0.403 | 0.387 |
| placebo_heatwave_a_a | 1,442 | 13.90 | 16.09 | 75 | 0.573 | 0.360 |
| placebo_heatwave_a_c | 1,442 | 15.79 | 17.36 | 110 | 0.718 | 0.718 |
| placebo_monsoon_c_a | 337 | 3.36 | 3.36 | 33 | 0.515 | 0.576 |
| placebo_monsoon_c_c | 331 | 9.26 | 9.26 | 7 | 0.000 | 0.000 |
| all_other_clean | 80,844 | 20.42 | 19.80 |  | n/a | n/a |

## Natural extremes on clean rows (test folds, fold mean ± std, alerts per 1,000)

Per-station top 0.5 % temp, bottom 0.5 % MSLP, top/bottom 0.5 % 3-step change in any variable; rows with no injected fault and no native gap. Tier columns show the rate when that tier is removed (which tier drives extreme alerts).

| Group | Rows | No calendar (default) | With calendar | Ratio to clean (default) | No T1 | No T2 | No T3 |
|---|---:|---:|---:|---:|---:|---:|---:|
| temp_top0.5pct | 519 | 9.5 ± 14.2 | 11.1 | 0.49 | 15.3 | 9.1 | 9.0 |
| mslp_bottom0.5pct | 487 | 10.0 ± 11.0 | 9.4 | 0.51 | 11.7 | 7.6 | 22.9 |
| change3_top0.5pct_any_var | 1,308 | 41.1 ± 15.5 | 40.8 | 2.11 | 59.0 | 35.8 | 59.1 |
| change3_bottom0.5pct_any_var | 1,372 | 39.9 ± 11.8 | 41.7 | 2.05 | 50.3 | 37.0 | 51.6 |
| any_extreme | 3,311 | 33.4 ± 9.5 | 34.4 | 1.71 | 44.8 | 30.2 | 46.3 |
| all_clean | 86,585 | 19.5 ± 4.5 | 19.1 | 1.00 | 24.2 | 21.3 | 26.3 |

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
