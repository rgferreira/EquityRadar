"""Build inactive shadow comparisons from immutable historical predictions."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from src.shadow_model import backfill_shadow_history


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database", type=Path, default=None)
    args = parser.parse_args()
    print(json.dumps(backfill_shadow_history(args.database), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
