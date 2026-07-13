"""Shared presentation system for Personal Equity Radar pages."""

from __future__ import annotations

import plotly.graph_objects as go
import pandas as pd
import streamlit as st
import streamlit.components.v1 as components


INK = "#e8eef7"
MUTED = "#93a4b8"
ACCENT = "#39d0b3"
BLUE = "#70a5ff"
GRID = "rgba(148, 163, 184, 0.12)"


def zebra_table(data: object) -> pd.io.formats.style.Styler:
    """Give native tables subtle, consistent alternating row tones."""
    frame = data.copy() if isinstance(data, pd.DataFrame) else pd.DataFrame(data)
    positions = {index: position for position, index in enumerate(frame.index)}

    def alternate(row: pd.Series) -> list[str]:
        color = "#0f1723" if positions.get(row.name, 0) % 2 == 0 else "#121c2a"
        return [f"background-color: {color};"] * len(row)

    return frame.style.apply(alternate, axis=1)


def inject_app_styles() -> None:
    """Inject a tiny global layer shared by every page."""
    st.markdown(
        """<style>
div[data-testid="stElementContainer"]:has(h1) {
     position: sticky !important; top: 2.55rem; z-index: 990; width: fit-content;
     padding: .12rem .45rem .2rem; margin-left: -.45rem;
     background: rgba(8, 13, 22, .94); border-radius: .4rem;
     backdrop-filter: blur(8px); }
/* Desktop gets a more comfortable reading scale while phone density stays compact. */
[data-testid="stSidebarNav"] a span,
[data-testid="stSidebarNav"] a p { font-size: 1.18rem !important; font-weight: 650; }
[data-testid="stSidebarNav"] a { min-height: 2.55rem; }
@media (min-width: 1100px) {
     html { font-size: 18px; }
}
/* Make the collapsed navigation discoverable without reserving horizontal space. */
[data-testid="stSidebarCollapsedControl"] button,
button[data-testid="stExpandSidebarButton"] {
     width: 3.15rem !important; height: 3.15rem !important;
     border: 1px solid rgba(112, 165, 255, .42) !important;
     border-radius: .8rem !important;
     background: rgba(16, 34, 56, .92) !important;
     box-shadow: 0 0 0 3px rgba(112, 165, 255, .08);
}
[data-testid="stSidebarCollapsedControl"] button svg,
[data-testid="stExpandSidebarButton"] svg {
     width: 1.65rem !important; height: 1.65rem !important;
}
[data-testid="stExpandSidebarButton"] [data-testid="stIconMaterial"] {
     font-size: 1.8rem !important; line-height: 1 !important;
}
[data-testid="stSidebarCollapsedControl"] button:hover,
button[data-testid="stExpandSidebarButton"]:hover {
     border-color: #70a5ff !important; transform: scale(1.04);
}
@media (max-width: 700px) {
     div[data-testid="stElementContainer"]:has(h1) { top: 2.45rem; }
     h1 { font-size: 1.65rem !important; }
     [data-testid="stSidebarCollapsedControl"] button,
     button[data-testid="stExpandSidebarButton"] {
          width: 2.85rem !important; height: 2.85rem !important; }
}
</style>""",
        unsafe_allow_html=True,
    )
    components.html(
        """<script>
(() => {
  const doc = window.parent.document;
  if (doc.documentElement.dataset.equityRadarSwipeNav === "ready") return;
  doc.documentElement.dataset.equityRadarSwipeNav = "ready";
  let startX = null;
  let startY = null;
  doc.addEventListener("touchstart", (event) => {
    const touch = event.touches[0];
    if (touch && touch.clientX <= 34) {
      startX = touch.clientX;
      startY = touch.clientY;
    } else {
      startX = startY = null;
    }
  }, {passive: true});
  doc.addEventListener("touchend", (event) => {
    if (startX === null) return;
    const touch = event.changedTouches[0];
    const horizontal = touch.clientX - startX;
    const vertical = Math.abs(touch.clientY - startY);
    startX = startY = null;
    if (horizontal < 72 || vertical > horizontal * 0.65) return;
    const control = doc.querySelector(
      '[data-testid="stSidebarCollapsedControl"] button, button[data-testid="stExpandSidebarButton"]'
    );
    if (control && window.parent.innerWidth <= 700) control.click();
  }, {passive: true});
})();
</script>""",
        height=0,
        width=0,
    )


def page_header(eyebrow: str, title: str, description: str, pill: str) -> None:
    """Render a native Streamlit masthead that survives frontend version changes."""
    st.caption(eyebrow.upper())
    st.title(title)
    description_col, pill_col = st.columns([5, 2], vertical_alignment="bottom")
    with description_col:
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
