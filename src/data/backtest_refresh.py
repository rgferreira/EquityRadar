"""Persistent background orchestration for point-in-time simulations."""

from concurrent.futures import Future, ThreadPoolExecutor
from collections import defaultdict
from collections.abc import Mapping
from pathlib import Path
from threading import RLock
from datetime import date, timedelta
import json

from src.backtesting import evaluate_outcomes, latest_model_runs, reconstruct_signal
from src.backtesting import lesson_summary
from src.data.database import (
    get_backtest_job_items, get_backtest_runs, get_cached_fundamentals,
    get_cached_industry_research, get_finra_daily_short_volume, get_positioning_history,
    get_outcome_labels, get_prediction_snapshots, save_backtest_run, save_outcome_label,
    save_prediction_snapshot, save_shadow_decision_snapshot,
    set_backtest_job_item, update_backtest_outcomes,
)
from src.data.market_data import fetch_price_history
from src.model_registry import (
    ACTIVE_SHADOW_ENABLED, build_prediction_snapshot, current_model_registration,
)
from src.outcome_labels import benchmark_for_ticker, build_relative_outcome_label
from src.shadow_model import build_shadow_snapshot

_executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="backtested-learning")
_lock = RLock()
_futures: dict[str, Future[None]] = {}
_outcome_future: Future[None] | None = None


def _persist_reconstruction(
    *, ticker: str, as_of_date: str, history: object,
    fundamentals: object, positioning_history: list[object], industry_research: object,
    daily_short_flow_history: list[object],
    db_path: str | Path | None, simulation_source: str,
    suggestion_rationale: str | None, benchmark_cache: dict[str, object | None],
) -> dict[str, object]:
    result = reconstruct_signal(
        history, as_of_date, fundamentals, positioning_history, industry_research,
        daily_short_flow_history,
    )
    outcomes = evaluate_outcomes(history, as_of_date)
    legacy_run = {
        "ticker": ticker, "as_of_date": as_of_date, "coverage": result["coverage"],
        "entry_score": result["entry_score"], "exit_score": result["exit_score"],
        "entry_signal": result["entry_signal"], "exit_signal": result["exit_signal"],
        "technical_score": result["technical"], "valuation_score": result["valuation"],
        "risk_score": result["risk"], "outcome_1m": outcomes["1M"],
        "outcome_3m": outcomes["3M"], "outcome_6m": outcomes["6M"],
        "outcome_12m": outcomes["12M"],
        "inputs_json": json.dumps({"metrics": result["metrics"],
                                     "fundamentals_used": result["fundamentals_used"],
                                     "finra_observations_used": result["finra_observations_used"],
                                     "temporal_coverage": result["temporal_coverage"],
                                     "positioning_modifier": result["positioning_modifier"],
                                     "technology_potential": result["technology_potential"],
                                     "daily_short_flow": result["daily_short_flow"]}),
        "model_version": result["model_version"],
        "simulation_source": simulation_source,
        "suggestion_rationale": suggestion_rationale,
    }
    save_backtest_run(legacy_run, db_path)
    model = current_model_registration()
    frozen_inputs = {
        "features": {
            "technical_score": result["technical"],
            "valuation_score": result["valuation"],
            "risk_score": result["risk"],
        },
        "positioning_adjustments": {
            "entry_adjustment": result["positioning_modifier"]["entry_adjustment"],
            "exit_adjustment": result["positioning_modifier"]["exit_adjustment"],
        },
        "temporal_coverage": result["temporal_coverage"],
        "input_references": result["input_references"],
        "technology_potential": result["technology_potential"],
        "daily_short_flow": result["daily_short_flow"],
    }
    frozen_outputs = {
        "entry_score": result["entry_score"], "exit_score": result["exit_score"],
        "entry_signal": result["entry_signal"], "exit_signal": result["exit_signal"],
    }
    snapshot = build_prediction_snapshot(
        ticker=ticker, as_of_date=as_of_date, model=model, inputs=frozen_inputs,
        outputs=frozen_outputs, simulation_source=simulation_source,
        suggestion_rationale=suggestion_rationale,
    )
    save_prediction_snapshot(snapshot, db_path)
    if ACTIVE_SHADOW_ENABLED:
        try:
            save_shadow_decision_snapshot(build_shadow_snapshot(
                ticker=ticker, as_of_date=as_of_date, surface="historical_simulation",
                inputs={**frozen_inputs, "industry_calibrated": False},
                current_outputs=frozen_outputs,
            ), db_path)
        except Exception:
            # Shadow research is isolated from the authoritative simulation pipeline.
            pass
    benchmark_ticker = benchmark_for_ticker(ticker)
    if benchmark_ticker not in benchmark_cache:
        try:
            benchmark_cache[benchmark_ticker] = (
                fetch_price_history(benchmark_ticker, period="max") if benchmark_ticker else None
            )
        except Exception:
            benchmark_cache[benchmark_ticker] = None
    relative_label = build_relative_outcome_label(
        prediction_id=str(snapshot["prediction_id"]), ticker=ticker,
        as_of_date=as_of_date, security_history=history,
        benchmark_history=benchmark_cache.get(benchmark_ticker),
        benchmark_ticker=benchmark_ticker,
    )
    if relative_label["status"] != "pending":
        save_outcome_label(relative_label, db_path)
    return legacy_run


