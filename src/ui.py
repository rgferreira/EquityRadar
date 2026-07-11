"""Shared presentation system for Personal Equity Radar pages."""

from __future__ import annotations

import plotly.graph_objects as go
import streamlit as st


INK = "#e8eef7"
MUTED = "#93a4b8"
ACCENT = "#39d0b3"
BLUE = "#70a5ff"
GRID = "rgba(148, 163, 184, 0.12)"


def inject_app_styles() -> None:
    """Reserved for a future theme layer; intentionally uses no HTML components."""


def page_header(eyebrow: str, title: str, description: str, pill: str) -> None:
    """Render a native Streamlit masthead that survives frontend version changes."""
    st.caption(eyebrow.upper())
    title_col, pill_col = st.columns([5, 2], vertical_alignment="bottom")
    with title_col:
        st.title(title)
        st.caption(description)
    with pill_col:
        st.info(pill, icon="ℹ️")
    st.divider()


def style_figure(figure: go.Figure, *, height: int | None = None) -> go.Figure:
    """Give Plotly charts a consistent low-chrome financial-dashboard theme."""
    figure.update_layout(
        template="plotly_dark",
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(8,20,35,.6)",
        font={"color": MUTED, "family": "Inter, ui-sans-serif, system-ui"},
        colorway=[ACCENT, BLUE, "#f0b36a", "#c18cff", "#ef7189"],
        hoverlabel={"bgcolor": "#102238", "bordercolor": "#28425f", "font_color": INK},
        legend={"orientation": "h", "yanchor": "bottom", "y": 1.02, "xanchor": "right", "x": 1},
        margin={"l": 12, "r": 12, "t": 54, "b": 12},
        height=height,
    )
    figure.update_xaxes(showgrid=False, zeroline=False)
    figure.update_yaxes(gridcolor=GRID, zeroline=False)
    return figure
