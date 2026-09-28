# SkyGuard AI — Engine Specification (SIH26073)

Single consolidated spec for building the Python detection engine and benchmark.
Merged from: 01 Problem Statement Analysis, 02 PRD, 03 Features Specification, 04 Master Proposal.
Scope of this file: everything the ENGINE task needs. Dashboard/UI and the PPT are out of scope here.
Version: 2026-09-28. Where a number is given here, use it exactly.

---

## 1. Problem statement (official, summarised)

- **PS ID:** SIH26073 — AI/ML-Based Intelligent Anomaly Detection for Automatic Weather Stations (AWS)
- **Organisation:** Ministry of Earth Sciences (MoES), India Meteorological Department (IMD). Category: Software. Theme: Disaster Management.
- **Task:** real-time AI/ML system that flags abnormal, inconsistent or faulty AWS observations using ONLY:
  - Temperature (°C), Station pressure (hPa), Relative humidity (%)
- Must distinguish genuine meteorological events from sensor/data faults, minimise false alarms, and scale to large networks.
- **Objectives:** detect anomalies in real-time streams; identify spikes, frozen values, communication errors, calibration drift; learn diurnal/seasonal patterns; multivariate T–P–RH consistency; confidence scores + explainable reasoning (SHAP/LIME preferred); predict sensor degradation/maintenance; optionally suggest corrected values.
- **Expected outputs:** real-time alerts, severity + confidence scores, root-cause classification, visualisation dashboard, sensor health status, corrected-value estimation (optional).
- **Suggested tech:** Explainable AI (SHAP/LIME); Edge AI on ESP32.
- **Deliverable:** fully executable code with example usage + a document explaining use cases.
- **Example use case:** a station reports 55 °C with very high RH and abnormal pressure variation while neighbours look normal → system must use temporal + spatial consistency, flag a probable sensor fault, alert, and suggest corrective action.

### Judging (evaluated on anomaly-injected data)

| Criterion | Weight | What it means for the engine |
|---|---|---|
| Innovation & novelty | 25% | Four-tier evidence fusion + coherent-event gate + physics features, proven by ablation |
| Detection accuracy | 20% | Per-fault-type precision/recall; low false alarms on REAL extremes |
| Real-time capability | 15% | Per-observation streaming scoring with measured latency |
| Explainability | 10% | One plain-English sentence + top-3 factors per alert |
| Scalability | 10% | One global model family for all stations |
| Practical deployability | 10% | CPU-only, pip install, Makefile, Docker-friendly, open formats |
| Visualization/UI | 5% | (dashboard task, not this one) |
| Energy efficiency | 5% | Tiny int8 edge model for ESP32-S3 (code + model only) |

The jury's test-data cadence (1-min vs hourly) is unknown → engine must accept any fixed cadence from 1 min to 1 h.

---

## 2. Domain facts to respect

- IMD operates about 707 AWS (IMD count as of 2020), mostly hourly, relayed by geostationary satellite to the Earth Station at IMD Pune; some newer networks use GPRS. One-way satellite links lose missed bursts permanently → gaps, duplicates and timestamp shifts are normal fault types.
- IMD's current QC is rule-based: range, climatological-extreme and step checks (Ranalkar et al., MAUSAM 66(1), 2015).
- India's verified all-time highest temperature: **51.0 °C at Phalodi, Rajasthan, 19 May 2016.** 55 °C is therefore physically implausible for India.
- WMO guidance (Zahumenský 2004) says values tripped by extreme weather should be flagged suspect, not rejected, and resolved later at the data processing centre. SkyGuard automates that second pass.

### WMO reference thresholds (Zahumenský 2004)

| Check | Temperature | Relative humidity | Station pressure |
|---|---|---|---|
| Plausible range | −80 to +60 °C | 0–100 % | 500–1100 hPa |
| Step: max change between consecutive 1-min values | 3 °C | 10 % | 0.5 hPa |
| Step: raw 10-second samples (tighter) | 2 °C | 5 % | 0.3 hPa |
| Persistence: min change over past 60 min | 0.1 °C | 1 % | 0.1 hPa |
| Internal consistency | dew point ≤ air temperature | | |

For hourly data these 1-min limits do NOT apply directly; use learned station-specific limits (see Tier 0).

---

## 3. Fault taxonomy (root-cause labels the engine outputs)

