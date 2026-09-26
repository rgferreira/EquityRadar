# Riesgo, score y validación operativa

Implementado el 26 de septiembre de 2026. El estado anterior se guardó y subió
antes de empezar: checkpoint `545cddb`, integración de seguridad remota `57d3a4e`
y corrección compatible del launcher `2dbb74c`. No se forzó el push ni se incluyó
la base privada. El desarrollo nuevo permanece separado de ese checkpoint.

## Resultado y decisión

Entry research incorpora **Riesgo y score**: atribución de pérdidas, ganancias y
pérdidas medias, payoff, recorrido adverso/favorable a cierres y devolución desde
el mejor cierre. El score se analiza en bandas fijas, equilibrando fechas, con
correlación de rangos dentro de cada fecha y diferencias entre bandas sobre fechas
comunes. No se interpreta como probabilidad ni se ajustan umbrales al histórico.

El candidato C mantiene las compras originales y asigna por volatilidad inversa
de 60 sesiones, con máximo inicial del 20% por nombre y efectivo sin redistribuir.
La extensión con máximo del 40% por sector se muestra por separado y exige el
sector original. Se comparan política actual y SPY, además de controles con la
misma exposición. [Contrato y método](../../experiments/entry-risk-v3.md).

Diagnóstico retrospectivo, 10 bps nominales de ida/vuelta; no son retornos de la
cartera personal. Exceso: media aritmética por bloque; drawdown: curva compuesta.

| Horizonte | Bloques | Exceso actual vs SPY | Exceso C vs SPY | Drawdown actual | Drawdown C |
|---|---:|---:|---:|---:|---:|
| 1M | 12 | +0,49 pp | −0,33 pp | −28,58% | −24,68% |
| 3M | 4 | +1,10 pp | +0,09 pp | −21,01% | −15,10% |

**C reduce la caída y sacrifica exceso de rentabilidad.** A 1M también pierde
0,78 pp por bloque frente a la política actual con idéntica exposición. La
exposición media de C es 80,25%; la actual, 91,67%. A 3M ambas son 100%: la
reducción del drawdown persiste, con menor exceso. Los costes adversos 30/50 bps
están guardados y visibles. No procede promocionar C ni retocar sus parámetros
para forzar una victoria retrospectiva.

La correlación media entre orden del score y exceso posterior dentro de fecha
es **0,074 a 1M**, con intervalo exploratorio **[−0,104; +0,250]** en 12 fechas.
A 3M es 0,004 en cuatro fechas, sin intervalo por insuficiencia de muestra.
No hay evidencia suficiente de ordenación económica fiable. En las ocho fechas
compartidas de compras 1M, 80–100 queda por debajo de 60–80; a 3M el signo cambia
en solo tres fechas. Eso no justifica invertir el score ni favorecer una banda.

Las 112 entradas 1M corresponden a 11 fechas con compras: ganancia media 15,96%,
pérdida media −10,49%, payoff 1,52. El 52,68% de retornos absolutos positivos no es
la precisión relativa a SPY. Los tres mayores contribuyentes a las pérdidas suman
aproximadamente 42,2% de las contribuciones negativas: concentración relevante,
sin que ello justifique eliminar esos nombres después de observar el resultado.
La atribución suma contribuciones negativas después de costes, antes de
compensarlas con ganancias; no representa el drawdown ni un retorno compuesto.

## Captura, fuentes y conservación

- A/B tienen capturas automáticas de los días 24, 25 y 26. C comienza su reloj
  propio el 26: una captura, ningún bloque prospectivo maduro. No hereda el pasado
  como evidencia prospectiva. Sus precios de estimación, padre, contrato y pesos
  quedan congelados y se comprueba su reproducción antes de guardar.
- El proceso integrado v2→v3 se ejecutó correctamente: 35 históricos, cero fallos
  de precios y preservación de las primeras capturas. C registra por separado los
  fallos y la espera de contexto; un fallo suyo no invalida una captura v2 completa.
- Opciones: 23/25 instrumentos utilizables, como máximo dos fechas distintas de
  cotización. Aún no existe continuidad suficiente para atribuir valor predictivo.
- CFTC se actualizó expresamente: **108 registros**, última posición del **22 de
  septiembre**. La comprobación anterior era del viernes antes de la publicación;
  consultar correctamente una fuente no significa que ya hubiera publicado la
  semana nueva. Sigue siendo posicionamiento agregado y retrasado, con peso cero.
