# Revamp implementado — 24 de septiembre de 2026

Se ha ejecutado el plan autorizado de una tarde sobre el árbol de trabajo existente, conservando sus cambios previos. El servicio está arrancado y verificado. La mejora operativa está medida; **no hay una mejora predictiva demostrada ni una promoción del nuevo ranking**.

## Qué cambia para el usuario

- **Dashboard:** primero posiciones y oportunidades; flujos divulgados y comparación piloto quedan en una sección opcional. Utiliza la última vista completa aunque haya envejecido, con fecha y aviso, mientras actualiza precios en segundo plano. El archivo de simulaciones se calcula al abrirlo. «Overall decision accuracy» pasa a «Legacy episode success» para no confundir ese diagnóstico con probabilidad de acierto futuro.
- **Company:** decisión antes del gráfico detallado; gráfico de precios/flujo y pestañas secundarias bajo demanda. La cotización extendida se obtiene de caché con actualización en segundo plano. El éxito histórico se identifica como diagnóstico legacy de retorno absoluto.
- **Portfolio:** valoración primero, gestión de transacciones al final; carga acotada y paralela de históricos. La exportación SQLite usa una copia consistente, incluidos los cambios del WAL.
- **Model tuning:** primera pantalla con 340 capturas v5, cero cambios maduros, 59% de captura/envejecimiento de v5 y 88% de la línea compatible v3/v5, en la verificación realizada. Se distingue ese progreso de la probabilidad de promocionar. Guía y versiones quedan plegadas; las pestañas cargan al seleccionarlas. Los umbrales y cálculos de los gates no cambian.
- **Entry research:** nueva página separada con ranking continuo 12–1 y filtro MA200, plazas teóricas equiponderadas y efectivo cuando no se cubren. Incluye contexto de mercado, sectores y cobertura de posicionamiento, sin asignar pesos nuevos a evidencia no validada. Compara con SPY y baselines bajo un contrato fijo.
- **Operations:** consulta acotada de las últimas 500 transiciones para detectar recuperaciones de proveedores; conserva las alertas ya guardadas.

## Rendimiento comprobado

La causa principal era volver a agrupar 16,7 millones de observaciones legacy en cada lectura. Se añadió una proyección pequeña del último registro por ticker/fecha/versión, mantenida por un trigger. No se borró el archivo histórico.

| Comprobación | Resultado |
|---|---:|
| Consulta original con 2.531 filas | 14,566 s |
| Backfill de la proyección, una vez | 13,168 s |
| Cinco lecturas posteriores al cambio | 22–58 ms |
| Cinco lecturas al terminar | 22–25 ms |
| Comparación completa antes/después de migrar | Las 2.531 filas eran idénticas |

La escritura de outcomes es ahora idempotente y atómica: repetir los mismos valores no crea filas; una revisión real sí añade evidencia. Un horizonte ausente no borra uno observado. El worker procesa una vez cada ticker/fecha, reutiliza históricos y comparte entre procesos un límite durable diario de intentos, incluidos fallos. Se detiene así el crecimiento por reintentos y multiplicación entre versiones.

La caché persistente almacena precios públicos por ticker y periodo. Una respuesta caducada se sirve con su fecha mientras se actualiza; un fallo conserva la anterior. Se limita el paralelismo y los reintentos. La actualización explícita continúa disponible.

Medición final en Chrome Rafael, tres navegaciones por pantalla con caché preparada, desde navegación hasta una sección útil renderizada:

| Pantalla | Mediana | Intervalo observado |
|---|---:|---:|
| Dashboard | 1,485 s | 0,944–2,152 s |
| Portfolio | 1,766 s | 1,555–2,976 s |
| Company | 1,783 s | 1,471–1,872 s |
| Model tuning | 1,015 s | 0,906–1,279 s |
| Entry research | 0,866 s | 0,731–2,219 s |

