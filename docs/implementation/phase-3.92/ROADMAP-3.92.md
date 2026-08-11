# Phase 3.92 — WhaleSeeker & Pilot Decisions

Phase 3.92 releases research value without presenting immature evidence as a champion-model
promotion. It has two isolated tracks:

1. expose the existing `technology-daily-short-flow-v3-shadow` through an explicit, reversible
   Pilot Decisions surface; and
2. build WhaleSeeker as a point-in-time congressional-disclosure research and discovery module.

The current live champion remains `coverage-aware-renormalized-v4-finra-freshness-live`. Phase
3.91 remains reserved for the queued Credit Stress Feature and is not part of this release.

## Ordered delivery

1. **PR-001 — Pilot deployment contract — implemented.** Persist an opt-in exposure state outside the model
   registry, render live-versus-pilot decisions, add a runtime kill switch and prove that the
   existing shadow experiment remains unchanged.
2. **PR-002 — Congressional data foundation — implemented.** Add a replaceable provider contract,
   FMP as the initial adapter, append-only raw payloads, normalized observations, amendments,
   source hashes, provider health and conservative `known_at` semantics.
3. **PR-003 — Historical bootstrap — implemented.** Import the maximum licensed history
   incrementally, retain publication-date uncertainty and keep retrospective and prospective
   cohorts separate. Next-session copyable outcomes remain scoped to PR-005.
4. **PR-004 — WhaleSeeker surfaces — implemented.** Insert discovery between Portfolio actions and Watchlist
   opportunities, add the dedicated WhaleSeeker page and deep-link ticker/politician evidence.
5. **PR-005 — Copyability research.** Add sample-aware politician profiles, private-versus-copyable
   return views, shrinkage-aware leaderboards and a non-executing Copyability Lab.
6. **PR-006 — Acceptance.** Run full automated and responsive acceptance, provider-failure drills,
   rollback verification, privacy review and documentation reconciliation.

## Non-negotiable isolation

- Pilot exposure does not change `CURRENT_MODEL_VERSION`, model registration, weights, thresholds,
  shadow configuration, snapshots, outcomes or promotion gates.
- Whale evidence has zero applied Entry/Exit impact in Phase 3.92.
- `trade_date` and provider `ReportDate` never substitute silently for `known_at`.
- Historical provider rows are not relabelled as prospectively observed evidence.
- Neither track performs or submits securities orders.

## Rollback

- `PILOT_DECISIONS_ENABLED=false` disables pilot exposure while retaining immutable evidence.
- `WHALESEEKER_ENABLED=false` disables ingestion and product surfaces while retaining raw lineage.
- All schema changes are additive. Existing predictions, outcomes and research records remain
  untouched.
