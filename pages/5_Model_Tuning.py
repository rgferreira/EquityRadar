"""Read-only Phase 3.9 live-versus-shadow research console."""

from __future__ import annotations

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from src.data.database import (
    get_outcome_labels, get_prediction_snapshots, get_shadow_decision_snapshots, init_db,
)
from src.model_tuning import (
    build_model_tuning_report, cumulative_date_evidence, prepare_shadow_comparisons,
)
from src.outcome_labels import RELATIVE_LABEL_VERSION
from src.ui import inject_app_styles, page_header, style_figure, zebra_table


def _pct(value: object, *, points: bool = False) -> str:
    if value is None:
        return "—"
    number = float(value) * (100 if points else 1)
    return f"{number:+.2f}{' pp' if points else '%'}"


def _interval(summary: dict[str, object], *, points: bool = False) -> str:
    estimate = _pct(summary.get("estimate"), points=points)
    if summary.get("ci_low") is None:
        return f"{estimate} · interval unavailable"
    return f"{estimate} · 95% CI {_pct(summary['ci_low'], points=points)} to {_pct(summary['ci_high'], points=points)}"


st.set_page_config(page_title="Model tuning | Personal Equity Radar", page_icon="🧪", layout="wide")
inject_app_styles()
init_db()
page_header(
    "Phase 3.9 research console", "Model tuning",
    "Confront the active policy with its inactive coverage-aware shadow on identical evidence.",
    "Read-only · No automatic promotion",
)
st.warning(
    "Shadow results are experimental evidence, not investment guidance. This page cannot change "
    "the active model, weights, thresholds, scores, or diagnostics.", icon="⚠️",
)

comparisons = prepare_shadow_comparisons(
    get_shadow_decision_snapshots(), get_prediction_snapshots(),
    get_outcome_labels(label_version=RELATIVE_LABEL_VERSION), horizon="3M",
)
if not comparisons:
    st.info("No shadow snapshots have accumulated yet.")
    st.stop()

with st.expander("Filter research evidence", expanded=False):
    filter_cols = st.columns(4)
    tickers = sorted({str(row["ticker"]) for row in comparisons})
    modes = sorted({str(row["coverage_mode"]) for row in comparisons})
    sources = sorted({str(row["simulation_source"]) for row in comparisons})
    selected_tickers = filter_cols[0].multiselect("Tickers", tickers, default=tickers)
    selected_modes = filter_cols[1].multiselect("Coverage modes", modes, default=modes)
    selected_sources = filter_cols[2].multiselect("Sources", sources, default=sources)
    changed_only = filter_cols[3].toggle("Signal changes only", value=False)

filtered = [
    row for row in comparisons
    if row["ticker"] in selected_tickers
    and row["coverage_mode"] in selected_modes
    and row["simulation_source"] in selected_sources
    and (not changed_only or row["signal_changed"])
]
report = build_model_tuning_report(filtered)
coverage = report["coverage"]
gate = report["gate"]

status_color = {
    "Collecting evidence": "blue", "Inconclusive": "orange",
    "Eligible for human review": "green",
}.get(str(gate["status"]), "gray")
st.markdown(f"### Evidence status: :{status_color}[{gate['status']}]")
st.caption(str(gate["rationale"]))

st.subheader(f"Promotion readiness · {gate['passed']}/{gate['total']} gates green")
criteria_columns = st.columns(2)
for index, criterion in enumerate(gate["criteria"]):
    icon = "🟢" if criterion["passed"] else "🔴"
    with criteria_columns[index % 2]:
        with st.container(border=True):
            st.markdown(f"**{icon} {criterion['criterion']}**")
            st.markdown(f"**Observed:** {criterion['observed']}  ")
            st.caption(f"Required: {criterion['required']}")
            st.caption(str(criterion["purpose"]))
st.caption(
    "All gates are mandatory. Green means eligible for a deliberate human promotion review—not proven "
    "alpha, not approval, and never automatic activation."
)

metrics = st.columns(6)
metrics[0].metric("Snapshots", int(coverage["snapshots"]))
metrics[1].metric("Tickers", int(coverage["tickers"]))
metrics[2].metric("Matured 3M", int(coverage["matured_observations"]))
metrics[3].metric("Matured dates", int(coverage["matured_dates"]))
metrics[4].metric("Signal changes", int(coverage["signal_changes"]))
metrics[5].metric("Changed dates", int(coverage["changed_dates"]))

summary_tab, outcomes_tab, drilldown_tab, lineage_tab = st.tabs([
    "Evidence overview", "Paired outcomes", "Drill-downs", "Lineage & maturity",
])

with summary_tab:
    st.subheader("Where the shadow differs")
    left, right = st.columns(2)
    frame = pd.DataFrame(filtered)
    with left:
        histogram = px.histogram(
            frame, x="score_delta", color="coverage_mode", nbins=24,
            labels={"score_delta": "Shadow − live Entry score", "count": "Snapshots"},
        )
        st.plotly_chart(style_figure(histogram, height=390), use_container_width=True)
    with right:
        transitions = (
            frame.groupby(["live_signal", "shadow_signal"], as_index=False)
            .size().rename(columns={"size": "snapshots"})
        )
        transition_chart = px.bar(
            transitions, x="live_signal", y="snapshots", color="shadow_signal",
            barmode="stack", labels={"live_signal": "Live signal", "shadow_signal": "Shadow signal"},
        )
        st.plotly_chart(style_figure(transition_chart, height=390), use_container_width=True)
    timeline = (
        frame.groupby("as_of_date", as_index=False)
        .agg(mean_score_delta=("score_delta", "mean"), signal_changes=("signal_changed", "sum"))
    )
    timeline_chart = go.Figure()
    timeline_chart.add_trace(go.Scatter(
        x=timeline["as_of_date"], y=timeline["mean_score_delta"], name="Mean score delta",
        mode="lines+markers",
    ))
    timeline_chart.add_trace(go.Bar(
        x=timeline["as_of_date"], y=timeline["signal_changes"], name="Signal changes",
        opacity=.35, yaxis="y2",
    ))
    timeline_chart.update_layout(
        yaxis={"title": "Shadow − live points"},
        yaxis2={"title": "Changes", "overlaying": "y", "side": "right", "rangemode": "tozero"},
    )
    st.plotly_chart(style_figure(timeline_chart, height=400), use_container_width=True)

