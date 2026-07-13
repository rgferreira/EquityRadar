from src.accuracy_audit import compare_accuracy_models


def _run(date, signal, outcome, mature=True):
    return {
        "ticker": "TEST", "as_of_date": date, "model_version": "v1",
        "entry_signal": signal, "entry_score": 65 if signal == "Watch" else 75,
        "outcome_1m": outcome, "outcome_3m": outcome * 3 if mature else None,
        "outcome_6m": outcome * 6 if mature else None,
    }


def test_accuracy_audit_preserves_legacy_and_current_rules():
    audit = compare_accuracy_models({"TEST": [
        _run("2025-01-01", "Watch", 1),
        _run("2025-02-01", "Buy candidate", -2, mature=False),
    ]})
    assert audit["legacy_observations"] == 2
    assert audit["current_observations"] == 1
    assert audit["legacy_micro_accuracy"] == 0
    assert audit["current_micro_accuracy"] == 100


def test_accuracy_audit_moving_curve_is_observation_weighted():
    audit = compare_accuracy_models({
        "A": [_run("2025-01-01", "Buy candidate", 2), _run("2025-02-01", "Buy candidate", -2)],
        "B": [_run("2025-01-01", "Buy candidate", 2)],
    })
    final = audit["current_moving_curve"][-1]
    assert final["observations"] == 3
    assert final["moving_accuracy"] == 66.7
