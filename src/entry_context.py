"""Frozen entry-policy ablations; additive prospective observations only."""
from __future__ import annotations

from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
import json

import pandas as pd

from src.data.database import (get_backtest_runs, get_cached_industry_research, get_cached_fundamentals,
                               get_cached_positioning, get_positioning_history, get_connection, get_watchlist)
from src.data.research_signals import canonical, digest, number, schema as signal_schema, timestamp, utcnow
from src.research_lab import rank_entries

VERSION = "entry-context-v2"
CONTRACT = {"version": VERSION, "horizons": {"1M": 21, "3M": 63},
            "cost_bps": [10, 30, 50], "embargo_days": 5, "warmup_dates": 3,
            "selection": "recorded_buy_market_ma200_or_sector_63d_top5_max2_per_sector",
            "market_average_sessions": 200, "sector_lookback_sessions": 63,
            "sector_slots": 5, "max_names_per_sector": 2, "sector_slot_weight": .2,
            "relative_strength_threshold_pct": 0, "cash_return_pct": 0,
            "promotion": "disabled", "bootstrap_seed": 20260924, "bootstrap_block": 2,
            "bootstrap_draws": 2000, "min_ci_cohorts": 10}
SECTOR_ETFS = {"Technology": "XLK", "Information Technology": "XLK", "Healthcare": "XLV",
    "Health Care": "XLV", "Financial Services": "XLF", "Financials": "XLF",
    "Consumer Cyclical": "XLY", "Consumer Discretionary": "XLY", "Consumer Defensive": "XLP",
    "Consumer Staples": "XLP", "Communication Services": "XLC", "Industrials": "XLI",
    "Energy": "XLE", "Utilities": "XLU", "Real Estate": "XLRE", "Basic Materials": "XLB", "Materials": "XLB"}


def close_series(history):
    if history is None or history.empty or "Close" not in history:
        return pd.Series(dtype=float, index=pd.DatetimeIndex([]))
    close = pd.to_numeric(history["Close"], errors="coerce").copy()
    close.index = pd.to_datetime(close.index).tz_localize(None).normalize()
    # Duplicate/corrupt bars cannot silently turn into a clean evaluation path.
    if close.index.has_duplicates:
        raise ValueError("duplicate_price_dates")
    return close.sort_index()


def price_features(history, cutoff):
    close = close_series(history).loc[lambda x: x.index <= pd.Timestamp(cutoff)]
    if close.empty or close.isna().any() or (close <= 0).any():
        return {}
    if (pd.Timestamp(cutoff) - close.index[-1]).days > 7:
        return {}
    def ret(n):
        return float((close.iloc[-1] / close.iloc[-n - 1] - 1) * 100) if len(close) > n else None
    return {"latest_price": float(close.iloc[-1]), "ma_200": float(close.tail(200).mean()) if len(close) >= 200 else None,
            "return_12m": ret(252), "return_1m": ret(21), "return_3m": ret(63),
            "price_date": close.index[-1].date().isoformat()}


def candidate_weights(cohort):
    rows = cohort["inputs"]
    if len({r["ticker"] for r in rows}) != len(rows):
        raise ValueError("duplicate_universe_ticker")
    tickers = [r["ticker"] for r in rows]
    if not tickers:
        return {"weights": {}, "unavailable": {"all": "empty_universe"}}
    buys = [r for r in rows if r.get("entry_signal") == "Buy candidate"]
    complete = all(number(r.get("entry_score")) is not None and r.get("entry_signal") in {"Buy candidate", "Watch", "Wait"} for r in rows)
    weights = {"SPY": {"SPY": 1.0}, "equal_weight_universe": {t: 1 / len(tickers) for t in tickers}}
    unavailable = {}
    v1 = rank_entries(rows)
    if not v1["excluded"]:
        weights["momentum_v1"] = {r["ticker"]: r["theoretical_weight"] for r in v1["rows"] if r["selected"]}
    if not complete:
        return {"weights": weights, "unavailable": {"current_policy": "incomplete_recorded_decisions"}}
    current = {r["ticker"]: 1 / len(buys) for r in buys} if buys else {}
    weights["current_policy"] = current
    market = cohort.get("market") or {}
    price, ma = number(market.get("latest_price")), number(market.get("ma_200"))
    if price is not None and ma is not None and price > 0 and ma > 0:
        weights["candidate_market"] = current.copy() if price > ma else {}
        weights["market_filter_only"] = weights["equal_weight_universe"].copy() if price > ma else {}
    else:
        unavailable["candidate_market"] = "missing_market_regime"
    market_return = number(market.get("return_3m"))
    sectors = cohort.get("sectors") or {}
    ranked = []
    for r in buys:
        etf = r.get("sector_etf")
        sr = number((sectors.get(etf) or {}).get("return_3m"))
        ar = number((r.get("metrics") or {}).get("return_3m"))
        if not etf or None in (sr, ar, market_return):
            unavailable["candidate_sector"] = "missing_original_sector_or_price_context"
            break
        ranked.append({**r, "stock_excess": ar - sr, "sector_excess": sr - market_return})
    if "candidate_sector" not in unavailable:
        ranked.sort(key=lambda r: (-r["stock_excess"], -r["sector_excess"], -r["entry_score"], r["ticker"]))
        for name, require_leadership in (("candidate_sector", True), ("sector_without_leadership", False)):
            counts, selected = Counter(), {}
            for r in ranked:
                if (len(selected) == 5 or r["stock_excess"] <= 0 or (require_leadership and r["sector_excess"] <= 0)
                        or counts[r["sector_etf"]] >= 2):
                    continue
                selected[r["ticker"]] = .2
                counts[r["sector_etf"]] += 1
            weights[name] = selected
    return {"weights": weights, "unavailable": unavailable}


