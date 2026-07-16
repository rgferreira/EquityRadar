from datetime import datetime

from src.data.database import init_db, record_provider_health
from src.data.finra_daily_volume_refresh import (
    ONBOARDING_PROVIDER_KEY, finra_daily_volume_onboarding_due,
)


def test_global_daily_freshness_does_not_suppress_new_ticker_onboarding(tmp_path):
    database = tmp_path / "onboarding.db"
    current = datetime.now()
    init_db(database)
    record_provider_health(
        "finra_daily_volume", "__WATCHLIST__", "healthy", db_path=database,
    )

    assert finra_daily_volume_onboarding_due(
        ["TSLA"], database, now=current,
    ) == ["TSLA"]

    record_provider_health(
        ONBOARDING_PROVIDER_KEY, "TSLA", "healthy", db_path=database,
    )
    assert finra_daily_volume_onboarding_due(
        ["TSLA"], database, now=current,
    ) == []