| # | Class | Signature in T / P / RH | Likely physical cause |
|---|---|---|---|
| F1 | Spike | One sample far off, returns next sample | EMI, ADC glitch, bit error |
| F2 | Stuck / frozen | Zero variance for hours, usually one variable | Sensor lock-up, logger repeating last value |
| F3 | Drift | Slow monotonic bias vs neighbours over days–weeks | Calibration drift, RH sensor ageing |
| F4 | Offset (level shift) | Abrupt constant bias that persists | Sensor swap, recalibration, firmware change |
| F5 | Noise inflation | Variance rises, mean unchanged | Loose connector, failing shield, power ripple |
| F6 | Saturation | Pinned at a bound (RH 100 % for days, T at logger limit) | RH sensor wetting, ADC range |
| F7 | Dropout | Missing timestamps, bursty gaps | Satellite/GPRS failure, power loss |
| F8 | Corruption | 0, −9999, bit flips, swapped fields, time shifts | Decoder bugs, frame corruption |
| F9 | Cross-variable inconsistency | Each value plausible, combination impossible | One sensor faulty while others fine |
| — | weather | Genuine event (not a fault) | — |

### Genuine events that must NOT be flagged

| Event | Sensor behaviour | Why it is real |
|---|---|---|
| Heatwave (NW India) | T 46–51 °C, RH very low | Physically consistent; neighbours agree |
| Thunderstorm / Kalbaisakhi / dust storm | T drops several °C in minutes, RH jumps, P jumps (meso-high) | All three move in physically expected directions; signature travels across stations |
| Cyclone landfall | P falls tens of hPa over hours, RH near 100 % | Coherent across coastal stations |
| Monsoon / fog / heavy rain | RH near 100 % for long periods, T nearly flat | Near-zero variance is real here |
| Western disturbance / cold wave | Sharp T fall, P and RH changes | Regional, synoptic-scale coherence |

Design rule: a move in one variable with no matching move in the other two and no neighbour agreement → fault. A large coherent move across all three variables and neighbours → weather.

---

## 4. Data

- **Training/demo data:** `meteostat` Python package, HOURLY temp, rhum, pres. Data licence CC BY-NC 4.0 (non-commercial use OK). Check installed version: API differs between v1 and v2.
- **Stations:** 24–30 Indian stations in 3 clusters so each has neighbours within ~150 km:
  (a) Delhi-NCR / Rajasthan, (b) Odisha / West Bengal coast, (c) Maharashtra (Pune–Mumbai). Period 2023-01-01 → 2025-12-31.
- **stations.csv:** station_id, name, lat, lon, elevation_m, cadence_min.
- **Screen the clean base with Tier 0 before injecting faults** (Meteostat data has its own gaps/errors).
- **Do-not-flag windows (real extremes, no injection):** May–June 2024 NW India heatwave; any cyclone landfall affecting cluster (b) in 2023–2025. Look up exact dates and cite sources in README.
- **Optional:** ERA5 reanalysis as a background field for sparse-neighbour stations (skip if time is short).
- **Official IMD data** (IMD Data Supply Portal) may not arrive in time; do not depend on it.

---

## 5. Architecture

```
Sources (AWS stream | historical archive | fault injector)
        → Ingest & normalise (units, resample, dedupe, gap + timestamp checks, attach station metadata)
        → 4 independent tiers in parallel:
             T0 Physics rules | T1 Station history | T2 Cross-variable | T3 Neighbours
        → Evidence fusion + coherent-event gate  →  P(fault), severity, root cause
        → XAI explainer | Imputer | Sensor health
        → outputs (scored stream, alerts, metrics)
```

Core bet: each fault type is obvious to exactly one tier and invisible to the others; fusion beats any single model. The ablation study must prove this.

---

## 6. Fault injector (skyguard/inject) — F-01

Takes clean, Tier-0-screened series; writes labelled copy.

