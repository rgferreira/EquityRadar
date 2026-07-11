import pytest

from src.data.database import get_cash_transactions, get_portfolio_holdings, get_portfolio_sales
from src.import_export import import_transactions_csv


def test_csv_import_handles_purchase_sale_and_cash_with_row_errors(tmp_path):
    database = tmp_path / "radar.db"
    content = """transaction_kind,date,ticker,shares,price_per_share,fees,cash_type,amount,currency,notes
purchase,2026-01-01,AAPL,5,100,1,,,,first buy
sale,2026-02-01,AAPL,2,120,1,,,,trim
cash,2026-02-02,AAPL,,,,dividend,10,USD,dividend
unknown,2026-02-03,,,,,,,,bad row
"""
    result = import_transactions_csv(content, database)
    assert result["imported"] == 3
    assert len(result["errors"]) == 1
    assert get_portfolio_holdings(database)[0]["shares"] == 3
    assert get_portfolio_sales(db_path=database)[0]["realized_pl"] == pytest.approx(38.6)
    assert get_cash_transactions(database)[0]["amount"] == 10


def test_csv_import_requires_transaction_kind_header(tmp_path):
    result = import_transactions_csv("date,ticker\n2026-01-01,AAPL\n", tmp_path / "radar.db")
    assert result["imported"] == 0
    assert "Missing required column" in result["errors"][0]
