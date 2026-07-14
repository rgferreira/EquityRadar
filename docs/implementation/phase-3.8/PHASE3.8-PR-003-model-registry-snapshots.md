# PHASE3.8-PR-003 — Model registry and immutable snapshots

Status: **implemented and validated on `phase/3.8-audit-hardening`**.

## Objective

Replace lexicographic model discovery and mutable backtest rows with explicit model governance and replayable predictions.

## Finding status

F-03/F-13/F-24 partially apply: version strings and `inputs_json` exist, but there is no authoritative registry, immutable prediction identity, or raw-to-feature lineage.

## Scope

- Add an explicit model registry with immutable version/config hash, creation time, status, and champion designation.
- Replace lexicographic “latest” selection with registry lookup.
- Persist append-only prediction snapshots containing prediction ID, model version/config hash, cutoff, verified input references, score components, and output.
- Provide an offline replay command/report that compares recomputation to the frozen snapshot.
- Treat legacy rows as legacy/unverified, never silently as registered predictions.

## Non-goals

- No model-weight optimization, new label, promotion decision, or cloud tracking service.
- No destructive conversion of `backtest_runs`.

## Probable files

`src/data/database.py`, `src/backtesting.py`, new registry/replay module and CLI script, migration and replay tests, documentation.

## Data and migration

Add registry, prediction, and immutable input-reference tables with foreign keys and uniqueness on prediction identity. Seed the current legacy model as non-promoted/legacy unless its configuration can be deterministically hashed. Existing `backtest_runs` remain read-only compatibility data.

## Tests

- Numeric-looking or arbitrary model names cannot change champion selection.
- Snapshot inserts are append-only/idempotent by prediction identity.
- Replay reports exact match or an explicit structured mismatch.
- Migration is idempotent and legacy rows remain unchanged.

## Acceptance criteria

- No operational code selects a model by string ordering.
- Every new prediction links to a registered immutable configuration and verified inputs.
- A frozen prediction can be replayed offline with an auditable result.

## Risks and rollback

Risk: compatibility paths can accidentally mix legacy and registered rows. Use explicit types/queries and dual-read only where documented. Roll back reads to legacy paths; retain additive tables for inspection.
