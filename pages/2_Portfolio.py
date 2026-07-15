"""Manual portfolio holdings, current valuation, and reconstructed history."""

from datetime import date

import plotly.graph_objects as go
import pandas as pd
import streamlit as st

from src.data.database import (
    add_portfolio_lot,
    add_cash_transaction,
    delete_cash_transaction,
    delete_portfolio_lot,
    get_portfolio_holdings,
    get_portfolio_lots,
    get_portfolio_sales,
    get_portfolio_targets,
    get_cash_transactions,
    get_cached_industry_research,
    get_watchlist,
    init_db,
    record_portfolio_sale,
    save_portfolio_snapshot,
    set_portfolio_target,
    update_portfolio_lot,
)
from src.data.market_data import (
    clear_market_data_cache, fetch_fx_rate, fetch_price_history, fetch_quote_currency,
)
from src.portfolio import (
    calculate_flow_adjusted_benchmark, calculate_portfolio_history, calculate_return_risk_metrics, calculate_risk_contributions,
    calculate_rebalance, enrich_holdings, normalize_performance,
)
from src.import_export import CSV_TEMPLATE, import_transactions_csv
from src.downloads import download_link
from src.utils.config import DATABASE_PATH, PORTFOLIO_BASE_CURRENCY
from src.ui import inject_app_styles, page_header, zebra_table

st.set_page_config(page_title="Portfolio | Personal Equity Radar", page_icon="💼", layout="wide")
init_db()
inject_app_styles()
page_header(
    "Portfolio intelligence", "Portfolio",
    "Understand what you own, how it performs, and where concentration or risk deserves attention.",
    f"Base currency · {PORTFOLIO_BASE_CURRENCY}",
)

with st.expander("Import, export, and backup"):
    st.markdown(download_link("Download transaction CSV template", CSV_TEMPLATE, "portfolio-transactions-template.csv", "text/csv"))
    pasted_csv = st.text_area("Paste transactions CSV", height=140, placeholder=CSV_TEMPLATE)
    if pasted_csv.strip() and st.button("Import pasted transactions"):
        result = import_transactions_csv(pasted_csv)
        st.success(f"Imported {result['imported']} transaction(s).")
        for import_error in result["errors"]:
            st.warning(import_error)
        if result["imported"]:
            st.rerun()

with st.expander("Add purchase lot"):
    portfolio_choices = ["Add a new ticker…", *get_watchlist()]
    with st.form("portfolio_lot", clear_on_submit=True):
        selected_ticker = st.selectbox("Watchlist ticker", portfolio_choices)
        new_ticker = st.text_input("New ticker", placeholder="MSFT") if selected_ticker == portfolio_choices[0] else ""
        purchase_date = st.date_input("Purchase date", value=date.today())
        shares = st.number_input("Shares", min_value=0.0, step=1.0)
        price_per_share = st.number_input("Price per share", min_value=0.0, step=0.01)
        fees = st.number_input("Fees", min_value=0.0, step=0.01)
        lot_notes = st.text_input("Notes", placeholder="Broker, account, or optional context")
        save_lot = st.form_submit_button("Add purchase lot", type="primary")

    if save_lot:
        portfolio_ticker = new_ticker if selected_ticker == portfolio_choices[0] else selected_ticker
        try:
            add_portfolio_lot({
                "ticker": portfolio_ticker,
                "purchase_date": purchase_date.isoformat(),
                "shares": shares,
                "price_per_share": price_per_share,
                "fees": fees,
                "notes": lot_notes,
            })
            st.success(f"Purchase lot added for {portfolio_ticker.strip().upper()}.")
            st.rerun()
        except ValueError as exc:
            st.warning(str(exc))

