"""Reprocess frozen entry research locally; no live scoring changes or orders."""
from pathlib import Path
import argparse
import json
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.research_pipeline import run_pipeline

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--history", action="store_true", help="Recompute legacy development diagnostics")
    parser.add_argument("--skip-providers", action="store_true", help="Reuse persisted macro/options/CFTC batches")
    parser.add_argument("--output", type=Path, help="Write an aggregate, privacy-safe completion summary")
    args = parser.parse_args()
    result = run_pipeline(include_history=args.history, refresh_sources=not args.skip_providers)
    rendered = json.dumps(result, indent=2, sort_keys=True)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered + "\n")
    print(rendered)