def _run(
    as_of_date: str, tickers: list[str], db_path: str | Path | None,
    simulation_source: str = "manual", suggestion_rationale: str | None = None,
) -> None:
    benchmark_cache: dict[str, object | None] = {}
    for ticker in tickers:
        set_backtest_job_item(as_of_date, ticker, "running", db_path=db_path)
        try:
            history = fetch_price_history(ticker, period="max")
            _persist_reconstruction(
                ticker=ticker, as_of_date=as_of_date, history=history,
                fundamentals=get_cached_fundamentals(ticker, db_path),
                positioning_history=get_positioning_history(ticker, db_path),
                industry_research=get_cached_industry_research(ticker, db_path),
                daily_short_flow_history=get_finra_daily_short_volume(ticker, db_path),
                db_path=db_path, simulation_source=simulation_source,
                suggestion_rationale=suggestion_rationale, benchmark_cache=benchmark_cache,
            )
            set_backtest_job_item(as_of_date, ticker, "completed", db_path=db_path)
        except Exception as exc:
            set_backtest_job_item(as_of_date, ticker, "failed", str(exc), db_path)


def restate_saved_simulations(db_path: str | Path | None = None) -> dict[str, object]:
    """Append a corrected active-model run for every saved cutoff; never rewrite legacy rows."""
    existing_runs = get_backtest_runs(db_path=db_path)
    source_runs = latest_model_runs(existing_runs)
    current_version = str(current_model_registration()["model_version"])
    already_corrected = {
        (str(run["ticker"]), str(run["as_of_date"]))
        for run in existing_runs if str(run["model_version"]) == current_version
    }
    by_ticker: dict[str, list[dict[str, object]]] = defaultdict(list)
    for run in source_runs:
        key = (str(run["ticker"]), str(run["as_of_date"]))
        if key not in already_corrected:
            by_ticker[key[0]].append(dict(run))
    before_lessons = {
        ticker: lesson_summary([row for row in existing_runs if str(row["ticker"]) == ticker])
        for ticker in by_ticker
    }
    benchmark_cache: dict[str, object | None] = {}
    ticker_audit: list[dict[str, object]] = []
    failed: list[dict[str, str]] = []
    created = score_changes = signal_changes = stale_exclusions = 0
    for ticker, runs in sorted(by_ticker.items()):
        try:
            history = fetch_price_history(ticker, period="max")
            fundamentals = get_cached_fundamentals(ticker, db_path)
            positioning = get_positioning_history(ticker, db_path)
            industry = get_cached_industry_research(ticker, db_path)
            daily_short_flow = get_finra_daily_short_volume(ticker, db_path)
        except Exception as exc:
            failed.append({"ticker": ticker, "as_of_date": "all", "error": str(exc)})
            continue
        ticker_created = ticker_score_changes = ticker_signal_changes = ticker_stale = 0
        for source in sorted(runs, key=lambda row: str(row["as_of_date"])):
            as_of_date = str(source["as_of_date"])
            set_backtest_job_item(as_of_date, ticker, "running", db_path=db_path)
            try:
                corrected = _persist_reconstruction(
                    ticker=ticker, as_of_date=as_of_date, history=history,
                    fundamentals=fundamentals, positioning_history=positioning,
                    industry_research=industry, daily_short_flow_history=daily_short_flow,
                    db_path=db_path,
                    simulation_source=str(source.get("simulation_source") or "manual"),
                    suggestion_rationale=source.get("suggestion_rationale"),
                    benchmark_cache=benchmark_cache,
                )
                ticker_created += 1
                ticker_score_changes += int(
                    float(corrected["entry_score"]) != float(source["entry_score"])
                    or float(corrected["exit_score"]) != float(source["exit_score"])
                )
                ticker_signal_changes += int(
                    corrected["entry_signal"] != source["entry_signal"]
                    or corrected["exit_signal"] != source["exit_signal"]
                )
                inputs = json.loads(str(corrected["inputs_json"]))
                ticker_stale += int(
                    (inputs.get("temporal_coverage") or {}).get("finra") == "stale_excluded"
                )
                set_backtest_job_item(as_of_date, ticker, "completed", db_path=db_path)
            except Exception as exc:
                set_backtest_job_item(as_of_date, ticker, "failed", str(exc), db_path)
                failed.append({"ticker": ticker, "as_of_date": as_of_date, "error": str(exc)})
        created += ticker_created
        score_changes += ticker_score_changes
        signal_changes += ticker_signal_changes
        stale_exclusions += ticker_stale
        ticker_audit.append({
            "ticker": ticker, "runs_recalculated": ticker_created,
            "score_changes": ticker_score_changes, "signal_changes": ticker_signal_changes,
            "stale_finra_exclusions": ticker_stale,
        })
    refreshed_runs = get_backtest_runs(db_path=db_path)
    for row in ticker_audit:
        ticker = str(row["ticker"])
        after = lesson_summary([run for run in refreshed_runs if str(run["ticker"]) == ticker])
        before = before_lessons[ticker]
        row["accuracy_before"] = before.get("decision_accuracy")
        row["accuracy_after"] = after.get("decision_accuracy")
        row["accuracy_delta_pp"] = (
            None if before.get("decision_accuracy") is None or after.get("decision_accuracy") is None
            else round(float(after["decision_accuracy"]) - float(before["decision_accuracy"]), 1)
        )
    return {
        "model_version": current_version,
        "legacy_rows_preserved": True,
        "runs_recalculated": created, "score_changes": score_changes,
        "signal_changes": signal_changes, "stale_finra_exclusions": stale_exclusions,
        "failed": failed, "tickers": ticker_audit,
    }


