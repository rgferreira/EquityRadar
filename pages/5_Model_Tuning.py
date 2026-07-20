"""Read-only Phase 3.9 live-versus-shadow decision center."""

from __future__ import annotations

import html

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from src.data.database import (
    get_model_gate_exclusions, get_model_promotion_event, get_outcome_labels,
    get_prediction_snapshots, get_shadow_decision_snapshots, init_db,
    save_model_gate_exclusions,
)
from src.model_registry import (
    COVERAGE_AWARE_SHADOW_VERSION, CURRENT_MODEL_VERSION,
    EVIDENCE_POLICY_PREVIOUS_LIVE_VERSION, TECHNOLOGY_POTENTIAL_SHADOW_VERSION,
)
from src.model_tuning import (
    build_model_tuning_report, build_post_promotion_report, cumulative_curve_overlap,
    cumulative_date_evidence, prepare_shadow_comparisons,
)
from src.outcome_labels import RELATIVE_LABEL_VERSION
from src.ui import inject_app_styles, page_header, style_figure, zebra_table


def _pct(value: object, *, points: bool = False) -> str:
    if value is None:
        return "Awaiting"
    number = float(value) * (100 if points else 1)
    return f"{number:+.2f}{' pp' if points else '%'}"


def _interval(summary: dict[str, object], *, points: bool = False) -> str:
    if summary.get("estimate") is None:
        return "Not calculable until a matching 3M outcome matures."
    estimate = _pct(summary.get("estimate"), points=points)
    if summary.get("ci_low") is None:
        return f"{estimate} · more independent dates are needed for an interval."
    return (
        f"{estimate} · 95% CI {_pct(summary['ci_low'], points=points)} "
        f"to {_pct(summary['ci_high'], points=points)}"
    )


def _model_card(role: str, version: str, state: str, description: str, tone: str) -> str:
    return (
        f"<div class='mt-model-card mt-{tone}'>"
        f"<div class='mt-role'>{html.escape(role)}</div>"
        f"<div class='mt-version'>{html.escape(version)}</div>"
        f"<div class='mt-state'>{html.escape(state)}</div>"
        f"<div class='mt-description'>{html.escape(description)}</div>"
        "</div>"
    )


def _utility_curve(
    rows: list[dict[str, object]], *, live_label: str, candidate_label: str,
) -> go.Figure | None:
    curve = pd.DataFrame(cumulative_date_evidence(rows))
    if curve.empty:
        return None
    figure = go.Figure()
    figure.add_trace(go.Scatter(
        x=curve["as_of_date"], y=curve["live_expanding_utility_pct"],
        name=live_label, mode="lines+markers",
        line={"color": "#a8bdd8", "dash": "dot", "width": 5},
        marker={"symbol": "circle-open", "size": 11, "line": {"width": 2}},
    ))
    figure.add_trace(go.Scatter(
        x=curve["as_of_date"], y=curve["shadow_expanding_utility_pct"],
        name=candidate_label, mode="lines+markers",
        line={"color": "#2f80ed", "width": 2.5},
        marker={"symbol": "diamond", "size": 6},
    ))
    figure.update_layout(
        hovermode="x unified",
        yaxis_title="Expanding date-clustered utility %",
        xaxis_title="Decision cutoff",
        legend={"orientation": "h", "yanchor": "bottom", "y": 1.02, "x": 0},
    )
    return style_figure(figure, height=420)


def _render_pair_summary(
    report: dict[str, object], *, live_label: str, candidate_label: str,
) -> None:
    pair = report["all_paired"]
    columns = st.columns(4)
    columns[0].metric(live_label, _pct(pair["live_utility_pct"]["estimate"]))
    columns[1].metric(candidate_label, _pct(pair["shadow_utility_pct"]["estimate"]))
    columns[2].metric("Paired utility Δ", _pct(pair["utility_delta_pct"]["estimate"]))
    columns[3].metric("Paired accuracy Δ", _pct(pair["accuracy_delta"]["estimate"], points=True))
    st.caption(
        f"Utility interval · {_interval(pair['utility_delta_pct'])}  \n"
        f"Accuracy interval · {_interval(pair['accuracy_delta'], points=True)}"
    )


