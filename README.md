# Personal Equity Radar

A local Streamlit research dashboard for a personal stock watchlist. It provides market-data metrics, simple transparent scoring, and a structured investment journal. It is a decision-support tool only: it does not connect to brokers, place orders, or automate trading.

Industry coverage self-configures in the background when a ticker is added: comparable companies are discovered, ranked and persisted; peer metrics refresh daily, membership monthly, and limited cohorts retry weekly.

Company detail also includes market positioning: short interest, near-term option-chain balance, ownership, insider activity and analyst actions become transparent Long positioning, Short pressure, Squeeze potential and Confidence scores. Official FINRA history gates small, visible modifiers capped at ±5 Entry points and ±7 Exit-review points. Short-interest freshness is measured from the official report date—not the download time—and reports older than 28 days are visibly excluded from scoring.

Backtested-learning results are retained as transparent diagnostic research, but Phase 3.8 quarantines them from live Entry/Exit scores by default pending point-in-time and out-of-sample scientific validation.

Phase 3.8 also provides immutable prediction snapshots, versioned benchmark-relative outcome labels, and an offline purged rolling-origin evaluator. These are research-governance tools, not proof of predictive skill or automated model-promotion machinery.

Historical simulations now require verified point-in-time `known_at` metadata for fundamentals, analyst/cohort and positioning evidence. Period ends, settlement dates and legacy fetch timestamps are never silently treated as publication dates; see `docs/temporal-data-contract.md`.

New simulations also create immutable, content-hashed input and prediction snapshots under an explicit model registry. The coverage-aware policy is the explicitly promoted live champion; the former live model remains registered as its rollback anchor and legacy runs remain immutable; see `docs/model-governance.md`.

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

Add tickers in **Watchlist**, value holdings in **Portfolio**, then use **Company** for single-name research. **Model tuning** monitors prospective model evidence, **Operations** exposes provider/recovery health, and **Scenario lab** evaluates hypothetical allocation changes without execution or persistence.

## Tests

```bash
pytest
```

With the local server running, render every route at desktop and phone dimensions:

```bash
python -m scripts.run_ui_acceptance
```

## Scoring

- Technical timing (0–100): 20 points for price above each 50/100/200-day moving average and 10 points for each positive 1/3/6/12-month return, capped at 100. The 52-week high/low and drawdown remain visible market context but do not add Technical points.
- Absolute valuation diagnostic (0–100): the average of available component scores for positive trailing/forward P/E, positive price-to-sales TTM, revenue growth, and EPS growth. Invalid or negative multiples are omitted. No usable inputs displays a neutral 50 diagnostically, but the promoted coverage-aware Entry fallback treats valuation as unavailable, gives it 0% weight, and renormalizes only the verified Technical/Risk evidence.
- Risk (0–100): the base market-risk score starts at 100 and subtracts up to 40 points for drawdown from the 52-week high plus a transparent annualized-volatility penalty. The fallback Entry score and Exit-review score use this full measure; industry-calibrated Entry uses volatility-only Risk resilience so the price-trend block is not counted twice.
- Entry score: when industry research is available, the transparent criteria are:

  | Criterion | Weight in Entry Score |
  |---|---:|
  | Business quality | 25% |
  | Peer-relative valuation | 30% |
  | Technical timing | 20% |
  | Risk resilience | 15% |
  | Analyst sentiment | 10% |
  | Market positioning | Modifier: up to +/-5 points |
  | Technology Potential | Shadow modifier: up to +/-5 points; 0 live contribution |
  | Backtested learning | Diagnostic evidence only; not applied to the live score |

  If industry research is unavailable, the promoted coverage-aware fallback uses 50% technical, 30% absolute valuation, and 20% risk; when meaningful valuation is also unavailable, its weight is omitted and the verified technical/risk weights are renormalized. The entry diagnostic is assigned from the resulting 0-100 score using predefined thresholds; it has no separate weighting formula. Entry scores express potential entry/add attractiveness, not a trading instruction.
- Technology Potential is preregistered as the next inactive shadow challenger. It compares R&D intensity, revenue growth, gross margin, free-cash-flow margin and balance-sheet funding capacity with direct peers. Its confidence-gated Entry modifier is `(score - 50) / 10 × confidence`, capped at +/-5; missing evidence contributes zero. It does not alter live Entry/Exit scores, and only prospective point-in-time observations may contribute to its promotion gates.
- Exit-review score: 60% technical deterioration and 40% risk deterioration. It flags when a holding merits reassessment; it never places or recommends an order.
- Archived decision-aware learning: historical simulations are stored per ticker and their original decision is judged against subsequent returns. Buy, Watch and Wait have distinct research utility, but the legacy learning modifier is scientifically quarantined and contributes exactly zero to current Entry/Exit scores.
- Position-aware decision layer: unowned companies use initiation decisions, while holdings translate the same company evidence into Add/Hold/Monitor/Trim/Exit using current weight, optional target weight and concentration. This changes the action, not the underlying company research scores.

