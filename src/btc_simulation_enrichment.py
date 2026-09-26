"""Retrospective, zero-weight BTC derivatives overlays for saved simulations."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from statistics import mean
from pathlib import Path

from src.backtesting import latest_model_runs
from src.data.database import (
    get_backtest_runs,
    get_bitcoin_derivatives_daily_observations,
    save_btc_simulation_enrichment,
)


METHODOLOGY_VERSION = "btc-derivatives-retrospective-overlay-v1"
MINIMUM_OBSERVATIONS = 11


def _sell_share(row: Mapping[str, object]) -> float:
    buy = float(row["taker_buy_volume"])
    sell = float(row["taker_sell_volume"])
    total = buy + sell
    if total <= 0:
        raise ValueError("BTC taker volume must be positive")
    return sell / total * 100


def build_btc_simulation_enrichment(
    run: Mapping[str, object], observations: Sequence[Mapping[str, object]],
) -> dict[str, object]:
    """Build a descriptive overlay using only completed days before the cutoff."""
    if str(run.get("ticker")) != "BTC-USD":
        raise ValueError("BTC simulation enrichments require ticker BTC-USD")
    cutoff = str(run["as_of_date"])
    eligible = sorted(
        (row for row in observations if str(row["period_date"]) < cutoff),
        key=lambda row: str(row["period_date"]),
    )
    if len(eligible) < MINIMUM_OBSERVATIONS:
        raise ValueError("At least 11 completed BTC derivatives periods are required")
    window = eligible[-MINIMUM_OBSERVATIONS:]
    current, previous, baseline = window[-1], window[-2], window[0]
    current_sell_share = _sell_share(current)
    average_sell_share = mean(_sell_share(row) for row in window[-10:])
    baseline_open_interest = float(baseline["open_interest_value_quote"])
    if baseline_open_interest <= 0:
        raise ValueError("BTC open interest baseline must be positive")

    short_delta_10d = float(current["short_account_pct"]) - float(baseline["short_account_pct"])
    sell_vs_average = current_sell_share - average_sell_share
    open_interest_change = (
        float(current["open_interest_value_quote"]) / baseline_open_interest - 1
    ) * 100
    if short_delta_10d > 0 and sell_vs_average > 0 and open_interest_change > 0:
        reading = "Short pressure building"
    elif short_delta_10d < 0 and sell_vs_average < 0 and open_interest_change < 0:
        reading = "Short pressure unwinding"
    else:
        reading = "Mixed derivatives pressure"

    metrics = {
        "latest_period_date": str(current["period_date"]),
        "observations": len(window),
        "short_account_pct": round(float(current["short_account_pct"]), 4),
        "short_delta_1d_pp": round(
            float(current["short_account_pct"]) - float(previous["short_account_pct"]), 4,
        ),
        "short_delta_10d_pp": round(short_delta_10d, 4),
        "taker_sell_share_pct": round(current_sell_share, 4),
        "taker_sell_average_10d_pct": round(average_sell_share, 4),
        "taker_sell_vs_average_pp": round(sell_vs_average, 4),
        "open_interest_change_10d_pct": round(open_interest_change, 4),
        "directional_read": reading,
        "decision_weight": 0.0,
    }
    input_references = {
        "policy": "completed UTC periods strictly before cutoff",
        "cutoff": cutoff,
        "period_dates": [str(row["period_date"]) for row in window],
        "observation_ids": [int(row["id"]) for row in window],
        "known_at": [str(row["known_at"]) for row in window],
        "known_at_status": "verified_observed",
        "provider_name": str(current["provider_name"]),
        "historical_availability": "not_point_in_time_verified",
    }
    identity = json.dumps(
        {
            "source_backtest_run_id": int(run["id"]),
            "methodology_version": METHODOLOGY_VERSION,
            "metrics": metrics,
            "input_references": input_references,
        },
        sort_keys=True,
        separators=(",", ":"),
    )
    return {
        "enrichment_id": hashlib.sha256(identity.encode("utf-8")).hexdigest(),
        "source_backtest_run_id": int(run["id"]),
        "ticker": "BTC-USD",
        "as_of_date": cutoff,
        "source_model_version": str(run["model_version"]),
        "methodology_version": METHODOLOGY_VERSION,
        "evidence_status": "retrospective_only",
        "metrics": metrics,
        "input_references": input_references,
    }


def recalculate_btc_simulation_enrichments(
    *, db_path: str | Path | None = None,
) -> dict[str, int]:
    """Append overlays for eligible active BTC cutoffs; never update source runs."""
    runs = latest_model_runs(get_backtest_runs("BTC-USD", db_path=db_path))
    observations = get_bitcoin_derivatives_daily_observations(db_path=db_path)
    inserted = eligible = insufficient_history = already_present = 0
    for run in runs:
        try:
            enrichment = build_btc_simulation_enrichment(run, observations)
        except ValueError as exc:
            if "11 completed" not in str(exc):
                raise
            insufficient_history += 1
            continue
        eligible += 1
        if save_btc_simulation_enrichment(enrichment, db_path=db_path):
            inserted += 1
        else:
            already_present += 1
    return {
        "active_cutoffs": len(runs),
        "eligible_cutoffs": eligible,
        "inserted": inserted,
        "already_present": already_present,
        "insufficient_history": insufficient_history,
    }
