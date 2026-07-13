"""Decision dashboard."""

import json
import pandas as pd
import streamlit as st
from datetime import date, datetime, timedelta

from src.data.database import (
    get_cached_industry_research,
    get_cached_positioning,
    save_dashboard_order,
    get_portfolio_holdings,
    get_portfolio_targets,
    get_positioning_history,
    get_backtest_runs,
    get_active_backtest,
    save_active_backtest,
    get_watchlist,
    init_db,
)
from src.data.market_data import calculate_metrics, clear_market_data_cache, fetch_price_history, get_price_history_fetched_at
from src.data.fmp import FMPProvider
from src.data.fundamentals import FallbackFundamentalsProvider, get_fundamentals
from src.data.yfinance_fundamentals import YFinanceFundamentalsProvider
from src.data.industry_refresh import industry_refresh_status, schedule_industry_refresh
from src.data.positioning_refresh import finra_backfill_status, positioning_refresh_status, schedule_finra_backfill, schedule_positioning_refresh
from src.scoring.risk import calculate_risk_score, explain_risk_score, risk_score_details
from src.scoring.technical import calculate_technical_score, explain_technical_score
from src.scoring.decision import calculate_entry_score, calculate_exit_review_score, entry_label, exit_review_label
from src.scoring.valuation import calculate_valuation_score, explain_valuation_score
from src.scoring.industry import industry_entry_score
from src.scoring.positioning import apply_positioning_adjustment, positioning_score_adjustments
from src.scoring.position_action import initiation_diagnostic, position_action
from src.utils.config import FMP_API_KEY
from src.ui import inject_app_styles, page_header
from src.backtesting import decision_outcome, learned_score_adjustments, lesson_summary
from src.data.backtest_refresh import (
    backtest_status, outcome_refresh_in_flight, schedule_backtest, schedule_outcome_refresh,
)

st.set_page_config(page_title="Decision dashboard | Personal Equity Radar", page_icon="📈", layout="wide")
init_db()
fundamentals_providers = []
if FMP_API_KEY:
    fundamentals_providers.append(FMPProvider(FMP_API_KEY))
