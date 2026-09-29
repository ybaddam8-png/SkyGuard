# SkyGuard AI benchmark report

## Run configuration

- 3-hourly cadence; 1 step = 3 h; lags 1/2/4/8; rolling windows 1/8.
- Grouped 5-fold cross-validation by station; mean and standard deviation reported.
- LightGBM models capped at 200 trees; LSTM and edge skipped under free-plan scope.
- Faults injected outside cluster-specific protected windows; native source gaps are not F7 labels.

## Data and injector

- Injected rows: 175,360; labelled fault observations: 10,942; stations: 20; protected rows: 3,390.
- Label counts: {'weather': 164418, 'F3': 2801, 'F4': 2355, 'F5': 1986, 'F6': 1784, 'F2': 1097, 'F9': 413, 'F7': 272, 'F8': 117, 'F1': 117}.
- Injector samples by event count (min per class: F1 60, F2 40, F3 24, F4 30, F5 30, F6 30, F7 30, F8 60, F9 30; spread over >=8 stations). Durations in steps (1 step = 3 h): F1/F8 1, F2 4–24, F3 56–112, F4 8–80, F5 4–80, F6 4–80, F7 1–8, F9 1–16.
- **Documented deviation:** F3 drift lasts 7–14 days (56–112 steps), shorter than the spec's 7–45 days, so 24 drift events fit in the coverage budget. F9 is back to spec (1–16 steps = 1–48 h). F3 final error follows spec section 6: 0.5–3 °C, 3–15 % RH, 0.5–3 hPa, variable T 45 % / RH 45 % / P 10 % (RH was 0.5–3 % before fix/detectability).
- Root-cause head is trained only on injector-labelled rows plus protected-window weather rows (spec section 8); a row receives a root cause only if the binary head flags it (P(fault) >= 0.5), otherwise "weather".

## Metrics (fold mean ± std)

| Metric | Mean | Std | |
|---|---:|---:|
| precision | 0.6291 | 0.0694 |
| recall | 0.6818 | 0.0412 |
| f1 | 0.6509 | 0.0271 |
| macro_f1 | 0.5906 | 0.0092 |
| t0_f1 | 0.4483 | 0.0190 |
| iforest_f1 | 0.4151 | 0.0144 |
| trivial_f1 | 0.1324 | 0.0072 |
| ece_raw | 0.1041 | 0.0204 |
| ece_calibrated | 0.0247 | 0.0033 |
| no_T1_f1 | 0.5809 | 0.0470 |
| no_T2_f1 | 0.6347 | 0.0292 |
| no_T3_f1 | 0.6105 | 0.0307 |

## Per-class root-cause F1 (OOF)

| Class | Precision | Recall | F1 |
|---|---:|---:|---:|
| F1 | 0.5447 | 0.5726 | 0.5583 |
| F2 | 0.5277 | 0.6436 | 0.5799 |
| F3 | 0.1735 | 0.1555 | 0.1640 |
| F4 | 0.2984 | 0.3023 | 0.3004 |
| F5 | 0.6724 | 0.8691 | 0.7582 |
| F6 | 0.9385 | 0.9490 | 0.9437 |
| F7 | 0.9510 | 1.0000 | 0.9749 |
| F8 | 0.7742 | 0.8205 | 0.7967 |
| F9 | 0.2321 | 0.2833 | 0.2552 |

Macro-F1 across F1–F9 (OOF): **0.5924**.

## Scoring latency

