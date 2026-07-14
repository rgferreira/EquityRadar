from src.evidence_monitoring import options_evidence_report


def test_options_gate_requires_continuity_and_overlap():
    rows = []
    for day in range(1, 22):
        rows.append({
            "snapshot_date": f"2026-06-{day:02d}",
            "payload": {
                "options": {"put_call_oi_ratio": 0.8},
                "short": {"shares_short": 100},
            },
        })
    report = options_evidence_report({"AAA": rows})[0]
    assert report["research_ready"] is True
    assert report["options_dates"] == 21


def test_missing_options_never_become_evidence():
    report = options_evidence_report({"AAA": [{"snapshot_date": "2026-06-01", "payload": {}}]})[0]
    assert report["research_ready"] is False
    assert report["coverage_pct"] == 0
