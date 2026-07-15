# Phase 3.9 next step — FINRA daily short-volume driver

Status: **provider, persistence and Company-chart flow layer implemented; slope is now an inactive shadow-model component; no live-model change authorized**.

## Purpose

Increase the temporal resolution of short-pressure monitoring between the official twice-monthly short-interest
reports by ingesting FINRA's consolidated TRF/ADF Daily Short Sale Volume files, normally published after each
trade date.

## Scientific boundary

- Official consolidated short interest remains the authoritative open-position anchor.
- Daily short-sale volume is a transaction-flow proxy and must never be presented as outstanding short interest,
  net new shorts, or covering volume.
- Missing daily observations remain missing and contribute no directional evidence.
- The new driver starts as separately visible, immutable shadow evidence; it cannot alter Entry or Exit-review
  scores without a later explicit promotion decision.

## Proposed slice

1. Add a replaceable daily-short-volume provider interface and FINRA file adapter. **Implemented.**
2. Persist symbol, trade date, short volume, exempt volume, total reported volume, source, `known_at`, and
   `fetched_at` using an additive migration.
   **Implemented with immutable revision-aware observations.**
3. Build transparent features such as daily short-volume share, rolling baseline, z-score, persistence and
   coverage confidence; do not infer net short positions.
   **Daily share, 10-session mean, its 10-session slope, persistence and coverage confidence implemented.**
4. Show the daily flow layer separately from the twice-monthly FINRA position pulse in Company and Operations.
   **Implemented as a third aligned Company-chart band plus provider-health rows.**
5. Backfill a bounded history, then accumulate 60–90 genuinely prospective trading sessions.
   **Historical display backfill is complete; shadow evaluation begins only with verified point-in-time snapshots.**
6. Evaluate incremental utility against the current live model and subsequent official short-interest changes
   using the existing purged, versioned evaluator.
   **Preregistered under `technology-daily-short-flow-v3-shadow`; awaiting prospective maturity.**

## Acceptance boundary

Implementation may be considered complete when point-in-time semantics, provider isolation, freshness,
mobile/desktop rendering and mocked-provider tests pass. Scoring remains unchanged until the preregistered
shadow evaluation supplies enough independent evidence and the user explicitly approves promotion.

Official references:

- <https://www.finra.org/finra-data/browse-catalog/short-sale-volume-data/daily-short-sale-volume-files>
- <https://www.finra.org/filing-reporting/regulatory-filing-systems/short-interest>
