# Implemented features

## Phase 3.9 — Model tuning research console

- A dedicated read-only page compares the active decision policy with the inactive coverage-aware shadow model.
- Paired 3M benchmark-relative outcomes use identical ticker/cutoff evidence and date-clustered uncertainty intervals.
- Score deltas, signal transitions, maturity, expanding utility and ticker/regime/source drill-downs are visible without exposing model activation controls.
- Evidence gates remain advisory and cannot promote or mutate the active model.

This is the detailed implementation record. For the live backlog and phase boundary, see [`next-best-actions.md`](next-best-actions.md); for the compact phase/model narrative, see [`internal-changelog.md`](internal-changelog.md); for all document roles, see [`README.md`](README.md).

## Phase 3.3 — UI polishing

- Renamed Dashboard to Decision dashboard throughout navigation and page chrome.
- Decision table adds a single prioritized Diagnostic, clickable ticker drill-down, Dashboard-order handoff to Company, and subtle full-row highlighting for current Portfolio holdings.
- Portfolio lot editing/deletion now sits in a collapsed workflow directly after Add purchase lot.
- Company includes an explicit back link, respects the current Decision dashboard order, and accepts ticker deep links.
- Entry cards now map one-to-one to the detailed tabs: Fundamentals & valuation, Market metrics, Industry & analysts, and Market positioning.
- Exit-review now mirrors Entry visually with a centered severity-colored score and a two-column deterioration breakdown.
- The main Company chart includes a synchronized FINRA pressure pulse: coral/teal short-interest change bars and a gold days-to-cover line beneath price and moving averages.
- Watchlist removal now uses live controls outside a form, confirms the exact selected ticker, and retains the Portfolio ownership guard.
- Decision dashboard drill-down uses same-tab row selection, eliminating the tab proliferation caused by link columns.
- Diagnostics show both sides (`Entry / Exit`) consistently; their width follows the longest current value.
- The compact two-column market snapshot now follows the decision table, reducing the phone scroll before the primary content.
- A short-reversal lever rewards only a reported change from rising to falling short interest when technical strength confirms it; rising shorts alone remain cautionary evidence.
- Every page keeps only its H1 title in a minimal sticky strip while scrolling.

## Market positioning MVP

- Provider-neutral daily positioning snapshots persisted in SQLite with provider, reporting date, and fetched-at metadata.
- Automatic stale-while-refresh loading on Company selection; provider errors preserve the last successful snapshot.
- Yahoo short interest, three nearest option expiries, ownership, insider transactions, and 90-day analyst actions, plus FMP Basic float validation where available.
- Transparent 0–100 Long positioning, Short pressure, Squeeze potential, and Confidence outputs with evidence and explicit options-data caveats.
- Phase 3.2 integration: official FINRA history provides six-report trend context; reliability-gated modifiers are capped at ±5 Entry points and ±7 Exit-review points and are shown explicitly in Company and Dashboard.
- Phase 3.8 PR-001 quarantine: backtested-learning evidence, confidence and historical accuracy remain visible, while a centralized default-off policy prevents those research modifiers from changing live Entry/Exit scores.
- Phase 3.8 PR-002 temporal contract: additive `period_end`/`published_at`/`known_at`/status metadata, conservative observed-at-fetch rules for new snapshots, unverified legacy exclusion, and cutoff-auditable simulation coverage.
- Phase 3.8 PR-003 governance: explicit active-candidate/champion registry, content-hashed input snapshots, immutable prediction identities and outputs, append-only compatibility outcomes, visible legacy separation, and offline structured replay.
- Phase 3.8 PR-004 labels: append-only benchmark-relative 1M/3M/6M outcomes with next-session execution, explicit benchmark/cost/timing provenance, missing-evidence states, and six-month drawdown.
- Phase 3.8 PR-005 evaluator: deterministic offline rolling-origin folds with horizon-aware purge/embargo, decision-date clustering, shared frozen baselines, uncertainty intervals, append-only reports, and no live-score or promotion path.
- Phase 3.9 shadow foundation: registered inactive coverage-aware candidate, immutable current-versus-shadow snapshots from Dashboard refreshes and new simulations, and strict failure isolation with no visible score or model-activity change.
- Extended-hours continuity: after post-market closes and before the next pre-market opens, Dashboard Price uses the latest after-hours print with a `POST` badge rather than reverting to the regular close.
- Historical bootstrap completed for the current watchlist, with 129–205 official FINRA observations per ticker. Missing current evidence still produces a zero adjustment.
- Missing official FINRA history now backfills automatically for every equity added to the Watchlist and when Dashboard or Company detects a coverage gap; the Company chart rerenders when the background job completes. Non-equity instruments remain explicitly without FINRA coverage.
- Saved simulations are rebuilt with a versioned point-in-time model after FINRA backfill. Each cutoff uses only reports published on or before that date, stores the exact observation count and modifier, and cannot see later FINRA reports.

## Phase 3.4 · Backtested Learning