editable_lots = get_portfolio_lots()
with st.expander("Edit/Delete lots"):
    if not editable_lots:
        st.caption("No purchase lots to edit yet.")
    else:
        lot_labels = {
            f"#{lot['id']} · {lot['ticker']} · {lot['purchase_date'] or 'unknown date'} · {lot['shares']} shares": lot
            for lot in editable_lots
        }
        selected_lot_label = st.selectbox("Lot to edit or delete", list(lot_labels))
        selected_lot = lot_labels[selected_lot_label]
        selected_lot_id = int(selected_lot["id"])
        watchlist = get_watchlist()
        with st.form("edit_portfolio_lot"):
            edit_ticker = st.selectbox(
                "Ticker", watchlist, index=watchlist.index(selected_lot["ticker"]),
                key=f"edit_lot_ticker_{selected_lot_id}",
            )
            edit_date = st.date_input(
                "Purchase date",
                value=date.fromisoformat(selected_lot["purchase_date"]) if selected_lot["purchase_date"] else date.today(),
                key=f"edit_lot_date_{selected_lot_id}",
            )
            edit_shares = st.number_input(
                "Shares", min_value=0.0001, value=float(selected_lot["shares"]), step=1.0,
                key=f"edit_lot_shares_{selected_lot_id}",
            )
            edit_price = st.number_input(
                "Price per share", min_value=0.01, value=float(selected_lot["price_per_share"] or 0.01), step=0.01,
                key=f"edit_lot_price_{selected_lot_id}",
            )
            edit_fees = st.number_input(
                "Fees", min_value=0.0, value=float(selected_lot["fees"]), step=0.01,
                key=f"edit_lot_fees_{selected_lot_id}",
            )
            edit_notes = st.text_input(
                "Notes", value=selected_lot["notes"] or "", key=f"edit_lot_notes_{selected_lot_id}",
            )
            update_lot = st.form_submit_button("Update lot")
        if update_lot:
            update_portfolio_lot(selected_lot_id, {
                "ticker": edit_ticker, "purchase_date": edit_date.isoformat(), "shares": edit_shares,
                "price_per_share": edit_price, "fees": edit_fees, "notes": edit_notes,
            })
            st.success("Purchase lot updated.")
            st.rerun()

        confirm_delete_lot = st.checkbox(
            "I understand this permanently deletes the selected lot", key="confirm_top_lot_delete",
        )
        if st.button("Delete selected lot", disabled=not confirm_delete_lot, key="delete_top_lot"):
            delete_portfolio_lot(selected_lot_id)
            st.success("Purchase lot deleted.")
            st.rerun()

with st.expander("Add cash or dividend transaction"):
    with st.form("cash_transaction", clear_on_submit=True):
        cash_type = st.selectbox(
            "Transaction type", ["deposit", "withdrawal", "dividend", "withholding_tax", "fee", "adjustment"]
        )
        cash_date = st.date_input("Transaction date", value=date.today())
        cash_amount = st.number_input("Amount", value=0.0, step=0.01)
        cash_currency = st.text_input("Currency", value=PORTFOLIO_BASE_CURRENCY, max_chars=3)
        cash_ticker = st.selectbox("Related ticker (optional)", ["None", *get_watchlist()])
        cash_notes = st.text_input("Cash transaction notes")
        save_cash = st.form_submit_button("Add cash transaction")
    if save_cash:
        try:
            add_cash_transaction({
                "transaction_date": cash_date.isoformat(), "transaction_type": cash_type,
                "amount": cash_amount, "currency": cash_currency,
                "ticker": "" if cash_ticker == "None" else cash_ticker, "notes": cash_notes,
            })
            st.success("Cash transaction recorded.")
            st.rerun()
        except ValueError as exc:
            st.warning(str(exc))

