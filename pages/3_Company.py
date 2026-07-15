"""Company detail page."""

import plotly.graph_objects as go
from plotly.subplots import make_subplots
import pandas as pd
import streamlit as st

from src.data.database import get_backtest_runs, get_cached_industry_research, get_cached_positioning, get_dashboard_order, get_journal_entries, get_portfolio_holdings, get_portfolio_targets, get_positioning_history, get_simulation_suggestions, get_watchlist, init_db
from src.backtesting import decision_accuracy_history, diagnostic_success_rate, decision_outcome, latest_model_runs, learned_score_adjustments
from src.model_policy import governed_learning_adjustments
from src.data.fmp import FMPProvider
from src.data.fundamentals import FallbackFundamentalsProvider, get_fundamentals
from src.data.market_data import calculate_metrics, fetch_price_history
from src.data.extended_hours import get_extended_hours_quote
from src.data.industry_refresh import industry_refresh_status, schedule_industry_refresh
from src.data.positioning_refresh import finra_backfill_status, positioning_refresh_status, schedule_finra_backfill, schedule_positioning_refresh
from src.data.yfinance_fundamentals import YFinanceFundamentalsProvider
from src.scoring.risk import calculate_risk_score, risk_score_details
from src.scoring.technical import calculate_technical_score
from src.scoring.technology import technology_potential_evidence
from src.scoring.decision import (
    calculate_coverage_aware_entry_score, calculate_exit_review_score,
    entry_label, exit_review_label,
)
from src.scoring.valuation import calculate_valuation_score, valuation_score_breakdown
from src.scoring.industry import industry_entry_score
from src.scoring.positioning import (
    apply_positioning_adjustment, effective_positioning_snapshot,
    positioning_score_adjustments, positioning_scores, short_interest_freshness,
)
from src.scoring.position_action import initiation_diagnostic, position_action
from src.utils.config import FMP_API_KEY
from src.ui import inject_app_styles, page_header, style_figure, zebra_table
from src.shadow_model import meaningful_valuation_available

st.set_page_config(page_title="Company | Personal Equity Radar", page_icon="📈", layout="wide")
init_db()
fundamentals_providers = []
if FMP_API_KEY:
    fundamentals_providers.append(FMPProvider(FMP_API_KEY))
fundamentals_providers.append(YFinanceFundamentalsProvider())
fundamentals_provider = FallbackFundamentalsProvider(fundamentals_providers)
inject_app_styles()
page_header(
    "Single-name research", "Company detail",
    "Move from price action to valuation and thesis context without losing the big picture.",
    "Market data · yfinance",
)
tickers = get_watchlist()
if not tickers:
    st.info("Add a ticker in Watchlist management first.")
    st.stop()

dashboard_order = get_dashboard_order()
tickers = [symbol for symbol in dashboard_order if symbol in tickers] + [
    symbol for symbol in tickers if symbol not in dashboard_order
]
session_requested_ticker = str(st.session_state.pop("company_requested_ticker", "")).upper()
requested_ticker = session_requested_ticker or str(st.query_params.get("ticker", "")).upper()
initial_ticker = requested_ticker if requested_ticker in tickers else tickers[0]
if requested_ticker in tickers and st.session_state.get("company_selector") != requested_ticker:
    st.session_state.company_selector = requested_ticker
elif st.session_state.get("company_selector") not in tickers:
    st.session_state.company_selector = initial_ticker


def sync_company_query() -> None:
    st.query_params["ticker"] = st.session_state.company_selector

ticker_col, history_col = st.columns([1, 1], vertical_alignment="bottom")
with ticker_col:
    ticker = st.selectbox(
        "Company", tickers, key="company_selector",
        on_change=sync_company_query,
    )
with history_col:
    history_label = st.radio("Chart history", ["1 year", "3 years"], horizontal=True)
history_period = "1y" if history_label == "1 year" else "3y"
company_snapshot = get_cached_industry_research(ticker) or {}
company_profile = company_snapshot.get("profile") or {}
company_name = str(company_profile.get("company_name") or ticker)
if company_name != ticker:
    st.caption(company_name)

schedule_industry_refresh([ticker], max_new=1)
schedule_positioning_refresh([ticker], max_new=1)
schedule_finra_backfill([ticker], max_new=1)

@st.fragment(run_every=4)
def render_selected_company_refresh_status() -> None:
    schedule_industry_refresh([ticker], max_new=1)
    status = industry_refresh_status(ticker)
    if status == "Discovering peers":
        st.caption("Discovering and ranking comparable companies automatically…")
    elif status == "Updating":
        st.caption("Industry and analyst research is updating automatically in the background…")
    elif status == "Stale":
        st.caption("Showing the previous industry snapshot while today’s update runs automatically.")
    elif status == "Provider unavailable":
        st.caption("The last provider attempt failed. Cached data is preserved; retry is automatic after cooldown.")
    signature_key = f"company_industry_status_{ticker}"
    previous = st.session_state.get(signature_key)
    st.session_state[signature_key] = status
    if previous is not None and previous != status:
        st.rerun()

render_selected_company_refresh_status()

@st.fragment(run_every=4)
def render_positioning_refresh_status() -> None:
    schedule_positioning_refresh([ticker], max_new=1)
    schedule_finra_backfill([ticker], max_new=1)
    status = positioning_refresh_status(ticker)
    finra_status = finra_backfill_status(ticker)
    if status == "Updating":
        st.caption("Market positioning is updating automatically in the background…")
    elif status == "Stale":
        st.caption("Showing the previous positioning snapshot while today’s update runs.")
    elif status == "Provider unavailable":
        st.caption("Positioning provider unavailable; the last successful snapshot is preserved.")
    if finra_status == "Backfilling":
        st.caption("Official FINRA short-interest history is backfilling automatically…")
    elif finra_status == "Stale":
        st.error("Official short-interest history is stale and excluded from scores while refresh retries automatically.")
    elif finra_status == "Provider unavailable":
        st.caption("FINRA history is temporarily unavailable; retry is automatic after cooldown.")
    key = f"company_positioning_status_{ticker}"
    previous = st.session_state.get(key)
    combined_status = (status, finra_status)
    st.session_state[key] = combined_status
    if previous is not None and previous != combined_status:
        st.rerun()

