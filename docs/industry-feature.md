# The Industry Feature

## Automatic cohort completion

Adding a watchlist ticker immediately starts peer discovery in the bounded background worker. FMP peer results are used when available on the configured plan; Yahoo industry constituents are the operational fallback. Candidates are ranked by industry, sector, market-cap proximity, revenue growth, and operating margin. The selected peers and their selection evidence are persisted.

The UI progresses through `Discovering peers`, `Ready`, or `Limited coverage`. Peer metrics refresh daily, while valid membership remains stable for 30 days. Limited cohorts retry after seven days; legacy limited records receive one immediate attempt. Page loads are recovery triggers only when work is due, so no manual refresh button is needed.

The Industry Feature replaces a universal valuation/timing interpretation with a transparent, confidence-aware entry score:

- 25% business quality
- 30% direct-peer relative valuation
- 20% technical timing
- 15% risk resilience
- 10% analyst sentiment

Business quality uses revenue growth, operating margin, free-cash-flow margin, and gross margin when available. Relative valuation compares forward P/E and price/sales with a curated direct-peer median. Analyst sentiment combines recommendation breadth, recent EPS revisions, median price-target upside, dispersion, coverage, and confidence. Missing evidence moves a dimension toward 50 rather than appearing negative.

Drawdown remains a technical-timing input and is removed from the Industry Feature risk-resilience contribution to prevent double-counting. The legacy exit-review score is unchanged.

Research snapshots are cached in SQLite once per calendar day and use stale-while-revalidate behavior. Company selection renders cached evidence immediately and automatically schedules missing or stale research. Dashboard completes the watchlist progressively with at most two concurrent cohort jobs, prioritizing portfolio holdings. Live fragments surface `Ready`, `Updating`, `Pending`, `Stale`, `Not applicable`, or `Provider unavailable` states and refresh the score after completion. Failed requests preserve the last successful snapshot and retry automatically after a 15-minute cooldown. ETFs and other non-company instruments are marked not applicable instead of remaining permanently pending.

Routine force-refresh controls are intentionally absent from Company detail. Provider refresh is an implementation concern, not a normal research workflow.

The pre-feature rollback archive is [`before-industry-feature.tar.gz`](../../some/backups/before-industry-feature.tar.gz), SHA-256 `372876b500b6ef8f96dfa14a120fb3e12096fef9e8646f67677094fa1d5fb518`.
