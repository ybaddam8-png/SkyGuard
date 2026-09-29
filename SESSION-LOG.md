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
