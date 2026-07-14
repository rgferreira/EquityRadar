# Model registry and immutable prediction lineage

Phase 3.8 PR-003 separates legacy simulation compatibility data from registered, replayable predictions.

## Registry policy

- A model version maps to one immutable canonical configuration and SHA-256 hash.
- The current known-at model is seeded as an **active candidate**, not a champion. PR-003 makes no promotion claim.
- Model activation and champion designation are explicit database operations; version names and lexical order have no authority.
- Registering the same version with different configuration content is rejected.
- Older `backtest_runs` versions remain `legacy_unregistered`; they are not silently converted or presented as immutable predictions.

## Snapshot layers

1. `prediction_input_snapshots` stores canonical feature inputs, temporal coverage, and verified source references under a content hash.
2. `prediction_snapshots` stores the registered model/config identity and frozen score/signal outputs under a deterministic prediction ID.
3. `backtest_runs` remains a compatibility projection for existing screens. Score/input conflicts are insert-once, while later legacy outcome observations are appended separately rather than rewriting the original row.

New simulations write both the compatibility projection and the authoritative immutable prediction. Existing simulations are deliberately not backfilled into the registry because their original inputs cannot be proven from current caches.

## Offline replay

Run:

```bash
python -m scripts.replay_prediction PREDICTION_ID
```

Use `--database PATH` for a non-default SQLite file. Replay recomputes Entry/Exit scores and labels from the frozen input snapshot and returns `exact_match`, `mismatch` with field-level differences, or `not_found`. Replay is diagnostic and cannot promote a model or change live scores.

## Rollback

Application reads can return to compatibility-only paths without dropping the additive registry/snapshot tables. Immutable rows should be retained for audit even if their consumer is rolled back.

## Evaluation labels

New immutable predictions receive the separately versioned outcome contract described in [`outcome-labels.md`](outcome-labels.md). Legacy absolute returns and benchmark-relative labels are deliberately stored and named separately; they must not be mixed in an evaluation.

## Inactive shadow candidate

The first post-3.8 candidate is documented in [`shadow-model.md`](shadow-model.md). It is registered inactive and records side-by-side comparisons without changing any visible or active decision. Registration is not promotion.