## Time Machine and point-in-time learning

The Decision dashboard can reconstruct a custom past date. Price metrics are truncated at that cutoff, timestamped fundamentals are included only when already available, and unavailable historical industry/analyst/positioning evidence is excluded rather than replaced with today's knowledge. Forward outcomes are evaluated only after the reconstructed decision and stored separately in SQLite. Each run records its inputs, coverage and model version so results remain reproducible and future scoring changes do not rewrite past evidence.

Phase 3.7 adds a learning-value gate. Each saved run shows its weighted outcome, decision conclusion, horizon coverage, maturity, learning priority, whether it was retained, and why. The engine prioritizes score/outcome disagreement and meaningful moves near decision boundaries, while provisional, noisy, near-duplicate and same-episode situations remain auditable but do not train current scores.

Time Machine can use either a custom cutoff or an automatically ranked interesting date. Suggestions are persisted and refreshed in the background each day or when watchlist membership changes. Every recommendation identifies its market-regime, watchlist-price, moving-average or FINRA positioning trigger, exposes a learning-value rank, and shows whether it is not run, running or completed. Selecting any date only stages it; simulation always requires explicit confirmation.

The saved-simulation panel includes a score-overlap audit. It maps known shared raw inputs, measures pairwise rank correlation across distinct point-in-time simulations, and estimates each component's incremental outcome information relative to the other available components. Model v4 removed drawdown from industry-calibrated Entry Risk resilience while retaining it in the separate Exit-review market-risk calculation; analyst actions belong only to Industry & analysts. Technical trend weights were rescaled to preserve its 0–100 range, and positioning continues to use ownership, options and short-interest evidence. Evidence-policy version `coverage-aware-renormalized-v4-finra-freshness-live` additionally rejects stale FINRA reports. Saved ticker/cutoff simulations are rebuilt append-only under the active version; older runs remain stored for rollback but are suppressed from normal views.

Company score headers add sample-aware context: the exact current Entry and Exit-review diagnostic reports its historical success only after three comparable informative simulations, always with the success fraction, while Entry also shows the ticker's aggregate decision accuracy. Company charts mark simulation cutoffs with fine dotted lines: blue for manual runs, purple for completed system suggestions, and gold for current suggested dates still pending. Simulation provenance and the original suggestion rationale are persisted with each run.

The bottom of Company detail charts cumulative confirmed decision accuracy through time. Each point is one independent matured episode, colored by whether its original decision proved successful; hover details expose the original signal, verdict, weighted outcome, utility and cumulative record. Provisional and same-episode simulations are excluded by the canonical learning evaluator.

Extended-hours awareness uses a separate yfinance intraday adapter and five-minute SQLite cache. Dashboard Price automatically switches to a timestamped `PRE` or `POST` quote when that exchange session is active; Company detail shows regular close, pre-market and after-hours snapshots separately. Provider trading periods determine session boundaries, including early closes. Extended quotes are advisory and never replace official closes in technical, Entry, Exit-review or backtested-learning calculations; 24/7 assets are labelled separately.

Price history remains provided by yfinance. Fundamentals use a provider-neutral interface with FMP first and a separate Yahoo Finance fallback adapter, and are cached in SQLite at most once per calendar day unless explicitly refreshed. Provider failures and missing fields are isolated per ticker and do not block prices.

Official FINRA short-interest history is refreshed daily and backfilled automatically for equities. It contributes bounded modifiers only when the report date remains inside the 28-day freshness gate. Historical simulations require both verified point-in-time availability and report-date freshness; crypto, stale reports and instruments without FINRA equity coverage remain non-directional. Operations shows report date/age separately from fetch time, while Company charts normalize price and FINRA observations onto one exact calendar axis with unified hover.

Entry scores can be calibrated by the Industry Feature after Company detail builds a daily research snapshot. The model combines business quality, direct-peer relative valuation, technical timing, non-duplicative risk resilience, and analyst sentiment. It displays the peer cohort, confidence, revisions, target dispersion inputs, provider, and freshness rather than presenting industry adjustment as an opaque score.

## Product queue

Planning and documentation are indexed in [`docs/README.md`](docs/README.md). The live ordered backlog is maintained in [`docs/next-best-actions.md`](docs/next-best-actions.md); completed behavior is recorded separately in [`docs/implemented-features.md`](docs/implemented-features.md).

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
