# Contrato congelado: entry-ranking-v1-research

Estado: investigación separada, sin promoción ni órdenes. El contrato se fijó antes de ejecutar la comparación. No cambia el champion ni Shorts v5. Implementación única en `src/research_lab.py`; una captura se acepta solo si su hash y su replay exacto coinciden.

## Hipótesis y datos

Ordenar de forma continua por momentum 12–1: `((1 + retorno_12m/100) / (1 + retorno_1m/100) - 1) * 100`. La exclusión del último mes se calcula como un cociente, no restando retornos. Exigir momentum positivo y precio por encima de MA200. No añadir pesos a calidad, opciones, flujos o macro sin validación separada.

Capturas nuevas: descargar tres años de precios ajustados; utilizar las últimas 253 sesiones anteriores a la fecha UTC de captura, excluyendo la barra diaria potencialmente incompleta de hoy. Los retornos utilizan 252 y 21 sesiones. No se cambia la ventana de precios del modelo oficial. Se guardan el universo, las métricas, la fecha de la última barra, el contexto público existente, la configuración, el ranking, la hora observada y el hash. Las series ajustadas pueden revisarse posteriormente. La hora observada permite saber cuándo la aplicación disponía de la captura; no se inventa un `known_at` histórico del proveedor.

El universo declarado es la watchlist actual, excluidos símbolos cripto `-USD` y SPY, que se utiliza como referencia. Los inputs ausentes se excluyen con motivo explícito, sin convertirlos en una señal bajista. La selección de la watchlist y las divisas continúan siendo limitaciones: no es un universo histórico libre de supervivencia ni una simulación con conversión FX.

Con N valores que tienen inputs válidos se fijan `ceil(0.20*N)` plazas. Se eligen como máximo esas plazas entre los valores que cumplen tendencia y momentum, con desempate alfabético. Cada plaza pesa `1/plazas`; las plazas vacías quedan en efectivo con retorno nominal cero. No se redistribuyen sus pesos entre los valores restantes. No hay apalancamiento, ventas en corto, instrucciones de cartera ni ejecución.

## Evaluación congelada

- Principal: un mes, 21 sesiones comunes. Secundaria: tres meses, 63 sesiones comunes.
- Entrada: cierre de la primera sesión negociable común estrictamente posterior a la fecha de decisión.
- Coste supuesto: 10 pb por ida y vuelta, proporcional al capital invertido, también aplicado a SPY. No incluye impuestos, impacto de mercado o FX.
- Comparadores: SPY, universo equiponderado, momentum sin filtro de tendencia y tendencia con efectivo. Cuando existe en toda la cohorte, también se muestra el ranking del Entry score guardado, etiquetado como diagnóstico; no se afirma que reproduzca la política del modelo oficial.
- El universo se determina con inputs, antes de leer resultados. Si falta el outcome de cualquier componente de ese universo, se excluye la fecha completa. No se eligen solo los supervivientes con resultados disponibles.
- Se exige el mismo benchmark, ventana de ejecución y salida, convención y coste. Vintages con retornos distintos de SPY para la misma ventana se rechazan; no se promedian para ocultar inconsistencias.
- Se recorren las fechas cronológicamente y se retiene la primera ventana; la siguiente debe comenzar después del final de la anterior. Se publican todas las exclusiones. Esto evita solapamientos mecánicos, pero no demuestra independencia estadística.
- Se publican media de retorno neto, exceso frente a SPY neto, exposición y acierto de las entradas seleccionadas. Son retornos de cohortes, no una curva patrimonial negociable ni alpha anualizado. Drawdown, Sharpe e intervalos de inferencia siguen ausentes mientras no exista una trayectoria y muestra adecuadas.
- Menos de diez cohortes se etiqueta «evidencia insuficiente». Alcanzar diez tampoco habilita promoción: este laboratorio nunca promociona automáticamente.

El histórico existente se une por ticker, fecha y versión exactos a las etiquetas registradas. La preferencia entre versiones es determinista por champion y versión, nunca por rentabilidad observada. Se presenta como retrospectivo no verificado. Los datos prospectivos tienen su propio almacén y se presentan por separado.

## Persistencia, operación y reversión

Tablas aditivas: `entry_research_snapshots` y `entry_research_outcomes`. La primera captura de cada fecha UTC queda congelada. Los resultados son inmutables por captura, ticker y horizonte; disponer de 1M no bloquea la llegada posterior de 3M. Los tickers retirados de la watchlist siguen recibiendo outcomes de sus capturas anteriores. Un fallo conserva los datos y el siguiente día vuelve a intentarse.

El mantenimiento existente de la aplicación intenta una captura al día mientras el servidor está activo. La nueva página también puede iniciar ese intento, sujeto al mismo límite durable. No se ha creado una automatización externa de Codex ni una fecha futura en el calendario. No existe garantía de captura si el servidor permanece apagado; las fechas omitidas no se reconstruyen como prospectivas.

Ejecución reproducible y local, sin proveedores:

```sh
.venv/bin/python scripts/run_strategy_comparison.py --output /ruta/informe.json
```

`--capture` solicita una descarga pública y una captura nueva. `--db` permite usar una base aislada. Volver al código anterior deja estas tablas sin uso y conserva todo el histórico oficial.

## Primer resultado observado

La comparación inicial produjo 9 cohortes no solapadas a 1M y 4 a 3M. El ranking obtuvo exceso medio de −1,804 pp a 1M y −0,686 pp a 3M frente a SPY neto. No justifica promoción. No se retocaron los pesos ni la regla después de observar este resultado. El informe reproducible completo está en `docs/audit/2026-09-24/STRATEGY_COMPARISON.json`.
