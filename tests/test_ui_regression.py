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
    ("pages/8_WhaleSeeker.py", "WhaleSeeker"),
    ("pages/3_Company.py", "Company detail"),
    ("pages/4_Journal.py", "Investment journal"),
    ("pages/0_Watchlist.py", "Watchlist management"),
    ("pages/5_Model_Tuning.py", "Model tuning"),
    ("pages/6_Operations.py", "Operations"),
    ("pages/7_Scenario_Lab.py", "Scenario lab"),
    ("pages/9_Research_Lab.py", "Entry research"),
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
        "Decision-dashboard", "Portfolio", "WhaleSeeker", "Company", "Journal", "Watchlist",
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
    assert portfolio.index("st.button(\"Prepare SQLite database backup\"") < portfolio.index("sqlite_backup_bytes(DATABASE_PATH)")
    assert "overlay_extended_hours_prices" in portfolio
    assert "render_portfolio_extended_hours_status" in portfolio


def test_company_uses_compact_responsive_chart_legend():
    company = Path("pages/3_Company.py").read_text(encoding="utf-8")
    assert "showlegend=False" in company
    assert "company-chart-legend" in company
    assert "FINRA short Δ" in company and "Suggested pending" in company
    assert "Daily short flow" in company and "10D flow avg" in company
    assert "BTC short accounts Δ" in company and "BTC taker-sell flow" in company
    assert "display-only, live-model weight 0.0" in company
    assert 'hovermode="x unified"' in company
    assert "exact shared calendar axis" in company


def test_whaleseeker_exposes_stale_and_unconfigured_provider_states():
    page = Path("pages/8_WhaleSeeker.py").read_text(encoding="utf-8")
    assert "Automatic WhaleSeeker refresh is unavailable" in page
    assert "more than 12 hours" in page
    assert "refresh automatically every six hours" in page


def test_dashboard_uses_persistent_snapshot_and_bounded_parallel_price_fetch():
    dashboard = Path("pages/1_Dashboard.py").read_text(encoding="utf-8")

    assert "get_dashboard_market_snapshot(tickers)" in dashboard
    assert "dashboard_snapshot_is_fresh" in dashboard
    assert '"Price observed at": latest_price_observed_at(history)' in dashboard
    assert 'fallback_row["Price data status"] = "Fallback after refresh failure"' in dashboard
    assert "if rows and not errors and len(rows) == len(tickers):" in dashboard
    assert "Stale-price warning" in dashboard
    assert "save_dashboard_market_snapshot(" in dashboard
    assert "ThreadPoolExecutor(max_workers=min(6, len(priority_tickers)))" in dashboard
    assert "as_completed(pending)" in dashboard
    assert "if ticker in previous_rows" in dashboard
    assert "Snapshot loaded · preparing" in dashboard
    assert "Market data ready · rendering" in dashboard
    assert 'if research_panel.open:' in dashboard
    assert 'startup_progress.progress(1.0, text=f"Dashboard ready' in dashboard
    assert "startup_progress.empty()" not in dashboard


