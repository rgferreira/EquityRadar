"""Immutable risk-sizing research and date-balanced economic score diagnostics."""
from __future__ import annotations

from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
import json

import numpy as np
import pandas as pd

from src.data.database import get_connection
from src.data.research_signals import canonical, digest, number, timestamp, utcnow
from src.entry_context import candidate_weights, close_series, replay as replay_parent, schema as parent_schema
from src.strategy_validation import build_window, drawdown, evaluate, paired_block_interval, portfolio_path

VERSION = "entry-risk-v3"
CONTRACT = {"version": VERSION, "registered_on": "2026-09-26", "vol_sessions": 60,
            "annual_sessions": 252, "name_cap": .2, "sector_cap": .4,
            "vol_zero_tolerance": 1e-8, "max_price_age_days": 7,
            "score_edges": [0, 20, 40, 60, 80, 100], "promotion": "disabled"}


def risk_features(histories, tickers, cutoff):
    """Exact trailing common sessions; nothing after cutoff enters the estimate."""
    try:
        market = close_series(histories.get("SPY"))
    except ValueError:
        market = pd.Series(dtype=float, index=pd.DatetimeIndex([]))
    dates = market.index[market.index <= pd.Timestamp(cutoff)][-(CONTRACT["vol_sessions"] + 1):]
    features = {}
    for ticker in tickers:
        try:
            prices = close_series(histories.get(ticker)).reindex(dates)
            if (len(dates) != 61 or (pd.Timestamp(cutoff) - dates[-1]).days > CONTRACT["max_price_age_days"]
                    or prices.isna().any() or not np.isfinite(prices).all() or (prices <= 0).any()):
                raise ValueError("missing_complete_trailing_prices")
            vol = float(np.log(prices).diff().dropna().std(ddof=1) * np.sqrt(CONTRACT["annual_sessions"]))
            if not np.isfinite(vol) or vol <= CONTRACT["vol_zero_tolerance"]:
                raise ValueError("zero_or_invalid_volatility")
            features[ticker] = {"annual_vol": vol, "dates": [d.date().isoformat() for d in dates],
                                "prices": prices.astype(float).tolist()}
        except ValueError as exc:
            features[ticker] = {"unavailable": str(exc)}
    return features


def risk_weights(parent, features):
    base = candidate_weights(parent)["weights"].get("current_policy")
    if base is None:
        return {"weights": {}, "unavailable": {"candidate_risk": "incomplete_current_policy"}}
    if not base:
        return {"weights": {"candidate_risk": {}, "candidate_risk_sector": {}}, "unavailable": {}}
    inverse = {}
    for ticker in base:
        vol = number(features.get(ticker, {}).get("annual_vol"))
        if vol is None or vol <= CONTRACT["vol_zero_tolerance"]:
            return {"weights": {}, "unavailable": {"candidate_risk": "missing_valid_trailing_volatility"}}
        inverse[ticker] = 1 / vol
    total = sum(inverse.values())
    weights = {t: min(v / total, CONTRACT["name_cap"]) for t, v in inverse.items()}
    result = {"weights": {"candidate_risk": weights}, "unavailable": {}}
    sectors = {r["ticker"]: r.get("sector_etf") for r in parent["inputs"]}
    if any(not sectors.get(t) for t in base):
        result["unavailable"]["candidate_risk_sector"] = "missing_original_sector"
        return result
    totals = defaultdict(float)
    for ticker, weight in weights.items():
        totals[sectors[ticker]] += weight
    result["weights"]["candidate_risk_sector"] = {
        t: w * min(1, CONTRACT["sector_cap"] / totals[sectors[t]]) for t, w in weights.items()}
    return result


def schema(db_path=None):
    parent_schema(db_path)
    with get_connection(db_path) as con:
        con.execute("""CREATE TABLE IF NOT EXISTS entry_risk_snapshots (
            snapshot_id TEXT PRIMARY KEY, version TEXT NOT NULL, as_of_date TEXT NOT NULL,
            payload_json TEXT NOT NULL, UNIQUE(version,as_of_date))""")
        con.execute("""CREATE TABLE IF NOT EXISTS entry_risk_reports (
            report_id TEXT PRIMARY KEY, version TEXT NOT NULL, source TEXT NOT NULL,
            horizon TEXT NOT NULL, observed_at TEXT NOT NULL, payload_json TEXT NOT NULL)""")


