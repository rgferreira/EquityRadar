# Data freshness and outcome maturation recovery — 2026-09-24

The current implementation still skips already-labelled predictions even when the
label is pending or lacks later horizons. Live 1M outcomes wait for a 75-day gate.
Congress has only two provider batches from August 12; the FMP configuration was
an evicted iCloud placeholder. BTC derivatives lack server-maintenance scheduling.
Successful provider states do not expire. These findings were checked against the
current working tree, including the earlier September 24 performance revamp.

## File-level implementation

- `src/utils/config.py`: private, non-iCloud operational configuration. Explicit
  process settings win; private runtime settings precede the legacy project dotenv
  after discovering that it points to a different, old database.
- `src/data/outcome_maturation.py` (new), `src/data/backtest_refresh.py`: additive,
  immutable horizon observations; daily completion of missing 1M/3M/6M results.
  Preserve raw v1 labels, their hashes and all predictions. An explicit current
  projection includes per-horizon price vintage and source hashes. Current tuning,
  gate evidence, pilot maturity and research comparisons consume that projection;
  frozen evaluation reports and historical promotion lineage retain raw labels.
- `src/operations.py`, `src/data/bitcoin_derivatives.py`: schedule BTC refresh and
  expose stale/blocked status. Distinguish source period from last successful fetch.
- `src/whaleseeker.py`, `src/data/congress_trading.py`, WhaleSeeker page: repair
  ingestion, bounded recovery of missing pages, current freshness and lazy views.
- `src/data_lifecycle.py` (new), Operations page: aggregate inventory of active,
  stale, immature, incomplete and archived research. No private portfolio content.
- Focused synthetic tests and a sanitized audit report with before/after counts.
- Follow-up authorization: delete disposable orphan caches only after a verified
  backup, preserving position dependencies, benchmarks and immutable research.

## Evaluation and acceptance

No score weights, thresholds, benchmark mapping, costs or promotion rules change.
Recovering outcomes is evaluated by exact session boundaries, no overwrite of a
completed horizon, no future/intraday bars, idempotent writes, original-label hash
preservation and fresh aggregate counts. Market data acquired today never supplies
historical `known_at`. Missing evidence remains missing. Provider failures remain
visible and isolated. Full pytest, compile/import, rendered Dashboard and ZeroTier
binding verification are required after changes.

## Risks, assumptions and rollback

Adjusted-price vintages can change between horizon observations; retain each
vintage's entry prices, execution date and full label hash rather than pretending
all horizons were observed together. Recovered historical disclosure availability
is today, not its transaction/filing date. Pagination can shift; imports are
bounded and deduplicated, and incomplete catch-up must remain explicit.

Private code/database backup: Application Support/EquityRadar/
freshness-backup-20260924. Restore only this patch's code to roll back, retaining
additive research tables. Do not restore the entire old database over newer data.
Private FMP fallback can be removed independently. No legacy observations, manual
simulations or archived experiments are deleted.
