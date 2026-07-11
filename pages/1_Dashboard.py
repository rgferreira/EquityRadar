"""Watchlist dashboard."""

import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from datetime import datetime

from src.data.database import (
    get_cached_industry_research,
    get_portfolio_holdings,
    get_watchlist,
    init_db,
)
from src.data.market_data import calculate_metrics, clear_market_data_cache, fetch_price_history, get_price_history_fetched_at
from src.data.fmp import FMPProvider
from src.data.fundamentals import FallbackFundamentalsProvider, get_fundamentals
from src.data.yfinance_fundamentals import YFinanceFundamentalsProvider
from src.data.industry_refresh import industry_refresh_status, schedule_industry_refresh
from src.scoring.risk import calculate_risk_score, explain_risk_score, risk_score_details
from src.scoring.technical import calculate_technical_score, explain_technical_score
from src.scoring.decision import calculate_entry_score, calculate_exit_review_score, entry_label, exit_review_label
from src.scoring.valuation import calculate_valuation_score, explain_valuation_score
from src.scoring.industry import industry_entry_score
from src.utils.config import FMP_API_KEY
from src.ui import inject_app_styles, page_header

st.set_page_config(page_title="Dashboard | Personal Equity Radar", page_icon="📈", layout="wide")
init_db()
fundamentals_providers = []
if FMP_API_KEY:
    fundamentals_providers.append(FMPProvider(FMP_API_KEY))
fundamentals_providers.append(YFinanceFundamentalsProvider())
fundamentals_provider = FallbackFundamentalsProvider(fundamentals_providers)
inject_app_styles()
page_header(
    "Market command center", "Watchlist dashboard",
    "Scan momentum, valuation, risk, and decision signals across every company you follow.",
    "Research only · No execution",
)


def move_manual_ticker(offset: int) -> None:
    """Move the selected ticker before Streamlit rerenders the page."""
    order = list(st.session_state.get("dashboard_manual_order", []))
    ticker = st.session_state.get("manual_order_ticker")
    if ticker not in order:
        return
    current_index = order.index(ticker)
    target_index = current_index + offset
    if 0 <= target_index < len(order):
        order[current_index], order[target_index] = order[target_index], order[current_index]
        st.session_state.dashboard_manual_order = order


def render_dashboard_table(frame: pd.DataFrame) -> None:
    """Render a dense, legible scan table with controlled typography and row height."""
    percentage_columns = {"1M %", "3M %", "6M %", "12M %", "Drawdown %"}
    price_columns = {"Price", "52W High", "52W Low", "50D MA", "100D MA", "200D MA"}
    score_columns = {"Technical", "Valuation", "Risk", "Entry score", "Exit-review score", "Exit score"}

    def display_value(column: str, value: object) -> str:
        if pd.isna(value):
            return "—"
        if column in percentage_columns:
            return f"{float(value):,.2f}%"
        if column in price_columns:
            return f"${float(value):,.2f}"
        if column in score_columns:
            return f"{float(value):.0f}"
        if column in {"Price data fetched at", "Freshness"}:
            return pd.Timestamp(value).strftime("%Y-%m-%d %H:%M:%S")
        return str(value)

    values = [
        [display_value(column, value) for value in frame[column]]
        for column in frame.columns
    ]
    widths = [
        80 if column == "Ticker" else
        112 if column in {"Entry signal", "Exit signal"} else
        145 if column == "Freshness" else
        88
        for column in frame.columns
    ]
    figure = go.Figure(data=[go.Table(
        columnwidth=widths,
        header={
            "values": [f"<b>{column}</b>" for column in frame.columns],
            "align": "left",
            "height": 34,
            "fill_color": "#111827",
            "line_color": "#273244",
            "font": {"color": "#cbd5e1", "size": 12},
        },
        cells={
            "values": values,
            "align": "left",
            "height": 30,
            "fill_color": "#080d16",
            "line_color": "#202938",
            "font": {"color": "#e2e8f0", "size": 12},
        },
    )])
    figure.update_layout(
        height=34 + 30 * len(frame) + 18,
        margin={"l": 0, "r": 0, "t": 0, "b": 0},
        paper_bgcolor="rgba(0,0,0,0)",
    )
    st.plotly_chart(figure, width="stretch", config={"displayModeBar": False})


def non_wrapping_signal_labels(frame: pd.DataFrame) -> pd.DataFrame:
    """Preserve signal semantics; Plotly controls wrapping and density visually."""
    compact = frame.copy()
    return compact.rename(columns={
        "Exit-review score": "Exit score",
        "Price data fetched at": "Freshness",
    })

refresh_col, status_col = st.columns([1, 4], vertical_alignment="center")
with refresh_col:
    refresh = st.button("Refresh market data", type="primary", width="stretch")
with status_col:
    st.caption("Prices refresh automatically on first load. Use refresh to request fresh provider data.")
