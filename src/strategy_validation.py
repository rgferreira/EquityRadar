"""Matched, non-overlapping daily-path economic validation of frozen entry rules."""
from __future__ import annotations

from collections import Counter, defaultdict
from datetime import date, timedelta
import json

import numpy as np
import pandas as pd

from src.data.database import get_connection
from src.data.research_signals import canonical, digest, utcnow
from src.entry_context import CONTRACT, VERSION, candidate_weights, close_series, price_features, replay, schema


def portfolio_path(paths, weights, round_trip_bps):
    """Weights budget entry fees; fixed shares, zero-interest cash, exit at block end."""
    if not 0 <= round_trip_bps <= 1000 or any(w < 0 for w in weights.values()) or sum(weights.values()) > 1 + 1e-9:
        raise ValueError("invalid_portfolio_contract")
    n = len(paths["SPY"])
    if any(len(v) != n or any(not np.isfinite(x) or x <= 0 for x in v) for v in paths.values()):
        raise ValueError("invalid_price_path")
    fee = round_trip_bps / 20000
    equity = np.full(n, 1 - sum(weights.values()), dtype=float)
    entry_notional = exit_notional = 0.0
    attribution = {}
    for ticker, weight in weights.items():
        prices = np.asarray(paths[ticker], dtype=float)
        invested = weight / (1 + fee)
        sleeve = invested * prices / prices[0]
        exit_notional += float(sleeve[-1])
        entry_notional += invested
        sleeve[-1] *= 1 - fee
        equity += sleeve
        attribution[ticker] = float((sleeve[-1] - weight) * 100)
    return {"equity": equity.tolist(), "net_return_pct": float((equity[-1] - 1) * 100),
            "traded_notional": entry_notional + exit_notional,
            "cost_pct": (entry_notional + exit_notional) * fee * 100,
            "attribution_pp": attribution}


def drawdown(equity):
    values = np.asarray([1.0, *equity], dtype=float)
    return float(np.min(values / np.maximum.accumulate(values) - 1) * 100)


