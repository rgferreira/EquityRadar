import json

from src.model_tuning import (
    build_post_promotion_report,
    build_model_tuning_report, cumulative_date_evidence, prepare_shadow_comparisons,
)


def test_post_promotion_monitor_excludes_materialized_history():
    predictions = [
        {
            "prediction_id": "old", "ticker": "AAA", "as_of_date": "2026-01-01",
            "model_version": "v3", "created_at": "2026-07-14 10:00:00",
            "output_json": '{"entry_signal":"Buy candidate"}',
        },
        {
            "prediction_id": "new", "ticker": "AAA", "as_of_date": "2026-07-15",
            "model_version": "v3", "created_at": "2026-07-15 10:00:00",
            "output_json": '{"entry_signal":"Buy candidate"}',
        },
    ]
    labels = [
        {
            "prediction_id": "old", "status": "available",
            "outcomes_json": '{"3M":{"relative_return_after_cost_pct":-2}}',
        },
        {
            "prediction_id": "new", "status": "available",
            "outcomes_json": '{"3M":{"relative_return_after_cost_pct":4}}',
        },
    ]
    report = build_post_promotion_report(
        predictions, labels, model_version="v3", promoted_at="2026-07-14 12:00:00",
    )
    assert report["matured_observations"] == 1
    assert report["independent_dates"] == 1
    assert report["accuracy_pct"] == 100.0


def shadow(identifier, decision_date, live_signal, candidate_signal, delta, *, ticker="AAA"):
    return {
        "shadow_snapshot_id": identifier,
        "ticker": ticker,
        "as_of_date": decision_date,
        "surface": "historical_replay",
        "current_model_version": "live-v1",
        "current_config_hash": "live-hash",
        "challenger_model_version": "shadow-v1",
        "challenger_config_hash": "shadow-hash",
        "input_json": json.dumps({"features": {"technical_score": 80}}),
        "current_output_json": json.dumps({"entry_score": 66, "entry_signal": live_signal}),
        "challenger_output_json": json.dumps({"entry_score": 66 + delta, "entry_signal": candidate_signal}),
        "entry_score_delta": delta,
        "signal_changed": int(live_signal != candidate_signal),
        "coverage_mode": "valuation_unavailable_renormalized",
    }


def prediction(identifier, decision_date, *, ticker="AAA"):
    return {
        "prediction_id": identifier,
        "ticker": ticker,
        "as_of_date": decision_date,
        "model_version": "live-v1",
        "config_hash": "live-hash",
        "simulation_source": "manual",
    }


def label(identifier, relative_return, *, status="available"):
    return {
        "prediction_id": identifier,
        "status": status,
        "outcomes": {"3M": {
            "end_date": "2026-06-01", "relative_return_after_cost_pct": relative_return,
        }} if status == "available" else {},
        "max_drawdown_6m_pct": -12,
    }


def test_join_is_versioned_and_missing_evidence_stays_missing():
    shadows = [
        shadow("s1", "2026-01-02", "Watch", "Buy candidate", 8),
        shadow("s2", "2026-02-02", "Wait", "Wait", 0),
    ]
    rows = prepare_shadow_comparisons(
        shadows,
        [prediction("p1", "2026-01-02"), prediction("p2", "2026-02-02")],
        [label("p1", 10), label("p2", 0, status="unavailable")],
    )

    assert rows[0]["utility_delta_pct"] == 20
    assert rows[0]["accuracy_delta"] == 1
    assert rows[1]["label_status"] == "unavailable"
    assert rows[1]["utility_delta_pct"] is None


def test_report_clusters_dates_and_never_promotes_automatically():
    shadows = []
    predictions = []
    labels = []
    for index in range(12):
        decision_date = f"2025-{index + 1:02d}-02"
        identifier = f"p{index}"
        ticker = ("AAA", "BBB", "CCC")[index % 3]
        shadows.append(shadow(
            f"s{index}", decision_date, "Wait", "Buy candidate", 10, ticker=ticker,
        ))
        predictions.append(prediction(identifier, decision_date, ticker=ticker))
        labels.append(label(identifier, 5))
    rows = prepare_shadow_comparisons(shadows, predictions, labels)
    report = build_model_tuning_report(rows)

    assert report["coverage"]["matured_dates"] == 12
    assert report["changed_paired"]["utility_delta_pct"]["estimate"] == 10
    assert report["gate"]["status"] == "Eligible for human review"
    assert report["gate"]["passed"] == report["gate"]["total"] == 6
    assert "promotion" not in report["gate"]


def test_cumulative_curve_uses_date_means_not_ticker_count():
    rows = [
        {"as_of_date": "2026-01-01", "live_utility_pct": 0, "shadow_utility_pct": 10},
        {"as_of_date": "2026-01-01", "live_utility_pct": 10, "shadow_utility_pct": 10},
        {"as_of_date": "2026-02-01", "live_utility_pct": -5, "shadow_utility_pct": 5},
    ]
    curve = cumulative_date_evidence(rows)

    assert curve[0]["live_expanding_utility_pct"] == 5
    assert curve[1]["live_expanding_utility_pct"] == 0
    assert curve[1]["shadow_expanding_utility_pct"] == 7.5


def test_gate_progress_is_explicit_while_changed_outcomes_are_immature():
    rows = [{
        "ticker": "AAA", "as_of_date": "2026-07-17", "signal_changed": True,
        "utility_delta_pct": None, "label_status": "awaiting_outcome",
        "score_delta": 2, "coverage_mode": "ready", "technical_regime": "Mixed technical",
        "simulation_source": "live",
    }]

    report = build_model_tuning_report(rows)

    assert report["coverage"]["pending_signal_changes"] == 1
    assert report["coverage"]["pending_changed_dates"] == 1
    assert report["gate"]["criteria"][1]["progress_pct"] == 0
    assert report["gate"]["criteria"][2]["available"] is False


def test_daily_shadow_comparisons_keep_first_frozen_observation_only():
    first = shadow("s1", "2026-07-17", "Watch", "Buy candidate", 8)
    second = {**shadow("s2", "2026-07-17", "Watch", "Buy candidate", 9), "created_at": "2026-07-17 12:00:00"}
    first["created_at"] = "2026-07-17 09:00:00"

    rows = prepare_shadow_comparisons(
        [second, first], [prediction("p1", "2026-07-17")], [label("p1", 5)],
    )

    assert len(rows) == 1
    assert rows[0]["score_delta"] == 8
