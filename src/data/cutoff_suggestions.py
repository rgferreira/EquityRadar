"""Automatic, explainable discovery of worthwhile historical simulation dates."""

from __future__ import annotations

from concurrent.futures import Future, ThreadPoolExecutor, wait
from datetime import date, timedelta
import hashlib
from pathlib import Path
from threading import RLock

import pandas as pd

from src.data.database import (
    get_positioning_history, get_simulation_suggestions, replace_simulation_suggestions,
)
from src.data.market_data import fetch_price_history

_executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="cutoff-suggestions")
_lock = RLock()
_future: Future[None] | None = None


def suggestion_signature(tickers: list[str]) -> str:
    payload = f"v3|{date.today().isoformat()}|{'|'.join(sorted(set(tickers)))}"
    return hashlib.sha256(payload.encode()).hexdigest()[:16]


def _price_candidates(ticker: str, history: pd.DataFrame, market: bool = False) -> list[dict[str, object]]:
    close = history["Close"].dropna().copy()
    close.index = pd.to_datetime(close.index).tz_localize(None)
    if len(close) < 80:
        return []
    latest_eligible = pd.Timestamp(close.index[-22])
    earliest = pd.Timestamp(latest_eligible.to_pydatetime() - timedelta(days=550))
    close = close.loc[(close.index >= earliest) & (close.index <= latest_eligible)]
    returns = close.pct_change(21) * 100
    ma50 = close.rolling(50).mean()
    gap = (close / ma50 - 1) * 100
    candidates: list[dict[str, object]] = []
    for timestamp in returns.abs().nlargest(3).index:
        move = float(returns.loc[timestamp])
        direction = "rally" if move > 0 else "sell-off"
        subject = "Broad market" if market else ticker
        candidates.append({
            "suggested_date": timestamp.date().isoformat(),
            "trigger_type": "Market momentum shock" if market else "Single-stock momentum shock",
            "rationale": f"{subject} {direction}: {move:+.1f}% over 21 sessions, creating a high-information momentum and risk checkpoint.",
            "priority": min(98.0, 45 + min(40, abs(move) * 1.5) + (10 if market else 0)),
            "evidence": {"ticker": ticker, "return_21d_pct": round(move, 2), "attribute": "21-session return"},
        })
    crossing = gap[(gap.shift(1) * gap <= 0) & gap.notna()]
    for timestamp in crossing.index[-2:]:
        direction = "reclaimed" if float(gap.loc[timestamp]) >= 0 else "lost"
        subject = "SPY" if market else ticker
        candidates.append({
            "suggested_date": timestamp.date().isoformat(),
            "trigger_type": "Market trend transition" if market else "Single-stock trend transition",
            "rationale": f"{subject} {direction} its 50-day moving average, marking a potential trend-regime transition.",
            "priority": 68.0 + (10 if market else 0),
            "evidence": {"ticker": ticker, "ma50_gap_pct": round(float(gap.loc[timestamp]), 2), "attribute": "50-day MA crossing"},
        })
    daily_returns = close.pct_change()
    annualized_volatility = daily_returns.rolling(21).std() * (252 ** .5) * 100
    if annualized_volatility.notna().any():
        timestamp = annualized_volatility.idxmax()
        volatility = float(annualized_volatility.loc[timestamp])
        baseline = float(annualized_volatility.median())
        candidates.append({
            "suggested_date": timestamp.date().isoformat(),
            "trigger_type": "Market volatility regime" if market else "Single-stock volatility shock",
            "rationale": (
                f"{'Broad market' if market else ticker} 21-session annualized volatility reached "
                f"{volatility:.1f}% versus a {baseline:.1f}% period median, creating a useful stress-regime checkpoint."
            ),
            "priority": min(94.0, 58 + max(0, volatility - baseline) * .7 + (8 if market else 0)),
            "evidence": {"ticker": ticker, "annualized_volatility_pct": round(volatility, 2),
                         "period_median_pct": round(baseline, 2), "attribute": "21-session volatility"},
        })
    drawdown = (close / close.rolling(126, min_periods=40).max() - 1) * 100
    if drawdown.notna().any():
        timestamp = drawdown.idxmin()
        depth = float(drawdown.loc[timestamp])
        candidates.append({
            "suggested_date": timestamp.date().isoformat(),
            "trigger_type": "Market drawdown extreme" if market else "Single-stock drawdown extreme",
            "rationale": (
                f"{'Broad market' if market else ticker} reached a {depth:.1f}% six-month drawdown, "
                "a high-information point for testing risk resilience and decision discipline."
            ),
            "priority": min(92.0, 54 + abs(depth) * 1.2 + (7 if market else 0)),
            "evidence": {"ticker": ticker, "drawdown_126d_pct": round(depth, 2),
                         "attribute": "126-session drawdown"},
        })
    return candidates