def schema(db_path=None):
    signal_schema(db_path)
    with get_connection(db_path) as con:
        con.execute("""CREATE TABLE IF NOT EXISTS entry_context_snapshots (
            snapshot_id TEXT PRIMARY KEY, version TEXT NOT NULL, as_of_date TEXT NOT NULL,
            payload_json TEXT NOT NULL, UNIQUE(version,as_of_date))""")
        con.execute("""CREATE TABLE IF NOT EXISTS entry_context_reports (
            report_id TEXT PRIMARY KEY, version TEXT NOT NULL, source TEXT NOT NULL,
            horizon TEXT NOT NULL, observed_at TEXT NOT NULL, payload_json TEXT NOT NULL)""")
        con.execute("""CREATE TABLE IF NOT EXISTS entry_context_paths (
            snapshot_id TEXT NOT NULL,horizon TEXT NOT NULL,payload_json TEXT NOT NULL,
            observed_at TEXT NOT NULL, PRIMARY KEY(snapshot_id,horizon))""")


def build_snapshot(inputs, *, captured_at, market, sectors, evidence=None, excluded=None):
    timestamp(captured_at)
    cohort = {"version": VERSION, "contract": CONTRACT, "captured_at": captured_at,
        "as_of_date": captured_at[:10], "source": "prospective", "inputs": inputs,
        "market": market, "sectors": sectors, "evidence": evidence or {}, "excluded": excluded or []}
    cohort["output"] = candidate_weights(cohort)
    return {**cohort, "snapshot_id": digest(cohort)}


def replay(snapshot):
    payload = {k: v for k, v in snapshot.items() if k != "snapshot_id"}
    from src.scoring.current_policy import combine_current_decisions
    for row in snapshot.get("inputs", []):
        if row.get("policy_inputs"):
            outputs = combine_current_decisions(**row["policy_inputs"])
            if outputs["entry_score"] != row["entry_score"] or outputs["entry_signal"] != row["entry_signal"]:
                return False
    return (snapshot.get("contract") == CONTRACT and digest(payload) == snapshot.get("snapshot_id")
            and candidate_weights(snapshot) == snapshot.get("output"))


def save_snapshot(snapshot, db_path=None):
    if not replay(snapshot):
        raise ValueError("context_snapshot_replay_failed")
    schema(db_path)
    with get_connection(db_path) as con:
        return con.execute("INSERT OR IGNORE INTO entry_context_snapshots VALUES (?,?,?,?)",
            (snapshot["snapshot_id"], VERSION, snapshot["as_of_date"], canonical(snapshot))).rowcount == 1


def snapshots(db_path=None):
    schema(db_path)
    with get_connection(db_path) as con:
        return [json.loads(r[0]) for r in con.execute("SELECT payload_json FROM entry_context_snapshots WHERE version=? ORDER BY as_of_date", (VERSION,))]


def historical_inputs(db_path=None):
    by_date = defaultdict(dict)
    for r in get_backtest_runs(db_path=db_path):
        if r["ticker"].endswith("-USD") or r["ticker"] == "SPY":
            continue
        previous = by_date[r["as_of_date"]].get(r["ticker"])
        priority = (int(r.get("model_is_champion") or 0), str(r["model_version"]))
        if previous and previous["priority"] >= priority:
            continue
        raw = json.loads(r.get("inputs_json") or "{}")
        # Never backdate the current company profile into the legacy inputs.
        sector = ((raw.get("industry") or {}).get("profile") or {}).get("sector")
        by_date[r["as_of_date"]][r["ticker"]] = {"ticker": r["ticker"], "metrics": raw.get("metrics") or {},
            "entry_score": r["entry_score"], "entry_signal": r["entry_signal"], "model_version": r["model_version"],
            "sector_etf": SECTOR_ETFS.get(sector), "priority": priority, "decision_source": "recorded_legacy_simulation"}
    return [{"as_of_date": day, "source": "retrospective_unverified", "inputs": list(rows.values())}
            for day, rows in sorted(by_date.items())]


