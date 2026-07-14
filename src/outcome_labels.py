"""Versioned, executable benchmark-relative outcome labels."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping

import pandas as pd


RELATIVE_LABEL_VERSION = "benchmark-relative-v1"
TIMING_CONVENTION = "next-common-tradable-session-close"
BENCHMARK_POLICY_VERSION = "broad-market-v1"
TOTAL_COST_BPS = 10.0
HORIZON_SESSIONS = {"1M": 21, "3M": 63, "6M": 126}


def benchmark_for_ticker(ticker: str) -> str | None:
    """Return the frozen broad-market benchmark mapping for supported assets."""
    normalized = ticker.strip().upper()
    if normalized.endswith("-USD"):
        return None
    return "^GSPC" if normalized == "SPY" else "SPY"


def _close_series(history: pd.DataFrame) -> pd.Series:
    if history.empty or "Close" not in history:
        return pd.Series(dtype=float)
    close = history["Close"].dropna().astype(float).copy()
    close.index = pd.to_datetime(close.index).tz_localize(None).normalize()
    return close[~close.index.duplicated(keep="last")].sort_index()


def _unavailable(
    *, ticker: str, prediction_id: str, benchmark_ticker: str | None, reason: str,
) -> dict[str, object]:
    payload: dict[str, object] = {
        "prediction_id": prediction_id,
        "ticker": ticker.strip().upper(),
        "label_version": RELATIVE_LABEL_VERSION,
        "status": "unavailable",
        "unavailable_reason": reason,
        "benchmark_ticker": benchmark_ticker,
        "benchmark_policy_version": BENCHMARK_POLICY_VERSION,
        "timing_convention": TIMING_CONVENTION,
        "cost_bps": TOTAL_COST_BPS,
        "execution_date": None,
        "security_entry_price": None,
        "benchmark_entry_price": None,
        "outcomes": {},
        "max_drawdown_6m_pct": None,
    }
    return _with_identity(payload)


def _with_identity(payload: Mapping[str, object]) -> dict[str, object]:
    canonical = json.dumps(dict(payload), sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    outcome_hash = hashlib.sha256(canonical.encode()).hexdigest()
    return {**dict(payload), "outcome_hash": outcome_hash,
            "label_id": hashlib.sha256(
                f"{payload['prediction_id']}|{payload['label_version']}".encode()
            ).hexdigest()}


def build_relative_outcome_label(
    *, prediction_id: str, ticker: str, as_of_date: str,
    security_history: pd.DataFrame, benchmark_history: pd.DataFrame | None,
    benchmark_ticker: str | None = None,
) -> dict[str, object]:
    """Build a deterministic label from frozen daily closes.

    Entry is the first session shared by the security and benchmark strictly
    after the decision cutoff. Each horizon is measured N common sessions
    after entry. The explicit round-trip cost is subtracted exactly once.
    """
    benchmark = benchmark_ticker if benchmark_ticker is not None else benchmark_for_ticker(ticker)
    if benchmark is None:
        return _unavailable(
            ticker=ticker, prediction_id=prediction_id, benchmark_ticker=None,
            reason="no_verified_benchmark_mapping",
        )
    if benchmark_history is None:
        return _unavailable(
            ticker=ticker, prediction_id=prediction_id, benchmark_ticker=benchmark,
            reason="missing_benchmark_history",
        )
    security = _close_series(security_history)
    benchmark_close = _close_series(benchmark_history)
    common = pd.concat(
        [security.rename("security"), benchmark_close.rename("benchmark")], axis=1, join="inner"
    ).dropna()
    eligible = common.loc[common.index > pd.Timestamp(as_of_date).normalize()]
    if eligible.empty:
        return _unavailable(
            ticker=ticker, prediction_id=prediction_id, benchmark_ticker=benchmark,
            reason="no_common_session_after_cutoff",
        )
    entry = eligible.iloc[0]
    execution_date = eligible.index[0]
    cost_pct = TOTAL_COST_BPS / 100.0
    outcomes: dict[str, object] = {}
    for label, sessions in HORIZON_SESSIONS.items():
        if len(eligible) <= sessions:
            outcomes[label] = None
            continue
        exit_row = eligible.iloc[sessions]
        security_return = (float(exit_row["security"]) / float(entry["security"]) - 1) * 100
        benchmark_return = (float(exit_row["benchmark"]) / float(entry["benchmark"]) - 1) * 100
        outcomes[label] = {
            "end_date": eligible.index[sessions].date().isoformat(),
            "security_return_pct": round(security_return, 6),
            "benchmark_return_pct": round(benchmark_return, 6),
            "relative_return_before_cost_pct": round(security_return - benchmark_return, 6),
            "relative_return_after_cost_pct": round(security_return - benchmark_return - cost_pct, 6),
        }
    drawdown = None
    if len(eligible) > HORIZON_SESSIONS["6M"]:
        path = eligible["security"].iloc[: HORIZON_SESSIONS["6M"] + 1]
        drawdown = float(((path / path.cummax()) - 1).min() * 100)
    payload = {
        "prediction_id": prediction_id,
        "ticker": ticker.strip().upper(),
        "label_version": RELATIVE_LABEL_VERSION,
        "status": "available" if any(value is not None for value in outcomes.values()) else "pending",
        "unavailable_reason": None,
        "benchmark_ticker": benchmark,
        "benchmark_policy_version": BENCHMARK_POLICY_VERSION,
        "timing_convention": TIMING_CONVENTION,
        "cost_bps": TOTAL_COST_BPS,
        "execution_date": execution_date.date().isoformat(),
        "security_entry_price": float(entry["security"]),
        "benchmark_entry_price": float(entry["benchmark"]),
        "outcomes": outcomes,
        "max_drawdown_6m_pct": round(drawdown, 6) if drawdown is not None else None,
    }
    return _with_identity(payload)
