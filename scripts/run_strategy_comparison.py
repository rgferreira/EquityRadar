"""Local-only reproducible strategy comparison (no network unless --capture is supplied)."""
import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.research_lab import capture_and_label, compare_strategies, historical_cohorts, prospective_cohorts


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--capture", action="store_true", help="Fetch public prices and freeze today's separate research snapshot")
    args = parser.parse_args()
    if args.capture:
        capture_and_label(args.db)
    report = {source: {h: compare_strategies(loader(args.db), h) for h in ("1M", "3M")}
              for source, loader in (("retrospective_unverified", historical_cohorts), ("prospective", prospective_cohorts))}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, allow_nan=False) + "\n")
    print(json.dumps({source: {h: r["evaluated_nonoverlapping_cohorts"] for h, r in horizons.items()}
                      for source, horizons in report.items()}))


if __name__ == "__main__":
    main()