tickers = get_watchlist()
if not tickers:
    st.info("Add one or more tickers from Watchlist management to begin.")
    st.stop()

initial_refresh = not st.session_state.get("dashboard_initial_refresh_done", False)
if refresh or initial_refresh:
    # Set this before fetching so a provider error does not cause a refresh loop.
    st.session_state.dashboard_initial_refresh_done = True
    clear_market_data_cache()
    rows, errors = [], []
    progress_text = "Loading fresh market data…" if initial_refresh else "Fetching market data…"
    progress = st.progress(0, text=progress_text)
    for index, ticker in enumerate(tickers, start=1):
        try:
            history = fetch_price_history(ticker)
            metrics = calculate_metrics(history)
            technical = calculate_technical_score(metrics)
            fundamentals = get_fundamentals(
                ticker,
                fundamentals_provider,
                current_price=metrics["latest_price"],
                force_refresh=refresh,
            )
            valuation = calculate_valuation_score(fundamentals)
            risk = calculate_risk_score(metrics, history)
            risk_details = risk_score_details(metrics, history)
            industry_risk = min(100, risk + int(risk_details["drawdown_penalty"] or 0))
            industry_research = get_cached_industry_research(ticker)
            industry_breakdown = industry_entry_score(technical, industry_risk, industry_research)
            calibrated_entry = (
                float(industry_breakdown["score"])
                if industry_research else calculate_entry_score(technical, valuation, risk)
            )
            rows.append({
                "Ticker": ticker,
                "Price": metrics["latest_price"],
                "1M %": metrics["return_1m"],
                "3M %": metrics["return_3m"],
                "6M %": metrics["return_6m"],
                "12M %": metrics["return_12m"],
                "52W High": metrics["high_52w"],
                "52W Low": metrics["low_52w"],
                "Drawdown %": metrics["drawdown_from_52w_high"],
                "50D MA": metrics["ma_50"],
                "100D MA": metrics["ma_100"],
                "200D MA": metrics["ma_200"],
                "Technical": technical,
                "Valuation": valuation,
                "Risk": risk,
                "Entry score": calibrated_entry,
                "Entry signal": entry_label(calibrated_entry),
                "Industry calibrated": "Yes" if industry_research else "Pending",
                "Exit-review score": calculate_exit_review_score(technical, risk),
                "Exit signal": exit_review_label(calculate_exit_review_score(technical, risk)),
                "Technical rationale": explain_technical_score(metrics),
                "Risk rationale": explain_risk_score(metrics, history),
                "Valuation rationale": explain_valuation_score(fundamentals),
                "Industry rationale": "; ".join(
                    [*industry_breakdown["quality_notes"], *industry_breakdown["valuation_notes"], *industry_breakdown["analyst_notes"]]
                ) if industry_research else "Open Company detail once to build the daily peer and analyst snapshot.",
                "Price data fetched at": get_price_history_fetched_at(ticker),
            })
        except Exception as exc:
            errors.append(f"{ticker}: {exc}")
        progress.progress(index / len(tickers), text=f"Fetched {index} of {len(tickers)}")
    progress.empty()
    st.session_state.dashboard_rows = rows
    st.session_state.dashboard_errors = errors
    st.session_state.last_refreshed_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