fundamentals_providers.append(YFinanceFundamentalsProvider())
fundamentals_provider = FallbackFundamentalsProvider(fundamentals_providers)
inject_app_styles()
page_header(
    "Market command center", "Decision dashboard",
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


def render_dashboard_table(frame: pd.DataFrame, owned_tickers: set[str], key_suffix: str = "all") -> int | None:
    """Render a compact table and return a selected row for same-tab drill-down."""
    longest_diagnostic = max((len(str(value)) for value in frame["Diagnostic"]), default=14)
    diagnostic_width = int(min(205, max(135, longest_diagnostic * 6.2)))
    config: dict[str, object] = {
        "Ticker": st.column_config.TextColumn(
            "Ticker", width=65, help="Select a row to open this company in the same tab.",
        ),
        "Diagnostic": st.column_config.TextColumn("Diagnostic", width=diagnostic_width),
        "Price": st.column_config.NumberColumn("Price", format="$%.2f", width="small"),
        "Entry score": st.column_config.NumberColumn("Entry score", format="%.1f", width="small"),
        "Exit score": st.column_config.NumberColumn("Exit score", format="%.1f", width="small"),
    }
    for column in ("1M %", "3M %", "6M %", "12M %", "Drawdown %"):
        config[column] = st.column_config.NumberColumn(column, format="%.2f%%")
    for column in ("Technical", "Valuation", "Risk", "Positioning entry adj", "Positioning exit adj", "Positioning reliability"):
        config[column] = st.column_config.NumberColumn(column, format="%.1f")
    def highlight_owned(row: pd.Series) -> list[str]:
        ticker = str(row["Ticker"])
        style = "background-color: #14283a;" if ticker in owned_tickers else ""
        return [style] * len(row)

    styled = frame.style.apply(highlight_owned, axis=1)
    generation = int(st.session_state.get("decision_table_generation", 0))
    event = st.dataframe(
        styled, hide_index=True, width="stretch", height=36 + 35 * len(frame), column_config=config,
        on_select="rerun", selection_mode="single-row", key=f"decision_table_{key_suffix}_{generation}",
    )
    selected_rows = event.selection.rows if hasattr(event, "selection") else []
    return int(selected_rows[0]) if selected_rows else None


def non_wrapping_signal_labels(frame: pd.DataFrame) -> pd.DataFrame:
    """Preserve signal semantics; Plotly controls wrapping and density visually."""
    compact = frame.copy()
    return compact.rename(columns={
        "Exit-review score": "Exit score",
        "Price data fetched at": "Freshness",
    })

persisted_backtest_date = get_active_backtest()
schedule_outcome_refresh()
default_backtest_date = (
    pd.Timestamp(persisted_backtest_date).date() if persisted_backtest_date
    else date.today() - timedelta(days=365)
)
with st.container(border=True):
    st.markdown("#### ⏳ Time Machine")
    mode_col, date_col = st.columns([1, 1])
    with mode_col:
        time_mode = st.radio(
            "Decision date", ["Present date", "Past date"], horizontal=True,
            index=1 if persisted_backtest_date else 0,
        )
    with date_col:
        as_of_date = st.date_input(
            "Historical cutoff", value=default_backtest_date,
            max_value=date.today() - timedelta(days=1), disabled=time_mode == "Present date",
        )
    if time_mode == "Past date":
        st.warning(f"Historical simulation · only evidence available by {as_of_date:%Y-%m-%d} is eligible.")
    else:
        st.caption("Live decision mode · select Past date to reconstruct an earlier dashboard.")

historical_mode = time_mode == "Past date"
selected_backtest_date = f"{as_of_date:%Y-%m-%d}" if historical_mode else None
if selected_backtest_date != persisted_backtest_date:
    save_active_backtest(selected_backtest_date)

with st.expander("Saved simulations & learning history"):
    saved_runs = get_backtest_runs()
    if not saved_runs:
        st.info("No persisted simulations yet.")
    else:
        archive_tab, learning_tab = st.tabs(["Simulation archive", "Learning by ticker"])
        with archive_tab:
            archive = pd.DataFrame(saved_runs)
            archive_summary = (
                archive.groupby("as_of_date", as_index=False)
                .agg(
                    Tickers=("ticker", "nunique"),
                    Completed_3M=("outcome_3m", "count"),
                    Average_entry=("entry_score", "mean"),
                    Saved_at=("created_at", "max"),
                )
                .sort_values("as_of_date", ascending=False)
                .rename(columns={"as_of_date": "Cutoff date", "Completed_3M": "3M outcomes",
                                 "Average_entry": "Average entry", "Saved_at": "Last saved"})
            )
            st.dataframe(archive_summary, hide_index=True, width="stretch")
            if outcome_refresh_in_flight():
                st.caption("Refreshing matured forward outcomes automatically…")
        with learning_tab:
            learned_ticker = st.selectbox(
                "Ticker learning history", sorted({str(run["ticker"]) for run in saved_runs}),
                key="learning_history_ticker",
            )
            ticker_runs = [run for run in saved_runs if run["ticker"] == learned_ticker]
            learned = learned_score_adjustments(ticker_runs)
            metric_cols = st.columns(4)
            metric_cols[0].metric("Learned / saved", f"{learned['sample_size']}/{learned['total_runs']}")
            metric_cols[1].metric("Decision accuracy", "—" if learned["decision_accuracy"] is None else f"{learned['decision_accuracy']:.0f}%")
            metric_cols[2].metric("Entry modifier", f"{learned['entry_adjustment']:+.1f}")
            metric_cols[3].metric("Exit modifier", f"{learned['exit_adjustment']:+.1f}")
            st.caption(str(learned["reason"]))
            learning_history = pd.DataFrame([
                {**run, **decision_outcome(run)} for run in ticker_runs
            ])[[
                "as_of_date", "entry_signal", "entry_score", "outcome_1m", "outcome_3m", "outcome_6m",
                "composite", "verdict", "learning_priority", "should_learn", "learning_reason",
            ]].rename(columns={"as_of_date": "Cutoff date", "composite": "Weighted monthly %",
                               "verdict": "Decision conclusion", "learning_priority": "Learning value",
                               "should_learn": "Used for learning", "learning_reason": "Why"})
            st.dataframe(learning_history, hide_index=True, width="stretch")

refresh_col, status_col = st.columns([1, 4], vertical_alignment="center")
with refresh_col:
    refresh = st.button(
        "Run historical simulation" if historical_mode else "Refresh market data",
        type="primary", width="stretch",
    )
with status_col:
    st.caption(
        "The simulation retrieves sufficient history automatically and persists reproducible outcomes."
        if historical_mode else
        "Prices refresh automatically on first load. Use refresh to request fresh provider data."
    )
tickers = get_watchlist()
if not tickers:
    st.info("Add one or more tickers from Watchlist management to begin.")
    st.stop()

initial_refresh = not st.session_state.get("dashboard_initial_refresh_done", False)
simulation_key = f"{as_of_date:%Y-%m-%d}" if historical_mode else None
simulation_changed = historical_mode and st.session_state.get("backtest_active_date") != simulation_key
current_job = backtest_status(simulation_key) if historical_mode else None
job_missing = historical_mode and int(current_job["total"]) == 0
if historical_mode and (refresh or simulation_changed or job_missing):
    schedule_backtest(simulation_key, tickers)
    st.session_state.backtest_active_date = simulation_key
    st.session_state.dashboard_rows_mode = "historical"
elif not historical_mode and (refresh or initial_refresh or st.session_state.get("dashboard_rows_mode") == "historical"):
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
            positioning_modifier = positioning_score_adjustments(
                get_cached_positioning(ticker), get_positioning_history(ticker), technical,
            )
            base_exit = calculate_exit_review_score(technical, risk)
            calibrated_entry = apply_positioning_adjustment(
                calibrated_entry, float(positioning_modifier["entry_adjustment"]),
            )
            calibrated_exit = apply_positioning_adjustment(
                base_exit, float(positioning_modifier["exit_adjustment"]),
            )
            learned = learned_score_adjustments(get_backtest_runs(ticker))
            calibrated_entry = apply_positioning_adjustment(calibrated_entry, float(learned["entry_adjustment"]))
            calibrated_exit = apply_positioning_adjustment(calibrated_exit, float(learned["exit_adjustment"]))
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
                "Positioning entry adj": positioning_modifier["entry_adjustment"],
                "Entry signal": entry_label(calibrated_entry),
                "Diagnostic": f"{entry_label(calibrated_entry)} / {exit_review_label(calibrated_exit)}",
                "Industry calibrated": "Yes" if industry_research else "Pending",
                "Exit-review score": calibrated_exit,
                "Positioning exit adj": positioning_modifier["exit_adjustment"],
                "Positioning reliability": positioning_modifier["reliability"],
                "Learning entry adj": learned["entry_adjustment"],
                "Learning exit adj": learned["exit_adjustment"],
                "Learning rationale": learned["reason"],
                "Short reversal lever": positioning_modifier.get("short_reversal_lever", "Unavailable"),
                "Exit signal": exit_review_label(calibrated_exit),
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
    st.session_state.dashboard_rows_mode = "present"

if historical_mode:
    runs = [run for run in get_backtest_runs() if run["as_of_date"] == simulation_key]
    rows, errors = [], []
    for run in runs:
        inputs = json.loads(str(run["inputs_json"]))
        metrics = inputs["metrics"]
        historical_positioning = inputs.get("positioning_modifier") or {}
        rows.append({
            "Ticker": run["ticker"], "Cutoff date": run["as_of_date"], "Price": metrics["latest_price"],
            "1M %": metrics["return_1m"], "3M %": metrics["return_3m"], "6M %": metrics["return_6m"],
            "12M %": metrics["return_12m"], "52W High": metrics["high_52w"], "52W Low": metrics["low_52w"],
            "Drawdown %": metrics["drawdown_from_52w_high"], "50D MA": metrics["ma_50"],
            "100D MA": metrics["ma_100"], "200D MA": metrics["ma_200"],
            "Technical": run["technical_score"], "Valuation": run["valuation_score"], "Risk": run["risk_score"],
            "Entry score": run["entry_score"], "Entry signal": run["entry_signal"],
            "Exit-review score": run["exit_score"], "Exit signal": run["exit_signal"],
            "Diagnostic": f"{run['entry_signal']} / {run['exit_signal']}", "Industry calibrated": run["coverage"],
            "Positioning entry adj": historical_positioning.get("entry_adjustment", 0.0),
            "Positioning exit adj": historical_positioning.get("exit_adjustment", 0.0),
            "Positioning reliability": historical_positioning.get("reliability", 0.0),
            "Short reversal lever": historical_positioning.get("short_reversal_lever", "Not available point-in-time"),
            "Technical rationale": explain_technical_score(metrics),
            "Risk rationale": "Reconstructed from price history available at the cutoff.",
            "Valuation rationale": "Timestamp eligibility enforced at the cutoff.",
            "Industry rationale": (
                f"Point-in-time FINRA evidence · {int(inputs.get('finra_observations_used', 0))} observations used."
                if inputs.get("finra_observations_used") else
                "Excluded unless timestamped evidence existed by the cutoff."
            ),
            "Price data fetched at": run["created_at"], "Outcome 1M %": run["outcome_1m"],
            "Outcome 3M %": run["outcome_3m"], "Outcome 6M %": run["outcome_6m"],
            "Outcome 12M %": run["outcome_12m"],
        })
    status = backtest_status(simulation_key)
    failed = [item for item in status["items"] if item["status"] == "failed"]
    errors = [f"{item['ticker']}: {item['error']}" for item in failed]
    st.session_state.dashboard_rows = rows
    st.session_state.dashboard_errors = errors

    @st.fragment(run_every=2)
    def render_backtest_progress() -> None:
        current = backtest_status(simulation_key)
        total = max(int(current["total"]), len(tickers))
        completed = int(current["completed"])
        if current["busy"]:
            st.status(
                f"Calculating {simulation_key} · {completed}/{total} completed · "
                f"{current['running']} running · {current['queued']} queued",
                state="running", expanded=True,
            )
            st.progress(completed / total, text="You may navigate elsewhere; this job continues in the background.")
        elif completed == total:
            st.success(f"Simulation complete · cutoff {simulation_key} · {completed}/{total} tickers persisted")
        elif completed + int(current["failed"]) == total:
            st.warning(
                f"Simulation finished with exclusions · cutoff {simulation_key} · "
                f"{completed}/{total} persisted · {current['failed']} unavailable"
            )
        else:
            st.warning(f"Simulation paused with {completed}/{total} completed and {current['failed']} failed. Run again to retry failures.")
        signature = (current["completed"], current["running"], current["queued"], current["failed"])
        previous = st.session_state.get(f"backtest_status_{simulation_key}")
        st.session_state[f"backtest_status_{simulation_key}"] = signature
        if previous is not None and previous != signature:
            st.rerun()

    render_backtest_progress()

rows = st.session_state.get("dashboard_rows", [])
errors = st.session_state.get("dashboard_errors", [])
if rows:
    portfolio_holdings = get_portfolio_holdings()
    portfolio_tickers = [str(item["ticker"]) for item in portfolio_holdings]
    refresh_priority = [*portfolio_tickers, *(ticker for ticker in tickers if ticker not in portfolio_tickers)]
    if not historical_mode:
        schedule_industry_refresh(refresh_priority, max_new=2)
        schedule_positioning_refresh(refresh_priority, max_new=2)
        schedule_finra_backfill(refresh_priority, max_new=2)
    for row in rows if not historical_mode else []:
        research = get_cached_industry_research(str(row["Ticker"]))
        status = industry_refresh_status(str(row["Ticker"]))
        row["Industry calibrated"] = status
        if research and research.get("applicable") is not False:
            drawdown = float(row.get("Drawdown %") or 0)
            drawdown_penalty = min(40, int(abs(min(drawdown, 0))))
            calibrated = industry_entry_score(
                float(row["Technical"]), min(100, float(row["Risk"]) + drawdown_penalty), research
            )
            modifier = positioning_score_adjustments(
                get_cached_positioning(str(row["Ticker"])),
                get_positioning_history(str(row["Ticker"])), float(row["Technical"]),
            )
            row["Positioning entry adj"] = modifier["entry_adjustment"]
            row["Positioning exit adj"] = modifier["exit_adjustment"]
            row["Positioning reliability"] = modifier["reliability"]
            row["Short reversal lever"] = modifier.get("short_reversal_lever", "Unavailable")
            row["Entry score"] = apply_positioning_adjustment(float(calibrated["score"]), float(modifier["entry_adjustment"]))
            base_exit = calculate_exit_review_score(float(row["Technical"]), float(row["Risk"]))
            row["Exit-review score"] = apply_positioning_adjustment(base_exit, float(modifier["exit_adjustment"]))
            learned = learned_score_adjustments(get_backtest_runs(str(row["Ticker"])))
            row["Learning entry adj"] = learned["entry_adjustment"]
            row["Learning exit adj"] = learned["exit_adjustment"]
            row["Learning rationale"] = learned["reason"]
            row["Entry score"] = apply_positioning_adjustment(float(row["Entry score"]), float(learned["entry_adjustment"]))
            row["Exit-review score"] = apply_positioning_adjustment(float(row["Exit-review score"]), float(learned["exit_adjustment"]))
            row["Entry signal"] = entry_label(float(row["Entry score"]))
            row["Exit signal"] = exit_review_label(float(row["Exit-review score"]))
            row["Diagnostic"] = f"{row['Entry signal']} / {row['Exit signal']}"
            row["Industry rationale"] = "; ".join(
                [*calibrated["quality_notes"], *calibrated["valuation_notes"], *calibrated["analyst_notes"]]
            )
    frame = pd.DataFrame(rows)
    if not historical_mode:
        shares_map = {str(item["ticker"]): float(item["shares"]) for item in portfolio_holdings}
        target_map = {str(item["ticker"]): float(item["target_weight_pct"]) for item in get_portfolio_targets()}
        position_values = {
            str(row["Ticker"]): shares_map[str(row["Ticker"])] * float(row["Price"])
            for row in rows if str(row["Ticker"]) in shares_map and row.get("Price") is not None
        }
        total_position_value = sum(position_values.values())
        for row in rows:
            symbol = str(row["Ticker"])
            row["Company diagnostic"] = row["Diagnostic"]
            if symbol in shares_map:
                weight = position_values.get(symbol, 0.0) / total_position_value * 100 if total_position_value else 0.0
                action = position_action(
                    float(row["Entry score"]), float(row["Exit-review score"]), weight, target_map.get(symbol),
                )
                row["Ownership"] = "Owned"
                row["Position action"] = action["action"]
                row["Add score"] = action["add_score"]
                row["Trim score"] = action["trim_score"]
                row["Position rationale"] = "; ".join(action["notes"])
                row["Diagnostic"] = f"Position · {action['action']}"
            else:
                row["Ownership"] = "Watchlist"
                row["Position action"] = "—"
                row["Add score"] = None
                row["Trim score"] = None
                row["Position rationale"] = "Not owned; interpreted as a possible new position."
                row["Diagnostic"] = initiation_diagnostic(
                    float(row["Entry score"]), str(row["Entry signal"]), str(row["Exit signal"]),
                )
        frame = pd.DataFrame(rows)
    above_50 = int((frame["Price"] > frame["50D MA"]).sum())
    above_200 = int((frame["Price"] > frame["200D MA"]).sum())
    avg_entry = frame["Entry score"].mean()
    avg_risk = frame["Risk"].mean()

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

        st.session_state.dashboard_display_order = frame["Ticker"].tolist()
        save_dashboard_order(st.session_state.dashboard_display_order)

        optional_columns = [
            "1M %", "3M %", "6M %", "12M %", "Drawdown %",
            "Technical", "Valuation", "Risk",
            "Positioning entry adj", "Positioning exit adj", "Positioning reliability",
            "Ownership", "Add score", "Trim score", "Company diagnostic",
        ]
        selected_metrics = st.multiselect(
            "Additional table columns",
            [column for column in optional_columns if column in frame.columns],
            default=[],
            help="Keep this empty for the compact phone-friendly decision view.",
        )
    identity_columns = ["Ticker", *(["Cutoff date"] if historical_mode else []), "Diagnostic"]
    display_frame = frame[[
        *identity_columns, "Price", "Entry score", "Exit-review score", "Industry calibrated", *selected_metrics,
    ]].copy()
    display_frame = non_wrapping_signal_labels(display_frame)
    selected_ticker_from_table = None
    if not historical_mode and portfolio_tickers:
        owned_frame = display_frame[display_frame["Ticker"].isin(portfolio_tickers)].copy()
        watchlist_frame = display_frame[~display_frame["Ticker"].isin(portfolio_tickers)].copy()
        if not owned_frame.empty:
            st.markdown("#### Portfolio actions")
            st.caption("Owned positions · sizing-aware Add / Hold / Monitor / Trim / Exit decisions")
            owned_selection = render_dashboard_table(owned_frame, set(portfolio_tickers), "portfolio")
            if owned_selection is not None:
                selected_ticker_from_table = str(owned_frame.iloc[owned_selection]["Ticker"])
        if not watchlist_frame.empty:
            st.markdown("#### Watchlist opportunities")
            st.caption("Unowned securities · potential position-initiation decisions")
            watchlist_selection = render_dashboard_table(watchlist_frame, set(), "watchlist")
            if watchlist_selection is not None:
                selected_ticker_from_table = str(watchlist_frame.iloc[watchlist_selection]["Ticker"])
    else:
        selected_row = render_dashboard_table(display_frame, set(portfolio_tickers), "historical")
        if selected_row is not None:
            selected_ticker_from_table = str(display_frame.iloc[selected_row]["Ticker"])
    if selected_ticker_from_table:
        st.session_state.company_requested_ticker = selected_ticker_from_table
        st.session_state.decision_table_generation = int(st.session_state.get("decision_table_generation", 0)) + 1
        st.switch_page("pages/3_Company.py")
    st.caption("MARKET SNAPSHOT")
    summary_frame = pd.DataFrame({
        "Breadth": [
            f"Above 50-day MA · {above_50}/{len(frame)} ({above_50 / len(frame):.0%})",
            f"Above 200-day MA · {above_200}/{len(frame)} ({above_200 / len(frame):.0%})",
        ],
        "Decision overview": [
            f"Companies tracked · {len(frame)}",
            f"Average entry / risk · {avg_entry:.0f} / {avg_risk:.0f}",
        ],
    })
    st.dataframe(
        summary_frame, hide_index=True, width="stretch", height=106,
        column_config={
            "Breadth": st.column_config.TextColumn(width="medium"),
            "Decision overview": st.column_config.TextColumn(width="medium"),
        },
    )
    refreshed_at = st.session_state.get("last_refreshed_at")
    if refreshed_at:
        st.caption(f"Last refreshed: {refreshed_at}. Refresh again to retrieve new provider data.")

    st.caption(f"Market regime · {above_50}/{len(frame)} above 50D MA · {above_200}/{len(frame)} above 200D MA")

    if historical_mode:
        st.subheader("Backtested learning")
        st.caption(f"Cutoff date · {simulation_key} · Outcomes are judged against the old decision, never used to calculate it. Composite = 50% 1M + 30% 3M + 20% 6M after monthly normalization.")
        analyses = {str(run["ticker"]): decision_outcome(run) for run in get_backtest_runs()
                    if run["as_of_date"] == simulation_key}
        outcome_view = frame[["Ticker", "Cutoff date", "Entry signal", "Entry score", "Outcome 1M %", "Outcome 3M %", "Outcome 6M %"]].copy()
        for horizon, sessions in (("1M", 21), ("3M", 63), ("6M", 126)):
            outcome_view[horizon] = outcome_view[f"Outcome {horizon} %"].map(
                lambda value, required=sessions: f"Pending · {required} sessions" if pd.isna(value) else f"{float(value):+.2f}%"
            )
        outcome_view["Weighted monthly"] = outcome_view["Ticker"].map(
            lambda ticker: "—" if analyses.get(str(ticker), {}).get("composite") is None else f"{float(analyses[str(ticker)]['composite']):+.2f}%"
        )
        outcome_view["Decision conclusion"] = outcome_view["Ticker"].map(lambda ticker: analyses.get(str(ticker), {}).get("verdict", "Pending"))
        outcome_view["Learning value"] = outcome_view["Ticker"].map(lambda ticker: analyses.get(str(ticker), {}).get("learning_priority", 0))
        outcome_view["Learn?"] = outcome_view["Ticker"].map(lambda ticker: "Yes" if analyses.get(str(ticker), {}).get("should_learn") else "No")
        outcome_view = outcome_view.drop(columns=["Outcome 1M %", "Outcome 3M %", "Outcome 6M %"])
        st.dataframe(outcome_view, hide_index=True, width="stretch")
        lesson_rows = []
        for ticker in frame["Ticker"]:
            lesson = lesson_summary(get_backtest_runs(str(ticker)))
            lesson_rows.append({"Ticker": ticker, "Learned / saved": f"{lesson['sample_size']}/{lesson['total_runs']}",
                                "Decision accuracy": lesson["decision_accuracy"],
                                "Weighted monthly %": lesson["average_composite"], "Confidence": lesson["confidence"]})
        st.dataframe(pd.DataFrame(lesson_rows), hide_index=True, width="stretch")

    @st.fragment(run_every=5)
    def render_cohort_refresh_status() -> None:
        schedule_industry_refresh(refresh_priority, max_new=2)
        schedule_positioning_refresh(refresh_priority, max_new=2)
        schedule_finra_backfill(refresh_priority, max_new=2)
        statuses = tuple((ticker, industry_refresh_status(ticker)) for ticker in tickers)
        positioning_statuses = tuple((ticker, positioning_refresh_status(ticker)) for ticker in tickers)
        finra_statuses = tuple((ticker, finra_backfill_status(ticker)) for ticker in tickers)
        ready = sum(status in {"Ready", "Limited coverage", "Not applicable"} for _, status in statuses)
        updating = [ticker for ticker, status in statuses if status in {"Updating", "Discovering peers"}]
        st.caption(
            f"Cohort coverage: {ready}/{len(statuses)} ready"
            + (f" · Updating {', '.join(updating)} automatically" if updating else "")
        )
        previous = st.session_state.get("cohort_status_signature")
        finra_updating = [ticker for ticker, status in finra_statuses if status == "Backfilling"]
        if finra_updating:
            st.caption(f"FINRA history updating · {', '.join(finra_updating)}")
        signature = (statuses, positioning_statuses, finra_statuses)
        st.session_state.cohort_status_signature = signature
        if previous is not None and previous != signature:
            st.rerun()

    if not historical_mode:
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
            st.write(
                f"**Market positioning:** Entry {float(row['Positioning entry adj']):+.1f}; "
                f"Exit {float(row['Positioning exit adj']):+.1f}; "
                f"reliability {float(row['Positioning reliability']):.0f}/100."
            )
            st.caption(f"Short reversal lever · {row['Short reversal lever']}")
            if not historical_mode:
                if row.get("Ownership") == "Owned":
                    st.write(
                        f"**Position action — {row['Position action']}:** Add {float(row['Add score']):.1f}/100 · "
                        f"Trim {float(row['Trim score']):.1f}/100. {row['Position rationale']}"
                    )
                else:
                    st.write(f"**Initiation decision:** {row['Diagnostic']}. {row['Position rationale']}")
            if not historical_mode:
                st.write(
                    f"**Backtested learning:** Entry {float(row.get('Learning entry adj', 0)):+.1f}; "
                    f"Exit {float(row.get('Learning exit adj', 0)):+.1f}. {row.get('Learning rationale', 'No completed simulations yet.')}"
                )
if errors:
    st.error("Some data could not be fetched:")
    for error in errors:
        st.write(f"- {error}")
