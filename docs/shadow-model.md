# Coverage-aware shadow promotion archive

`coverage-aware-renormalized-v1` began as an inactive candidate and accumulated immutable comparisons. On 2026-07-14 all six readiness gates cleared and the policy was explicitly promoted as `coverage-aware-renormalized-v3-live`. The former `backtested-learning-v4-orthogonal-known-at-v1` model remains the rollback anchor.

## Shadow contract

- When meaningful valuation evidence is available, the candidate preserves the existing 50/30/20 technical/valuation/risk composite.
- When valuation is missing or unverified, the candidate removes its placeholder weight and renormalizes technical/risk to 5/7 and 2/7.
- Frozen positioning adjustments and existing 55/70 labels are preserved.
- Industry-calibrated live decisions are observation-only in this first slice; the candidate records no invented change where its research contract does not apply.
- Exit scores remain unchanged.
- Shadow failures are isolated and cannot block dashboard rows or historical simulations.

`shadow_decision_snapshots` stores immutable input, former-live output, promoted-policy output, hashes, delta, label-change flag, surface, and both registered model identities. These rows are now a frozen promotion archive; no new comparison is generated for this already-promoted hypothesis.

Historical promotion materialization created additive prediction, run and label rows under the new live identity without refetching or rewriting the source evidence.

## Promotion and rollback

The model became active only through an explicit user decision after a 6/6 gate record. Rollback reactivates the registered former version and restores its code policy; append-only predictions, labels, runs and shadow snapshots remain preserved. A future shadow requires a distinct, preregistered hypothesis—it is not created automatically by this promotion.
