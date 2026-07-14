"""Offline replay of one immutable registered prediction snapshot."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from src.data.database import get_prediction_snapshot
from src.model_registry import replay_prediction


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("prediction_id")
    parser.add_argument("--database", type=Path, default=None)
    arguments = parser.parse_args()
    snapshot = get_prediction_snapshot(arguments.prediction_id, arguments.database)
    if snapshot is None:
        print(json.dumps({"status": "not_found", "prediction_id": arguments.prediction_id}))
        return 2
    report = replay_prediction(snapshot)
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report["matches"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