- La limitación de suscripción del histórico del Congreso sigue siendo distinta.
  No se compraron fuentes ni se asignaron pesos a macro, opciones o instituciones.
- Dos tablas aditivas: `entry_risk_snapshots` y `entry_risk_reports`. Sin borrados,
  reescrituras de simulaciones manuales ni cambios de pesos, salidas o reglas A/B.

## Rendimiento, interfaz y seguridad

Se midieron diez recargas completas por ruta en Chrome Rafael, sobre ZeroTier,
hasta ver el título y el final de ejecución de Streamlit. Cachés del navegador y
servidor calientes; las cifras incluyen sobrecarga de automatización. Con diez
muestras, el p95 empírico por rango coincide con el máximo y tiene poca precisión.
No se presenta como latencia en frío ni como una medición desde la red móvil.

| Página | Mediana | p95 empírico |
|---|---:|---:|
| Entry research | 1,05 s | 1,73 s |
| Dashboard | 2,35 s | 3,68 s |
| Operations | 1,39 s | 1,60 s |
| Company | 1,25 s | 1,81 s |
| Model tuning | 1,46 s | 1,60 s |
| WhaleSeeker | 0,88 s | 1,17 s |

Ninguna de las 60 recargas mostró excepciones. Dashboard sigue siendo la prioridad
de rendimiento; esta muestra no demuestra haber eliminado todos los arranques lentos.
Entry research reduce metadatos superiores, agrupa fechas y asignaciones en
desplegables y muestra tablas con nombres comprensibles. Se comprobó una vista de
390×844 sin desbordamiento horizontal; el tamaño del navegador se restauró.
El encabezado consulta recuentos y únicamente la última captura de cada versión;
no carga todos los precios e inputs históricos al abrir la página.

Revisión acotada de seguridad: 62 dependencias instaladas auditadas, ninguna omitida
y cero vulnerabilidades conocidas; configuración CORS/XSRF activa, telemetría
desactivada, base y configuración privada con permisos 0600 y directorio de secretos
0700. Lista de hosts HTTPS permitidos, límites de tamaño/tiempo y errores de fuente
sin cuerpos ni URLs con credenciales revisados. Los archivos sensibles no están
versionados; se integraron las protecciones remotas de publicación.

El reinicio verificó Dashboard renderizado y ruta ZeroTier. El listener se mantiene
solo en la IPv4 activa de ZeroTier. La pertenencia a esa red continúa siendo el
límite de acceso: no existe autenticación de usuario dentro de la aplicación.
No se ha realizado un pentest externo ni una recuperación en un equipo limpio.

## Verificación, archivos y reversión

**363 pruebas superadas**, con un aviso previo de deprecación de yfinance.
Compilación de `src`, `pages` y el CLI; revisión de diff y ausencia de errores en
las vistas históricas. Pruebas nuevas: ausencia de datos futuros, huecos y
volatilidad cero, límites y efectivo, sector ausente, reloj propio, captura
inmutable, costes/MAE/MFE, controles emparejados, franjas equilibradas por fecha,
ordenación, espera sin contexto y renderizado de resultados maduros.

Backup privado con integridad verificada y restauración aislada satisfactoria;
55 tablas y recuentos idénticos en la copia restaurada. Comparación con el backup:
cero filas originales modificadas o perdidas en backtests, inputs y predicciones,
shadow, capturas v2 e informes v2. Evidencia en los JSON de esta carpeta.

Archivos funcionales: `src/entry_risk.py`, `src/research_pipeline.py`,
`scripts/run_entry_risk.py`, `pages/9_Research_Lab.py` y `tests/test_entry_risk.py`.
Documentación: contrato v3, este informe, evidencia agregada y reconciliación de
`docs/next-best-actions.md`, `docs/implemented-features.md` y `docs/README.md`.

Rollback: revertir el commit de esta iteración sobre `2dbb74c`; conservar las dos
tablas nuevas y los históricos. Backup privado en
`~/Library/Application Support/EquityRadar/risk-research-backup-20260926/`.
No sustituir la base activa por una copia antigua sobre nuevas capturas.

La siguiente investigación debería formular una hipótesis independiente sobre
selección/ordenación, apoyándose en estos diagnósticos, y contrastarla con datos
prospectivos. Añadir factores o reducir exposición por sí solos no ha demostrado
resolver el exceso de rentabilidad. Las simulaciones manuales continúan siendo
útiles para diagnóstico y trazabilidad; la recogida futura ya es automática.
