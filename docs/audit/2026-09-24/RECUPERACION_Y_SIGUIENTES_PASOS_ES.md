# Simulaciones, datos estancados y siguiente mejora del modelo

Revisión y ejecución del 24 de septiembre de 2026. Complementa el
[revamp inicial](IMPLEMENTACION_ES.md) y su [revisión funcional/técnica](REVISION_Y_PLAN_ES.md).
La autorización adicional fue reprocesar todo lo posible y borrar datos huérfanos.

## Resultado principal

Tus simulaciones manuales siguen siendo útiles. Hay **1.746 registros manuales de
24 fechas**, con varias versiones y horizontes solapados: no son 1.746 apuestas
independientes. Permiten reproducir decisiones, comparar métodos y estudiar errores.
El backtesting sigue siendo central para aceptar o rechazar hipótesis. La política
de aprendizaje tiene **peso aplicado cero** en la decisión oficial desde la
cuarentena de Phase 3.8, anterior a este trabajo; capturar una simulación no entrena
automáticamente un modelo ni cambia sus pesos.

Se han completado **1.512 resultados por horizonte** que faltaban, reevaluado
**967 combinaciones activo/fecha**, actualizado los datos accesibles de WhaleSeeker
y BTC, añadido **95 contrafactuales FINRA y 4 BTC**, y eliminado **2 filas de caché
huérfanas**. No se ha promovido ningún modelo ni cambiado sus factores o umbrales.

## Qué estaba parado y qué se ha hecho

| Componente | Hallazgo comprobado | Resultado |
|---|---|---|
| Etiquetas de backtesting | Tener cualquier etiqueta excluía una predicción para siempre, incluso `pending` o con horizontes incompletos. El filtro de 75 días también impedía evaluar 1M en vivo | Nueva tabla aditiva por horizonte; cada resultado se congela cuando madura. Proyección explícita para las vistas actuales y gates; archivo original intacto |
| Precios usados al madurar | Caché en memoria sin caducidad podía reutilizar precios del arranque | Refresco diario obtiene precios nuevos una vez por activo. Excluye la barra diaria aún abierta |
| WhaleSeeker | Solo dos lotes del 12 de agosto. Clave en marcador iCloud; la copia de ejecución tampoco incluye el dotenv del proyecto | Clave existente recuperada y configuración operativa privada fuera de iCloud, permisos 600 |
| Base de datos de CLI | Al recuperar el dotenv aparecía una ruta antigua al DB del proyecto, distinta de la usada por el servidor | La configuración local dirige también las herramientas a la base activa de Application Support. Variables explícitas del proceso conservan prioridad |
| Histórico de ballenas | FMP devuelve HTTP 402 para `page=1` en ambas cámaras: acceso condicionado por suscripción | Consulta de primeras páginas restablecida; recuperación paginada acotada y con checkpoint. El hueco queda marcado como bloqueado; no se falsea cobertura completa |
| BTC derivados | Último periodo: 29 de agosto; el refresco dependía de navegar a Company | 25 observaciones nuevas, hasta el 23 de septiembre; integrado en mantenimiento del servidor |
| Estado de proveedores | Un `healthy` antiguo podía quedar verde indefinidamente | Caduca por edad; intentos iniciales de onboarding se distinguen del mantenimiento activo. Se excluyen estados de activos fuera del universo actual |
| Trabajos fallidos | 154 conflictos con predicciones congeladas; 33 cortes con historial insuficiente | Clasificados. Los 33 se reintentaron y siguen sin datos suficientes. No se sobrescribieron las 154 predicciones originales |
| FINRA diario | Datos hasta el 23 de septiembre, 24 instrumentos | Activo. Reprocesados todos los cortes elegibles con la metodología congelada |
| Short interest oficial | Último periodo observado: 31 de agosto, distinto del día de descarga | Conserva su política de frescura por fecha del informe; un fetch de hoy no convierte un informe antiguo en nuevo |
| Opciones/griegas | 0 de 25 instrumentos con observaciones de opciones utilizables; 0 cumplen continuidad | No constituyen una señal disponible. No se han inventado cadenas, griegas ni flujo institucional |
| Evaluaciones antiguas | Dos informes y un experimento de julio; contrafactuales de agosto | Archivo de investigación válido, no procesos diarios fallidos. Conservados; nuevos resultados y reevaluaciones quedan separados |
| Nuevo laboratorio de entradas | Una captura prospectiva; ningún horizonte maduro | Inmadurez esperada. Captura automática mientras funciona el servidor |
| Cachés de universo retirado | Una fila de industria y otra de posicionamiento | Eliminadas con backup previo. Benchmarks y datos necesarios para posiciones quedan protegidos |

WhaleSeeker conserva ahora **109 observaciones / 108 operaciones públicas únicas**,
frente a 50 / 49 antes: **59 observaciones nuevas**. Últimas publicaciones: Cámara,
23 de septiembre; Senado, 21 de septiembre. Son declaraciones de políticos, no
órdenes en tiempo real de grandes gestoras. La fecha de primera observación de lo
recuperado sigue siendo hoy; no se sustituye por la fecha de operación o publicación.

