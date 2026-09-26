"""Replay risk research from local caches; no provider calls or live policy edits."""
from pathlib import Path
from io import StringIO
import argparse
import json
import sys

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.data.database import get_connection
from src.entry_context import snapshots, historical_inputs
from src.entry_risk import run_research


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--history", action="store_true", help="Also diagnose already-seen legacy history")
    parser.add_argument("--output", type=Path, help="Aggregate completion metadata only")
    args = parser.parse_args()
    with get_connection() as con:
        rows = con.execute("SELECT ticker,history_json FROM market_price_cache WHERE period='max'").fetchall()
    histories = {r["ticker"]: pd.read_json(StringIO(r["history_json"]), orient="split") for r in rows}
    result = run_research(histories, snapshots(), historical_inputs() if args.history else None)
    rendered = json.dumps(result, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered)
    print(rendered)


if __name__ == "__main__":
    main()