def test_macos_launcher_is_idempotent_and_scoped_to_equity_radar():
    control = Path("scripts/macos/equity-radar-control.zsh").read_text(encoding="utf-8")
    launcher = Path("scripts/macos/EquityRadarLauncher.swift").read_text(encoding="utf-8")
    manifest = Path("scripts/macos/Info.plist").read_text(encoding="utf-8")
    builder = Path("scripts/macos/build-launcher.zsh").read_text(encoding="utf-8")
    project = Path("scripts/macos/EquityRadarLauncher.xcodeproj/project.pbxproj").read_text(
        encoding="utf-8"
    )
    icon = Path("scripts/macos/Resources/EquityRadar.icns")
    icon_master = Path("scripts/macos/Resources/EquityRadarIcon-Master.png")
    assert "running_pid" in control and "is_equity_radar_pid" in control
    assert "hydrate_project_sources" in control
    assert "Project source files could not be made locally available" in control
    assert 'SUPPORT_DIR="$HOME/Library/Application Support/EquityRadar"' in control
    assert 'RUNTIME_DIR="$SUPPORT_DIR/runtime"' in control
    assert 'VENV_DIR="$SUPPORT_DIR/venv-3.9"' in control
    assert 'PYTHON="$VENV_DIR/bin/python"' in control
    assert 'PYTHON_FORMULA="python@3.13"' in control
    assert "ensure_python_environment" in control
    assert 'HOMEBREW_NO_AUTO_UPDATE=1 "$brew" install "$PYTHON_FORMULA"' in control
    assert 'rollback="$SUPPORT_DIR/venv.rollback.' in control
    assert 'PID_FILE="$RUNTIME_DIR/equity-radar.pid"' in control
    assert 'LOG_FILE="$RUNTIME_DIR/streamlit.log"' in control
    assert 'SOURCE_STATE_FILE="$RUNTIME_DIR/source-state.sha256"' in control
    assert 'VERIFIED_PID_FILE="$RUNTIME_DIR/verified-dashboard.pid"' in control
    assert 'RUNTIME_APP="$RUNTIME_SOURCE_DIR/app.py"' in control
    assert "prepare_runtime_config" in control
    assert "prepare_runtime_source_copy" in control
    assert 'RUNTIME_SOURCE_NEXT="$RUNTIME_DIR/source.next"' in control
    assert 'RUNTIME_SOURCE_ROLLBACK="$RUNTIME_DIR/source.rollback"' in control
    assert '/usr/bin/ditto "$PROJECT_ROOT/pages" "$RUNTIME_SOURCE_NEXT/pages"' in control
    assert '/usr/bin/ditto "$PROJECT_ROOT/src" "$RUNTIME_SOURCE_NEXT/src"' in control
    assert '/bin/ln -sfn "$PROJECT_ROOT/pages"' not in control
    assert '/bin/ln -sfn "$PROJECT_ROOT/src"' not in control
    assert '"$PYTHON" "$RUNTIME_ACCEPTANCE"' in control
    assert "prepare_launch_agent" in control
    assert "source_revision" in control and "dashboard_ready" in control
    assert '"$verified_pid" == "$pid"' in control
    start_server = control.index("start_server()")
    assert control.index('if pid="$(running_pid)"; then', start_server) < control.index(
        "if ! hydrate_project_sources", start_server,
    )
    assert control.count('/usr/bin/open "$URL" >/dev/null 2>&1 </dev/null') == 2
    assert "--probe-route /" in control
    assert '--probe-expected "Decision dashboard"' in control
    assert "restart) restart_server" in control
    assert 'SERVICE_LABEL="com.rgferreira.equityradar.server"' in control
    assert '/bin/launchctl bootstrap "$SERVICE_DOMAIN" "$SERVICE_PLIST"' in control
    assert '/bin/launchctl bootout "$SERVICE_TARGET"' in control
    assert "<key>EQUITY_RADAR_DB_PATH</key>" in control
    assert '<string>$RUNTIME_DB</string>' in control
    assert 'source.backup(destination)' in control
    assert 'destination.execute("PRAGMA quick_check")' in control
    assert 'temporary_path.replace(destination_path)' in control
    assert '/bin/chmod 700 "$DATA_DIR"' in control
    assert '/bin/chmod 600 "$RUNTIME_DB"' in control
    assert "<key>Umask</key>" in control and "<integer>63</integer>" in control
    assert '"$PROJECT_ROOT/.streamlit"' not in control
    assert '"streamlit"' in control and '"app.py"' in control
    assert "<string>--server.address</string>" in control
    assert 'BIND_ADDRESS="$address"' in control
    assert "zerotier_address" in control
    assert "listener_on_zerotier_address" in control
    assert "<string>$BIND_ADDRESS</string>" in control
    assert '/_stcore/health' in control
    assert 'Button("Stop everything"' in launcher and 'Button("Start everything"' in launcher
    assert '@AppStorage("startServerOnLaunch")' in launcher
    assert 'Toggle("Start server on launch"' in launcher
    assert "startServerOnLaunch = true" in launcher
    assert "beginAutomaticStart()" in launcher
    assert 'executeControl("start")' in launcher
    assert "while !Task.isCancelled" in launcher
    assert "retryDelaySeconds = min(retryDelaySeconds * 2, 30)" in launcher
    assert "cancelAutomaticStart(" in launcher
    assert 'keyboardShortcut(.defaultAction)' in launcher
    assert 'Quit normally from the app menu or press ⌘Q.' in launcher
    assert "import AppKit" in launcher
    assert "import Darwin" in launcher
    assert 'forResource: "EquityRadar"' in launcher
    assert "NSApplication.shared.applicationIconImage = icon" in launcher
    assert "EquityRadarApplicationGuard.shared.acquire()" in launcher
    assert 'appendingPathComponent("equity-radar-ui.lock"' in launcher
    assert "Darwin.lockf(descriptor, F_TLOCK, 0)" in launcher
    assert launcher.count("activateCanonicalInstance()") >= 4
    assert 'withBundleIdentifier: self.bundleIdentifier' in launcher
    assert 'WindowGroup("Equity Radar")' not in launcher
    assert launcher.count('Window("Equity Radar", id: "equity-radar-main")') == 1
    assert "LSUIElement" not in manifest
    assert "<key>LSMultipleInstancesProhibited</key>\n    <true/>" in manifest
    assert "<key>CFBundleIconFile</key>\n    <string>EquityRadar</string>" in manifest
    assert "NSDocumentsFolderUsageDescription" in manifest
    assert icon.read_bytes()[:4] == b"icns"
    assert icon_master.read_bytes()[:8] == b"\x89PNG\r\n\x1a\n"
    assert "EquityRadar.icns in Resources" in project
    assert 'PREVIOUS_APP="$BUILD_ROOT/' in builder
    assert 'DEFAULT_DESTINATION="$HOME/Applications/Equity Radar.app"' in builder
    assert 'DESKTOP_LINK="$HOME/Desktop/Equity Radar.app"' in builder
    assert '/bin/ln -s "$DESTINATION" "$DESKTOP_LINK"' in builder
    assert "work/backups/launcher-" not in builder
    assert "Full Xcode unavailable; rebuilt and locally signed the native launcher." in builder
    widget_support = Path("scripts/macos/EquityRadarWidgetSupport.swift").read_text(
        encoding="utf-8"
    )
    assert 'process.executableURL = URL(fileURLWithPath: "/bin/zsh")' in widget_support
    assert "materializedEquityRadarControlScript" in widget_support
    assert "verifyEquityRadarProjectAccess" in widget_support
    assert 'if action == "start"' in widget_support
    assert '"$SOURCE_DIR/EquityRadarLauncher.swift"' in builder
    assert '"$SOURCE_DIR/EquityRadarWidgetSupport.swift"' in builder
    assert '"$SOURCE_DIR/Info.plist" "$PATCHED_APP/Contents/Info.plist"' in builder
    assert '"$SOURCE_DIR/Resources/EquityRadar.icns"' in builder
    assert 'LAUNCH_SERVICES_REGISTER=' in builder
    assert '"$LAUNCH_SERVICES_REGISTER" -f "$DESTINATION"' in builder
    assert "-target arm64-apple-macosx26.0" in builder
    assert '/usr/bin/codesign --verify --deep --strict "$DESTINATION"' in builder
    assert '/usr/bin/codesign --force --sign - "$PATCHED_APP"' in builder
    assert "amfid" in builder and "unprovisioned" in builder


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