def build_snapshot(parent, histories, captured_at):
    now = timestamp(captured_at)
    if (now.date().isoformat() != parent["as_of_date"] or timestamp(parent["captured_at"]) > now
            or now.date().isoformat() < CONTRACT["registered_on"] or not replay_parent(parent)):
        raise ValueError("not_a_current_prospective_parent")
    features = risk_features(histories, [r["ticker"] for r in parent["inputs"]],
                             (now.date() - timedelta(days=1)).isoformat())
    data = {"version": VERSION, "contract": CONTRACT, "source": "prospective",
            "as_of_date": now.date().isoformat(), "captured_at": now.isoformat(),
            "parent": parent, "features": features, "output": risk_weights(parent, features)}
    return {**data, "snapshot_id": digest(data)}


def replay(snapshot):
    try:
        payload = {k: v for k, v in snapshot.items() if k != "snapshot_id"}
        parent = snapshot["parent"]
        now = timestamp(snapshot["captured_at"])
        if (snapshot["version"] != VERSION or snapshot["source"] != "prospective"
                or snapshot["contract"] != CONTRACT or digest(payload) != snapshot["snapshot_id"]
                or not replay_parent(parent) or parent["as_of_date"] != now.date().isoformat()
                or snapshot["as_of_date"] != parent["as_of_date"]
                or timestamp(parent["captured_at"]) > now or snapshot["as_of_date"] < CONTRACT["registered_on"]):
            return False
        for feature in snapshot["features"].values():
            if "unavailable" in feature:
                continue
            prices = np.asarray(feature["prices"], dtype=float)
            dates = feature["dates"]
            if (len(prices) != 61 or len(dates) != 61 or sorted(set(dates)) != dates
                    or dates[-1] >= snapshot["as_of_date"] or not np.isfinite(prices).all() or (prices <= 0).any()):
                return False
            vol = float(np.std(np.diff(np.log(prices)), ddof=1) * np.sqrt(CONTRACT["annual_sessions"]))
            if not np.isclose(vol, feature["annual_vol"], rtol=1e-12, atol=0):
                return False
        return snapshot["output"] == risk_weights(parent, snapshot["features"])
    except (KeyError, ValueError, TypeError):
        return False


def snapshots(db_path=None):
    schema(db_path)
    with get_connection(db_path) as con:
        return [json.loads(r[0]) for r in con.execute(
            "SELECT payload_json FROM entry_risk_snapshots WHERE version=? ORDER BY as_of_date", (VERSION,))]


def capture_overview(db_path=None):
    """Bound page reads to the latest payload; never load years of raw inputs."""
    from src.entry_context import VERSION as PARENT_VERSION
    schema(db_path)
    result = {}
    with get_connection(db_path) as con:
        for name, table, version in (("v2", "entry_context_snapshots", PARENT_VERSION),
                                      ("v3", "entry_risk_snapshots", VERSION)):
            count = con.execute(f"SELECT COUNT(*) FROM {table} WHERE version=?", (version,)).fetchone()[0]
            row = con.execute(f"SELECT payload_json FROM {table} WHERE version=? ORDER BY as_of_date DESC LIMIT 1",
                              (version,)).fetchone()
            latest = json.loads(row[0]) if row else None
            result[name] = {"count": count, "latest": {k: latest[k] for k in ("captured_at", "output")} if latest else None}
    return result


def capture(parents, histories, db_path=None, *, now=None):
    now = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    day = now.date().isoformat()
    existing = next((s for s in snapshots(db_path) if s["as_of_date"] == day), None)
    if existing:
        return {"status": "captured", "saved": False, "snapshot_id": existing["snapshot_id"]}
    parent = next((p for p in parents if p["as_of_date"] == day), None)
    if not parent:
        return {"status": "awaiting_current_parent", "saved": False}
    snapshot = build_snapshot(parent, histories, now.isoformat())
    if not replay(snapshot):
        raise ValueError("risk_snapshot_replay_failed")
    with get_connection(db_path) as con:
        saved = con.execute("INSERT OR IGNORE INTO entry_risk_snapshots VALUES (?,?,?,?)",
            (snapshot["snapshot_id"], VERSION, day, canonical(snapshot))).rowcount == 1
    return {"status": "captured", "saved": saved, "snapshot_id": snapshot["snapshot_id"]}