st.set_page_config(page_title="Model tuning | Personal Equity Radar", page_icon="🧪", layout="wide")
inject_app_styles()
init_db()
st.html("""
<style>
.mt-model-grid,.mt-step-grid{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:.75rem;margin:.6rem 0 1rem}
.mt-step-grid{grid-template-columns:repeat(4,minmax(0,1fr))}
.mt-model-card,.mt-step{border:1px solid #39465b;border-radius:.75rem;padding:1rem;min-width:0;background:#151b25}
.mt-live{border-top:4px solid #52d6a5}.mt-shadow{border-top:4px solid #4f8cff}.mt-rollback{border-top:4px solid #a8b0bc}
.mt-role,.mt-step-number{font-size:.72rem;letter-spacing:.08em;text-transform:uppercase;color:#9aa6b5;font-weight:700}
.mt-version{font-size:.9rem;font-weight:700;line-height:1.3;margin:.35rem 0;overflow-wrap:anywhere;color:#f3f6fa}
.mt-state{font-size:1.05rem;font-weight:750;margin:.3rem 0}.mt-description{font-size:.8rem;color:#aeb7c4;line-height:1.45}
.mt-step{padding:.8rem}.mt-step strong{display:block;margin:.25rem 0;font-size:.9rem}.mt-step p{margin:0;color:#aeb7c4;font-size:.78rem;line-height:1.4}
@media(max-width:700px){.mt-model-grid,.mt-step-grid{grid-template-columns:1fr}.mt-model-card{padding:.8rem}.mt-version{font-size:.82rem}}
</style>
""")
page_header(
    "Phase 3.9 shadow decision center", "Model tuning",
    "Compare the live model with one active shadow hypothesis using versioned, benchmark-relative evidence.",
    "Research governance · No automatic promotion",
)

predictions = get_prediction_snapshots()
labels = get_outcome_labels(label_version=RELATIVE_LABEL_VERSION)
shadow_snapshots = get_shadow_decision_snapshots()
promotion = get_model_promotion_event(CURRENT_MODEL_VERSION)
immediate_rollback = str(
    (promotion or {}).get("rollback_model_version") or EVIDENCE_POLICY_PREVIOUS_LIVE_VERSION
)

active_snapshots = [
    row for row in shadow_snapshots
    if str(row.get("challenger_model_version")) == TECHNOLOGY_POTENTIAL_SHADOW_VERSION
]
promotion_archive_snapshots = [
    row for row in shadow_snapshots
    if str(row.get("challenger_model_version")) == COVERAGE_AWARE_SHADOW_VERSION
]
retired_snapshots = [
    row for row in shadow_snapshots
    if str(row.get("challenger_model_version"))
    not in {TECHNOLOGY_POTENTIAL_SHADOW_VERSION, COVERAGE_AWARE_SHADOW_VERSION}
]
comparisons = prepare_shadow_comparisons(active_snapshots, predictions, labels, horizon="3M")
promotion_comparisons = prepare_shadow_comparisons(
    promotion_archive_snapshots, predictions, labels, horizon="3M",
)
retired_comparisons = prepare_shadow_comparisons(retired_snapshots, predictions, labels, horizon="3M")

tickers = sorted({str(row["ticker"]) for row in comparisons})
persisted_gate_exclusions = get_model_gate_exclusions()
excluded = set(persisted_gate_exclusions)
gate_comparisons = [row for row in comparisons if row["ticker"] not in excluded]
gate_report = build_model_tuning_report(gate_comparisons)
coverage = gate_report["coverage"]
gate = gate_report["gate"]

model_grid = "".join([
    _model_card(
        "Current live", CURRENT_MODEL_VERSION, "Applied to user-facing scores",
        "The production policy. It is monitored prospectively and changes only after an explicit human decision.", "live",
    ),
    _model_card(
        "Active shadow", TECHNOLOGY_POTENTIAL_SHADOW_VERSION,
        f"{gate['status']} · {gate['passed']}/{gate['total']} gates",
        "Runs beside live on the same inputs. Its outputs are diagnostic only and cannot alter scores.", "shadow",
    ),
    _model_card(
        "Immediate rollback", immediate_rollback, "Frozen and available",
        "The direct recovery model recorded when the current live version was activated.", "rollback",
    ),
])
st.html(f"<div class='mt-model-grid'>{model_grid}</div>")

