# Entry context v2 — frozen research contract

Registered 2026-09-24 before running this experiment. Research only; no live policy
or promotion changes. v1 remains immutable. This document defines the method for
the four steps authorized by Rafa. Historical results already examined in earlier
work are development diagnostics, never a fresh unseen holdout.

## Fixed candidates and comparators

- Current policy reference: recorded `Buy candidate` decisions, equal weight among
  buys, otherwise cash. It is a theoretical entry basket, not the user's portfolio
  or the application's discretionary exit policy. Record score, source and vintage.
- Candidate A: identical buys and weights, but remain in cash if SPY's last completed
  close is at or below its trailing 200-session average. Missing regime makes the
  cohort unavailable, not bearish. No fitted threshold.
- Candidate B: use the same buy set; require positive 63-session sector ETF excess
  over SPY and positive stock excess over its sector ETF. Rank lexicographically
  by stock-minus-sector return, sector-minus-SPY return, recorded entry score and
  ticker. Select at most five, 20% per slot, at most two names per sector; empty
  slots remain cash. Fixed US sector ETF mapping, unknown sectors unavailable.
- Ablations: the sector selection without its sector-leadership condition and the
  market filter alone; controls: SPY, equal-weight universe, frozen v1 momentum.
- Macro, CFTC and options initially receive **zero directional weight**. Their
  values, availability and missingness are frozen alongside prospective decisions.
  Coverage alone never authorizes a factor weight or promotion.

## Evaluation and admission

Primary horizon 21 common daily sessions (1M); secondary 63 (3M). Enter at the
first common completed-session close strictly after the capture date. Reject a
whole cohort if any member of its input universe lacks its complete price path;
no forward-fill, silent survivor filtering or backdated current sector mapping.
Historical sector context must come from the original stored input or is missing.

One chronological test block at a time; forbid test windows overlapping a prior
test. Training/diagnostic history must end at least five calendar days before the
test capture. Rules have no estimated parameters; report purged prior dates rather
than pretend to fit a model. First three eligible dates are warm-up. Prospective
captures made after registration form the actual unseen evaluation stream.

Use adjusted daily prices and fixed-share buy-and-hold baskets during each block,
liquidated at its end; cash return 0. Debit 5 bps on entry notional and 5 bps on
exit market value (10 bps nominal round trip), with 30 and 50 bps stress scenarios.
SPY follows the identical cost and cash-gap convention. Report entry/exit turnover,
net return, geometric equity, maximum daily drawdown (including starting capital),
excess versus SPY and the current-policy basket, entry precision versus SPY, exposure,
cohort counts, period/sector attribution and leave-one-selected-name-out sensitivity.

Uncertainty: paired moving-block bootstrap of cohort excess, circular blocks of two,
2,000 draws with fixed seed 20260924; with fewer than ten test cohorts no confidence
interval. Multiple candidates make all intervals exploratory, not promotion tests.
Report all frozen candidates regardless of results, never select a retrospective
winner. Missing data and insufficient independent periods remain explicit.

## Temporal contract and sources

Every source batch retains exact provider payload, digest, first observation time,
effective/report date and verified publication time when supplied. Revisions append
a new batch. `known_at` for new decision captures is conservative first observation,
never an effective date, publication schedule or current download assigned to history.
Source publication timestamps remain separate; no fabricated macro surprises.

Macro: official Fed H.15 / NY Fed reference rates and monetary-policy RSS; nominal
curve, real rates and corporate credit spread when available. Store revisions from
now; backfilled current vintages are context only. A missing source stays unavailable.
Flows: official CFTC TFF futures-only asset-manager and leveraged-money positioning,
normalized by open interest with weekly differences. This is delayed positioning,
not cash flow or proof of a specific institution's trades. Congressional coverage
and its FMP entitlement gap remain distinct.

Options: independent Yahoo/yfinance capture of up to three expiries in 20–60 calendar
days, closest to 30/45/60 days. Persist strike, expiry, bid/ask, volume, open interest,
IV, last trade time and underlying quote time. Eligible standard USD contracts need
positive bid, ask >= bid, spread/mid <= 25%, OI >= 100, IV in (0,5], moneyness 0.8–1.2
and a trade within seven calendar days. Require at least three liquid calls and puts
per expiry for summaries. No invented dealer gamma exposure: derive European
Black–Scholes delta/gamma/vega only when spot, fresh rate and dividend yield are
available; label the approximation and its inputs. No historical chain reconstruction.

## File plan, risks and rollback

Add `src/data/research_signals.py` (append-only batches/status and temporal queries),
`src/data/macro_context.py`, `src/data/institutional_positioning.py`,
`src/data/options_context.py` (bounded public providers), `src/entry_context.py`
(fixed candidates and captures), `src/strategy_validation.py` (economic evaluator),
and `src/research_pipeline.py` (background orchestration). Extend Research Lab,
Operations and WhaleSeeker with cached summaries; no provider calls on page render.
Add focused synthetic tests and a reproducible local CLI. Preserve legacy tables.

Operational implementation: `src/scoring/current_policy.py` extracts the existing
Dashboard's final combination without changing weights or thresholds. Subsequent
daily captures compute that same policy from completed bars and current local
provider caches, storing the exact numeric policy inputs for replay. They do not
require someone to open Dashboard. The initial capture on 24 September retains
the already observed Dashboard decisions and is not replaced. Data source and
model configuration are explicit; this is still a theoretical entry basket.

Provider verification selected the Fed's active 30-day A2/P2-minus-AA nonfinancial
commercial-paper feeds as the credit measure. The old Moody's Baa RSS was stopped
in 2016 and is not admitted. H.15 feed-update timestamps are retained as update
metadata, not certified initial release times. Future-dated update metadata blocks
context until that timestamp. Monetary-policy RSS `pubDate` is retained separately.

Risks: sparse cohorts, personal-watchlist selection, retroactive adjusted-price
revisions, incomplete sectors, delayed/limited provider coverage, approximation of
American options, API latency. Do not describe these data as validated alpha.

Rollback: private verified online SQLite/code backup in
`~/Library/Application Support/EquityRadar/four-steps-backup-20260924/`.
Revert only this task's file patches and scheduler hook; leave additive tables
in place. Never replace the active database with an old backup over newer captures.

Acceptance: actual source ingestion, immutable forward capture, persisted historical
diagnostics with honest exclusions, automatic maturation, UI coverage and failure
states, full pytest, compile/import checks, verified Dashboard/ZeroTier restart.