Los 11 días sin fichero en el historial de FINRA no se han eliminado ni declarado
automáticamente averías: pueden incluir cierres de mercado. Su cobertura se conserva
como ausencia explícita, no se rellena con datos inventados.

## Resultado del reprocesado de outcomes

| Fuente | Horizonte | Archivo anterior | Vista actual |
|---|---|---:|---:|
| Manual | 1M | 1.407 | 1.452 |
| Manual | 3M | 1.369 | 1.407 |
| Manual | 6M | 850 | 1.159 |
| Sugerida | 1M | 340 | 364 |
| Sugerida | 3M | 115 | 290 |
| Sugerida | 6M | 69 | 92 |
| En vivo | 1M | 0 | 898 |

Son observaciones por versión, no muestras independientes. Los horizontes aún no
transcurridos permanecen pendientes; BTC no recibe un benchmark de renta variable
inventado. Se consultaron 26 historiales públicos, sin fallos. Los 967 cortes legacy
se reevaluaron con observaciones aditivas, sin modificar sus registros anteriores.

La proyección actual preserva el primer resultado completo de cada horizonte y su
propio precio de entrada, fecha de observación, benchmark, costes y hash. Distintos
horizontes pueden proceder de diferentes vintages de precios ajustados. No se los
presenta como una única observación original. Los informes históricos congelados
y la reconstrucción de promociones anteriores siguen leyendo el archivo original.

También se corrigió el estado por horizonte: disponer de 1M no convierte el estado
de 3M en `available`, ni reinicia artificialmente su progreso de maduración.

## Qué dicen ahora los resultados

**El shadow no está rechazado por resultados prospectivos suficientes; todavía
carece de outcomes maduros para los casos en que cambia la decisión.** Hay 232
pares 3M maduros de 33 fechas, pero cero cambios de decisión maduros. Los 80 cambios
observados en 41 fechas siguen esperando 3M. Los gates permanecen **1/6**.

La pantalla sigue mostrando **59% de captura/antigüedad del v5 actual** y **88% de la
línea compatible v3/v5**. Ninguno de esos porcentajes es accuracy ni probabilidad
de promoción. Los intervalos actuales agrupados por fecha tampoco corrigen toda
la dependencia causada por horizontes solapados.

La reevaluación íntegra del contrafactual FINRA con los resultados legacy actuales
da **54,26% para la decisión original y 52,91% al añadir la señal**: −1,35 puntos.
Son 223 observaciones seleccionadas de 20 fechas, con solo cinco cambios de señal
en esa selección. La utilidad media también empeora (−0,2066 en las unidades de
esa política). Es un diagnóstico retrospectivo y su accuracy mide la utilidad de
decisión legacy; no equivale a precisión de entradas relativa al benchmark. La
vista de overlays archivados daba 53,1% / 51,4%; se conserva, pero no se confunde
con esta nueva reevaluación.

El ranking experimental 12–1, tras recuperar outcomes, se puede contrastar en
**10 cohortes sin solapamiento a 1M y 5 a 3M**:

| Método | Exceso medio por cohorte frente a SPY, 1M | Exceso medio, 3M |
|---|---:|---:|
| Ranking experimental 12–1 | −0,93 pp | −0,82 pp |
| Ranking por score de entrada registrado, diagnóstico | −0,40 pp | +3,86 pp |
| Universo equiponderado | −1,83 pp | −0,28 pp |

No son rentabilidades anualizadas ni resultados de una cartera real. La muestra
es pequeña, retrospectiva, seleccionada manualmente y sin garantía point-in-time
completa. El resultado positivo del score a 3M orienta la siguiente prueba, pero
no prueba alpha. No se han ajustado parámetros para mejorar estas cifras.

## Plan de siguientes pasos, por orden

1. **Cerrar la evaluación económica.** Comparar el modelo actual y como máximo
   dos candidatos sobre el mismo universo, entrada siguiente sesión, benchmark y
   costes. Mantener precisión de entradas, exceso neto, drawdown y rotación como
   métricas separadas. Separar reconstrucción histórica de decisiones prospectivas.
   Usar validación temporal con purga del horizonte y evaluación por bloques o
   cohortes sin solapamiento. Congelar las reglas antes de mirar el siguiente bloque.
2. **Priorizar selección de entradas y contexto.** Primer candidato: política
   actual con una regla sencilla de abstención/riesgo según régimen de mercado.
   Segundo: fortaleza relativa del sector y del activo dentro del sector, con
   control de concentración. Benchmark: modelo actual y reglas simples. No seguir
   ajustando el ranking 12–1 sobre esta misma muestra para forzar una victoria.
3. **Incorporar macro verificable, con pocas variables.** Tipos reales, curva y
   crédito, conservando fecha de publicación y revisiones mediante fuentes y
   vintages oficiales. Empezar por contexto y control de exposición; no asignar
   una suma arbitraria de pesos a todas las señales disponibles.