def paired_block_interval(values):
    if len(values) < CONTRACT["min_ci_cohorts"]:
        return None
    data = np.asarray(values, dtype=float)
    rng = np.random.default_rng(CONTRACT["bootstrap_seed"])
    block = CONTRACT["bootstrap_block"]
    starts = rng.integers(0, len(data), size=(CONTRACT["bootstrap_draws"], (len(data) + block - 1) // block))
    indices = (starts[:, :, None] + np.arange(block)) % len(data)
    means = data[indices.reshape(len(starts), -1)[:, :len(data)]].mean(axis=1)
    return np.quantile(means, [.025, .975]).tolist()


def build_window(cohort, histories, horizon):
    """Require every declared input's complete SPY-session path, including unselected names."""
    sessions = CONTRACT["horizons"][horizon]
    tickers = [r["ticker"] for r in cohort["inputs"]]
    if len(tickers) < 5:
        return None, "fewer_than_five_inputs"
    if len(set(tickers)) != len(tickers):
        return None, "duplicate_universe"
    try:
        prices = {t: close_series(histories.get(t)) for t in ["SPY", *tickers]}
    except ValueError:
        return None, "duplicate_price_dates"
    market = prices["SPY"]
    future = market.index[market.index > pd.Timestamp(cohort["as_of_date"])]
    if len(future) <= sessions:
        return None, "horizon_not_mature_or_benchmark_missing"
    dates = future[:sessions + 1]
    if (dates[0].date() - date.fromisoformat(cohort["as_of_date"])).days > 7:
        return None, "execution_gap"
    path = {}
    for ticker, series in prices.items():
        aligned = series.reindex(dates)
        if aligned.isna().any() or not np.isfinite(aligned).all() or (aligned <= 0).any():
            return None, "incomplete_path_for_frozen_universe"
        path[ticker] = aligned.astype(float).tolist()
    return {"dates": [d.date().isoformat() for d in dates], "prices": path}, None


def evaluate(cohorts, histories, horizon="1M", *, db_path=None, persist_paths=False):
    if horizon not in CONTRACT["horizons"]:
        raise ValueError("unsupported_horizon")
    if persist_paths:
        schema(db_path)
    excluded, candidates, unavailable = Counter(), [], Counter()
    for raw in sorted(cohorts, key=lambda r: r["as_of_date"]):
        cohort = dict(raw)
        if cohort["source"] == "prospective" and not replay(cohort):
            excluded["invalid_frozen_snapshot"] += 1
            continue
        if cohort["source"] != "prospective":
            cohort["market"] = price_features(histories.get("SPY"), cohort["as_of_date"])
            cohort["sectors"] = {r["sector_etf"]: price_features(histories.get(r["sector_etf"]), cohort["as_of_date"])
                                 for r in cohort["inputs"] if r.get("sector_etf")}
        saved_path = None
        if persist_paths and cohort.get("snapshot_id"):
            with get_connection(db_path) as con:
                saved_path = con.execute("SELECT payload_json FROM entry_context_paths WHERE snapshot_id=? AND horizon=?",
                    (cohort["snapshot_id"], horizon)).fetchone()
        if saved_path:
            window, reason = json.loads(saved_path[0]), None
        else:
            window, reason = build_window(cohort, histories, horizon)
        if reason:
            excluded[reason] += 1
            continue
        if persist_paths and cohort.get("snapshot_id") and not saved_path:
            with get_connection(db_path) as con:
                con.execute("INSERT OR IGNORE INTO entry_context_paths VALUES (?,?,?,?)",
                    (cohort["snapshot_id"], horizon, canonical(window), utcnow()))
        output = candidate_weights(cohort)
        if "current_policy" not in output["weights"]:
            excluded["incomplete_current_policy_reference"] += 1
            continue
        unavailable.update(output["unavailable"].keys())
        candidates.append({"cohort": cohort, "window": window, "output": output})
    chosen, last_end = [], ""
    for item in candidates:
        cohort, window = item["cohort"], item["window"]
        embargo_cutoff = (date.fromisoformat(cohort["as_of_date"]) - timedelta(days=CONTRACT["embargo_days"])).isoformat()
        prior = [p["cohort"]["as_of_date"] for p in candidates if p["window"]["dates"][-1] < embargo_cutoff]
        if len(set(prior)) < CONTRACT["warmup_dates"]:
            excluded["insufficient_purged_prior_dates"] += 1
            continue
        if window["dates"][0] <= last_end:
            excluded["overlapping_test_window"] += 1
            continue
        item["purged_prior_dates"] = sorted(set(prior))
        chosen.append(item)
        last_end = window["dates"][-1]
    summary, curves, periods = [], [], []
    for cost in CONTRACT["cost_bps"]:
        by_strategy = defaultdict(list)
        for item in chosen:
            cohort, window = item["cohort"], item["window"]
            results = {name: portfolio_path(window["prices"], weights, cost)
                       for name, weights in item["output"]["weights"].items()}
            for name, values in results.items():
                weights = item["output"]["weights"][name]
                hits = [window["prices"][t][-1] / window["prices"][t][0] > window["prices"]["SPY"][-1] / window["prices"]["SPY"][0]
                        for t in weights if weights[t] > 0 and t != "SPY"]
                record = {"as_of_date": cohort["as_of_date"], "execution_date": window["dates"][0],
                    "end_date": window["dates"][-1], "strategy": name, "cost_bps": cost,
                    "net_return_pct": values["net_return_pct"], "excess_spy_pct": values["net_return_pct"] - results["SPY"]["net_return_pct"],
                    "excess_current_pct": values["net_return_pct"] - results["current_policy"]["net_return_pct"],
                    "entry_hit_rate_pct": sum(hits) / len(hits) * 100 if hits else None,
                    "selected_count": len(weights), "exposure_pct": sum(weights.values()) * 100,
                    "traded_notional": values["traded_notional"], "cost_pct": values["cost_pct"],
                    "max_drawdown_pct": drawdown(values["equity"]),
                    "sector_attribution_pp": {}, "purged_prior_dates": item["purged_prior_dates"]}
                sector_map = {r["ticker"]: r.get("sector_etf") or "Unknown (original context absent)" for r in cohort["inputs"]}
                for ticker, value in values["attribution_pp"].items():
                    sector = "Benchmark" if ticker == "SPY" else sector_map[ticker]
                    record["sector_attribution_pp"][sector] = record["sector_attribution_pp"].get(sector, 0) + value
                periods.append(record)
                by_strategy[name].append({"record": record, "equity": values["equity"], "item": item})
        for name, values in sorted(by_strategy.items()):
            equity, curve, records = 1.0, [], [v["record"] for v in values]
            for v in values:
                for day, wealth in zip(v["item"]["window"]["dates"], v["equity"]):
                    curve.append({"date": day, "equity": equity * wealth})
                equity *= v["equity"][-1]
            excess = [r["excess_spy_pct"] for r in records]
            current_excess = [r["excess_current_pct"] for r in records]
            hits = [r["entry_hit_rate_pct"] for r in records if r["entry_hit_rate_pct"] is not None]
            selected_names = set(t for v in values for t in v["item"]["output"]["weights"][name] if t != "SPY")
            loo = []
            for omitted in sorted(selected_names):
                diffs = []
                for v in values:
                    item = v["item"]
                    weights = {t: w for t, w in item["output"]["weights"][name].items() if t != omitted}
                    alt = portfolio_path(item["window"]["prices"], weights, cost)
                    spy = portfolio_path(item["window"]["prices"], {"SPY": 1.0}, cost)
                    diffs.append(alt["net_return_pct"] - spy["net_return_pct"])
                loo.append({"omitted": omitted, "mean_excess_spy_pct": float(np.mean(diffs))})
            summary.append({"strategy": name, "cost_bps": cost, "test_cohorts": len(values),
                "net_return_pct": (equity - 1) * 100, "max_drawdown_pct": drawdown([r["equity"] for r in curve]),
                "mean_excess_spy_pct": float(np.mean(excess)), "mean_excess_current_pct": float(np.mean(current_excess)),
                "excess_spy_exploratory_95ci": paired_block_interval(excess),
                "excess_current_exploratory_95ci": paired_block_interval(current_excess),
                "mean_entry_hit_rate_pct": float(np.mean(hits)) if hits else None,
                "mean_exposure_pct": float(np.mean([r["exposure_pct"] for r in records])),
                "mean_traded_notional": float(np.mean([r["traded_notional"] for r in records])),
                "positive_excess_cohorts": sum(v > 0 for v in excess),
                "worst_leave_one_name_out": min(loo, key=lambda r: r["mean_excess_spy_pct"]) if loo else None})
            curves.append({"strategy": name, "cost_bps": cost, "points": curve,
                           "note": "Theoretical closed daily paths; cash between test blocks. Same strategy's eligible test dates only."})
    return {"version": VERSION, "contract": CONTRACT, "horizon": horizon,
        "source": cohorts[0]["source"] if cohorts else "prospective", "capture_dates": len(cohorts),
        "mature_complete_dates": len(candidates), "test_cohorts": len(chosen), "exclusions": dict(excluded),
        "unavailable_candidates": dict(unavailable), "summary": summary, "periods": periods, "curves": curves,
        "dataset_signature": digest([{"cohort": i["cohort"], "window": i["window"]} for i in candidates]),
        "promotion_eligible": False, "status": "research_only" if chosen else "insufficient_evidence",
        "limitations": ["Legacy data and current adjusted price vintages are retrospective, never unseen out-of-sample evidence",
            "Watchlist selection/survivorship and discretionary entry/exit differences remain",
            "Non-overlapping blocks are not proven independent; exploratory intervals do not correct multiple testing",
            "Daily close drawdown omits intraday moves; no taxes, market impact or FX model",
            "Unavailable candidates are excluded explicitly; paired excess uses identical dates, total curves may span different dates"]}


def save_report(report, db_path=None):
    schema(db_path)
    report_id = digest(report)
    with get_connection(db_path) as con:
        con.execute("INSERT OR IGNORE INTO entry_context_reports VALUES (?,?,?,?,?,?)",
                    (report_id, VERSION, report["source"], report["horizon"], utcnow(), canonical(report)))
    return report_id


def latest_report(source, horizon, db_path=None):
    schema(db_path)
    with get_connection(db_path) as con:
        row = con.execute("""SELECT payload_json FROM entry_context_reports WHERE version=? AND source=? AND horizon=?
            ORDER BY observed_at DESC,rowid DESC LIMIT 1""", (VERSION, source, horizon)).fetchone()
    return json.loads(row[0]) if row else None
