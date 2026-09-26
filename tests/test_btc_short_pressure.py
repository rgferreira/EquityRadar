from datetime import date, timedelta

from src.scoring.btc_short_pressure import btc_short_pressure_evidence
from src.shadow_model import technology_potential_shadow_output


def _rows(*, selling_rises: bool, count: int = 90) -> list[dict[str, object]]:
    start = date(2026, 5, 27)
    rows = []
    for index in range(count):
        recent = max(0, index - (count - 11))
        sell = 95 + recent * 2 if selling_rises else 115 - recent * 2
        rows.append({
            "id": index + 1, "period_date": (start + timedelta(days=index)).isoformat(),
            "taker_buy_volume": 100.0, "taker_sell_volume": float(sell),
            "short_account_pct": 40.0 + max(0, index - (count - 11)) * 0.12,
            "open_interest_value_quote": 1_000.0 + index * 5,
            "known_at": "2026-08-25T08:00:00+00:00",
            "known_at_status": "verified_observed",
        })
    return rows


def test_btc_crowding_plus_seller_exhaustion_is_entry_positive() -> None:
    evidence = btc_short_pressure_evidence(_rows(selling_rises=False), as_of=date(2026, 8, 25))

    assert evidence["state"] == "Squeeze potential"
    assert evidence["entry_modifier"] > 0
    assert evidence["exit_modifier"] < 0
    assert evidence["included_in_shadow"] is True


def test_btc_crowding_plus_active_selling_is_entry_negative() -> None:
    evidence = btc_short_pressure_evidence(_rows(selling_rises=True), as_of=date(2026, 8, 25))

    assert evidence["state"] == "Downside short pressure"
    assert evidence["entry_modifier"] < 0
    assert evidence["exit_modifier"] > 0


def test_btc_evidence_excludes_cutoff_period_and_unverified_rows() -> None:
    rows = _rows(selling_rises=False)
    rows.append({**rows[-1], "id": 999, "period_date": "2026-08-25", "short_account_pct": 99.0})
    rows.append({**rows[-1], "id": 1000, "period_date": "2026-08-24", "known_at_status": "unverified"})

    evidence = btc_short_pressure_evidence(rows, as_of=date(2026, 8, 25))

    assert evidence["latest_period_date"] == "2026-08-24"
    assert evidence["short_account_pct"] < 50


def test_unified_shadow_applies_btc_adapter_without_changing_official_outputs() -> None:
    evidence = btc_short_pressure_evidence(_rows(selling_rises=False), as_of=date(2026, 8, 25))
    official = {"entry_score": 68.0, "entry_signal": "Watch", "exit_score": 42.0, "exit_signal": "Hold"}

    shadow = technology_potential_shadow_output(
        {"technology_potential": {}, "daily_short_flow": {}, "btc_short_pressure": evidence},
        official,
    )

    assert shadow["shorts_adapter"] == "binance_btc_perpetual"
    assert shadow["shorts_entry_modifier"] == evidence["entry_modifier"]
    assert shadow["entry_score"] > official["entry_score"]
    assert official == {"entry_score": 68.0, "entry_signal": "Watch", "exit_score": 42.0, "exit_signal": "Hold"}
