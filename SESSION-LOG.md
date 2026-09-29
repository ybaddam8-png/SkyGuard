# Session log

## 2026-09-29 — fix/dashboard: static demo mode, real metrics wiring, no-fake-data pass

Done by Claude Code (Claude Sonnet 5), branched off `fix/benchmark` so the dashboard picks
up every fix from that branch (corrected injector, bounds, baselines, metrics, SHAP
explanations, imputation, figures). User was away for this part; decisions below were
made autonomously per their instruction.

1. **Copied regenerated engine outputs** into `client/src/data/`: `metrics.json`,
   `scored_stream_sample.json`, `alerts_examples.json`, `stations.csv`, and all 5 figures.
2. **Found and fixed a real bug on `fix/benchmark`** while wiring this up: `tier_scores_for()`
   in `src/run_step2.py` emitted bare Python `NaN` (invalid JSON) for F7-dropout rows,
   which broke the Vite JSON import once `alerts_examples.json` was actually read by the
   client. Fixed with a NaN/inf-safe rounding helper and `allow_nan=False` on both
   `json.dump` calls so a future regression fails the pipeline loudly instead of shipping
   broken JSON silently.
3. **Static demo mode** (`VITE_STATIC_DEMO=1`, now the `pnpm build` default): `useAuth`
   disables its `trpc.auth.me` query via react-query's `enabled: false` instead of hitting
   a server that won't exist; `getReplayState`/`listFeedback` queries are disabled the same
   way; operator feedback, injected-fault events, and replay scrub position are read/written
   to `localStorage` (wrapped in try/catch) instead of calling the tRPC mutations; the
   sign-in button is hidden entirely. Also removed `pnpm.patchedDependencies` from
   `package.json` — it pointed at `patches/wouter@3.7.1.patch`, which was never committed
   anywhere in git history and blocked `pnpm install` outright.
4. **No-fake-data pass**: the KPI row, nav alert-queue badge, network-view coverage/consensus
   stats, station watchlist readings, sensor-health scores, and the alert drawer's tier
   consensus/explanation/top-factors/imputed-value block were all hardcoded or fabricated
   before this session (e.g. a health score literally computed as `i===0?74:i===4?68:...`).
   Every one of those now derives from `client/src/data/*` at render time - health scores
   blend real station coverage with real recent fault rate from the scored stream; the
   drawer's tier consensus/explanation/top factors/imputed value read straight from each
   alert's `tier_scores`/`explanation`/`top_factors`/`imputed` fields (real SHAP + imputation
   output from `fix/benchmark`, not the old generic template).
5. **Injected-fault alerts now actually reach the alert queue** - the "Inject anomaly" flow
   previously only moved the map marker; the new fault was never added to `liveAlerts`.
   Added a small `injectedAlerts` local-storage-backed list so every fault type triggers a
   real, visible queue entry (verified for F1/F2/F3/F5/F6/F8; F4/F7/F9 aren't in the
   Injector's own dropdown, that's unchanged pre-existing scope).
6. Added `<link rel="icon" href="data:,">` to `client/index.html` to stop the browser's
   default favicon request from showing as a console 404.

**Verified with `npx playwright cli`** (fresh persistent profile, 1920x1080, against
`pnpm run preview` serving the `pnpm build` output): network map, alert queue, station
drill-down with the Why panel open, sensor health, benchmark evidence, and the heatwave
protected-window figure all load with zero console errors; `Play` advances the replay;
injecting a fault increments the alert-queue badge and appears at the top of the queue.
Screenshots in `outputs/screenshots/`. `pnpm run check` (tsc), `pnpm run build`, and
`pnpm test` (existing server vitest suite) all pass.

**Build and preview locally:**
```bash
pnpm install
pnpm run build     # VITE_STATIC_DEMO=1 by default - no server/login needed
pnpm run preview   # serves dist/public at http://localhost:4173
```

**Not done, deliberately out of scope**: no deployment anywhere - not asked, and the user
said to ask first. `dist/` chunk-size warning (985 kB JS bundle) is pre-existing and
unrelated to this session's changes; left alone.

## 2026-09-28 — fix/benchmark: fix injector, bounds, baselines, metrics, explanations, figures, repro

