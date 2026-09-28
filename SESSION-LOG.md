# Session log

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
