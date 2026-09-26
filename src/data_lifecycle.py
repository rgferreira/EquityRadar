"""Aggregate lifecycle inventory, without reading personal portfolio information."""

from datetime import date
from collections import Counter

from src.data.database import get_connection, get_prediction_snapshots, init_db
from src.data.outcome_maturation import get_current_outcome_labels
from src.whaleseeker import whale_catchup_states


def research_lifecycle(db_path=None, *, today=None):
    today = today or date.today()
    init_db(db_path)
    with get_connection(db_path) as connection:
        manual = dict(connection.execute("""SELECT COUNT(*) records, COUNT(DISTINCT as_of_date) dates,
            MAX(created_at) updated FROM backtest_runs WHERE simulation_source='manual'""").fetchone())
        jobs = [dict(row) for row in connection.execute(
            "SELECT error,COUNT(*) records FROM backtest_job_items WHERE status='failed' GROUP BY error")]
        btc = dict(connection.execute("""SELECT COUNT(*) records, MAX(period_date) period,
            MAX(fetched_at) updated FROM bitcoin_derivatives_daily_observations""").fetchone())
        whale = dict(connection.execute("""SELECT COUNT(*) records,MAX(filed_date) period,
            MAX(fetched_at) updated FROM whale_disclosure_observations""").fetchone())
        archival = []
        for table, label in (("evaluation_runs", "Frozen evaluations"),
                             ("challenger_experiment_runs", "Frozen challenger experiments"),
                             ("finra_simulation_enrichments", "FINRA historical overlays"),
                             ("btc_simulation_enrichments", "BTC historical overlays")):
            row = connection.execute(f"SELECT COUNT(*) n,MAX(created_at) latest FROM {table}").fetchone()
            archival.append({"section": label, "status": "Archived research", "records": row["n"],
                             "latest_evidence": row["latest"], "meaning": "Frozen result; rerun requires an explicit new experiment"})
        cached_orphans = sum(connection.execute(
            f"SELECT COUNT(*) FROM {table} WHERE ticker NOT IN (SELECT ticker FROM watchlist)").fetchone()[0]
            for table in ("industry_research_cache", "positioning_cache"))
    labels = {row["prediction_id"]: row for row in get_current_outcome_labels(db_path=db_path)}
    predictions = get_prediction_snapshots(db_path=db_path)
    coverage, waiting, overdue = Counter(), Counter(), Counter()
    for prediction in predictions:
        if str(prediction["ticker"]).endswith("-USD"):
            continue
        age = (today - date.fromisoformat(prediction["as_of_date"])).days
        outcomes = labels.get(prediction["prediction_id"], {}).get("outcomes", {})
        for horizon, conservative_days in (("1M", 38), ("3M", 100), ("6M", 195)):
            if isinstance(outcomes.get(horizon), dict):
                coverage[horizon] += 1
            elif age >= conservative_days:
                overdue[horizon] += 1
            else:
                waiting[horizon] += 1
    conflicts = sum(r["records"] for r in jobs if "Immutable" in str(r["error"]))
    insufficient = sum(r["records"] for r in jobs if "Insufficient price history" in str(r["error"]))
    catchup = whale_catchup_states(db_path)
    pending_catchup = sum(r["status"] == "pending" for r in catchup)
    blocked_catchup = any(r["status"] == "blocked_entitlement" for r in catchup)
    rows = [{"section": "Manual simulations", "status": "Historical diagnostics", "records": manual["records"],
             "latest_evidence": manual["updated"],
             "meaning": f"{manual['dates']} cutoff dates; versions/overlapping horizons are not independent bets. Learning weight = 0."},
            {"section": "Congress disclosures", "status": "Blocked by subscription" if blocked_catchup else "Gap recovery pending" if pending_catchup else "Observed disclosures",
             "records": whale["records"], "latest_evidence": whale["period"],
             "meaning": "FMP HTTP 402 blocks older pages; latest-page checks continue. Score weight = 0." if blocked_catchup else "Provider health measures query freshness. Filing date is not real-time flow; score weight = 0."},
            {"section": "BTC derivatives", "status": "Stale" if not btc["period"] or (today-date.fromisoformat(btc["period"])).days > 2 else "Current",
             "records": btc["records"], "latest_evidence": btc["period"],
             "meaning": "Daily source period; now scheduled independently of Company navigation."}]
    rows += [{"section": f"Relative outcomes {h}", "status": "Review gaps" if overdue[h] else "Maturing",
              "records": coverage[h], "latest_evidence": today.isoformat(),
              "meaning": f"{waiting[h]} awaiting maturity; {overdue[h]} older missing outcomes to inspect. Session prices determine actual maturity."}
             for h in ("1M", "3M", "6M")]
    rows += [{"section": "Simulation retries", "status": "Classified failures", "records": sum(r["records"] for r in jobs),
              "latest_evidence": None, "meaning": f"{conflicts} frozen-identity conflicts; {insufficient} insufficient-history cutoffs. Do not overwrite original predictions."},
             {"section": "Retired-universe caches", "status": "Inactive cache", "records": cached_orphans,
              "latest_evidence": None, "meaning": "Not in the current watchlist; retained without requiring daily refresh."}]
    return rows + archival
