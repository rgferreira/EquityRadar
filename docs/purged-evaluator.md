# Purged rolling-origin evaluator

Phase 3.8 PR-005 adds an offline diagnostic evaluator over immutable prediction snapshots and `benchmark-relative-v1` outcomes. It cannot alter live scores, activate a model, or promote a champion.

## Pre-registered v1 contract

- Primary horizon: 3M benchmark-relative return after the PR-004 cost convention.
- Rolling-origin test groups are whole decision dates; same-date tickers are one correlated cluster, not independent samples.
- Training observations are eligible only when their target-label end date is strictly before the test date's five-calendar-day embargo boundary.
- Candidate decisions and frozen base-score, zero-relative benchmark, `always_buy`, `always_wait`, and technical-momentum baselines use exactly the same test prediction IDs.
- Utility and decision accuracy are averaged within date first. Normal-approximation 95% intervals use independent date-cluster means and remain unavailable with one date.
- Reports distinguish `insufficient_evidence` from evaluated underperformance. The default requires three independent test dates.
- Per-ticker diagnostics are descriptive only and do not increase the independent-date count.

Run locally with:

```bash
python -m scripts.run_purged_evaluation
```

Use `--horizon`, `--embargo-days`, `--database`, or `--output` to make an alternative configuration explicit. Each configuration and immutable dataset signature produce a deterministic evaluation ID. The append-only `evaluation_runs` registry stores configuration/report hashes and metadata; it has no model-registry write path.

## Interpretation and rollback

Small effective samples are expected and are a valid `insufficient_evidence` result. Reports are not evidence of alpha and are not a permission to tune repeatedly. Rollback removes the evaluator consumer/CLI while retaining immutable reports for audit.

The first diagnostic motivated one explicitly pre-registered, offline-only missing-valuation experiment. Its frozen hypothesis and confirmation dates are documented in [`coverage-aware-challenger.md`](coverage-aware-challenger.md); it has no live-model or promotion path.
