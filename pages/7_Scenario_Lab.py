"""Non-executing portfolio allocation laboratory."""

from __future__ import annotations

import pandas as pd
import streamlit as st

from src.data.database import (
    get_cash_transactions, get_portfolio_holdings, get_watchlist,
)
from src.data.market_data import fetch_price_history
from src.portfolio import simulate_allocation_scenario
from src.ui import inject_app_styles, page_header, zebra_table


st.set_page_config(page_title="Scenario lab | Personal Equity Radar", page_icon="🧭", layout="wide")
inject_app_styles()
page_header(
    "Counterfactual portfolio", "Scenario lab",
    "Explore cash additions, buys and sells before recording any real transaction.",
    "Simulation only · Never executes",
)
st.warning(
    "Nothing entered here changes holdings, lots, cash, Journal records or model evidence. "
    "Trades are gross USD allocation assumptions and exclude taxes, fees, FX and market impact."
)

holdings = get_portfolio_holdings()
current_values = {}
for holding in holdings:
    try:
        history = fetch_price_history(str(holding["ticker"]), period="1y")
        if not history.empty:
            current_values[str(holding["ticker"])] = float(holding["shares"]) * float(history["Close"].dropna().iloc[-1])
    except Exception:
        # One unavailable quote must not prevent analysis of the remaining positions.
        continue

cash = sum(float(row["amount"]) for row in get_cash_transactions())
universe = sorted(set(get_watchlist()) | set(current_values))
if not universe:
    st.info("Add a watchlist ticker before building a scenario.")
    st.stop()

external_cash = st.number_input(
    "Hypothetical external cash addition (USD)", min_value=0.0, value=0.0, step=100.0,
)
editor = pd.DataFrame({
    "Ticker": universe,
    "Current value (USD)": [current_values.get(ticker, 0.0) for ticker in universe],
    "Proposed trade (USD)": [0.0] * len(universe),
})
edited = st.data_editor(
    editor, hide_index=True, width="stretch", key="scenario-trades",
    disabled=["Ticker", "Current value (USD)"],
    column_config={
        "Current value (USD)": st.column_config.NumberColumn(format="$%.2f"),
        "Proposed trade (USD)": st.column_config.NumberColumn(
            help="Positive = hypothetical buy; negative = hypothetical sale", format="$%.2f",
        ),
    },
)
trades = {
    str(row["Ticker"]): float(row["Proposed trade (USD)"] or 0)
    for _, row in edited.iterrows() if float(row["Proposed trade (USD)"] or 0)
}
try:
    scenario = simulate_allocation_scenario(
        current_values, trades, current_cash=max(0.0, cash), external_cash_change=external_cash,
    )
except ValueError as exc:
    st.error(str(exc))
    st.stop()

metrics = st.columns(4)
metrics[0].metric("Portfolio after scenario", f"${scenario['after_total']:,.2f}")
metrics[1].metric("Cash after scenario", f"${scenario['after_cash']:,.2f}")
metrics[2].metric(
    "Largest position", f"{scenario['after_max_weight_pct']:.1f}%",
    delta=f"{scenario['after_max_weight_pct'] - scenario['before_max_weight_pct']:+.1f} pp",
    delta_color="inverse",
)
metrics[3].metric(
    "Concentration HHI", f"{scenario['after_hhi']:.3f}",
    delta=f"{scenario['after_hhi'] - scenario['before_hhi']:+.3f}", delta_color="inverse",
)
result = pd.DataFrame(scenario["rows"])
st.dataframe(
    zebra_table(result), hide_index=True, width="stretch",
    column_config={
        "current_value": st.column_config.NumberColumn("Current value", format="$%.2f"),
        "proposed_trade": st.column_config.NumberColumn("Hypothetical trade", format="$%+.2f"),
        "after_value": st.column_config.NumberColumn("Value after", format="$%.2f"),
        "before_weight_pct": st.column_config.NumberColumn("Weight before", format="%.2f%%"),
        "after_weight_pct": st.column_config.NumberColumn("Weight after", format="%.2f%%"),
        "weight_change_pp": st.column_config.NumberColumn("Weight Δ", format="%+.2f pp"),
    },
)
st.caption("Scenario results are decision support only and cannot create orders or portfolio records.")
