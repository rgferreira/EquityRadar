# Coverage-aware shadow candidate

Phase 3.9 begins with `coverage-aware-renormalized-v1` registered as an **inactive candidate**. The current `backtested-learning-v4-orthogonal-known-at-v1` model remains the only active model and continues to power every visible score, diagnostic, and portfolio action.

## Shadow contract

- When meaningful valuation evidence is available, the candidate preserves the existing 50/30/20 technical/valuation/risk composite.
- When valuation is missing or unverified, the candidate removes its placeholder weight and renormalizes technical/risk to 5/7 and 2/7.
- Frozen positioning adjustments and existing 55/70 labels are preserved.
- Industry-calibrated live decisions are observation-only in this first slice; the candidate records no invented change where its research contract does not apply.
- Exit scores remain unchanged.
- Shadow failures are isolated and cannot block dashboard rows or historical simulations.

`shadow_decision_snapshots` stores immutable input, current output, candidate output, hashes, delta, label-change flag, surface, and both registered model identities. Dashboard refreshes and new historical simulations write comparisons, but no shadow value is rendered or consumed by live decision code.

Existing immutable predictions can be compared without refetching or rewriting them:

```bash
python -m scripts.backfill_shadow_history
```

The operation is idempotent and writes only additive shadow rows.

## Activation gate and rollback

The candidate cannot become active by accumulation, filename, version ordering, or evaluator output. Activation requires an explicit model-registry operation and user approval after evidence review. Rollback removes shadow producers/consumers while preserving append-only snapshots; the Phase 3.8 tag and private SQLite backup remain the full code/data restoration point.
