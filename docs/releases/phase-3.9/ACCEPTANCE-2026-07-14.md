# Phase 3.9 operational acceptance — 2026-07-14

Phase 3.9 remains anchored at `coverage-aware-renormalized-v3-live`. None of the operational work in
this acceptance slice changes model weights, thresholds, diagnostics or the exit policy.

## Delivered controls

- Prospective post-promotion monitoring excludes history materialized during promotion and compares
  future matured evidence with the frozen 378-observation promotion baseline.
- Synthetic Streamlit AppTest coverage exercises every page and empty state without personal fixtures.
- A server-lifetime scheduler refreshes due market, fundamentals, industry, positioning, extended-hours,
  outcome and cutoff-suggestion evidence without requiring a browser session.
- Operations exposes provider freshness, scheduler status, daily verified SQLite backups and manifests.
- Research alerts persist only material diagnostic changes and matured lessons; ordinary price noise is excluded.
- Options-history continuity is monitored but remains excluded from live scores.
- The Scenario lab computes reversible allocation counterfactuals and cannot persist or execute trades.
- Archived backtested-learning diagnostics explicitly report a live contribution of zero on every ticker.

## Scientific boundary

The next hypothesis, `options-positioning-v1`, is preregistered for coverage accumulation only. Coverage
readiness does not create a shadow model. A separate purged evaluation and prospective shadow period are
required before any score-policy proposal.

## Recovery boundary

Backups use SQLite's online backup API, `PRAGMA integrity_check`, and a SHA-256 manifest. The UI verifies
backups but never restores over the live database. Rollback remains commit-based and the former model is
still registered as the model-policy rollback anchor.