holdings_before_sale = get_portfolio_holdings()
if holdings_before_sale:
    with st.expander("Record sale"):
        with st.form("portfolio_sale", clear_on_submit=True):
            sale_ticker = st.selectbox("Ticker to sell", [str(item["ticker"]) for item in holdings_before_sale])
            sale_date = st.date_input("Sale date", value=date.today())
            sale_shares = st.number_input("Shares sold", min_value=0.0, step=1.0)
            sale_price = st.number_input("Sale price per share", min_value=0.0, step=0.01)
            sale_fees = st.number_input("Sale fees", min_value=0.0, step=0.01)
            sale_notes = st.text_input("Sale notes", placeholder="Optional context")
            save_sale = st.form_submit_button("Record sale")
        if save_sale:
            try:
                record_portfolio_sale({
                    "ticker": sale_ticker, "sale_date": sale_date.isoformat(), "shares": sale_shares,
                    "price_per_share": sale_price, "fees": sale_fees, "notes": sale_notes,
                    "currency": fetch_quote_currency(sale_ticker) or PORTFOLIO_BASE_CURRENCY,
                })
                st.success(f"Sale recorded for {sale_ticker} using FIFO lots.")
                st.rerun()
            except ValueError as exc:
                st.warning(str(exc))

holdings = get_portfolio_holdings()
if not holdings:
    st.info("No stocks are currently marked as owned.")
    st.stop()

refresh = st.button("Refresh portfolio prices")
if refresh:
    clear_market_data_cache()

histories, errors = {}, []
with st.spinner("Valuing portfolio…"):
    for holding in holdings:
        ticker = str(holding["ticker"])
        try:
            histories[ticker] = fetch_price_history(ticker, period="max")
        except Exception as exc:
            errors.append(f"{ticker}: {exc}")

latest_prices = {
    ticker: float(history["Close"].dropna().iloc[-1])
    for ticker, history in histories.items()
    if not history.empty and history["Close"].notna().any()
}
lots = get_portfolio_lots()
sales = get_portfolio_sales()
currencies = {ticker: fetch_quote_currency(ticker) or PORTFOLIO_BASE_CURRENCY for ticker in latest_prices}
cash_transactions = get_cash_transactions()
cash_currencies = {str(item["currency"]) for item in cash_transactions}
fx_rates = {
    currency: fetch_fx_rate(currency, PORTFOLIO_BASE_CURRENCY)
    for currency in set(currencies.values()) | cash_currencies if currency != PORTFOLIO_BASE_CURRENCY
}
valued_holdings = enrich_holdings(
    holdings, latest_prices, lots, currencies, fx_rates, PORTFOLIO_BASE_CURRENCY
)
normalized_sales = []
for sale in sales:
    normalized_sale = dict(sale)
    sale_currency = currencies.get(str(sale["ticker"]), PORTFOLIO_BASE_CURRENCY)
    sale_fx = 1.0 if sale_currency == PORTFOLIO_BASE_CURRENCY else fx_rates.get(sale_currency)
    normalized_sale["currency"] = sale_currency
    normalized_sale["fx_to_base"] = sale_fx
    normalized_sale["realized_pl_base"] = (
        float(sale["realized_pl"]) * sale_fx
        if sale["realized_pl"] is not None and sale_fx is not None else None
    )
    normalized_sales.append(normalized_sale)
known_values = [float(row["market_value"]) for row in valued_holdings if row["market_value"] is not None]
cash_balance_base = sum(
    float(item["amount"]) * (1.0 if item["currency"] == PORTFOLIO_BASE_CURRENCY else fx_rates.get(str(item["currency"]), 0) or 0)
    for item in cash_transactions
)
total_value = sum(known_values) + cash_balance_base
known_unrealized = [float(row["unrealized_pl"]) for row in valued_holdings if row["unrealized_pl"] is not None]
known_realized = [float(sale["realized_pl_base"]) for sale in normalized_sales if sale["realized_pl_base"] is not None]
holdings_frame = pd.DataFrame(valued_holdings)
holdings_frame["updated_at"] = pd.to_datetime(holdings_frame["updated_at"])