def generate_cutoff_suggestions(tickers: list[str], db_path: str | Path | None = None) -> list[dict[str, object]]:
    """Rank novel market and watchlist events, keeping rationales fully auditable."""
    candidates: list[dict[str, object]] = []
    market_history = fetch_price_history("SPY", period="3y")
    candidates.extend(_price_candidates("SPY", market_history, market=True))
    market_index = pd.to_datetime(market_history.index).tz_localize(None)
    latest_eligible_date = pd.Timestamp(market_index[-22]).date()
    earliest_date = latest_eligible_date - timedelta(days=550)
    histories: dict[str, pd.DataFrame] = {}
    worker_count = min(6, max(1, len(tickers)))
    history_pool = ThreadPoolExecutor(max_workers=worker_count, thread_name_prefix="cutoff-history")
    futures = {
        history_pool.submit(fetch_price_history, ticker, period="3y"): ticker
        for ticker in tickers
    }
    completed, pending = wait(futures, timeout=20)
    for future in completed:
        ticker = futures[future]
        try:
            histories[ticker] = future.result()
        except Exception:
            continue
    for future in pending:
        future.cancel()
    history_pool.shutdown(wait=False, cancel_futures=True)
    for ticker in tickers:
        if ticker in histories:
            candidates.extend(_price_candidates(ticker, histories[ticker]))
        positioning = get_positioning_history(ticker, db_path)
        eligible = []
        for row in positioning:
            short = row.get("short") or {}
            change = short.get("short_change_pct")
            reporting_date = row.get("reporting_date")
            if change is not None and reporting_date:
                parsed_date = pd.Timestamp(str(reporting_date)).date()
                if earliest_date <= parsed_date <= latest_eligible_date:
                    eligible.append((abs(float(change)), float(change), parsed_date.isoformat()))
        if eligible:
            _, change, reporting_date = max(eligible)
            candidates.append({
                "suggested_date": reporting_date,
                "trigger_type": "Short-interest build-up" if change > 0 else "Short-interest unwinding",
                "rationale": f"{ticker} reported an exceptional {change:+.1f}% short-interest change, suitable for testing whether positioning altered the decision signal.",
                "priority": min(95.0, 55 + min(35, abs(change) * .4)),
                "evidence": {"ticker": ticker, "short_change_pct": round(change, 2), "attribute": "FINRA short interest"},
            })
    # Prefer high-value events and suppress dates representing essentially the same regime.
    chosen: list[dict[str, object]] = []

    def add_novel(candidate: dict[str, object]) -> bool:
        candidate_date = pd.Timestamp(str(candidate["suggested_date"]))
        if any(abs((candidate_date - pd.Timestamp(str(item["suggested_date"]))).days) < 14 for item in chosen):
            return False
        chosen.append(candidate)
        return True

    ranked = sorted(candidates, key=lambda item: float(item["priority"]), reverse=True)
    # Preserve a useful mix: the broad market always gets representation, while
    # ticker-specific anomalies retain most of the available slots.
    for candidate in (item for item in ranked if str(item["trigger_type"]).startswith("Market")):
        add_novel(candidate)
        if sum(str(item["trigger_type"]).startswith("Market") for item in chosen) == 3:
            break
    for candidate in ranked:
        add_novel(candidate)
        if len(chosen) == 10:
            break
    return sorted(chosen, key=lambda item: float(item["priority"]), reverse=True)


def _refresh(tickers: list[str], db_path: str | Path | None, signature: str) -> None:
    suggestions = generate_cutoff_suggestions(tickers, db_path)
    if suggestions:
        replace_simulation_suggestions(suggestions, signature, db_path)


def schedule_cutoff_suggestions(
    tickers: list[str], db_path: str | Path | None = None, *, force: bool = False,
) -> bool:
    """Refresh once daily or whenever watchlist membership changes."""
    global _future
    signature = suggestion_signature(tickers)
    stored = get_simulation_suggestions(db_path)
    fresh = bool(stored and str(stored[0].get("source_signature")) == signature)
    with _lock:
        if (fresh and not force) or (_future and not _future.done()):
            return False
        _future = _executor.submit(_refresh, list(tickers), db_path, signature)
    return True


def cutoff_suggestion_status() -> str:
    with _lock:
        return "Discovering interesting dates…" if _future and not _future.done() else "Suggestions update automatically"
