# Data source registry

Current implementation registry as of 2026-08-24. This is the central map of data entering PersonalEquityRadar: what is collected, where it is stored, when the application can prove it knew the value, and whether it can affect a decision score.

This document describes the current code, not a provider's full catalogue and not evidence that a signal is predictive. The temporal rules in [`temporal-data-contract.md`](temporal-data-contract.md) remain authoritative.

## Source inventory

| Domain | Current provider and access | Data acquired | Refresh / available history | Persistence and lineage | Application use | Principal limitation |
|---|---|---|---|---|---|---|
| Daily price history | Yahoo Finance through `yfinance` `Ticker.history`; no project API key | Auto-adjusted daily OHLCV; close drives returns, moving averages, drawdown and volatility | Per process cache; requested as 1 year, 3 years or maximum history | Not persisted as a raw provider table; fetch time is held in process | Dashboard prices, Company chart, technical and risk evidence, return calculations | Operational, unofficial adapter; historical bars do not carry a provider publication timestamp |
| Quote currency and FX | Yahoo Finance through `fast_info.currency` and `{FROM}{TO}=X` daily history | Trading currency and latest FX close | Per process cache | Not persisted independently | Portfolio base-currency conversion and allocation values | Latest daily FX close, not an executable conversion quote |
| Asset profile | Yahoo Finance `Ticker.info` | Sector and country | Per process cache | Not persisted independently | Portfolio allocation summaries and industry context | Coverage varies by instrument |
| Fundamentals and valuation | Financial Modeling Prep (FMP) `ratios-ttm`, `income-statement-growth`, optional `analyst-estimates`; Yahoo `Ticker.info` fallback | Trailing/forward P/E, price/sales, revenue growth, EPS growth and reference period | Daily application cache; current snapshot rather than a reconstructed filing history | `fundamentals_cache`, with provider, period end, `known_at`, status and fetch time | Absolute valuation and coverage-aware Entry evidence | FMP availability depends on plan; Yahoo is fallback. No value is backdated to its fiscal period without verified publication time |
| Industry, peers and analysts | Yahoo `Ticker.info`, `Industry.top_companies`, recommendations, EPS revisions and analyst price targets; FMP `stock-peers` where available; curated peer lists for selected symbols | Company profile, comparable-company candidates, relative valuation/quality fields, analyst recommendations, revisions and targets | Daily snapshot; peer membership normally rediscovered monthly, or weekly when coverage is limited | `industry_research_cache`, including normalized payload, provider and observed-at metadata | Industry-calibrated Entry components and Company research | Snapshot combines fields with different economic dates; it becomes historically usable only when observed by the app |
| Current positioning snapshot | Yahoo `Ticker.info`, first three option expiries, insider transactions and upgrades/downgrades; FMP `shares-float` validation | Short float/shares/days-to-cover, options volume/OI/IV, ownership, insider row counts and 90-day analyst actions | Daily snapshot | `positioning_cache` plus captured `positioning_history` | Reliability-gated positioning scores and bounded Entry/Exit modifier | Options are not intrinsically directional; ownership and short-interest fields lag; Yahoo is unofficial |
| Official short interest | FINRA Consolidated Short Interest API | Settlement-dated shares short, previous position, percentage change, average volume, days to cover and revision flag | Bounded historical backfill, up to provider result limit; periodic underlying reports | `positioning_history`, component explicitly tagged `historical_short_interest` | Company pressure pulse and reliability-gated positioning evidence | Settlement date is not public-availability time; historical backfill is recorded as first observed, never presumed known on settlement date; not applicable to BTC |
| Daily short-sale flow | FINRA Consolidated NMS Daily Short Sale Volume files | Daily short, short-exempt and total FINRA-reported volume by symbol | Daily; bounded rolling backfill and small revision window | Immutable `finra_daily_short_volume_observations` plus dated fetch ledger and payload hash | Company daily-flow chart and a zero-weight shadow diagnostic | Flow is not outstanding short interest and is not the whole consolidated market volume |
| BTC perpetual positioning and flow | Public Binance USD-M Futures endpoints plus the official Binance Public Data archive for BTCUSDT; no API key | Daily taker buy/sell BTC volume, percentage of accounts net long/short, and open-interest value in USDT | One-year bootstrap from five-minute archived positioning snapshots and daily contract klines; live refresh at most once per UTC day. The immutable local series then grows prospectively | `bitcoin_derivatives_daily_observations`, with venue, instrument, endpoint set, raw daily inputs, payload hash, observed-at `known_at` and fetch time | Company BTC chart: taker-sell flow, 10-day average, daily short-account delta and open interest; display-only with live-model weight 0.0 | One venue and one perpetual contract, not the whole crypto market. Account count is not short notional. Open interest contains both long and short sides. Archive gaps remain missing rather than interpolated |
| Congressional trading / WhaleSeeker | FMP `house-latest` and `senate-latest`, authenticated by project API key | Politician, chamber, asset/ticker, transaction class, amount range, trade date, filing/publication evidence and source document link when provided | Latest pages plus cursor-controlled historical backfill, 25 rows per request | Immutable raw batches in `whale_raw_payloads`; revision-aware normalized records in `whale_disclosure_observations`; cursor and health state persisted separately | Dashboard and WhaleSeeker exploration; pilot/display layer, not a direct trading instruction | Statutory disclosures may arrive well after the trade; ticker and asset descriptions require normalization; provider access/rate limits depend on plan. Quiver is not a current ingestion dependency |
| Extended-hours / 24-hour awareness | Yahoo Finance 5-minute history with pre/post-market data | Pre-market, regular and after-hours price context; latest 24/7 price for crypto pairs | Five-minute cache TTL | `extended_hours_cache` with provider, quote date and fetch time | Advisory price overlay and Company session context | Advisory only and excluded from scores; availability depends on Yahoo intraday coverage |
| User-owned research data | Manual entries in the local Streamlit application | Watchlist, portfolio lots/sales, targets, cash events, journal, simulations and acknowledgements | On user action | Local SQLite tables; no external synchronization | Personal portfolio context and research workflow | Private local data; must never be printed, committed or sent to providers |

