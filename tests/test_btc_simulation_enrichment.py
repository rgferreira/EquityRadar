from datetime import date, timedelta

import pytest

from src.btc_simulation_enrichment import (
    build_btc_simulation_enrichment,
    recalculate_btc_simulation_enrichments,
)
from src.data.database import (
    get_backtest_runs,
    get_btc_simulation_enrichments,
    save_backtest_run,
    save_bitcoin_derivatives_daily_observations,
)


def _observations(start: date, count: int) -> list[dict[str, object]]:
    rows = []
    for index in range(count):
        period = start + timedelta(days=index)
        rows.append({
            "id": index + 1,
            "venue": "Binance USD-M Futures",
            "instrument": "BTCUSDT perpetual",
            "period_date": period.isoformat(),
            "taker_buy_volume": 100.0,
            "taker_sell_volume": 90.0 + index,
            "long_account_pct": 60.0 - index / 10,
            "short_account_pct": 40.0 + index / 10,
            "open_interest_value_quote": 1_000.0 + index * 10,
            "quote_currency": "USDT",
            "provider_name": "Synthetic provider",
            "source_endpoints": ["/synthetic"],
            "payload": {"index": index},
            "payload_hash": f"hash-{index}",
            "known_at": "2026-08-25T10:00:00+00:00",
            "known_at_status": "verified_observed",
            "fetched_at": "2026-08-25T10:00:00+00:00",
        })
    return rows


def _run(run_id: int = 7, cutoff: str = "2026-01-12") -> dict[str, object]:
    return {
        "id": run_id, "ticker": "BTC-USD", "as_of_date": cutoff,
        "model_version": "test-model", "entry_signal": "Watch", "entry_score": 50,
    }


def test_overlay_excludes_same_day_and_future_observations() -> None:
    rows = _observations(date(2026, 1, 1), 13)
    rows[11]["short_account_pct"] = 99.0
    rows[12]["short_account_pct"] = 98.0

    overlay = build_btc_simulation_enrichment(_run(), rows)

    assert overlay["metrics"]["latest_period_date"] == "2026-01-11"
    assert overlay["metrics"]["short_account_pct"] == pytest.approx(41.0)
    assert overlay["metrics"]["decision_weight"] == 0.0
    assert overlay["evidence_status"] == "retrospective_only"
    assert overlay["input_references"]["historical_availability"] == "not_point_in_time_verified"


def test_overlay_describes_building_short_pressure_without_changing_source() -> None:
    run = _run()
    original = dict(run)

    overlay = build_btc_simulation_enrichment(run, _observations(date(2026, 1, 1), 11))

    assert overlay["metrics"]["short_delta_10d_pp"] == pytest.approx(1.0)
    assert overlay["metrics"]["taker_sell_vs_average_pp"] > 0
    assert overlay["metrics"]["open_interest_change_10d_pct"] == pytest.approx(10.0)
    assert overlay["metrics"]["directional_read"] == "Short pressure building"
    assert run == original


def test_recalculation_is_additive_idempotent_and_preserves_backtest(tmp_path) -> None:
    database = tmp_path / "btc-overlay.db"
    rows = _observations(date(2026, 1, 1), 12)
    save_bitcoin_derivatives_daily_observations(rows, db_path=database)
    save_backtest_run({
        "ticker": "BTC-USD", "as_of_date": "2026-01-12", "coverage": "Price-only",
        "entry_score": 50, "exit_score": 40, "entry_signal": "Watch",
        "exit_signal": "Hold", "technical_score": 50, "valuation_score": 50,
        "risk_score": 50, "outcome_1m": 3.2, "outcome_3m": None,
        "outcome_6m": None, "outcome_12m": None, "inputs_json": "{}",
        "model_version": "test-model", "simulation_source": "manual",
        "suggestion_rationale": None,
    }, db_path=database)
    before = get_backtest_runs("BTC-USD", db_path=database)

    first = recalculate_btc_simulation_enrichments(db_path=database)
    second = recalculate_btc_simulation_enrichments(db_path=database)

    assert first["inserted"] == 1
    assert second["inserted"] == 0
    assert second["already_present"] == 1
    assert get_backtest_runs("BTC-USD", db_path=database) == before
    stored = get_btc_simulation_enrichments(db_path=database)
    assert len(stored) == 1
    assert stored[0]["source_entry_signal"] == "Watch"
    assert stored[0]["metrics"]["decision_weight"] == 0.0