Done by Claude Code (Claude Sonnet 5), following an external review of `src/run_step2.py`.
Environment: fresh `.venv` (uv, Python 3.11) since none existed on this machine; packages
pinned via `uv pip freeze` into `requirements.txt` after a clean pipeline run.

7 commits on `fix/benchmark`, one per bug category, each verified with a full
`src/run_step2.py` run + `pytest tests/` before committing:

1. **Injection rate**: `inject_faults()` drew a fixed per-class-per-station event count
   (`int(len(eligible)*0.0035)`), which produced 66.2% station-time coverage once long
   fault durations were accounted for, against a ~3% spec target. Rewrote as a
   coverage-budgeted sampler (target 3.2-4.5%, split across 9 classes with a capped
   Dirichlet draw so no class exceeds 28%) and moved it to `src/skyguard_inject.py` with
   its own test suite. Result: 4.19% overall coverage, largest class share 19%.
2. **Physical bounds**: clipped all classes except F1 (gross spike) and F8
   (sentinel/bit corruption) into `temp_c[-80,60]`/`mslp_hpa[870,1085]`/`rh_pct[0,100]`
   after stacking; fixed F6 to pin RH to exactly 100 or 0 (50/50) instead of only ever
   the upper bound.
3. **Fair baselines**: IsolationForest `contamination` now uses the training fold's own
   prevalence (`y[tr].mean()`) instead of a hardcoded 0.03; added an "always fault"
   trivial baseline (F1 0.080 ± 0.009, vs the fusion model's 0.584 ± 0.113).
4. **Missing metrics**: fixed an inverted ablation bug (the `no_T1`/`no_T2`/`no_T3` column
   lists were backwards — training on the tier being ablated instead of excluding it);
   added false alarms per 1,000 obs inside each protected window, expected calibration
   error before/after per-fold isotonic calibration (0.076 -> 0.018), p50/p95 scoring
   latency (0.99 ms / 1.76 ms), and per-fold macro-F1 (previously only a single OOF
   aggregate).
5. **Explanations and imputation**: replaced the hardcoded alert template with real SHAP
   TreeExplainer output per row (using the fold that scored it out-of-fold), mapped to
   plain-language templates; added T2 (climatology) / T3 (neighbour) inverse-variance
   blended imputation with an 80% interval, T1 quantile fallback when no neighbour data
   exists. `alerts_examples.json` now covers all 9 fault classes (was only ever 2-3
   classes when sampled from the last-14-day tail alone).
6. **Figures**: `heatwave_no_injection.png` now overlays alert markers (P(fault)>=0.5)
   inside protected windows and reports the alert count in the title.
7. **Reproducibility**: `requirements.txt` (pinned, `uv pip freeze` from a clean run),
   `Makefile` (`make bench`/`test`/`all`), `tests/test_injector.py` (prevalence,
   per-class cap, protected-window integrity, seed-42 reproducibility, bounds, F6 pin),
   and rewrote `README.md`'s status section (previously claimed "no fault injection and
   no model training have been run" despite the whole benchmark engine already existing).

Full `make all` run time: ~3.5 minutes (well under the 20-minute budget).

**What's still weak**: macro-F1 across F1-F9 is 0.41, well under the spec's 0.90 target —
reported honestly, not tuned toward the target. `monsoon_c`'s false-alarm rate (87.7/1000)
is high relative to the other two protected windows, though it's also the smallest window
(342 observations) so it's noisy. No number in this session was hand-edited; every figure
above came from an actual pipeline run.

## fix/slow-faults: injector event-count sampling and slow-signal features

**Diagnosis (before any change).** F3/F4/F5 scored F1 = 0.0 and F9 0.043 for three reasons:
(1) the multiclass head trained on ~76-84k unprotected weather rows against 135-717 rows per
fault class and was scored as an ungated argmax on every row; (2) the spec section 8
slow-signal evidence (T3 residual rolling mean, CUSUM, residual-variance ratio) did not exist;
(3) the old coverage-budget injector produced only 2 F3 events (both in one CV fold, so fold 1
tested F3 with a model that had never seen it), 10 F4, 8 F5 and 5 F9 events. Per-class results
were unmeasurable, so the old numbers are labelled "old injector" and are not like-for-like.

**Changes.**
- `src/skyguard_inject.py`: samples by event count (per-class minimums F1 60, F2 40, F3 24, F4 30,
  F5 30, F6 30, F7 30, F8 60, F9 30; code uses 70/60/24/36/36/30/36/70/36 so F3 stays under 30% of
  labelled rows), cycles stations so every class lands on all 12, no overlapping events or
  protected rows. Durations in 3 h steps: F9 1-16, F3 56-112, F4 8-80, F5 4-80, F2 4-24.
  Documented deviation: F3 is 7-14 days, not the spec's 7-45. Coverage 6.7% (band 4-8%).
- `tests/test_injector.py`: prevalence band 4-8%, minimum events and >= 8 stations per class,
  duration bounds, max class share < 30%.
- `src/run_step2.py`: causal per-station features `slow_t3_*_rmean8/24`, two-sided CUSUM of z3
  clipped to [-5, 5] (k = 0.5), `slow_t1_*_varratio` and `slow_t2_*_varratio` (rolling std over 8
  steps / station healthy std from clean data); multiclass head trained on labelled rows plus
  protected-window weather, `class_weight='balanced'`, root cause only where P(fault) >= 0.5;
  ablation blocks extended with the matching slow features; per-fold test/train event counts
  printed and asserted (no reassignment needed: min 4 test events, min 18 train events per class);
  event-level recall, class-correct recall, median detection delay, alerts per 1,000 steps outside
  events and protected windows, share of alerts inside events; per-class F1 and event recall per
  ablation; paired per-fold ablation differences; confusion matrix saved in `metrics.json`.

**Results (new injector; not comparable to old).** Binary F1 0.484 +/- 0.066, macro-F1 (OOF) 0.433.
Per-class F1: F1 0.528, F2 0.651, F3 0.016, F4 0.061, F5 0.735, F6 0.867, F7 0.104, F8 0.745, F9 0.193.
F5 and F6 recovered; F3, F4 and F9 did not. Stop rule triggered (F3/F4 under 0.2 F1 with 24/36
events): no further changes made.

**Why F3/F4 stay low (measured).** The binary head flags F3 rows at about 4.5% in every quartile of
the event, i.e. no better than its background alert rate, so drift never becomes visible even late
in an event; F4 is flagged at 14-22%. F3 rows are mostly predicted "weather" (1801/1887); of the
F4 rows that are flagged, more are called F3 than F4. Event-level F3 recall of 0.79 is mostly the
background alert rate: about 44 alerts per 1,000 clean steps over an 84-step event makes a stray
flag near-certain, and class-correct F3 recall is 0.25. Read event recall next to the alert rate.

**Ablation.** Flat to slightly negative: removing a tier changes binary F1 by less than fold noise
(paired diffs full - ablated: no_T1 +0.027 mean, 0/5 folds where ablated >= full; no_T2 +0.009,
1/5; no_T3 +0.010 with std 0.044, 3/5). Unlike before, no_T2 no longer beats full in all folds. T2 was not removed.
F7 event recall fell to 0.25 (F1 0.10) under the new injector; not investigated. Hypothesis, unverified:
native source gaps carry the same all-NaN signature as F7 rows.

## fix/detectability — Stage 0: diagnosis (no code change)

Measured on the clean base (T3 residual in physical units = station climatology deviation minus
the distance/elevation-weighted mean of neighbour deviations, same rule as `run_step2.py`).

**a) Noise floor (median over 12 stations).** std of the 1-step / 8-step / 24-step / 56-step mean of
the healthy T3 residual: temp 1.55 / 1.03 / 0.82 / 0.64 °C; mslp 1.04 / 0.68 / 0.59 / 0.54 hPa;
RH 9.0 / 6.4 / 5.2 / 4.5 %. Averaging barely helps (56 steps cuts std only 2.4x, not 7.5x): the
residual is strongly autocorrelated. Minimum detectable bias (3 sigma of the 56-step mean):
temp ~1.9 °C (1.5-2.5), mslp ~1.6 hPa (0.8-5.9; stations 42921 and 43063 are ~5.3-5.9 hPa),
RH ~13 % (10-19).

