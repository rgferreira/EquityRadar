# Personal Equity Radar: revisión funcional, científica, técnica y de seguridad

> Actualización posterior: el plan autorizado se ha ejecutado. Ver [implementación, resultados y límites](IMPLEMENTACION_ES.md). Este informe conserva el diagnóstico previo.

Fecha: 24 de septiembre de 2026. Alcance solicitado: diagnóstico completo y propuesta de revamp realizable en una tarde. Objetivo confirmado por Rafa: superar al mercado, mejorar las entradas y combinar adecuadamente mercado, sector, compañía, flujos, opciones y política monetaria.

La aplicación se denomina PersonalEquityRadar en este repositorio. Se ha revisado HEAD c4801c8 **más el árbol de trabajo existente**, que contiene numerosos cambios anteriores a esta revisión. La base activa está fuera del repositorio; analizar solamente la copia de SQLite del proyecto habría producido conclusiones equivocadas.

## 1. Dictamen

La infraestructura permite un revamp pequeño. No recomiendo una reconstrucción de la aplicación. Hay tres prioridades:

1. **Eliminar el cuello de botella de SQLite y su causa de crecimiento.** Está demostrado y tiene una solución pequeña, aditiva y reversible.
2. **Reparar la lectura de la evidencia antes de elegir nuevos pesos.** La accuracy visible, la evaluación histórica y la fórmula realmente utilizada en vivo no representan exactamente el mismo objeto.
3. **Crear una comparación de estrategias por familias de señales, con un primer candidato sencillo y falsable.** La ambición institucional debe traducirse en selección de señales, control de redundancia, horizontes coherentes y evaluación económica; no en acumular indicadores.

Una tarde puede entregar una aplicación sustancialmente más ágil, una presentación correcta del estado del shadow y un laboratorio útil con una nueva estrategia de investigación. **No puede demostrar una mejora prospectiva de accuracy a tres meses ni implementar con rigor toda la infraestructura de datos de una gran gestora.**

Convención: «verificado» significa observado en código, consultas de solo lectura, pruebas o navegador; «hipótesis» identifica una propuesta de investigación; «pendiente» señala una comprobación no realizada.

## 2. Qué significa realmente el 88% del shadow

Modelo activo: coverage-aware-renormalized-v4-finra-freshness-live. Candidato: technology-unified-shorts-v5-shadow. Los gates de acciones reutilizan explícitamente la línea compatible v3–v5; BTC está excluido de esa transferencia.

| Medida, universo de promoción persistido | Línea de acciones v3–v5 | Solo v5 |
|---|---:|---:|
| Comparaciones tras selección por ticker y fecha | 1.440 | 340 |
| Instrumentos incluidos | 22 | 22 |
| Fechas distintas | 90 | 18 |
| Comparaciones con resultado 3M | 179 | 22 |
| Fechas con resultado 3M | 28 | 1 |
| Decisiones de entrada modificadas | 80 | 12 |
| Decisiones modificadas con resultado 3M | **0** | **0** |
| Indicador de avance | **88%** | **59%** |
| Gates verdes | **1/6** | **0/6** |

El indicador suma dos mitades: captura de cinco fechas con cambios y envejecimiento aproximado de esas cinco fechas sobre 92 días. No mide probabilidad de promoción, proporción de datos de todas las fuentes ni porcentaje de decisiones acertadas. La madurez real del resultado se calcula sobre 63 sesiones comunes del activo y benchmark; 92 días es solo una aproximación visual.

Las 179 comparaciones maduras proceden de reconstrucciones históricas manuales o sugeridas con tecnología y flujo diario no disponibles. Los dos modelos toman las mismas decisiones: diferencia de utilidad y accuracy igual a cero. **No son 179 oportunidades en las que el nuevo método haya demostrado fallar.** Las 80 decisiones relevantes siguen pendientes. El monitor prospectivo del live tampoco tiene todavía resultados 3M maduros.

Las primeras decisiones cambiadas de la línea v3 son de julio; las de v5 empiezan en agosto. El calendario de resultados debe depender de las sesiones bursátiles efectivas, no de forzar una fecha civil. Esta revisión no programa ninguna acción futura.

Además, **11 de las 41 fechas con cambios son fines de semana**. Contar fechas civiles distintas como observaciones independientes sobre retornos 3M solapados sobrestima la independencia. La vista de promoción agrupa por fecha, pero no llama al evaluador purgado; su intervalo usa media ±1,96 errores estándar entre fechas. El purgado del evaluador offline separa entrenamiento y prueba, pero tampoco elimina por sí mismo el solapamiento entre todos los resultados de prueba.

