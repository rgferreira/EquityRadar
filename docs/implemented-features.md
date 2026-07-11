# Implemented features

## Market data

- yfinance supplies one year of daily prices and moving-average/return metrics.
- Dashboard data refreshes on initial session load and on demand.
- Dashboard price, percentage, moving-average, and score columns use consistent formatting.
- Each ticker displays the actual yfinance cache-fetch timestamp.
- Company charts can switch between one-year and three-year histories.

## Fundamentals and valuation

- Financial Modeling Prep is the primary MVP fundamentals provider behind a replaceable `FundamentalsProvider` contract; a separate Yahoo Finance adapter supplies a resilient fallback when the FMP plan returns no usable fields.
- `FMP_API_KEY` is loaded from `.env`; no credential is hardcoded.
- Normalized fundamentals are cached in SQLite once per calendar day unless the user forces refresh.
- Stored fields: trailing P/E, forward P/E, price-to-sales TTM, revenue growth, EPS growth, reporting date, provider name, and fetched-at timestamp.
- Forward P/E is derived only from a positive current price and positive next-year consensus EPS when estimates are accessible; otherwise it remains null.
- Negative/non-meaningful multiples are treated as missing. The 0–100 score averages only available components and exposes its breakdown in Company detail.
- Missing fields and provider failures do not interrupt prices or other tickers; cached rows retain the name of the provider that actually succeeded.
- The Industry Feature calibrates entry attractiveness through business quality (25%), peer-relative valuation (30%), technical timing (20%), risk resilience (15%), and confidence-aware analyst sentiment (10%).
- Curated direct-peer cohorts are persisted with daily classification, valuation, recommendation, EPS-revision, price-target, provider, confidence, and fetched-at evidence.
- Company detail exposes the peers, dimension weights, confidence, analyst coverage, target upside, and evidence used; Dashboard marks whether each score has been industry-calibrated.
- Drawdown affects technical timing but is removed from Industry Feature risk resilience to avoid double-counting the same market damage.
- Cohort and analyst snapshots now refresh automatically through bounded stale-while-revalidate jobs: Company selection gets priority, Dashboard fills at most two watchlist cohorts concurrently, stale evidence remains visible, failures cool down before automatic retry, and non-company instruments are marked not applicable.
- The Company force-refresh checkbox was removed; normal navigation is the refresh trigger.

## Portfolio, journal, and ordering

- Manual portfolio holdings linked safely to the watchlist.
- Purchase lots with trade date, shares, price, fees, notes, editing/deletion, and migration of legacy aggregate holdings.
- Structured investment journal.
- Journal entries can be filtered, edited, deleted with confirmation, and exported to CSV.
- Company detail calculates target-price upside/downside against the current market price.
- Selected-column sorting and persistent per-session manual Dashboard order.
- FIFO sales, cost basis, realized/unrealized P&L, daily snapshots, base-currency normalization, cash/dividends, benchmarks, allocation/concentration, return/risk analytics, targets/rebalancing, and CSV/database portability.