**b) SNR of injected events** (magnitude / station-variable 56-step-mean std):
F3: <1: 9, 1-2: 6, 2-4: 7, >4: 2. F4: <1: 1, 1-2: 13, 2-4: 13, >4: 9. All 9 RH drift events are
SNR < 1 because the injector draws F3 magnitude 0.5-3 for every variable, while the spec says
3-15 % for RH (injector bug, below spec). Every station holds 1-3 F3 and 2-3 F4 events.

**c) Code audit.**
- CUSUM resets / decision interval: **no** (plain accumulation, no h, no reset). Input centred on the
  station's healthy mean: **no**. Worse: its input z3 uses `sigma_min` = the station's p99.9 3-h
  step (~13 °C, ~6 hPa, ~50 % RH) in the denominator, so a 3 °C offset gives z3 ≈ 0.2, below the
  allowance k = 0.5. The CUSUM and the z3 rolling means added in fix/slow-faults were near-dead.
- T2 includes the target's own lags or rolling stats: **no lags**, but T2 is not a model at all:
  `z2_v = clim_z_v - 0.15 * (other clim_z)`, i.e. mostly the variable's own climatology anomaly.
- Gap rows filled with 0: **yes** (`fillna(0)` on every feature; raw values become 0). Per-variable
  `_missing` flags exist; no `is_missing` (whole timestamp) or `gap_length_before`. Native gaps
  (0.1-17 % of rows per station) are labelled "weather" and look identical to injected F7 rows.