def _finished(key: str, _future: Future[None]) -> None:
    with _lock:
        _futures.pop(key, None)


def schedule_backtest(
    as_of_date: str, tickers: list[str], db_path: str | Path | None = None,
    simulation_source: str = "manual", suggestion_rationale: str | None = None,
) -> bool:
    """Queue unfinished tickers; the worker survives Streamlit page navigation."""
    normalized = [ticker.strip().upper() for ticker in tickers]
    existing = {item["ticker"]: item for item in get_backtest_job_items(as_of_date, db_path)}
    completed_runs = {str(run["ticker"]) for run in get_backtest_runs(db_path=db_path)
                      if run["as_of_date"] == as_of_date}
    for ticker in completed_runs:
        if ticker in normalized and ticker not in existing:
            set_backtest_job_item(as_of_date, ticker, "completed", db_path=db_path)
            existing[ticker] = {"ticker": ticker, "status": "completed"}
    pending = [ticker for ticker in normalized if existing.get(ticker, {}).get("status") != "completed"]
    if not pending:
        return False
    key = as_of_date
    with _lock:
        if key in _futures:
            return False
        for ticker in pending:
            set_backtest_job_item(as_of_date, ticker, "queued", db_path=db_path)
        future = _executor.submit(
            _run, as_of_date, pending, db_path, simulation_source, suggestion_rationale,
        )
        _futures[key] = future
        future.add_done_callback(lambda completed: _finished(key, completed))
    return True


