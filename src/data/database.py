"""SQLite persistence for watchlist and investment journal."""

import sqlite3
import json
from collections.abc import Mapping
from pathlib import Path

from src.utils.config import DATABASE_PATH


def get_connection(db_path: str | Path | None = None) -> sqlite3.Connection:
    connection = sqlite3.connect(db_path or DATABASE_PATH)
    connection.row_factory = sqlite3.Row
    return connection


def init_db(db_path: str | Path | None = None) -> None:
    with get_connection(db_path) as connection:
        connection.executescript("""
            CREATE TABLE IF NOT EXISTS watchlist (
                ticker TEXT PRIMARY KEY,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS portfolio_holdings (
                ticker TEXT PRIMARY KEY,
                shares REAL NOT NULL CHECK(shares >= 0),
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (ticker) REFERENCES watchlist(ticker)
            );
            CREATE TABLE IF NOT EXISTS journal_entries (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ticker TEXT NOT NULL,
                entry_date TEXT NOT NULL,
                action TEXT NOT NULL CHECK(action IN ('watch', 'buy_candidate', 'reject', 'sell_review')),
                thesis TEXT,
                catalyst TEXT,
                main_risk TEXT,
                invalidation_condition TEXT,
                target_price REAL,
                time_horizon TEXT,
                conviction INTEGER NOT NULL CHECK(conviction BETWEEN 1 AND 5),
                notes TEXT,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS fundamentals_cache (
                ticker TEXT PRIMARY KEY,
                trailing_pe REAL,
                forward_pe REAL,
                price_to_sales_ttm REAL,
                revenue_growth REAL,
                eps_growth REAL,
                reporting_date TEXT,
                provider_name TEXT NOT NULL,
                fetched_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS industry_research_cache (
                ticker TEXT PRIMARY KEY,
                payload_json TEXT NOT NULL,
                provider_name TEXT NOT NULL,
                fetched_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS positioning_cache (
                ticker TEXT PRIMARY KEY,
                payload_json TEXT NOT NULL,
                provider_name TEXT NOT NULL,
                reporting_date TEXT,
                fetched_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS positioning_history (
                ticker TEXT NOT NULL,
                snapshot_date TEXT NOT NULL,
                payload_json TEXT NOT NULL,
                provider_name TEXT NOT NULL,
                reporting_date TEXT,
                fetched_at TEXT NOT NULL,
                PRIMARY KEY (ticker, snapshot_date)
            );
            CREATE TABLE IF NOT EXISTS portfolio_lots (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ticker TEXT NOT NULL,
                purchase_date TEXT,
                shares REAL NOT NULL CHECK(shares > 0),
                price_per_share REAL CHECK(price_per_share > 0),
                fees REAL NOT NULL DEFAULT 0 CHECK(fees >= 0),
                source TEXT NOT NULL DEFAULT 'manual',
                notes TEXT,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (ticker) REFERENCES watchlist(ticker)
            );
            CREATE TABLE IF NOT EXISTS portfolio_sales (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ticker TEXT NOT NULL,
                sale_date TEXT NOT NULL,
                shares REAL NOT NULL CHECK(shares > 0),
                price_per_share REAL NOT NULL CHECK(price_per_share > 0),
                fees REAL NOT NULL DEFAULT 0 CHECK(fees >= 0),
                cost_basis REAL,
                realized_pl REAL,
                notes TEXT,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (ticker) REFERENCES watchlist(ticker)
            );
            CREATE TABLE IF NOT EXISTS portfolio_snapshots (
                snapshot_date TEXT PRIMARY KEY,
                total_value REAL NOT NULL CHECK(total_value >= 0),
                base_currency TEXT NOT NULL DEFAULT 'USD',
                priced_positions INTEGER NOT NULL CHECK(priced_positions >= 0),
                total_positions INTEGER NOT NULL CHECK(total_positions >= 0),
                captured_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS cash_transactions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                transaction_date TEXT NOT NULL,
                transaction_type TEXT NOT NULL CHECK(transaction_type IN ('deposit','withdrawal','dividend','withholding_tax','fee','adjustment')),
                amount REAL NOT NULL,
                currency TEXT NOT NULL,
                ticker TEXT,
                notes TEXT,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS portfolio_targets (
                ticker TEXT PRIMARY KEY,
                target_weight_pct REAL NOT NULL CHECK(target_weight_pct >= 0 AND target_weight_pct <= 100),
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (ticker) REFERENCES watchlist(ticker)
            );
            CREATE TABLE IF NOT EXISTS schema_migrations (
                migration_key TEXT PRIMARY KEY,
                applied_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS ui_preferences (
                preference_key TEXT PRIMARY KEY,
                value_json TEXT NOT NULL,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS backtest_runs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ticker TEXT NOT NULL,
                as_of_date TEXT NOT NULL,
                coverage TEXT NOT NULL,
                entry_score REAL NOT NULL,
                exit_score REAL NOT NULL,
                entry_signal TEXT NOT NULL,
                exit_signal TEXT NOT NULL,
                technical_score REAL NOT NULL,
                valuation_score REAL NOT NULL,
                risk_score REAL NOT NULL,
                outcome_1m REAL,
                outcome_3m REAL,
                outcome_6m REAL,
                outcome_12m REAL,
                inputs_json TEXT NOT NULL,
                model_version TEXT NOT NULL,
                outcome_refreshed_at TEXT,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(ticker, as_of_date, model_version)
            );
            CREATE TABLE IF NOT EXISTS backtest_job_items (
                as_of_date TEXT NOT NULL,
                ticker TEXT NOT NULL,
                status TEXT NOT NULL CHECK(status IN ('queued','running','completed','failed')),
                error TEXT,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY(as_of_date, ticker)
            );
        """)
        snapshot_columns = {
            row["name"] for row in connection.execute("PRAGMA table_info(portfolio_snapshots)")
        }
        if "base_currency" not in snapshot_columns:
            connection.execute(
                "ALTER TABLE portfolio_snapshots ADD COLUMN base_currency TEXT NOT NULL DEFAULT 'USD'"
            )
        backtest_columns = {
            row["name"] for row in connection.execute("PRAGMA table_info(backtest_runs)")
        }
        if "outcome_refreshed_at" not in backtest_columns:
            connection.execute("ALTER TABLE backtest_runs ADD COLUMN outcome_refreshed_at TEXT")
        migrated = connection.execute(
            "SELECT 1 FROM schema_migrations WHERE migration_key = 'portfolio_holdings_to_lots_v1'"
        ).fetchone()
        if not migrated:
            connection.execute(
                """
                INSERT INTO portfolio_lots (ticker, shares, source, notes)
                SELECT ticker, shares, 'legacy', 'Migrated from aggregate holding; purchase details unknown'
                FROM portfolio_holdings WHERE shares > 0
                """
            )
            connection.execute(
                "INSERT INTO schema_migrations (migration_key) VALUES ('portfolio_holdings_to_lots_v1')"
            )


