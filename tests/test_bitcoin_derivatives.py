import csv
from datetime import date, datetime, timedelta, timezone
from io import BytesIO, StringIO
from zipfile import ZIP_DEFLATED, ZipFile

from src.data.bitcoin_derivatives import (
    BinanceBitcoinDerivativesProvider,
    BinanceBitcoinDerivativesArchiveProvider,
    bitcoin_derivatives_refresh_due,
)
from src.data.database import (
    get_bitcoin_derivatives_daily_observations,
    save_bitcoin_derivatives_daily_observations,
)


def _timestamp_ms(value: str) -> int:
    return int(datetime.fromisoformat(value).replace(tzinfo=timezone.utc).timestamp() * 1000)


def _provider() -> tuple[BinanceBitcoinDerivativesProvider, list[str]]:
    requested: list[str] = []
    taker_start = _timestamp_ms("2026-08-20T00:00:00")
    period_end = _timestamp_ms("2026-08-21T00:00:00")

    def requester(url: str) -> object:
        requested.append(url)
        if "takerlongshortRatio" in url:
            return [{
                "buySellRatio": "1.5", "buyVol": "150", "sellVol": "100",
                "timestamp": taker_start,
            }]
        if "globalLongShortAccountRatio" in url:
            return [{
                "longShortRatio": "1.5", "longAccount": "0.6", "shortAccount": "0.4",
                "timestamp": period_end,
            }]
        if "openInterestHist" in url:
            return [{
                "sumOpenInterest": "50000", "sumOpenInterestValue": "3000000000",
                "timestamp": period_end,
            }]
        raise AssertionError("Unexpected endpoint")

    return BinanceBitcoinDerivativesProvider(requester=requester), requested


def test_binance_provider_aligns_start_and_end_timestamps() -> None:
    provider, requested = _provider()

    rows = provider.fetch_daily(
        limit=1, fetched_at=datetime(2026, 8, 21, 8, 30, tzinfo=timezone.utc),
    )

    assert len(rows) == 1
    assert len(requested) == 3
    assert all("symbol=BTCUSDT" in url and "period=1d" in url and "limit=1" in url for url in requested)
    assert rows[0]["period_date"] == "2026-08-20"
    assert rows[0]["taker_buy_volume"] == 150
    assert rows[0]["taker_sell_volume"] == 100
    assert rows[0]["long_account_pct"] == 60
    assert rows[0]["short_account_pct"] == 40
    assert rows[0]["open_interest_value_quote"] == 3_000_000_000
    assert rows[0]["fetched_at"] == "2026-08-21T08:30:00+00:00"
    assert len(str(rows[0]["payload_hash"])) == 64


def test_bitcoin_derivatives_persistence_is_immutable_and_returns_latest_revision(tmp_path) -> None:
    database = tmp_path / "bitcoin-derivatives.db"
    provider, _ = _provider()
    first = provider.fetch_daily(
        limit=1, fetched_at=datetime(2026, 8, 21, 8, 30, tzinfo=timezone.utc),
    )

    assert save_bitcoin_derivatives_daily_observations(first, db_path=database) == 1
    assert save_bitcoin_derivatives_daily_observations(first, db_path=database) == 0

    revised = [{
        **first[0],
        "taker_sell_volume": 110,
        "payload_hash": "a" * 64,
        "fetched_at": "2026-08-21T09:30:00+00:00",
    }]
    assert save_bitcoin_derivatives_daily_observations(revised, db_path=database) == 1

    latest = get_bitcoin_derivatives_daily_observations(db_path=database)
    assert len(latest) == 1
    assert latest[0]["taker_sell_volume"] == 110
    assert latest[0]["known_at"] == "2026-08-21T09:30:00+00:00"
    assert latest[0]["known_at_status"] == "verified_observed"


def test_bitcoin_derivatives_refresh_is_due_only_once_per_utc_day(tmp_path) -> None:
    database = tmp_path / "bitcoin-derivatives-due.db"
    provider, _ = _provider()
    template = provider.fetch_daily(
        limit=1, fetched_at=datetime(2026, 8, 21, 8, 30, tzinfo=timezone.utc),
    )
    start = date(2025, 8, 22)
    rows = [{
        **template[0],
        "period_date": (start + timedelta(days=offset)).isoformat(),
        "payload_hash": f"{offset:064x}",
    } for offset in range(365)]
    save_bitcoin_derivatives_daily_observations(rows, db_path=database)

    assert bitcoin_derivatives_refresh_due(
        database, now=datetime(2026, 8, 21, 23, 0, tzinfo=timezone.utc),
    ) is False
    assert bitcoin_derivatives_refresh_due(
        database, now=datetime(2026, 8, 22, 0, 1, tzinfo=timezone.utc),
    ) is True


def _metrics_zip(period_date: str) -> bytes:
    output = StringIO()
    writer = csv.DictWriter(output, fieldnames=[
        "create_time", "symbol", "sum_open_interest", "sum_open_interest_value",
        "count_toptrader_long_short_ratio", "sum_toptrader_long_short_ratio",
        "count_long_short_ratio", "sum_taker_long_short_vol_ratio",
    ])
    writer.writeheader()
    writer.writerow({
        "create_time": f"{period_date} 23:55:00", "symbol": "BTCUSDT",
        "sum_open_interest": "100", "sum_open_interest_value": "3000000000",
        "count_toptrader_long_short_ratio": "1.1", "sum_toptrader_long_short_ratio": "1.2",
        "count_long_short_ratio": "1.5", "sum_taker_long_short_vol_ratio": "0.9",
    })
    writer.writerow({
        "create_time": f"{period_date} 00:05:00", "symbol": "BTCUSDT",
        "sum_open_interest": "90", "sum_open_interest_value": "2500000000",
        "count_toptrader_long_short_ratio": "1.0", "sum_toptrader_long_short_ratio": "1.1",
        "count_long_short_ratio": "1.0", "sum_taker_long_short_vol_ratio": "1.0",
    })
    body = BytesIO()
    with ZipFile(body, "w", ZIP_DEFLATED) as archive:
        archive.writestr(f"BTCUSDT-metrics-{period_date}.csv", output.getvalue())
    return body.getvalue()


def test_archive_provider_uses_daily_close_metrics_and_exact_kline_taker_volume() -> None:
    period_date = "2025-08-26"
    open_timestamp = _timestamp_ms(f"{period_date}T00:00:00")
    provider = BinanceBitcoinDerivativesArchiveProvider(
        archive_requester=lambda url: _metrics_zip(period_date),
        json_requester=lambda url: [[
            open_timestamp, "100", "110", "90", "105", "1000", open_timestamp + 86_399_999,
            "100000", 100, "400", "40000", "0",
        ]],
        max_workers=1,
    )

    rows = provider.fetch_range(
        date.fromisoformat(period_date), date.fromisoformat(period_date),
        fetched_at=datetime(2026, 8, 25, 10, 0, tzinfo=timezone.utc),
    )

    assert len(rows) == 1
    assert rows[0]["period_date"] == period_date
    assert rows[0]["long_account_pct"] == 60
    assert rows[0]["short_account_pct"] == 40
    assert rows[0]["taker_buy_volume"] == 400
    assert rows[0]["taker_sell_volume"] == 600
    assert rows[0]["open_interest_value_quote"] == 3_000_000_000
    assert rows[0]["payload"]["metrics_close"]["create_time"].endswith("23:55:00")
