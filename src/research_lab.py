"""Transparent, isolated entry-ranking research. Never changes live decision policy."""
from __future__ import annotations

from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime, timezone
import hashlib
import json
import math
from pathlib import Path
from threading import Lock

from src.data.outcome_maturation import get_current_outcome_labels as get_outcome_labels
from src.data.database import (
    claim_daily_refresh, daily_refresh_attempted, get_backtest_runs, get_connection,
     get_prediction_snapshots, get_watchlist, init_db,
)
from src.outcome_labels import TOTAL_COST_BPS, build_relative_outcome_label

VERSION = "entry-ranking-v1-research"
CONFIG = {
    "version": VERSION, "rank": "(1 + return_12m/100)/(1 + return_1m/100) - 1",
    "eligibility": "momentum_12_1 > 0 and latest_price > ma_200",
    "top_fraction": 0.2, "weighting": "equal theoretical slots; vacant slots earn zero cash return",
    "primary_horizon": "1M", "secondary_horizon": "3M", "cost_bps": TOTAL_COST_BPS,
    "execution": "next-common-tradable-session-close", "benchmark": "SPY",
    "cash_return_pct": 0.0, "promotion": "disabled; research only",
}
FAMILIES = [
    {"Family": "Price / entry", "Use now": "Continuous 12–1 rank + MA200 trend filter", "Validation needed": "Prospective excess return after costs"},
    {"Family": "Market / sector", "Use now": "SPY trend and sector context; no extra weight", "Validation needed": "Sector-neutral and regime ablations; vintage history"},
    {"Family": "Micro / quality / valuation", "Use now": "Existing company research remains explanatory", "Validation needed": "Verified publication times, no double counting"},
    {"Family": "Large flows / shorts", "Use now": "Existing FINRA and disclosed trades as context", "Validation needed": "Delay and direction; disclosure is not current institutional flow"},
    {"Family": "Options / Greeks", "Use now": "Existing aggregates only; Greeks unavailable", "Validation needed": "Strike / expiry / liquidity chain history; IV, skew and term structure"},
    {"Family": "Monetary policy / credit", "Use now": "Unavailable; no directional contribution", "Validation needed": "Official releases, surprises and point-in-time vintages"},
]


def _json(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)


def _number(value: object) -> float | None:
    try:
        number = float(value)
        return number if math.isfinite(number) else None
    except (ValueError, TypeError):
        return None


def rank_entries(inputs: list[dict[str, object]]) -> dict[str, object]:
    """One pure implementation for new captures and exact replay; missing is not bearish."""
    rows, excluded = [], []
    seen = set()
    for item in inputs:
        ticker = str(item["ticker"])
        if ticker in seen:
            raise ValueError("Duplicate ticker in research universe")
        seen.add(ticker)
        metrics = item.get("metrics") or {}
        price, ma, r12, r1 = [_number(metrics.get(k)) for k in ("latest_price", "ma_200", "return_12m", "return_1m")]
        if None in (price, ma, r12, r1) or price <= 0 or ma <= 0 or r1 <= -100 or r12 <= -100:
            excluded.append({"ticker": ticker, "reason": "missing_or_invalid_price_features"})
            continue
        momentum = ((1 + r12 / 100) / (1 + r1 / 100) - 1) * 100
        rows.append({"ticker": ticker, "momentum_12_1_pct": momentum,
                     "above_ma200": price > ma, "eligible": momentum > 0 and price > ma,
                     "entry_score_recorded": _number(item.get("entry_score"))})
    rows.sort(key=lambda r: (-r["momentum_12_1_pct"], r["ticker"]))
    slots = math.ceil(len(rows) * CONFIG["top_fraction"]) if rows else 0
    selected = [r["ticker"] for r in rows if r["eligible"]][:slots]
    for index, row in enumerate(rows, 1):
        row.update(rank=index, selected=row["ticker"] in selected,
                   theoretical_weight=(1 / slots if row["ticker"] in selected else 0))
    return {"rows": rows, "excluded": excluded, "slots": slots,
            "cash_weight": 1 - len(selected) / slots if slots else 1.0}


