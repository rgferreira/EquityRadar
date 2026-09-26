from scripts import run_ui_acceptance


class HealthResponse:
    def __enter__(self):
        return self

    def __exit__(self, *args):
        return None

    def read(self):
        return b"ok"


def test_route_probe_requires_expected_content_without_streamlit_error(monkeypatch):
    monkeypatch.setattr(run_ui_acceptance, "urlopen", lambda *args, **kwargs: HealthResponse())
    monkeypatch.setattr(run_ui_acceptance, "find_chromium", lambda: "chromium")
    monkeypatch.setattr(
        run_ui_acceptance, "render",
        lambda *args, **kwargs: "Decision dashboard\nResearch only",
    )

    result = run_ui_acceptance.probe_route("http://127.0.0.1:8501")

    assert result["passed"] is True
    assert result["errors"] == []


def test_route_probe_rejects_streamlit_error_even_if_heading_is_present(monkeypatch):
    monkeypatch.setattr(run_ui_acceptance, "urlopen", lambda *args, **kwargs: HealthResponse())
    monkeypatch.setattr(run_ui_acceptance, "find_chromium", lambda: "chromium")
    monkeypatch.setattr(
        run_ui_acceptance, "render",
        lambda *args, **kwargs: "Decision dashboard\nTraceback (most recent call last)",
    )

    result = run_ui_acceptance.probe_route("http://127.0.0.1:8501")

    assert result["passed"] is False
    assert result["errors"] == ["Traceback (most recent call last)"]


def test_route_probe_rejects_database_lock_even_if_dashboard_heading_is_present(monkeypatch):
    monkeypatch.setattr(run_ui_acceptance, "urlopen", lambda *args, **kwargs: HealthResponse())
    monkeypatch.setattr(run_ui_acceptance, "find_chromium", lambda: "chromium")
    monkeypatch.setattr(
        run_ui_acceptance, "render",
        lambda *args, **kwargs: "Market command center\nsqlite3.OperationalError: database is locked",
    )

    result = run_ui_acceptance.probe_route(
        "http://127.0.0.1:8501", expected="Market command center",
    )

    assert result["passed"] is False
    assert result["errors"] == ["OperationalError"]


def test_render_completion_waits_for_streamlit_script_to_finish():
    running = {
        "html": "Market command center",
        "state": "running",
    }
    finished = {
        "html": "Market command center",
        "state": "notRunning",
    }

    assert run_ui_acceptance._render_is_complete(running, "Market command center") is False
    assert run_ui_acceptance._render_is_complete(finished, "Market command center") is True


def test_render_completion_returns_a_running_streamlit_error_for_rejection():
    failed = {
        "html": "Market command center\nsqlite3.OperationalError: database is locked",
        "state": "running",
    }

    assert run_ui_acceptance._render_is_complete(failed, "Market command center") is True


def test_render_probe_reads_main_content_instead_of_sidebar_navigation():
    source = run_ui_acceptance.Path(run_ui_acceptance.__file__).read_text(encoding="utf-8")

    assert "stMainBlockContainer" in source
    assert "html: document.body.innerText" not in source