with st.expander("How this page works · read in 30 seconds", expanded=True):
    st.html("""
    <div class='mt-step-grid'>
      <div class='mt-step'><div class='mt-step-number'>1 · Observe</div><strong>Live and shadow score together</strong><p>The shadow never reaches Dashboard decisions.</p></div>
      <div class='mt-step'><div class='mt-step-number'>2 · Wait</div><strong>The same 3M outcome matures</strong><p>No future data may enter the original decision.</p></div>
      <div class='mt-step'><div class='mt-step-number'>3 · Compare</div><strong>Benchmark-relative utility is paired</strong><p>Dates—not ticker rows—are independent evidence.</p></div>
      <div class='mt-step'><div class='mt-step-number'>4 · Decide</div><strong>Six gates permit human review</strong><p>Green gates never promote a model automatically.</p></div>
    </div>
    """)
    st.caption(
        "Score movement is descriptive. Promotion evidence becomes decision-relevant only when the shadow "
        "changes a diagnostic and that changed decision later receives a mature, point-in-time-valid outcome."
    )

st.warning(
    "This console evaluates research evidence; it does not claim durable alpha and cannot change model "
    "weights, thresholds, scores, diagnostics, or the active model.", icon="⚠️",
)

if promotion:
    prospective = build_post_promotion_report(
        predictions, labels, model_version=CURRENT_MODEL_VERSION,
        promoted_at=str(promotion["promoted_at"]),
    )
    with st.container(border=True):
        st.markdown("### Live-model monitoring after activation")
        st.caption(
            f"Current live was activated {promotion['promoted_at']} as `{promotion['decision_type']}`. "
            "Only decisions dated on/after activation and created afterward count here; later-created "
            "historical simulations are excluded."
        )
        monitor_columns = st.columns(4)
        monitor_columns[0].metric("Prospective matured rows", prospective["matured_observations"])
        monitor_columns[1].metric("Prospective dates", prospective["independent_dates"])
        monitor_columns[2].metric(
            "Prospective accuracy",
            "Awaiting 3M" if prospective["accuracy_pct"] is None else f"{prospective['accuracy_pct']:.2f}%",
        )
        baseline = prospective["frozen_baseline"]
        monitor_columns[3].metric("Frozen original accuracy", f"{baseline['accuracy_pct']:.2f}%")
        st.caption(
            "The frozen baseline belongs to the original 6/6 promotion experiment. The current v4 live "
            "model was activated later as an evidence-policy correction, not through a second gate clearance."
        )
        if prospective["status"] == "awaiting_maturity":
            st.info(
                "No genuinely post-activation 3M outcome has matured yet. This is expected and prevents "
                "historical replays from masquerading as prospective monitoring."
            )
        else:
            st.caption(
                f"Prospective utility · {_interval(prospective['utility_interval'])} · "
                f"Accuracy · {_interval(prospective['accuracy_interval'], points=True)}"
            )

with st.expander("Research-view filters · do not alter promotion gates", expanded=False):
    filter_columns = st.columns(4)
    modes = sorted({str(row["coverage_mode"]) for row in comparisons})
    sources = sorted({str(row["simulation_source"]) for row in comparisons})
    selected_tickers = filter_columns[0].multiselect("Tickers", tickers, default=tickers)
    selected_modes = filter_columns[1].multiselect("Coverage modes", modes, default=modes)
    selected_sources = filter_columns[2].multiselect("Sources", sources, default=sources)
    changed_only = filter_columns[3].toggle("Signal changes only", value=False)

filtered = [
    row for row in comparisons
    if row["ticker"] in selected_tickers
    and row["coverage_mode"] in selected_modes
    and row["simulation_source"] in selected_sources
    and (not changed_only or row["signal_changed"])
]
report = build_model_tuning_report(filtered)