def save_backtest_run(run: Mapping[str, object], db_path: str | Path | None = None) -> None:
    """Persist a reproducible point-in-time simulation and its separated outcomes."""
    init_db(db_path)
    fields = (
        "ticker", "as_of_date", "coverage", "entry_score", "exit_score", "entry_signal", "exit_signal",
        "technical_score", "valuation_score", "risk_score", "outcome_1m", "outcome_3m",
        "outcome_6m", "outcome_12m", "inputs_json", "model_version",
    )
    values = [run.get(field) for field in fields]
    with get_connection(db_path) as connection:
        connection.execute(
            f"""INSERT INTO backtest_runs ({', '.join(fields)}) VALUES ({', '.join('?' for _ in fields)})
            ON CONFLICT(ticker, as_of_date, model_version) DO UPDATE SET
                coverage=excluded.coverage, entry_score=excluded.entry_score, exit_score=excluded.exit_score,
                entry_signal=excluded.entry_signal, exit_signal=excluded.exit_signal,
                technical_score=excluded.technical_score, valuation_score=excluded.valuation_score,
                risk_score=excluded.risk_score, outcome_1m=excluded.outcome_1m,
                outcome_3m=excluded.outcome_3m, outcome_6m=excluded.outcome_6m,
                outcome_12m=excluded.outcome_12m, inputs_json=excluded.inputs_json
            """,
            values,
        )


def get_backtest_runs(ticker: str | None = None, db_path: str | Path | None = None) -> list[dict[str, object]]:
    init_db(db_path)
    query = "SELECT * FROM backtest_runs"
    params: tuple[object, ...] = ()
    if ticker:
        query += " WHERE ticker = ?"
        params = (ticker.strip().upper(),)
    query += " ORDER BY as_of_date DESC, ticker"
    with get_connection(db_path) as connection:
        return [dict(row) for row in connection.execute(query, params).fetchall()]


