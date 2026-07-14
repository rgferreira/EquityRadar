"""Run the pre-registered missing-valuation challenger on confirmation dates."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from src.challenger_research import CHALLENGER_CONFIG, evaluate_coverage_challenger
from src.data.database import get_evaluation_dataset, save_challenger_experiment


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database", type=Path, default=None)
    parser.add_argument("--output", type=Path, default=None)
    args = parser.parse_args()
    rows = get_evaluation_dataset(str(CHALLENGER_CONFIG["label_version"]), args.database)
    report = evaluate_coverage_challenger(rows)
    save_challenger_experiment(report, args.database)
    if args.output:
        args.output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    print(json.dumps({
        "experiment_id": report["experiment_id"], "status": report["status"],
        "coverage": report["coverage"], "candidate_utility_pct": report["candidate_utility_pct"],
        "challenger_utility_pct": report["challenger_utility_pct"],
        "paired_utility_delta_pct": report["paired_utility_delta_pct"],
        "paired_accuracy_delta": report["paired_accuracy_delta"],
        "scientific_note": report["scientific_note"],
    }, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
