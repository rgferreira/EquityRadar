from datetime import date, timedelta

from src.data.database import (
    add_ticker, get_backtest_runs, get_finra_simulation_enrichments,
    save_backtest_run, save_finra_daily_short_volume_file,
)
from src.finra_simulation_enrichment import (
    build_finra_simulation_enrichment, recalculate_finra_simulation_enrichments,
)
from src.model_registry import TECHNOLOGY_POTENTIAL_SHADOW_VERSION
from src.scoring.daily_short_flow import retrospective_daily_short_flow_evidence


def _rows(start: date, count: int = 35) -> list[dict[str, object]]:
    rows = []
    for index in range(count):
        rows.append({
            "id": index + 1, "ticker": "TEST",
            "trade_date": (start + timedelta(days=index)).isoformat(),
            "short_volume": 40.0 + index, "short_exempt_volume": 0.0,
            "total_volume": 100.0, "market": "Q",
            "provider_name": "Synthetic FINRA", "payload_hash": f"hash-{index}",
            "known_at": "2026-08-25T08:00:00+00:00",
            "known_at_status": "verified_observed",
        })
    return rows


def _run() -> dict[str, object]:
    return {
        "id": 42, "ticker": "TEST", "as_of_date": "2026-02-05",
        "entry_score": 68.0, "entry_signal": "Watch",
        "exit_score": 42.0, "exit_signal": "Hold",
        "outcome_1m": 5.0, "outcome_3m": 8.0, "outcome_6m": None,
        "outcome_12m": None, "model_version": "source-v1",
        "inputs_json": '{"technology_potential":{"confidence":0,"entry_modifier":0}}',
    }


def test_retrospective_flow_is_quarantined_and_strictly_before_cutoff() -> None:
    rows = _rows(date(2026, 1, 1))
    rows.append({**rows[-1], "id": 999, "trade_date": "2026-02-05", "short_volume": 0.0})

    evidence = retrospective_daily_short_flow_evidence(rows, as_of="2026-02-05")

    assert evidence["evidence_status"] == "retrospective_only"
    assert evidence["historical_availability"] == "not_point_in_time_verified"
    assert evidence["latest_trade_date"] == "2026-02-04"
    assert evidence["confidence"] > 0


def test_finra_counterfactual_changes_only_candidate_and_has_zero_decision_weight() -> None:
    run = _run()
    original = dict(run)

    enrichment = build_finra_simulation_enrichment(run, _rows(date(2026, 1, 1)))

    assert enrichment["shadow_model_version"] == TECHNOLOGY_POTENTIAL_SHADOW_VERSION
    assert enrichment["evidence_status"] == "retrospective_only"
    assert enrichment["metrics"]["decision_weight"] == 0.0
    assert enrichment["metrics"]["shorts_entry_modifier"] < 0
    assert enrichment["metrics"]["counterfactual_entry_score"] < run["entry_score"]
    assert enrichment["input_references"]["historical_availability"] == "not_point_in_time_verified"
    assert run == original


def test_finra_counterfactual_rejects_insufficient_history() -> None:
    try:
        build_finra_simulation_enrichment(_run(), _rows(date(2026, 1, 20), count=10))
    except ValueError as exc:
        assert "Insufficient retrospective" in str(exc)
    else:
        raise AssertionError("Expected insufficient retrospective FINRA history")


def test_recalculation_is_idempotent_and_preserves_source_simulation(tmp_path) -> None:
    database = tmp_path / "finra-counterfactual.db"
    add_ticker("TEST", database)
    for row in _rows(date(2026, 1, 1)):
        save_finra_daily_short_volume_file(
            str(row["trade_date"]), [row], "Synthetic FINRA", "https://example.invalid/file",
            "2026-08-25T08:00:00+00:00", db_path=database,
        )
    save_backtest_run({
        **_run(), "coverage": "Price-only", "technical_score": 50,
        "valuation_score": 50, "risk_score": 50, "simulation_source": "manual",
        "suggestion_rationale": None,
    }, database)
    before = get_backtest_runs("TEST", database)

    first = recalculate_finra_simulation_enrichments(db_path=database)
    second = recalculate_finra_simulation_enrichments(db_path=database)

    assert first["inserted"] == 1
    assert second["inserted"] == 0
    assert second["already_present"] == 1
    assert get_backtest_runs("TEST", database) == before
    overlays = get_finra_simulation_enrichments(db_path=database)
    assert len(overlays) == 1
    assert overlays[0]["metrics"]["decision_weight"] == 0.0
