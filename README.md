# Personal Equity Radar

A local Streamlit research dashboard for a personal stock watchlist. It provides market-data metrics, simple transparent scoring, and a structured investment journal. It is a decision-support tool only: it does not connect to brokers, place orders, or automate trading.

Industry coverage self-configures in the background when a ticker is added: comparable companies are discovered, ranked and persisted; peer metrics refresh daily, membership monthly, and limited cohorts retry weekly.

Company detail also includes market positioning: short interest, near-term option-chain balance, ownership, insider activity and analyst actions become transparent Long positioning, Short pressure, Squeeze potential and Confidence scores. Official FINRA history gates small, visible modifiers capped at ±5 Entry points and ±7 Exit-review points.

## Setup

```bash
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\\Scripts\\activate
pip install -r requirements.txt
cp .env.example .env
```

Optionally set `EQUITY_RADAR_DB_PATH` in `.env`; by default the SQLite database is created as `personal_equity_radar.db` in the project root.
Set `FMP_API_KEY` in `.env` to enable Financial Modeling Prep as the primary fundamentals source. Credentials are never stored in source code. When the current FMP plan returns no usable company data, the provider-neutral chain falls back to Yahoo Finance and records the provider actually used.

## Run

```bash
streamlit run app.py
```

Add tickers in **Decision dashboard**, value current holdings in **Portfolio**, then use **Company** to inspect one- or three-year charts and target-price upside/downside. Use **Journal** to record, filter, edit, delete, and export thesis entries.

## Tests

```bash
pytest
```

## Scoring

- Technical (0–100): price versus 50/100/200-day averages, positive 1/3/6/12-month returns, and proximity to the 52-week high.
- Valuation (0–100): the average of available component scores for positive trailing/forward P/E, positive price-to-sales TTM, revenue growth, and EPS growth. Invalid or negative multiples are omitted; no usable inputs yields a neutral 50.
- Risk (0–100): lower drawdown and lower annualized daily volatility produce a higher score.
- Entry score: 50% technical, 30% valuation, 20% risk. It expresses potential entry/add attractiveness, not a trading instruction.
- Exit-review score: 60% technical deterioration and 40% risk deterioration. It flags when a holding merits reassessment; it never places or recommends an order.
- Decision-aware backtested learning: historical simulations are stored per ticker and their original decision is judged against subsequent returns. A Wait followed by gains is a missed opportunity, not a generic win; a Wait followed by weakness is correct avoidance. Comparable monthly 1M/3M/6M returns are combined at 50%/30%/20%. Only mature, informative, non-duplicate observations enter learning, and at least three selected observations are required before a visible modifier capped at ±5 affects Entry (with the opposite Exit-review adjustment).
- Position-aware decision layer: unowned companies use initiation decisions, while holdings translate the same company evidence into Add/Hold/Monitor/Trim/Exit using current weight, optional target weight and concentration. This changes the action, not the underlying company research scores.

## Time Machine and point-in-time learning

The Decision dashboard can reconstruct a custom past date. Price metrics are truncated at that cutoff, timestamped fundamentals are included only when already available, and unavailable historical industry/analyst/positioning evidence is excluded rather than replaced with today's knowledge. Forward outcomes are evaluated only after the reconstructed decision and stored separately in SQLite. Each run records its inputs, coverage and model version so results remain reproducible and future scoring changes do not rewrite past evidence.

Phase 3.7 adds a learning-value gate. Each saved run shows its weighted outcome, decision conclusion, horizon coverage, learning priority, whether it was retained, and why. The engine prioritizes score/outcome disagreement and meaningful moves near decision boundaries, while immature, noisy and near-duplicate situations remain auditable but do not train current scores.

Price history remains provided by yfinance. Fundamentals use a provider-neutral interface with FMP first and a separate Yahoo Finance fallback adapter, and are cached in SQLite at most once per calendar day unless explicitly refreshed. Provider failures and missing fields are isolated per ticker and do not block prices.

Official FINRA short-interest history is backfilled automatically for newly added equities and missing-coverage watchlist members. It contributes bounded modifiers to current scores. Historical simulations use only FINRA reports available by their cutoff and are versioned/rebuilt after new history arrives; crypto and instruments without FINRA equity coverage remain neutral.

Entry scores can be calibrated by the Industry Feature after Company detail builds a daily research snapshot. The model combines business quality, direct-peer relative valuation, technical timing, non-duplicative risk resilience, and analyst sentiment. It displays the peer cohort, confidence, revisions, target dispersion inputs, provider, and freshness rather than presenting industry adjustment as an opaque score.

## Product queue

The ordered backlog for the next phase is maintained in [`docs/next-best-actions.md`](docs/next-best-actions.md).

### Implemented: Portfolio page and valuation

Portfolio is an independent page between Decision dashboard and Company. It records shares, values each position and the total using current yfinance prices, and charts transaction-aware historical value.

- A portfolio holding must also exist in the watchlist.
- Adding a ticker from Portfolio automatically adds it to the watchlist.
- Removing a ticker from the watchlist must preserve this relationship safely (the implementation should require the user to remove the portfolio holding first, or offer a clear combined removal action).

### Implemented: Initial market-data refresh

Force-refresh market data once when the Decision dashboard initially loads in a browser session.

### Implemented: Decision dashboard ordering

Switch the Decision dashboard between a selected-column sort and a persistent manual ticker order. Company inherits the currently displayed order.

### Implemented: FMP fundamentals and valuation

- FMP adapter behind a replaceable provider interface.
- Daily SQLite cache for trailing P/E, forward P/E when available or derivable, price-to-sales TTM, revenue growth, EPS growth, reporting date, provider, and fetch timestamp.
- Transparent valuation scoring and Company-page input/component breakdown.
- Safe partial-data and provider-error behavior; yfinance continues to provide market prices independently.
