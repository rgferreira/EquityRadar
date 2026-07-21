"""Synthetic AppTest coverage for every user-facing page.

These tests deliberately use an empty temporary database: browser regression
coverage must never depend on or expose the user's local research data.
"""

from pathlib import Path

import pandas as pd
import pytest
from streamlit.testing.v1 import AppTest

from src.data.database import init_db
from src.data.database import add_ticker


PAGES = (
    ("pages/1_Dashboard.py", "Decision dashboard"),
    ("pages/2_Portfolio.py", "Portfolio"),
    ("pages/3_Company.py", "Company detail"),
    ("pages/4_Journal.py", "Investment journal"),
    ("pages/0_Watchlist.py", "Watchlist management"),
    ("pages/5_Model_Tuning.py", "Model tuning"),
    ("pages/6_Operations.py", "Operations"),
    ("pages/7_Scenario_Lab.py", "Scenario lab"),
)


@pytest.fixture
def isolated_ui_database(tmp_path, monkeypatch):
    database = tmp_path / "ui-regression.db"
    init_db(database)
    monkeypatch.setattr("src.data.database.DATABASE_PATH", database)
    monkeypatch.setattr("src.utils.config.DATABASE_PATH", database)
    monkeypatch.setattr("src.operations.DATABASE_PATH", database)
    monkeypatch.setattr("src.backup.DATABASE_PATH", database)
    return database


@pytest.mark.parametrize(("page", "expected_title"), PAGES)
def test_page_empty_state_has_no_streamlit_exception(
    isolated_ui_database: Path, page: str, expected_title: str,
):
    app = AppTest.from_file(page, default_timeout=20).run()
    assert not app.exception
    assert app.title and app.title[0].value == expected_title


def test_mobile_navigation_contract_remains_present():
    source = Path("src/ui.py").read_text(encoding="utf-8")
    assert "touchstart" in source and "touchend" in source
    assert "window.parent.innerWidth <= 700" in source
    assert "stSidebarCollapsedControl" in source


def test_navigation_and_simulation_contracts_are_regression_guarded():
    shell = Path("app.py").read_text(encoding="utf-8")
    for route in (
        "Decision-dashboard", "Portfolio", "Company", "Journal", "Watchlist",
        "Model-tuning", "Operations", "Scenario-lab",
    ):
        assert f'url_path="{route}"' in shell
    dashboard = Path("pages/1_Dashboard.py").read_text(encoding="utf-8")
    assert '"Present date", "Past date"' in dashboard
    assert "Run historical simulation" in dashboard
    assert "Saved simulations & learning history" in dashboard
    assert '"1D %": metrics.get("return_1d")' in dashboard
    # The model-lineage query is deliberately bulk-loaded once per render. A
    # per-ticker query adds several seconds after provider fetching completes.
    assert dashboard.count("get_backtest_runs()") == 1
    assert "backtest_runs_by_ticker" in dashboard
    tuning = Path("pages/5_Model_Tuning.py").read_text(encoding="utf-8")
    assert "How this page works · read in 30 seconds" in tuning
    assert '"Current live"' in tuning
    assert '"Active shadow"' in tuning
    assert '"Immediate rollback"' in tuning
    assert "Evidence pipeline" in tuning
    assert "Paired 3M benchmark-relative outcomes" in tuning
    assert "Both traces are present and overlap exactly" in tuning
    assert "Frozen promotion audit" in tuning
    assert "Experiments remain separate" in tuning
    assert "later-created " in tuning
    assert "historical simulations are excluded" in tuning


def test_responsive_breakpoint_contract_covers_phone_density():
    styles = Path("src/ui.py").read_text(encoding="utf-8")
    assert "@media (max-width: 700px)" in styles
    assert "@media (min-width: 1100px)" in styles
    assert "touch.clientX <= 34" in styles
    assert ".company-chart-legend" in styles


def test_portfolio_backup_and_profiles_do_not_bloat_normal_page_loads():
    portfolio = Path("pages/2_Portfolio.py").read_text(encoding="utf-8")
    assert "Prepare SQLite database backup" in portfolio
    assert "fetch_asset_profile" not in portfolio
    assert portfolio.index("st.button(\"Prepare SQLite database backup\"") < portfolio.index("DATABASE_PATH.read_bytes()")
    assert "overlay_extended_hours_prices" in portfolio
    assert "render_portfolio_extended_hours_status" in portfolio