- Coherent-event gate (spec section 8): **not implemented**.
- Also: T1 feeds the target's own lags, so after an offset/drift onset the T1 median follows the
  biased value; T3 uses a weighted mean, not the spec's weighted median.

**d) What explains the failures.** F3/F4: mostly the dead z3 scale (model problem) plus a real
noise floor (15/24 F3 events have SNR < 2; all RH drifts are below floor by injector bug). F7:
label ambiguity with native gaps; the model cannot separate them from features. Wrong
hypotheses from fix/slow-faults: that the slow features "did not help" was not evidence of a
noise floor, because they were built on a z-score whose floor swamped any bias; and the CUSUM
[-5, 5] clip was irrelevant because z3 almost never exceeded 0.5.

## fix/detectability — Stage 1: label and evaluation definitions

Changes: F3 injector magnitude back to spec (RH 3-15 %, variable T 45 % / RH 45 % / P 10 %);
F3 pre-detectable rows (error below tolerance) get weight 0 and are not scored (1,108 rows);
deterministic T0 gap rule (missing timestamp => F7, P(fault) = 1); `is_missing` and
`gap_length_before` features; native-gap rows (11,219) excluded from row scoring, clean-step alert
rate and protected-window false alarms; raw T3 residual `r3_*` computed (not a model input yet) for
the healthy noise floor and SNR; detectability curve by SNR bin. `make all` and pytest pass.

Result (definitions changed, so not like-for-like with fix/slow-faults): binary F1 0.621 +/- 0.056,
macro-F1 0.544. Most of the jump is definitional: F7 is now 0.997 F1 by construction (gap rule),
and F3's untestable early rows are no longer scored. Monsoon false alarms 78.9 -> 3.2 per 1,000:
the old number was mostly the model flagging native gaps inside the window, which are now
excluded. Alerts per 1,000 clean steps 44.1 -> 31.0. F3 F1 0.080, F4 0.144, F9 0.179.
Class-correct event recall at SNR >= 3: F3 0.60 (5 events), F4 0.58 (19 events).
Learned-model evidence for slow faults is unchanged in this stage (no new features yet).

## fix/detectability — Stage 2: slow-signal features (STOP RULE TRIGGERED)

Changes: T2 is now a pure cross-variable LightGBM quantile model (other two variables' values,
lags, rolling stats, climatology anomaly, time, site, target station climatology; no own lags or
rolling stats), replacing the `clim_z` proxy. Healthy-period baseline: every T1/T2/T3 residual is
centred and scaled by the station-variable's own clean-data mean and std. On the T1 and T3
residuals: rolling mean 8/24/56, level change (mean of last 8 minus mean of steps t-39..t-16),
causal least-squares slope 24/56, two-sided CUSUM (k = 0.5, h = 5, reset after alarm) and CUSUM
alarm count over 56 steps; variance ratio on T1/T2/T3. The dead z3-based slow features were
removed. Ablation blocks cover `t2_q*` and all `slow_t{1,2,3}_*`. `make all` and pytest pass.

