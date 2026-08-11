# Phase 3.92 PR-002 — WhaleSeeker data foundation

**Implementation status:** complete; automated verification passed on 2026-08-11.

## Audit finding status

The temporal-integrity finding still applies. A congressional `transactionDate` describes when a
trade occurred and `disclosureDate` describes the filing date; neither proves the exact instant at
which PersonalEquityRadar could have observed the disclosure. Historical imports therefore use the
application's first observation timestamp as conservative `known_at` and remain distinguishable
from future prospectively observed records.

## Scope

- Add a provider-neutral congressional-trading contract.
- Implement FMP House and Senate adapters with conservative page-size limits.
- Store content-addressed raw payloads before normalized observations.
- Normalize politicians, chambers, assets, transaction type, amount range and source document.
- Preserve amendments as append-only revisions linked to the prior observation.
- Record provider health without storing credentials or exposing raw payloads in logs.
- Keep WhaleSeeker evidence at zero decision weight.

## Provider decision

FMP is the initial provider because the configured account already exposes the House and Senate
endpoints. Quiver remains a replaceable challenger. Its API may later be tested for one paid month,
but Phase 3.92 does not depend on it and does not scrape the Quiver website.

## Planned files

- `src/data/database.py`: additive raw-payload and normalized-observation tables and repositories.
- `src/data/congress_trading.py`: provider protocol, FMP adapter, normalization and ingestion.
- `tests/test_congress_trading.py`: synthetic normalization, lineage, revision and failure tests.

## Temporal contract

- `trade_date`: provider-reported transaction date; never availability.
- `filed_date`: provider-reported disclosure date; date-only metadata, never silently `known_at`.
- `published_at`: only populated when a source provides a verified publication timestamp.
- `known_at`: first timestamp at which this application actually observed the record.
- `known_at_status`: `observed_by_app` unless a future source proves an earlier exact timestamp.
- `fetched_at`: retrieval timestamp for the raw payload and normalized revision.

## Acceptance criteria

1. Synthetic House and Senate responses normalize deterministically without network access.
2. Raw payload is stored before and linked from every normalized observation.
3. Reingesting identical content is idempotent for observations.
4. Changed content creates an append-only revision and never rewrites the prior row.
5. `known_at` is not copied from `trade_date` or date-only `filed_date`.
6. Provider failure records health and persists no partial batch.
7. Model registry, shadow snapshots and official decisions remain unchanged.

## Rollback

Set `WHALESEEKER_ENABLED=false` in the future scheduler/UI integration. The additive tables and raw
lineage may remain; no existing research record or model state needs to be rewritten.
