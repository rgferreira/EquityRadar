"""Local read-only results for frozen entry experiments and source coverage."""
import pandas as pd
import streamlit as st

from src.data.database import get_watchlist
from src.data.institutional_positioning import institutional_summary
from src.data.macro_context import macro_summary
from src.data.options_context import options_coverage
from src.data.research_signals import statuses
from src.entry_context import CONTRACT
from src.strategy_validation import latest_report
from src.entry_risk import latest_report as latest_risk_report, capture_overview
from src.ui import inject_app_styles, page_header

STRATEGIES = {"current_policy": "Política actual", "candidate_market": "A · Filtro de mercado",
    "candidate_sector": "B · Fuerza del sector", "SPY": "SPY", "equal_weight_universe": "Universo equiponderado",
    "momentum_v1": "Momentum v1 · control", "market_filter_only": "Solo filtro de mercado",
    "sector_without_leadership": "Sin liderazgo sectorial", "candidate_risk": "C · Tamaño por riesgo",
    "candidate_risk_sector": "C · Con límite sectorial", "current_matched_exposure": "Política actual · misma exposición",
    "SPY_matched_exposure": "SPY · misma exposición"}

st.set_page_config(page_title="Entry research | Personal Equity Radar", page_icon="🔬", layout="wide")
inject_app_styles()
page_header("Entry research", "Entry research", "Entradas, exceso frente al mercado y control de caídas.", "Investigación · Sin promoción automática")
overview = capture_overview()
latest, latest_risk = overview["v2"]["latest"], overview["v3"]["latest"]
st.caption(f"A/B: {overview['v2']['count']} capturas · C: {overview['v3']['count']} capturas · Peso añadido al modelo: 0%")
if latest:
    choices = [{"Estrategia": STRATEGIES[name], "Entradas": len(weights), "Exposición teórica %": round(sum(weights.values()) * 100),
                "Activos": ", ".join(weights) or "Efectivo"} for name, weights in latest["output"]["weights"].items()
               if name in {"current_policy", "candidate_market", "candidate_sector"}]
    with st.expander("Selección A/B registrada"):
        st.caption(f"Última captura: {latest['captured_at']}. Referencia: política actual del Dashboard; fuente y datos congelados en cada captura.")
        st.dataframe(pd.DataFrame(choices), hide_index=True, width="stretch")
    if latest["output"]["unavailable"]:
        st.warning("Hay candidatos sin contexto suficiente. Consulta las exclusiones; no se convierten en ventas ni en señales neutrales.")
else:
    st.info("La captura automática espera decisiones actuales y precios suficientes. El proceso funciona en segundo plano.")

