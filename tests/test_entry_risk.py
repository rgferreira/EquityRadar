from copy import deepcopy
from datetime import datetime, timezone

import numpy as np
import pandas as pd
import pytest

from src.entry_context import build_snapshot as build_parent
from src.entry_risk import (build_snapshot, capture, evaluate_risk, replay, risk_features,
                            risk_weights, score_diagnostics, snapshots, unit_outcome)


def histories():
    dates = pd.bdate_range("2023-01-02", "2027-12-31")
    x = np.arange(len(dates))
    return {ticker: pd.DataFrame({"Close": 100 * np.exp(np.cumsum(
        .0002 + .002 * (i + 1) * np.sin(x * .31 + i)))}, index=dates)
        for i, ticker in enumerate(["SPY", "XLK", "XLF", *[f"T{i}" for i in range(6)]])}


def cohort(day="2026-09-26"):
    return {"source": "retrospective_unverified", "as_of_date": day,
            "inputs": [{"ticker": f"T{i}", "entry_score": 90 - i * 10,
                        "entry_signal": "Buy candidate", "model_version": "synthetic",
                        "sector_etf": "XLK" if i < 4 else "XLF", "metrics": {}}
                       for i in range(6)]}


def parent():
    return build_parent(cohort()["inputs"], captured_at="2026-09-26T08:00:00+00:00", market={}, sectors={})


def test_volatility_uses_exact_completed_sessions_and_no_future_or_missing_returns():
    h = histories()
    first = risk_features(h, ["T0"], "2026-09-25")
    h["T0"].loc[h["T0"].index > "2026-09-25", "Close"] *= 100
    assert risk_features(h, ["T0"], "2026-09-25") == first
    assert len(first["T0"]["prices"]) == 61
    h["T0"] = h["T0"].drop(pd.Timestamp(first["T0"]["dates"][20]))
    assert "unavailable" in risk_features(h, ["T0"], "2026-09-25")["T0"]
    h["T0"] = pd.DataFrame({"Close": 100}, index=h["SPY"].index)
    assert risk_features(h, ["T0"], "2026-09-25")["T0"]["unavailable"] == "zero_or_invalid_volatility"


def test_candidate_caps_cash_sector_and_missingness_do_not_change_entries():
    c = cohort()
    features = {f"T{i}": {"annual_vol": .1 * (i + 1)} for i in range(6)}
    result = risk_weights(c, features)
    weights = result["weights"]["candidate_risk"]
    assert set(weights) == {r["ticker"] for r in c["inputs"]}
    assert max(weights.values()) <= .2
    assert sum(weights.values()) < 1
    sectors = result["weights"]["candidate_risk_sector"]
    assert sum(w for t, w in sectors.items() if int(t[1:]) < 4) == pytest.approx(.4)
    assert all(sectors[t] <= weights[t] for t in weights)
    c["inputs"][0]["sector_etf"] = None
    assert "candidate_risk" in risk_weights(c, features)["weights"]
    assert "candidate_risk_sector" not in risk_weights(c, features)["weights"]
    features.pop("T0")
    assert not risk_weights(c, features)["weights"]
    for row in c["inputs"]:
        row["entry_signal"] = "Wait"
    assert risk_weights(c, {})["weights"]["candidate_risk"] == {}


def test_new_clock_replay_and_first_snapshot_immutability(tmp_path):
    from src.entry_risk import capture_overview
    h, p = histories(), parent()
    at = "2026-09-26T11:00:00+00:00"
    snap = build_snapshot(p, h, at)
    assert replay(snap)
    tampered = deepcopy(snap)
    tampered["features"]["T0"]["annual_vol"] *= 2
    assert not replay(tampered)
    with pytest.raises(ValueError, match="not_a_current"):
        build_snapshot(p, h, "2026-09-27T11:00:00+00:00")
    db = tmp_path / "risk.db"
    assert capture([p], h, db, now=datetime.fromisoformat(at))["saved"]
    h["T0"]["Close"] *= 100
    assert not capture([p], h, db, now=datetime(2026, 9, 26, 12, tzinfo=timezone.utc))["saved"]
    assert snapshots(db) == [snap]
    overview = capture_overview(db)
    assert overview["v3"]["count"] == 1
    assert overview["v3"]["latest"] == {k: snap[k] for k in ("captured_at", "output")}
    assert capture([p], h, db, now=datetime(2026, 9, 27, 12, tzinfo=timezone.utc))["status"] == "awaiting_current_parent"


def test_unit_paths_include_costs_and_distinguish_exit_giveback():
    row = unit_outcome([100, 80, 140, 110], [100, 101, 102, 105], 50)
    factor = .9975 / 1.0025
    assert row["net_return_pct"] == pytest.approx((1.1 * factor - 1) * 100)
    assert row["mae_pct"] == pytest.approx((.8 * factor - 1) * 100)
    assert row["mfe_pct"] == pytest.approx((1.4 * factor - 1) * 100)
    assert row["giveback_pp"] == pytest.approx(.3 * factor * 100)
    assert row["excess_spy_pp"] == pytest.approx(.05 * factor * 100)