with st.expander("Portfolio exports"):
    export_links = [
        download_link("Holdings CSV", holdings_frame.to_csv(index=False), "portfolio-holdings.csv", "text/csv"),
        download_link("Lots CSV", pd.DataFrame(lots).to_csv(index=False), "portfolio-lots.csv", "text/csv"),
        download_link("Sales CSV", pd.DataFrame(sales).to_csv(index=False), "portfolio-sales.csv", "text/csv"),
        download_link("Cash CSV", pd.DataFrame(cash_transactions).to_csv(index=False), "portfolio-cash.csv", "text/csv"),
    ]
    st.markdown("  \n".join(export_links))
    st.caption("The SQLite backup is prepared only on request so normal page loads stay lightweight.")
    if DATABASE_PATH.exists() and st.button("Prepare SQLite database backup", key="prepare_portfolio_backup"):
        st.download_button(
            "Download SQLite database backup", data=DATABASE_PATH.read_bytes(),
            file_name="personal-equity-radar-backup.db", mime="application/x-sqlite3",
            on_click="ignore",
        )
save_portfolio_snapshot(
    date.today().isoformat(), total_value, len(known_values), len(holdings), PORTFOLIO_BASE_CURRENCY
)

value_columns = st.columns(3)
value_columns[0].metric("Current portfolio value", f"{PORTFOLIO_BASE_CURRENCY} {total_value:,.2f}")
value_columns[1].metric("Known unrealized P&L", f"{PORTFOLIO_BASE_CURRENCY} {sum(known_unrealized):,.2f}" if known_unrealized else "—")
value_columns[2].metric("Cash balance", f"{PORTFOLIO_BASE_CURRENCY} {cash_balance_base:,.2f}")

coverage_columns = st.columns(3)
coverage_columns[0].metric("Positions", len(holdings))
coverage_columns[1].metric("Priced positions", f"{len(known_values)}/{len(holdings)}")
coverage_columns[2].metric("Known realized P&L", f"{PORTFOLIO_BASE_CURRENCY} {sum(known_realized):,.2f}" if known_realized else "—")

st.dataframe(
    zebra_table(holdings_frame),
    hide_index=True,
    width="stretch",
    column_config={
        "ticker": "Ticker",
        "shares": st.column_config.NumberColumn("Shares", format="%.2f"),
        "price": st.column_config.NumberColumn("Current price", format="$%.2f"),
        "currency": "Trading currency",
        "fx_to_base": st.column_config.NumberColumn(f"FX to {PORTFOLIO_BASE_CURRENCY}", format="%.6f"),
        "local_market_value": st.column_config.NumberColumn("Local market value", format="%.2f"),
        "market_value": st.column_config.NumberColumn(f"Value ({PORTFOLIO_BASE_CURRENCY})", format="%.2f"),
        "weight_pct": st.column_config.NumberColumn("Weight", format="%.2f%%"),
        "local_cost_basis": st.column_config.NumberColumn("Local cost basis", format="%.2f"),
        "cost_basis": st.column_config.NumberColumn(f"Cost basis ({PORTFOLIO_BASE_CURRENCY})", format="%.2f"),
        "average_cost": st.column_config.NumberColumn("Average cost", format="$%.2f"),
        "unrealized_pl": st.column_config.NumberColumn("Unrealized P&L", format="$%.2f"),
        "return_pct": st.column_config.NumberColumn("Return", format="%.2f%%"),
        "updated_at": st.column_config.DatetimeColumn("Holding updated", format="YYYY-MM-DD HH:mm:ss"),
    },
)

if lots:
    st.subheader("Purchase lots")
    lots_frame = pd.DataFrame(lots)
    lots_frame["purchase_date"] = pd.to_datetime(lots_frame["purchase_date"], errors="coerce")
    lots_frame["cost_basis"] = (
        lots_frame["shares"] * lots_frame["price_per_share"] + lots_frame["fees"]
    )
    st.dataframe(
        zebra_table(lots_frame),
        hide_index=True,
        width="stretch",
        column_config={
            "purchase_date": st.column_config.DateColumn("Purchase date", format="YYYY-MM-DD"),
            "shares": st.column_config.NumberColumn("Shares", format="%.4f"),
            "price_per_share": st.column_config.NumberColumn("Purchase price", format="$%.2f"),
            "fees": st.column_config.NumberColumn("Fees", format="$%.2f"),
            "cost_basis": st.column_config.NumberColumn("Cost basis", format="$%.2f"),
        },
    )
    legacy_count = sum(
        1 for lot in lots
        if lot["source"] == "legacy" and (not lot.get("purchase_date") or lot.get("price_per_share") is None)
    )
    if legacy_count:
        st.info(
            f"{legacy_count} migrated lot(s) have unknown purchase date/price. Use Edit/Delete lots above when those details are available."
        )

