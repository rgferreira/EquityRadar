# Preregistered research hypothesis: options-positioning-v1

Status: **coverage accumulation only**. Created 2026-07-14.

## Hypothesis

Changes in liquid, consistently observed put/call and implied-volatility evidence may add incremental
3-month benchmark-relative decision utility after controlling for the live technical, valuation, risk,
industry and FINRA evidence families.

## Admission gate

- At least 20 distinct dated options snapshots per included ticker.
- At least 75% options coverage across daily positioning snapshots.
- No gap longer than seven days in the admitted interval.
- At least 20 same-date observations with short-interest evidence.
- Verified `known_at` semantics and a fixed liquid-contract selection policy before evaluation.

## Evaluation

Use the existing purged, date-clustered evaluator. Compare the frozen live policy with and without the
options feature on identical observations. Report benchmark-relative utility, decision accuracy,
downside, independent dates and confidence intervals. Missing options evidence remains missing.

## Promotion boundary

Coverage readiness authorizes only an offline experiment. It does not authorize score changes, a shadow
model, or promotion. Any challenger requires a versioned specification and prospective shadow period.
