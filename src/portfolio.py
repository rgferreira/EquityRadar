"""Portfolio valuation helpers independent of the Streamlit UI."""

from collections.abc import Mapping

import pandas as pd


def normalize_performance(series: pd.Series, base: float = 100.0) -> pd.Series:
    clean = series.dropna()
    if clean.empty or float(clean.iloc[0]) == 0:
        return pd.Series(dtype=float, name=series.name)
    return (clean / float(clean.iloc[0]) * base).rename(series.name)


def calculate_return_risk_metrics(series: pd.Series, risk_free_rate: float = 0.0) -> dict[str, float | None]:
    clean = series.dropna()
    returns = clean.pct_change().dropna()
    if returns.empty:
        return {"total_return_pct": None, "annualized_volatility_pct": None, "max_drawdown_pct": None, "sharpe": None}
    total_return = (float(clean.iloc[-1]) / float(clean.iloc[0]) - 1) * 100
    annualized_volatility = float(returns.std(ddof=1) * (252 ** 0.5) * 100) if len(returns) > 1 else 0.0
    max_drawdown = float((clean / clean.cummax() - 1).min() * 100)
    excess_daily = returns - risk_free_rate / 252
    standard_deviation = returns.std(ddof=1)
    sharpe = float(excess_daily.mean() / standard_deviation * (252 ** 0.5)) if len(returns) > 1 and standard_deviation > 0 else None
    return {"total_return_pct": total_return, "annualized_volatility_pct": annualized_volatility, "max_drawdown_pct": max_drawdown, "sharpe": sharpe}


def calculate_risk_contributions(
    holdings: list[Mapping[str, object]], histories: Mapping[str, pd.DataFrame]
) -> dict[str, float]:
    series, values = {}, {}
    for holding in holdings:
        ticker = str(holding["ticker"])
        history = histories.get(ticker)
        if history is None or history.empty or "Close" not in history:
            continue
        close = history["Close"].dropna()
        if len(close) < 3:
            continue
        series[ticker] = close.pct_change()
        values[ticker] = float(holding["shares"]) * float(close.iloc[-1])
    returns = pd.DataFrame(series).dropna()
    total = sum(values.values())
    if returns.empty or total <= 0:
        return {}
    tickers = list(returns.columns)
    weights = pd.Series({ticker: values[ticker] / total for ticker in tickers})
    covariance = returns.cov() * 252
    portfolio_variance = float(weights @ covariance @ weights)
    if portfolio_variance <= 0:
        return {ticker: 0.0 for ticker in tickers}
    contributions = weights * (covariance @ weights) / portfolio_variance * 100
    return {ticker: float(contributions[ticker]) for ticker in tickers}


def calculate_time_weighted_return(
    values: pd.Series, external_flows: pd.Series | None = None
) -> float | None:
    """Calculate linked-period TWR, treating flows as occurring at each period end."""
    clean = values.dropna().sort_index()
    if len(clean) < 2:
        return None
    flows = external_flows.reindex(clean.index, fill_value=0.0) if external_flows is not None else pd.Series(0.0, index=clean.index)
    growth = 1.0
    for index in range(1, len(clean)):
        previous = float(clean.iloc[index - 1])
        if previous == 0:
            return None
        period_return = (float(clean.iloc[index]) - float(flows.iloc[index])) / previous - 1
        growth *= 1 + period_return
    return (growth - 1) * 100


def calculate_rebalance(
    valued_holdings: list[Mapping[str, object]], targets: Mapping[str, float], total_value: float
) -> list[dict[str, float | str]]:
    current = {str(row["ticker"]): float(row.get("market_value") or 0) for row in valued_holdings}
    rows = []
    for ticker in sorted(set(current) | set(targets)):
        target_weight = float(targets.get(ticker, 0))
        target_value = total_value * target_weight / 100
        current_value = current.get(ticker, 0)
        rows.append({
            "ticker": ticker, "current_value": current_value,
            "current_weight_pct": current_value / total_value * 100 if total_value else 0,
            "target_weight_pct": target_weight, "target_value": target_value,
            "trade_value": target_value - current_value,
        })
    return rows


