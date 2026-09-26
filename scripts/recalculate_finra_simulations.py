#!/usr/bin/env python3
"""Append quarantined FINRA-flow counterfactuals for eligible simulations."""

import json

from src.finra_simulation_enrichment import (
    finra_counterfactual_summary, recalculate_finra_simulation_enrichments,
)


if __name__ == "__main__":
    result = recalculate_finra_simulation_enrichments()
    print(json.dumps({"recalculation": result, "summary": finra_counterfactual_summary()}, sort_keys=True))