Result vs Stage 1 (same definitions): binary F1 0.621 -> 0.694, macro-F1 0.544 -> 0.577,
F3 F1 0.080 -> 0.133, F4 0.144 -> 0.277, ECE raw 0.097 -> 0.058, alerts per 1,000 clean steps
31.0 -> 21.6, protected-window false alarms heatwave 1.2 -> 1.9, biparjoy 4.8 -> 0, monsoon 3.2 -> 0.
F3's detectable-window flag rate now rises 21 % -> 30 % across the event (was a flat 4.5 %).

Stop rule: class-correct event recall at SNR >= 3 is F4 0.68 (19 events, passes) but F3 0.00
(5 events, any-class 0.60). Stopped before Stages 3-4 as instructed.

Diagnosis: 2 of the 5 SNR >= 3 F3 events (both pressure) are not flagged at all; the other 3 are
flagged at 3-14 % of rows and called F4 or F2. Across all scored F3 rows, 84 are called F3 and
82 F4. The drift-shape feature does not separate: median |slope56| of the normalised T3 residual
is 0.012 on F3 temperature rows, identical to weather rows (0.012), while level change separates
F4 (0.93) from weather (0.45). The residual is strongly autocorrelated (Stage 0: the 56-step mean
std is only 2.4x below the 1-step std), so a 1-3 °C ramp over 7-14 days looks like the residual's
own slow wander. The SNR definition (final magnitude / 56-step-mean std) also overstates a ramp's
detectability: the mean error over a window is about half the final magnitude. With 5 events the
0/5 is weak evidence, but no stage produced class-correct drift detection. T3 slow features hurt
F3 classification (no_T3 class-correct F3 event recall 0.24 vs 0.14 full) and help F4
(no_T3 F4 F1 0.200 vs 0.277). Also: `doy_sin`/`doy_cos` are the top binary-head features by split
count, which suggests the head spends capacity on timing noise.

Not done (stop rule): Stage 3 (more stations), Stage 4 (monsoon diagnosis, coherent-event gate,
training-fold operating point, AUC-PR).

## fix/detectability — Stage A: calendar shortcut check, placebo windows, natural extremes

Change: fusion heads (binary and multiclass) no longer get `hour_sin/cos`, `doy_sin/cos` or the
month-hour climatology lookup `*_clim_mu` (a calendar proxy added as a T2 input in Stage 2). T1/T2
keep time features as forecasters. A with-calendar binary head is refit per fold for comparison.
Placebo windows: each protected window shifted +182 days, in both clusters (fixed rule, chosen
before results; faults occur inside them). `make all` and pytest pass.

| | With calendar (Stage 2) | No calendar (default) |
|---|---:|---:|
| Binary F1 (fold mean) | 0.694 | 0.694 |
| Macro-F1 (OOF) | 0.581 | 0.587 |
| Alerts / 1,000 clean steps | 21.6 | 23.3 |
| Clean alerts / 1,000: heatwave_a / biparjoy_a / monsoon_c | 1.9 / 0 / 0 | 1.9 / 0 / 0 |
| Placebo windows (6), clean alerts / 1,000 | 3.4-14.2 | 3.4-22.1 |

Calendar features were not the shortcut: protected-window false alarms are identical with and
without them, and recall did not collapse (0.685 -> 0.694), so no-calendar stays the default.
But the protected windows are still much quieter than ordinary clean data (0-1.9 vs 23.6 per
1,000). Placebo windows at other times of year land at 3.4-22.1, closer to ordinary data.
A second, unintended effect explains part of the gap: causal rolling features spill over after an
event ends. Clean rows 1-8 steps after an event alert at 142.6 per 1,000; 9-24 steps 25.5;
more than 112 steps 17.9. Protected rows sit a median 259 steps from any event, so they never
get spillover. Even against the 17.9 far-from-event rate, the protected windows are quieter;
likely real (heatwave and monsoon are spatially coherent, so neighbour residuals are small), but
unproven. The low protected-window numbers should not be read as a general false-alarm rate.