section = st.radio("Ver", ["Riesgo y score", "Validación", "Macro, instituciones y opciones", "Archivo v1"], horizontal=True)
if section == "Riesgo y score":
    if latest_risk:
        with st.expander("Asignaciones teóricas y disponibilidad de C"):
            st.caption(f"Última captura C: {latest_risk['captured_at']}. A/B y los pesos del modelo permanecen congelados.")
            st.json(latest_risk["output"])
    source = st.radio("Evidencia C", ["Prospectiva", "Diagnóstico histórico"], horizontal=True)
    horizon = st.radio("Horizonte C", ["1M", "3M"], horizontal=True)
    cost = st.select_slider("Coste nominal de ida y vuelta (bps)", options=CONTRACT["cost_bps"], value=10)
    report = latest_risk_report("prospective" if source == "Prospectiva" else "retrospective_unverified", horizon)
    if source == "Diagnóstico histórico":
        st.warning("Histórico ya examinado, con disponibilidad original no acreditada. Sirve para diagnóstico; no demuestra ventaja futura.")
    if not report or not report["test_cohorts"]:
        st.info("C aún no tiene bloques de prueba maduros. Su reloj prospectivo empieza con su propia captura; no hereda resultados de A/B.")
    if report and report["test_cohorts"]:
        comparison = st.selectbox("Comparación emparejada", ["candidate_risk", "candidate_risk_sector"], format_func=STRATEGIES.get)
        rows = [r for r in report["summary"] if r["comparison"] == comparison and r["cost_bps"] == cost]
        st.subheader("Rentabilidad y riesgo con las mismas fechas")
        if rows:
            fields = ["strategy", "test_cohorts", "mean_excess_spy_pp", "mean_excess_current_pp",
                      "mean_excess_matched_current_pp", "max_drawdown_pct", "mean_exposure_pct"]
            display = pd.DataFrame(rows)[fields].copy()
            display["strategy"] = display["strategy"].map(STRATEGIES)
            display = display.rename(columns={"strategy": "Estrategia", "test_cohorts": "Bloques",
                "mean_excess_spy_pp": "Exceso vs SPY (pp)", "mean_excess_current_pp": "Exceso vs actual (pp)",
                "mean_excess_matched_current_pp": "Exceso a igual exposición (pp)",
                "max_drawdown_pct": "Caída máxima (%)", "mean_exposure_pct": "Exposición media (%)"})
            st.dataframe(display.round(2), hide_index=True, width="stretch")
            curves = {STRATEGIES[r["strategy"]]: pd.Series({pd.Timestamp(p["date"]): p["equity"] for p in r["points"]})
                      for r in report["curves"] if r["comparison"] == comparison and r["cost_bps"] == cost
                      and r["strategy"] in {comparison, "current_policy", "current_matched_exposure", "SPY"}}
            st.line_chart(pd.DataFrame(curves).sort_index(), height=280)
        else:
            st.info("No hay bloques elegibles para este candidato. El sector ausente no se rellena con el actual.")
        st.caption("Cada comparación usa fechas idénticas. Los controles con la misma exposición permiten separar el efecto de mantener efectivo del efecto de los tamaños.")
        diagnostics = report["diagnostics"][str(cost)]
        loss = diagnostics["losses"]
        st.subheader("Dónde fallan las entradas actuales")
        cols = st.columns(3)
        for column, label, key in zip(cols, ("Ganancia media", "Pérdida media", "Resultado medio por entrada"),
                                     ("mean_win_pct", "mean_loss_pct", "pooled_expectancy_pct")):
            value = loss[key]
            column.metric(label, f"{value:.2f}%" if value is not None else "Sin muestra")
        st.caption(f"{loss['entries']} entradas en {loss['dates']} fechas. Estadísticas descriptivas con operaciones correlacionadas; no son retornos de la cartera personal.")
        st.dataframe(pd.DataFrame(diagnostics["loss_concentration"][:10]).rename(columns={"ticker": "Valor",
            "gross_loss_contribution_pp": "Contribución bruta a pérdidas (pp)", "share_of_gross_losses_pct": "Parte de las pérdidas (%)"}).round(2),
            hide_index=True, width="stretch")
        st.subheader("¿Una puntuación alta aporta mejores entradas?")
        selection = st.radio("Población del score", ["all_inputs", "buys"],
                             format_func=lambda s: "Todos los activos" if s == "all_inputs" else "Solo compras", horizontal=True)
        bands = [r for r in diagnostics["score"]["bands"] if r["selection"] == selection]
        band_display = pd.DataFrame(bands).reindex(columns=["score_band", "dates", "observations", "mean_excess_spy_pp",
            "date_balanced_hit_pct", "mean_net_return_pct", "mean_mae_pct"]).rename(columns={
                "score_band": "Score", "dates": "Fechas", "observations": "Observaciones", "mean_excess_spy_pp": "Exceso vs SPY (pp)",
                "date_balanced_hit_pct": "Aciertos vs SPY (%)", "mean_net_return_pct": "Retorno neto (%)", "mean_mae_pct": "Peor recorrido medio (%)"})
        st.dataframe(band_display.round(2), hide_index=True, width="stretch")
        st.caption("Media primero por fecha y después entre fechas; bandas fijas, sin ajustar umbrales. El score no es una probabilidad. Versiones y tamaño de muestra permanecen visibles.")
        with st.expander("Ordenación dentro de cada fecha y franjas con fechas comunes"):
            st.dataframe(pd.DataFrame([r for r in diagnostics["score"]["ordering"] if r["selection"] == selection]), hide_index=True, width="stretch")
            st.dataframe(pd.DataFrame([r for r in diagnostics["score"]["paired_bands"] if r["selection"] == selection]), hide_index=True, width="stretch")
            st.caption("IC: correlación entre el orden del score y el del exceso posterior dentro de cada fecha. Negativo indica orden inverso en la muestra; no permite invertir la estrategia sin una nueva prueba.")
            st.json({"bands_with_uncertainty_and_versions": bands, "excluded_scores": diagnostics["score"]["excluded_scores"]})
        with st.expander("Peores entradas, recorrido y límites estadísticos"):
            st.dataframe(pd.DataFrame(diagnostics["worst_entries"]), hide_index=True, width="stretch")
            st.json({"losses": loss, "summary": rows, "unavailable_risk": report["unavailable_risk"],
                     "exclusions": report["exclusions"], "limitations": report["limitations"]})
            st.caption("MAE/MFE: peor/mejor liquidación hipotética a cierres, con costes. El mejor cierre observado después no constituye una regla de salida ejecutable.")
    with st.expander("Contrato C y estado de ejecución"):
        from src.entry_risk import CONTRACT as RISK_CONTRACT
        st.json(RISK_CONTRACT)
        st.dataframe(pd.DataFrame([s for s in statuses() if s["family"] == "pipeline"]), hide_index=True, width="stretch")
