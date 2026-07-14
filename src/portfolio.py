"""Portfolio valuation helpers independent of the Streamlit UI."""

from collections.abc import Mapping

import pandas as pd


def normalize_performance(series: pd.Series, base: float = 100.0) -> pd.Series:
    clean = series.dropna()
    if clean.empty or float(clean.iloc[0]) == 0:
        return pd.Series(dtype=float, name=series.name)
    return (clean / float(clean.iloc[0]) * base).rename(series.name)


def calculate_flow_adjusted_benchmark(
    benchmark_prices: pd.Series, portfolio_values: pd.Series, external_flows: pd.Series,
    base: float = 100.0,
) -> pd.Series:
    """Apply portfolio inflow/outflow jumps to a benchmark price-return curve.

    A flow on a non-trading day is applied on the next shared trading date. The
    initial funding establishes the base and therefore does not create a jump.
    """
    aligned = pd.concat(
        [benchmark_prices.rename("benchmark"), portfolio_values.rename("portfolio")],
        axis=1, join="inner",
    ).dropna().sort_index()
    if aligned.empty:
        return pd.Series(dtype=float, name="Flow-adjusted benchmark")
    flows = pd.Series(0.0, index=aligned.index)
    normalized_dates = pd.DatetimeIndex(aligned.index).tz_localize(None).normalize()
    for flow_date, amount in external_flows.groupby(level=0).sum().items():
        eligible = normalized_dates >= pd.Timestamp(flow_date).tz_localize(None).normalize()
        if eligible.any():
            flows.iloc[int(eligible.argmax())] += float(amount)
    result = pd.Series(index=aligned.index, dtype=float, name="Flow-adjusted benchmark")
    result.iloc[0] = base
    for position in range(1, len(aligned)):
        market_growth = float(aligned["benchmark"].iloc[position]) / float(aligned["benchmark"].iloc[position - 1])
        flow = float(flows.iloc[position])
        after_flow = float(aligned["portfolio"].iloc[position])
        before_flow = after_flow - flow
        flow_factor = after_flow / before_flow if flow and before_flow > 0 else 1.0
        result.iloc[position] = float(result.iloc[position - 1]) * market_growth * flow_factor
    return result


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


def simulate_allocation_scenario(
    current_values: Mapping[str, float], proposed_trades: Mapping[str, float], *,
    current_cash: float = 0.0, external_cash_change: float = 0.0,
) -> dict[str, object]:
    """Apply hypothetical dollar trades without changing portfolio persistence."""
    tickers = sorted(set(current_values) | set(proposed_trades))
    after_values: dict[str, float] = {}
    for ticker in tickers:
        after = float(current_values.get(ticker, 0)) + float(proposed_trades.get(ticker, 0))
        if after < -1e-9:
            raise ValueError(f"Hypothetical sale exceeds the {ticker} position value")
        after_values[ticker] = max(0.0, after)
    after_cash = float(current_cash) + float(external_cash_change) - sum(
        float(value) for value in proposed_trades.values()
    )
    if after_cash < -1e-9:
        raise ValueError("Hypothetical purchases exceed available cash plus the external cash change")
    before_total = sum(float(value) for value in current_values.values()) + float(current_cash)
    after_total = sum(after_values.values()) + max(0.0, after_cash)

    def weights(values: Mapping[str, float], cash: float, total: float) -> dict[str, float]:
        result = {ticker: value / total * 100 if total else 0.0 for ticker, value in values.items()}
        result["Cash"] = cash / total * 100 if total else 0.0
        return result

    before_weights = weights(current_values, float(current_cash), before_total)
    after_weights = weights(after_values, max(0.0, after_cash), after_total)
    rows = [{
        "ticker": ticker,
        "current_value": float(current_values.get(ticker, 0)),
        "proposed_trade": float(proposed_trades.get(ticker, 0)),
        "after_value": after_values[ticker],
        "before_weight_pct": before_weights.get(ticker, 0.0),
        "after_weight_pct": after_weights.get(ticker, 0.0),
        "weight_change_pp": after_weights.get(ticker, 0.0) - before_weights.get(ticker, 0.0),
    } for ticker in tickers]
    investable_after = [value for ticker, value in after_weights.items() if ticker != "Cash"]
    return {
        "rows": rows,
        "before_total": before_total,
        "after_total": after_total,
        "after_cash": max(0.0, after_cash),
        "before_max_weight_pct": max(
            (value for ticker, value in before_weights.items() if ticker != "Cash"), default=0.0,
        ),
        "after_max_weight_pct": max(investable_after, default=0.0),
        "before_hhi": sum((value / 100) ** 2 for ticker, value in before_weights.items() if ticker != "Cash"),
        "after_hhi": sum((value / 100) ** 2 for value in investable_after),
    }


def calculate_portfolio_history(
    holdings: list[Mapping[str, object]], histories: Mapping[str, pd.DataFrame],
    currencies: Mapping[str, str] | None = None,
    fx_rates: Mapping[str, float | None] | None = None,
    base_currency: str = "USD",
    lots: list[Mapping[str, object]] | None = None,
    cash_transactions: list[Mapping[str, object]] | None = None,
) -> pd.Series:
    """Value open lots only from their purchase dates across historical closes.

    Legacy holdings without dated lots retain the old current-shares reconstruction,
    because their true ownership start cannot be inferred safely.
    """
    components: list[pd.Series] = []
    currencies, fx_rates = currencies or {}, fx_rates or {}
    dated_lots: dict[str, list[Mapping[str, object]]] = {}
    for lot in lots or []:
        if lot.get("purchase_date"):
            dated_lots.setdefault(str(lot["ticker"]), []).append(lot)
    for holding in holdings:
        ticker = str(holding["ticker"])
        history = histories.get(ticker)
        if history is None or history.empty or "Close" not in history:
            continue
        currency = currencies.get(ticker, base_currency)
        rate = 1.0 if currency == base_currency else fx_rates.get(currency)
        if rate is None:
            continue
        close = history["Close"].dropna().sort_index()
        position_lots = dated_lots.get(ticker, [])
        if position_lots:
            shares_by_day = pd.Series(0.0, index=close.index)
            normalized_index = pd.DatetimeIndex(close.index).tz_localize(None).normalize()
            for lot in position_lots:
                bought = pd.Timestamp(str(lot["purchase_date"])).normalize()
                shares_by_day.loc[normalized_index >= bought] += float(lot["shares"])
            components.append((close * shares_by_day * rate).rename(ticker))
        else:
            components.append(close.rename(ticker) * float(holding["shares"]) * rate)
    if not components:
        return pd.Series(dtype=float, name="Portfolio value")
    frame = pd.concat(components, axis=1).sort_index().ffill().fillna(0.0)
    result = frame.sum(axis=1)
    for transaction in cash_transactions or []:
        currency = str(transaction.get("currency") or base_currency)
        rate = 1.0 if currency == base_currency else fx_rates.get(currency)
        if rate is None:
            continue
        transaction_date = pd.Timestamp(str(transaction["transaction_date"])).normalize()
        normalized_index = pd.DatetimeIndex(result.index).tz_localize(None).normalize()
        result.loc[normalized_index >= transaction_date] += float(transaction["amount"]) * rate
    result = result.rename("Portfolio value")
    return result[result > 0]


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