Acción propuesta: presentar arriba «0 cambios evaluables / 80 capturados; mejora todavía no estimable», seguido del avance temporal. Mantener el archivo original y añadir un diagnóstico por sesión y bloque temporal; cualquier nueva política de promoción debe quedar versionada y no reinterpretar silenciosamente el experimento anterior.

Evidencia: [model_tuning.py](../../../src/model_tuning.py), [model_registry.py](../../../src/model_registry.py), [evaluation.py](../../../src/evaluation.py). La pantalla Model tuning se comprobó también en Chrome, perfil Rafael.

## 3. Problemas del modelo y de su evaluación

### 3.1 La fórmula evaluada no coincide con toda la fórmula visible

La ruta básica pondera Technical/Valuation/Risk. Cuando hay análisis de industria, Dashboard y Company utilizan otra composición: calidad 25%, valoración relativa 30%, técnica 20%, riesgo 15% y analistas 10%. Después aplican positioning. El registro y el reproductor no describen/reproducen completamente esa bifurcación.

Prueba de replay sobre las predicciones del modelo activo:

- 577 reconstrucciones manuales y 317 sugeridas de la ruta básica: coincidencia exacta.
- **1.294 predicciones live con industria: discrepancia en el reproductor actual.**

Esto verifica un defecto de reproducibilidad. No demuestra que esos 1.294 scores sean numéricamente incorrectos; demuestra que la herramienta con la que se auditan no reproduce su cálculo y que el snapshot no contiene toda la información necesaria para reconstruir esa ruta.

Recomendación: conservar esos registros, identificar la limitación y capturar prospectivamente el desglose efectivo y la versión de la ruta. No reconstruir retrospectivamente los peers ni inventar su disponibilidad. Para el laboratorio nuevo, calcular y almacenar la salida con una función pura única.

### 3.2 La accuracy del Dashboard sigue siendo un diagnóstico legacy

La columna Overall decision accuracy usa lesson_summary/select_learning_observations. Se basa en utilidades derivadas de retornos absolutos, horizontes mezclados y selección de episodios. La nueva evaluación de promoción utiliza retornos relativos al benchmark. Las cifras no se deben interpretar como una misma probabilidad de acierto.

Reejecución del evaluador vigente sobre las reconstrucciones de la versión activa, excluyendo SPY/BTC-USD/SPCX: 793 entradas, 616 elegibles y 418 filas de prueba en 19 fechas.

| Política histórica | Accuracy agrupada por fecha | Utilidad diagnóstica media | Intervalo 95% de utilidad del evaluador vigente |
|---|---:|---:|---:|
| Modelo core registrado | 49,76% | +0,01% | −5,71% a +5,73% |
| Baseline técnico existente | 53,11% | +3,28% | −1,02% a +7,58% |
| Siempre Buy | 50,24% | +9,80% | +4,41% a +15,20% |

**Son diagnósticos retrospectivos seleccionados, no rentabilidad de una cartera ni evidencia prospectiva del live con industria.** Los intervalos heredan la limitación de dependencia temporal indicada arriba. El resultado justifica probar baselines simples y revisar la función objetivo; no justifica desplegar «siempre Buy».

La utilidad de Watch es siempre −abs(retorno relativo), aunque su accuracy puede ser positiva si el retorno cae dentro de ±3%. Wait recibe el negativo del retorno relativo, como una evaluación de rechazo. Esta función no simula fielmente el resultado de mantener efectivo ni los costes de una cartera. Optimizarla como si fuera P&L induce incentivos distintos del objetivo económico de Rafa.

La política base_score del evaluador vuelve a etiquetar el mismo entry_score: no constituye una ablación real de los componentes del modelo.

### 3.3 Algunas etiquetas quedan congeladas antes de completar horizontes

materialize_matured_prediction_labels excluye cualquier predicción que tenga ya una etiqueta. La reconstrucción puede guardar una etiqueta con 1M disponible y 3M vacío. Posteriormente esa predicción queda excluida de la maduración. Hay **124 etiquetas available de abril/mayo sin resultado 3M**, además de otros estados no disponibles que requieren distinguir falta de benchmark de errores recuperables.

La solución debe ser aditiva: nuevas observaciones por horizonte y fecha de evaluación, preservando las anteriores. No sobrescribir outcomes antiguos. También conviene disponer de un resultado prospectivo secundario a 1M para aprender antes, manteniendo 3M como horizonte confirmatorio del experimento vigente.