with outcomes_tab:
    st.subheader("Paired 3M benchmark-relative outcomes")
    st.caption(
        "Every comparison uses the same ticker, cutoff, outcome contract and benchmark. "
        "Dates—not rows—are treated as independent evidence clusters."
    )
    all_pair = report["all_paired"]
    changed_pair = report["changed_paired"]
    all_cols = st.columns(2)
    all_cols[0].metric("All snapshots · utility delta", _pct(all_pair["utility_delta_pct"]["estimate"]))
    all_cols[0].caption(_interval(all_pair["utility_delta_pct"]))
    all_cols[1].metric("All snapshots · accuracy delta", _pct(all_pair["accuracy_delta"]["estimate"], points=True))
    all_cols[1].caption(_interval(all_pair["accuracy_delta"], points=True))
    changed_cols = st.columns(2)
    changed_cols[0].metric("Changed signals · utility delta", _pct(changed_pair["utility_delta_pct"]["estimate"]))
    changed_cols[0].caption(_interval(changed_pair["utility_delta_pct"]))
    changed_cols[1].metric("Changed signals · accuracy delta", _pct(changed_pair["accuracy_delta"]["estimate"], points=True))
    changed_cols[1].caption(_interval(changed_pair["accuracy_delta"], points=True))

    curve = pd.DataFrame(cumulative_date_evidence(filtered))
    if not curve.empty:
        curve_long = curve.melt(
            id_vars=["as_of_date", "independent_dates"],
            value_vars=["live_expanding_utility_pct", "shadow_expanding_utility_pct"],
            var_name="policy", value_name="expanding_utility_pct",
        )
        curve_long["policy"] = curve_long["policy"].map({
            "live_expanding_utility_pct": "Live", "shadow_expanding_utility_pct": "Shadow",
        })
        chart = px.line(
            curve_long, x="as_of_date", y="expanding_utility_pct", color="policy", markers=True,
            labels={"as_of_date": "Decision cutoff", "expanding_utility_pct": "Expanding date-clustered utility %"},
        )
        st.plotly_chart(style_figure(chart, height=420), use_container_width=True)
    else:
        st.info("No 3M outcomes have matured for the selected evidence.")

with drilldown_tab:
    st.subheader("Stability checks")
    selector = st.radio(
        "Break down by", ["Ticker", "Coverage mode", "Technical regime", "Simulation source"],
        horizontal=True,
    )
    lookup = {
        "Ticker": ("by_ticker", "ticker"),
        "Coverage mode": ("by_coverage_mode", "coverage_mode"),
        "Technical regime": ("by_technical_regime", "technical_regime"),
        "Simulation source": ("by_simulation_source", "simulation_source"),
    }
    report_key, label = lookup[selector]
    breakdown = pd.DataFrame(report[report_key])
    st.dataframe(
        zebra_table(breakdown), hide_index=True, use_container_width=True,
        column_config={
            label: st.column_config.TextColumn(selector),
            "utility_delta_pct": st.column_config.NumberColumn("Utility Δ", format="%+.2f%%"),
            "accuracy_delta_pp": st.column_config.NumberColumn("Accuracy Δ", format="%+.2f pp"),
            "mean_score_delta": st.column_config.NumberColumn("Score Δ", format="%+.2f"),
        },
    )
    st.caption("Small groups are descriptive only; they are not independent promotion tests.")

with lineage_tab:
    st.subheader("Evidence lineage and maturity")
    statuses = pd.DataFrame([
        {"Outcome status": status.replace("_", " ").title(), "Snapshots": count}
        for status, count in sorted(coverage["label_statuses"].items())
    ])
    st.dataframe(zebra_table(statuses), hide_index=True, use_container_width=True)
    st.caption(
        "Not linked means a live dashboard observation has no immutable historical prediction/outcome yet. "
        "Unavailable is preserved as missing evidence and never treated directionally."
    )
    detail_columns = [
        "ticker", "as_of_date", "surface", "simulation_source", "coverage_mode",
        "live_score", "shadow_score", "score_delta", "live_signal", "shadow_signal",
        "signal_changed", "label_status", "outcome_end_date", "relative_return_pct",
        "utility_delta_pct",
    ]
    detail = pd.DataFrame(filtered)[detail_columns].sort_values(["as_of_date", "ticker"], ascending=[False, True])
    st.dataframe(
        zebra_table(detail), hide_index=True, use_container_width=True, height=min(720, 42 + len(detail) * 35),
        column_config={
            "relative_return_pct": st.column_config.NumberColumn("3M relative return", format="%+.2f%%"),
            "utility_delta_pct": st.column_config.NumberColumn("Utility Δ", format="%+.2f%%"),
            "score_delta": st.column_config.NumberColumn("Score Δ", format="%+.1f"),
        },
    )

st.divider()
st.caption(
    "Promotion boundary · This console is observational. Model activation requires an explicit, "
    "reviewable and reversible decision after preregistered evidence gates are met."
)