def build_snapshot(inputs: list[dict[str, object]], *, captured_at: str,
                   context: dict[str, object] | None = None) -> dict[str, object]:
    payload = {"config": CONFIG, "captured_at": captured_at, "as_of_date": captured_at[:10],
               "availability": "Observed by this application at capture; no historical known_at claim",
               "inputs": inputs, "context": context or {}, "output": rank_entries(inputs)}
    return {**payload, "snapshot_id": hashlib.sha256(_json(payload).encode()).hexdigest()}


def replay_snapshot(snapshot: dict[str, object]) -> bool:
    if snapshot.get("config") != CONFIG:
        return False
    payload = {key: value for key, value in snapshot.items() if key != "snapshot_id"}
    return (hashlib.sha256(_json(payload).encode()).hexdigest() == snapshot.get("snapshot_id")
            and rank_entries(snapshot["inputs"]) == snapshot["output"])


def context_summary(snapshot: dict[str, object]) -> dict[str, object]:
    """Describe frozen signal coverage and theoretical sector exposure, without weights."""
    market = snapshot.get("context", {}).get("market", {})
    price, average = _number(market.get("latest_price")), _number(market.get("ma_200"))
    sectors: dict[str, float] = defaultdict(float)
    by_ticker = {item["ticker"]: item for item in snapshot["inputs"]}
    options_coverage = industry_coverage = short_coverage = 0
    for row in snapshot["output"]["rows"]:
        context = by_ticker[row["ticker"]].get("context_only", {})
        industry = context.get("industry") or {}
        positioning = context.get("positioning") or {}
        industry_coverage += bool(industry)
        options_coverage += _number((positioning.get("options") or {}).get("put_call_oi_ratio")) is not None
        short_coverage += _number((positioning.get("short") or {}).get("shares_short")) is not None
        sector = str((industry.get("profile") or {}).get("sector") or "Unknown")
        if row["selected"]:
            sectors[sector] += row["theoretical_weight"] * 100
    return {"market_above_ma200": price > average if price is not None and average and average > 0 else None,
            "market_return_1m_pct": _number(market.get("return_1m")),
            "theoretical_sector_exposure_pct": dict(sectors),
            "coverage": {"rankable": len(snapshot["output"]["rows"]), "industry_context": industry_coverage,
                         "options_oi_aggregate": options_coverage, "reported_short_interest": short_coverage,
                         "option_greeks": 0, "monetary_surprises": 0},
            "role": "Context only. Coverage does not establish freshness, direction or predictive value."}


def _schema(db_path: str | Path | None) -> None:
    init_db(db_path)
    with get_connection(db_path) as con:
        con.execute("""CREATE TABLE IF NOT EXISTS entry_research_snapshots (
            snapshot_id TEXT PRIMARY KEY, strategy_version TEXT NOT NULL, as_of_date TEXT NOT NULL,
            payload_json TEXT NOT NULL, UNIQUE(strategy_version,as_of_date))""")
        con.execute("""CREATE TABLE IF NOT EXISTS entry_research_outcomes (
            snapshot_id TEXT NOT NULL, ticker TEXT NOT NULL, horizon TEXT NOT NULL,
            payload_json TEXT NOT NULL, observed_at TEXT NOT NULL,
            PRIMARY KEY(snapshot_id,ticker,horizon))""")


def save_snapshot(snapshot: dict[str, object], db_path: str | Path | None = None) -> bool:
    if not replay_snapshot(snapshot):
        raise ValueError("Research snapshot cannot be replayed exactly")
    _schema(db_path)
    with get_connection(db_path) as con:
        return con.execute("INSERT OR IGNORE INTO entry_research_snapshots VALUES (?, ?, ?, ?)",
                           (snapshot["snapshot_id"], VERSION, snapshot["as_of_date"], _json(snapshot))).rowcount == 1


def get_snapshots(db_path: str | Path | None = None) -> list[dict[str, object]]:
    _schema(db_path)
    with get_connection(db_path) as con:
        return [json.loads(r[0]) for r in con.execute(
            "SELECT payload_json FROM entry_research_snapshots WHERE strategy_version=? ORDER BY as_of_date", (VERSION,))]