| Class | Model | Parameters sampled | Variables |
|---|---|---|---|
| F1 Spike | x_t + s·σ_local, 1 sample or 2–3 samples | s in [3, 15] local std devs, random sign | T, P, RH |
| F2 Stuck | x_t = x_t0 for duration d, optional tiny dither | d in [2 h, 72 h] | one variable at a time |
| F3 Drift | x_t + r·(t − t0) | r so error reaches 0.5–3 °C, 3–15 % RH, 0.5–3 hPa over 7–45 days | T, RH mainly; P rarely |
| F4 Offset | x_t + b for t ≥ t0 | magnitude of b: 0.5–4 °C, 3–15 %, 0.5–5 hPa; random sign | all |
| F5 Noise | x_t + ε, ε ~ N(0, k·σ_local) | k in [1.5, 5], duration 6 h to 10 days | all |
| F6 Saturation | clip(x_t, lo, hi) | RH pinned 100 % or 0 %; T at logger limit | RH, T |
| F7 Dropout | delete rows | single gaps, bursts 3–24 h, periodic loss | all |
| F8 Corruption | sentinel (0, −9999), flip 1 random bit in a 16-bit reading, T↔RH swap, timestamp shift ±1 h | probability per row 0.1–1 % | all |
| F9 Cross-variable | replace one variable with its value from another day or a neighbour, range kept plausible | 1–48 h windows | one of three |

Realism rules:
- Inject into ~3 % of station-hours. Never inside do-not-flag windows.
- ~70 % of injected values stay inside the WMO plausible range (Tier 0 alone must not catch most faults).
- 10 % overlapping faults (e.g. drift then stuck).

Outputs: `observations_injected.parquet`, `labels.parquet` (station, time, variable, class, start, end, magnitude).

CLI:
```
python -m skyguard.inject --in data/clean/ --out data/bench/ --seed 42 --rate 0.03
python -m skyguard.bench  --data data/bench/ --report reports/benchmark_report.md
```

---

## 7. Detection tiers (skyguard/tiers)

Each tier outputs, per variable per observation, a score (robust z or rule flags) plus features. Tiers never decide alone.

### T0 — physics and WMO rules (t0_rules.py) — F-02

| Check | Rule | Flag |
|---|---|---|
| Plausible range | T −80 to 60 °C, RH 0–100 %, P 500–1100 hPa | hard fail |
| Climatological range | outside station-month p0.1–p99.9 widened by 3·IQR | soft |
| Step | absolute change from previous value above WMO limit for consecutive 1-min values (3 °C, 10 %, 0.5 hPa); at coarser cadence, above the station's learned p99.9 step for that cadence | soft |
| Persistence | std over window below 0.1 °C / 1 % / 0.1 hPa per 60 min, window scaled to cadence (e.g. 6 h for hourly); RH 97–100 % exempt when plausibly saturated | soft |
| Dew point | Td ≤ T (WMO rule) and Td ≤ station's highest historical Td + 2 °C (catches impossible pairs like 55 °C at high RH) | soft |
| Sentinels / format | 0 hPa, −9999, NaN strings, duplicate or out-of-order timestamps | hard fail |

Dew point (Magnus, Sonntag constants):
```
gamma = ln(RH/100) + 17.62*T / (243.12 + T)
Td    = 243.12*gamma / (17.62 - gamma)
```

### T1 — station temporal model (t1_temporal.py) — F-03

- One GLOBAL LightGBM quantile model per variable (q10, q50, q90) predicting next value.
- Features: lags 1, 2, 3, 6, 12, 24 h; rolling mean/std over 3 h and 24 h; hour-of-day and day-of-year as sin/cos; station climatology for that hour and month (target encoding); elevation, latitude.
- Score: `z1 = (x_t - q50) / ((q90 - q10) / 2.563)`  (for a normal distribution q90 − q10 = 2.563σ)
- Rationale: learns "normal" from unlabelled data → generalises to unseen fault types.
- Optional companion: 1-D CNN autoencoder on 24-step windows; reconstruction error catches collective anomalies (stuck, noise).

### T2 — cross-variable consistency (t2_cross.py) — F-04

- LightGBM predicts each variable from the other two + time features + lags (e.g. RH from T, P, T-lags, hour); residual z-scores as in T1.
- Actual vapour pressure (changes slowly outside fronts/storms → physics signal for RH faults):
```
e = (RH/100) * 6.112 * exp(17.62*T / (243.12 + T))   [hPa]
```
- Features: 1 h change in e beyond station p99.5 with no matching move in T or P → RH fault; RH flat while T swings ≥ 5 °C implies an unrealistic e swing → F2 or F9; zero-variance run length per variable; same-sign T–RH co-movement in fair weather (feature, not rule).

### T3 — spatial neighbours (t3_spatial.py) — F-05

