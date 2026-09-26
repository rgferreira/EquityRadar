"""Independent, persistent options chains and explicitly approximate Greeks."""
from __future__ import annotations

from collections import Counter
from datetime import date, datetime, timezone
import math

from src.data.macro_context import macro_summary
from src.data.research_signals import attempt, latest_batch, number, timestamp, utcnow, statuses, schema
from src.data.database import get_connection

LIQUIDITY = {"min_dte": 20, "max_dte": 60, "min_open_interest": 100,
             "max_relative_spread": .25, "max_trade_age_days": 7,
             "min_moneyness": .8, "max_moneyness": 1.2, "max_iv": 5.0}


def greeks(spot, strike, years, iv, rate, dividend_yield, kind):
    """European BSM approximation; vega is price change per one volatility point."""
    values = [number(v) for v in (spot, strike, years, iv, rate, dividend_yield)]
    if None in values or min(values[:4]) <= 0 or kind not in {"call", "put"}:
        return None
    s, k, t, sigma, r, q = values
    d1 = (math.log(s / k) + (r - q + sigma * sigma / 2) * t) / (sigma * math.sqrt(t))
    n = .5 * (1 + math.erf(d1 / math.sqrt(2)))
    density = math.exp(-d1 * d1 / 2) / math.sqrt(2 * math.pi)
    discount = math.exp(-q * t)
    return {"delta": discount * (n if kind == "call" else n - 1),
            "gamma": discount * density / (s * sigma * math.sqrt(t)),
            "vega_per_vol_point": s * discount * density * math.sqrt(t) / 100}


def liquid_contract(row, spot, now):
    bid, ask, oi, iv, strike = [number(row.get(k)) for k in ("bid", "ask", "openInterest", "impliedVolatility", "strike")]
    if None in (bid, ask, oi, iv, strike, spot) or spot <= 0:
        return False
    if (bid <= 0 or ask < bid or oi < LIQUIDITY["min_open_interest"] or not 0 < iv <= 5
            or not .8 <= strike / spot <= 1.2 or (ask - bid) / ((ask + bid) / 2) > .25
            or row.get("contractSize") != "REGULAR" or row.get("currency") != "USD"):
        return False
    try:
        trade = timestamp(row["lastTradeDate"])
        dte = (date.fromisoformat(row["expiry"]) - now.date()).days
        age = (now - trade).total_seconds() / 86400
        return 0 <= age <= 7 and 20 <= dte <= 60
    except (KeyError, TypeError, ValueError):
        return False


def summarize_chain(rows, spot, now, *, rate=None, dividend_yield=None, quote_at=None):
    accepted, excluded = [], Counter()
    quote_fresh = quote_at and 0 <= (now - timestamp(quote_at)).total_seconds() <= 4 * 86400
    for row in rows:
        if not quote_fresh or not liquid_contract(row, spot, now):
            excluded["liquidity_or_freshness"] += 1
            continue
        derived = greeks(spot, row["strike"], (date.fromisoformat(row["expiry"]) - now.date()).days / 365.25,
                         row["impliedVolatility"], rate, dividend_yield, row["kind"])
        accepted.append({**row, "greeks": derived})
    expiries = []
    for expiry in sorted({r["expiry"] for r in accepted}):
        calls = [r for r in accepted if r["expiry"] == expiry and r["kind"] == "call"]
        puts = [r for r in accepted if r["expiry"] == expiry and r["kind"] == "put"]
        if min(len(calls), len(puts)) < 3:
            continue
        atm = [min(side, key=lambda r: abs(r["strike"] / spot - 1)) for side in (calls, puts)]
        near_atm = all(abs(r["strike"] / spot - 1) <= .05 for r in atm)
        c25 = [r for r in calls if r["greeks"] and .15 <= r["greeks"]["delta"] <= .35]
        p25 = [r for r in puts if r["greeks"] and -.35 <= r["greeks"]["delta"] <= -.15]
        skew = (min(p25, key=lambda r: abs(r["greeks"]["delta"] + .25))["impliedVolatility"]
                - min(c25, key=lambda r: abs(r["greeks"]["delta"] - .25))["impliedVolatility"] if c25 and p25 else None)
        expiries.append({"expiry": expiry, "liquid_calls": len(calls), "liquid_puts": len(puts),
            "liquid_put_call_oi_ratio": sum(r["openInterest"] for r in puts) / sum(r["openInterest"] for r in calls),
            "atm_iv": sum(r["impliedVolatility"] for r in atm) / 2 if near_atm else None,
            "approx_25delta_put_minus_call_iv": skew})
    iv_points = [e for e in expiries if e["atm_iv"] is not None]
    return {"raw_contracts": len(rows), "liquid_contracts": len(accepted),
        "greeks_contracts": sum(r["greeks"] is not None for r in accepted), "expiries": expiries,
        "term_iv_far_minus_near": iv_points[-1]["atm_iv"] - iv_points[0]["atm_iv"] if len(iv_points) >= 2 else None,
        "excluded": dict(excluded), "accepted_contracts": accepted,
        "status": "usable_context" if expiries else "insufficient_liquidity"}


