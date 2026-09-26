# Los cuatro pasos implementados

24 de septiembre de 2026. Ejecución local, sin cambios de pesos en producción ni
promociones. El nuevo trabajo aparece en **Entry research**, **Operations** y
**WhaleSeeker**. [Contrato congelado](../../experiments/entry-context-v2.md).

## Resultado funcional

1. **Validación temporal y económica.** Evaluador con ventanas de prueba sin
   solapamiento, purga del horizonte y cinco días de embargo. Entrada en el cierre
   de la siguiente sesión, trayectorias diarias completas, costes de 10/30/50 bps,
   exceso frente a SPY y a la política actual, precisión de las entradas, drawdown,
   exposición, negociación, atribución por sector y sensibilidad al retirar un
   activo. Intervalos exploratorios por bloques a partir de diez cohortes. No se
   confunde la muestra histórica ya examinada con una prueba nueva fuera de muestra.
2. **Dos candidatos capturados.** A mantiene las compras de la política actual y
   se abstiene si SPY está bajo su media de 200 sesiones. B exige fortaleza del
   sector frente a SPY y del activo frente al sector, con cinco huecos de 20% y
   máximo dos nombres por sector. Reglas congeladas antes de ver resultados; no
   hay una búsqueda de pesos para forzar una victoria. Primera captura: **23 activos**,
   cuatro entradas de la política actual/A y dos de B. Son cestas teóricas.
3. **Macro operativa.** Cinco series numéricas de la Fed: Treasury 2Y/10Y, tipo real
   10Y y papel comercial AA/A2 a 30 días; además EFFR, SOFR y comunicados monetarios.
   Se calculan curva y diferencial de crédito de corto plazo. Cada revisión se
   conserva; las publicaciones RSS mantienen su fecha. Las series numéricas usan
   disponibilidad conservadora desde la primera observación: la actualización de
   un feed no acredita su publicación inicial. No se ha reconstruido ALFRED ni se
   han inventado sorpresas monetarias o fechas históricas de disponibilidad.
4. **Instituciones y opciones con datos reales.** **104 registros CFTC**, 26 semanas
   de cuatro contratos: S&P 500, Nasdaq, Treasury 10Y y euro. Último periodo: 15 de
   septiembre. **9.662 contratos de opciones**, **2.628 líquidos** con griegas
   aproximadas, y contexto utilizable en **23 de 25 instrumentos** comprobados.
   Se conservan cadenas, vencimientos, bid/ask, volumen, interés abierto, IV y fechas;
   se derivan skew y estructura temporal donde hay cobertura suficiente.