def historical_cohorts(db_path: str | Path | None = None) -> list[dict[str, object]]:
    """Local retrospective diagnostics; selection and timestamps are explicitly unverified."""
    predictions = {str(p["prediction_id"]): p for p in get_prediction_snapshots(db_path=db_path)}
    labels = {str(l["prediction_id"]): l for l in get_outcome_labels(db_path=db_path)}
    runs = {(r["ticker"], r["as_of_date"], r["model_version"]): r for r in get_backtest_runs(db_path=db_path)}
    by_date = defaultdict(dict)
    for pid, p in predictions.items():
        if str(p["ticker"]).endswith("-USD") or p["ticker"] == "SPY":
            continue
        run = runs.get((p["ticker"], p["as_of_date"], p["model_version"]))
        if not run:
            continue
        # Deterministic preference for champion records; never choose by observed outcome.
        previous = by_date[p["as_of_date"]].get(p["ticker"])
        priority = (int(run.get("model_is_champion") or 0), str(p["model_version"]))
        if previous and previous["priority"] >= priority:
            continue
        inputs = json.loads(run.get("inputs_json") or "{}")
        by_date[p["as_of_date"]][p["ticker"]] = {
            "ticker": p["ticker"], "metrics": inputs.get("metrics") or {},
            "entry_score": run.get("entry_score"), "label": labels.get(pid), "priority": priority,
        }
    return [{"as_of_date": day, "inputs": list(rows.values()), "source": "retrospective_unverified"}
            for day, rows in sorted(by_date.items())]


def prospective_cohorts(db_path: str | Path | None = None) -> list[dict[str, object]]:
    snapshots = get_snapshots(db_path)
    with get_connection(db_path) as con:
        observations = {(r["snapshot_id"], r["ticker"], r["horizon"]): json.loads(r["payload_json"])
                        for r in con.execute("SELECT * FROM entry_research_outcomes")}
    result = []
    for snapshot in snapshots:
        inputs = []
        for item in snapshot["inputs"]:
            labels = [observations.get((snapshot["snapshot_id"], item["ticker"], h)) for h in ("1M", "3M")]
            available = next((l for l in labels if l), None)
            label = dict(available) if available else None
            if label:
                label["outcomes"] = {h: (l or {}).get("outcomes", {}).get(h) for h, l in zip(("1M", "3M"), labels)}
            inputs.append({**item, "label": label})
        result.append({"as_of_date": snapshot["as_of_date"], "inputs": inputs, "source": "prospective"})
    return result