- The Decision dashboard Time Machine switches between present-day analysis and a custom historical cutoff.
- Historical reconstruction downloads sufficient price history automatically and strictly excludes observations after the selected date from technical, risk, valuation, Entry, and Exit-review calculations.
- Fundamentals are eligible only when their reporting/fetched date is on or before the cutoff; otherwise the simulation is explicitly labelled price-only.
- Forward 1/3/6/12-month outcomes are calculated separately after scoring and persisted in SQLite with the full inputs and scoring-model version.
- Per-ticker lessons expose confirmed independent episodes versus saved simulations, confirmed decision accuracy, provisional outcomes, weighted outcome and confidence.
- Phase 3.7 interprets outcomes against the original decision: positive performance after Wait is a missed opportunity, while weakness after Wait is correct avoidance. It combines monthly-normalized 1M/3M/6M performance with 50%/30%/20% weights and transparently renormalizes weights while later horizons remain immature.
- A systematic learning-value gate requires a matured 3M outcome, retains informative score/outcome disagreements, and filters near-duplicate or same-signal simulations inside one 21-day decision episode. One-month-only evidence remains provisional and cannot alter scores. Only confirmed independent episodes count toward the three-observation minimum for transparent opposing Entry/Exit-review modifiers capped at ±5 points.
- Simulations run in a persistent background worker with per-ticker queued/running/completed/failed state, so navigating to another page does not cancel the job.
- Dashboard provides a saved-simulation archive and per-ticker history showing decision conclusions, weighted outcomes, learning value, inclusion/exclusion and rationale; Company detail presents the same decision-aware evidence beside its current score impact.
- Active simulations expose live persisted progress and remain visible after returning to Dashboard; completed jobs distinguish unavailable tickers from work still running and never retry permanent provider failures in a loop.
- Saved runs automatically refresh incomplete forward outcomes once per calendar day. Immature 3M/12M horizons are labelled with their required trading-session count instead of displaying an ambiguous null value.
- Intelligent cutoff discovery ranks up to six non-redundant historical dates from broad-market regimes, watchlist momentum/MA events and FINRA short-interest changes. Suggestions refresh automatically each day or after watchlist changes, persist their evidence and rationale, and visibly track Not run, Running and Completed states alongside a custom-date option.
- Suggested and custom dates are staged without side effects; the user must explicitly confirm every historical simulation.
- The Score overlap audit deduplicates model versions by ticker/cutoff, measures component rank correlations, estimates leave-one-component-out incremental R² against normalized forward outcomes, and identifies architectural reuse of drawdown, analyst actions, technical gates and learned feedback.
- Model v4 applies the accepted orthogonality revision: Technical no longer scores proximity to the 52-week high because Risk already owns drawdown, and Market positioning no longer scores analyst upgrades/downgrades because Industry & analysts owns that evidence. Technical MA weights were rescaled to keep a transparent 0–100 range; top-level component weights remain unchanged.
- Every distinct saved ticker/cutoff was recalculated under v4 with its original point-in-time restrictions. Older model rows remain in SQLite as rollback evidence, while Dashboard, Company and learning calculations select only the newest model per ticker/cutoff.
- Entry and Exit-review headers show exact-diagnostic historical success with an explicit numerator/denominator and a three-comparable-observation minimum; Entry also shows aggregate ticker decision accuracy.
- Company detail ends with a responsive cumulative confirmed-accuracy timeline whose auditable points share the same independent-episode selection used by live score modifiers.
- Extended-hours awareness retrieves pre-market and after-hours quotes through a replaceable yfinance adapter, caches them for five minutes in SQLite, refreshes the watchlist non-blockingly and exposes timestamps in Dashboard and Company. Exchange-provided trading periods drive session classification; official closing prices remain the sole scoring input.
- Historical simulation provenance is persisted as manual or system-suggested, including the suggestion rationale. Company charts render fine dotted cutoff markers in blue (manual), purple (completed suggestion), and gold (suggested but pending).
- Company detail applies the same per-ticker Backtested Learning modifier as Dashboard to both Entry and Exit-review scores, exposes the stored observation history in its own tab, and color-codes learned impact (green favorable, red adverse, gray inactive) with Exit-review semantics correctly inverted.

## Phase 3.5 · Position-Aware Decisions

- Company Entry and Exit-review remain common research evidence so owned and unowned securities stay analytically comparable.
- Decision dashboard separates owned positions into **Portfolio actions** and unowned securities into **Watchlist opportunities** instead of relying on row highlighting.
- Time Machine can explicitly re-scan for more suggested cutoffs; suggestions distinguish market momentum, trend, volatility and drawdown regimes, single-stock shocks and transitions, and FINRA short-interest build-ups or unwind events.
- Unowned diagnostics use initiation vocabulary: Initiate / Buy candidate / Watch / Wait.
- Owned positions receive a transparent Add score, Trim pressure and final Add / Hold / Monitor closely / Trim review / Exit review action.
- Position actions incorporate current portfolio weight, optional target-weight gap and concentration; company deterioration still independently drives Exit review.
- Company detail detects ownership automatically and shows current weight, target weight, Add score, Trim pressure and full position-action rationale. Unowned companies explicitly remain initiation decisions.

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