Natural extremes (clean rows only, test folds, fold mean alerts per 1,000; all clean = 22.5):
top 0.5 % temp 7.4 (519 rows, 0.33x), bottom 0.5 % MSLP 13.5 (487 rows, 0.60x), top 0.5 % 3-step
change in any variable 54.7 (1,308 rows, 2.44x), bottom 0.5 % 3-step change 44.8 (1,372 rows,
1.99x). None exceeds 3x clean. Level extremes are alerted less than ordinary rows; fast changes
about 2x. With calendar features the change rows are 45.4 / 40.6. Removing a tier does not bring
change-row alerts down much (no T2: 46.0 top change); no single tier drives them.

## fix/detectability — Stage B: baselines on the current benchmark

Same evaluation definitions for every detector (pre-detectable F3 rows and native gaps excluded),
fold mean ± std of binary F1: fusion 0.694 ± 0.053; fusion without the F7 gap rule 0.694 ± 0.053;
T0 rules incl. gap rule 0.491 ± 0.060; T0 without gap rule 0.474 ± 0.061; Isolation Forest
(contamination = training-fold prevalence) 0.427 ± 0.090; always-fault 0.127 ± 0.010.

F7, both ways: injected-gap recall 1.000 with and without the gap rule; precision 0.994 with native
gaps excluded, 0.014 when native gaps count as negatives (all 11,219 native-gap rows are called F7).
The gap rule changes nothing: because native gaps carry weight 0, the learned model maps
`is_missing` to F7 by itself. F7's 0.99 F1 is therefore definitional either way: it rests on
excluding native gaps from scoring. Treating native gaps as negatives (fix/slow-faults) gave F7
F1 0.104. `make all` and pytest pass.

## fix/detectability — Stage C: drift labelling

