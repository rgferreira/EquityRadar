"""Company detail page."""

import plotly.graph_objects as go
from plotly.subplots import make_subplots
import pandas as pd
import streamlit as st

from src.data.database import get_backtest_runs, get_cached_industry_research, get_cached_positioning, get_dashboard_order, get_journal_entries, get_portfolio_holdings, get_portfolio_targets, get_positioning_history, get_watchlist, init_db
from src.backtesting import learned_score_adjustments
from src.data.fmp import FMPProvider
from src.data.fundamentals import FallbackFundamentalsProvider, get_fundamentals
from src.data.market_data import calculate_metrics, fetch_price_history
from src.data.industry_refresh import industry_refresh_status, schedule_industry_refresh
from src.data.positioning_refresh import positioning_refresh_status, schedule_positioning_refresh
from src.data.yfinance_fundamentals import YFinanceFundamentalsProvider
from src.scoring.risk import calculate_risk_score, explain_risk_score, risk_score_details
from src.scoring.technical import calculate_technical_score, explain_technical_score
from src.scoring.decision import calculate_exit_review_score, entry_label, exit_review_label
from src.scoring.valuation import calculate_valuation_score, explain_valuation_score, valuation_score_breakdown
from src.scoring.industry import industry_entry_score
from src.scoring.positioning import apply_positioning_adjustment, positioning_score_adjustments, positioning_scores
from src.scoring.position_action import initiation_diagnostic, position_action
from src.utils.config import FMP_API_KEY
from src.ui import inject_app_styles, page_header, style_figure

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