## BTC metric definitions

The BTC panels intentionally mirror the *questions* asked by the equity panels, not their source-specific definitions:

- **Daily flow** = `taker sell volume / (taker buy volume + taker sell volume) × 100` for the Binance BTCUSDT perpetual. This measures aggressive executed flow at that venue.
- **10D flow average** = rolling mean of the daily taker-sell percentage, with at least three observed periods.
- **Short Δ** = day-over-day change in the percentage of Binance global accounts reported net short, expressed in percentage points.
- **Open interest** = Binance `sumOpenInterestValue`, displayed in billions of USDT on the secondary axis. It is market participation, not a bearish quantity by itself.

For the latest month, Binance labels taker-volume timestamps at the start of each UTC daily period, while the account-ratio and open-interest series label the end boundary. The adapter subtracts one millisecond from the latter two before joining. For the older bootstrap, it uses the final archived five-minute positioning observation of each UTC day and exact taker/total volume from the matching daily contract kline. Missing archive dates remain visible as gaps and are never interpolated.

## Temporal and scientific policy

- Economic dates (`trade_date`, `settlementDate`, fiscal `date`, `period_date`) never substitute for public availability.
- When a source supplies no independently verified publication timestamp, `known_at` is the first time the application observed the response and the status is `verified_observed` (or the WhaleSeeker equivalent `observed_by_app`).
- Immutable/revision-aware tables retain provider corrections rather than overwriting prior observations.
- Missing or malformed evidence remains unavailable; it does not become neutral, bullish or bearish evidence.
- A chart or pilot layer does not automatically become a model input. BTC derivatives and WhaleSeeker remain outside the live Entry/Exit policy unless a separately approved evaluation and promotion changes that policy.

## BTC alternatives evaluated, not automatically mixed

| Source | Useful public data | Why it is not automatically merged into the current series |
|---|---|---|
| Bybit V5 | Daily historical open interest and long/short account ratio | A second venue would introduce a series break unless normalized and displayed separately; no automatic fallback may silently change the metric's venue |
| Deribit public API | BTC perpetual funding-rate history | Funding is a different measure from taker flow, short-account share and open interest; it is a candidate future panel, not a substitute |
| CFTC Commitments of Traders / CME Bitcoin futures | Regulated weekly positions and open interest by trader category | High-quality but weekly and delayed; best treated as a distinct macro positioning layer rather than interpolated into a daily exchange series |
| OKX public market data | Derivatives market snapshots and histories | Not selected until a stable daily field contract and retention window are verified and tested |

Fallback policy is **preserve cached Binance observations and disclose unavailability**. The application does not silently splice another venue into the same line.

## Provider governance and security

- Credentials are read from local configuration and are never stored in source lineage, logs or documentation.
- Public downloads use HTTPS, bounded timeouts and, for the newer ingestion paths, bounded response sizes and sanitized error messages.
- `provider_health_state` and `provider_health_transitions` track attempts and recovery without persisting credentials.
- Cached successful data is preserved when a provider fails; retries are bounded by cooldowns.
- Provider payloads used by WhaleSeeker and BTC derivatives retain hashes and raw lineage so normalized fields can be audited.

## Authoritative links

- [FINRA Consolidated Short Interest API](https://developer.finra.org/docs#getting-started)
- [FINRA Daily Short Sale Volume](https://www.finra.org/finra-data/browse-catalog/short-sale-volume-data/daily-short-sale-volume-files)
- [Binance USD-M Futures long/short ratio, taker volume and open-interest endpoints](https://developers.binance.com/en/docs/derivatives/usds-margined-futures/market-data/rest-api)
- [Binance Public Data archive and integrity guidance](https://github.com/binance/binance-public-data)
- [FMP API documentation](https://site.financialmodelingprep.com/developer/docs)
- [yfinance documentation](https://ranaroussi.github.io/yfinance/)
- [Bybit historical open interest](https://bybit-exchange.github.io/docs/v5/market/open-interest)
- [Bybit long/short ratio](https://bybit-exchange.github.io/docs/api-explorer/v5/market/long-short-ratio)
- [Deribit funding-rate history](https://docs.deribit.com/api-reference/market-data/public-get_funding_rate_history)
- [CFTC Commitments of Traders](https://www.cftc.gov/MarketReports/CommitmentsofTraders/index.htm)

## Related project documents

- [`temporal-data-contract.md`](temporal-data-contract.md): point-in-time field definitions and conservative availability policy.
- [`market-positioning-source-audit.md`](market-positioning-source-audit.md): deeper reliability analysis for equity positioning inputs.
- [`implemented-features.md`](implemented-features.md): user-visible behavior and implementation history.
- [`audit/2026-07-13/FORENSIC_REVIEW_ES.md`](audit/2026-07-13/FORENSIC_REVIEW_ES.md): authoritative scientific and engineering risk register.