rows = st.session_state.get("dashboard_rows", [])
errors = st.session_state.get("dashboard_errors", [])
if rows:
    portfolio_tickers = [str(item["ticker"]) for item in get_portfolio_holdings()]
    refresh_priority = [*portfolio_tickers, *(ticker for ticker in tickers if ticker not in portfolio_tickers)]
    schedule_industry_refresh(refresh_priority, max_new=2)
    for row in rows:
        research = get_cached_industry_research(str(row["Ticker"]))
        status = industry_refresh_status(str(row["Ticker"]))
        row["Industry calibrated"] = status
        if research and research.get("applicable") is not False:
            drawdown = float(row.get("Drawdown %") or 0)
            drawdown_penalty = min(40, int(abs(min(drawdown, 0))))
            calibrated = industry_entry_score(
                float(row["Technical"]), min(100, float(row["Risk"]) + drawdown_penalty), research
            )
            row["Entry score"] = float(calibrated["score"])
            row["Entry signal"] = entry_label(float(calibrated["score"]))
            row["Industry rationale"] = "; ".join(
                [*calibrated["quality_notes"], *calibrated["valuation_notes"], *calibrated["analyst_notes"]]
            )
    frame = pd.DataFrame(rows)
    above_50 = int((frame["Price"] > frame["50D MA"]).sum())
    above_200 = int((frame["Price"] > frame["200D MA"]).sum())
    avg_entry = frame["Entry score"].mean()
    avg_risk = frame["Risk"].mean()
    overview = st.columns(4)
    overview[0].metric("Companies tracked", len(frame))
    overview[1].metric("Above 50-day MA", f"{above_50}/{len(frame)}", f"{above_50 / len(frame):.0%} breadth")
    overview[2].metric("Above 200-day MA", f"{above_200}/{len(frame)}", f"{above_200 / len(frame):.0%} breadth")
    overview[3].metric("Average entry / risk", f"{avg_entry:.0f} / {avg_risk:.0f}")

    st.subheader("Watchlist signals")
    with st.expander("Customize order and visible metrics"):
        order_mode = st.radio(
            "Ordering mode",
            ["Sort by column", "Manual order"],
            horizontal=True,
        )
        if order_mode == "Sort by column":
            sort_col, sort_direction = st.columns([2, 1])
            with sort_col:
                sort_column = st.selectbox(
                    "Sort column",
                    frame.columns,
                    index=list(frame.columns).index("Entry score"),
                )
            with sort_direction:
                descending = st.checkbox("Descending", value=True)
            frame = frame.sort_values(sort_column, ascending=not descending, na_position="last")
        else:
            current_tickers = frame["Ticker"].tolist()
            saved_order = st.session_state.get("dashboard_manual_order", [])
            manual_order = [ticker for ticker in saved_order if ticker in current_tickers]
            manual_order.extend(ticker for ticker in current_tickers if ticker not in manual_order)
            st.session_state.dashboard_manual_order = manual_order

            selected_ticker = st.selectbox("Ticker to move", manual_order, key="manual_order_ticker")
            move_up, move_down, _ = st.columns([1, 1, 4])
            selected_index = manual_order.index(selected_ticker)
            with move_up:
                st.button(
                    "Move up",
                    disabled=selected_index == 0,
                    on_click=move_manual_ticker,
                    args=(-1,),
                )
            with move_down:
                st.button(
                    "Move down",
                    disabled=selected_index == len(manual_order) - 1,
                    on_click=move_manual_ticker,
                    args=(1,),
                )
            frame = frame.assign(
                _manual_order=frame["Ticker"].map({ticker: index for index, ticker in enumerate(manual_order)})
            ).sort_values("_manual_order").drop(columns="_manual_order")

        optional_columns = [
            "1M %", "3M %", "6M %", "12M %", "Drawdown %",
            "Technical", "Valuation", "Risk",
        ]
        selected_metrics = st.multiselect(
            "Additional table columns",
            [column for column in optional_columns if column in frame.columns],
            default=[],
            help="Keep this empty for the compact phone-friendly decision view.",
        )
    display_frame = frame[[
        "Ticker", "Price", "Entry score", "Exit-review score", "Industry calibrated", *selected_metrics,
    ]].copy()
    display_frame = non_wrapping_signal_labels(display_frame)
    render_dashboard_table(display_frame)
    refreshed_at = st.session_state.get("last_refreshed_at")
    if refreshed_at:
        st.caption(f"Last refreshed: {refreshed_at}. Refresh again to retrieve new provider data.")

    st.caption(f"Market regime · {above_50}/{len(frame)} above 50D MA · {above_200}/{len(frame)} above 200D MA")

    @st.fragment(run_every=5)
    def render_cohort_refresh_status() -> None:
        schedule_industry_refresh(refresh_priority, max_new=2)
        statuses = tuple((ticker, industry_refresh_status(ticker)) for ticker in tickers)
        ready = sum(status in {"Ready", "Limited coverage", "Not applicable"} for _, status in statuses)
        updating = [ticker for ticker, status in statuses if status in {"Updating", "Discovering peers"}]
        st.caption(
            f"Cohort coverage: {ready}/{len(statuses)} ready"
            + (f" · Updating {', '.join(updating)} automatically" if updating else "")
        )
        previous = st.session_state.get("cohort_status_signature")
        st.session_state.cohort_status_signature = statuses
        if previous is not None and previous != statuses:
            st.rerun()

    render_cohort_refresh_status()

    st.subheader("Score rationale")
    for _, row in frame.iterrows():
        with st.expander(f"{row['Ticker']} — {row['Entry signal']} / {row['Exit signal']}"):
            st.write(f"**Entry score ({row['Entry score']:.1f}/100):** potential buy/add attractiveness.")
            st.write(f"**Exit-review score ({row['Exit-review score']:.1f}/100):** urgency to reassess or sell; it is not an execution instruction.")
            fetched_at = pd.Timestamp(row["Price data fetched at"]).strftime("%Y-%m-%d %H:%M:%S")
            st.caption(f"Price freshness: {fetched_at} · Industry calibrated: {row['Industry calibrated']}")
            st.write(f"**Technical ({row['Technical']}/100):** {row['Technical rationale']}")
            st.write(f"**Risk ({row['Risk']}/100):** {row['Risk rationale']}")
            st.write(f"**Valuation ({row['Valuation']}/100):** {row['Valuation rationale']}")
            st.write(f"**Industry Feature:** {row['Industry rationale']}")
if errors:
    st.error("Some data could not be fetched:")
    for error in errors:
        st.write(f"- {error}")