4. **Resolver la cobertura de flujos antes de ponderarlos.** Congreso tiene demora
   y un hueco de suscripción. Una integración 13F sería otra fuente: holdings
   trimestrales con hasta 45 días para declarar, no flujo inmediato. Para opciones,
   primero hacen falta cadenas persistidas, bid/ask, volumen, interés abierto,
   vencimiento y una política de liquidez; después se puede evaluar si IV/skew o
   griegas aportan algo. No se ha contratado ni ampliado ninguna suscripción.
5. **Promover solo por mejora demostrada.** Exigir mejora fuera de muestra después
   de costes, estabilidad entre periodos y sectores, y que el resultado no dependa
   de un activo. Mantener costes más adversos como prueba de sensibilidad. Rechazar
   un candidato que solo mejora el porcentaje de aciertos mientras empeora utilidad.

Expectativa razonable: ahora podemos descubrir antes qué funciona y qué no. Una
tarde permite reparar datos y probar hipótesis, pero no fabricar meses de evidencia
prospectiva ni prometer una accuracy objetivo. Un horizonte 1M necesita 21 sesiones
comunes después de la entrada; 3M, 63. Más simulaciones del mismo periodo no acortan
esa espera ni eliminan el sesgo de selección. Este orden es un plan técnico, no una
agenda con fechas inventadas ni una promesa de ejecución futura programada.

La disciplina de pocas hipótesis y pruebas comparables concuerda con la discusión
de AQR sobre [data mining](https://www.aqr.com/insights/perspectives/lies-damned-lies-and-data-mining).
La demora de 13F consta en las [preguntas oficiales de la SEC](https://www.sec.gov/rules-regulations/staff-guidance/division-investment-management-frequently-asked-questions/frequently-asked-questions-about-form-13f).
El bloqueo de FMP se verificó directamente en la cuenta mediante respuestas HTTP
402, sin almacenar la URL con credenciales; la documentación del proveedor está
[aquí](https://site.financialmodelingprep.com/developer/docs).

## Pantallas, validación y reversión

- Operations muestra primero las incidencias del ciclo de vida y deja el inventario
  completo desplegable. Distingue inmadurez, archivo, huecos y bloqueo de proveedor.
- WhaleSeeker muestra consulta y publicación recientes, más la cobertura bloqueada.
  Sus pestañas se cargan al abrirlas. La vista reciente se limita a 100 registros;
  calcular retornos descriptivos es opcional, para evitar decenas de descargas al entrar.
- **330 pruebas superadas**, con fixtures sintéticas; un aviso de deprecación de
  yfinance. Compilación e importación de 64 módulos comprobadas. `git diff --check`
  correcto. Sin migraciones destructivas.
- Reinicio del controlador macOS confirmado: **Dashboard renderizado y ruta
  ZeroTier verificada**. Listener exclusivo en `10.147.17.69:8501`.
- Chrome Rafael: WhaleSeeker, Operations y Model tuning sin excepciones. Vista de
  390 px sin desbordamiento horizontal. Dos comprobaciones móviles de contenido
  visible: 984 ms y 787 ms; muestra funcional pequeña, no un SLO ni un nuevo p95.
- Comparación SQL con el backup: **cero registros originales cambiados o perdidos**
  en 2.531 backtests, 2.548 inputs, 3.235 predicciones, 1.873 etiquetas, 3.010
  snapshots shadow, 50 observaciones Whale y **16.696.417 outcomes legacy**.
  SQLite `quick_check`: `ok`.

Migraciones aditivas: `prediction_horizon_outcomes` y `whale_catchup_state`. La
limpieza se limita a cachés descartables fuera del universo activo, protegiendo
activos necesarios para posiciones y benchmarks. Cero inputs de predicción huérfanos
y cero etiquetas sin predicción. Los raw de consultas repetidas son evidencia de
ingestión y no se borran por carecer de una operación nueva.

El detalle de archivos está en [el plan de ejecución](../../implementation/freshness-recovery/PLAN.md).
Cambios adicionales: estado por horizonte en `src/model_tuning.py` y limpieza acotada
en `src/data/maintenance_cleanup.py`. Copia privada verificable y parches por tarea
en `~/Library/Application Support/EquityRadar/freshness-backup-20260924/`.
Rollback: revertir únicamente esos parches; conservar tablas aditivas. Recuperar
las dos filas de caché desde el backup si fuera necesario. No restaurar todo el DB
antiguo sobre observaciones nuevas. La configuración privada se puede retirar por
separado, aunque se perdería la corrección del acceso al proveedor.

Límites pendientes: hueco histórico FMP, inexistencia de opciones utilizables,
falta de macro con vintages, dependencia temporal en inferencia de gates y pocas
cohortes independientes. La limpieza no elimina archivos de investigación ni
backups por ser antiguos. La revisión de red/autenticación más amplia del informe
inicial sigue siendo un trabajo posterior; esta reparación no constituye un pentest.