if sales:
    st.subheader("Sales and realized P&L")
    sales_frame = pd.DataFrame(normalized_sales)
    sales_frame["sale_date"] = pd.to_datetime(sales_frame["sale_date"])
    st.dataframe(
        zebra_table(sales_frame),
        hide_index=True,
        width="stretch",
        column_config={
            "sale_date": st.column_config.DateColumn("Sale date", format="YYYY-MM-DD"),
            "shares": st.column_config.NumberColumn("Shares", format="%.4f"),
            "price_per_share": st.column_config.NumberColumn("Sale price", format="$%.2f"),
            "fees": st.column_config.NumberColumn("Fees", format="$%.2f"),
            "cost_basis": st.column_config.NumberColumn("FIFO cost basis", format="$%.2f"),
            "realized_pl": st.column_config.NumberColumn("Realized P&L", format="$%.2f"),
            "realized_pl_base": st.column_config.NumberColumn(f"Realized P&L ({PORTFOLIO_BASE_CURRENCY})", format="%.2f"),
        },
    )
    if any(sale["realized_pl"] is None for sale in sales):
        st.info("Realized P&L is unavailable for sales that consumed legacy lots with unknown purchase cost.")

if cash_transactions:
    st.subheader("Cash ledger")
    cash_frame = pd.DataFrame(cash_transactions)
    cash_frame["transaction_type"] = cash_frame.apply(
        lambda row: "sale proceeds" if pd.notna(row.get("source_sale_id")) else row["transaction_type"],
        axis=1,
    )
    cash_frame["transaction_date"] = pd.to_datetime(cash_frame["transaction_date"])
    cash_frame["amount_base"] = [
        float(item["amount"]) * (1.0 if item["currency"] == PORTFOLIO_BASE_CURRENCY else fx_rates.get(str(item["currency"]), 0) or 0)
        for item in cash_transactions
    ]
    st.dataframe(
        zebra_table(cash_frame), hide_index=True, width="stretch",
        column_config={
            "transaction_date": st.column_config.DateColumn("Date", format="YYYY-MM-DD"),
            "amount": st.column_config.NumberColumn("Amount", format="%.2f"),
            "amount_base": st.column_config.NumberColumn(f"Amount ({PORTFOLIO_BASE_CURRENCY})", format="%.2f"),
        },
    )
    deletable_cash_transactions = [item for item in cash_transactions if item.get("source_sale_id") is None]
    cash_labels = {
        f"#{item['id']} · {item['transaction_date']} · {item['transaction_type']} · {item['amount']} {item['currency']}": item
        for item in deletable_cash_transactions
    }
    if cash_labels:
        cash_to_delete = st.selectbox("Cash transaction to delete", list(cash_labels))
        confirm_cash_delete = st.checkbox("I understand this permanently deletes the selected cash transaction")
        if st.button("Delete cash transaction", disabled=not confirm_cash_delete):
            delete_cash_transaction(int(cash_labels[cash_to_delete]["id"]))
            st.success("Cash transaction deleted.")
            st.rerun()
    if len(deletable_cash_transactions) != len(cash_transactions):
        st.caption("Sale-proceeds entries are linked to their sale record and cannot be deleted independently.")