readiness_tab, outcomes_tab, diagnostics_tab, lineage_tab, archive_tab = st.tabs([
    "Readiness", "Paired outcomes", "Score diagnostics", "Lineage & maturity", "Promotion archive",
])

with readiness_tab:
    status_color = {
        "Collecting evidence": "gray", "Inconclusive": "orange",
        "Eligible for human review": "green",
    }.get(str(gate["status"]), "gray")
    st.subheader("Can the active shadow be considered for promotion?")
    st.markdown(f"**Current answer:** :{status_color}[{gate['status']}] · **{gate['passed']}/{gate['total']} gates green**")
    st.caption(str(gate["rationale"]))
    if not comparisons:
        st.info(
            "No active-shadow snapshots exist yet. Loading the Dashboard records prospective observations; "
            "legacy outcomes will not be reused or invented."
        )
    metric_row_one = st.columns(3)
    metric_row_one[0].metric("Active snapshots", int(coverage["snapshots"]))
    metric_row_one[1].metric("Included tickers", int(coverage["tickers"]))
    metric_row_one[2].metric("Independent dates", int(coverage["independent_dates"]))
    metric_row_two = st.columns(3)
    metric_row_two[0].metric("Matured 3M pairs", int(coverage["matured_observations"]))
    metric_row_two[1].metric("Changed diagnostics", int(coverage["signal_changes"]))
    metric_row_two[2].metric("Matured changed dates", int(coverage["changed_dates"]))
    st.caption(
        "A large snapshot count is not enough: the decisive bottleneck is mature outcomes from dates "
        "on which the shadow would actually have changed the diagnostic."
    )

    st.markdown("#### Promotion-readiness gates")
    st.caption(
        "Pipeline percentage measures evidence completion—not the probability of passing. "
        f"Currently {coverage['pending_signal_changes']} changed observations across "
        f"{coverage['pending_changed_dates']} date(s) are awaiting 3M outcomes."
    )
    gate_columns = st.columns(2)
    for index, criterion in enumerate(gate["criteria"]):
        icon = (
            "🟢" if criterion["passed"] else
            "⚪" if not criterion["available"] or gate["status"] == "Collecting evidence" else "🔴"
        )
        with gate_columns[index % 2]:
            with st.container(border=True):
                st.markdown(f"**{icon} {criterion['criterion']}**")
                st.markdown(f"**Observed:** {criterion['observed']}")
                st.progress(
                    int(criterion["progress_pct"]),
                    text=f"Evidence pipeline · {int(criterion['progress_pct'])}%",
                )
                st.caption(str(criterion["progress_detail"]))
                st.caption(f"Pass rule · {criterion['required']}")
                st.caption(str(criterion["purpose"]))

    gate_universe_options = sorted(set(tickers) | set(persisted_gate_exclusions))
    with st.expander("Promotion gate universe", expanded=False):
        st.caption(
            "Excluded tickers retain every snapshot and outcome but do not contribute to these six gates."
        )
        pending_gate_exclusions = st.multiselect(
            "Excluded from promotion gates", gate_universe_options,
            default=persisted_gate_exclusions, key="pending_model_gate_exclusions",
        )
        if st.button("Save gate universe", type="primary"):
            save_model_gate_exclusions(pending_gate_exclusions)
            st.success("Gate universe saved; underlying evidence remains intact.")
            st.rerun()
        st.caption(
            "Currently excluded · " + (" · ".join(persisted_gate_exclusions) if persisted_gate_exclusions else "None")
        )