def test_score_bands_balance_dates_and_never_label_score_as_probability():
    def row(day, excess, score=100):
        return {"as_of_date": day, "entry_score": score, "selected": True,
                "excess_spy_pp": excess, "net_return_pct": excess, "mae_pct": -5}
    rows = [row("2026-01-01", 10) for _ in range(9)] + [row("2026-02-01", -10), row("2026-02-01", 0, None)]
    result = score_diagnostics(rows)
    assert result["excluded_scores"] == 1 and not result["probability_calibration"]
    assert len(result["bands"]) == 2
    for band in result["bands"]:
        assert band["score_band"] == "[80,100]"
        assert band["mean_excess_spy_pp"] == 0
        assert band["date_balanced_hit_pct"] == 50
        assert band["excess_exploratory_95ci"] is None
        assert band["dates"] == 2 and band["observations"] == 10


def test_matched_economic_comparisons_fees_and_diagnostic_populations():
    cs = [cohort(d.date().isoformat()) for d in pd.bdate_range("2024-01-02", "2026-06-30", freq="25B")]
    report = evaluate_risk(cs, histories())
    assert report["test_cohorts"] >= 10
    assert not report["promotion_eligible"]
    for comparison in ["candidate_risk", "candidate_risk_sector"]:
        rows = [r for r in report["periods"] if r["comparison"] == comparison and r["cost_bps"] == 10]
        dates = {r["as_of_date"] for r in rows}
        for day in dates:
            paired = {r["strategy"]: r for r in rows if r["as_of_date"] == day}
            assert len(paired) == 5
            assert paired[comparison]["exposure_pct"] == pytest.approx(paired["current_matched_exposure"]["exposure_pct"])
            assert paired[comparison]["excess_matched_current_pp"] == pytest.approx(
                paired[comparison]["net_return_pct"] - paired["current_matched_exposure"]["net_return_pct"])
    for name in ["candidate_risk", "candidate_risk_sector"]:
        a, b = [next(r for r in report["summary"] if r["strategy"] == name and r["cost_bps"] == cost) for cost in [10, 50]]
        assert b["net_return_pct"] < a["net_return_pct"]
    assert report["diagnostics"]["10"]["losses"]["entries"] == report["test_cohorts"] * 6


def test_invalid_risk_snapshots_and_missing_sector_are_explicit():
    snap = build_snapshot(parent(), histories(), "2026-09-26T11:00:00+00:00")
    snap["output"] = {}
    report = evaluate_risk([snap], histories(), source="prospective")
    assert report["invalid_snapshots"] == 1 and report["capture_dates"] == 0
    cs = [cohort(d.date().isoformat()) for d in pd.bdate_range("2024-01-02", "2025-01-31", freq="25B")]
    for c in cs:
        for r in c["inputs"]:
            r["sector_etf"] = None
    report = evaluate_risk(cs, histories())
    assert report["unavailable_risk"]["missing_original_sector"] == report["test_cohorts"]
    assert all(r["comparison"] == "candidate_risk" for r in report["summary"])


def test_score_ordering_uses_same_dates_and_rejects_constant_ranks():
    rows = [{"as_of_date": day, "entry_score": score, "selected": True,
             "excess_spy_pp": -score, "net_return_pct": -score, "mae_pct": -score}
            for day in ["2026-01-01", "2026-02-01"] for score in [10, 30, 50, 70, 90]]
    # A lone extreme outcome on an extra date must not contaminate paired bands.
    rows.append({**rows[0], "as_of_date": "2026-03-01", "excess_spy_pp": 1000})
    result = score_diagnostics(rows)
    for ordering in result["ordering"]:
        assert ordering["mean_within_date_rank_ic"] == pytest.approx(-1)
        assert ordering["dates"] == 2
    for band in result["paired_bands"]:
        assert band["shared_dates"] == 2
        assert band["upper_minus_lower_excess_pp"] == -20


def test_unattended_run_without_current_parent_waits_instead_of_failing(tmp_path):
    from src.entry_risk import run_research, VERSION
    from src.data.research_signals import statuses
    db = tmp_path / "waiting.db"
    result = run_research({}, [], db_path=db)
    assert result["capture"]["status"] == "awaiting_current_parent"
    assert len(result["reports"]) == 2
    state = next(s for s in statuses(db) if s["scope"] == VERSION)
    assert state["status"] == "empty" and state["error_code"] == "awaiting_current_parent"


def test_mature_research_ui_renders_paired_results_and_score_diagnostics(tmp_path, monkeypatch):
    from streamlit.testing.v1 import AppTest
    from src.entry_risk import save_report
    db = tmp_path / "risk-ui.db"
    monkeypatch.setattr("src.data.database.DATABASE_PATH", db)
    monkeypatch.setattr("src.utils.config.DATABASE_PATH", db)
    cs = [cohort(d.date().isoformat()) for d in pd.bdate_range("2024-01-02", "2025-01-31", freq="25B")]
    save_report(evaluate_risk(cs, histories()), db)
    app = AppTest.from_file("pages/9_Research_Lab.py", default_timeout=20).run()
    assert not app.exception
    app.radio[1].set_value("Diagnóstico histórico").run()
    assert not app.exception
    assert any("Dónde fallan" in s.value for s in app.subheader)
    assert any("Exceso a igual exposición (pp)" in frame.value.columns for frame in app.dataframe)
    app.selectbox[0].set_value("candidate_risk_sector").run()
    app.select_slider[0].set_value(50).run()
    assert not app.exception
    assert any("Peor recorrido medio (%)" in frame.value.columns for frame in app.dataframe)
