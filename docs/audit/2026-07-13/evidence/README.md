# PersonalEquityRadar forensic review — evidence pack

Generated 2026-07-13 from the sanitized `PersonalEquityRadar_AuditBundle.zip`.

## Contents

- `repository_inventory.json`: source-file, database-schema, PRAGMA and row-count inventory.
- `empirical_summary.json`: independently recomputed sample, maturity, clustering, distributions, rank diagnostics, stability and policy-utility summaries.
- `baseline_diagnostics.json`: current policy versus trivial policies under the application's own utility; current score versus core without positioning.
- `latest_model_research_rows.csv`: sanitized research rows for the latest model only; no personal portfolio or Journal data.
- `learning_episodes_by_ticker.csv`: episode-count summary only.
- `empirical_audit.py`: reproducible calculation script used for the empirical summary.
- `pytest_q.txt`, `pytest_collect.txt`: original test output and collected tests.
- `compileall.txt`, `import_check.txt`: compile/import checks.
- `streamlit_health.txt`, `streamlit_server.log`: application startup/health evidence.
- `pip_freeze.txt`: isolated environment package versions.
- `manifest.sha256`: checksums for this pack.

## Privacy

This pack excludes the SQLite database, portfolio quantities, transactions, cost bases, cash flows, Journal text, API keys and secrets. The CSV files contain only research/backtest observations from the sanitized database.

## Important interpretation

Passing tests or reproducing calculations does not validate the investment methodology. The report explains the point-in-time, selection, clustering and objective-function limitations that prevent treating these rows as independent evidence of alpha.