def update_backtest_outcomes(
    ticker: str, as_of_date: str, outcomes: Mapping[str, object],
    db_path: str | Path | None = None,
) -> None:
    """Refresh only forward outcomes; reconstructed inputs/scores remain immutable."""
    init_db(db_path)
    with get_connection(db_path) as connection:
        connection.execute(
            """UPDATE backtest_runs SET outcome_1m=?, outcome_3m=?, outcome_6m=?, outcome_12m=?,
                outcome_refreshed_at=CURRENT_TIMESTAMP
            WHERE ticker=? AND as_of_date=?""",
            (outcomes.get("1M"), outcomes.get("3M"), outcomes.get("6M"), outcomes.get("12M"),
             ticker.strip().upper(), as_of_date),
        )


def set_backtest_job_item(
    as_of_date: str, ticker: str, status: str, error: str | None = None,
    db_path: str | Path | None = None,
) -> None:
    init_db(db_path)
    with get_connection(db_path) as connection:
        connection.execute(
            """INSERT INTO backtest_job_items (as_of_date, ticker, status, error, updated_at)
            VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(as_of_date, ticker) DO UPDATE SET status=excluded.status,
                error=excluded.error, updated_at=CURRENT_TIMESTAMP""",
            (as_of_date, ticker.strip().upper(), status, error),
        )


def get_backtest_job_items(as_of_date: str, db_path: str | Path | None = None) -> list[dict[str, object]]:
    init_db(db_path)
    with get_connection(db_path) as connection:
        rows = connection.execute(
            "SELECT * FROM backtest_job_items WHERE as_of_date = ? ORDER BY ticker", (as_of_date,)
        ).fetchall()
    return [dict(row) for row in rows]


def add_ticker(ticker: str, db_path: str | Path | None = None) -> None:
    normalized = ticker.strip().upper()
    if not normalized:
        raise ValueError("Ticker cannot be empty")
    init_db(db_path)
    with get_connection(db_path) as connection:
        connection.execute("INSERT OR IGNORE INTO watchlist (ticker) VALUES (?)", (normalized,))


def remove_ticker(ticker: str, db_path: str | Path | None = None) -> None:
    normalized = ticker.strip().upper()
    init_db(db_path)
    with get_connection(db_path) as connection:
        holding = connection.execute(
            "SELECT 1 FROM portfolio_holdings WHERE ticker = ?", (normalized,)
        ).fetchone()
        if holding:
            raise ValueError(f"{normalized} is in the portfolio. Mark it as not owned first.")
        connection.execute("DELETE FROM watchlist WHERE ticker = ?", (normalized,))


def get_watchlist(db_path: str | Path | None = None) -> list[str]:
    init_db(db_path)
    with get_connection(db_path) as connection:
        return [row["ticker"] for row in connection.execute("SELECT ticker FROM watchlist ORDER BY ticker")]


def save_dashboard_order(tickers: list[str], db_path: str | Path | None = None) -> None:
    normalized = [str(ticker).strip().upper() for ticker in tickers if str(ticker).strip()]
    init_db(db_path)
    with get_connection(db_path) as connection:
        connection.execute(
            """
            INSERT INTO ui_preferences (preference_key, value_json, updated_at)
            VALUES ('decision_dashboard_order', ?, CURRENT_TIMESTAMP)
            ON CONFLICT(preference_key) DO UPDATE SET
                value_json=excluded.value_json, updated_at=CURRENT_TIMESTAMP
            """,
            (json.dumps(normalized),),
        )


def get_dashboard_order(db_path: str | Path | None = None) -> list[str]:
    init_db(db_path)
    with get_connection(db_path) as connection:
        row = connection.execute(
            "SELECT value_json FROM ui_preferences WHERE preference_key = 'decision_dashboard_order'"
        ).fetchone()
    if not row:
        return []
    value = json.loads(row["value_json"])
    return [str(ticker) for ticker in value] if isinstance(value, list) else []


def save_active_backtest(as_of_date: str | None, db_path: str | Path | None = None) -> None:
    """Persist the Time Machine selection across navigation and browser reloads."""
    init_db(db_path)
    with get_connection(db_path) as connection:
        connection.execute(
            """INSERT INTO ui_preferences (preference_key, value_json, updated_at)
            VALUES ('active_backtest_date', ?, CURRENT_TIMESTAMP)
            ON CONFLICT(preference_key) DO UPDATE SET value_json=excluded.value_json,
                updated_at=CURRENT_TIMESTAMP""",
            (json.dumps(as_of_date),),
        )


def get_active_backtest(db_path: str | Path | None = None) -> str | None:
    init_db(db_path)
    with get_connection(db_path) as connection:
        row = connection.execute(
            "SELECT value_json FROM ui_preferences WHERE preference_key='active_backtest_date'"
        ).fetchone()
    return json.loads(row["value_json"]) if row else None