def capture_context(histories, evidence, db_path=None, *, now=None):
    from src.data.market_data import calculate_metrics
    from src.scoring.current_policy import combine_current_decisions
    from src.scoring.technical import calculate_technical_score
    from src.scoring.risk import calculate_risk_score, risk_score_details
    from src.scoring.valuation import calculate_valuation_score
    from src.scoring.industry import industry_entry_score
    from src.scoring.positioning import positioning_score_adjustments
    from src.backtesting import learned_score_adjustments
    from src.model_policy import governed_learning_adjustments
    from src.shadow_model import meaningful_valuation_available
    from src.model_registry import current_model_registration
    tickers = get_watchlist(db_path)
    supplied_now = now is not None
    now = now or datetime.now(timezone.utc)
    existing = next((s for s in snapshots(db_path) if s["as_of_date"] == now.date().isoformat()), None)
    if existing:
        return {"status": "captured", "snapshot_saved": False, "snapshot_id": existing["snapshot_id"],
                "inputs": len(existing["inputs"]), "excluded": len(existing["excluded"])}
    cutoff = (now.date() - timedelta(days=1)).isoformat()
    runs = defaultdict(list)
    for run in get_backtest_runs(db_path=db_path):
        runs[run["ticker"]].append(run)
    registration = current_model_registration()
    inputs, excluded = [], []
    for ticker in sorted(t for t in tickers if not t.endswith("-USD") and t != "SPY"):
        features = price_features(histories.get(ticker), cutoff)
        if not features or features.get("ma_200") is None:
            excluded.append({"ticker": ticker, "reason": "missing_completed_price_features"})
            continue
        history = histories[ticker].copy()
        idx = pd.to_datetime(history.index).tz_localize(None)
        history = history.loc[(idx < pd.Timestamp(now.date())) & (idx >= pd.Timestamp(now.date()) - pd.DateOffset(years=1))]
        metrics = calculate_metrics(history)
        technical = calculate_technical_score(metrics)
        risk = calculate_risk_score(metrics, history)
        industry_risk = min(100, risk + int(risk_score_details(metrics, history)["drawdown_penalty"] or 0))
        fundamentals = get_cached_fundamentals(ticker, db_path)
        research = get_cached_industry_research(ticker, db_path) or {}
        positioning = positioning_score_adjustments(get_cached_positioning(ticker, db_path), get_positioning_history(ticker, db_path), technical)
        learning = governed_learning_adjustments(learned_score_adjustments(runs[ticker]))
        policy_inputs = {"technical": technical, "valuation": calculate_valuation_score(fundamentals), "risk": risk,
            "industry_score": industry_entry_score(technical, industry_risk, research)["score"] if research else None,
            "valuation_available": meaningful_valuation_available(fundamentals),
            "entry_modifier": positioning["entry_adjustment"], "exit_modifier": positioning["exit_adjustment"],
            "learning_entry": learning["applied_entry_adjustment"], "learning_exit": learning["applied_exit_adjustment"]}
        outputs = combine_current_decisions(**policy_inputs)
        sector = (research.get("profile") or {}).get("sector")
        inputs.append({"ticker": ticker, "metrics": features, "entry_score": outputs["entry_score"],
            "entry_signal": outputs["entry_signal"], "decision_known_at": now.isoformat(), "policy_inputs": policy_inputs,
            "model_version": registration["model_version"], "model_config_hash": registration["config_hash"],
            "decision_source": "shared_dashboard_policy_completed_daily_prices", "sector": sector, "sector_etf": SECTOR_ETFS.get(sector),
            "context_observed_at": {"fundamentals": (fundamentals or {}).get("fetched_at"), "industry": research.get("fetched_at")},
            "sector_known_at": now.isoformat()})
    if len(inputs) < 5:
        return {"status": "insufficient_current_decisions", "snapshot_saved": False}
    captured_at = now if supplied_now else datetime.now(timezone.utc)
    for row in inputs:
        row["decision_known_at"] = captured_at.isoformat()
        row["sector_known_at"] = captured_at.isoformat()
    snapshot = build_snapshot(inputs, captured_at=captured_at.isoformat(),
        market=price_features(histories.get("SPY"), cutoff),
        sectors={etf: price_features(histories.get(etf), cutoff) for etf in sorted(set(SECTOR_ETFS.values()))},
        evidence=evidence, excluded=excluded)
    saved = save_snapshot(snapshot, db_path)
    return {"status": "captured", "snapshot_saved": saved, "inputs": len(inputs),
            "excluded": len(excluded), "snapshot_id": snapshot["snapshot_id"]}
