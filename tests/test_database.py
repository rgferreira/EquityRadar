import pytest

from src.data.database import (
    add_journal_entry,
    add_ticker,
    get_journal_entries,
    get_portfolio_holdings,
    get_watchlist,
    remove_ticker,
    set_portfolio_holding,
    save_fundamentals,
    get_cached_fundamentals,
    update_journal_entry,
    delete_journal_entry,
    add_portfolio_lot,
    get_portfolio_lots,
    update_portfolio_lot,
    delete_portfolio_lot,
    record_portfolio_sale,
    get_portfolio_sales,
    save_portfolio_snapshot,
    get_portfolio_snapshots,
    add_cash_transaction,
    get_cash_transactions,
    delete_cash_transaction,
    set_portfolio_target,
    get_portfolio_targets,
    get_dashboard_order,
    save_dashboard_order,
    get_active_backtest,
    save_active_backtest,
)


def test_decision_dashboard_order_persists_across_sessions(tmp_path):
    database = tmp_path / "radar.db"
    save_dashboard_order(["NVDA", "GOOG", "AAPL"], database)
    assert get_dashboard_order(database) == ["NVDA", "GOOG", "AAPL"]


def test_active_backtest_date_persists_and_clears(tmp_path):
    database = tmp_path / "radar.db"
    save_active_backtest("2026-05-08", database)
    assert get_active_backtest(database) == "2026-05-08"
    save_active_backtest(None, database)
    assert get_active_backtest(database) is None


def test_watchlist_add_and_remove(tmp_path):
    database = tmp_path / "radar.db"
    add_ticker("aapl", database)
    add_ticker("AAPL", database)
    assert get_watchlist(database) == ["AAPL"]
    remove_ticker("aapl", database)
    assert get_watchlist(database) == []


def test_journal_entries_are_returned_newest_first(tmp_path):
    database = tmp_path / "radar.db"
    base = {"ticker": "MSFT", "action": "watch", "conviction": 3}
    add_journal_entry({**base, "entry_date": "2025-01-01"}, database)
    add_journal_entry({**base, "entry_date": "2025-02-01", "thesis": "Improving margins"}, database)
    entries = get_journal_entries("MSFT", database)
    assert [entry["entry_date"] for entry in entries] == ["2025-02-01", "2025-01-01"]
    assert entries[0]["thesis"] == "Improving margins"


def test_journal_entry_can_be_updated_and_deleted(tmp_path):
    database = tmp_path / "radar.db"
    original = {"ticker": "MSFT", "entry_date": "2025-01-01", "action": "watch", "conviction": 3}
    add_journal_entry(original, database)
    entry_id = get_journal_entries(db_path=database)[0]["id"]
    updated = {
        **original, "action": "buy_candidate", "conviction": 5,
        "target_price": 500, "thesis": "Updated thesis",
    }
    update_journal_entry(entry_id, updated, database)
    entry = get_journal_entries(db_path=database)[0]
    assert entry["action"] == "buy_candidate"
    assert entry["target_price"] == 500
    delete_journal_entry(entry_id, database)
    assert get_journal_entries(db_path=database) == []


def test_portfolio_holding_adds_watchlist_ticker_and_blocks_removal(tmp_path):
    database = tmp_path / "radar.db"
    set_portfolio_holding("nvda", owned=True, shares=12, db_path=database)

    assert get_watchlist(database) == ["NVDA"]
    holdings = get_portfolio_holdings(database)
    assert len(holdings) == 1
    assert holdings[0]["ticker"] == "NVDA"
    assert holdings[0]["shares"] == 12.0
    with pytest.raises(ValueError, match="Mark it as not owned first"):
        remove_ticker("NVDA", database)

    set_portfolio_holding("NVDA", owned=False, db_path=database)
    remove_ticker("NVDA", database)
    assert get_watchlist(database) == []


def test_portfolio_lots_aggregate_into_holdings_and_support_crud(tmp_path):
    database = tmp_path / "radar.db"
    first_id = add_portfolio_lot({
        "ticker": "aapl", "purchase_date": "2026-01-10", "shares": 2,
        "price_per_share": 100, "fees": 1,
    }, database)
    second_id = add_portfolio_lot({
        "ticker": "AAPL", "purchase_date": "2026-02-10", "shares": 3,
        "price_per_share": 110, "fees": 2,
    }, database)
    assert get_portfolio_holdings(database)[0]["shares"] == 5
    lots = get_portfolio_lots("AAPL", database)
    assert {lot["id"] for lot in lots} == {first_id, second_id}

    update_portfolio_lot(first_id, {
        "ticker": "AAPL", "purchase_date": "2026-01-11", "shares": 4,
        "price_per_share": 101, "fees": 1.5, "notes": "corrected",
    }, database)
    assert get_portfolio_holdings(database)[0]["shares"] == 7
    assert next(lot for lot in get_portfolio_lots("AAPL", database) if lot["id"] == first_id)["notes"] == "corrected"

    delete_portfolio_lot(second_id, database)
    assert get_portfolio_holdings(database)[0]["shares"] == 4