portfolio_history = calculate_portfolio_history(
    holdings, histories, currencies, fx_rates, PORTFOLIO_BASE_CURRENCY, lots, cash_transactions
)
if not portfolio_history.empty:
    st.subheader("Portfolio value over time")
    st.caption(
        "Each purchase lot enters the portfolio on its recorded purchase date. Values use historical closing prices; "
        "legacy lots with no date are necessarily treated as held throughout the available history."
    )
    figure = go.Figure()
    figure.add_scatter(x=portfolio_history.index, y=portfolio_history, name="Portfolio value", fill="tozeroy")
    figure.update_layout(height=430, yaxis_title=f"Value ({PORTFOLIO_BASE_CURRENCY})", xaxis_title=None)
    st.plotly_chart(figure, width="stretch")

    st.subheader("Return and risk analytics")
    st.caption("Metrics use the same lot- and purchase-date-aware value series shown above.")
    analytics = calculate_return_risk_metrics(portfolio_history)
    analytics_columns = st.columns(4)
    analytics_columns[0].metric("Value change", "—" if analytics["total_return_pct"] is None else f"{analytics['total_return_pct']:.2f}%")
    analytics_columns[1].metric("Annualized volatility", "—" if analytics["annualized_volatility_pct"] is None else f"{analytics['annualized_volatility_pct']:.2f}%")
    analytics_columns[2].metric("Maximum drawdown", "—" if analytics["max_drawdown_pct"] is None else f"{analytics['max_drawdown_pct']:.2f}%")
    analytics_columns[3].metric("Sharpe (0% risk-free)", "—" if analytics["sharpe"] is None else f"{analytics['sharpe']:.2f}")
    contributions = calculate_risk_contributions(holdings, histories)
    if contributions:
        contribution_frame = pd.DataFrame({"Ticker": list(contributions), "Risk contribution %": list(contributions.values())})
        st.dataframe(
            zebra_table(contribution_frame.sort_values("Risk contribution %", ascending=False)), hide_index=True,
            width="stretch", column_config={"Risk contribution %": st.column_config.NumberColumn(format="%.2f%%")},
        )

    st.subheader("Benchmark comparison")
    benchmark_options = {
        "S&P 500": "^GSPC", "Nasdaq Composite": "^IXIC", "MSCI World ETF (URTH)": "URTH"
    }
    benchmark_label = st.selectbox("Benchmark", list(benchmark_options))
    benchmark_ticker = benchmark_options[benchmark_label]
    try:
        benchmark_history = fetch_price_history(benchmark_ticker, period="max")
        flow_rows = []
        for lot in lots:
            if lot.get("purchase_date") and lot.get("price_per_share") is not None:
                currency = currencies.get(str(lot["ticker"]), PORTFOLIO_BASE_CURRENCY)
                rate = 1.0 if currency == PORTFOLIO_BASE_CURRENCY else fx_rates.get(currency)
                if rate is not None:
                    amount = (float(lot["shares"]) * float(lot["price_per_share"]) + float(lot.get("fees", 0) or 0)) * rate
                    flow_rows.append((pd.Timestamp(str(lot["purchase_date"])), amount))
        for item in cash_transactions:
            if item["transaction_type"] not in {"deposit", "withdrawal", "adjustment"}:
                continue
            rate = 1.0 if item["currency"] == PORTFOLIO_BASE_CURRENCY else fx_rates.get(str(item["currency"]))
            if rate is not None:
                flow_rows.append((pd.Timestamp(str(item["transaction_date"])), float(item["amount"]) * rate))
        external_flows = (
            pd.DataFrame(flow_rows, columns=["date", "amount"]).groupby("date")["amount"].sum()
            if flow_rows else pd.Series(dtype=float)
        )
        adjusted_benchmark = calculate_flow_adjusted_benchmark(
            benchmark_history["Close"], portfolio_history, external_flows,
        )
        aligned = pd.concat([
            normalize_performance(portfolio_history), adjusted_benchmark,
        ], axis=1, join="inner").dropna()
        aligned.columns = ["Portfolio", benchmark_label]
        comparison = go.Figure()
        comparison.add_scatter(x=aligned.index, y=aligned["Portfolio"], name="Portfolio")
        comparison.add_scatter(x=aligned.index, y=aligned[benchmark_label], name=benchmark_label)
        comparison.update_layout(height=380, yaxis_title="Growth of 100", xaxis_title=None)
        st.plotly_chart(comparison, width="stretch")
        st.caption("Both curves receive the same proportional jump when new capital enters the portfolio.")
    except Exception as exc:
        st.warning(f"Benchmark unavailable: {exc}")

