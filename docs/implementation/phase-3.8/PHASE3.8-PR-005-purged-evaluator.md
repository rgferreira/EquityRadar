# PHASE3.8-PR-005 — Purged evaluator

## Objective

Evaluate frozen predictions out of sample with horizon-aware leakage controls, transparent baselines, and uncertainty reporting.

## Finding status

F-04/F-05/F-17/F-27 partially apply. The 21-day episode selector reduces duplicates but is not a purged rolling-origin evaluation and does not control overlapping horizons, date clusters, survivor selection, or multiple comparisons.

## Scope

- Add an offline rolling-origin evaluator over immutable predictions and versioned relative outcomes.
- Purge/embargo training observations whose label windows overlap validation/test windows.
- Group or cluster correlated observations by decision date and ticker as specified.
- Compare against transparent baselines such as no-learning/base score, broad benchmark, and simple momentum/always-wait policies where meaningful.
- Report sample counts, coverage, point estimates, uncertainty intervals, and per-period/per-ticker diagnostics.
- Persist evaluator configuration and report metadata, not a promoted model decision.

## Non-goals

- No live score changes, automated hyperparameter search, opaque ML, multiple-comparison fishing, or automatic model promotion.
- No use of the sanitized evidence pack as a training or validation dataset.

## Probable files

New evaluator module and CLI under `src/`/`scripts/`, registry/outcome database reads, synthetic evaluator tests, generated report documentation.

## Data and migration

Prefer immutable report artifacts plus a small append-only evaluation-run registry keyed by configuration hash. It depends on PR-003 prediction IDs and PR-004 label versions.

## Tests

- Synthetic overlapping horizons prove purge/embargo behavior.
- Identical-date observations remain clustered rather than counted as independent evidence.
- Baseline and candidate use identical test windows and label versions.
- Empty/small samples produce explicit insufficient-evidence results.
- Deterministic seed/config produces repeatable reports.

## Acceptance criteria

- No training observation can overlap the evaluated label window.
- Reports show coverage, baselines, uncertainty, and all evaluation assumptions.
- The evaluator cannot change live scores or champion status.
- Results distinguish “not enough evidence” from underperformance.

## Risks and rollback

Risk: small effective samples may prevent conclusions; that is a valid result, not a failure. Rollback removes the evaluator consumer/CLI and leaves immutable predictions/outcomes untouched.
