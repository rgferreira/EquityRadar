# Coverage-aware model promotion — 2026-07-14

- New live champion: `coverage-aware-renormalized-v3-live`
- Promoted challenger: `coverage-aware-renormalized-v1`
- Rollback anchor: `backtested-learning-v4-orthogonal-known-at-v1`
- Evidence: 378 paired, matured 3M observations across 18 included tickers
- Accuracy: 43.12% former live versus 46.83% shadow
- Gates: 6/6 green
- Across-date consistency: 62% positive dates; required threshold 60%

The promoted policy preserves verified 50/30/20 technical/valuation/risk weights. When valuation evidence is unavailable, it treats valuation as missing and renormalizes the verified technical and risk inputs to 5/7 and 2/7. Industry-calibrated scores and the exit-review policy are unchanged.

Promotion is a reversible research-policy decision, not evidence of durable benchmark outperformance or an execution instruction. Legacy predictions, labels, outcomes and shadow snapshots remain immutable. New historical rows use the promoted model identity.