p95 global por rango más próximo: **2,976 s**, 15 muestras, cero excepciones de página. La medición incluye la automatización de navegador. Es una muestra pequeña, no un SLA: el objetivo de contenido útil <2 s no se cumplió en todas las muestras y no se han medido arranques con proveedores fríos. El objetivo de consulta <250 ms sí se cumple con amplio margen.

## Resultado funcional y científico

La regla nueva quedó fijada antes de calcular resultados. El histórico utilizable proporciona **9 cohortes no solapadas a 1M y 4 a 3M**. El exceso medio del ranking frente a SPY, con el coste supuesto aplicado, es **−1,804 pp a 1M y −0,686 pp a 3M**. No respalda una promoción. No se cambiaron pesos o umbrales tras observarlo.

Se exige el mismo universo determinado por inputs, benchmark, ventana de ejecución y salida, y costes. Falta de outcomes de cualquier miembro o discrepancias entre vintages excluyen la fecha completa. No se seleccionan solo los valores con resultados disponibles. Se publican causas de exclusión y comparadores; las medias de cohortes no se presentan como rentabilidad anualizada o una curva negociable.

Hay **una captura prospectiva congelada**, con **22 valores clasificables y uno excluido por inputs ausentes**. Su replay es exacto. Todavía no tiene outcomes futuros maduros. El mantenimiento de la aplicación intenta una captura diaria mientras el servidor está activo; cada horizonte 1M/3M tiene un registro separado, de modo que 1M no bloquea la llegada de 3M. Las capturas anteriores siguen recibiendo etiquetas aunque un ticker salga de la watchlist. No se ha creado una automatización externa de Codex ni una cita futura.

El contexto de mercado y las familias existentes están visibles, pero la cobertura no se confunde con actualidad o capacidad predictiva. Los agregados de opciones no equivalen a una cadena de griegas; los disclosures políticos no equivalen a flujo institucional actual. Política monetaria, sorpresas, crédito y nuevas señales sectoriales necesitan contratos de disponibilidad e historia propios. No se simula esa información con valores neutros ni se inventa un `known_at`.

Contrato y reproducción: [entry-ranking-v1.md](../../experiments/entry-ranking-v1.md). El CLI funciona sin red por defecto; `--capture` solicita precios públicos. La evaluación de históricos no verificados se mantiene separada de las capturas nuevas.

## Seguridad inmediata

- GitPython actualizado a 3.1.60, soupsieve a 2.9 y pip a 26.2. `pip check` correcto. `pip-audit` sobre las 61 distribuciones del entorno: **cero vulnerabilidades conocidas** en la ejecución realizada.
- `.env`, `.env.alerts` y los backups existentes tienen permisos privados; directorio de copias 0700 y archivos 0600. Las nuevas copias y manifiestos se generan con esos permisos.
- Exportación de SQLite mediante API de backup, probada con transacciones confirmadas aún en WAL.
- Adaptador FMP genérico limitado al origen HTTPS oficial, endpoints acotados y respuestas de hasta 2 MiB. Los errores mostrados no incluyen URLs o cuerpos con claves. Prueba sintética de redacción incluida.
- Bandit: 0 altas, 15 medias y 12 bajas. El nuevo aviso medio corresponde a SQL compuesto exclusivamente con nombres de columnas constantes y valores ligados; no se introduce entrada de usuario en identificadores. El resto conserva las limitaciones de la revisión anterior. No se declara certificación de seguridad.
- Listener comprobado únicamente en `10.147.17.69:8501`. El controlador ha verificado ruta ZeroTier y Dashboard renderizado tras el reinicio final.

## Pruebas, integridad y alcance

**322 pruebas pasan**, con una advertencia de deprecación de yfinance. Suite final con base aislada. Compileall correcto e importación de los 61 módulos de `src` correcta. `git diff --check` sin errores.

Pruebas nuevas: escrituras concurrentes idempotentes, revisión real, migración y escritores de la versión anterior, límite diario persistente, caché obsoleta no bloqueante y fallback, copia con WAL, errores FMP sin credenciales, ranking con datos ausentes, efectivo, costes, igualdad de universo, exclusión de solapamientos, replay/hash, captura diaria inmutable y llegada separada de horizontes para valores retirados.