def test_existing_aggregate_holding_is_migrated_to_legacy_lot(tmp_path):
    database = tmp_path / "radar.db"
    set_portfolio_holding("NVDA", owned=True, shares=12, db_path=database)
    lots = get_portfolio_lots("NVDA", database)
    assert len(lots) == 1
    assert lots[0]["source"] == "legacy"
    assert lots[0]["purchase_date"] is None
    assert lots[0]["price_per_share"] is None


def test_portfolio_sale_consumes_fifo_lots_and_calculates_realized_pl(tmp_path):
    database = tmp_path / "radar.db"
    add_portfolio_lot({
        "ticker": "AAPL", "purchase_date": "2026-01-01", "shares": 2,
        "price_per_share": 100, "fees": 2,
    }, database)
    add_portfolio_lot({
        "ticker": "AAPL", "purchase_date": "2026-02-01", "shares": 3,
        "price_per_share": 120, "fees": 3,
    }, database)
    sale_id = record_portfolio_sale({
        "ticker": "AAPL", "sale_date": "2026-03-01", "shares": 3,
        "price_per_share": 150, "fees": 3,
    }, database)
    sale = get_portfolio_sales("AAPL", database)[0]
    assert sale["id"] == sale_id
    assert sale["cost_basis"] == pytest.approx(323)  # first lot 202 + one share of second lot 121
    assert sale["realized_pl"] == pytest.approx(124)  # proceeds 447 less cost 323
    assert get_portfolio_holdings(database)[0]["shares"] == 2
    remaining = get_portfolio_lots("AAPL", database)
    assert len(remaining) == 1
    assert remaining[0]["shares"] == 2
    assert remaining[0]["fees"] == pytest.approx(2)


def test_sale_of_unknown_legacy_cost_keeps_realized_pl_unknown(tmp_path):
    database = tmp_path / "radar.db"
    set_portfolio_holding("NVDA", owned=True, shares=2, db_path=database)
    record_portfolio_sale({
        "ticker": "NVDA", "sale_date": "2026-03-01", "shares": 1,
        "price_per_share": 150, "fees": 1,
    }, database)
    sale = get_portfolio_sales("NVDA", database)[0]
    assert sale["cost_basis"] is None
    assert sale["realized_pl"] is None


def test_daily_portfolio_snapshot_upserts_same_date(tmp_path):
    database = tmp_path / "radar.db"
    save_portfolio_snapshot("2026-07-11", 1000, 2, 2, "EUR", database)
    save_portfolio_snapshot("2026-07-11", 1050, 2, 2, "EUR", database)
    save_portfolio_snapshot("2026-07-12", 1075, 2, 3, "EUR", database)
    snapshots = get_portfolio_snapshots(database)
    assert [row["snapshot_date"] for row in snapshots] == ["2026-07-11", "2026-07-12"]
    assert snapshots[0]["total_value"] == 1050
    assert snapshots[0]["base_currency"] == "EUR"
    assert snapshots[1]["priced_positions"] == 2


def test_cash_ledger_normalizes_inflow_and_outflow_signs(tmp_path):
    database = tmp_path / "radar.db"
    deposit_id = add_cash_transaction({
        "transaction_date": "2026-07-01", "transaction_type": "deposit",
        "amount": -1000, "currency": "usd",
    }, database)
    tax_id = add_cash_transaction({
        "transaction_date": "2026-07-02", "transaction_type": "withholding_tax",
        "amount": 15, "currency": "USD", "ticker": "AAPL",
    }, database)
    transactions = get_cash_transactions(database)
    assert [item["amount"] for item in transactions] == [-15, 1000]
    assert transactions[0]["ticker"] == "AAPL"
    delete_cash_transaction(tax_id, database)
    assert [item["id"] for item in get_cash_transactions(database)] == [deposit_id]


def test_portfolio_targets_are_upserted(tmp_path):
    database = tmp_path / "radar.db"
    set_portfolio_target("aapl", 40, database)
    set_portfolio_target("AAPL", 45, database)
    assert get_portfolio_targets(database)[0]["target_weight_pct"] == 45


def test_fundamentals_migration_and_cache_round_trip(tmp_path):
    database = tmp_path / "radar.db"
    payload = {
        "ticker": "AAPL", "trailing_pe": 20.5, "forward_pe": None,
        "price_to_sales_ttm": 4.2, "revenue_growth": 0.1, "eps_growth": 0.15,
        "reporting_date": "2026-06-30", "provider_name": "FMP",
        "fetched_at": "2026-07-10T10:00:00",
    }
    save_fundamentals(payload, database)
    cached = get_cached_fundamentals("aapl", database)
    assert cached is not None
    assert cached["trailing_pe"] == 20.5
    assert cached["forward_pe"] is None