st.subheader("Allocation and concentration")
allocation_rows = [row for row in valued_holdings if row["market_value"] is not None]
if allocation_rows:
    allocation_frame = pd.DataFrame(allocation_rows)
    profiles = {}
    for ticker in allocation_frame["ticker"]:
        research = get_cached_industry_research(str(ticker)) or {}
        profile = research.get("profile") or {}
        profiles[ticker] = profile if isinstance(profile, dict) else {}
    allocation_frame["sector"] = [profiles[ticker].get("sector") or "Unknown" for ticker in allocation_frame["ticker"]]
    allocation_frame["country"] = [profiles[ticker].get("country") or "Unknown" for ticker in allocation_frame["ticker"]]
    allocation_tabs = st.tabs(["Position", "Sector", "Country", "Currency"])
    for tab, field in zip(allocation_tabs, ["ticker", "sector", "country", "currency"]):
        grouped = allocation_frame.groupby(field, as_index=False)["market_value"].sum()
        with tab:
            pie = go.Figure(data=[go.Pie(labels=grouped[field], values=grouped["market_value"], hole=.42)])
            pie.update_layout(height=360, margin={"t": 20, "b": 20, "l": 20, "r": 20})
            st.plotly_chart(pie, width="stretch")
    concentrated = allocation_frame[allocation_frame["weight_pct"] > 35]
    if not concentrated.empty:
        labels = ", ".join(f"{row.ticker} ({row.weight_pct:.1f}%)" for row in concentrated.itertuples())
        st.warning(f"Position concentration above 35%: {labels}")

st.subheader("Targets and rebalancing")
with st.form("portfolio_target"):
    target_ticker = st.selectbox("Target ticker", get_watchlist())
    target_weight = st.number_input("Target weight %", min_value=0.0, max_value=100.0, step=1.0)
    save_target = st.form_submit_button("Save target weight")
if save_target:
    set_portfolio_target(target_ticker, target_weight)
    st.success(f"Target saved for {target_ticker}.")
    st.rerun()

target_rows = get_portfolio_targets()
if target_rows:
    target_map = {str(row["ticker"]): float(row["target_weight_pct"]) for row in target_rows}
    target_total = sum(target_map.values())
    if abs(target_total - 100) > 0.01:
        st.warning(f"Target weights sum to {target_total:.2f}%, not 100%. Trade amounts are provisional.")
    rebalance_frame = pd.DataFrame(calculate_rebalance(valued_holdings, target_map, total_value))
    st.dataframe(
        zebra_table(rebalance_frame), hide_index=True, width="stretch",
        column_config={
            "current_value": st.column_config.NumberColumn(f"Current ({PORTFOLIO_BASE_CURRENCY})", format="%.2f"),
            "current_weight_pct": st.column_config.NumberColumn("Current weight", format="%.2f%%"),
            "target_weight_pct": st.column_config.NumberColumn("Target weight", format="%.2f%%"),
            "target_value": st.column_config.NumberColumn(f"Target ({PORTFOLIO_BASE_CURRENCY})", format="%.2f"),
            "trade_value": st.column_config.NumberColumn("Buy (+) / sell (-)", format="%.2f"),
        },
    )
    st.caption("Planning aid only. No orders are generated or transmitted.")

if errors:
    st.warning("Some positions could not be priced; available positions are still shown.")
    for error in errors:
        st.write(f"- {error}")
missing_fx = [currency for currency, rate in fx_rates.items() if rate is None]
if missing_fx:
    st.warning(f"Missing FX conversion to {PORTFOLIO_BASE_CURRENCY}: {', '.join(sorted(missing_fx))}.")
