# Phase 3.8 audit triage

Audit date: 2026-07-13

Reconciled against: `phase/3.8-audit-hardening` based on `dcf9443` (2026-07-14)

Scope: documentation intake only; no production code or tests changed.

## Conclusion

The scientific findings required by PR-001 through PR-005 remain materially applicable to current HEAD. Existing model-version strings, saved input JSON, episode spacing, and provenance fields are useful foundations, but they do not provide verified point-in-time semantics, immutable predictions, benchmark-relative labels, or purged out-of-sample evaluation.

## Finding reconciliation

| Finding | Status | Current evidence (path and symbol) | Dependency | Risk if unchanged | Proposed PR |
|---|---|---|---|---|---|
| F-07: learning affects live scores from a small in-sample history | still applies | `src/backtesting.py::learned_score_adjustments` activates after three observations and caps adjustments at ±5; `pages/1_Dashboard.py` and `pages/3_Company.py` apply those adjustments to displayed Entry/Exit scores | None; first containment slice | Research feedback is presented inside operational scores before validation | PR-001 quarantine learning |
| F-01/F-02: unverified availability timestamps are accepted as point-in-time evidence | still applies | `src/backtesting.py::evidence_available` falls back to `reporting_date` or `fetched_at`; `src/data/fmp.py::FMPProvider.fetch`, `src/data/yfinance_fundamentals.py::YahooFundamentalsProvider.fetch`, and `src/data/finra_short_interest.py` populate dates that can be fiscal-period or settlement dates rather than public `known_at` | PR-001 containment first | Look-ahead leakage can invalidate every historical score | PR-002 known-at semantics |
| F-03/F-13/F-24: no authoritative model registry or immutable prediction lineage | partially applies | `src/backtesting.py::MODEL_VERSION` and `backtest_runs.inputs_json` preserve some context, but `src/data/database.py::save_backtest_run` uses mutable UPSERTs and `src/backtesting.py::_latest_runs_by_cutoff` / `latest_model_runs` select versions lexicographically | PR-002 temporal contract | Replays are not reproducible; a version name can silently become “latest” | PR-003 model registry and snapshots |
| F-06: outcomes are absolute close-to-close returns | still applies | `src/backtesting.py::evaluate_outcomes` derives raw 1M/3M/6M returns with no benchmark, next-session execution convention, costs, or downside label; `decision_outcome` only combines those absolute returns | PR-002 and PR-003 for reliable timestamps/predictions | A rising market can make weak decisions appear successful | PR-004 relative outcomes |
| F-04/F-05/F-17/F-27: evaluation is not purged, clustered, or genuinely out of sample | partially applies | `src/backtesting.py::select_learning_observations` spaces same-signal episodes by 21 days, but there is no horizon-aware purge/embargo, rolling-origin evaluator, ticker/date clustering, uncertainty interval, or baseline comparison | PR-003 immutable predictions and PR-004 labels | Overlap and selection bias inflate apparent accuracy and learning curves | PR-005 purged evaluator |

## Drift since the audited snapshot

- The evidence pack recorded 94 passing tests; current HEAD collects and passes 96.
- Extended-hours quote support and additional documentation landed after the audit. Extended-hours data remains advisory and does not resolve the five scientific findings.
- The active historical scorer is still `backtested-learning-v4-orthogonal`; learning modifiers remain visible and applied in live score presentation.
- Current code includes useful source/provenance fields and episode selection logic, but no finding above is fully resolved.

## Commands and current results

Run on 2026-07-14 without accessing secrets, personal SQLite records, or external providers:

```text
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m pytest -q -p no:cacheprovider
96 passed in 0.95s

PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m pytest --collect-only -q -p no:cacheprovider
96 tests collected in 0.40s

PYTHONPYCACHEPREFIX=/private/tmp/per-phase38-pyc .venv/bin/python -m compileall -q -f app.py pages src tests
success (no output)

PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -c "import app; print('import app: OK')"
import app: OK (with expected Streamlit bare-context warnings)

curl -fsS --max-time 5 http://127.0.0.1:8501/_stcore/health
ok
```

The supplied evidence pack is sanitized and must not be cited as proof of alpha.