def test_company_uses_compact_responsive_chart_legend():
    company = Path("pages/3_Company.py").read_text(encoding="utf-8")
    assert "showlegend=False" in company
    assert "company-chart-legend" in company
    assert "FINRA short Δ" in company and "Suggested pending" in company
    assert "Daily short flow" in company and "10D flow avg" in company
    assert 'hovermode="x unified"' in company
    assert "exact shared calendar axis" in company


def test_macos_launcher_is_idempotent_and_scoped_to_equity_radar():
    control = Path("scripts/macos/equity-radar-control.zsh").read_text(encoding="utf-8")
    launcher = Path("scripts/macos/EquityRadarLauncher.swift").read_text(encoding="utf-8")
    manifest = Path("scripts/macos/Info.plist").read_text(encoding="utf-8")
    builder = Path("scripts/macos/build-launcher.zsh").read_text(encoding="utf-8")
    assert "running_pid" in control and "is_equity_radar_pid" in control
    assert "hydrate_project_sources" in control
    assert "Project source files could not be made locally available" in control
    assert '"streamlit"' in control and '"app.py"' in control
    assert '/_stcore/health' in control
    assert 'Button("Stop everything"' in launcher and 'Button("Start everything"' in launcher
    assert 'keyboardShortcut(.defaultAction)' in launcher
    assert 'Quit normally from the app menu or press ⌘Q.' in launcher
    assert "LSUIElement" not in manifest
    assert 'PREVIOUS_APP="$BUILD_ROOT/' in builder
    assert "work/backups/launcher-" not in builder


def test_company_learning_diagnostic_colors_are_defined_before_rendering():
    company = Path("pages/3_Company.py").read_text(encoding="utf-8")
    for variable in ("learning_entry_color", "learning_exit_color"):
        assignment = company.index(f"{variable} =")
        rendering = company.index(f"color:{{{variable}}}")
        assert assignment < rendering


def test_scoring_explanations_match_live_feature_semantics():
    readme = Path("README.md").read_text(encoding="utf-8")
    company = Path("pages/3_Company.py").read_text(encoding="utf-8")
    assert "52-week high/low and drawdown remain visible market context but do not add Technical points" in readme
    assert "gives it 0% weight" in readme
    assert "industry-calibrated Entry uses volatility-only Risk resilience" in readme
    assert "Drawdown remains visible and contributes to Exit review" in company
    assert "60% Technical deterioration plus 40% full market-risk deterioration" in company


def test_historical_simulation_requires_explicit_confirmation(isolated_ui_database, monkeypatch):
    add_ticker("AAA", isolated_ui_database)
    index = pd.date_range("2025-01-01", periods=380, freq="D")
    history = pd.DataFrame({
        "Close": [100 + value * .1 for value in range(len(index))],
        "High": [101 + value * .1 for value in range(len(index))],
    }, index=index)
    monkeypatch.setattr("src.data.market_data.fetch_price_history", lambda *a, **k: history.copy())
    monkeypatch.setattr("src.data.market_data.get_price_history_fetched_at", lambda *a, **k: "2026-07-14T12:00:00")
    monkeypatch.setattr("src.data.fundamentals.get_fundamentals", lambda *a, **k: None)
    monkeypatch.setattr("src.data.industry_refresh.schedule_industry_refresh", lambda *a, **k: [])
    monkeypatch.setattr("src.data.positioning_refresh.schedule_finra_backfill", lambda *a, **k: [])
    monkeypatch.setattr("src.data.positioning_refresh.schedule_positioning_refresh", lambda *a, **k: [])
    monkeypatch.setattr("src.data.extended_hours_refresh.schedule_extended_hours_refresh", lambda *a, **k: [])
    monkeypatch.setattr("src.data.cutoff_suggestions.schedule_cutoff_suggestions", lambda *a, **k: False)
    monkeypatch.setattr("src.data.backtest_refresh.schedule_outcome_refresh", lambda *a, **k: False)
    scheduled = []
    monkeypatch.setattr(
        "src.data.backtest_refresh.schedule_backtest",
        lambda cutoff, tickers, **kwargs: scheduled.append((cutoff, tuple(tickers))) or [],
    )
    app = AppTest.from_file("pages/1_Dashboard.py", default_timeout=30).run()
    decision_mode = next(radio for radio in app.radio if radio.label == "Decision date")
    decision_mode.set_value("Past date").run()
    assert scheduled == []
    run_buttons = [button for button in app.button if button.label == "Run historical simulation"]
    assert len(run_buttons) == 1
    run_buttons[0].click().run()
    assert scheduled