def backtest_status(as_of_date: str, db_path: str | Path | None = None) -> dict[str, object]:
    items = get_backtest_job_items(as_of_date, db_path)
    counts = {status: sum(item["status"] == status for item in items)
              for status in ("queued", "running", "completed", "failed")}
    return {"items": items, "total": len(items), **counts,
            "busy": bool(counts["queued"] or counts["running"])}


def _refresh_outcomes(db_path: str | Path | None) -> None:
    for run in get_backtest_runs(db_path=db_path):
        if all(run.get(field) is not None for field in ("outcome_1m", "outcome_3m", "outcome_6m", "outcome_12m")):
            continue
        try:
            history = fetch_price_history(str(run["ticker"]), period="max")
            update_backtest_outcomes(
                str(run["ticker"]), str(run["as_of_date"]),
                evaluate_outcomes(history, str(run["as_of_date"])), db_path,
            )
        except Exception:
            # A bad symbol or immature horizon must not block other saved runs.
            continue
    materialize_matured_prediction_labels(db_path)


def materialize_matured_prediction_labels(
    db_path: str | Path | None = None, *, today: date | None = None,
    history_fetcher: object = fetch_price_history,
) -> dict[str, int]:
    """Persist a relative label only once its 3M outcome is actually mature."""
    current_day = today or date.today()
    earliest_candidate = current_day - timedelta(days=75)
    labeled = {str(row["prediction_id"]) for row in get_outcome_labels(db_path=db_path)}
    candidates = [
        row for row in get_prediction_snapshots(db_path=db_path)
        if str(row["prediction_id"]) not in labeled
        and date.fromisoformat(str(row["as_of_date"])) <= earliest_candidate
    ]
    benchmark_cache: dict[str, object | None] = {}
    created = pending = failed = 0
    for prediction in candidates:
        ticker = str(prediction["ticker"])
        benchmark = benchmark_for_ticker(ticker)
        try:
            security_history = history_fetcher(ticker, period="max")
            if benchmark not in benchmark_cache:
                benchmark_cache[benchmark] = (
                    history_fetcher(benchmark, period="max") if benchmark else None
                )
            label = build_relative_outcome_label(
                prediction_id=str(prediction["prediction_id"]), ticker=ticker,
                as_of_date=str(prediction["as_of_date"]), security_history=security_history,
                benchmark_history=benchmark_cache.get(benchmark), benchmark_ticker=benchmark,
            )
            outcomes = label.get("outcomes") or {}
            if label["status"] == "available" and isinstance(outcomes.get("3M"), Mapping):
                save_outcome_label(label, db_path)
                created += 1
            elif label["status"] == "unavailable" and label.get("unavailable_reason") == "no_verified_benchmark_mapping":
                save_outcome_label(label, db_path)
                created += 1
            else:
                pending += 1
        except Exception:
            failed += 1
    return {"candidates": len(candidates), "created": created, "pending": pending, "failed": failed}


def schedule_outcome_refresh(db_path: str | Path | None = None) -> bool:
    """Auto-complete matured outcomes at most once daily, without a refresh button."""
    global _outcome_future
    runs = get_backtest_runs(db_path=db_path)
    today = date.today().isoformat()
    legacy_stale = any(
        any(run.get(field) is None for field in ("outcome_1m", "outcome_3m", "outcome_6m", "outcome_12m"))
        and str(run.get("outcome_refreshed_at") or "")[:10] != today
        for run in runs
    )
    labeled = {str(row["prediction_id"]) for row in get_outcome_labels(db_path=db_path)}
    label_due = any(
        str(row["prediction_id"]) not in labeled
        and date.fromisoformat(str(row["as_of_date"])) <= date.today() - timedelta(days=75)
        for row in get_prediction_snapshots(db_path=db_path)
    )
    with _lock:
        if not (legacy_stale or label_due) or (_outcome_future and not _outcome_future.done()):
            return False
        _outcome_future = _executor.submit(_refresh_outcomes, db_path)
    return True


