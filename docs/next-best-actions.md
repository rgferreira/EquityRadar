# Next best actions

This ordered development-phase backlog is now complete and retained as an implementation record.

1. **Purchase lots, dates, and prices — implemented** — supports multiple purchases per ticker, including trade date, shares, price, commissions, notes, editing/deletion, and migration of existing aggregate positions as legacy lots.
2. **Cost basis and real P&L — implemented** — calculates average cost, unrealized return/P&L, and FIFO realized P&L after sales; unknown legacy costs remain explicitly unavailable.
3. **Daily portfolio snapshots — implemented** — persists one updatable valuation per calendar day and charts the recorded portfolio history separately from the reconstructed current-holdings history.
4. **Currencies and base-currency conversion — implemented** — detects trading currency through yfinance, retrieves FX rates, and normalizes market value, cost, P&L, snapshots, and reconstructed history to `PORTFOLIO_BASE_CURRENCY`.
5. **Dividends and cash — implemented** — records dividends, withholding tax, fees, deposits, withdrawals, adjustments, related ticker, currency, and normalized cash balance.
6. **Benchmark comparison — implemented** — compares one-year growth of 100 against S&P 500, Nasdaq Composite, or URTH/MSCI World ETF.
7. **Allocation and concentration — implemented** — visualizes exposure by position, sector, country, and currency, with warnings above a 35% position weight.
8. **Portfolio return and risk analytics — implemented** — adds flow-adjusted TWR from recorded snapshots, reconstructed return, volatility, drawdown, Sharpe, and position risk contribution.
9. **Targets and rebalancing — implemented** — stores per-ticker target weights and calculates theoretical buy/sell values, with a warning when targets do not total 100%.
10. **Import, export, and backups — implemented** — imports purchase/sale/cash CSV rows with per-row errors and exports holdings, lots, sales, cash, journal data, templates, and SQLite backups.
11. **Investigate Revolut Exchange FIX API — completed** — assessment in [`revolut-fix-assessment.md`](revolut-fix-assessment.md). Conclusion: crypto-only, manually credentialed FIX 4.4 gateway; not suitable for the current equity/no-execution product boundary.

## Features — Phase 4 (saved for later)

1. Add purchase dates and cost basis to portfolio positions.
2. Show realized and unrealized gains, including return percentages.
3. Support portfolio transactions: buys, sells, dividends, fees, and cash.
4. Replace assumed historical holdings with transaction-aware performance history.
5. Add portfolio performance benchmarks and time-weighted returns.
6. Add sector, country, currency, and position concentration limits with alerts.
7. Add dividend tracking: yield, projected income, payment calendar, and growth.
8. Add target allocations and actionable rebalancing suggestions.
9. Add scheduled background refreshes and visible provider-health diagnostics.
10. Add automated end-to-end UI regression tests for Dashboard, Portfolio, Company, and Journal.

## UI — Phase 3

Redesign Dashboard, Portfolio, and Company without changing their page identities or underlying behavior. Introduce a cohesive premium visual system, clearer information hierarchy, compact executive summaries, consistent chart styling, and progressive disclosure for detailed research data.

## Market factoring-in — Phase 3.2 (implemented)

Use accumulated positioning history to add a small, capped, transparent adjustment to Entry and Exit-review scores. Official FINRA backfill supplied the short-interest history needed to implement the first calibrated version without waiting for new short reports.

Readiness gate:

- Add a bounded daily cohort collector so every watchlist equity accumulates snapshots without requiring manual Company-page visits.
- At least 30 valid daily positioning snapshots for most watchlist equities, with 60 preferred for calibration.
- At least two distinct short-interest reporting dates per ticker so a repeated provider value is not mistaken for a daily observation.
- Sufficient option-chain continuity to calculate changes rather than only absolute put/call readings.
- Separate data-coverage confidence from directional-signal reliability.
- Measure overlap with technical, analyst, and risk inputs before selecting weights.
- Backtest a capped initial adjustment (proposed maximum: ±5 Entry points and ±7 Exit-review points) and display the exact contribution.

The initial gate is met for short-interest history. Options history continues accumulating and affects confidence through current coverage; future calibration can add options-change signals once sufficient dated chains exist. Phase 4 remains on hold.

## Backtested Learning — Phase 3.4 backlog

1. **Automatically backfill every newly added watchlist ticker across all saved simulation cutoff dates — implemented.** Adding a ticker enqueues point-in-time reconstruction and outcome retrieval for each persisted simulation without requiring manual reruns. Work continues in the background with per-date progress and isolated errors, respects the original cutoff, and includes a recovery trigger for tickers added before this automation existed.