- Up to k = 8 neighbours within 150 km and 500 m elevation difference (BallTree, haversine). Widen to 300 km in sparse regions and lower confidence.
- Compare deviations, not raw values: d = x − climatology(station, hour, day-of-year). Pressure: use deviation AND 3-hour tendency (absolute station pressure depends on elevation).
- Expected deviation = weighted median of neighbour deviations, w = exp(−dist/75 km) · exp(−|Δz|/300 m).
- Score: `z3 = (d0 - wmedian(d_j)) / (1.4826 * MAD(d_j) + sigma_min)`
- Also output `neighbour_agreement` = share of neighbours whose deviation has the same sign and at least half the size of this station's.
- Stretch only: graph attention network replacing the weighted median.

---

## 8. Fusion, severity, root cause, coherent-event gate (skyguard/fusion) — F-06, F-07

Evidence features (~40): z1, z2, z3 per variable and maxima; T0 flags; zero-variance run length; CUSUM of T3 residual; rolling residual variance ratio; gap length before sample; sentinel/format flags; vapour-pressure jump; neighbour_agreement; count of variables with |z| > 3; cadence.

Heads:
- Binary LightGBM → P(fault), isotonic calibration on held-out fold. Target ECE < 0.05.
- Multiclass LightGBM → F1–F9 or "weather"; trained on injector labels + do-not-flag windows.

Severity (estimated error = |observed − imputed| vs tolerance 0.5 °C, 5 % RH, 0.5 hPa):

| Severity | P(fault) | Estimated error vs tolerance | Action |
|---|---|---|---|
| Critical | ≥ 0.9 | ≥ 5× | withhold from feeds, page QC officer, open maintenance ticket |
| High | ≥ 0.75 | ≥ 2× | replace with imputed value in clean feed, queue for review |
| Medium | ≥ 0.5 | any | pass with suspect flag, show in queue |
| Low | 0.3–0.5 | any | log only; feeds sensor health |

Both conditions must hold for a level; otherwise drop to the next level down.

Coherent-event gate (before any fault verdict):
1. At least 2 of 3 variables moved beyond their T1 band in physically consistent directions (storm: T down, RH up, P up).
2. neighbour_agreement ≥ 0.5, or the same signature appears at neighbours within ±2 h.
3. No T0 hard fail and no sentinel.
If all three hold → label "weather", cap P(fault) at 0.3. If only (1) holds and the station has no neighbours → do not cap; explanation says "possible real event; no neighbours to confirm".

---

## 9. Explanations and imputation — F-08, F-09

Explanation sentence:
1. SHAP TreeExplainer on fusion model → contribution per feature.
2. Map top 3 positive contributors to templates, e.g.
   - `zero_var_run_rh` → "RH unchanged at {v} % for {h} h"
   - `z3_t` → "{n} of {k} neighbours read {d} °C lower"
   - `e_jump` → "implied vapour pressure jumped {x} hPa with no temperature change"
3. Join with root-cause label + recommended action.