### 3.4 El candidato actual tiene poca capacidad de cambiar la política

El shadow añade hasta ±5 puntos de Technology y ±2 de Shorts al score existente. Solo cambia etiquetas cerca de sus fronteras. En la línea evaluada cambia 80/1.440 comparaciones, aproximadamente 5,6%; no cabe esperar que transforme radicalmente la accuracy global sin alterar la selección de entradas.

Technology reutiliza crecimiento, márgenes y balance, información que también participa en calidad e industria. Puede duplicar exposición a las mismas características. FINRA diario mide volumen de ventas cortas comunicado a FINRA, no apertura neta de posiciones institucionales ni todo el volumen del mercado. [FINRA explica estas limitaciones](https://www.finra.org/rules-guidance/notices/information-notice-051019).

### 3.5 Opciones: datos aprovechables y una incoherencia existente

Se conservan 1.680 snapshots diarios de positioning; 1.600 contienen put/call OI. El control actual de continuidad admite 23 de 26 instrumentos para investigación. Esa cobertura **no certifica liquidez, griegas, una política estable de strikes ni valor predictivo**.

El proveedor resume las tres primeras expiraciones y guarda agregados de volumen, OI e IV. No persiste una cadena completa con strikes, DTE, bid/ask y griegas. No permite reconstruir gamma histórica ni atribuir posiciones a dealers.

La especificación options-positioning-v1 exige investigación antes de nuevas influencias operativas; sin embargo, los ratios put/call ya entran indirectamente en positioning_scores y en sus ajustes live. Una prueba sintética, manteniendo lo demás constante, cambia Entry de +0,1 a −0,1 y Exit de −0,1 a +0,2 al variar esos ratios. La gate de cobertura es informativa: no gobierna esa ruta preexistente. Hay que documentarla y medir su contribución por separado.

### 3.6 Hallazgos de julio que siguen siendo relevantes

| Hallazgo original | Estado actual |
|---|---|
| Learning contamina scores con pocas observaciones | Corregido en la política operativa: DIAGNOSTIC_ONLY. Persisten métricas legacy muy visibles. |
| No existen known_at ni predicciones inmutables | Parcialmente corregido: existen controles y registros. Persisten limitaciones de snapshots y replay de industria. |
| No hay benchmark ni evaluador purgado | Implementados, con limitaciones estadísticas y de conexión a los gates. |
| Missing se convierte en neutralidad numérica | Mejorado en el core por renormalización; industria aún aproxima componentes sin evidencia a 50. |
| Mezcla de divisas en acciones de posición | Sigue aplicando en Dashboard/Company: shares × precio local para pesos. Portfolio sí utiliza conversión. No se consultaron posiciones privadas para probarlo. |
| Exceso de tareas en páginas y llamadas a proveedores | Sigue aplicando; ahora se suma el crecimiento de la tabla legacy. |

## 4. Estrategia propuesta: selección relativa con contexto y timing separado

Las fuentes públicas de grandes gestoras describen combinación de señales, validación cuantitativa y construcción de carteras con riesgo controlado. No publican un conjunto de pesos replicable para esta watchlist. [BlackRock, proceso sistemático](https://www.blackrock.com/us/individual/investment-ideas/systematic-investing). La evidencia amplia sobre [momentum](https://www.aqr.com/Insights/Research/Journal-Article/Fact-Fiction-and-Momentum-Investing) y [calidad](https://www.aqr.com/Insights/Research/Working-Paper/Quality-Minus-Junk) orienta hipótesis, pero no valida la implementación concreta de PersonalEquityRadar.

### 4.1 Función de cada familia

| Familia | Lo que existe | Uso propuesto | Alcance de una tarde |
|---|---|---|---|
| Mercado | Precios y benchmark de outcomes; sin régimen explícito | Tendencia, amplitud del universo y volatilidad como contexto de riesgo | Reutilizar precios disponibles; amplitud de watchlist claramente etiquetada, sin llamarla amplitud del mercado |
| Sector | Peers, valoración/calidad relativa; no rotación sectorial | Distinguir fortaleza de sector de fortaleza específica de la empresa | Reutilizar clasificación/peers actuales; sector-vs-benchmark solo con serie disponible y mapping explícito |
| Micro / fundamentales | Calidad, crecimiento, balance, valoración y revisiones | Selección de oportunidades; comparar dentro de sectores y evitar duplicaciones | Descomponer los cálculos existentes y capturar evidencia prospectiva completa |
| Precio / entradas | MAs y signos de retornos, con saturación frecuente | Ranking continuo de momentum, tendencia y distancia al punto de entrada | Nuevo ranking 12–1 meses con filtro de tendencia; baseline operativo del laboratorio |
| Flujos | FINRA, propiedad institucional, insiders, congresistas | Confirmación, concentración y presión; distinguir stock de posiciones de flujo de órdenes | Auditoría y tarjetas comparables; nuevas contribuciones solo en investigación |
| Opciones y griegas | Ratios agregados e IV, cobertura diaria suficiente en parte del universo | IV relativa y cambios de ratios para investigación de timing/riesgo | Diagnóstico con datos existentes; cadena contractual y griegas quedan fuera del compromiso de seis horas |
| Política monetaria / crédito | No hay un adaptador de régimen implementado | Sorpresas monetarias, tipos reales, curva y spreads; contexto y riesgo de evento | Diseñar contrato/fuente y mostrar ausencia explícita. Integración histórica con vintages: siguiente trabajo |
| Riesgo y cartera | Volatilidad, drawdown, concentración y contabilidad | Separar calidad de señal, riesgo asumido y encaje de posición | Mostrar por separado; corregir coherencia FX en una tarea focalizada antes de confiar en acciones multi-divisa |

La política monetaria debe atender a sorpresas respecto a expectativas; «bajan tipos = comprar» pierde información esencial. [Investigación de Bernanke y Kuttner, Federal Reserve Bank of New York](https://www.newyorkfed.org/research/staff_reports/sr174.html). Para historia macro revisable se necesitarían vintages de publicación, no la última serie corregida.

Tampoco asumiría que call OI equivale a dealers largos o que put OI implica dealers cortos. Los estudios de Cboe utilizan información de posiciones/actividad más detallada para estimar exposición neta. [Cboe, posicionamiento e impacto de 0DTE](https://www.cboe.com/insights/posts/0-dt-es-decoded-positioning-trends-and-market-impact). Las griegas son sensibilidades, no pronósticos direccionales por sí mismas.

### 4.2 Primer candidato implementable

Nombre propuesto: **entry-ranking-v1-research**. Será una comparación local separada, sin sustituir el champion ni mezclar snapshots con Shorts v5.

- Universo: acciones comparables del universo congelado al inicio; ETFs de referencia y cripto fuera de esta prueba. La watchlist histórica tiene sesgo de selección/supervivencia: el informe lo conservará explícitamente.
- Ranking inicial: momentum 12–1 meses, calculado como (1 + retorno 12M) / (1 + retorno 1M) − 1, usando unidades decimales. Evita sumar varias señales binarias de momentum muy relacionadas. Si falta historia suficiente, el activo no recibe ranking elegible.
- Filtro inicial de investigación, fijado antes de mirar resultados: precio por encima de MA200 y momentum 12–1 positivo. Selección del 20% superior del universo elegible, con igual ponderación en una simulación teórica; sin órdenes, apalancamiento ni posiciones cortas. Si faltan candidatos, se conserva efectivo en las plazas vacantes.
- Mercado, sector, calidad, valoración, revisiones, flujos y opciones se muestran al lado como explicaciones y posibles objeciones. En esta primera comparación **no reciben un peso direccional inventado** cuando su evidencia incremental aún no existe.
- Las siguientes ablaciones predefinidas son core + calidad/valor, core + revisiones y core + contexto de flujo/opciones. El máximo número de variantes queda registrado; no se ejecuta una búsqueda abierta de combinaciones.
- Para una futura combinación de familias admitidas, el punto de partida de investigación será igual peso por familia independiente y normalización dentro de sector; ningún reparto se presentará como «óptimo institucional». Los pesos solo se moverán tras comparar contribución fuera de muestra, estabilidad, correlación y costes. Mercado y riesgo se evaluarán además como filtros/exposición, no como votos intercambiables con fundamentales.

El candidato de una tarde sirve para contestar si una política de selección simple merece más trabajo y para empezar a capturar lo necesario para una versión multifactor. No permite declarar ya mejor al sistema.

### 4.3 Evaluación mínima que corresponde al objetivo de Rafa

1. Comparar benchmark, universo equiponderado, momentum simple, live realmente calculable y candidato sobre el mismo conjunto, fecha y regla de ejecución. No usar el score final como falso baseline de ablación.
2. Métrica primaria del laboratorio: exceso de retorno neto de las entradas seleccionadas frente a benchmark; accuracy de entradas y número/cobertura de señales como métricas complementarias.
3. Añadir pérdida media de los fallos, peor resultado, rotación y drawdown cuando exista la trayectoria necesaria. No deducir drawdown de retornos finales únicamente.
4. Mantener la referencia actual de 10 pb y una sensibilidad a 25 pb, con costes ligados a cambios de exposición en la simulación. Es un supuesto de investigación, no una medición del coste real del broker.
5. Señal de entrada evaluada a 1M y confirmación a 3M; 5D/10D solo exploratorios para timing de flujos si hay datos suficientes. No acortar el gate actual para fabricar una promoción.
6. Agrupar por sesión de ejecución, purgar train/test, usar bloques temporales o ventanas no solapadas para incertidumbre y reservar un periodo prospectivo. Los backtests sobre fechas elegidas por eventos no son holdout intacto.
7. Registrar variantes y resultados negativos. La selección entre muchos backtests infla la aparente evidencia; el [Deflated Sharpe Ratio de Bailey y López de Prado](https://www.davidhbailey.com/dhbpapers/deflated-sharpe.pdf) formaliza una parte de ese problema. No incorporaría una plataforma estadística completa esta tarde.

## 5. Rendimiento: causa demostrada y arreglo probado aisladamente

La base activa ocupa aproximadamente **1.934 MB**. La tabla legacy_outcome_observations ocupa **1.841 MB**, con **16.696.417 filas**. No tiene índice para la búsqueda de último resultado por ticker/fecha/versión.

get_backtest_runs materializa en cada llamada un GROUP BY sobre toda esa tabla para obtener MAX(id). EXPLAIN QUERY PLAN confirma SCAN y una tabla temporal para agrupación. Dos lecturas midieron 13,160 s y 12,948 s. Dashboard llama a esa consulta directamente y de nuevo al decidir si refrescar outcomes; varios módulos y páginas también la utilizan.

La causa de crecimiento está en la ruta de refresco: recorre las versiones de backtest y update_backtest_outcomes añade filas para todas las versiones de ese ticker/fecha; no comprueba si los valores son idénticos. Además, una predicción pendiente a partir de 75 días puede mantener label_due activo y relanzar refrescos aunque su horizonte 3M no haya madurado. El código limita concurrencia, pero esa rama no impone por sí sola una ejecución al día.

Experimento de solo lectura de producción: crear una proyección TEMP en memoria con el último resultado de cada clave.

| Prueba aislada | Resultado |
|---|---:|
| Claves resumidas | 1.800 |
| Construcción inicial | 12,069 s |
| Consulta original | 12,418 s |
| Consulta usando la proyección | **0,029 s** |
| Filas devueltas | 2.531 |
| Comparación de todas las columnas y filas | **Exactamente iguales** |

La mejora de la consulta es superior a 400 veces en este experimento; **no es una medición de mejora de toda la página ni de p95 en producción**. Prueba que no es necesario cambiar el contenido para eliminar buena parte del bloqueo.

Solución preferida: tabla derivada persistente de últimos resultados, con clave única y actualización transaccional al añadir una observación; backfill una sola vez y marca de migración. Añadir idempotencia y registro de último intento de refresco. Mantener íntegra la tabla histórica. Un índice por sí solo seguiría recorriendo millones de entradas si se conserva la agregación global.

Otros costes verificados por código:

- Dashboard descarta el snapshot de arranque cuando supera 15 minutos y puede bloquear esperando proveedores; limpia globalmente la caché al refrescar.
- Company consulta precios de todas las posiciones para calcular el peso de una empresa; la latencia crece con el conjunto, incluso para una ficha.
- Portfolio descarga historia máxima en serie antes de mostrar la valoración.
- Los historiales de precios usan LRU sin TTL: pueden estar indefinidamente obsoletos hasta invalidación, a la vez que las invalidaciones amplias penalizan navegación.
- Operations lee todas las transiciones de proveedores y reconstruye alertas en la ruta de render.
- Tabs y expanders ejecutan contenido no visible por defecto. Streamlit 1.59.1 ya instalado permite control de estado para carga bajo demanda; no hace falta migrar de framework. [Documentación de tabs](https://docs.streamlit.io/develop/api-reference/layout/st.tabs).
- El gate común del shell es redundante, pero su lectura y preparación medidas sumaron unas centésimas; no es el cuello principal encontrado.

## 6. Jerarquía de información por página

| Página | Problema observado | Cambio acotado |
|---|---|---|
| Dashboard | Mezcla señales, piloto, investigación retrospectiva y descubrimiento; trabajo histórico en ruta principal | Arriba cambios relevantes y oportunidades; botones/freshness compactos. Piloto, WhaleSeeker y archivo bajo demanda. |
| Company | Ficha pesada con gauges, muchos diagnósticos y carga de todas las tabs | Arriba decisión, horizonte, precio/freshness, tres motivos y dos riesgos; detalles técnicos y learning debajo. |
| Portfolio | Importación, alta y edición de lotes preceden a valoración | Valoración y exposición primero; operaciones de registro en una única sección bajo demanda. |
| Model tuning | Cabecera, tres tarjetas de versiones y tutorial expandido ocupan la primera pantalla | Estado 0/80, mejora estimable/no estimable y obstáculo primero; versiones y guía plegadas. |
| Operations | Tablas extensas y alertas calculadas al abrir | Fallos activos y último refresco primero; historial limitado/paginado y alertas materializadas. |
| WhaleSeeker | Descubrimiento público puede distraer de decisiones propias | Conservar como investigación secundaria; no presentarlo como flujo institucional en tiempo real. |
| Journal | No se ha identificado un cuello propio dominante | Conservar el flujo; no rediseñar en esta tarde. |
| Watchlist | Gestión, no decisión | Mantener como configuración secundaria. |
| Scenario lab | Herramienta ocasional con dependencias de precios | Ejecutar el escenario solicitado; no precalcularlo para navegar. |

Verificación visual real realizada en Model tuning. El resto se revisó en código y con la suite AppTest, principalmente de estados vacíos/sintéticos; no se certificó visualmente todo el contenido real de todas las páginas ni se extrajeron datos de cartera o Journal.

## 7. Seguridad

Se revisaron dependencias instaladas, análisis estático de app/src/pages, rutas de red, guardado de secretos, import/export, backups y límite de exposición. No se realizaron ataques activos contra proveedores ni un pentest de la red ZeroTier.

| Área | Resultado | Prioridad/acción |
|---|---|---|
| Dependencias | pip-audit: 7 entradas en 3 paquetes; 6 advisories únicos porque pip aparece duplicado | Actualizar y probar GitPython 3.1.60, pip ≥26.2 y soupsieve 2.9.0; verificar nuevamente la auditoría |
| GitPython 3.1.59 | Tres avisos; uno permite ejecución al usar repositorios hostiles bajo condiciones específicas | Prioridad alta de actualización; no se demostró una vía explotable desde la UI de esta app. [Advisory del mantenedor](https://github.com/gitpython-developers/GitPython/security/advisories/GHSA-239g-whfq-7xj9) |
| Red | Listener observado exclusivamente en IPv4 de ZeroTier, sin 0.0.0.0 ni bind LAN general | Mantener. La app no tiene autenticación propia: la confianza recae en los miembros/reglas de ZeroTier, que no se auditaron |
| Secretos | .env y .env.alerts con modo 0644; no versionados. Escaneo de patrones comunes en árbol versionado sin coincidencias | Endurecer a 0600. El acceso efectivo depende también de directorios padre/ACL; no se declara fuga observada |
| Base activa | Archivo 0600 y directorio 0700 | Correcto como protección local por permisos |
| Backups | 56 archivos observados con modo 0644 y 2 con 0600; directorio 0755 | Uniformar archivo 0600/directorio 0700 y revisar retención sin borrar en esta tarea |
| Exportación SQLite | Portfolio ofrece DATABASE_PATH.read_bytes() pese a operar en WAL | Usar la API de backup consistente que ya existe; la copia del archivo principal puede omitir cambios del WAL |
| Errores de proveedores | Congress sanitiza excepciones; FMP genérico conserva rutas de error menos estrictas | Centralizar mensajes seguros sin URL con credenciales; no se imprimieron claves ni se acreditó una fuga actual |
| SQL/URLs | Bandit: 0 altas, 14 medias y 9 bajas | Las alertas SQL revisadas usan columnas de código y parámetros ligados; son falsos positivos en esas rutas. Revisar/adaptar validación HTTPS de FMP genérico; no se atribuye una inyección demostrada |
| CSV y contenido | Exporta texto de usuario; no hay defensa específica contra fórmulas de hoja de cálculo | Añadir sanitización al exportar celdas peligrosas y límites de tamaño; prioridad posterior al rendimiento |
| Almacenamiento y entorno | Las copias están bajo Documents/work/backups | Pendiente auditar ACL, cifrado/retención y posible sincronización del directorio; no se afirma que sea público |

La auditoría de dependencias de Phase 3.92 quedó anticuada: su afirmación de «sin vulnerabilidades conocidas» ya no aplica al entorno de hoy. [Advisory de soupsieve](https://github.com/facelessuser/soupsieve/security/advisories/GHSA-j934-xhv5-fg8f). Un escaneo sin hallazgos altos de Bandit no equivale a certificar seguridad completa.

## 8. Plan de una tarde: seis horas de implementación

Son duraciones de trabajo, no una reserva de calendario ni una fecha de ejecución. Propuesta de tres cambios revisables, con el laboratorio separado de mejoras operativas.

| Bloque | Tiempo | Entrega concreta |
|---|---:|---|
| A. SQLite y refrescos | 90 min | Proyección de últimos outcomes, idempotencia, evitar refresco repetido y lectura repetida en navegación |
| B. Evidencia y contratos | 60 min | Estado correcto de madurez/accuracy; marcar replays limitados; capturar contrato completo del nuevo laboratorio y su salida; especificar reparación aditiva de etiquetas |
| C. Estrategia de investigación | 90 min | Ranking 12–1 + tendencia, baselines, informe comparable y tarjeta de familias reutilizando datos locales; captura nueva separada |
| D. UX y carga bajo demanda | 60 min | Dashboard/Company/Portfolio/Model tuning: resumen primero y secciones secundarias condicionales; snapshot obsoleto visible con aviso mientras refresca |
| E. Seguridad inmediata | 20 min | Dependencias afectadas y permisos; usar backup consistente para exportación si cabe en el bloque |
| F. Validación y entrega | 40 min | Tests, compile/import, benchmark, Chrome desktop/móvil y reinicio/verificación ZeroTier |
| **Total** | **360 min** | **Aplicación más rápida y comparación de estrategia reproducible, sin promoción automática** |

Alcance explícito del bloque B: resuelve la presentación y evita prometer replay donde no existe. La migración completa de etiquetas por horizonte y la rehabilitación de todo el histórico no se esconden dentro de 60 minutos: requieren una tarea posterior propia. El nuevo laboratorio no dependerá de mutar ese histórico.

Alcance explícito del bloque C: el cálculo de ranking y sus baselines se implementa; solo se evalúan retrospectivamente las fechas con inputs realmente disponibles. Las familias sin historia verificada se muestran/capturan prospectivamente. Si el subconjunto no permite una comparación económica honesta, la salida será «evidencia insuficiente» con cobertura y ranking actual, no un backtest fabricado.

Si una incidencia consume el margen, el orden de reducción será integraciones nuevas, tarjetas secundarias y refinamiento visual. No se sacrifican idempotencia, equivalencia de consultas, aislamiento de modelos ni las comprobaciones del servicio para anunciar más señales.

### Archivos y aceptación

| Cambio | Archivos previstos | Demostración de aceptación |
|---|---|---|
| Proyección y deduplicación | src/data/database.py; src/data/backtest_refresh.py; tests/test_database.py; tests/test_backtesting.py | Mismas filas/resultados; segundo refresco idéntico no añade observaciones; actualización real añade evidencia y actualiza proyección atómicamente |
| Ruta de render rápida | pages/1_Dashboard.py; src/data/dashboard_refresh.py; src/data/market_data.py; src/operations.py | Abrir/ordenar no dispara descarga completa; dato obsoleto tiene fecha y aviso; fallo de proveedor conserva la última vista |
| Estado científico | src/model_tuning.py; pages/5_Model_Tuning.py; tests/test_model_tuning.py | 88% no aparece como calidad/probabilidad; v5 y línea compatible distinguibles; fechas civiles no se presentan como independencia demostrada |
| Laboratorio | Nuevos src/research_lab.py y scripts/run_strategy_comparison.py; tests/test_research_lab.py; docs/experiments/entry-ranking-v1.md | Fórmula congelada, replay exacto de nuevos snapshots, casos de datos ausentes, igualdad de universo/costes, ningún cambio en champion/Shorts v5 |
| Jerarquía y lazy load | pages/1_Dashboard.py; pages/2_Portfolio.py; pages/3_Company.py; pages/5_Model_Tuning.py; tests/test_ui_regression.py | Información decisional en primera pantalla; tabs/expanders cerrados no ejecutan trabajo pesado |
| Seguridad | requirements.txt; tests/test_phase_392_security_contract.py; src/backup.py y exportación de Portfolio si entra | Auditoría actualizada, permisos privados, exportación coherente con WAL, sin ampliación de red |

Objetivos de rendimiento a comprobar, no resultados ya alcanzados: consulta de backtests <250 ms en caliente; primer contenido útil cacheado <2 s; navegación cacheada p95 <3 s en una muestra repetida y acotada. Medir arranque frío y disponibilidad de datos frescos por separado. No prometer que un proveedor externo responda en ese plazo.

### Riesgos, supuestos y reversión

- Se presupone mantener Python, Streamlit, SQLite y el acceso privado por ZeroTier. No hacen falta servicios cloud, brokers ni ML opaco.
- La migración crea una proyección derivada; no elimina los 16,7 millones de registros. Requiere un backfill y una ventana breve de escritura controlada. La copia de seguridad se verifica antes.
- La proyección se reconstruye desde el archivo inmutable; la app vuelve al lector anterior si se revierte el cambio. Las nuevas tablas pueden permanecer sin uso. La idempotencia no debe suprimir revisiones reales de outcomes.
- El nuevo ranking es una hipótesis con riesgo de momentum y concentración sectorial. No se aplican automáticamente sus entradas al modelo oficial ni a la cartera.
- No se cambian retrospectivamente umbrales, factores, fechas known_at ni outcomes para mejorar cifras. No se abre Credit Stress 3.91 como parte implícita de este trabajo.
- El árbol de trabajo contiene cambios previos: la implementación deberá aislar su parche y preservar ese estado. No usar reset/revert global del repositorio como rollback.
- Tras cambios de módulos/páginas: ejecutar el restart del controlador macOS y exigir Dashboard renderizado, ruta ZeroTier verificada y listener en la IPv4 activa de ZeroTier. Comprobar móvil; un HTTP 200 aislado no es aceptación.

## 9. Trabajo posterior que merece su propia decisión

1. Etiquetas aditivas por horizonte, sesiones canónicas e inferencia por bloques; coherencia económica entre accuracy y cartera simulada.
2. Replay completo de las rutas operativas futuras y trazabilidad de peers, industria y fuente de cada componente.
3. Régimen macro con fuentes oficiales y vintages, curva, tipos reales y crédito; separado de la hipótesis Shorts actual.
4. Cadena de opciones persistida con política fija de liquidez/strikes/DTE antes de griegas, skew o term structure. Una fuente de flujo institucional real requeriría confirmar disponibilidad/licencia.
5. Auditoría económica FX de Dashboard/Company y coherencia de position actions.
6. Retención/archivo y posible reducción física del histórico redundante, solo mediante un proyecto reversible aparte. No borrar investigación legacy esta tarde.
7. Pentest acotado de superficie autenticada/red, miembros y reglas ZeroTier, ACL y recuperación completa.

## 10. Validación realizada durante esta revisión

- Suite completa: **305 tests superados**, 92,44 s, un warning de deprecación de yfinance. Se indicó una base de prueba temporal; la suite usa fixtures sintéticas. Muchos AppTests son de estado vacío: no demuestran rendimiento con una base de 1,9 GB.
- Compileall de app/src/pages/scripts/tests: correcto, bytecode dirigido a temporal.
- Importación de los **59 módulos descubiertos bajo src**: correcta.
- pip check: sin incompatibilidades. git diff --check: sin errores en el estado revisado.
- pip-audit: 62 distribuciones revisadas, 7 entradas/6 advisories únicos en 3 paquetes. Herramientas instaladas en un entorno temporal, sin actualizar el entorno de la aplicación.
- Bandit: 15.085 líneas revisadas; 0 altas, 14 medias, 9 bajas; evaluación manual de contexto descrita arriba.
- Consultas SQLite en modo solo lectura y experimento TEMP con producción adjunta como solo lectura; resultados completos idénticos.
- Replay de registros actuales y diagnóstico de baselines, agregando resultados sin publicar datos de posiciones, cantidades, costes, cash flows o texto del Journal.
- Inspección de Model tuning en Chrome Rafael y comprobación del listener ZeroTier. No se reinició producción porque esta tarea entrega una revisión y un plan, no cambios de aplicación.

Entregables de esta tarea: este informe y [evidencia agregada de investigación/rendimiento](EVIDENCIA_AGREGADA.json). No se ha implementado el revamp ni modificado la política de decisión.
