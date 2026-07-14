"""Run and persist the offline Phase 3.8 purged evaluator."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from src.data.database import get_evaluation_dataset, save_evaluation_run
from src.evaluation import DEFAULT_EVALUATION_CONFIG, evaluate_predictions


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database", type=Path, default=None)
    parser.add_argument("--horizon", choices=("1M", "3M", "6M"), default="3M")
    parser.add_argument("--embargo-days", type=int, default=5)
    parser.add_argument("--output", type=Path, help="Optional local JSON report path")
    args = parser.parse_args()
    config = {
        **DEFAULT_EVALUATION_CONFIG,
        "target_horizon": args.horizon,
        "embargo_calendar_days": args.embargo_days,
    }
    rows = get_evaluation_dataset(str(config["label_version"]), args.database)
    report = evaluate_predictions(rows, config)
    save_evaluation_run(report, args.database)
    if args.output:
        args.output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    print(json.dumps({
        "evaluation_id": report["evaluation_id"],
        "status": report["status"],
        "coverage": report["coverage"],
        "scientific_note": report["scientific_note"],
    }, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