Changes: slope features on the T1/T3 residuals are now z-scores of slope (divided by the
station-variable's healthy-period std of the same causal slope, clean base only); causal shape
features over the last 56 steps: R^2 of a straight-line fit (ramp) and R^2 of the best single
step (offset), on T1 and T3 residuals. SNR reported two ways: mean error over the event (used for
the detectability table) and final magnitude (second table). `make all` and pytest pass.

Result vs Stage B: binary F1 0.694 -> 0.707, macro-F1 0.587 -> 0.603, F3 F1 0.156 -> 0.172,
F4 0.292 -> 0.325, F9 0.215 -> 0.224, alerts per 1,000 clean steps 23.3 -> 20.1. F3 class-correct
event recall 0.286 -> 0.238 (21 detectable events, so +/-1 event); F4 0.556 -> 0.611.

Drift at mean-error SNR >= 3: 1 event, not class-correct (0/1). Below 0.5 -> diagnosis, move on.
Diagnosis: by mean-error SNR, 20 of 21 detectable F3 events sit below SNR 2 (8 below 1). A spec
drift of 0.5-3 °C / 3-15 % RH over 7-14 days has a mean error of half that, which on this
6-station-per-cluster network is at or under the T3 noise floor (56-step-mean std ~0.64 °C,
~4.5 % RH). By final magnitude 5 events are >= 3 and 0 of them are class-correct. This is mainly a
noise-floor problem for F3 on the current network; the shape features did not separate the few
events above it. More stations (denser neighbours, lower T3 noise) is the next lever.

## fix/detectability — Stage D: 15-station default, 20-station comparison

Data prep now selects stations automatically from `data/clean/candidate_synoptic_coverage.csv`
(`model=False`, no interpolation, exact synoptic timestamps, same code path; `meteostat==1.7.6`
added to requirements.txt; nullable Float64 cast to float64, values unchanged; cadence pinned to
3-hourly). Cluster (a): 9 stations at >= 50 %; cluster (c): 6 at >= 50 %, so the 35 % fallback
added 5 `low_coverage` stations (43157, 43002, 43001, 43109, 43057). Re-fetched data for the
original 12 stations is identical to the previous fetch. Injector event counts scale with station
count (per-class minimums unchanged); default GroupKFold needed no reassignment.

The first 20-station run exposed a metric bug: F7 precision 1.11, because injected F7 events that
span a native gap were counted as true positives but excluded from the denominator. Fixed
(injected-gap rows now exclude native gaps): 20 stations 0.951, 15 stations 0.896.

Decision (the user's, with the reason fixed in advance): the default is the 15-station set (the 35 %
floor was a fallback; 15-station F1 0.698 is within 0.03 of Stage C's 0.707). `stations.csv` keeps
all 20 rows with `in_default_set` and `low_coverage`; `SKYGUARD_ALL_STATIONS=1` writes the 20-station
comparison to `outputs/all_stations/` and `data/bench/all_stations/` (outputs copied from the
20-station run with the same code). Full tables are in README "Station-set comparison".

15 vs 20 stations: binary F1 0.698 vs 0.651; macro-F1 0.597 vs 0.592; alerts per 1,000 clean steps
22.9 vs 33.3; false alarms per 1,000 heatwave 3.7 vs 9.1, biparjoy 3.3 vs 6.5, monsoon 0.0 vs 20.0.
The false-alarm rise came with the 5 low-coverage coastal stations, though the fold assignment and
injected events also differ between the two runs. Ablation, 15 stations: removing T1 +0.051 (0/5
folds), T2 +0.014 (0/5), T3 +0.030 (1/5): every tier now helps, unlike the 12-station runs.
Drift (F3) class-correct event recall 0.48 over 30 events (12 stations: 0.24 over 24).
Versus Stage C (12 stations): binary F1 0.707 -> 0.698, macro-F1 0.603 -> 0.597, F3 F1 0.172 -> 0.197,
F4 0.325 -> 0.208, F9 0.224 -> 0.300; heatwave false alarms 1.9 -> 3.7, biparjoy 0 -> 3.3.
`make all` (pytest 8 passed), `make sync-dashboard`, `pnpm run build` and `pnpm run check` pass.

## fix/detectability — Stage E: coherent-event gate, operating point, explanation quality (15 stations)

Coherent-event gate implemented as spec section 8 (>= 2 of 3 variables beyond the T1 q10-q90 band;
T and RH, when both out, in opposite directions; pressure either way; mean neighbour_agreement over
those variables >= 0.5, which at 3-hourly cadence is the same test as "same signature within +-2 h";
no T0 hard fail or sentinel; not a gap; P(fault) capped at 0.3). It gates 6,606 rows, 866 of them
injected-fault rows. Result: recall 0.681 -> 0.620, F1 0.698 -> 0.662, false alarms per 1,000
heatwave 3.7 -> 2.9, biparjoy 3.3 -> 3.3, monsoon 0 -> 0. Fault recall got worse, so the gate is
REVERTED (`GATE_ON=False`); both columns stay in the report. (The first gated run also left the
ablation heads ungated, which skewed its ablation; the reverted run is consistent.)

Operating point from training folds only (4-fold grouped CV inside the training stations, threshold =
98th percentile of out-of-fold P(fault) on clean, unprotected training steps): threshold 0.503 ± 0.024,
test precision 0.719, recall 0.682, F1 0.699, alerts per 1,000 clean test steps 23.3 ± 8.4 (target 20:
not met on test; the test stations are noisier than the training ones). At 0.5: precision 0.717,
recall 0.681, F1 0.698, 23.0 per 1,000. AUC-PR 0.752 ± 0.048.

Alert sentences now name witnesses: T0 rules, T1, T2, T3 (|healthy-baselined residual| > 3 objects;
T3 abstains without neighbours) and a slow-signal witness (24-step mean). Explanation quality (top SHAP
factor of the binary head on flagged injected-fault rows, up to 300 per class): F1 from T1 0.011
(T0 step rule 0.91); F2 from T0/T2 0.963; F3 from T3/slow 0.800 (mostly slow T1 features); F4 0.747;
F9 from T2 0.641. Weakness seen: the slow-signal witness can quote a very large 24-step mean that is
spillover from a nearby injected sentinel (F8 -9999). `make all` (pytest 8 passed),
`make sync-dashboard`, `pnpm run build` and `pnpm run check` pass.

## fix/detectability — polish: alert sentences and PS reading

Alert sentences cap every quoted score at ">10 sigma" (tier z-scores, witness residuals, largest tier
score, climatology z), and the slow-signal witness is not quoted when a T0 sentinel or hard-fail flag
is set on the row. Regenerated via `make all` (explanations need the fold models); metrics unchanged
(binary F1 0.698, macro-F1 0.597). Checked all 110 explanation sentences in `alerts_examples.json` and
`scored_stream_sample.json`: none quotes a number above 10 sigma. README gained "Limits and reading of
the PS". `make all` (pytest 8 passed), `make sync-dashboard`, `pnpm run build` pass.