with outcomes_tab:
    st.subheader("Paired 3M benchmark-relative outcomes")
    st.caption(
        "Active comparison: current live versus active shadow, using the same ticker, cutoff, outcome "
        "contract, transaction-cost convention, and benchmark."
    )
    active_coverage = report["coverage"]
    if active_coverage["matured_observations"] == 0:
        st.info("No selected active-shadow observation has a mature 3M paired outcome yet.")
    elif active_coverage["matured_signal_changes"] == 0:
        st.info(
            f"{active_coverage['matured_observations']} paired observations across "
            f"{active_coverage['matured_dates']} dates have matured, but none changed the diagnostic. "
            "They measure policy equivalence so far; they cannot establish shadow improvement."
        )
    _render_pair_summary(
        report, live_label="Current live utility", candidate_label="Active shadow utility",
    )

    st.markdown("#### Outcomes where the diagnostic changed")
    changed_pair = report["changed_paired"]
    if active_coverage["matured_signal_changes"] == 0:
        with st.container(border=True):
            st.info(
                f"Not calculable yet. {active_coverage['pending_signal_changes']} changed observations across "
                f"{active_coverage['pending_changed_dates']} date(s) are still awaiting their 3M outcomes."
            )
    else:
        changed_columns = st.columns(2)
        changed_columns[0].metric("Changed-signal utility Δ", _pct(changed_pair["utility_delta_pct"]["estimate"]))
        changed_columns[0].caption(_interval(changed_pair["utility_delta_pct"]))
        changed_columns[1].metric(
            "Changed-signal accuracy Δ", _pct(changed_pair["accuracy_delta"]["estimate"], points=True),
        )
        changed_columns[1].caption(_interval(changed_pair["accuracy_delta"], points=True))

    st.markdown("#### Utility evolution by independent decision date")
    active_chart = _utility_curve(
        filtered, live_label="Current live", candidate_label="Active shadow",
    )
    if active_chart is None:
        st.info("The curve will appear after the first selected 3M outcome matures.")
    else:
        st.plotly_chart(active_chart, use_container_width=True)
        overlap = cumulative_curve_overlap(filtered)
        if overlap["fully_overlapping"]:
            st.info(
                f"Both traces are present and overlap exactly on all {overlap['dates']} matured dates. "
                "The dotted open-circle line is current live; the solid diamond line is active shadow. "
                "Exact overlap means the matured diagnostics were identical."
            )
        else:
            st.caption(
                f"Curve overlap · {overlap['overlapping_dates']}/{overlap['dates']} dates · "
                f"maximum expanding utility gap {float(overlap['max_gap_pct']):.2f} percentage points."
            )

    matured_rows = [row for row in filtered if row.get("utility_delta_pct") is not None]
    with st.expander(f"Inspect matured paired rows · {len(matured_rows)}", expanded=False):
        if not matured_rows:
            st.caption("No matured rows in the current research view.")
        else:
            matured_frame = pd.DataFrame(matured_rows)[[
                "ticker", "as_of_date", "live_signal", "shadow_signal", "relative_return_pct",
                "live_utility_pct", "shadow_utility_pct", "utility_delta_pct",
            ]]
            st.dataframe(
                zebra_table(matured_frame), hide_index=True, use_container_width=True,
                height=min(620, 42 + len(matured_frame) * 35),
                column_config={
                    "relative_return_pct": st.column_config.NumberColumn("3M relative return", format="%+.2f%%"),
                    "live_utility_pct": st.column_config.NumberColumn("Live utility", format="%+.2f%%"),
                    "shadow_utility_pct": st.column_config.NumberColumn("Shadow utility", format="%+.2f%%"),
                    "utility_delta_pct": st.column_config.NumberColumn("Utility Δ", format="%+.2f%%"),
                },
            )