Verificación en Chrome: cinco pantallas a 390×844, sin desbordamiento horizontal del documento ni excepciones. Gráfico diferido de Company y cuatro pestañas secundarias de Model tuning abiertos y comprobados. Se restauró el viewport normal. No se publicaron capturas ni contenidos de posiciones, transacciones o Journal. La prueba móvil es de ancho de navegador; no se afirma una prueba física en iPhone.

Comparación contra la copia previa: todos los registros originales de `backtest_runs` (2.531), `prediction_snapshots` (3.235), `prediction_input_snapshots` (2.548), `outcome_label_observations` (1.873) y `shadow_decision_snapshots` (3.010) permanecen idénticos. El registro de modelos completo también permanece idéntico. No se cambiaron champion, Shorts v5, factores, umbrales ni decisiones oficiales.

Cambios de código agrupados para revisión, sobre el estado previo del usuario:

| Grupo | Archivos |
|---|---|
| Almacenamiento y seguridad | `src/data/database.py`, `src/data/backtest_refresh.py`, `src/backup.py`, `src/data/fmp.py`, `requirements.txt`; tests de proyección, backup, fundamentales y seguridad |
| Caché, presentación y ciencia | `src/data/price_cache.py` nuevo, `src/data/market_data.py`, `src/data/dashboard_refresh.py`, `src/model_tuning.py`; páginas Dashboard, Portfolio, Company, Model tuning y Operations; tests de caché, tuning, piloto y UI |
| Laboratorio | `src/research_lab.py`, `pages/9_Research_Lab.py`, `scripts/run_strategy_comparison.py` y tests nuevos; integración en `app.py` y `src/operations.py` |

Migraciones aditivas: `latest_legacy_outcomes`, trigger de proyección, `daily_refresh_attempts`, `market_price_cache`, `entry_research_snapshots` y `entry_research_outcomes`; marcador `latest_legacy_outcomes_v1` para no repetir el backfill. No hay DROP, VACUUM ni reescritura del histórico en producción.

## Reversión y pendientes expresos

Antes del cambio se creó y verificó una copia SQLite de 1.934.053.376 bytes. La copia, las versiones previas/posteriores de los 28 archivos de código modificados y tres parches delimitados están en el directorio privado `~/Library/Application Support/EquityRadar/revamp-backup-20260924/`. El manifiesto de código registra los hashes. Esa base de reversión incluye los cambios locales previos del usuario: no se debe usar un reset global de Git.

Para revertir código, detener el servicio, comprobar que los archivos no han recibido cambios posteriores, restaurar únicamente los originales del manifiesto y retirar solo los archivos nuevos indicados; después ejecutar tests y el restart con comprobación ZeroTier/Dashboard. Las tablas aditivas pueden quedar sin uso; el trigger mantiene la proyección incluso con escritores antiguos. No restaurar la base completa salvo una incidencia de integridad, porque descartaría capturas posteriores. Los permisos endurecidos y las actualizaciones de seguridad pueden conservarse.

Pendientes que no se presentan como resueltos: reparación versionada de etiquetas legacy por horizonte; replay completo del circuito industrial; curva patrimonial y drawdown con FX; sector neutral y macro con vintages; cadena de opciones y griegas; flujo institucional con fuente verificable; retención y eventual reducción del histórico redundante; CSV seguro frente a fórmulas; revisión de ACL/cifrado, miembros y reglas ZeroTier y pentest acotado. Son extensiones de alcance, no pruebas de alpha omitidas.

Evidencias agregadas: [consulta](PERFORMANCE_IMPLEMENTATION.json), [navegación](UI_IMPLEMENTATION.json), [integridad](INTEGRITY_IMPLEMENTATION.json) y [estrategias](STRATEGY_COMPARISON.json).
