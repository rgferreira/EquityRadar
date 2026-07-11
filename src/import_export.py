"""CSV transaction import for portfolio purchases, sales, and cash movements."""

import csv
from io import StringIO
from pathlib import Path

from src.data.database import add_cash_transaction, add_portfolio_lot, record_portfolio_sale


def import_transactions_csv(content: str, db_path: str | Path | None = None) -> dict[str, object]:
    reader = csv.DictReader(StringIO(content))
    imported, errors = 0, []
    required_header = "transaction_kind"
    if not reader.fieldnames or required_header not in reader.fieldnames:
        return {"imported": 0, "errors": [f"Missing required column: {required_header}"]}
    for row_number, row in enumerate(reader, start=2):
        try:
            kind = (row.get("transaction_kind") or "").strip().lower()
            if kind == "purchase":
                add_portfolio_lot({
                    "ticker": row.get("ticker"), "purchase_date": row.get("date"),
                    "shares": row.get("shares"), "price_per_share": row.get("price_per_share"),
                    "fees": row.get("fees") or 0, "notes": row.get("notes"),
                }, db_path)
            elif kind == "sale":
                record_portfolio_sale({
                    "ticker": row.get("ticker"), "sale_date": row.get("date"),
                    "shares": row.get("shares"), "price_per_share": row.get("price_per_share"),
                    "fees": row.get("fees") or 0, "notes": row.get("notes"),
                }, db_path)
            elif kind == "cash":
                add_cash_transaction({
                    "transaction_date": row.get("date"), "transaction_type": row.get("cash_type"),
                    "amount": row.get("amount"), "currency": row.get("currency"),
                    "ticker": row.get("ticker"), "notes": row.get("notes"),
                }, db_path)
            else:
                raise ValueError(f"Unsupported transaction_kind: {kind or '(empty)'}")
            imported += 1
        except Exception as exc:
            errors.append(f"Row {row_number}: {exc}")
    return {"imported": imported, "errors": errors}


CSV_TEMPLATE = "transaction_kind,date,ticker,shares,price_per_share,fees,cash_type,amount,currency,notes\n"
