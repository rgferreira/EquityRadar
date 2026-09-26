"""Delayed CFTC institutional positioning, distinct from Congressional disclosures."""
from __future__ import annotations

from datetime import date, timedelta
import json

from src.data.research_signals import attempt, bounded_get, latest_batch, number, timestamp, utcnow

URL = "https://publicreporting.cftc.gov/resource/gpe5-46if.json"
# CFTC contract codes, not ticker substitutions or inferred cash-flow destinations.
CONTRACTS = {"13874A": "S&P 500 consolidated", "209742": "Nasdaq-100", "099741": "Euro FX", "043602": "10-year Treasury"}
FIELDS = ("market_and_exchange_names,cftc_contract_market_code,report_date_as_yyyy_mm_dd,"
          "open_interest_all,asset_mgr_positions_long,asset_mgr_positions_short,"
          "lev_money_positions_long,lev_money_positions_short")


def normalize(records):
    result = []
    for row in records:
        code = row.get("cftc_contract_market_code")
        oi = number(row.get("open_interest_all"))
        if code not in CONTRACTS or oi is None or oi <= 0:
            continue
        values = [number(row.get(k)) for k in ("asset_mgr_positions_long", "asset_mgr_positions_short",
                                               "lev_money_positions_long", "lev_money_positions_short")]
        if None in values or any(v < 0 for v in values):
            continue
        result.append({"contract": code, "market": row["market_and_exchange_names"],
            "period_end": row["report_date_as_yyyy_mm_dd"][:10], "published_at": None,
            "open_interest": oi, "asset_manager_net_pct_oi": (values[0] - values[1]) / oi * 100,
            "leveraged_money_net_pct_oi": (values[2] - values[3]) / oi * 100})
    result.sort(key=lambda r: (r["contract"], r["period_end"]))
    previous = {}
    for row in result:
        prior = previous.get(row["contract"])
        consecutive = prior and (date.fromisoformat(row["period_end"]) - date.fromisoformat(prior["period_end"])).days == 7
        for family in ("asset_manager", "leveraged_money"):
            key = family + "_net_pct_oi"
            row[family + "_weekly_change_pp"] = row[key] - prior[key] if consecutive else None
        previous[row["contract"]] = row
    return result


def fetch_positioning():
    since = (date.today() - timedelta(days=190)).isoformat()
    codes = ",".join("'" + k + "'" for k in CONTRACTS)
    raw = json.loads(bounded_get(URL, params={"$select": FIELDS,
        "$where": f"cftc_contract_market_code in ({codes}) AND report_date_as_yyyy_mm_dd >= '{since}T00:00:00'",
        "$order": "report_date_as_yyyy_mm_dd DESC,cftc_contract_market_code", "$limit": 500}))
    rows = normalize(raw)
    return {"source_url": URL, "raw_records": raw, "records": rows,
            "meaning": "Delayed futures positioning; weekly net changes are not dollar flows",
            "publication_note": "Usually Friday for Tuesday positions; no inferred historical known_at"} if rows else None


def refresh_institutions(db_path=None):
    return attempt("institutional", "cftc_tff", fetch_positioning, db_path=db_path)


def institutional_summary(db_path=None, *, as_of=None):
    now = timestamp(as_of or utcnow())
    batch = latest_batch("institutional", "cftc_tff", as_of=now.isoformat(), db_path=db_path)
    if not batch:
        return {"status": "unavailable", "records": [], "directional_weight": 0}
    latest = {}
    for row in batch["payload"]["records"]:
        if row["contract"] not in latest or row["period_end"] > latest[row["contract"]]["period_end"]:
            age = (now.date() - date.fromisoformat(row["period_end"])).days
            latest[row["contract"]] = {**row, "status": "fresh" if 0 <= age <= 14 else "stale",
                                       "known_at": batch["observed_at"]}
    return {"status": "captured", "records": list(latest.values()), "batch_id": batch["batch_id"],
            "history_records": len(batch["payload"]["records"]), "expected_contracts": len(CONTRACTS),
            "directional_weight": 0, "meaning": batch["payload"]["meaning"]}
