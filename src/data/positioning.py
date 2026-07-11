"""Provider-neutral market-positioning snapshots."""

from collections.abc import Mapping
from datetime import datetime, timedelta
from statistics import median

import pandas as pd
import yfinance as yf

from src.data.fmp import FMPProvider
from src.utils.config import FMP_API_KEY


def _number(value: object) -> float | None:
    try:
        return float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None


class YahooPositioningProvider:
    name = "Yahoo Finance + FMP float validation"

    def __init__(self, fmp_provider: FMPProvider | None = None):
        self.fmp_provider = fmp_provider or (FMPProvider(FMP_API_KEY) if FMP_API_KEY else None)

    def fetch(self, ticker: str) -> dict[str, object]:
        normalized = ticker.strip().upper()
        security = yf.Ticker(normalized)
        info = security.info
        shares_short = _number(info.get("sharesShort"))
        prior_short = _number(info.get("sharesShortPriorMonth"))
        short_change = (
            (shares_short / prior_short - 1) * 100 if shares_short is not None and prior_short else None
        )
        report_timestamp = info.get("dateShortInterest")
        reporting_date = (
            datetime.fromtimestamp(float(report_timestamp)).date().isoformat()
            if report_timestamp else None
        )

        calls_volume = puts_volume = calls_oi = puts_oi = 0.0
        iv_values: list[float] = []
        expiries_used: list[str] = []
        for expiry in list(security.options)[:3]:
            try:
                chain = security.option_chain(expiry)
            except Exception:
                continue
            expiries_used.append(str(expiry))
            for frame, is_put in ((chain.calls, False), (chain.puts, True)):
                if not isinstance(frame, pd.DataFrame) or frame.empty:
                    continue
                volume = float(frame.get("volume", pd.Series(dtype=float)).fillna(0).sum())
                open_interest = float(frame.get("openInterest", pd.Series(dtype=float)).fillna(0).sum())
                if is_put:
                    puts_volume += volume; puts_oi += open_interest
                else:
                    calls_volume += volume; calls_oi += open_interest
                if "impliedVolatility" in frame:
                    iv_values.extend(float(value) for value in frame["impliedVolatility"].dropna() if float(value) > 0)

        insider_buys = insider_sells = 0
        insiders = security.insider_transactions
        if isinstance(insiders, pd.DataFrame) and not insiders.empty:
            text = insiders.astype(str).agg(" ".join, axis=1).str.lower()
            insider_buys = int(text.str.contains("purchase|buy").sum())
            insider_sells = int(text.str.contains("sale|sell").sum())

        upgrades = downgrades = 0
        actions = security.upgrades_downgrades
        if isinstance(actions, pd.DataFrame) and not actions.empty:
            recent = actions.copy()
            try:
                cutoff = pd.Timestamp.now(tz="UTC") - timedelta(days=90)
                recent = recent[pd.to_datetime(recent.index, utc=True) >= cutoff]
            except Exception:
                recent = recent.head(100)
            action_text = recent.get("Action", recent.get("action", pd.Series(dtype=str))).astype(str).str.lower()
            upgrades = int(action_text.str.contains("up").sum())
            downgrades = int(action_text.str.contains("down").sum())

        fmp_float = None
        if self.fmp_provider:
            rows = self.fmp_provider._optional_get("shares-float", symbol=normalized)
            if rows:
                fmp_float = _number(rows[0].get("floatShares", rows[0].get("freeFloat")))
        return {
            "ticker": normalized,
            "short": {
                "short_percent_float": _number(info.get("shortPercentOfFloat")),
                "shares_short": shares_short, "shares_short_prior_month": prior_short,
                "short_change_pct": short_change, "days_to_cover": _number(info.get("shortRatio")),
            },
            "options": {
                "expiries_used": expiries_used,
                "call_volume": calls_volume, "put_volume": puts_volume,
                "put_call_volume_ratio": puts_volume / calls_volume if calls_volume else None,
                "call_open_interest": calls_oi, "put_open_interest": puts_oi,
                "put_call_oi_ratio": puts_oi / calls_oi if calls_oi else None,
                "median_contract_iv": median(iv_values) if iv_values else None,
            },
            "ownership": {
                "institutional_percent": _number(info.get("heldPercentInstitutions")),
                "insider_percent": _number(info.get("heldPercentInsiders")),
                "public_float_shares_fmp": fmp_float,
            },
            "insiders": {"purchase_rows": insider_buys, "sale_rows": insider_sells},
            "analyst_actions": {"upgrades_90d": upgrades, "downgrades_90d": downgrades},
            "reporting_date": reporting_date,
        }


class PositioningProvider:
    """Small protocol-like base for replaceable positioning adapters."""

    name: str

    def fetch(self, ticker: str) -> Mapping[str, object]:
        raise NotImplementedError