def fetch_options(ticker, *, db_path=None):
    import yfinance as yf
    now = datetime.now(timezone.utc)
    macro = macro_summary(db_path, as_of=now.isoformat())
    rate_record = macro["rates"].get("SOFR") or macro["rates"].get("EFFR")
    rate = rate_record["value_pct"] / 100 if rate_record else None
    security = yf.Ticker(ticker)
    expiries = [e for e in security.options if 20 <= (date.fromisoformat(e) - now.date()).days <= 60]
    chosen = sorted({min(expiries, key=lambda e: (abs((date.fromisoformat(e) - now.date()).days - target), e))
                     for target in (30, 45, 60)}) if expiries else []
    rows, quote, errors = [], {}, []
    for expiry in chosen:
        try:
            chain = security.option_chain(expiry)
            if not quote:
                quote = chain.underlying or {}
            for kind, frame in (("call", chain.calls), ("put", chain.puts)):
                if len(frame) > 5000:
                    raise ValueError("option_chain_too_large")
                for raw in frame.to_dict("records"):
                    row = {k: number(raw.get(k)) for k in ("strike", "bid", "ask", "lastPrice", "volume", "openInterest", "impliedVolatility")}
                    row.update(kind=kind, expiry=expiry, contractSymbol=str(raw.get("contractSymbol") or ""),
                               contractSize=str(raw.get("contractSize") or ""), currency=str(raw.get("currency") or ""),
                               lastTradeDate=raw["lastTradeDate"].isoformat() if raw.get("lastTradeDate") is not None else None)
                    rows.append(row)
        except Exception as exc:
            errors.append({"expiry": expiry, "code": type(exc).__name__})
    now = datetime.now(timezone.utc)
    quote_time = number(quote.get("regularMarketTime"))
    quote_at = datetime.fromtimestamp(quote_time, timezone.utc).isoformat() if quote_time else None
    spot, dividend = number(quote.get("regularMarketPrice")), number(quote.get("trailingAnnualDividendYield"))
    if dividend is not None and not 0 <= dividend <= .3:
        dividend = None
    result = summarize_chain(rows, spot, now, rate=rate, dividend_yield=dividend, quote_at=quote_at)
    if errors and not rows:
        raise ValueError("option_chain_download_failed")
    if not chosen:
        result["status"] = "no_eligible_expiries"
    return {"source": "Yahoo Finance via yfinance; delayed, indicative quotes",
        "captured_at": now.isoformat(), "ticker": ticker, "spot": spot, "quote_at": quote_at,
        "rate": rate, "rate_reference": rate_record, "dividend_yield": dividend,
        "greeks_method": "European Black-Scholes-Merton approximation; American exercise and discrete dividends not modeled",
        "dealer_gamma_exposure": None, "institutional_flow": None,
        "liquidity_policy": LIQUIDITY, "requested_expiries": chosen, "errors": errors,
        "raw_contracts": rows, "summary": result, "directional_weight": 0}


def refresh_options(ticker, db_path=None):
    return attempt("options", ticker, lambda: fetch_options(ticker, db_path=db_path), db_path=db_path)


def options_coverage(tickers, db_path=None, *, as_of=None):
    now = timestamp(as_of or utcnow())
    schema(db_path)
    states = {(s["family"], s["scope"]): s for s in statuses(db_path)}
    with get_connection(db_path) as con:
        # Compact projection: page loads never deserialize the full chain archive.
        con.execute("""CREATE TABLE IF NOT EXISTS research_option_capture_index (
            batch_id TEXT PRIMARY KEY,scope TEXT NOT NULL,observed_at TEXT NOT NULL,
            quote_day TEXT,usable INTEGER NOT NULL)""")
        con.execute("""INSERT OR IGNORE INTO research_option_capture_index
            SELECT b.batch_id,b.scope,b.observed_at,substr(json_extract(b.payload_json,'$.quote_at'),1,10),
                json_extract(b.payload_json,'$.summary.status')='usable_context'
            FROM research_signal_batches b LEFT JOIN research_option_capture_index i USING(batch_id)
            WHERE b.family='options' AND i.batch_id IS NULL""")
        days = [dict(r) for r in con.execute("""SELECT scope,substr(observed_at,1,10) AS day,
            MAX(usable) AS usable FROM research_option_capture_index WHERE observed_at<=?
            GROUP BY scope,substr(observed_at,1,10) ORDER BY scope,day""", (now.isoformat(),))]
        quote_days = {r[0]: r[1] for r in con.execute("""SELECT scope,COUNT(DISTINCT quote_day)
            FROM research_option_capture_index WHERE observed_at<=? AND usable=1 GROUP BY scope""", (now.isoformat(),))}
    rows = []
    for ticker in sorted(set(tickers)):
        batch = latest_batch("options", ticker, as_of=now.isoformat(), db_path=db_path)
        state = states.get(("options", ticker), {})
        if not batch:
            rows.append({"ticker": ticker, "status": state.get("status", "pending"), "liquid_contracts": 0,
                         "usable_expiries": 0, "error_code": state.get("error_code")})
            continue
        p, s = batch["payload"], batch["payload"]["summary"]
        age = (now - timestamp(batch["observed_at"])).total_seconds() / 3600
        ticker_days = [d for d in days if d["scope"] == ticker]
        usable_days = [d["day"] for d in ticker_days if d["usable"]]
        gaps = [(date.fromisoformat(b) - date.fromisoformat(a)).days for a, b in zip(usable_days, usable_days[1:])]
        rows.append({"ticker": ticker, "status": s["status"] if age <= 36 else "stale",
            "last_attempt_status": state.get("status"), "known_at": batch["observed_at"],
            "raw_contracts": s["raw_contracts"], "liquid_contracts": s["liquid_contracts"],
            "greeks_contracts": s["greeks_contracts"], "usable_expiries": len(s["expiries"]),
            "age_hours": round(age, 1), "batch_id": batch["batch_id"], "partial_errors": len(p["errors"]),
            "capture_dates": len(ticker_days), "usable_dates": len(usable_days),
            "distinct_quote_dates": quote_days.get(ticker, 0),
            "usable_capture_pct": round(len(usable_days) / len(ticker_days) * 100, 1) if ticker_days else 0,
            "max_gap_calendar_days": max(gaps) if gaps else None, "promotion_eligible": False})
    return rows
