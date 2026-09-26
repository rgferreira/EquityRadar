#!/usr/bin/env python3
"""Append zero-weight retrospective BTC overlays to eligible saved simulations."""

import json

from src.btc_simulation_enrichment import recalculate_btc_simulation_enrichments


if __name__ == "__main__":
    print(json.dumps(recalculate_btc_simulation_enrichments(), sort_keys=True))
