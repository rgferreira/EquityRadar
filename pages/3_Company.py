"""Company detail page."""

import plotly.graph_objects as go
import streamlit as st

from src.data.database import get_cached_industry_research, get_journal_entries, get_watchlist, init_db
from src.data.fmp import FMPProvider
from src.data.fundamentals import FallbackFundamentalsProvider, get_fundamentals
from src.data.market_data import calculate_metrics, fetch_price_history
from src.data.industry_refresh import industry_refresh_status, schedule_industry_refresh
from src.data.yfinance_fundamentals import YFinanceFundamentalsProvider
from src.scoring.risk import calculate_risk_score, explain_risk_score, risk_score_details
from src.scoring.technical import calculate_technical_score, explain_technical_score
from src.scoring.decision import calculate_exit_review_score, entry_label, exit_review_label
from src.scoring.valuation import calculate_valuation_score, explain_valuation_score, valuation_score_breakdown
from src.scoring.industry import industry_entry_score
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

ticker_col, history_col = st.columns([1, 1], vertical_alignment="bottom")
with ticker_col:
    ticker = st.selectbox("Company", tickers)
with history_col:
    history_label = st.radio("Chart history", ["1 year", "3 years"], horizontal=True)
history_period = "1y" if history_label == "1 year" else "3y"

schedule_industry_refresh([ticker], max_new=1)

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
    industry_breakdown = industry_entry_score(technical, industry_risk, industry_research)

    figure = go.Figure()
    figure.add_scatter(x=history.index, y=history["Close"], name="Close")
    for window, label in ((50, "50-day MA"), (100, "100-day MA"), (200, "200-day MA")):
        moving_average = history["Close"].rolling(window).mean()
        if moving_average.notna().any():
            figure.add_scatter(
                x=history.index,
                y=moving_average,
                name=label,
                line={"dash": "dot"},
            )
    st.markdown(f"**{ticker} · {history_label.lower()} price history**")
    figure.update_layout(yaxis_title="Price")
    style_figure(figure, height=470)
    st.plotly_chart(figure, width="stretch")

    entry_score = float(industry_breakdown["score"])
    exit_score = calculate_exit_review_score(technical, risk)
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

    st.caption("ENTRY ATTRACTIVENESS · EXACT WEIGHTED INPUTS")
    component_cells = [
        "<b>Business quality · 25%</b><br>" + f"{float(industry_breakdown['business_quality']):.1f}/100",
        "<b>Peer-relative value · 30%</b><br>" + f"{float(industry_breakdown['relative_valuation']):.1f}/100",
        "<b>Technical timing · 20%</b><br>" + f"{float(industry_breakdown['technical_timing']):.1f}/100",
        "<b>Risk resilience · 15%</b><br>" + f"{float(industry_breakdown['risk_resilience']):.1f}/100",
        "<b>Analyst sentiment · 10%</b><br>" + f"{float(industry_breakdown['analyst_sentiment']):.1f}/100",
        "",
    ]
    component_figure = go.Figure(go.Table(
        columnwidth=[1, 1],
        cells={
            "values": [component_cells[0::2], component_cells[1::2]],
            "align": "left",
            "height": 60,
            "fill_color": "#0e1117",
            "line_color": "#283142",
            "font": {"color": "#e4e9f0", "size": 13},
        },
    ))
    component_figure.update_layout(
        height=190,
        margin={"l": 0, "r": 0, "t": 0, "b": 0},
        paper_bgcolor="rgba(0,0,0,0)",
    )
    st.plotly_chart(component_figure, width="stretch", config={"displayModeBar": False})

    st.caption("EXIT MONITORING · SEPARATE DETERIORATION SIGNAL")
    exit_column, exit_context = st.columns([1, 2], vertical_alignment="center")
    exit_column.metric("Exit-review score", f"{exit_score:.1f}/100")
    exit_column.caption(exit_review_label(exit_score))
    exit_context.caption("Uses technical deterioration and the legacy market-risk score. It is not an input to the entry score.")

    with st.expander("How these scores were calculated"):
        st.write("**Entry score:** 25% business quality + 30% peer-relative valuation + 20% technical timing + 15% risk resilience + 10% analyst sentiment.")
        st.write(f"**Technical timing ({technical}/100):** {explain_technical_score(metrics)}")
        st.write(f"**Legacy absolute valuation ({valuation}/100, shown in Fundamentals):** {explain_valuation_score(fundamentals)}")
        st.write(f"**Legacy market risk ({risk}/100, used by Exit Review):** {explain_risk_score(metrics, metric_history)}")
        st.write("**Exit-review score:** a separate technical/risk deterioration signal, not an entry-score component or execution instruction.")

    fundamentals_tab, industry_tab, metrics_tab, journal_tab = st.tabs([
        "Fundamentals & valuation", "Industry & analysts", "Market metrics", "Journal context"
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
