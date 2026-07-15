# FINRA report-date freshness correction — 2026-07-15

## Finding

Short-interest freshness was operationally displayed using download time in some surfaces, initial official-history completion could prevent later refreshes, and the decision modifier did not enforce a maximum report age. A freshly downloaded old report could therefore appear current and influence Entry/Exit scores.

## Corrected policy

- Live version: `coverage-aware-renormalized-v4-finra-freshness-live`.
- Rollback anchor: immutable `coverage-aware-renormalized-v3-live`.
- Freshness clock: official FINRA reporting/settlement date, never `fetched_at`.
- Maximum report age: 28 calendar days at the decision cutoff.
- Missing, future, unverified or stale short-interest evidence contributes zero short-interest directionality.
- Factor weights, thresholds and labels are unchanged.

## Restatement contract

Saved ticker/cutoff simulations are recalculated under the corrected version and inserted as new immutable rows. Existing scores, predictions, outcome labels and legacy simulations are never overwritten. Normal accuracy and learning views select the active corrected version; a private local audit report records score, signal and accuracy deltas by ticker.

## UI and operations

Operations now exposes official report date, age and score eligibility per ticker. Company uses one normalized calendar axis for price and FINRA panels, unified hover, and an explicit included/excluded freshness caption. Official FINRA history is checked daily even after an initial backfill succeeds.

## Rollback

Reactivate `coverage-aware-renormalized-v3-live`; the v3 rows and prediction snapshots remain intact. This restores the old decision surface without deleting v4 evidence.