schedule_industry_refresh([ticker], max_new=1)
schedule_positioning_refresh([ticker], max_new=1)

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
    status = positioning_refresh_status(ticker)
    if status == "Updating":
        st.caption("Market positioning is updating automatically in the background…")
    elif status == "Stale":
        st.caption("Showing the previous positioning snapshot while today’s update runs.")
    elif status == "Provider unavailable":
        st.caption("Positioning provider unavailable; the last successful snapshot is preserved.")
    key = f"company_positioning_status_{ticker}"
    previous = st.session_state.get(key)
    st.session_state[key] = status
    if previous is not None and previous != status:
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
    valuation = calculate_valuation_score(fundamentals)
    risk = calculate_risk_score(metrics, metric_history)
    risk_details = risk_score_details(metrics, metric_history)
    industry_risk = min(100, risk + int(risk_details["drawdown_penalty"] or 0))
    industry_research = get_cached_industry_research(ticker)
    positioning = get_cached_positioning(ticker)
    positioning_breakdown = positioning_scores(positioning)
    positioning_history = get_positioning_history(ticker)
    positioning_modifier = positioning_score_adjustments(positioning, positioning_history, technical)
    backtest_runs = get_backtest_runs(ticker)
    learning_modifier = learned_score_adjustments(backtest_runs)
    industry_breakdown = industry_entry_score(technical, industry_risk, industry_research)

    figure = make_subplots(
        rows=2, cols=1, shared_xaxes=True, vertical_spacing=.04,
        row_heights=[.78, .22], specs=[[{}], [{"secondary_y": True}]],
    )
    figure.add_scatter(x=history.index, y=history["Close"], name="Close", row=1, col=1)
    for window, label in ((50, "50-day MA"), (100, "100-day MA"), (200, "200-day MA")):
        moving_average = history["Close"].rolling(window).mean()
        if moving_average.notna().any():
            figure.add_scatter(
                x=history.index,
                y=moving_average,
                name=label,
                line={"dash": "dot"},
                row=1, col=1,
            )
    finra_rows = []
    history_start = history.index.min().tz_localize(None) if getattr(history.index, "tz", None) else history.index.min()
    for observation in positioning_history:
        if observation.get("snapshot_type") != "historical_short_interest":
            continue
        reported = observation.get("reporting_date") or observation.get("snapshot_date")
        short_data = observation.get("short", {})
        if not reported or not isinstance(short_data, dict):
            continue
        reported_at = pd.Timestamp(str(reported))
        if reported_at < history_start:
            continue
        finra_rows.append({
            "date": reported_at,
            "change": short_data.get("short_change_pct"),
            "days": short_data.get("days_to_cover"),
            "shares": short_data.get("shares_short"),
        })
    if finra_rows:
        finra_frame = pd.DataFrame(finra_rows).sort_values("date")
        colors = ["#ff6375" if float(value or 0) > 0 else "#35d0ba" for value in finra_frame["change"]]
        hover = [
            f"FINRA report {row.date:%Y-%m-%d}<br>Short change {float(row.change or 0):+.2f}%"
            f"<br>Shares short {float(row.shares or 0):,.0f}<br>Days to cover {float(row.days or 0):.2f}"
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
    st.markdown(f"**{ticker} · {history_label.lower()} price history**")
    figure.update_yaxes(title_text="Price", row=1, col=1)
    figure.update_yaxes(title_text="Short Δ %", row=2, col=1, secondary_y=False, zeroline=True)
    figure.update_yaxes(title_text="Days", row=2, col=1, secondary_y=True, showgrid=False)
    style_figure(figure, height=560)
    st.plotly_chart(figure, width="stretch")
    if finra_rows:
        st.caption("FINRA pressure pulse · coral = rising short interest · teal = falling · gold = days to cover")

    base_entry_score = float(industry_breakdown["score"])
    base_exit_score = calculate_exit_review_score(technical, risk)
    entry_score = apply_positioning_adjustment(base_entry_score, float(positioning_modifier["entry_adjustment"]))
    exit_score = apply_positioning_adjustment(base_exit_score, float(positioning_modifier["exit_adjustment"]))
    entry_score = apply_positioning_adjustment(entry_score, float(learning_modifier["entry_adjustment"]))
    exit_score = apply_positioning_adjustment(exit_score, float(learning_modifier["exit_adjustment"]))
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
    entry_figure = go.Figure(go.Indicator(
        mode="number",
        value=entry_score,
        number={"suffix": "/100", "valueformat": ".1f", "font": {"size": 36, "color": entry_color}},
        title={
            "text": f"<b>ENTRY SCORE</b><br><span style='font-size:0.78em;color:#9aa4b2'>{entry_label(entry_score)}</span>",
            "font": {"size": 15, "color": "#d6deea"},
        },
        domain={"x": [0, 1], "y": [0, 1]},
    ))
    entry_figure.update_layout(
        height=125,
        margin={"l": 0, "r": 0, "t": 26, "b": 0},
        paper_bgcolor="rgba(0,0,0,0)",
    )
    st.plotly_chart(entry_figure, width="stretch", config={"displayModeBar": False})

    st.caption("ENTRY MAP · EACH CARD MATCHES A DETAIL TAB BELOW")
    entry_card_rows = [
        (
            ("Fundamentals & valuation · 55%", f"Business quality {float(industry_breakdown['business_quality']):.1f} · Peer value {float(industry_breakdown['relative_valuation']):.1f}"),
            ("Market metrics · 35%", f"Technical {float(industry_breakdown['technical_timing']):.1f} · Risk resilience {float(industry_breakdown['risk_resilience']):.1f}"),
        ),
        (
            ("Industry & analysts · 10%", f"{float(industry_breakdown['analyst_sentiment']):.1f}/100"),
            ("Market positioning modifier · capped ±5", f"{float(positioning_modifier['entry_adjustment']):+.1f} points"),
        ),
    ]
    for card_row in entry_card_rows:
        card_columns = st.columns(2)
        for column, (title, detail) in zip(card_columns, card_row):
            with column:
                with st.container(border=True):
                    st.markdown(f"**{title}**")
                    st.caption(detail)

    learning_entry_adjustment = float(learning_modifier["entry_adjustment"])
    learning_entry_color = "#38d996" if learning_entry_adjustment > 0 else "#ff6375" if learning_entry_adjustment < 0 else "#9aa4b2"
    learning_columns = st.columns(2)
    with learning_columns[0]:
        with st.container(border=True):
            st.markdown("**Backtested learning modifier · capped ±5**")
            st.markdown(
                f"<span style='color:{learning_entry_color};font-size:1.35rem;font-weight:700'>"
                f"{learning_entry_adjustment:+.1f} Entry points</span>", unsafe_allow_html=True,
            )
    with learning_columns[1]:
        with st.container(border=True):
            st.markdown("**Learning evidence**")
            st.caption(f"{int(learning_modifier['sample_size'])} completed 3M sample(s) · {learning_modifier['confidence']}")

    exit_color = "#ff6375" if exit_score >= 70 else "#f0ad4e" if exit_score >= 50 else "#38d996"
    exit_figure = go.Figure(go.Indicator(
        mode="number", value=exit_score,
        number={"suffix": "/100", "valueformat": ".1f", "font": {"size": 36, "color": exit_color}},
        title={
            "text": f"<b>EXIT-REVIEW SCORE</b><br><span style='font-size:0.78em;color:#9aa4b2'>{exit_review_label(exit_score)}</span>",
            "font": {"size": 15, "color": "#d6deea"},
        },
        domain={"x": [0, 1], "y": [0, 1]},
    ))
    exit_figure.update_layout(
        height=125, margin={"l": 0, "r": 0, "t": 26, "b": 0},
        paper_bgcolor="rgba(0,0,0,0)",
    )
    st.plotly_chart(exit_figure, width="stretch", config={"displayModeBar": False})
    st.caption("EXIT MAP · DETERIORATION INPUTS")
    exit_columns = st.columns(2)
    for column, title, detail in (
        (exit_columns[0], "Technical deterioration · 60%", f"{100 - float(technical):.1f}/100"),
        (exit_columns[1], "Market-risk deterioration · 40%", f"{100 - float(risk):.1f}/100"),
    ):
        with column:
            with st.container(border=True):
                st.markdown(f"**{title}**")
                st.caption(detail)
    learning_exit_adjustment = float(learning_modifier["exit_adjustment"])
    learning_exit_color = "#ff6375" if learning_exit_adjustment > 0 else "#38d996" if learning_exit_adjustment < 0 else "#9aa4b2"
    st.markdown(
        f"<div style='color:#9aa4b2;font-size:.88rem'>Base {base_exit_score:.1f} · "
        f"Market positioning {float(positioning_modifier['exit_adjustment']):+.1f} · "
        f"Backtested learning <strong style='color:{learning_exit_color}'>{learning_exit_adjustment:+.1f}</strong></div>",
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
        st.write(f"**Entry score:** base {base_entry_score:.1f} from 25% business quality + 30% peer-relative valuation + 20% technical timing + 15% risk resilience + 10% analyst sentiment; market-positioning adjustment {float(positioning_modifier['entry_adjustment']):+.1f}; backtested-learning adjustment {float(learning_modifier['entry_adjustment']):+.1f}.")
        st.write(f"**Technical timing ({technical}/100):** {explain_technical_score(metrics)}")
        st.write(f"**Legacy absolute valuation ({valuation}/100, shown in Fundamentals):** {explain_valuation_score(fundamentals)}")
        st.write(f"**Legacy market risk ({risk}/100, used by Exit Review):** {explain_risk_score(metrics, metric_history)}")
        st.write(f"**Exit-review score:** base technical/risk deterioration {base_exit_score:.1f}; market-positioning adjustment {float(positioning_modifier['exit_adjustment']):+.1f}; backtested-learning adjustment {float(learning_modifier['exit_adjustment']):+.1f}. It is not an execution instruction.")
        st.caption(f"Backtested learning · {learning_modifier['reason']}")

    fundamentals_tab, metrics_tab, industry_tab, positioning_tab, learning_tab, journal_tab = st.tabs([
        "Fundamentals & valuation", "Market metrics", "Industry & analysts", "Market positioning", "Backtested learning", "Journal context"
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
                "Reporting date": fundamentals.get("reporting_date"),
                "Provider": fundamentals.get("provider_name"),
                "Fetched at": fundamentals.get("fetched_at"),
            }
            st.dataframe(
                {"Input": list(inputs), "Value": ["—" if value is None else str(value) for value in inputs.values()]},
                hide_index=True,
                width="stretch",
            )
            breakdown = valuation_score_breakdown(fundamentals)
            if breakdown:
                st.dataframe(
                    {"Component": [key.replace("_", " ").title() for key in breakdown], "Score": list(breakdown.values())},
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
                f"Provider: {industry_research.get('provider_name')} · Fetched: {industry_research.get('fetched_at')}"
            )
            feature_rows = [
                {"Dimension": "Business quality", "Score": industry_breakdown["business_quality"], "Weight": "25%", "Confidence": f"{float(industry_breakdown['quality_confidence']):.0%}"},
                {"Dimension": "Relative valuation", "Score": industry_breakdown["relative_valuation"], "Weight": "30%", "Confidence": f"{float(industry_breakdown['valuation_confidence']):.0%}"},
                {"Dimension": "Technical timing", "Score": industry_breakdown["technical_timing"], "Weight": "20%", "Confidence": "100%"},
                {"Dimension": "Risk resilience", "Score": industry_breakdown["risk_resilience"], "Weight": "15%", "Confidence": "100%"},
                {"Dimension": "Analyst sentiment", "Score": industry_breakdown["analyst_sentiment"], "Weight": "10%", "Confidence": f"{float(industry_breakdown['analyst_confidence']):.0%}"},
            ]
            st.dataframe(feature_rows, hide_index=True, width="stretch")
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
                st.dataframe(peer_rows, hide_index=True, width="stretch", column_config={
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
                f"Provider: {positioning.get('provider_name')} · Short-interest report: "
                f"{positioning.get('reporting_date') or 'unknown'} · Fetched: {positioning.get('fetched_at')}"
            )
            short, options = positioning.get("short", {}), positioning.get("options", {})
            ownership = positioning.get("ownership", {})
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
            st.dataframe(rows, hide_index=True, width="stretch")
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
        st.subheader("Backtested learning")
        st.caption("Ticker-specific evidence from persisted point-in-time simulations. Forward outcomes never enter their own historical score.")
        learning_columns = st.columns(4)
        learning_columns[0].metric("Completed 3M samples", int(learning_modifier["sample_size"]))
        learning_columns[1].metric(
            "3M win rate", "—" if learning_modifier["win_rate"] is None else f"{float(learning_modifier['win_rate']):.0f}%",
        )
        learning_columns[2].metric("Entry adjustment", f"{float(learning_modifier['entry_adjustment']):+.1f}")
        learning_columns[3].metric("Exit adjustment", f"{float(learning_modifier['exit_adjustment']):+.1f}")
        st.markdown(
            f"<div style='display:flex;gap:1rem;flex-wrap:wrap'>"
            f"<span style='color:{learning_entry_color};font-weight:700'>Entry impact {learning_entry_adjustment:+.1f}</span>"
            f"<span style='color:{learning_exit_color};font-weight:700'>Exit-review impact {learning_exit_adjustment:+.1f}</span>"
            f"</div>", unsafe_allow_html=True,
        )
        if int(learning_modifier["sample_size"]) < 3:
            st.info(f"No score influence yet · {learning_modifier['reason']}.")
        else:
            st.success(f"Applied to current scores · {learning_modifier['reason']}.")
        if backtest_runs:
            history_rows = pd.DataFrame(backtest_runs)[[
                "as_of_date", "coverage", "entry_signal", "entry_score", "exit_signal", "exit_score",
                "outcome_1m", "outcome_3m", "outcome_6m", "outcome_12m", "model_version",
            ]].rename(columns={"as_of_date": "Cutoff date"})
            st.dataframe(history_rows, hide_index=True, width="stretch")
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
        st.dataframe(metric_rows, hide_index=True, width="stretch")

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
                enriched_entries,
                hide_index=True,
                width="stretch",
                column_config={
                    "target_price": st.column_config.NumberColumn("Target price", format="$%.2f"),
                    "target_upside_downside_pct": st.column_config.NumberColumn("Upside/downside", format="%.2f%%"),
                },
            )
        else:
            st.caption("No journal entries for this ticker yet.")
except Exception as exc:
    st.error(f"Could not fetch data for {ticker}: {exc}")