def set_portfolio_holding(
    ticker: str,
    owned: bool,
    shares: float = 0,
    db_path: str | Path | None = None,
) -> None:
    """Record ownership. A portfolio ticker is always added to the watchlist."""
    normalized = ticker.strip().upper()
    if not normalized:
        raise ValueError("Ticker cannot be empty")
    if shares < 0:
        raise ValueError("Shares cannot be negative")
    if owned and shares <= 0:
        raise ValueError("Owned holdings must have more than zero shares")

    add_ticker(normalized, db_path)
    with get_connection(db_path) as connection:
        if owned:
            connection.execute(
                """
                INSERT INTO portfolio_holdings (ticker, shares, updated_at)
                VALUES (?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(ticker) DO UPDATE SET
                    shares = excluded.shares,
                    updated_at = CURRENT_TIMESTAMP
                """,
                (normalized, shares),
            )
            existing_legacy = connection.execute(
                "SELECT id FROM portfolio_lots WHERE ticker = ? AND source = 'legacy' ORDER BY id LIMIT 1",
                (normalized,),
            ).fetchone()
            if existing_legacy:
                connection.execute(
                    "UPDATE portfolio_lots SET shares = ? WHERE id = ?",
                    (shares, existing_legacy["id"]),
                )
            elif not connection.execute(
                "SELECT 1 FROM portfolio_lots WHERE ticker = ?", (normalized,)
            ).fetchone():
                connection.execute(
                    "INSERT INTO portfolio_lots (ticker, shares, source, notes) VALUES (?, ?, 'legacy', ?)",
                    (normalized, shares, "Aggregate holding; purchase details unknown"),
                )
        else:
            connection.execute("DELETE FROM portfolio_holdings WHERE ticker = ?", (normalized,))
            connection.execute("DELETE FROM portfolio_lots WHERE ticker = ?", (normalized,))


def get_portfolio_holdings(db_path: str | Path | None = None) -> list[dict[str, object]]:
    init_db(db_path)
    with get_connection(db_path) as connection:
        return [
            dict(row)
            for row in connection.execute(
                "SELECT ticker, shares, updated_at FROM portfolio_holdings ORDER BY ticker"
            )
        ]


def _sync_portfolio_holding(ticker: str, connection: sqlite3.Connection) -> None:
    total = connection.execute(
        "SELECT COALESCE(SUM(shares), 0) AS shares FROM portfolio_lots WHERE ticker = ?", (ticker,)
    ).fetchone()["shares"]
    if total > 0:
        connection.execute(
            """
            INSERT INTO portfolio_holdings (ticker, shares, updated_at)
            VALUES (?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(ticker) DO UPDATE SET shares=excluded.shares, updated_at=CURRENT_TIMESTAMP
            """,
            (ticker, total),
        )
    else:
        connection.execute("DELETE FROM portfolio_holdings WHERE ticker = ?", (ticker,))


def add_portfolio_lot(lot: Mapping[str, object], db_path: str | Path | None = None) -> int:
    normalized = str(lot.get("ticker", "")).strip().upper()
    shares = float(lot.get("shares", 0) or 0)
    price = float(lot.get("price_per_share", 0) or 0)
    fees = float(lot.get("fees", 0) or 0)
    purchase_date = str(lot.get("purchase_date", "")).strip()
    if not normalized:
        raise ValueError("Ticker cannot be empty")
    if shares <= 0 or price <= 0:
        raise ValueError("Shares and price per share must be greater than zero")
    if fees < 0:
        raise ValueError("Fees cannot be negative")
    if not purchase_date:
        raise ValueError("Purchase date is required")
    add_ticker(normalized, db_path)
    with get_connection(db_path) as connection:
        cursor = connection.execute(
            """
            INSERT INTO portfolio_lots
                (ticker, purchase_date, shares, price_per_share, fees, source, notes)
            VALUES (?, ?, ?, ?, ?, 'manual', ?)
            """,
            (normalized, purchase_date, shares, price, fees, lot.get("notes")),
        )
        _sync_portfolio_holding(normalized, connection)
        return int(cursor.lastrowid)


def get_portfolio_lots(
    ticker: str | None = None, db_path: str | Path | None = None
) -> list[dict[str, object]]:
    init_db(db_path)
    query, params = "SELECT * FROM portfolio_lots", []
    if ticker:
        query += " WHERE ticker = ?"
        params.append(ticker.strip().upper())
    query += " ORDER BY COALESCE(purchase_date, '0000-00-00') DESC, id DESC"
    with get_connection(db_path) as connection:
        return [dict(row) for row in connection.execute(query, params)]


