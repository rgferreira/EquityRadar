# Phase 3.9 operational acceptance — 2026-07-14

> Historical acceptance snapshot. The live model and acceptance suite have evolved since this record; see the [2026-07-20 engineering closure](CLOSURE-2026-07-20.md) for the current release boundary. This file is preserved rather than rewritten.

Phase 3.9 remains anchored at `coverage-aware-renormalized-v3-live`. None of the operational work in
this acceptance slice changes model weights, thresholds, diagnostics or the exit policy.

## Delivered controls

- Prospective post-promotion monitoring excludes history materialized during promotion and compares
  future matured evidence with the frozen 378-observation promotion baseline.
- Synthetic Streamlit AppTest coverage exercises every page and empty state without personal fixtures;
  explicit-confirmation simulation behavior is interaction-tested.
- `scripts/run_ui_acceptance.py` renders all eight routes with headless Chromium at desktop and phone
  dimensions; the release run passed 16/16 route/viewport checks.
- A server-lifetime scheduler refreshes due market, fundamentals, industry, positioning, extended-hours,
  outcome and cutoff-suggestion evidence without requiring a browser session.
- Operations exposes cached freshness plus per-provider/ticker in-flight state, cooldown, isolated error and
  recovery status for prices, fundamentals, industry, positioning, FINRA and extended hours.
- Research alerts persist diagnostic changes, score-boundary crossings, material FINRA reversals, provider
  recoveries and matured lessons; ordinary price noise is excluded.
- Options-history continuity is monitored but remains excluded from live scores.
- The Scenario lab computes reversible allocation counterfactuals and cannot persist or execute trades.
- Archived backtested-learning diagnostics explicitly report a live contribution of zero on every ticker.

## Scientific boundary

The next hypothesis, `options-positioning-v1`, is preregistered for coverage accumulation only. Coverage
readiness does not create a shadow model. A separate purged evaluation and prospective shadow period are
required before any score-policy proposal.

## Recovery boundary

Backups use SQLite's online backup API, `PRAGMA integrity_check`, and a SHA-256 schema/row-count manifest.
The restore drill copies a backup into an isolated temporary database, verifies integrity, schema and row
counts, then removes the temporary copy; it never touches the live database. The release drill passed.
Rollback remains commit-based and the former model is still registered as the model-policy rollback anchor.

## Final acceptance evidence

- 178 Python tests passed.
- Python compilation passed for application, pages, source and scripts.
- 22/22 Company ticker pages rendered without exceptions; all archived-learning cards show zero live contribution.
- 16/16 real Chromium route/viewport checks passed across desktop and phone sizes.
- Fresh backup integrity, isolated restore, schema equality and row-count equality passed.
- Active/champion model, 6/6 promotion record, rollback anchor and diagnostic-only learning policy were verified.
- Streamlit restart health returned `ok` on port 8501.