def compare_strategies(cohorts: list[dict[str, object]], horizon: str = "1M") -> dict[str, object]:
    """Compare fixed strategies on complete, matched, non-overlapping cohort windows.

    Eligibility is fixed before inspecting outcomes. If any input-eligible security
    lacks a matching outcome, the whole date is withheld instead of survivor filtering.
    These are cohort-return diagnostics, not a reconstructed tradable equity curve.
    """
    if horizon not in ("1M", "3M"):
        raise ValueError("Unsupported research horizon")
    rejected, periods = Counter(), []
    last_end = ""
    for cohort in sorted(cohorts, key=lambda c: c["as_of_date"]):
        ranking = rank_entries(cohort["inputs"])
        rows = ranking["rows"]
        if len(rows) < 5:
            rejected["fewer_than_five_input_eligible_securities"] += 1
            continue
        source = {r["ticker"]: r for r in cohort["inputs"]}
        labels = [source[r["ticker"]].get("label") for r in rows]
        if any(not l or not l.get("outcomes", {}).get(horizon) for l in labels):
            rejected["incomplete_outcomes_for_frozen_universe"] += 1
            continue
        windows = {(l.get("benchmark_ticker"), l.get("timing_convention"), l.get("cost_bps"),
                    l.get("execution_date"), l["outcomes"][horizon].get("end_date")) for l in labels}
        if len(windows) != 1:
            rejected["inconsistent_execution_or_label_contract"] += 1
            continue
        benchmark, timing, cost, start, end = next(iter(windows))
        if benchmark != "SPY" or timing != CONFIG["execution"] or cost != CONFIG["cost_bps"] or not start or not end or start <= cohort["as_of_date"] or end <= start:
            rejected["unsupported_label_contract"] += 1
            continue
        if start <= last_end:
            rejected["overlapping_evaluation_window"] += 1
            continue
        outcomes = [l["outcomes"][horizon] for l in labels]
        br = [_number(o.get("benchmark_return_pct")) for o in outcomes]
        sr = [_number(o.get("security_return_pct")) for o in outcomes]
        if None in br + sr or max(br) - min(br) > 0.00001:
            rejected["invalid_or_inconsistent_returns"] += 1
            continue
        n, slots = len(rows), ranking["slots"]
        strategies = {
            VERSION: {r["ticker"]: r["theoretical_weight"] for r in rows},
            "equal_weight_universe": {r["ticker"]: 1 / n for r in rows},
            "momentum_without_trend_filter": {r["ticker"]: 1 / slots if i < slots else 0 for i, r in enumerate(rows)},
            "trend_only_with_cash": {r["ticker"]: 1 / n if r["above_ma200"] else 0 for r in rows},
        }
        if all(r["entry_score_recorded"] is not None for r in rows):
            scored = sorted(rows, key=lambda r: (-r["entry_score_recorded"], r["ticker"]))
            strategies["recorded_entry_score_rank_diagnostic"] = {r["ticker"]: 1 / slots if i < slots else 0 for i, r in enumerate(scored)}
        returns = dict(zip((r["ticker"] for r in rows), sr))
        metrics = {}
        for name, weights in strategies.items():
            net = sum(w * (returns[t] - cost / 100) for t, w in weights.items())
            selected = [t for t, w in weights.items() if w > 0]
            benchmark_net = br[0] - cost / 100
            metrics[name] = {"net_return_pct": net, "excess_vs_net_benchmark_pct": net - benchmark_net,
                             "exposure": sum(weights.values()), "selected_count": len(selected),
                             "entry_hit_rate_pct": (sum(returns[t] > br[0] for t in selected) / len(selected) * 100 if selected else None)}
        metrics["SPY"] = {"net_return_pct": br[0] - cost / 100, "excess_vs_net_benchmark_pct": 0,
                          "exposure": 1, "selected_count": 1, "entry_hit_rate_pct": None}
        periods.append({"as_of_date": cohort["as_of_date"], "execution_date": start, "end_date": end,
                        "universe_size": n, "input_exclusions": len(ranking["excluded"]), "strategies": metrics})
        last_end = end
    summary = []
    names = sorted({name for p in periods for name in p["strategies"]})
    for name in names:
        values = [p["strategies"][name] for p in periods if name in p["strategies"]]
        hits = [v["entry_hit_rate_pct"] for v in values if v["entry_hit_rate_pct"] is not None]
        summary.append({"strategy": name, "cohorts": len(values),
                        "mean_net_return_pct": sum(v["net_return_pct"] for v in values) / len(values),
                        "mean_excess_pct": sum(v["excess_vs_net_benchmark_pct"] for v in values) / len(values),
                        "mean_exposure_pct": sum(v["exposure"] for v in values) / len(values) * 100,
                        "mean_entry_hit_rate_pct": sum(hits) / len(hits) if hits else None})
    return {"version": VERSION, "horizon": horizon, "candidate_dates": len(cohorts),
            "evaluated_nonoverlapping_cohorts": len(periods), "exclusions": dict(rejected),
            "summary": summary, "periods": periods, "promotion_eligible": False,
            "status": "insufficient_evidence" if len(periods) < 10 else "descriptive_research_only",
            "drawdown": None, "limitations": ["Historical selection / survivorship and known_at are unverified",
            "Cohorts are non-overlapping; statistical independence is not established",
            "Mean cohort returns are not annualized alpha or a portfolio equity curve",
            "10 bps round trip is an assumption; taxes, slippage and FX are not modeled"]}


_capture_pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix="entry-research")
_capture_lock = Lock()
_capture_future = None


