# PHASE3.8-PR-002 — Known-at semantics

Status: **implemented and validated on `phase/3.8-audit-hardening`**.

## Objective

Create an auditable temporal contract so historical reconstruction uses only evidence verified to be publicly knowable by the cutoff.

## Finding status

F-01 and F-02 still apply: `reporting_date`, FINRA settlement dates, and `fetched_at` can currently pass `evidence_available` as if they were public-availability timestamps.

## Scope

- Define typed temporal fields: `period_end`, `published_at`, `known_at`, `fetched_at`, and a verification/status field.
- Implement source-specific availability rules for fundamentals, FINRA, analyst/cohort data, and prices.
- Make unverified legacy rows unavailable to point-in-time reconstruction rather than guessing a date.
- Preserve current/live display behavior where appropriate, clearly separating it from historical validity.
- Add additive schema migration and temporal provenance.

## Non-goals

- No mass timestamp inference, destructive rewrite, score recalibration, or external provider expansion.
- No immutable prediction registry or new outcome label yet.

## Probable files

`src/backtesting.py`, `src/data/database.py`, provider adapters under `src/data/`, migration tests, provider/backtesting tests, documentation.

## Data and migration

Add nullable temporal/provenance columns or append-only observation tables through the existing migration mechanism. Legacy values remain intact and are marked unverified until a deterministic source rule can establish `known_at`.

## Tests

- Period end, settlement date, and fetch time alone never establish historical availability.
- Boundary tests immediately before/at/after verified `known_at`.
- Legacy unverified rows are excluded without crashing other data refreshes.
- Migration is idempotent and preserves existing rows.

## Acceptance criteria

- `evidence_available` requires verified `known_at` for historical decisions.
- Every supported source documents how `known_at` is derived.
- No legacy timestamp is silently promoted or overwritten.

## Risks and rollback

Risk: historical coverage will fall because uncertainty is no longer treated as evidence; that is the intended conservative behavior. Roll back application reads and leave additive columns/tables in place.