def calculate_portfolio_history(
    holdings: list[Mapping[str, object]], histories: Mapping[str, pd.DataFrame],
    currencies: Mapping[str, str] | None = None,
    fx_rates: Mapping[str, float | None] | None = None,
    base_currency: str = "USD",
) -> pd.Series:
    """Value current shares across historical adjusted closes on common dates."""
    components: list[pd.Series] = []
    currencies, fx_rates = currencies or {}, fx_rates or {}
    for holding in holdings:
        ticker = str(holding["ticker"])
        history = histories.get(ticker)
        if history is None or history.empty or "Close" not in history:
            continue
        currency = currencies.get(ticker, base_currency)
        rate = 1.0 if currency == base_currency else fx_rates.get(currency)
        if rate is None:
            continue
        components.append(history["Close"].dropna().rename(ticker) * float(holding["shares"]) * rate)
    if not components:
        return pd.Series(dtype=float, name="Portfolio value")
    frame = pd.concat(components, axis=1).sort_index().ffill().dropna(how="all")
    return frame.sum(axis=1, min_count=1).rename("Portfolio value")


def enrich_holdings(
    holdings: list[Mapping[str, object]], latest_prices: Mapping[str, float],
    lots: list[Mapping[str, object]] | None = None,
    currencies: Mapping[str, str] | None = None,
    fx_rates: Mapping[str, float | None] | None = None,
    base_currency: str = "USD",
) -> list[dict[str, object]]:
    rows = []
    lots = lots or []
    currencies, fx_rates = currencies or {}, fx_rates or {}
    lots_by_ticker: dict[str, list[Mapping[str, object]]] = {}
    for lot in lots:
        lots_by_ticker.setdefault(str(lot["ticker"]), []).append(lot)
    normalized_values: dict[str, float | None] = {}
    for item in holdings:
        ticker = str(item["ticker"])
        price = latest_prices.get(ticker)
        currency = currencies.get(ticker, base_currency)
        rate = 1.0 if currency == base_currency else fx_rates.get(currency)
        normalized_values[ticker] = (
            float(item["shares"]) * price * rate if price is not None and rate is not None else None
        )
    total = sum(value for value in normalized_values.values() if value is not None)
    for holding in holdings:
        row = dict(holding)
        ticker = str(holding["ticker"])
        price = latest_prices.get(ticker)
        currency = currencies.get(ticker, base_currency)
        fx_rate = 1.0 if currency == base_currency else fx_rates.get(currency)
        local_value = float(holding["shares"]) * price if price is not None else None
        value = normalized_values[ticker]
        position_lots = lots_by_ticker.get(ticker, [])
        cost_known = bool(position_lots) and all(lot.get("price_per_share") is not None for lot in position_lots)
        local_cost_basis = (
            sum(float(lot["shares"]) * float(lot["price_per_share"]) + float(lot.get("fees", 0) or 0) for lot in position_lots)
            if cost_known else None
        )
        cost_basis = local_cost_basis * fx_rate if local_cost_basis is not None and fx_rate is not None else None
        avg_cost = local_cost_basis / float(holding["shares"]) if local_cost_basis is not None and holding["shares"] else None
        unrealized_pl = value - cost_basis if value is not None and cost_basis is not None else None
        return_pct = unrealized_pl / cost_basis * 100 if unrealized_pl is not None and cost_basis else None
        row.update({
            "price": price, "currency": currency, "fx_to_base": fx_rate,
            "local_market_value": local_value, "market_value": value,
            "weight_pct": value / total * 100 if value is not None and total else None,
            "local_cost_basis": local_cost_basis, "cost_basis": cost_basis, "average_cost": avg_cost,
            "unrealized_pl": unrealized_pl, "return_pct": return_pct,
        })
        rows.append(row)
    return rows
