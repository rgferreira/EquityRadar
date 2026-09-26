"""Bounded background capture and maturation; page rendering only reads local results."""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from threading import Lock

import pandas as pd

from src.data.database import get_watchlist
from src.data.institutional_positioning import institutional_summary, refresh_institutions
from src.data.macro_context import macro_summary, refresh_macro
from src.data.options_context import options_coverage, refresh_options
from src.data.research_signals import latest_batch, record_status, statuses, timestamp, utcnow
from src.entry_context import (SECTOR_ETFS, VERSION, capture_context, historical_inputs, snapshots)
from src.strategy_validation import evaluate, save_report

_pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix="entry-context-pipeline")
_lock = Lock()
_future = None


def due(state, now, hours):
    if not state:
        return True
    try:
        elapsed = (now - timestamp(state["attempted_at"])).total_seconds() / 3600
        threshold = .75 if state["status"] == "running" else (1 if state["status"] == "failed" else hours)
        return elapsed >= threshold
    except (TypeError, ValueError, KeyError):
        return True


def run_pipeline(db_path=None, *, include_history=False, refresh_sources=True):
    from src.data.price_cache import fetch_cached_price_history
    now = datetime.now(timezone.utc)
    record_status("pipeline", VERSION, "running", db_path=db_path)
    try:
        tickers = [t for t in get_watchlist(db_path) if not t.endswith("-USD")]
        source_results = []
        state = {(s["family"], s["scope"]): s for s in statuses(db_path)}
        if refresh_sources:
            if any(due(state.get(("macro", key)), now, 6) for key in ("overnight_rates", "nominal_2y", "real_10y", "policy_releases")):
                source_results.extend(refresh_macro(db_path))
            if due(state.get(("institutional", "cftc_tff")), now, 24):
                source_results.append(refresh_institutions(db_path))
            options_tickers = sorted(set(tickers + ["SPY", "QQQ"]))
            with ThreadPoolExecutor(max_workers=2) as pool:
                jobs = [pool.submit(refresh_options, t, db_path) for t in options_tickers
                        if due(state.get(("options", t)), now, 24)]
                source_results.extend(f.result() for f in as_completed(jobs))
        old = snapshots(db_path)
        legacy = historical_inputs(db_path) if include_history else []
        needed = set(tickers + ["SPY", *SECTOR_ETFS.values()])
        needed.update(r["ticker"] for c in old + legacy for r in c["inputs"])
        histories, failures = {}, []
        with ThreadPoolExecutor(max_workers=4) as pool:
            jobs = {pool.submit(fetch_cached_price_history, t, period="max", timeout=10,
                                db_path=db_path, force_refresh=True): t for t in sorted(needed)}
            for future in as_completed(jobs):
                ticker = jobs[future]
                try:
                    h = future.result()
                    dates = pd.to_datetime(h.index).tz_localize(None)
                    histories[ticker] = h.loc[dates < pd.Timestamp(now.date())]
                except Exception:
                    failures.append(ticker)
        options = {}
        for ticker in sorted(set(tickers + ["SPY", "QQQ"])):
            b = latest_batch("options", ticker, db_path=db_path)
            if b:
                options[ticker] = {"batch_id": b["batch_id"], "known_at": b["observed_at"],
                    **{k: v for k, v in b["payload"]["summary"].items() if k != "accepted_contracts"}}
        capture = capture_context(histories, {"macro": macro_summary(db_path),
            "institutions": institutional_summary(db_path), "options": options}, db_path)
        prospective = snapshots(db_path)
        reports = []
        for cohorts in ([prospective, legacy] if include_history else [prospective]):
            for horizon in ("1M", "3M"):
                report = evaluate(cohorts, histories, horizon, db_path=db_path, persist_paths=True)
                report_id = save_report(report, db_path)
                reports.append({"source": report["source"], "horizon": horizon, "report_id": report_id,
                                "test_cohorts": report["test_cohorts"], "exclusions": report["exclusions"]})
        summary = {"capture": capture, "reports": reports, "source_status_counts": {
            s: sum(r["status"] == s for r in source_results) for s in ("captured", "empty", "failed")},
            "price_histories": len(histories), "price_failures": len(failures),
            "options_usable_tickers": sum(r["status"] == "usable_context" for r in options_coverage(tickers, db_path)),
            "completed_at": utcnow()}
        record_status("pipeline", VERSION, "captured" if capture["status"] == "captured" else "failed",
                      error_code=None if capture["status"] == "captured" else capture["status"], db_path=db_path)
        return summary
    except Exception as exc:
        record_status("pipeline", VERSION, "failed", error_code=type(exc).__name__, db_path=db_path)
        raise


def schedule_pipeline(db_path=None):
    global _future
    state = next((s for s in statuses(db_path) if s["family"] == "pipeline" and s["scope"] == VERSION), None)
    if not get_watchlist(db_path) or not due(state, datetime.now(timezone.utc), 6):
        return False
    with _lock:
        if _future and not _future.done():
            return False
        _future = _pool.submit(run_pipeline, db_path)
        return True
