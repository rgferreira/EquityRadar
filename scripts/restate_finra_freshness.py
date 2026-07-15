"""Append-only restatement of saved simulations under FINRA report-date freshness."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from src.data.backtest_refresh import restate_saved_simulations


if __name__ == "__main__":
    report = restate_saved_simulations()
    destination = Path("work/reports")
    destination.mkdir(parents=True, exist_ok=True)
    path = destination / f"finra-freshness-restatement-{datetime.now():%Y%m%d-%H%M%S}.json"
    path.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    print(json.dumps({key: value for key, value in report.items() if key != "tickers"}, indent=2))
    print(f"audit_report={path}")