- p50: 1.744 ms; p95: 2.387 ms (timed row-by-row on fold 0's test set, n=500).

## False alarms in protected windows (P(fault) >= 0.5)

| Window | Observations | False alarms / 1,000 |
|---|---:|---:|
| heatwave_a | 2,421 | 9.09 |
| biparjoy_a | 308 | 6.49 |
| monsoon_c | 449 | 20.04 |

## Evaluation definitions

- **F3 pre-detectable rows.** A drift row counts as a fault (training positive and scored row) only from the first step where the injected error reaches the tolerance (0.5 °C, 5 % RH, 0.5 hPa). Earlier rows (1,418) get sample weight 0 and are excluded from row-level scoring; the event stays in the event table. F3 event detection only counts flags from the tolerance crossing onward. Delay is reported from the tolerance crossing and from the PRD crossing (1 °C, 5 % RH, 1 hPa); a negative PRD delay means the drift was flagged before it reached the PRD threshold.
- **F7 and native gaps.** A missing expected timestamp is a comms fault whatever its cause, and the label file cannot separate injected from native gaps. A deterministic T0 gap rule flags every missing timestamp as F7 (P(fault) = 1). F7 recall is measured on injected gaps; the 39,945 native-gap rows are excluded from all row-level scoring (so from the F7 precision denominator), from the clean-step alert rate and from the protected-window false-alarm rates. F7 recall is therefore 1.0 by construction and says nothing about the learned model.
- **SNR.** Detectability tables use MEAN-ERROR SNR: F3 = mean injected error over the event (about half the final magnitude for a ramp) / std of the 56-step mean of the station-variable healthy T3 residual; F4 = offset / same std. A second table uses final-magnitude SNR for F3. F5: injected noise std / 1-step std of the healthy T3 residual.

## Event-level detection (alongside row-level metrics)

An event counts as detected if any row inside its detectable window has P(fault) >= 0.5. Delay = hours from the start of the detectable window to the first flagged row (detected events only).

| Class | Events | Detectable | Recall | Recall (class correct) | Median delay (h) |
|---|---:|---:|---:|---:|---:|
| F1 | 117 | 117 | 1.000 | 0.573 | 0.0 |
| F2 | 100 | 100 | 0.930 | 0.890 | 9.0 |
| F3 | 40 | 39 | 0.846 | 0.487 | 18.0 |
| F4 | 60 | 60 | 0.850 | 0.733 | 9.0 |
| F5 | 60 | 60 | 1.000 | 0.967 | 0.0 |
| F6 | 50 | 50 | 1.000 | 1.000 | 0.0 |
| F7 | 60 | 60 | 1.000 | 1.000 | 0.0 |
| F8 | 117 | 117 | 1.000 | 0.821 | 0.0 |
| F9 | 60 | 60 | 0.900 | 0.600 | 0.0 |

F3 median delay from PRD crossing: 12.0 h over 29 detected events that reach the PRD threshold.

## Detectability curve (recall by MEAN-ERROR SNR bin, full model)

| Class | SNR bin | Events | Event recall (any class) | Event recall (class correct) | Row recall (any class) | Row recall (class correct) |
|---|---|---:|---:|---:|---:|---:|
| F3 | <1 | 16 | 0.688 | 0.250 | 0.130 | 0.055 |
| F3 | 1-2 | 14 | 0.929 | 0.571 | 0.315 | 0.220 |
| F3 | 2-4 | 8 | 1.000 | 0.750 | 0.294 | 0.209 |
| F3 | >4 | 1 | 1.000 | 1.000 | 0.474 | 0.105 |
| F3 | >=3 | 2 | 1.000 | 0.500 | 0.212 | 0.030 |
| F4 | <1 | 4 | 1.000 | 1.000 | 0.503 | 0.363 |
| F4 | 1-2 | 11 | 0.727 | 0.636 | 0.266 | 0.172 |
| F4 | 2-4 | 26 | 0.846 | 0.692 | 0.380 | 0.275 |
| F4 | >4 | 19 | 0.895 | 0.789 | 0.555 | 0.404 |
| F4 | >=3 | 31 | 0.903 | 0.806 | 0.485 | 0.355 |
| F5 | <1 | 0 | n/a | n/a | n/a | n/a |
| F5 | 1-2 | 0 | n/a | n/a | n/a | n/a |
| F5 | 2-4 | 0 | n/a | n/a | n/a | n/a |
| F5 | >4 | 60 | 1.000 | 0.967 | 0.957 | 0.869 |
| F5 | >=3 | 60 | 1.000 | 0.967 | 0.957 | 0.869 |

### Same, F3 by FINAL-MAGNITUDE SNR

| Class | SNR bin | Events | Event recall (any class) | Event recall (class correct) | Row recall (any class) | Row recall (class correct) |
|---|---|---:|---:|---:|---:|---:|
| F3 | <1 | 1 | 1.000 | 0.000 | 0.020 | 0.000 |
| F3 | 1-2 | 15 | 0.667 | 0.267 | 0.142 | 0.061 |
| F3 | 2-4 | 14 | 0.929 | 0.571 | 0.315 | 0.220 |
| F3 | >4 | 9 | 1.000 | 0.778 | 0.304 | 0.203 |
| F3 | >=3 | 14 | 1.000 | 0.714 | 0.312 | 0.218 |

Healthy T3 noise floor (median over stations; 3 sigma of the 56-step mean): temp_c 1.68; mslp_hpa 1.34; rh_pct 12.45.

| Variant | Alerts | Alerts / 1,000 clean steps (outside events, protected windows and native gaps) | Share of alerts inside an injected event |
|---|---:|---:|---:|
| full | 10,766 | 33.28 | 0.622 |
| no_T1 | 11,955 | 47.06 | 0.518 |
| no_T2 | 11,415 | 38.18 | 0.591 |
| no_T3 | 11,935 | 43.24 | 0.557 |

## Ablation (tier columns removed, heads retrained)

| Tier removed | Paired per-fold F1 diff (full − ablated) | Mean | Std | Folds ablated >= full |
|---|---|---:|---:|---:|
| no_T1 | +0.0140, +0.0814, +0.0914, +0.0460, +0.1171 | +0.0700 | 0.0404 | 0/5 |
| no_T2 | +0.0075, +0.0278, +0.0083, +0.0173, +0.0204 | +0.0163 | 0.0085 | 0/5 |
| no_T3 | +0.0481, +0.0410, +0.0396, +0.0441, +0.0292 | +0.0404 | 0.0070 | 0/5 |

| Variant | F1 | F2 | F3 | F4 | F5 | F6 | F7 | F8 | F9 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| full F1 | 0.558 | 0.580 | 0.164 | 0.300 | 0.758 | 0.944 | 0.975 | 0.797 | 0.255 |
| no_T1 F1 | 0.576 | 0.570 | 0.022 | 0.183 | 0.725 | 0.929 | 0.989 | 0.780 | 0.197 |
| no_T2 F1 | 0.529 | 0.566 | 0.157 | 0.297 | 0.747 | 0.932 | 0.989 | 0.813 | 0.168 |
| no_T3 F1 | 0.603 | 0.568 | 0.124 | 0.226 | 0.758 | 0.948 | 0.985 | 0.860 | 0.235 |
| full event recall | 1.000 | 0.930 | 0.846 | 0.850 | 1.000 | 1.000 | 1.000 | 1.000 | 0.900 |
| no_T1 event recall | 1.000 | 0.940 | 0.744 | 0.867 | 1.000 | 1.000 | 1.000 | 1.000 | 0.917 |
| no_T2 event recall | 0.991 | 0.910 | 0.872 | 0.917 | 1.000 | 1.000 | 1.000 | 1.000 | 0.850 |
| no_T3 event recall | 1.000 | 0.940 | 0.846 | 0.833 | 1.000 | 1.000 | 1.000 | 1.000 | 0.883 |
| full class-correct event recall | 0.573 | 0.890 | 0.487 | 0.733 | 0.967 | 1.000 | 1.000 | 0.821 | 0.600 |
| no_T1 class-correct event recall | 0.598 | 0.890 | 0.333 | 0.733 | 0.967 | 1.000 | 1.000 | 0.863 | 0.483 |
| no_T2 class-correct event recall | 0.547 | 0.850 | 0.590 | 0.800 | 0.967 | 1.000 | 1.000 | 0.838 | 0.500 |
| no_T3 class-correct event recall | 0.615 | 0.880 | 0.564 | 0.750 | 0.983 | 1.000 | 1.000 | 0.863 | 0.600 |

## Baselines on the current benchmark (same evaluation definitions, fold mean ± std)

All rows below are scored on the same rows: pre-detectable F3 rows and native gaps excluded.

| Detector | Binary F1 |
|---|---:|
| Fusion (with F7 gap rule) | 0.6509 ± 0.0271 |
| Fusion without the F7 gap rule | 0.6509 ± 0.0271 |
| WMO rules only (T0, incl. gap rule) | 0.4483 ± 0.0190 |
| WMO rules only (T0, no gap rule) | 0.4306 ± 0.0172 |
| Isolation Forest (contamination = training-fold prevalence) | 0.4151 ± 0.0144 |
| Always fault | 0.1324 ± 0.0072 |

| F7 | Injected-gap recall | Precision (native gaps excluded) | Precision (native gaps counted as negatives) | Native-gap rows called F7 |
|---|---:|---:|---:|---:|
| with_gap_rule | 1.000 | 0.951 | 0.006 | 39,945 / 39,945 |
| without_gap_rule | 1.000 | 0.951 | 0.006 | 39,943 / 39,945 |

## Calendar shortcut check and placebo windows

Fusion heads exclude ['hour_sin', 'hour_cos', 'doy_sin', 'doy_cos', 'temp_c_clim_mu', 'mslp_hpa_clim_mu', 'rh_pct_clim_mu']. The with-calendar binary head is refit per fold for comparison only. Placebo windows = each protected window shifted +182 days, in both clusters (faults occur there).

| Window | Obs | Clean alerts/1,000 (no calendar) | Clean alerts/1,000 (with calendar) | Fault rows | Fault-row recall (no calendar) | Fault-row recall (with calendar) |
|---|---:|---:|---:|---:|---:|---:|
| biparjoy_a | 308 | 6.49 | 12.99 | 0 | n/a | n/a |
| heatwave_a | 2,421 | 9.09 | 8.67 | 0 | n/a | n/a |
| monsoon_c | 449 | 20.04 | 17.82 | 0 | n/a | n/a |
| placebo_biparjoy_a_a | 307 | 7.35 | 7.35 | 35 | 0.714 | 0.686 |
| placebo_biparjoy_a_c | 279 | 88.56 | 66.42 | 8 | 1.000 | 1.000 |
| placebo_heatwave_a_a | 2,125 | 23.67 | 27.61 | 97 | 0.392 | 0.536 |
| placebo_heatwave_a_c | 2,057 | 65.46 | 76.10 | 178 | 0.803 | 0.843 |
| placebo_monsoon_c_a | 501 | 10.55 | 14.77 | 27 | 1.000 | 1.000 |
| placebo_monsoon_c_c | 470 | 67.29 | 62.65 | 39 | 0.923 | 0.923 |
| all_other_clean | 115,979 | 32.82 | 31.64 |  | n/a | n/a |

## Natural extremes on clean rows (test folds, fold mean ± std, alerts per 1,000)

Per-station top 0.5 % temp, bottom 0.5 % MSLP, top/bottom 0.5 % 3-step change in any variable; rows with no injected fault and no native gap. Tier columns show the rate when that tier is removed (which tier drives extreme alerts).

| Group | Rows | No calendar (default) | With calendar | Ratio to clean (default) | No T1 | No T2 | No T3 |
|---|---:|---:|---:|---:|---:|---:|---:|
| temp_top0.5pct | 743 | 48.4 ± 28.8 | 46.0 | 1.54 | 57.3 | 56.5 | 69.5 |
| mslp_bottom0.5pct | 681 | 56.7 ± 32.2 | 50.9 | 1.80 | 66.2 | 65.3 | 86.9 |
| change3_top0.5pct_any_var | 1,739 | 69.6 ± 28.8 | 67.8 | 2.21 | 84.7 | 80.6 | 87.6 |
| change3_bottom0.5pct_any_var | 1,824 | 73.1 ± 24.6 | 68.4 | 2.32 | 87.2 | 68.5 | 87.2 |
| any_extreme | 4,513 | 65.8 ± 12.7 | 61.5 | 2.09 | 79.8 | 71.5 | 86.3 |
| all_clean | 124,512 | 31.5 ± 9.9 | 30.7 | 1.00 | 44.1 | 36.1 | 41.1 |

## Fold event counts

Min/max test events per class across folds: {'F1': [23, 24], 'F2': [20, 20], 'F3': [8, 8], 'F4': [12, 12], 'F5': [12, 12], 'F6': [10, 10], 'F7': [12, 12], 'F8': [23, 24], 'F9': [12, 12]}. Min train events per class: {'F1': 93, 'F2': 80, 'F3': 32, 'F4': 48, 'F5': 48, 'F6': 40, 'F7': 48, 'F8': 93, 'F9': 48}. Fold stations (GroupKFold default assignment, no reassignment needed): {'1': ['42170', '42921', '43057', '43157'], '2': ['42131', '42348', '43014', '43117'], '3': ['42111', '42189', '43003', '43110'], '4': ['42103', '42182', '43002', '43109'], '5': ['42101', '42181', '43001', '43063']}.

## Neighbour policy

Primary links use 200 km / 500 m. Stations with fewer than two primary neighbours use sparse links widened to 300 km / 800 m and a 0.7 T3 confidence multiplier. A station with zero links makes T3 abstain and fusion treats T3 as missing.

## Honest limitations

The benchmark is an injected-data estimate over a small station network (20 stations) with substantial native gaps. Results below specification targets, if any, are reported without tuning them away.

## Figures

- `outputs/figures/per_class_f1.png`
- `outputs/figures/ablation.png`
- `outputs/figures/confusion_matrix.png`
- `outputs/figures/example_fault_spans.png`
- `outputs/figures/heatwave_no_injection.png`
