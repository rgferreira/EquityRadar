import json

from src.scoring.orthogonality import audit_frame, score_orthogonality_audit


def synthetic_runs(count=20):
    rows = []
    for index in range(count):
        technical = 20 + index * 3
        rows.append({
            "ticker": f"T{index % 4}", "as_of_date": f"2025-{index // 28 + 1:02d}-{index % 28 + 1:02d}",
            "technical_score": technical, "valuation_score": 30 + (index * 17) % 65,
            "risk_score": technical + (index % 2), "entry_signal": "Wait", "entry_score": 45,
            "outcome_1m": index / 3, "outcome_3m": index, "outcome_6m": index * 2,
            "inputs_json": json.dumps({"positioning_modifier": {"entry_adjustment": (index % 5) - 2}}),
            "model_version": "test-v1",
        })
    return rows


def test_audit_frame_extracts_persisted_components_and_outcomes():
    frame = audit_frame(synthetic_runs(5))
    assert set(["Technical", "Valuation", "Risk resilience", "Positioning modifier"]).issubset(frame.columns)
    assert frame["Forward outcome"].notna().all()


def test_audit_flags_correlated_components_and_reports_unique_value():
    audit = score_orthogonality_audit(synthetic_runs())
    technical_risk = next(row for row in audit["pairwise"] if row["Components"] == "Technical ↔ Risk resilience")
    assert technical_risk["Overlap level"] == "High"
    assert audit["matured_outcomes"] == 20
    assert all("Incremental R²" in row for row in audit["components"])


def test_architectural_audit_names_known_raw_input_overlap():
    audit = score_orthogonality_audit([])
    assert any("Drawdown" in row["Shared evidence"] for row in audit["semantic"])
    assert any("Analyst" in row["Shared evidence"] for row in audit["semantic"])
