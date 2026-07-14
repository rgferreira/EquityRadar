"""Synthetic AppTest coverage for every user-facing page.

These tests deliberately use an empty temporary database: browser regression
coverage must never depend on or expose the user's local research data.
"""

from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

from src.data.database import init_db


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