render_positioning_refresh_status()

if st.button("← Back to Decision dashboard", type="tertiary"):
    st.switch_page("pages/1_Dashboard.py")

try:
    with st.spinner(f"Loading {ticker} market data…"):
        history = fetch_price_history(ticker, period=history_period)
    metric_history = history if history_period == "1y" else fetch_price_history(ticker, period="1y")
    metrics = calculate_metrics(metric_history)
    technical = calculate_technical_score(metrics)
    fundamentals = get_fundamentals(
        ticker,
        fundamentals_provider,
        current_price=metrics["latest_price"],
        force_refresh=False,
    )
    risk = calculate_risk_score(metrics, metric_history)
    risk_details = risk_score_details(metrics, metric_history)
    industry_risk = min(100, risk + int(risk_details["drawdown_penalty"] or 0))
    industry_research = get_cached_industry_research(ticker)
    technology_evidence = technology_potential_evidence(industry_research)
    positioning = get_cached_positioning(ticker)
    positioning_history = get_positioning_history(ticker)
    effective_positioning = effective_positioning_snapshot(positioning, positioning_history)
    scoring_positioning = effective_positioning["snapshot"]
    positioning_breakdown = positioning_scores(scoring_positioning)
    positioning_modifier = positioning_score_adjustments(positioning, positioning_history, technical)
    backtest_runs = latest_model_runs(get_backtest_runs(ticker))
    registered_backtests = sum(
        int(run.get("has_prediction_snapshot") or 0) for run in backtest_runs
    )
    learning_modifier = learned_score_adjustments(backtest_runs)
    learning_policy = governed_learning_adjustments(learning_modifier)
    industry_breakdown = industry_entry_score(technical, industry_risk, industry_research)
    absolute_valuation = calculate_valuation_score(fundamentals)
    extended_quote = get_extended_hours_quote(ticker)

    if extended_quote:
        def extended_value(price_field: str, change_field: str) -> str:
            price = extended_quote.get(price_field)
            change = extended_quote.get(change_field)
            if price is None:
                return "—"
            suffix = "" if change is None else f" · {float(change):+.2f}%"
            return f"${float(price):,.2f}{suffix}"

        st.caption("EXTENDED-HOURS AWARENESS · advisory only · excluded from Entry/Exit scores")
        quote_columns = st.columns(3)
        quote_columns[0].metric("Regular close", f"${float(metrics['latest_price']):,.2f}")
        quote_columns[1].metric(
            "Pre-market", extended_value("premarket_price", "premarket_change_pct"),
            help=str(extended_quote.get("premarket_timestamp") or "No pre-market quote timestamp"),
        )
        quote_columns[2].metric(
            "After-hours", extended_value("afterhours_price", "afterhours_change_pct"),
            help=str(extended_quote.get("afterhours_timestamp") or "No after-hours quote timestamp"),
        )
        state = str(extended_quote.get("market_state") or "closed")
        st.caption(
            f"Market state · {state} · Provider: {extended_quote.get('provider_name')} · "
            f"Fetched: {extended_quote.get('fetched_at')}"
        )

    figure = make_subplots(
        rows=2, cols=1, shared_xaxes=True, vertical_spacing=.04,
        row_heights=[.78, .22], specs=[[{}], [{"secondary_y": True}]],
    )
    chart_dates = pd.DatetimeIndex(pd.to_datetime(history.index))
    if chart_dates.tz is not None:
        chart_dates = chart_dates.tz_localize(None)
    chart_dates = chart_dates.normalize()
    figure.add_scatter(x=chart_dates, y=history["Close"], name="Close", row=1, col=1)
    for window, label in ((50, "50-day MA"), (100, "100-day MA"), (200, "200-day MA")):
        moving_average = history["Close"].rolling(window).mean()
        if moving_average.notna().any():
            figure.add_scatter(
                x=chart_dates,
                y=moving_average,
                name=label,
                line={"dash": "dot"},
                row=1, col=1,
            )
    finra_rows = []
    history_start = chart_dates.min()
    for observation in positioning_history:
        if observation.get("snapshot_type") != "historical_short_interest":
            continue
        reported = observation.get("reporting_date") or observation.get("snapshot_date")
        short_data = observation.get("short", {})
        if not reported or not isinstance(short_data, dict):
            continue
        reported_at = pd.Timestamp(str(reported)).normalize()
        if reported_at < history_start:
            continue
        finra_rows.append({
            "date": reported_at,
            "change": short_data.get("short_change_pct"),
            "days": short_data.get("days_to_cover"),
            "shares": short_data.get("shares_short"),
            "known_at": observation.get("known_at"),
            "known_at_status": observation.get("known_at_status"),
            "age": short_interest_freshness(observation).get("age_days"),
        })
    if finra_rows:
        finra_frame = pd.DataFrame(finra_rows).sort_values("date").drop_duplicates("date", keep="last")
        colors = ["#ff6375" if float(value or 0) > 0 else "#35d0ba" for value in finra_frame["change"]]
        hover = [
            f"FINRA settlement date {row.date:%Y-%m-%d}<br>Short change {float(row.change or 0):+.2f}%"
            f"<br>Shares short {float(row.shares or 0):,.0f}<br>Days to cover {float(row.days or 0):.2f}"
            f"<br>Observed by app: {row.known_at or 'unverified legacy'}"
            f"<br>Current report age: {row.age if row.age is not None else 'unknown'} days"
            for row in finra_frame.itertuples()
        ]
        figure.add_bar(
            x=finra_frame["date"], y=finra_frame["change"], name="FINRA short Δ",
            marker_color=colors, customdata=hover, hovertemplate="%{customdata}<extra></extra>",
            row=2, col=1, secondary_y=False,
        )
        figure.add_scatter(
            x=finra_frame["date"], y=finra_frame["days"], name="Days to cover",
            mode="lines+markers", line={"color": "#f5c26b", "width": 1.5},
            marker={"size": 4}, row=2, col=1, secondary_y=True,
        )
    chart_start = chart_dates.min()
    chart_end = chart_dates.max()
    completed_dates = {str(run["as_of_date"]): run for run in backtest_runs}
    simulation_markers: list[tuple[pd.Timestamp, str, str]] = []
    for cutoff, run in completed_dates.items():
        marker_type = "Suggested simulation" if run.get("simulation_source") == "suggested" else "Manual simulation"
        marker_color = "#c792ea" if marker_type == "Suggested simulation" else "#7aa2f7"
        simulation_markers.append((pd.Timestamp(cutoff), marker_type, marker_color))
    for suggestion in get_simulation_suggestions():
        cutoff = str(suggestion["suggested_date"])
        if cutoff not in completed_dates:
            simulation_markers.append((pd.Timestamp(cutoff), "Suggested · pending", "#f5c26b"))
    visible_marker_types: dict[str, str] = {}
    for marker_date, marker_type, marker_color in simulation_markers:
        if not chart_start <= marker_date <= chart_end:
            continue
        figure.add_vline(
            x=marker_date, line_width=1, line_dash="dot", line_color=marker_color,
            opacity=.72, row="all", col=1,
        )
        visible_marker_types[marker_type] = marker_color
    for marker_type, marker_color in visible_marker_types.items():
        figure.add_scatter(
            x=[None], y=[None], mode="lines", name=marker_type,
            line={"color": marker_color, "width": 1, "dash": "dot"}, row=1, col=1,
        )
    company_heading = f"{ticker} — {company_name}" if company_name != ticker else ticker
    st.markdown(f"**{company_heading} · {history_label.lower()} price history**")
    figure.update_yaxes(title_text="Price", row=1, col=1)
    figure.update_yaxes(title_text="Short Δ %", row=2, col=1, secondary_y=False, zeroline=True)
    figure.update_yaxes(title_text="Days", row=2, col=1, secondary_y=True, showgrid=False)
    style_figure(figure, height=560)
    # Plotly's horizontal legend becomes a tall, narrow stack on phones. A
    # compact semantic legend keeps all series discoverable without consuming
    # a large part of the chart viewport.
    figure.update_layout(
        showlegend=False, hovermode="x unified",
        margin={"l": 12, "r": 12, "t": 12, "b": 12},
    )
    figure.update_xaxes(
        showspikes=True, spikemode="across", spikesnap="cursor",
        spikecolor="#94a3b8", spikethickness=1,
    )
    legend_items = [
        ("line close", "Close"), ("line ma50", "MA 50"),
        ("line ma100", "MA 100"), ("line ma200", "MA 200"),
    ]
    if finra_rows:
        legend_items.extend([("bar finra", "FINRA short Δ"), ("line cover", "Days to cover")])
    marker_labels = {
        "Manual simulation": ("line manual", "Manual sim."),
        "Suggested simulation": ("line suggested", "Suggested sim."),
        "Suggested · pending": ("line pending", "Suggested pending"),
    }
    legend_items.extend(marker_labels[item] for item in visible_marker_types if item in marker_labels)
    st.html(
        "<div class='company-chart-legend' aria-label='Chart legend'>"
        + "".join(
            f"<span class='legend-item'><i class='{kind}'></i>{label}</span>"
            for kind, label in legend_items
        )
        + "</div>"
    )
    st.plotly_chart(figure, width="stretch")
    if finra_rows:
        eligibility = "included in scores" if positioning_modifier["short_scoring_eligible"] else "excluded from scores"
        st.caption(
            "FINRA pressure pulse · exact shared calendar axis · bars use official settlement dates · "
            f"latest report {positioning_modifier.get('short_report_date') or 'unknown'} "
            f"({positioning_modifier.get('short_age_days') if positioning_modifier.get('short_age_days') is not None else 'unknown'} days old; {eligibility})"
        )
    if visible_marker_types:
        st.caption("Simulation markers · blue = manual · purple = completed suggestion · gold = suggested and pending")

    base_entry_score = (
        float(industry_breakdown["score"])
        if industry_research else calculate_coverage_aware_entry_score(
            technical, absolute_valuation, risk,
            valuation_available=meaningful_valuation_available(fundamentals),
        )
    )
    base_exit_score = calculate_exit_review_score(technical, risk)
    entry_score = apply_positioning_adjustment(base_entry_score, float(positioning_modifier["entry_adjustment"]))
    exit_score = apply_positioning_adjustment(base_exit_score, float(positioning_modifier["exit_adjustment"]))
    entry_score = apply_positioning_adjustment(entry_score, float(learning_policy["applied_entry_adjustment"]))
    exit_score = apply_positioning_adjustment(exit_score, float(learning_policy["applied_exit_adjustment"]))
    portfolio_holdings = get_portfolio_holdings()
    selected_holding = next((item for item in portfolio_holdings if item["ticker"] == ticker), None)
    target_map = {str(item["ticker"]): float(item["target_weight_pct"]) for item in get_portfolio_targets()}
    position_values: dict[str, float] = {}
    for holding in portfolio_holdings:
        symbol = str(holding["ticker"])
        try:
            price = float(metrics["latest_price"]) if symbol == ticker else float(fetch_price_history(symbol)["Close"].dropna().iloc[-1])
            position_values[symbol] = float(holding["shares"]) * price
        except Exception:
            continue
    total_position_value = sum(position_values.values())
    current_weight = position_values.get(ticker, 0.0) / total_position_value * 100 if total_position_value else 0.0
    portfolio_decision = (
        position_action(entry_score, exit_score, current_weight, target_map.get(ticker))
        if selected_holding else None
    )
    entry_color = "#38d996" if entry_score >= 60 else "#f0ad4e" if entry_score >= 40 else "#ff6375"
    current_entry_signal = entry_label(entry_score)
    entry_success = diagnostic_success_rate(backtest_runs, current_entry_signal, "entry")
    entry_success_text = (
        f"Historical success {float(entry_success['success_rate']):.0f}% · {entry_success['successes']}/{entry_success['sample_size']}"
        if entry_success["available"] else
        f"Historical success unavailable · {entry_success['sample_size']} comparable (need 3)"
    )
    overall_accuracy_text = (
        "Confirmed decision accuracy unavailable"
        if learning_modifier["decision_accuracy"] is None else
        f"Confirmed decision accuracy {float(learning_modifier['decision_accuracy']):.0f}% · "
        f"{int(learning_modifier['correct_decisions'])}/{int(learning_modifier['sample_size'])}"
        + (f" · {int(learning_modifier['provisional_runs'])} provisional" if learning_modifier.get("provisional_runs") else "")
    )
    entry_figure = go.Figure(go.Indicator(
        mode="number",
        value=entry_score,
        number={"suffix": "/100", "valueformat": ".1f", "font": {"size": 36, "color": entry_color}},
        title={
            "text": (
                f"<b>ENTRY SCORE</b><br><span style='font-size:0.78em;color:#9aa4b2'>{current_entry_signal}</span>"
                f"<br><span style='font-size:0.68em;color:#9aa4b2'>{entry_success_text}</span>"
                f"<br><span style='font-size:0.68em;color:#9aa4b2'>{overall_accuracy_text}</span>"
            ),
            "font": {"size": 15, "color": "#d6deea"},
        },
        domain={"x": [0, 1], "y": [0, 1]},
    ))
    entry_figure.update_layout(
        height=165,
        margin={"l": 0, "r": 0, "t": 36, "b": 0},
        paper_bgcolor="rgba(0,0,0,0)",
    )
    st.plotly_chart(entry_figure, width="stretch", config={"displayModeBar": False})

    st.caption("ENTRY MAP · EACH CARD MATCHES A DETAIL TAB BELOW")
    business_quality = float(industry_breakdown["business_quality"])
    relative_valuation = float(industry_breakdown["relative_valuation"])
    technical_timing = float(industry_breakdown["technical_timing"])
    risk_resilience = float(industry_breakdown["risk_resilience"])
    analyst_sentiment = float(industry_breakdown["analyst_sentiment"])
    fundamentals_points = business_quality * .25 + relative_valuation * .30
    market_points = technical_timing * .20 + risk_resilience * .15
    analyst_points = analyst_sentiment * .10
    positioning_card = (
        f"Market positioning modifier ({float(positioning_modifier['entry_adjustment']):+.1f})",
        ["Reliability-gated · capped at ±5 Entry points",
         f"Evidence reliability · {float(positioning_modifier['reliability']):.0f}/100"],
    )
    if industry_research:
        entry_card_rows = [
            (
                (
                    f"55% · Fundamentals & valuation (+{fundamentals_points:.2f})",
                    [f"25% Business quality · {business_quality:.1f} (+{business_quality * .25:.2f})",
                     f"30% Peer value · {relative_valuation:.1f} (+{relative_valuation * .30:.2f})"],
                ),
                (
                    f"35% · Market metrics (+{market_points:.2f})",
                    [f"20% Technical timing · {technical_timing:.1f} (+{technical_timing * .20:.2f})",
                     f"15% Risk resilience · {risk_resilience:.1f} (+{risk_resilience * .15:.2f})"],
                ),
            ),
            (
                (
                    f"10% · Industry & analysts (+{analyst_points:.2f})",
                    [f"10% Analyst sentiment · {analyst_sentiment:.1f} (+{analyst_points:.2f})",
                     "Industry cohort calibrates quality and valuation above"],
                ),
                positioning_card,
            ),
        ]
    else:
        valuation_available = meaningful_valuation_available(fundamentals)
        technical_weight = .50 if valuation_available else 5 / 7
        risk_weight = .20 if valuation_available else 2 / 7
        valuation_weight = .30 if valuation_available else 0
        entry_card_rows = [
            (
                (
                    f"{technical_weight:.1%} · Technical evidence (+{technical * technical_weight:.2f})",
                    [f"Technical timing · {technical:.1f}/100",
                     "Weights renormalized only across available evidence"],
                ),
                (
                    f"{risk_weight:.1%} · Risk resilience (+{risk * risk_weight:.2f})",
                    [f"Risk resilience · {risk:.1f}/100", "Exit policy remains unchanged"],
                ),
            ),
            (
                (
                    f"{valuation_weight:.1%} · Valuation (+{absolute_valuation * valuation_weight:.2f})",
                    [f"Absolute valuation · {absolute_valuation:.1f}/100",
                     "Unavailable valuation contributes no neutral placeholder"],
                ),
                positioning_card,
            ),
        ]
    for card_row in entry_card_rows:
        card_columns = st.columns(2)
        for column, (title, details) in zip(card_columns, card_row):
            with column:
                with st.container(border=True):
                    st.markdown(f"**{title}**")
                    for detail in details:
                        st.caption(detail)

    with st.container(border=True):
        technology_modifier = float(technology_evidence["entry_modifier"])
        technology_color = (
            "#38d996" if technology_modifier > 0
            else "#ff6375" if technology_modifier < 0 else "#9aa4b2"
        )
        st.markdown("**Technology Potential · active shadow modifier**")
        st.markdown(
            f"<span style='color:{technology_color};font-size:1.15rem;font-weight:700'>"
            f"{float(technology_evidence['score']):.1f}/100 · {technology_modifier:+.1f} shadow Entry points"
            f"</span>", unsafe_allow_html=True,
        )
        st.caption(
            f"Confidence {float(technology_evidence['confidence']):.0%} · "
            f"{technology_evidence['coverage']} coverage · live contribution exactly 0.0"
        )
        st.caption(str(technology_evidence["rationale"]))

    learning_entry_adjustment = float(learning_modifier["entry_adjustment"])
    learning_columns = st.columns(2)
    with learning_columns[0]:
        with st.container(border=True):
            st.markdown("**Archived learning diagnostic · excluded from live score**")
            st.markdown(
                f"<span style='color:#9aa4b2;font-size:1.15rem;font-weight:650'>"
                f"Historical counterfactual {learning_entry_adjustment:+.1f}</span>", unsafe_allow_html=True,
            )
            st.caption("Research context only · contributes exactly 0.0 points to the live Entry score")
    with learning_columns[1]:
        learning_outcome_text = (
            "Decision-aware evidence still developing" if learning_modifier["decision_accuracy"] is None
            else f"Confirmed accuracy · {float(learning_modifier['decision_accuracy']):.0f}% · Weighted monthly {float(learning_modifier['average_composite']):+.2f}%"
        )
        st.markdown(
            f"<div style='background:#d9dde2;color:#111820;border:1px solid #eef1f4;"
            f"border-radius:12px;padding:16px 18px;min-height:118px'>"
            f"<div style='font-weight:750;font-size:1rem;margin-bottom:12px'>"
            f"Learning evidence · {learning_modifier['confidence']}</div>"
            f"<div style='font-size:.88rem;margin-bottom:7px'>Confirmed episodes / saved simulations · "
            f"{int(learning_modifier['sample_size'])}/{int(learning_modifier['total_runs'])}</div>"
            f"<div style='font-size:.88rem'>{learning_outcome_text}</div></div>",
            unsafe_allow_html=True,
        )

    exit_color = "#ff6375" if exit_score >= 70 else "#f0ad4e" if exit_score >= 50 else "#38d996"
    current_exit_signal = exit_review_label(exit_score)
    exit_success = diagnostic_success_rate(backtest_runs, current_exit_signal, "exit")
    exit_success_text = (
        f"Historical success {float(exit_success['success_rate']):.0f}% · {exit_success['successes']}/{exit_success['sample_size']}"
        if exit_success["available"] else
        f"Historical success unavailable · {exit_success['sample_size']} comparable (need 3)"
    )
    exit_figure = go.Figure(go.Indicator(
        mode="number", value=exit_score,
        number={"suffix": "/100", "valueformat": ".1f", "font": {"size": 36, "color": exit_color}},
        title={
            "text": (
                f"<b>EXIT-REVIEW SCORE</b><br><span style='font-size:0.78em;color:#9aa4b2'>{current_exit_signal}</span>"
                f"<br><span style='font-size:0.68em;color:#9aa4b2'>{exit_success_text}</span>"
            ),
            "font": {"size": 15, "color": "#d6deea"},
        },
        domain={"x": [0, 1], "y": [0, 1]},
    ))
    exit_figure.update_layout(
        height=150, margin={"l": 0, "r": 0, "t": 34, "b": 0},
        paper_bgcolor="rgba(0,0,0,0)",
    )
    st.plotly_chart(exit_figure, width="stretch", config={"displayModeBar": False})
    st.caption("EXIT MAP · DETERIORATION INPUTS")
    technical_deterioration = 100 - float(technical)
    risk_deterioration = 100 - float(risk)
    exit_columns = st.columns(2)
    for column, title, details in (
        (exit_columns[0], f"60% · Technical deterioration (+{technical_deterioration * .60:.2f})",
         [f"Deterioration · {technical_deterioration:.1f}/100", f"60% × {technical_deterioration:.1f} = +{technical_deterioration * .60:.2f}"]),
        (exit_columns[1], f"40% · Market-risk deterioration (+{risk_deterioration * .40:.2f})",
         [f"Deterioration · {risk_deterioration:.1f}/100", f"40% × {risk_deterioration:.1f} = +{risk_deterioration * .40:.2f}"]),
    ):
        with column:
            with st.container(border=True):
                st.markdown(f"**{title}**")
                for detail in details:
                    st.caption(detail)
    learning_exit_adjustment = float(learning_modifier["exit_adjustment"])
    learning_entry_color = (
        "#38d996" if learning_entry_adjustment > 0
        else "#ff6375" if learning_entry_adjustment < 0 else "#9aa4b2"
    )
    learning_exit_color = (
        "#ff6375" if learning_exit_adjustment > 0
        else "#38d996" if learning_exit_adjustment < 0 else "#9aa4b2"
    )
    st.markdown(
        f"<div style='color:#9aa4b2;font-size:.88rem'>Base {base_exit_score:.1f} · "
        f"Market positioning {float(positioning_modifier['exit_adjustment']):+.1f} · "
        f"Archived learning counterfactual {learning_exit_adjustment:+.1f} "
        f"(research only; live contribution 0.0)</div>",
        unsafe_allow_html=True,
    )

    st.markdown("### Investor decision")
    if portfolio_decision:
        action = str(portfolio_decision["action"])
        action_color = "#38d996" if action == "Add candidate" else "#ff6375" if action in {"Trim review", "Exit review"} else "#f0ad4e" if action == "Monitor closely" else "#9fd3ff"
        st.markdown(
            f"<div style='border:1px solid #344457;border-radius:12px;padding:14px'>"
            f"<div style='color:#9aa4b2;font-size:.8rem'>OWNED POSITION</div>"
            f"<div style='color:{action_color};font-size:1.55rem;font-weight:750'>{action}</div>"
            f"</div>", unsafe_allow_html=True,
        )
        action_columns = st.columns(4)
        action_columns[0].metric("Add score", f"{float(portfolio_decision['add_score']):.1f}/100")
        action_columns[1].metric("Trim pressure", f"{float(portfolio_decision['trim_score']):.1f}/100")
        action_columns[2].metric("Current weight", f"{float(portfolio_decision['current_weight_pct']):.1f}%")
        action_columns[3].metric(
            "Target weight", "Not set" if portfolio_decision["target_weight_pct"] is None else f"{float(portfolio_decision['target_weight_pct']):.1f}%",
        )
        with st.expander("Position-action rationale"):
            for note in portfolio_decision["notes"]:
                st.write(f"- {note}")
            st.caption("Trim reflects position sizing; Exit review reflects deterioration in the investment case.")
    else:
        initiation = initiation_diagnostic(entry_score, entry_label(entry_score), exit_review_label(exit_score))
        st.info(f"**Not currently owned · {initiation}.** Entry/Exit evidence is interpreted as a possible new position, not an add/trim decision.")

    with st.expander("How these scores were calculated"):
        if industry_research:
            st.markdown("- **Business quality (25%)** — profitability, growth, margins and financial durability relative to comparable companies.")
            st.markdown("- **Peer-relative valuation (30%)** — positive forward P/E and price/sales relative to the direct-peer medians; invalid or negative multiples are ignored.")
            st.markdown("- **Technical timing (20%)** — 20 points for price above each 50/100/200-day moving average and 10 points for each positive 1/3/6/12-month return, capped at 100.")
            st.markdown("- **Risk resilience (15%)** — annualized-volatility resilience only. Drawdown remains visible and contributes to Exit review, not this industry-calibrated Entry block.")
            st.markdown("- **Analyst sentiment (10%)** — recommendations, estimate revisions, coverage and target-price expectations, confidence-adjusted.")
        else:
            st.markdown(f"- **Technical evidence ({technical_weight:.1%})** — the same transparent moving-average and 1/3/6/12-month return score shown in Market metrics.")
            st.markdown(f"- **Absolute valuation ({valuation_weight:.1%})** — available positive P/E and price/sales multiples plus revenue/EPS growth; unavailable valuation receives 0% rather than a neutral placeholder.")
            st.markdown(f"- **Risk resilience ({risk_weight:.1%})** — the base market-risk score after transparent drawdown and annualized-volatility penalties.")
        st.markdown("- **Market positioning modifier** — a small reliability-gated adjustment from FINRA short interest and available positioning evidence.")
        st.markdown("- **Archived learning diagnostic** — a historical counterfactual retained for research; its live Entry/Exit contribution is exactly zero.")
        st.markdown("- **Exit-review score** — 60% Technical deterioration plus 40% full market-risk deterioration (drawdown and volatility), followed by the bounded positioning modifier; it is not an execution instruction.")

    fundamentals_tab, metrics_tab, industry_tab, positioning_tab, learning_tab, journal_tab = st.tabs([
        "Fundamentals & valuation", "Market metrics", "Industry & analysts", "Market positioning", "Archived learning", "Journal context"
    ])
    with fundamentals_tab:
        st.subheader("Fundamentals and valuation")
        if fundamentals:
            inputs = {
                "Trailing P/E": "—" if fundamentals.get("trailing_pe") is None else f"{fundamentals['trailing_pe']:.2f}x",
                "Forward P/E": "—" if fundamentals.get("forward_pe") is None else f"{fundamentals['forward_pe']:.2f}x",
                "Price/sales TTM": "—" if fundamentals.get("price_to_sales_ttm") is None else f"{fundamentals['price_to_sales_ttm']:.2f}x",
                "Revenue growth": "—" if fundamentals.get("revenue_growth") is None else f"{fundamentals['revenue_growth'] * 100:.2f}%",
                "EPS growth": "—" if fundamentals.get("eps_growth") is None else f"{fundamentals['eps_growth'] * 100:.2f}%",
                "Period end": fundamentals.get("period_end") or fundamentals.get("reporting_date"),
                "Historical known at": fundamentals.get("known_at"),
                "Historical status": fundamentals.get("known_at_status") or "unverified legacy",
                "Provider": fundamentals.get("provider_name"),
                "Fetched at": fundamentals.get("fetched_at"),
            }
            st.dataframe(
                zebra_table({"Input": list(inputs), "Value": ["—" if value is None else str(value) for value in inputs.values()]}),
                hide_index=True,
                width="stretch",
            )
            breakdown = valuation_score_breakdown(fundamentals)
            if breakdown:
                st.dataframe(
                    zebra_table({"Component": [key.replace("_", " ").title() for key in breakdown], "Score": list(breakdown.values())}),
                    hide_index=True,
                    width="stretch",
                )
        else:
            st.warning("No fundamentals were available from FMP or Yahoo Finance. Price data is unaffected.")

    with industry_tab:
        st.subheader("Industry calibration and analyst expectations")
        if industry_research:
            profile = industry_research.get("profile", {})
            st.caption(
                f"{profile.get('sector') or 'Unknown sector'} · {profile.get('industry') or 'Unknown industry'} · "
                f"Provider: {industry_research.get('provider_name')} · Fetched: {industry_research.get('fetched_at')} · "
                f"Historical status: {industry_research.get('known_at_status') or 'unverified legacy'}"
            )
            feature_rows = [
                {"Dimension": "Business quality", "Score": industry_breakdown["business_quality"], "Weight": "25%", "Confidence": f"{float(industry_breakdown['quality_confidence']):.0%}"},
                {"Dimension": "Relative valuation", "Score": industry_breakdown["relative_valuation"], "Weight": "30%", "Confidence": f"{float(industry_breakdown['valuation_confidence']):.0%}"},
                {"Dimension": "Technical timing", "Score": industry_breakdown["technical_timing"], "Weight": "20%", "Confidence": "100%"},
                {"Dimension": "Risk resilience", "Score": industry_breakdown["risk_resilience"], "Weight": "15%", "Confidence": "100%"},
                {"Dimension": "Analyst sentiment", "Score": industry_breakdown["analyst_sentiment"], "Weight": "10%", "Confidence": f"{float(industry_breakdown['analyst_confidence']):.0%}"},
            ]
            st.dataframe(zebra_table(feature_rows), hide_index=True, width="stretch")
            peers = industry_research.get("peer_profiles", [])
            if peers:
                st.markdown("**Peer group used**")
                selection = {
                    item.get("ticker"): item for item in industry_research.get("peer_selection", [])
                }
                peer_rows = [{
                    "Ticker": peer.get("ticker"),
                    "Similarity": selection.get(peer.get("ticker"), {}).get("similarity_score"),
                    "Why selected": ", ".join(selection.get(peer.get("ticker"), {}).get("reasons", [])),
                    "Forward P/E": peer.get("forward_pe"),
                    "Price/sales": peer.get("price_to_sales"),
                    "Revenue growth": None if peer.get("revenue_growth") is None else float(peer["revenue_growth"]) * 100,
                    "Operating margin": None if peer.get("operating_margin") is None else float(peer["operating_margin"]) * 100,
                    "FCF margin": None if peer.get("free_cash_flow_margin") is None else float(peer["free_cash_flow_margin"]) * 100,
                } for peer in peers]
                st.dataframe(zebra_table(peer_rows), hide_index=True, width="stretch", column_config={
                    "Similarity": st.column_config.NumberColumn(format="%.1f/100"),
                    "Forward P/E": st.column_config.NumberColumn(format="%.2fx"),
                    "Price/sales": st.column_config.NumberColumn(format="%.2fx"),
                    "Revenue growth": st.column_config.NumberColumn(format="%.2f%%"),
                    "Operating margin": st.column_config.NumberColumn(format="%.2f%%"),
                    "FCF margin": st.column_config.NumberColumn(format="%.2f%%"),
                })
            targets = industry_research.get("price_targets", {})
            recommendations = industry_research.get("recommendations", {})
            analyst_cols = st.columns(3)
            analyst_cols[0].metric("Analyst sentiment", f"{float(industry_breakdown['analyst_sentiment']):.0f}/100")
            analyst_cols[1].metric("Median target upside", "—" if targets.get("median_upside_pct") is None else f"{float(targets['median_upside_pct']):.1f}%")
            coverage = sum(float(recommendations.get(key, 0) or 0) for key in ("strongBuy", "buy", "hold", "sell", "strongSell"))
            analyst_cols[2].metric("Analyst coverage", f"{coverage:.0f}" if coverage else "—")
            with st.expander("Industry Feature evidence"):
                for heading, notes in (
                    ("Business quality", industry_breakdown["quality_notes"]),
                    ("Relative valuation", industry_breakdown["valuation_notes"]),
                    ("Analyst sentiment", industry_breakdown["analyst_notes"]),
                ):
                    st.markdown(f"**{heading}**")
                    for note in notes:
                        st.write(f"- {note}")
        else:
            st.warning("Industry and analyst research is currently unavailable; the feature remains neutral.")

    with positioning_tab:
        st.subheader("Market positioning")
        st.caption("Factored into decisions through small, reliability-gated modifiers")
        if positioning:
            if positioning_modifier["short_scoring_eligible"]:
                st.success(
                    f"Short-interest report {positioning_modifier['short_report_date']} · "
                    f"{positioning_modifier['short_age_days']} days old · eligible for scoring"
                )
            else:
                st.error(
                    f"Short-interest evidence {positioning_modifier['short_evidence_status']} · "
                    "excluded from Entry/Exit scores; missing evidence is not interpreted as low short interest."
                )
            score_columns = st.columns(4)
            score_columns[0].metric("Long positioning", f"{positioning_breakdown['long_positioning']:.1f}/100")
            score_columns[1].metric("Short pressure", f"{positioning_breakdown['short_pressure']:.1f}/100")
            score_columns[2].metric("Squeeze potential", f"{positioning_breakdown['squeeze_potential']:.1f}/100")
            score_columns[3].metric("Confidence", f"{positioning_breakdown['confidence']:.0f}/100")
            st.info(f"Decision implication: {positioning_breakdown['decision_implication']}")
            modifier_columns = st.columns(3)
            modifier_columns[0].metric("Entry adjustment", f"{float(positioning_modifier['entry_adjustment']):+.1f}")
            modifier_columns[1].metric("Exit adjustment", f"{float(positioning_modifier['exit_adjustment']):+.1f}")
            modifier_columns[2].metric("Modifier reliability", f"{float(positioning_modifier['reliability']):.0f}/100")
            if positioning_modifier.get("short_reversal_confirmed"):
                st.success(f"Short reversal lever: {positioning_modifier['short_reversal_lever']}")
            else:
                st.caption(f"Short reversal lever · {positioning_modifier['short_reversal_lever']}")
            st.caption(
                f"Provider: {positioning_modifier.get('short_evidence_source') or positioning.get('provider_name')} · Short-interest report: "
                f"{positioning_modifier.get('short_report_date') or 'unknown'} · Fetched: {positioning.get('fetched_at')} · "
                f"Historical status: {positioning.get('known_at_status') or 'unverified legacy'}"
            )
            short = scoring_positioning.get("short", {}) if isinstance(scoring_positioning, dict) else {}
            options = scoring_positioning.get("options", {}) if isinstance(scoring_positioning, dict) else {}
            ownership = scoring_positioning.get("ownership", {}) if isinstance(scoring_positioning, dict) else {}
            rows = [
                {"Signal": "Short float", "Value": "—" if short.get("short_percent_float") is None else f"{float(short['short_percent_float']):.2%}"},
                {"Signal": "Short-interest change", "Value": "—" if short.get("short_change_pct") is None else f"{float(short['short_change_pct']):+.2f}%"},
                {"Signal": "Days to cover", "Value": "—" if short.get("days_to_cover") is None else f"{float(short['days_to_cover']):.2f}"},
                {"Signal": "Put/call volume", "Value": "—" if options.get("put_call_volume_ratio") is None else f"{float(options['put_call_volume_ratio']):.2f}"},
                {"Signal": "Put/call open interest", "Value": "—" if options.get("put_call_oi_ratio") is None else f"{float(options['put_call_oi_ratio']):.2f}"},
                {"Signal": "Median contract IV", "Value": "—" if options.get("median_contract_iv") is None else f"{float(options['median_contract_iv']):.2%}"},
                {"Signal": "Institutional ownership", "Value": "—" if ownership.get("institutional_percent") is None else f"{float(ownership['institutional_percent']):.2%}"},
                {"Signal": "FMP float validation", "Value": "—" if ownership.get("public_float_shares_fmp") is None else f"{float(ownership['public_float_shares_fmp']):,.0f} shares"},
            ]
            st.dataframe(zebra_table(rows), hide_index=True, width="stretch")
            with st.expander("Positioning evidence and interpretation"):
                for note in positioning_breakdown["notes"]:
                    st.write(f"- {note}")
                st.markdown("**Historical calibration**")
                for note in positioning_modifier["notes"]:
                    st.write(f"- {note}")
            st.info("Options may be bought, written, or used as hedges. Short-sale volume is not used as a substitute for open short interest.")
        else:
            st.info("Positioning coverage is being assembled automatically. Price and company research remain available.")

    with learning_tab:
        st.subheader("Archived learning diagnostic")
        st.caption("Historical research only · live Entry/Exit contribution is exactly 0.0. The legacy outcome composite weights normalized 1M/3M/6M returns at 50%/30%/20%.")
        if backtest_runs:
            st.caption(
                f"Model lineage · {registered_backtests} immutable prediction(s) · "
                f"{len(backtest_runs) - registered_backtests} compatibility-only run(s)"
            )
        learning_columns = st.columns(4)
        learning_columns[0].metric("Confirmed / saved", f"{int(learning_modifier['sample_size'])}/{int(learning_modifier['total_runs'])}")
        learning_columns[1].metric(
            "Confirmed accuracy", "—" if learning_modifier["decision_accuracy"] is None else f"{float(learning_modifier['decision_accuracy']):.0f}%",
        )
        learning_columns[2].metric("Entry evidence", f"{float(learning_modifier['entry_adjustment']):+.1f}")
        learning_columns[3].metric("Exit evidence", f"{float(learning_modifier['exit_adjustment']):+.1f}")
        st.markdown(
            f"<div style='display:flex;gap:1rem;flex-wrap:wrap'>"
            f"<span style='color:{learning_entry_color};font-weight:700'>Entry diagnostic {learning_entry_adjustment:+.1f}</span>"
            f"<span style='color:{learning_exit_color};font-weight:700'>Exit-review diagnostic {learning_exit_adjustment:+.1f}</span>"
            f"</div>", unsafe_allow_html=True,
        )
        if int(learning_modifier["sample_size"]) < 3:
            st.info(f"Diagnostic evidence remains neutral · {learning_modifier['reason']}.")
        else:
            st.info(f"Quarantined · not applied to current scores. {learning_modifier['reason']}.")
        if backtest_runs:
            history_rows = pd.DataFrame([{**run, **decision_outcome(run)} for run in backtest_runs])[[
                "as_of_date", "entry_signal", "entry_score", "outcome_1m", "outcome_3m", "outcome_6m",
                "composite", "verdict", "learning_priority", "should_learn", "learning_reason",
            ]].rename(columns={"as_of_date": "Cutoff date", "composite": "Weighted monthly %",
                               "verdict": "Decision conclusion", "learning_priority": "Learning value",
                               "should_learn": "Used for learning", "learning_reason": "Why"})
            st.dataframe(zebra_table(history_rows), hide_index=True, width="stretch")
        else:
            st.info("No saved simulations exist for this ticker yet.")

    with metrics_tab:
        st.subheader("Calculated metrics")
        percentage_metrics = {"return_1m", "return_3m", "return_6m", "return_12m", "drawdown_from_52w_high"}
        metric_rows = []
        for key, value in metrics.items():
            if value is None:
                formatted_value = "—"
            elif key in percentage_metrics:
                formatted_value = f"{value:.2f}%"
            else:
                formatted_value = f"${value:.2f}"
            metric_rows.append({"Metric": key.replace("_", " ").title(), "Value": formatted_value})
        st.dataframe(zebra_table(metric_rows), hide_index=True, width="stretch")

    with journal_tab:
        st.subheader("Latest journal entries")
        entries = get_journal_entries(ticker=ticker)
        if entries:
            current_price = metrics["latest_price"]
            enriched_entries = []
            for entry in entries:
                enriched = dict(entry)
                target = enriched.get("target_price")
                enriched["target_upside_downside_pct"] = (
                    (float(target) / current_price - 1) * 100 if target and current_price else None
                )
                enriched_entries.append(enriched)
            st.dataframe(
                zebra_table(enriched_entries),
                hide_index=True,
                width="stretch",
                column_config={
                    "target_price": st.column_config.NumberColumn("Target price", format="$%.2f"),
                    "target_upside_downside_pct": st.column_config.NumberColumn("Upside/downside", format="%.2f%%"),
                },
            )
        else:
            st.caption("No journal entries for this ticker yet.")

    st.divider()
    st.subheader("Decision accuracy over time")
    accuracy_history = decision_accuracy_history(backtest_runs)
    st.caption(
        "Cumulative confirmed accuracy after each independent decision episode. "
        "Provisional, noisy and same-episode simulations are excluded."
    )
    if accuracy_history:
        accuracy_frame = pd.DataFrame(accuracy_history)
        marker_colors = ["#38d996" if value else "#ff6375" for value in accuracy_frame["successful"]]
        custom_data = accuracy_frame[[
            "entry_signal", "verdict", "correct_decisions", "episodes", "composite", "decision_utility",
        ]].to_numpy()
        accuracy_figure = go.Figure()
        accuracy_figure.add_trace(go.Scatter(
            x=pd.to_datetime(accuracy_frame["as_of_date"]),
            y=accuracy_frame["accuracy"],
            mode="lines+markers",
            name="Confirmed accuracy",
            line={"color": "#70a5ff", "width": 3},
            marker={"color": marker_colors, "size": 10, "line": {"color": "#dbe7f5", "width": 1}},
            customdata=custom_data,
            hovertemplate=(
                "<b>%{x|%Y-%m-%d}</b><br>Confirmed accuracy %{y:.1f}%"
                "<br>Signal %{customdata[0]}<br>%{customdata[1]}"
                "<br>Record %{customdata[2]}/%{customdata[3]}"
                "<br>Weighted monthly %{customdata[4]:+.2f}%"
                "<br>Decision utility %{customdata[5]:+.2f}<extra></extra>"
            ),
        ))
        accuracy_figure.add_hline(
            y=50, line={"color": "#7f8b99", "width": 1, "dash": "dot"},
            annotation_text="50% reference", annotation_position="bottom right",
        )
        accuracy_figure.update_yaxes(title="Confirmed accuracy", range=[0, 105], ticksuffix="%")
        accuracy_figure.update_xaxes(title=None)
        accuracy_figure.update_layout(
            height=350, margin={"l": 20, "r": 20, "t": 24, "b": 20},
            hovermode="x unified", showlegend=False,
        )
        style_figure(accuracy_figure)
        st.plotly_chart(accuracy_figure, width="stretch", config={"displayModeBar": False})
        latest_accuracy = accuracy_history[-1]
        st.caption(
            f"Latest confirmed record · {latest_accuracy['correct_decisions']}/{latest_accuracy['episodes']} "
            f"correct decisions · {float(latest_accuracy['accuracy']):.1f}%"
        )
    else:
        st.info("No confirmed independent decision episodes are available yet.")
except Exception as exc:
    st.error(f"Could not fetch data for {ticker}: {exc}")
