"""Explicit, bounded deletion of disposable cache orphans only."""

from src.data.database import get_connection, init_db

CACHE_TABLES = ("fundamentals_cache", "industry_research_cache", "positioning_cache",
                "extended_hours_cache", "market_price_cache")


def clean_orphan_caches(db_path=None, *, apply=False):
    """Delete caches outside the active universe, retaining positions/benchmarks.

    Callers must create a verified backup before apply=True. Historical predictions,
    raw disclosures, input snapshots and outcomes are never cleanup targets.
    """
    init_db(db_path)
    with get_connection(db_path) as connection:
        protected = {row[0] for row in connection.execute("SELECT ticker FROM watchlist")}
        protected.update(row[0] for row in connection.execute("SELECT ticker FROM portfolio_holdings"))
        protected.update(row[0] for row in connection.execute("SELECT DISTINCT ticker FROM portfolio_lots"))
        protected.update(row[0] for row in connection.execute(
            "SELECT DISTINCT benchmark_ticker FROM outcome_label_observations WHERE benchmark_ticker IS NOT NULL"))
        protected.update({"SPY", "^GSPC"})
        report = {}
        for table in CACHE_TABLES:
            # Older databases may not have the optional persisted price cache yet.
            if not connection.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,)).fetchone():
                continue
            keys = [row[0] for row in connection.execute(f"SELECT DISTINCT ticker FROM {table}")
                    if row[0] not in protected]
            count = 0
            for ticker in keys:
                count += connection.execute(f"SELECT COUNT(*) FROM {table} WHERE ticker=?", (ticker,)).fetchone()[0]
                if apply:
                    connection.execute(f"DELETE FROM {table} WHERE ticker=?", (ticker,))
            report[table] = count
        return {"applied": apply, "rows": report, "total": sum(report.values())}