elif section == "Validación":
    source = st.radio("Evidencia", ["Prospectiva", "Diagnóstico histórico"], horizontal=True)
    horizon = st.radio("Horizonte", ["1M", "3M"], horizontal=True)
    report = latest_report("prospective" if source == "Prospectiva" else "retrospective_unverified", horizon)
    cost = st.select_slider("Coste nominal de ida y vuelta (bps)", options=CONTRACT["cost_bps"], value=10)
    if report:
        st.caption(f"{report['test_cohorts']} bloques de prueba sin solapamiento; {report['mature_complete_dates']} fechas con trayectorias completas. "
                   "Historia previa purgada con cinco días de embargo. Las reglas no ajustan parámetros.")
        rows = [r for r in report["summary"] if r["cost_bps"] == cost]
        if rows:
            fields = ["strategy", "test_cohorts", "mean_excess_spy_pct", "mean_excess_current_pct", "max_drawdown_pct",
                      "mean_entry_hit_rate_pct", "mean_exposure_pct", "positive_excess_cohorts"]
            display = pd.DataFrame(rows)[fields].copy()
            display["strategy"] = display["strategy"].map(STRATEGIES)
            st.dataframe(display.round(2), hide_index=True, width="stretch")
            curve_names = [r["strategy"] for r in rows]
            selected_curves = st.multiselect("Curvas de capital", curve_names,
                default=[name for name in ("SPY", "current_policy", "candidate_market") if name in curve_names],
                format_func=lambda name: STRATEGIES.get(name, name))
            curves = {STRATEGIES[r["strategy"]]: pd.Series({pd.Timestamp(p["date"]): p["equity"] for p in r["points"]})
                      for r in report["curves"] if r["cost_bps"] == cost and r["strategy"] in selected_curves}
            if curves:
                st.line_chart(pd.DataFrame(curves).sort_index(), height=300)
            st.caption("Capital teórico normalizado. Efectivo entre bloques; cada curva usa las fechas disponibles para esa estrategia. "
                       "Los excesos comparan siempre fechas idénticas. Drawdown medido a cierres diarios.")
        else:
            st.info("Todavía no hay suficientes bloques maduros. Capturar más activos de una misma fecha no crea periodos independientes.")
        if source == "Diagnóstico histórico":
            st.warning("Muestra histórica ya observada: diagnóstico de desarrollo, sin validez point-in-time acreditada. "
                       "No es una prueba nueva fuera de muestra ni justifica promocionar.")
        with st.expander("Exclusiones, incertidumbre, costes y atribución"):
            st.json({"exclusions": report["exclusions"], "unavailable_candidates": report["unavailable_candidates"],
                     "summary": rows, "limitations": report["limitations"]})
            st.dataframe(pd.DataFrame([r for r in report["periods"] if r["cost_bps"] == cost]), hide_index=True, width="stretch")
    else:
        st.info("El evaluador aún no ha guardado un informe para esta selección.")
    with st.expander("Método congelado y estado automático"):
        st.json(CONTRACT)
        st.caption("Método completo: docs/experiments/entry-context-v2.md. Dos candidatos, sin búsqueda de pesos sobre este histórico.")
        st.dataframe(pd.DataFrame([s for s in statuses() if s["family"] == "pipeline"]), hide_index=True, width="stretch")