def capture_and_label(db_path: str | Path | None = None) -> dict[str, object]:
    from src.data.price_cache import fetch_cached_price_history
    from src.data.market_data import calculate_metrics
    from src.data.database import get_cached_industry_research, get_cached_positioning
    import pandas as pd
    tickers = [t for t in get_watchlist(db_path) if not t.endswith("-USD") and t != "SPY"]
    now = datetime.now(timezone.utc)
    old_snapshots = get_snapshots(db_path)
    with get_connection(db_path) as con:
        completed = {(r[0], r[1], r[2]) for r in con.execute(
            "SELECT snapshot_id,ticker,horizon FROM entry_research_outcomes")}
    pending_tickers = {item["ticker"] for old in old_snapshots for item in old["inputs"]
                       if any((old["snapshot_id"], item["ticker"], h) not in completed for h in ("1M", "3M"))}
    histories, inputs = {}, []
    with ThreadPoolExecutor(max_workers=4) as pool:
        pending = {pool.submit(fetch_cached_price_history, t, period="3y", db_path=db_path, force_refresh=True): t
                   for t in sorted(set(tickers + ["SPY"]) | pending_tickers)}
        for future in as_completed(pending):
            symbol = pending[future]
            try:
                history = future.result()
                # Never capture today's potentially partial daily bar.
                index = pd.to_datetime(history.index).tz_localize(None)
                histories[symbol] = history.loc[index < pd.Timestamp(now.date())]
            except Exception:
                pass
    for ticker in sorted(tickers):
        history = histories.get(ticker)
        metrics = calculate_metrics(history.tail(253)) if history is not None and not history.empty else {}
        research = get_cached_industry_research(ticker, db_path) or {}
        inputs.append({"ticker": ticker, "metrics": metrics,
                       "price_observed_date": str(history.index[-1]) if history is not None and not history.empty else None,
                       "price_source": "yfinance adjusted daily; previous completed date only",
                       "context_only": {"industry": research, "positioning": get_cached_positioning(ticker, db_path)}})
    market = histories.get("SPY")
    snapshot = build_snapshot(inputs, captured_at=datetime.now(timezone.utc).isoformat(), context={
        "market": calculate_metrics(market.tail(253)) if market is not None and not market.empty else {},
        "families": FAMILIES, "declared_universe": sorted(tickers), "universe_policy": "current personal watchlist; selection bias unresolved"})
    saved = save_snapshot(snapshot, db_path)
    labels_created = 0
    # New horizons are independent immutable records; 1M does not block later 3M.
    for old in old_snapshots:
        if (now.date() - date.fromisoformat(old["as_of_date"])).days < 21:
            continue
        for item in old["inputs"]:
            ticker = item["ticker"]
            if ticker not in histories or market is None or all(
                (old["snapshot_id"], ticker, h) in completed for h in ("1M", "3M")
            ):
                continue
            label = build_relative_outcome_label(prediction_id=old["snapshot_id"] + ":" + ticker,
                ticker=ticker, as_of_date=old["as_of_date"], security_history=histories[ticker],
                benchmark_history=market, benchmark_ticker="SPY")
            for horizon in ("1M", "3M"):
                if label["outcomes"].get(horizon):
                    with get_connection(db_path) as con:
                        labels_created += con.execute("INSERT OR IGNORE INTO entry_research_outcomes VALUES (?, ?, ?, ?, ?)",
                            (old["snapshot_id"], ticker, horizon, _json(label), datetime.now(timezone.utc).isoformat())).rowcount
    return {"snapshot_saved": saved, "inputs": len(inputs), "rankable": len(snapshot["output"]["rows"]),
            "labels_created": labels_created}


def schedule_capture(db_path: str | Path | None = None) -> bool:
    global _capture_future
    day = datetime.now(timezone.utc).date().isoformat()
    if not get_watchlist(db_path) or daily_refresh_attempted(VERSION, day, db_path):
        return False
    with _capture_lock:
        if _capture_future and not _capture_future.done():
            return False
        if not claim_daily_refresh(VERSION, day, db_path):
            return False
        _capture_future = _capture_pool.submit(capture_and_label, db_path)
    return True