def update_portfolio_lot(
    lot_id: int, lot: Mapping[str, object], db_path: str | Path | None = None
) -> None:
    init_db(db_path)
    with get_connection(db_path) as connection:
        existing = connection.execute("SELECT * FROM portfolio_lots WHERE id = ?", (lot_id,)).fetchone()
        if not existing:
            raise ValueError(f"Portfolio lot {lot_id} does not exist")
        ticker = str(lot.get("ticker", existing["ticker"])).strip().upper()
        shares = float(lot.get("shares", existing["shares"]) or 0)
        price_value = lot.get("price_per_share", existing["price_per_share"])
        price = float(price_value) if price_value not in (None, "") else None
        fees = float(lot.get("fees", existing["fees"]) or 0)
        purchase_date = lot.get("purchase_date", existing["purchase_date"])
        if shares <= 0 or (price is not None and price <= 0) or fees < 0:
            raise ValueError("Lot values must be positive and fees cannot be negative")
        add_ticker(ticker, db_path)
        connection.execute(
            """
            UPDATE portfolio_lots SET ticker=?, purchase_date=?, shares=?, price_per_share=?,
                fees=?, notes=? WHERE id=?
            """,
            (ticker, purchase_date, shares, price, fees, lot.get("notes", existing["notes"]), lot_id),
        )
        _sync_portfolio_holding(existing["ticker"], connection)
        if ticker != existing["ticker"]:
            _sync_portfolio_holding(ticker, connection)


def delete_portfolio_lot(lot_id: int, db_path: str | Path | None = None) -> None:
    init_db(db_path)
    with get_connection(db_path) as connection:
        existing = connection.execute("SELECT ticker FROM portfolio_lots WHERE id = ?", (lot_id,)).fetchone()
        if not existing:
            raise ValueError(f"Portfolio lot {lot_id} does not exist")
        connection.execute("DELETE FROM portfolio_lots WHERE id = ?", (lot_id,))
        _sync_portfolio_holding(existing["ticker"], connection)