elif section == "Macro, instituciones y opciones":
    macro = macro_summary()
    st.subheader("Tipos, curva y crédito")
    macro_rows = pd.DataFrame([{"serie": k, **v} for k, v in macro["series"].items()])
    display_macro = macro_rows.reindex(columns=["serie", "value_pct", "period_end", "status"]).rename(
        columns={"serie": "Serie", "value_pct": "Tipo %", "period_end": "Fecha del dato", "status": "Estado"})
    display_macro["Serie"] = display_macro["Serie"].replace({"nominal_2y": "Treasury 2 años", "nominal_10y": "Treasury 10 años",
        "real_10y": "Tipo real 10 años", "cp_aa_30d": "Papel comercial AA 30d", "cp_a2_30d": "Papel comercial A2 30d"})
    st.dataframe(display_macro, hide_index=True, width="stretch")
    macro_columns = st.columns(2)
    for column, key, label in zip(macro_columns, ("curve_10y_minus_2y_pp", "credit_cp_a2_minus_aa_pp"), ("Curva 10Y–2Y", "Crédito A2–AA")):
        value = macro[key]
        column.metric(label, f"{value:.2f} pp" if value is not None else "Sin dato verificable")
    rate_columns = st.columns(2)
    for column, name in zip(rate_columns, ("EFFR", "SOFR")):
        rate = macro["rates"].get(name)
        column.metric(name, f"{rate['value_pct']:.2f}%" if rate else "Sin dato")
    st.caption("Crédito de papel comercial a corto plazo; no es un spread de bonos. Revisiones conservadas desde la primera captura. "
               "La fecha efectiva y la actualización del feed no sustituyen la publicación inicial.")
    with st.expander("Publicaciones monetarias con fecha de la fuente"):
        st.dataframe(pd.DataFrame(macro["policy_releases"]), hide_index=True, width="stretch")
        st.dataframe(macro_rows, hide_index=True, width="stretch")
        st.json(macro["rates"])
    st.subheader("Posicionamiento institucional CFTC")
    institutions = institutional_summary()
    st.dataframe(pd.DataFrame(institutions["records"]), hide_index=True, width="stretch")
    st.caption("Posiciones semanales declaradas en futuros. Los cambios normalizados por interés abierto no son flujos de dinero ni operaciones en tiempo real.")
    st.subheader("Cadenas de opciones persistidas")
    coverage = options_coverage([t for t in get_watchlist() if not t.endswith("-USD")] + ["SPY", "QQQ"])
    st.dataframe(pd.DataFrame(coverage), hide_index=True, width="stretch")
    st.caption("Vencimientos de 20–60 días; filtros de spread, interés abierto y antigüedad. IV, skew y estructura temporal solo con liquidez suficiente. "
               "Griegas aproximadas con BSM europeo cuando hay spot, tipo y dividendo. No se infiere gamma de dealers.")
    with st.expander("Estado de fuentes y límites"):
        st.dataframe(pd.DataFrame(statuses()), hide_index=True, width="stretch")
        st.caption("Datos para investigación: 0% de peso direccional. La continuidad y el valor predictivo necesitan evidencia prospectiva.")
else:
    from src.research_lab import CONFIG, compare_strategies, historical_cohorts, prospective_cohorts
    st.caption("Experimento v1 conservado. Sus cohortes medias no incluyen una trayectoria diaria de drawdown.")
    source = st.radio("Fuente v1", ["Prospectiva v1", "Histórica v1"], horizontal=True)
    horizon = st.radio("Horizonte v1", ["1M", "3M"], horizontal=True)
    report = compare_strategies(prospective_cohorts() if source == "Prospectiva v1" else historical_cohorts(), horizon)
    st.dataframe(pd.DataFrame(report["summary"]), hide_index=True, width="stretch")
    with st.expander("Contrato y exclusiones v1"):
        st.json({"contract": CONFIG, "exclusions": report["exclusions"], "limitations": report["limitations"]})