def unit_outcome(prices, benchmark, cost):
    fee = cost / 20000
    net = np.asarray(prices) / prices[0] * (1 - fee) / (1 + fee) - 1
    spy = benchmark[-1] / benchmark[0] * (1 - fee) / (1 + fee) - 1
    return {"net_return_pct": float(net[-1] * 100), "excess_spy_pp": float((net[-1] - spy) * 100),
            "mae_pct": float(min(0, net.min()) * 100), "mfe_pct": float(max(0, net.max()) * 100),
            "giveback_pp": float((max(0, net.max()) - net[-1]) * 100)}


def loss_summary(rows):
    returns = [r["net_return_pct"] for r in rows]
    wins, losses = [r for r in returns if r > 0], [r for r in returns if r < 0]
    mean_win = float(np.mean(wins)) if wins else None
    mean_loss = float(np.mean(losses)) if losses else None
    return {"entries": len(rows), "dates": len({r["as_of_date"] for r in rows}),
            "win_rate_pct": len(wins) / len(rows) * 100 if rows else None,
            "mean_win_pct": mean_win, "mean_loss_pct": mean_loss,
            "payoff_ratio": mean_win / abs(mean_loss) if wins and losses else None,
            "pooled_expectancy_pct": float(np.mean(returns)) if returns else None,
            "mean_mae_pct": float(np.mean([r["mae_pct"] for r in rows])) if rows else None,
            "mean_mfe_pct": float(np.mean([r["mfe_pct"] for r in rows])) if rows else None,
            "mean_giveback_pp": float(np.mean([r["giveback_pp"] for r in rows])) if rows else None}