Los datos CFTC son posiciones agregadas de gestores y fondos apalancados; su variación
no mide dólares entrando en una acción. La publicación suele ser el viernes con
posiciones del martes, según la [guía oficial CFTC](https://publicreporting.cftc.gov/stories/s/COT-Help/p2fg-u73y/).
No sustituye el histórico de Congreso que FMP sigue bloqueando por suscripción.

Las griegas usan una aproximación europea Black–Scholes–Merton con spot, tipo y
rendimiento por dividendo observados; no representan gamma de dealers ni modelan
el ejercicio americano. La interfaz de cadenas es la de
[yfinance](https://ranaroussi.github.io/yfinance/reference/yfinance.stock.html).

La macro procede de los [feeds de datos de la Fed](https://www.federalreserve.gov/feeds/h15_data.htm),
[commercial paper](https://www.federalreserve.gov/feeds/cp_rates.htm),
[comunicados monetarios](https://www.federalreserve.gov/feeds/feeds.htm) y la
[API de la Fed de Nueva York](https://markets.newyorkfed.org/static/docs/markets-api.html).
Se descartó un feed Baa detenido en 2016. Los timestamps de actualización futuros
se marcan como no verificables hasta ese instante; no se utilizan para adelantar datos.

## Lo que dicen los resultados

Diagnóstico retrospectivo, **12 bloques 1M** y **4 bloques 3M**; no son retornos de la
cartera personal. La política actual se representa como cesta equiponderada de sus
entradas, con liquidación al final del bloque, no como su política discrecional de salida.

| Prueba 1M, 10 bps | Política actual | Candidato A |
|---|---:|---:|
| Exceso medio por bloque frente a SPY | +0,49 pp | +0,18 pp |
| Drawdown máximo a cierres | −28,58% | −31,14% |
| Precisión media de entradas frente a SPY | 46,12% | 50,73% |

**A aumenta los aciertos y empeora el resultado económico y el drawdown.** No hay
razón para promocionarlo con estos datos. A 3M coincide con la política actual en
los cuatro bloques admitidos; la muestra es demasiado pequeña para inferencia.
Los intervalos 1M de exceso frente a SPY abarcan cero. Todos los controles y costes
adversos permanecen visibles, también cuando un resultado resulta desfavorable.

Los históricos no conservaban el sector original. B solo aparece en un bloque
histórico trivial sin compras; no permite evaluar su selección. El sector se guarda
desde ahora. No se ha rellenado el pasado con la clasificación actual. El control
con reglas momentum v1 se recalcula sobre el universo del nuevo evaluador, por lo
que sus cifras no son comparables directamente con el informe v1 anterior.

Solo hay **una fecha de cotización de opciones** y **una captura prospectiva v2**.
La cobertura no demuestra capacidad predictiva. Los horizontes necesitan 21/63
sesiones después de la entrada; las ventanas de prueba además requieren historia
previa purgada. Más simulaciones del mismo día no acortan esa espera.

## Funcionamiento desatendido y rendimiento

El mantenimiento existente lanza el proceso en segundo plano. Macro se consulta
cada seis horas; CFTC y opciones, como máximo una vez cada 24 horas tras una captura
correcta. Los fallos permiten reintento tras una hora; un estado `running` abandonado
se recupera a partir de 45 minutos. Son umbrales de elegibilidad del servicio local,
no garantías de ejecución a una hora exacta. Requiere que el Mac y el servidor estén activos.

Una primera captura por fecha permanece inmutable. Las siguientes utilizan el
mismo cálculo final compartido con Dashboard y precios completados, sin requerir
abrir la página. Inputs numéricos, configuración del modelo y decisiones quedan
congelados para replay. Las primeras trayectorias maduras también se conservan,
incluso si el activo sale de la watchlist. Macro/opciones/instituciones tienen peso
adicional cero hasta demostrar aportación mediante una hipótesis y evaluación propias.

Las páginas leen SQLite y resultados persistidos; no consultan proveedores al
renderizar. Las opciones tienen un índice compacto para evitar releer todo el
archivo de cadenas al comprobar continuidad. Una medición local de los tres
resúmenes fue **72 ms**; no constituye un p95 ni una garantía de latencia. Las cifras
principales aparecen primero y la trazabilidad extensa está desplegable.

## Verificación, integridad y reversión

**350 pruebas superadas**, un aviso previo de deprecación de yfinance. Compilación
completa de `src` y `pages`, y prueba de importación de los nueve módulos afectados.
La cobertura incluye costes y cash, clamps originales del Dashboard, ausencia de
look-ahead en precios, sectores ausentes, purga y solapamiento, revisiones A→B→A,
timestamps con offset, liquidez, griegas sin datos, captura sin Dashboard y conservación
de la primera trayectoria de resultados.

El reprocesado preservó exactamente la primera captura y ambos informes prospectivos.
Las nuevas descargas históricas produjeron diferencias de unas 0,000005 pp en el
exceso medio, registradas como nuevos informes; el histórico no se sobreescribe.
La comparación SQL con el backup arroja **cero registros originales cambiados o
perdidos** en backtests, inputs, predicciones, etiquetas, shadow, v1, observaciones
Whale y los 16,7 millones de outcomes legacy. `quick_check=ok`; cero referencias de
fuentes huérfanas.

Migraciones aditivas: `research_signal_batches`, `research_signal_status`,
`research_option_capture_index`, `entry_context_snapshots`, `entry_context_paths`
y `entry_context_reports`. No se borraron datos adicionales en esta fase.

El controlador confirmó Dashboard renderizado y ruta ZeroTier verificada. El listener
permanece exclusivamente en `10.147.17.69:8501`. Las pruebas de navegador y vista móvil
se recogen en la evidencia final de validación, junto con el inventario por archivo.

Rollback: revertir solo los parches de esta fase y su hook del mantenimiento,
conservando las tablas aditivas. Backup privado verificado y copias de código en
`~/Library/Application Support/EquityRadar/four-steps-backup-20260924/`. No restaurar
el DB antiguo sobre capturas posteriores. Evidencia agregada, sin secretos ni datos
de cartera, en [four-steps-evidence](four-steps-evidence/).