def outcome_refresh_in_flight() -> bool:
    with _lock:
        return bool(_outcome_future and not _outcome_future.done())


def schedule_ticker_backfill(ticker: str, db_path: str | Path | None = None) -> list[str]:
    """Queue a new ticker for every persisted cutoff that does not yet know about it."""
    normalized = ticker.strip().upper()
    runs = get_backtest_runs(db_path=db_path)
    dates = sorted({str(run["as_of_date"]) for run in runs})
    completed_dates = {str(run["as_of_date"]) for run in runs if run["ticker"] == normalized}
    scheduled: list[str] = []
    with _lock:
        for as_of_date in dates:
            if as_of_date in completed_dates:
                continue
            existing = {str(item["ticker"]): item for item in get_backtest_job_items(as_of_date, db_path)}
            # Failed is a completed attempt and needs an explicit retry, not a navigation loop.
            if normalized in existing:
                continue
            key = f"ticker-backfill:{normalized}:{as_of_date}"
            if key in _futures:
                continue
            set_backtest_job_item(as_of_date, normalized, "queued", db_path=db_path)
            date_runs = [run for run in runs if str(run["as_of_date"]) == as_of_date]
            provenance = latest_model_runs(date_runs)[0] if date_runs else {}
            future = _executor.submit(
                _run, as_of_date, [normalized], db_path,
                str(provenance.get("simulation_source") or "manual"),
                provenance.get("suggestion_rationale"),
            )
            _futures[key] = future
            future.add_done_callback(lambda completed, job_key=key: _finished(job_key, completed))
            scheduled.append(as_of_date)
    return scheduled


def schedule_ticker_recalculation(ticker: str, db_path: str | Path | None = None) -> list[str]:
    """Rebuild every saved cutoff using the newest point-in-time scoring model."""
    normalized = ticker.strip().upper()
    dates = sorted({str(run["as_of_date"]) for run in get_backtest_runs(normalized, db_path)})
    scheduled: list[str] = []
    with _lock:
        for as_of_date in dates:
            key = f"finra-recalc:{normalized}:{as_of_date}"
            if key in _futures:
                continue
            date_runs = [run for run in get_backtest_runs(normalized, db_path) if str(run["as_of_date"]) == as_of_date]
            provenance = latest_model_runs(date_runs)[0] if date_runs else {}
            future = _executor.submit(
                _run, as_of_date, [normalized], db_path,
                str(provenance.get("simulation_source") or "manual"),
                provenance.get("suggestion_rationale"),
            )
            _futures[key] = future
            future.add_done_callback(lambda completed, job_key=key: _finished(job_key, completed))
            scheduled.append(as_of_date)
    return scheduled


def ticker_backfill_status(ticker: str, db_path: str | Path | None = None) -> dict[str, object]:
    normalized = ticker.strip().upper()
    runs = get_backtest_runs(normalized, db_path)
    all_dates = sorted({str(run["as_of_date"]) for run in get_backtest_runs(db_path=db_path)})
    completed = {str(run["as_of_date"]) for run in runs}
    items = []
    for as_of_date in all_dates:
        match = next((item for item in get_backtest_job_items(as_of_date, db_path)
                      if item["ticker"] == normalized), None)
        status = "completed" if as_of_date in completed else str(match["status"]) if match else "missing"
        items.append({"as_of_date": as_of_date, "status": status,
                      "error": match.get("error") if match else None})
    return {"ticker": normalized, "items": items, "total": len(all_dates),
            "completed": sum(item["status"] == "completed" for item in items),
            "failed": sum(item["status"] == "failed" for item in items),
            "busy": any(item["status"] in {"queued", "running"} for item in items)}