def score_diagnostics(rows):
    groups = defaultdict(lambda: defaultdict(list))
    populations = defaultdict(lambda: defaultdict(list))
    excluded = 0
    edges = CONTRACT["score_edges"]
    for row in rows:
        score = number(row["entry_score"])
        if score is None or not 0 <= score <= 100:
            excluded += 1
            continue
        index = min(int(score // 20), 4)
        label = f"[{edges[index]},{edges[index+1]}" + ("]" if index == 4 else ")")
        for selection in (["all_inputs", "buys"] if row["selected"] else ["all_inputs"]):
            groups[(selection, label)][row["as_of_date"]].append(row)
            populations[selection][row["as_of_date"]].append(row)
    output = []
    for (selection, band), by_date in sorted(groups.items()):
        dates = sorted(by_date)
        excess = [float(np.mean([r["excess_spy_pp"] for r in by_date[d]])) for d in dates]
        output.append({"selection": selection, "score_band": band, "dates": len(dates),
            "observations": sum(len(v) for v in by_date.values()), "mean_excess_spy_pp": float(np.mean(excess)),
            "excess_exploratory_95ci": paired_block_interval(excess),
            "date_balanced_hit_pct": float(np.mean([np.mean([r["excess_spy_pp"] > 0 for r in by_date[d]]) for d in dates]) * 100),
            "mean_net_return_pct": float(np.mean([np.mean([r["net_return_pct"] for r in by_date[d]]) for d in dates])),
            "mean_mae_pct": float(np.mean([np.mean([r["mae_pct"] for r in by_date[d]]) for d in dates])),
            "model_versions": sorted({str(r.get("model_version", "unknown")) for v in by_date.values() for r in v})})
    ordering, paired_bands = [], []
    for selection, by_date in sorted(populations.items()):
        correlations = []
        for day, values in sorted(by_date.items()):
            if len(values) < 5:
                continue
            scores = pd.Series([r["entry_score"] for r in values], dtype=float).rank()
            excess = pd.Series([r["excess_spy_pp"] for r in values], dtype=float).rank()
            if scores.nunique() > 1 and excess.nunique() > 1:
                correlations.append(float(scores.corr(excess)))
        ordering.append({"selection": selection, "dates": len(correlations),
            "mean_within_date_rank_ic": float(np.mean(correlations)) if correlations else None,
            "rank_ic_exploratory_95ci": paired_block_interval(correlations)})
        labels = sorted(band for sel, band in groups if sel == selection)
        for lower, upper in zip(labels, labels[1:]):
            lo, hi = groups[(selection, lower)], groups[(selection, upper)]
            shared = sorted(set(lo) & set(hi))
            differences = [float(np.mean([r["excess_spy_pp"] for r in hi[d]])
                                 - np.mean([r["excess_spy_pp"] for r in lo[d]])) for d in shared]
            paired_bands.append({"selection": selection, "lower_band": lower, "upper_band": upper,
                "shared_dates": len(shared), "upper_minus_lower_excess_pp": float(np.mean(differences)) if differences else None,
                "difference_exploratory_95ci": paired_block_interval(differences)})
    return {"bands": output, "ordering": ordering, "paired_bands": paired_bands,
            "excluded_scores": excluded, "probability_calibration": False}


def _window(parent, histories, horizon, db_path, persist_paths):
    if persist_paths and parent.get("snapshot_id"):
        with get_connection(db_path) as con:
            row = con.execute("SELECT payload_json FROM entry_context_paths WHERE snapshot_id=? AND horizon=?",
                              (parent["snapshot_id"], horizon)).fetchone()
        if row:
            return json.loads(row[0])
    return build_window(parent, histories, horizon)[0]


def evaluate_risk(cohorts, histories, horizon="1M", *, source="retrospective_unverified", db_path=None, persist_paths=False):
    """Prospective input is v3 snapshots; retrospective input is original v2 cohorts."""
    invalid = 0
    if source == "prospective":
        valid = [s for s in cohorts if replay(s)]
        invalid = len(cohorts) - len(valid)
        parents = [s["parent"] for s in valid]
        features = {s["as_of_date"]: s["features"] for s in valid}
    else:
        parents = cohorts
        features = {p["as_of_date"]: risk_features(histories, [r["ticker"] for r in p["inputs"]], p["as_of_date"]) for p in parents}
    base = evaluate(parents, histories, horizon, db_path=db_path, persist_paths=persist_paths)
    eligible = {r["as_of_date"] for r in base["periods"] if r["strategy"] == "current_policy" and r["cost_bps"] == 10}
    chosen = [p for p in parents if p["as_of_date"] in eligible]
    unavailable, periods, curves, summaries, diagnostics = Counter(), [], [], [], {}
    by_strategy = defaultdict(list)
    windows = {p["as_of_date"]: _window(p, histories, horizon, db_path, persist_paths) for p in chosen}
    for p in chosen:
        unavailable.update(risk_weights(p, features[p["as_of_date"]])["unavailable"].values())
    for cost in base["contract"]["cost_bps"]:
        entries = []
        for parent in chosen:
            day = parent["as_of_date"]
            window = windows[day]
            prices = window["prices"]
            current = candidate_weights(parent)["weights"]["current_policy"]
            for row in parent["inputs"]:
                outcome = unit_outcome(prices[row["ticker"]], prices["SPY"], cost)
                entries.append({"as_of_date": day, "ticker": row["ticker"], "entry_score": row.get("entry_score"),
                    "model_version": row.get("model_version", "unknown"), "sector": row.get("sector_etf") or "Unknown",
                    "selected": row["ticker"] in current, "contribution_pp": current.get(row["ticker"], 0) * outcome["net_return_pct"], **outcome})
            candidates = risk_weights(parent, features[day])["weights"]
            for candidate, weights in candidates.items():
                exposure = sum(weights.values())
                strategies = {candidate: weights, "current_policy": current, "SPY": {"SPY": 1.0},
                    "current_matched_exposure": {t: w * exposure for t, w in current.items()},
                    "SPY_matched_exposure": {"SPY": exposure}}
                results = {name: portfolio_path(prices, w, cost) for name, w in strategies.items()}
                for name, result in results.items():
                    record = {"comparison": candidate, "strategy": name, "cost_bps": cost, "as_of_date": day,
                        "execution_date": window["dates"][0], "end_date": window["dates"][-1],
                        "exposure_pct": sum(strategies[name].values()) * 100,
                        "net_return_pct": result["net_return_pct"], "max_drawdown_pct": drawdown(result["equity"]),
                        "excess_spy_pp": result["net_return_pct"] - results["SPY"]["net_return_pct"],
                        "excess_current_pp": result["net_return_pct"] - results["current_policy"]["net_return_pct"],
                        "excess_matched_current_pp": result["net_return_pct"] - results["current_matched_exposure"]["net_return_pct"]}
                    periods.append(record)
                    by_strategy[(candidate, name, cost)].append((record, result["equity"], window["dates"]))
        buys = [r for r in entries if r["selected"]]
        losses = defaultdict(float)
        for row in buys:
            losses[row["ticker"]] += max(0, -row["contribution_pp"])
        total_loss = sum(losses.values())
        diagnostics[str(cost)] = {"losses": loss_summary(buys), "score": score_diagnostics(entries),
            "loss_concentration": [{"ticker": t, "gross_loss_contribution_pp": v,
                "share_of_gross_losses_pct": v / total_loss * 100 if total_loss else 0}
                for t, v in sorted(losses.items(), key=lambda x: (-x[1], x[0])) if v > 0],
            "worst_entries": sorted(buys, key=lambda r: (r["contribution_pp"], r["as_of_date"], r["ticker"]))[:10]}
    for (comparison, name, cost), items in sorted(by_strategy.items()):
        equity, points = 1.0, []
        for record, wealth, dates in items:
            points.extend({"date": day, "equity": equity * value} for day, value in zip(dates, wealth))
            equity *= wealth[-1]
        rows = [i[0] for i in items]
        summary = {"comparison": comparison, "strategy": name, "cost_bps": cost, "test_cohorts": len(rows),
            "net_return_pct": (equity - 1) * 100, "max_drawdown_pct": drawdown([p["equity"] for p in points]),
            "mean_exposure_pct": float(np.mean([r["exposure_pct"] for r in rows]))}
        for metric in ("excess_spy_pp", "excess_current_pp", "excess_matched_current_pp"):
            values = [r[metric] for r in rows]
            summary[f"mean_{metric}"] = float(np.mean(values))
            summary[f"{metric}_exploratory_95ci"] = paired_block_interval(values)
        summaries.append(summary)
        curves.append({"comparison": comparison, "strategy": name, "cost_bps": cost, "points": points})
    return {"version": VERSION, "contract": CONTRACT, "evaluation_contract": base["contract"], "source": source,
        "horizon": horizon, "capture_dates": len(parents), "test_cohorts": len(chosen), "invalid_snapshots": invalid,
        "exclusions": base["exclusions"], "unavailable_risk": dict(unavailable), "summary": summaries,
        "periods": periods, "curves": curves, "diagnostics": diagnostics, "promotion_eligible": False,
        "status": "research_only" if chosen else "insufficient_evidence",
        "dataset_signature": digest({"parent": base["dataset_signature"], "risk_features": features}),
        "limitations": [*base["limitations"], "All C/control curves are paired within their comparison set",
            "MAE/MFE are close-based hypothetical liquidation paths, not executable exit forecasts",
            "Score bands are date-balanced descriptive slices, not calibrated probabilities",
            "Loss payoff statistics pool trades; observations are correlated and no trade-level significance is claimed"]}


def save_report(report, db_path=None):
    schema(db_path)
    report_id = digest(report)
    with get_connection(db_path) as con:
        con.execute("INSERT OR IGNORE INTO entry_risk_reports VALUES (?,?,?,?,?,?)",
            (report_id, VERSION, report["source"], report["horizon"], utcnow(), canonical(report)))
    return report_id


def latest_report(source, horizon, db_path=None):
    schema(db_path)
    with get_connection(db_path) as con:
        row = con.execute("""SELECT payload_json FROM entry_risk_reports WHERE version=? AND source=? AND horizon=?
            ORDER BY observed_at DESC,rowid DESC LIMIT 1""", (VERSION, source, horizon)).fetchone()
    return json.loads(row[0]) if row else None


def run_research(histories, parents, legacy=None, db_path=None):
    from src.data.research_signals import record_status
    record_status("pipeline", VERSION, "running", db_path=db_path)
    try:
        captured = capture(parents, histories, db_path)
        reports = []
        sources = [("prospective", snapshots(db_path))]
        if legacy is not None:
            sources.append(("retrospective_unverified", legacy))
        for source, cohorts in sources:
            for horizon in ("1M", "3M"):
                report = evaluate_risk(cohorts, histories, horizon, source=source, db_path=db_path, persist_paths=True)
                reports.append({"source": source, "horizon": horizon, "report_id": save_report(report, db_path),
                                "test_cohorts": report["test_cohorts"]})
        record_status("pipeline", VERSION, "captured" if captured["status"] == "captured" else "empty",
                      error_code=None if captured["status"] == "captured" else captured["status"], db_path=db_path)
        return {"capture": captured, "reports": reports}
    except Exception as exc:
        record_status("pipeline", VERSION, "failed", error_code=type(exc).__name__, db_path=db_path)
        raise
