from datetime import datetime, timedelta

from src.data.dashboard_refresh import (
    DASHBOARD_AUTO_REFRESH_COOLDOWN,
    automatic_dashboard_refresh_due,
    last_dashboard_provider_refresh_at,
    record_dashboard_provider_refresh,
    reset_dashboard_refresh_cooldown,
)


def setup_function():
    reset_dashboard_refresh_cooldown()


def test_automatic_refresh_is_suppressed_inside_one_minute():
    started = datetime(2026, 7, 14, 12, 0, 0)
    record_dashboard_provider_refresh(started)

    assert last_dashboard_provider_refresh_at() == started
    assert automatic_dashboard_refresh_due(started + timedelta(seconds=59)) is False
    assert automatic_dashboard_refresh_due(started + DASHBOARD_AUTO_REFRESH_COOLDOWN) is True


def test_first_automatic_refresh_is_due():
    assert automatic_dashboard_refresh_due(datetime(2026, 7, 14, 12, 0, 0)) is True