def record_portfolio_sale(
    sale: Mapping[str, object], db_path: str | Path | None = None
) -> int:
    """Record a sale and consume open lots FIFO. Unknown legacy costs produce unknown P&L."""
    normalized = str(sale.get("ticker", "")).strip().upper()
    shares_to_sell = float(sale.get("shares", 0) or 0)
    sale_price = float(sale.get("price_per_share", 0) or 0)
    fees = float(sale.get("fees", 0) or 0)
    sale_date = str(sale.get("sale_date", "")).strip()
    if not normalized or not sale_date:
        raise ValueError("Ticker and sale date are required")
    if shares_to_sell <= 0 or sale_price <= 0 or fees < 0:
        raise ValueError("Sale shares/price must be positive and fees cannot be negative")
    init_db(db_path)
    with get_connection(db_path) as connection:
        available = connection.execute(
            "SELECT COALESCE(SUM(shares), 0) AS shares FROM portfolio_lots WHERE ticker = ?",
            (normalized,),
        ).fetchone()["shares"]
        if shares_to_sell > available + 1e-9:
            raise ValueError(f"Cannot sell {shares_to_sell:g} shares; only {available:g} are available")
        lots = connection.execute(
            """
            SELECT * FROM portfolio_lots WHERE ticker = ?
            ORDER BY CASE WHEN purchase_date IS NULL THEN 0 ELSE 1 END, purchase_date, id
            """,
            (normalized,),
        ).fetchall()
        remaining, cost_basis, cost_known = shares_to_sell, 0.0, True
        for lot in lots:
            if remaining <= 1e-9:
                break
            consumed = min(remaining, float(lot["shares"]))
            if lot["price_per_share"] is None:
                cost_known = False
            else:
                lot_fee_share = float(lot["fees"]) * consumed / float(lot["shares"])
                cost_basis += consumed * float(lot["price_per_share"]) + lot_fee_share
            leftover = float(lot["shares"]) - consumed
            if leftover <= 1e-9:
                connection.execute("DELETE FROM portfolio_lots WHERE id = ?", (lot["id"],))
            else:
                remaining_fee = float(lot["fees"]) * leftover / float(lot["shares"])
                connection.execute(
                    "UPDATE portfolio_lots SET shares = ?, fees = ? WHERE id = ?",
                    (leftover, remaining_fee, lot["id"]),
                )
            remaining -= consumed
        known_cost = cost_basis if cost_known else None
        proceeds = shares_to_sell * sale_price - fees
        realized_pl = proceeds - cost_basis if cost_known else None
        cursor = connection.execute(
            """
            INSERT INTO portfolio_sales
                (ticker, sale_date, shares, price_per_share, fees, cost_basis, realized_pl, notes)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (normalized, sale_date, shares_to_sell, sale_price, fees, known_cost, realized_pl, sale.get("notes")),
        )
        _sync_portfolio_holding(normalized, connection)
        return int(cursor.lastrowid)


def get_portfolio_sales(
    ticker: str | None = None, db_path: str | Path | None = None
) -> list[dict[str, object]]:
    init_db(db_path)
    query, params = "SELECT * FROM portfolio_sales", []
    if ticker:
        query += " WHERE ticker = ?"
        params.append(ticker.strip().upper())
    query += " ORDER BY sale_date DESC, id DESC"
    with get_connection(db_path) as connection:
        return [dict(row) for row in connection.execute(query, params)]


def save_portfolio_snapshot(
    snapshot_date: str,
    total_value: float,
    priced_positions: int,
    total_positions: int,
    base_currency: str = "USD",
    db_path: str | Path | None = None,
) -> None:
    if total_value < 0 or priced_positions < 0 or total_positions < 0:
        raise ValueError("Snapshot values cannot be negative")
    if priced_positions > total_positions:
        raise ValueError("Priced positions cannot exceed total positions")
    init_db(db_path)
    with get_connection(db_path) as connection:
        connection.execute(
            """
            INSERT INTO portfolio_snapshots
                (snapshot_date, total_value, base_currency, priced_positions, total_positions, captured_at)
            VALUES (?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(snapshot_date) DO UPDATE SET
                total_value=excluded.total_value,
                base_currency=excluded.base_currency,
                priced_positions=excluded.priced_positions,
                total_positions=excluded.total_positions,
                captured_at=CURRENT_TIMESTAMP
            """,
            (snapshot_date, total_value, base_currency.strip().upper(), priced_positions, total_positions),
        )


def get_portfolio_snapshots(db_path: str | Path | None = None) -> list[dict[str, object]]:
    init_db(db_path)
    with get_connection(db_path) as connection:
        return [
            dict(row) for row in connection.execute(
                "SELECT * FROM portfolio_snapshots ORDER BY snapshot_date"
            )
        ]


def add_cash_transaction(
    transaction: Mapping[str, object], db_path: str | Path | None = None
) -> int:
    transaction_type = str(transaction.get("transaction_type", ""))
    allowed = {"deposit", "withdrawal", "dividend", "withholding_tax", "fee", "adjustment"}
    if transaction_type not in allowed:
        raise ValueError("Unsupported cash transaction type")
    amount = float(transaction.get("amount", 0) or 0)
    if amount == 0:
        raise ValueError("Cash transaction amount cannot be zero")
    # Outflows are stored as negative amounts regardless of how the UI supplied them.
    if transaction_type in {"withdrawal", "withholding_tax", "fee"}:
        amount = -abs(amount)
    elif transaction_type in {"deposit", "dividend"}:
        amount = abs(amount)
    currency = str(transaction.get("currency", "")).strip().upper()
    transaction_date = str(transaction.get("transaction_date", "")).strip()
    if not currency or not transaction_date:
        raise ValueError("Transaction date and currency are required")
    ticker = str(transaction.get("ticker", "")).strip().upper() or None
    init_db(db_path)
    with get_connection(db_path) as connection:
        cursor = connection.execute(
            """
            INSERT INTO cash_transactions
                (transaction_date, transaction_type, amount, currency, ticker, notes)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (transaction_date, transaction_type, amount, currency, ticker, transaction.get("notes")),
        )
        return int(cursor.lastrowid)


def get_cash_transactions(db_path: str | Path | None = None) -> list[dict[str, object]]:
    init_db(db_path)
    with get_connection(db_path) as connection:
        return [
            dict(row) for row in connection.execute(
                "SELECT * FROM cash_transactions ORDER BY transaction_date DESC, id DESC"
            )
        ]


def delete_cash_transaction(transaction_id: int, db_path: str | Path | None = None) -> None:
    init_db(db_path)
    with get_connection(db_path) as connection:
        cursor = connection.execute("DELETE FROM cash_transactions WHERE id = ?", (transaction_id,))
        if cursor.rowcount == 0:
            raise ValueError(f"Cash transaction {transaction_id} does not exist")


def set_portfolio_target(
    ticker: str, target_weight_pct: float, db_path: str | Path | None = None
) -> None:
    normalized = ticker.strip().upper()
    if not 0 <= target_weight_pct <= 100:
        raise ValueError("Target weight must be between 0 and 100")
    add_ticker(normalized, db_path)
    with get_connection(db_path) as connection:
        connection.execute(
            """
            INSERT INTO portfolio_targets (ticker, target_weight_pct, updated_at)
            VALUES (?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(ticker) DO UPDATE SET
                target_weight_pct=excluded.target_weight_pct, updated_at=CURRENT_TIMESTAMP
            """,
            (normalized, target_weight_pct),
        )


def get_portfolio_targets(db_path: str | Path | None = None) -> list[dict[str, object]]:
    init_db(db_path)
    with get_connection(db_path) as connection:
        return [dict(row) for row in connection.execute("SELECT * FROM portfolio_targets ORDER BY ticker")]


def save_fundamentals(
    fundamentals: Mapping[str, object], db_path: str | Path | None = None
) -> None:
    """Upsert a normalized provider response into the daily cache."""
    init_db(db_path)
    fields = (
        "ticker", "trailing_pe", "forward_pe", "price_to_sales_ttm",
        "revenue_growth", "eps_growth", "reporting_date", "provider_name", "fetched_at",
    )
    with get_connection(db_path) as connection:
        connection.execute(
            f"""
            INSERT INTO fundamentals_cache ({', '.join(fields)})
            VALUES ({', '.join('?' for _ in fields)})
            ON CONFLICT(ticker) DO UPDATE SET
                trailing_pe=excluded.trailing_pe,
                forward_pe=excluded.forward_pe,
                price_to_sales_ttm=excluded.price_to_sales_ttm,
                revenue_growth=excluded.revenue_growth,
                eps_growth=excluded.eps_growth,
                reporting_date=excluded.reporting_date,
                provider_name=excluded.provider_name,
                fetched_at=excluded.fetched_at
            """,
            [fundamentals.get(field) for field in fields],
        )


def get_cached_fundamentals(
    ticker: str, db_path: str | Path | None = None
) -> dict[str, object] | None:
    init_db(db_path)
    with get_connection(db_path) as connection:
        row = connection.execute(
            "SELECT * FROM fundamentals_cache WHERE ticker = ?", (ticker.strip().upper(),)
        ).fetchone()
        return dict(row) if row else None


def save_industry_research(
    ticker: str, payload: Mapping[str, object], provider_name: str, fetched_at: str,
    db_path: str | Path | None = None,
) -> None:
    """Persist a normalized industry/analyst research snapshot."""
    init_db(db_path)
    with get_connection(db_path) as connection:
        connection.execute(
            """
            INSERT INTO industry_research_cache (ticker, payload_json, provider_name, fetched_at)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(ticker) DO UPDATE SET payload_json=excluded.payload_json,
                provider_name=excluded.provider_name, fetched_at=excluded.fetched_at
            """,
            (ticker.strip().upper(), json.dumps(payload), provider_name, fetched_at),
        )


def get_cached_industry_research(
    ticker: str, db_path: str | Path | None = None,
) -> dict[str, object] | None:
    """Return the normalized cached industry snapshot, if present."""
    init_db(db_path)
    with get_connection(db_path) as connection:
        row = connection.execute(
            "SELECT payload_json, provider_name, fetched_at FROM industry_research_cache WHERE ticker = ?",
            (ticker.strip().upper(),),
        ).fetchone()
    if not row:
        return None
    payload = json.loads(row["payload_json"])
    payload["provider_name"] = row["provider_name"]
    payload["fetched_at"] = row["fetched_at"]
    return payload


def save_positioning_snapshot(
    ticker: str, payload: Mapping[str, object], provider_name: str,
    reporting_date: str | None, fetched_at: str, db_path: str | Path | None = None,
) -> None:
    init_db(db_path)
    with get_connection(db_path) as connection:
        connection.execute(
            """
            INSERT INTO positioning_cache
                (ticker, payload_json, provider_name, reporting_date, fetched_at)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(ticker) DO UPDATE SET payload_json=excluded.payload_json,
                provider_name=excluded.provider_name, reporting_date=excluded.reporting_date,
                fetched_at=excluded.fetched_at
            """,
            (ticker.strip().upper(), json.dumps(payload), provider_name, reporting_date, fetched_at),
        )
        connection.execute(
            """
            INSERT INTO positioning_history
                (ticker, snapshot_date, payload_json, provider_name, reporting_date, fetched_at)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(ticker, snapshot_date) DO UPDATE SET payload_json=excluded.payload_json,
                provider_name=excluded.provider_name, reporting_date=excluded.reporting_date,
                fetched_at=excluded.fetched_at
            """,
            (ticker.strip().upper(), fetched_at[:10], json.dumps(payload), provider_name, reporting_date, fetched_at),
        )


def get_cached_positioning(
    ticker: str, db_path: str | Path | None = None,
) -> dict[str, object] | None:
    init_db(db_path)
    with get_connection(db_path) as connection:
        row = connection.execute(
            "SELECT payload_json, provider_name, reporting_date, fetched_at FROM positioning_cache WHERE ticker = ?",
            (ticker.strip().upper(),),
        ).fetchone()
    if not row:
        return None
    payload = json.loads(row["payload_json"])
    payload.update({
        "provider_name": row["provider_name"], "reporting_date": row["reporting_date"],
        "fetched_at": row["fetched_at"],
    })
    return payload


def get_positioning_history(ticker: str, db_path: str | Path | None = None) -> list[dict[str, object]]:
    init_db(db_path)
    with get_connection(db_path) as connection:
        rows = connection.execute(
            "SELECT * FROM positioning_history WHERE ticker = ? ORDER BY snapshot_date",
            (ticker.strip().upper(),),
        ).fetchall()
    return [{**json.loads(row["payload_json"]), **{
        "snapshot_date": row["snapshot_date"], "provider_name": row["provider_name"],
        "reporting_date": row["reporting_date"], "fetched_at": row["fetched_at"],
    }} for row in rows]


def save_positioning_history_snapshot(
    ticker: str, snapshot_date: str, payload: Mapping[str, object], provider_name: str,
    reporting_date: str | None, fetched_at: str, db_path: str | Path | None = None,
) -> None:
    """Persist historical evidence without replacing the current positioning cache."""
    init_db(db_path)
    with get_connection(db_path) as connection:
        connection.execute(
            """
            INSERT INTO positioning_history
                (ticker, snapshot_date, payload_json, provider_name, reporting_date, fetched_at)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(ticker, snapshot_date) DO UPDATE SET payload_json=excluded.payload_json,
                provider_name=excluded.provider_name, reporting_date=excluded.reporting_date,
                fetched_at=excluded.fetched_at
            """,
            (ticker.strip().upper(), snapshot_date, json.dumps(payload), provider_name, reporting_date, fetched_at),
        )


def add_journal_entry(entry: Mapping[str, object], db_path: str | Path | None = None) -> None:
    required = {"ticker", "entry_date", "action", "conviction"}
    missing = required - entry.keys()
    if missing:
        raise ValueError(f"Missing journal fields: {', '.join(sorted(missing))}")
    init_db(db_path)
    fields = ("ticker", "entry_date", "action", "thesis", "catalyst", "main_risk", "invalidation_condition", "target_price", "time_horizon", "conviction", "notes")
    values = [entry.get(field) for field in fields]
    values[0] = str(values[0]).strip().upper()
    with get_connection(db_path) as connection:
        connection.execute(
            f"INSERT INTO journal_entries ({', '.join(fields)}) VALUES ({', '.join('?' for _ in fields)})",
            values,
        )


def update_journal_entry(
    entry_id: int, entry: Mapping[str, object], db_path: str | Path | None = None
) -> None:
    required = {"ticker", "entry_date", "action", "conviction"}
    missing = required - entry.keys()
    if missing:
        raise ValueError(f"Missing journal fields: {', '.join(sorted(missing))}")
    init_db(db_path)
    fields = ("ticker", "entry_date", "action", "thesis", "catalyst", "main_risk", "invalidation_condition", "target_price", "time_horizon", "conviction", "notes")
    values = [entry.get(field) for field in fields]
    values[0] = str(values[0]).strip().upper()
    with get_connection(db_path) as connection:
        cursor = connection.execute(
            f"UPDATE journal_entries SET {', '.join(f'{field} = ?' for field in fields)} WHERE id = ?",
            [*values, entry_id],
        )
        if cursor.rowcount == 0:
            raise ValueError(f"Journal entry {entry_id} does not exist")


def delete_journal_entry(entry_id: int, db_path: str | Path | None = None) -> None:
    init_db(db_path)
    with get_connection(db_path) as connection:
        cursor = connection.execute("DELETE FROM journal_entries WHERE id = ?", (entry_id,))
        if cursor.rowcount == 0:
            raise ValueError(f"Journal entry {entry_id} does not exist")


def get_journal_entries(ticker: str | None = None, db_path: str | Path | None = None, action: str | None = None, conviction: int | None = None) -> list[dict[str, object]]:
    init_db(db_path)
    query = "SELECT * FROM journal_entries"
    filters, params = [], []
    if ticker:
        filters.append("ticker = ?")
        params.append(ticker.strip().upper())
    if action:
        filters.append("action = ?")
        params.append(action)
    if conviction:
        filters.append("conviction = ?")
        params.append(str(conviction))
    if filters:
        query += " WHERE " + " AND ".join(filters)
    query += " ORDER BY entry_date DESC, id DESC"
    with get_connection(db_path) as connection:
        return [dict(row) for row in connection.execute(query, params)]