Imputation: inverse-variance blend of T2 (same station's healthy sensors) and T3 (neighbours) predictions; T1 as fallback; 80 % interval from blended quantiles. Never overwrite raw data; separate `corrected` column with provenance tag.

Alert JSON shape (values illustrative):
```json
{
  "station_id": "STN_0001",
  "time_utc": "2026-05-19T09:00:00Z",
  "variable": "rh",
  "observed": 97.0,
  "p_fault": 0.94,
  "severity": "high",
  "root_cause": "F2_stuck",
  "explanation": "RH unchanged at 97.0 % for 9 h while temperature rose 6.1 °C; 4 of 5 neighbours read 55–62 %. Likely stuck humidity sensor — inspect and clean or replace the RH probe.",
  "top_factors": [
    {"feature": "zero_var_run_rh", "shap": 1.82},
    {"feature": "z3_rh", "shap": 1.10},
    {"feature": "e_implied_swing", "shap": 0.64}
  ],
  "imputed": {"value": 58.4, "low": 53.9, "high": 63.0, "method": "blend_t2_t3"},
  "tier_scores": {"t0": ["persistence"], "z1": 2.1, "z2": 6.8, "z3": 7.4},
  "model_version": "fusion-0.3.1"
}
```

---

## 10. Sensor health and predictive maintenance — F-10

- Bias: EWMA of T3 residual (λ = 0.02 for hourly data). Two-sided CUSUM on the same residual → drift alarm (F3).
- Days to maintenance: Theil–Sen fit of EWMA bias over last 30 days, extrapolated to tolerance (0.5 °C, 5 % RH, 0.5 hPa). Report only if slope significant, else "stable".
- Health score:
```
H = 100 * (1 - min(1, 0.5*|b|/tau + 0.3*f30 + 0.2*max(0, sigma_r/sigma_ref - 1)))
```
  b = current bias, tau = tolerance, f30 = share of Medium+ alerts in last 30 days, sigma_r = recent residual std, sigma_ref = healthy-period residual std. Weights are starting values; tune on benchmark.

| Health | Status | Ticket |
|---|---|---|
| 80–100 | Healthy | none |
| 60–79 | Watch | check at next routine visit |
| 40–59 | Degrading | schedule visit within forecast window; carry spare |
| < 40 | Failed / failing | urgent; data auto-replaced by imputation |

Self-healing loop: failed sensor values replaced by imputation in clean feed until maintenance is confirmed; then bias baseline resets.

---

## 11. Requirements that affect the engine

Functional:
- FR-1 ingest CSV/JSON rows at any fixed cadence 1 min–1 h.
- FR-2 score every observation within one cycle: P(fault) per variable and overall.
- FR-3 severity from P(fault) and estimated error size (§8).
- FR-4 root cause F1–F9 or "weather".
- FR-5 one-sentence explanation + top-3 factors.
- FR-6 imputed value with 80 % interval.
- FR-7 0–100 health per sensor with trend and days to maintenance.
- FR-9 injector CLI + benchmark report.

Non-functional:
- NFR-1 p95 latency < 50 ms per observation; 1,000 stations per hourly cycle in < 60 s on a 4-core CPU, no GPU.
- NFR-2 one global model family; a new station needs only metadata + 30 days history.
- NFR-3 cold start: new station runs on T0, T2, T3 until T1 has 30 days.
- NFR-4 graceful degradation: missing neighbours/variable lowers confidence, never crashes.
- NFR-5 reproducible: fixed seeds; benchmark rerunnable in one command.
- NFR-6 every alert auditable: inputs, tier scores, model version, explanation stored.
- NFR-8 open formats only: CSV/Parquet in, JSON out.

Input row schema: station_id (str), time_utc (ISO 8601), temp_c (float, °C), pressure_hpa (float, station level), rh_pct (float, %), edge_flags (int bitmask, optional). At least one of the three variables required.

---

## 12. Targets (ours; set to beat the WMO rule baseline)

| Metric | Target | Measured on |
|---|---|---|
| Macro-F1 across F1–F9 | ≥ 0.90 | injected benchmark, held-out stations |
| Uplift vs WMO rules | ≥ +0.15 F1 on drift, offset, cross-variable | same |
| False alarms on real extremes | < 2 % of observations | do-not-flag windows |
| Root-cause top-1 accuracy | ≥ 85 % | correctly detected faults |
| Drift detection delay | < 72 h after drift reaches 1 °C / 5 % RH / 1 hPa | injected drift |
| Imputation MAE | ≤ 0.8 °C, ≤ 5 % RH, ≤ 0.5 hPa | masked real values |
| Latency | p95 < 50 ms per observation | streaming replay |
| Calibration | ECE < 0.05 | benchmark |
| Edge model | < 50 KB int8, < 10 ms on ESP32-S3 (not measurable without hardware) | — |

Report actual results honestly even if below target.

---

## 13. Evaluation protocol — F-14

1. Split BY STATION: 70 % train, 15 % validation, 15 % test. Second split: last 12 months held out for temporal generalisation.
2. Inject faults into validation/test with fixed seeds; report per-class precision, recall, F1, median detection delay.
3. Baselines on same data: (a) WMO rules only; (b) Isolation Forest on (T, P, RH, hour); (c) per-station LSTM autoencoder (optional if time is short). SkyGuard must beat them on macro-F1.
4. Ablation: remove T1, T2, T3 one at a time; report macro-F1 and per-class F1 drop.
5. False-alarm test: do-not-flag windows; report alerts per 1,000 observations.
6. Latency/throughput: replay test stations; log p50/p95 per-observation latency.

---

## 14. Use cases the outputs must demonstrate

| ID | Scenario | Expected behaviour | Deciding tier |
|---|---|---|---|
| UC-1 | 55 °C with high RH, neighbours normal | T0 hard fail (4 °C above India record 51.0 °C; impossible dew point), T3 disagreement, gate fails → P(fault) > 0.99, Critical, F1 or F8, value withheld, imputed value suggested | T0 + T3 |
| UC-2 | Real heatwave, Rajasthan 49–51 °C, low RH | no fault; labelled "weather" | T3 + gate |
| UC-3 | Pre-monsoon squall: T −8 °C in an hour, RH up, P up | passes as weather | T2 + gate |
| UC-4 | Cyclone landfall pressure fall | passes; health unaffected | T3 |
| UC-5 | RH stuck at 97 % for 9 h | F2 by hour ~3, High, RH imputed | T0 + T2 |
| UC-6 | T drifts +1.5 °C over 3 weeks | CUSUM alarm, health → Degrading, days-to-maintenance shown | T3 + health |
| UC-7 | Satellite dropout then corrupted frame (0 hPa, swapped fields) | F7 gap logged; F8 flagged; no false drift alarm after gap | T0 |
| UC-8 | New station, no history | runs on T0, T2, T3; T1 after 30 days; lower confidence stated | cold-start rule |

---

## 15. Edge tier (code + model only; no hardware) — F-13

- Hardware target: ESP32-S3 + BME280 (measures T, P, RH over I²C).
- Model: 1-D CNN autoencoder, 24 steps × 3 variables, exported to TensorFlow Lite, int8-quantised, target < 50 KB.
- On-device checks: range, step, persistence, dew point, reconstruction error > threshold → 8-bit flag byte per packet.
- Duty cycle: wake every 60 s, read, infer, sleep. Reference measurements (ESP32-S3 dev board at 3.3 V): ~105 mW awake, ~0.026 mW deep sleep → ~0.55 mW average at ~0.3 s awake per minute, before radio (estimate).
- Reference: a quantised LSTM autoencoder on ESP32 ran in ~4 ms at 0.27–0.33 W (Hammad et al. 2023).
- Label everything "not run on hardware".

---

## 16. Tech stack and repo layout

Python 3.11; pandas, numpy, pyarrow, meteostat, scikit-learn, lightgbm, shap, scipy, matplotlib, joblib (pin versions). Optional: torch or tensorflow for the autoencoder/TFLite export.

```
skyguard/
  skyguard/
    ingest/     # loaders, normaliser, metadata
    inject/     # fault models F1-F9, CLI
    tiers/      # t0_rules.py, t1_temporal.py, t2_cross.py, t3_spatial.py
    fusion/     # meta-model, calibration, event gate, severity
    explain/    # SHAP -> sentence templates
    impute/
    health/     # EWMA, CUSUM, RUL
    bench/      # metrics, baselines, ablation
  edge/         # TFLite export, ESP32 sketch outline
  notebooks/    # 01_data, 02_inject, 03_train, 04_eval, 05_usecases
  outputs/      # metrics.json, benchmark_report.md, figures/, scored_stream.*, alerts_examples.json
  Makefile      # make data | inject | train | bench | all
  requirements.txt
  README.md
```

Required outputs for the dashboard task:
- `outputs/scored_stream.parquet` and `outputs/scored_stream_sample.json` (test stations, last 14 days; one row per station-hour: observed values, tier scores, p_fault, severity, root_cause, explanation, imputed value + interval, health scores)
- `outputs/metrics.json`, `outputs/benchmark_report.md`
- `outputs/figures/`: per-class F1 vs baselines, ablation, confusion matrix, example station raw vs corrected with fault spans, heatwave window with no alerts
- `outputs/alerts_examples.json`: 10 diverse alerts in the §9 shape
- `stations.csv`

---

## 17. References

- Zahumenský, I. (2004). Guidelines on Quality Control Procedures for Data from Automatic Weather Stations. WMO CBS.
- Ranalkar, M.R. et al. (2015). Development of operational near real-time network monitoring and quality control system for implementation at AWS data receiving earth station. MAUSAM 66(1), 93–106.
- Båserud, L. et al. (2020). TITAN automatic spatial quality control of meteorological in-situ observations. Adv. Sci. Res. 17, 153–163. Library: github.com/metno/titanlib
- IMD Pune training material: Introduction to AWS; Notes on AWS and ARG.
- Hammad, S.S., Iskandaryan, D., Trilles, S. (2023). An unsupervised TinyML approach applied to the detection of urban noise anomalies under the smart cities environment. Internet of Things 23, 100848.
- World Weather Attribution: Phalodi 51.0 °C, 19 May 2016.
- Meteostat Python library documentation (dev.meteostat.net).