with diagnostics_tab:
    st.subheader("How the active shadow differs before outcomes mature")
    st.caption(
        "These are diagnostic comparisons, not performance claims. A score change without a label change "
        "does not yet create a different investment decision."
    )
    frame = pd.DataFrame(filtered)
    if frame.empty:
        st.info("No active-shadow observations match the selected research filters.")
    else:
        chart_columns = st.columns(2)
        with chart_columns[0]:
            histogram = px.histogram(
                frame, x="score_delta", color="coverage_mode", nbins=24,
                labels={"score_delta": "Active shadow − current live Entry points", "count": "Snapshots"},
            )
            histogram.update_layout(legend={"orientation": "h", "y": 1.08})
            st.plotly_chart(style_figure(histogram, height=370), use_container_width=True)
        with chart_columns[1]:
            transitions = (
                frame.groupby(["live_signal", "shadow_signal"], as_index=False)
                .size().rename(columns={"size": "snapshots"})
            )
            transition_chart = px.bar(
                transitions, x="live_signal", y="snapshots", color="shadow_signal", barmode="stack",
                labels={"live_signal": "Current live diagnostic", "shadow_signal": "Active shadow diagnostic"},
            )
            transition_chart.update_layout(legend={"orientation": "h", "y": 1.08})
            st.plotly_chart(style_figure(transition_chart, height=370), use_container_width=True)
        timeline = (
            frame.groupby("as_of_date", as_index=False)
            .agg(mean_score_delta=("score_delta", "mean"), signal_changes=("signal_changed", "sum"))
        )
        timeline_chart = go.Figure()
        timeline_chart.add_trace(go.Scatter(
            x=timeline["as_of_date"], y=timeline["mean_score_delta"],
            name="Mean score Δ", mode="lines+markers",
        ))
        timeline_chart.add_trace(go.Bar(
            x=timeline["as_of_date"], y=timeline["signal_changes"],
            name="Diagnostic changes", opacity=.3, yaxis="y2",
        ))
        timeline_chart.update_layout(
            hovermode="x unified", legend={"orientation": "h", "y": 1.08},
            yaxis={"title": "Active shadow − current live points"},
            yaxis2={"title": "Changes", "overlaying": "y", "side": "right", "rangemode": "tozero"},
        )
        st.plotly_chart(style_figure(timeline_chart, height=390), use_container_width=True)

        st.markdown("#### Stability drill-down")
        selector = st.radio(
            "Break down by", ["Ticker", "Coverage mode", "Technical regime", "Simulation source"],
            horizontal=True,
        )
        lookup = {
            "Ticker": ("by_ticker", "ticker"), "Coverage mode": ("by_coverage_mode", "coverage_mode"),
            "Technical regime": ("by_technical_regime", "technical_regime"),
            "Simulation source": ("by_simulation_source", "simulation_source"),
        }
        report_key, label = lookup[selector]
        breakdown = pd.DataFrame(report[report_key])
        st.dataframe(
            zebra_table(breakdown), hide_index=True, use_container_width=True,
            height=min(620, 42 + len(breakdown) * 35),
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
    label_statuses = coverage["label_statuses"]
    broken_links = int(label_statuses.get("prediction_not_linked", 0))
    if broken_links:
        st.error(f"Lineage integrity warning · {broken_links} observation(s) are not linked to a prediction.")
    else:
        st.success("Lineage integrity check passed · every active observation is linked to a prediction.")
    definitions = {
        "available": "A valid 3M benchmark-relative outcome is attached and may enter paired analysis.",
        "awaiting_outcome": "Prediction is linked; the 3M horizon has not completed.",
        "pending": "Outcome materialization is scheduled or still incomplete.",
        "unavailable": "Required evidence is missing; it remains non-directional.",
        "prediction_not_linked": "Integrity defect: no matching immutable prediction exists.",
    }
    status_rows = []
    for status in sorted(set(definitions) | set(label_statuses)):
        status_rows.append({
            "Outcome status": status.replace("_", " ").title(),
            "Snapshots": int(label_statuses.get(status, 0)),
            "Meaning": definitions.get(status, "Preserved provider status."),
        })
    st.dataframe(zebra_table(pd.DataFrame(status_rows)), hide_index=True, use_container_width=True)
    st.caption("Missing or unavailable evidence never becomes neutral, positive, or negative evidence.")

    detail_columns = [
        "ticker", "as_of_date", "current_model_version", "challenger_model_version", "surface",
        "simulation_source", "coverage_mode", "live_score", "shadow_score", "score_delta",
        "live_signal", "shadow_signal", "signal_changed", "label_status", "outcome_end_date",
        "relative_return_pct", "utility_delta_pct",
    ]
    if not filtered:
        st.info("No lineage rows match the selected research filters.")
    else:
        detail = pd.DataFrame(filtered)[detail_columns].sort_values(
            ["as_of_date", "ticker"], ascending=[False, True],
        )
        st.dataframe(
            zebra_table(detail), hide_index=True, use_container_width=True,
            height=min(720, 42 + len(detail) * 35),
            column_config={
                "relative_return_pct": st.column_config.NumberColumn("3M relative return", format="%+.2f%%"),
                "utility_delta_pct": st.column_config.NumberColumn("Utility Δ", format="%+.2f%%"),
                "score_delta": st.column_config.NumberColumn("Score Δ", format="%+.1f"),
            },
        )

with archive_tab:
    st.subheader("Frozen promotion audit")
    st.caption(
        "This section alone shows the former-live versus promoted-policy experiment. It is immutable, "
        "already consumed, and cannot authorize promotion of the active shadow."
    )
    if not promotion_comparisons:
        st.info("No frozen coverage-aware promotion comparison is available.")
    else:
        archived_current = str(promotion_comparisons[0]["current_model_version"])
        archived_candidate = str(promotion_comparisons[0]["challenger_model_version"])
        st.caption(
            f"Frozen experiment · former live `{archived_current}` → candidate `{archived_candidate}`."
        )
        promotion_report = build_model_tuning_report(promotion_comparisons)
        promotion_gate = promotion_report["gate"]
        st.success(
            f"Archived result · {promotion_gate['passed']}/{promotion_gate['total']} gates green · "
            "the candidate was promoted and this evidence is now read-only."
        )
        _render_pair_summary(
            promotion_report,
            live_label="Former-live utility",
            candidate_label="Promoted-policy utility",
        )
        archive_chart = _utility_curve(
            promotion_comparisons, live_label="Former live", candidate_label="Promoted policy",
        )
        if archive_chart is not None:
            st.plotly_chart(archive_chart, use_container_width=True)
            archive_overlap = cumulative_curve_overlap(promotion_comparisons)
            st.caption(
                f"Former-live/promoted overlap · {archive_overlap['overlapping_dates']}/"
                f"{archive_overlap['dates']} dates · maximum expanding utility gap "
                f"{float(archive_overlap['max_gap_pct'] or 0):.2f} percentage points. "
                "Distinct line styles keep coincident portions visible."
            )
        with st.expander("Archived gate evidence", expanded=False):
            archive_columns = st.columns(2)
            for index, criterion in enumerate(promotion_gate["criteria"]):
                with archive_columns[index % 2]:
                    icon = "🟢" if criterion["passed"] else "🔴"
                    st.markdown(f"{icon} **{criterion['criterion']}** · {criterion['observed']}")

    st.markdown("#### Other retired shadow experiments")
    if not retired_comparisons:
        st.caption("No additional retired shadow evidence is stored.")
    else:
        retired_rows = []
        experiment_keys = sorted({
            (str(row["current_model_version"]), str(row["challenger_model_version"]))
            for row in retired_comparisons
        })
        for current_version, challenger_version in experiment_keys:
            experiment = [
                row for row in retired_comparisons
                if row["current_model_version"] == current_version
                and row["challenger_model_version"] == challenger_version
            ]
            experiment_report = build_model_tuning_report(experiment)
            experiment_coverage = experiment_report["coverage"]
            retired_rows.append({
                "Retired shadow": challenger_version,
                "Compared with": current_version,
                "Snapshots": experiment_coverage["snapshots"],
                "Dates": experiment_coverage["independent_dates"],
                "Matured 3M": experiment_coverage["matured_observations"],
                "Diagnostic changes": experiment_coverage["signal_changes"],
                "Final gate state": experiment_report["gate"]["status"],
            })
        st.dataframe(
            zebra_table(pd.DataFrame(retired_rows)), hide_index=True, use_container_width=True,
            height=min(420, 42 + len(retired_rows) * 35),
        )
        st.caption("Experiments remain separate; their evidence is never pooled across model versions.")

st.divider()
st.caption(
    f"Model record · `{CURRENT_MODEL_VERSION}` is live · immediate rollback `{immediate_rollback}` · "
    f"active shadow `{TECHNOLOGY_POTENTIAL_SHADOW_VERSION}` · all historical evidence remains immutable."
)
