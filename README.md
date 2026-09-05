# Agente PMR — Pagos Minoristas Reales

Sistema agentico que convierte una edicion del **Informe Mensual de Pagos Minoristas
del BCRA** en una serie de tarjetas deflactada a pesos constantes, validada contra el
propio informe, y publicada como JSON estructurado y dashboard HTML.

Trabajo final · Programacion de y con Agentes de IA · MBA UCEMA · 2026 2T

---

## El problema real

En Payway el Informe de Pagos Minoristas se procesa a mano todos los meses. El BCRA
publica los datos en pesos nominales; con inflacion de dos digitos anuales, una serie
nominal no dice nada util: todo crece siempre. Para leer si el negocio de tarjetas se
expande o se contrae hay que deflactar por IPC, y eso es un trabajo repetitivo,
mecanico y —justamente por eso— propenso a errores que no se notan.

El agente automatiza ese trabajo y, sobre todo, **se controla a si mismo**: contrasta
sus propios calculos contra las variaciones que el BCRA publica en el texto del
informe. Es una segunda fuente independiente validando a la primera.

El dashboard esta armado como una serie de exhibits: cada uno se encabeza con el
hallazgo enunciado, no con el nombre de la serie, y abre con una sintesis ejecutiva de
tres mensajes. Todas las series se muestran en pesos constantes; el contraste entre la
planilla de series y el texto del informe cierra el documento como control de
consistencia.

---

## Que hace, en concreto

1. Descarga el Excel de series y el PDF del informe, validando `content-type` y tamanio.
2. Determina hasta que mes llegan realmente los datos de tarjetas, leyendo la nota al
   pie del PDF y contrastandola contra el Excel.
3. Carga cuatro pestanias mapeando columnas por encabezado.
4. Deflacta por IPC Nacional Nivel General del INDEC a pesos del mes de corte.
5. Calcula monto real, variacion interanual, ticket promedio y participacion para 24 meses.
6. Contrasta ocho cifras contra lo que el PDF declara, con tolerancia de 0,5 pp.
7. Emite `salida.json` y, a partir de el, `dashboard.html`.

### El detalle que hace falta conocer

El "mes de analisis" del informe no aplica a todo. Transferencias y pagos con
transferencia corresponden al mes del titulo; **tarjetas llega un mes antes**. En la
edicion de julio 2026, tarjetas llega a junio 2026. Un informe que promedie los dos
cortes queda mal sin que nada lo indique. El agente lee ese desfasaje del PDF y lo
declara explicitamente en la salida.

---

## Como correrlo

```bash
python3 -m pip install openpyxl          # unica dependencia
sudo apt-get install poppler-utils       # pdftotext

python3 agente/pmr.py 2026-07 --out corridas/2026-07
python3 agente/dashboard.py corridas/2026-07/salida.json
```

Abrir `corridas/2026-07/dashboard.html`.

---

## Estructura

```
README.md                    este archivo
DECISIONES.md                la historia de la construccion: iteraciones y errores
prompts/
  system_prompt.md           el contrato (rol, contexto, tarea, restricciones, formato, ejemplos)
  user_prompt.md             invocacion parametrizada, tres variantes
agente/
  pmr.py                     capa de herramientas: descarga, parseo, deflactacion, validacion
  dashboard.py               generador del exhibit HTML a partir del JSON
  ipc_fuente.json            deflactor IPC con sus fuentes
  marca/logo.png             logo del encabezado; reemplazarlo cambia todos los dashboards
corridas/
  2026-07/                   corrida estandar
  2026-04/                   edicion anterior; verifica que el corte no este cableado
  2026-04-base-forzada/      variante B; ejercita la ruta de advertencia y L1
  2026-08-inexistente/       prueba de resistencia contra una edicion no publicada
```

Cada carpeta de corrida contiene `entrada.md` (prompt, comando, fecha, insumos y
resultado), `salida.json`, `dashboard.html` y los archivos originales del BCRA tal como
se descargaron. `entrada.md` lo genera `pmr.py` a partir de la corrida, no se escribe a
mano: ver `DECISIONES.md`, iteracion 21.

---

## Las cuatro corridas

| Corrida | Edicion | Estado | Que demuestra |
|---|---|---|---|
| 1 | 2026-07 | `ok` | El camino completo, con las cuatro validaciones dentro de tolerancia |
| 2 | 2026-04 | `ok` | El corte de tarjetas se deduce, no esta cableado: da marzo 2026, con una nota al pie redactada distinto |
| 3 | 2026-04 (base forzada) | `ok_con_advertencias` | La ruta de advertencia y la supervision L1: banner visible y `requiere_revision_humana: true` |
| 4 | 2026-08 | `error` | Ante una edicion no publicada, falla ruidosa en vez de sustitucion silenciosa |

Resultado del contraste en la corrida 1:

| Concepto | Informe BCRA | Calculado | Delta |
|---|---|---|---|
| Credito — var. i.a. cantidad | +1,6 % | +1,57 % | 0,03 pp |
| Credito — var. i.a. monto real | −10,2 % | −10,19 % | 0,01 pp |
| Debito — var. i.a. cantidad | −6,9 % | −6,94 % | 0,04 pp |
| Debito — var. i.a. monto real | −13,4 % | −13,41 % | 0,01 pp |

---

## Supervision humana (L0–L4)

| Paso | Nivel | Quien decide |
|---|---|---|
| Descarga y validacion de archivos | **L3** — ejecuta y notifica | Agente |
| Deflactacion y calculo de metricas | **L3** — ejecuta y notifica | Agente |
| Conflicto de corte temporal | **L1** — propone, la persona decide | Analista |
| Discrepancia > 0,5 pp contra el PDF | **L1** — propone, la persona decide | Analista |
| Publicacion del dashboard | **L0** — accion exclusivamente humana | Analista (firma) |

Ningun paso opera en **L4**. Es deliberado: la salida alimenta reportes de gestion y
una cifra mal deflactada se propaga sin dejar rastro.

---

## Analisis economico

### Donde estan los tokens

La descarga, el parseo, la deflactacion y el calculo son deterministicos: **cuestan
cero tokens**. El modelo interviene en dos lugares: redactar el resumen ejecutivo a
partir del JSON, y resolver la lectura de la nota al pie cuando el patron
deterministico no encuentra coincidencia.

Medicion sobre la corrida de 2026-07:

| Componente | Tokens (aprox.) |
|---|---|
| `system_prompt.md` | 2.400 entrada |
| Invocacion (una variante del user prompt) | 150 entrada |
| JSON condensado a 12 meses, enviado al modelo | 3.000 entrada |
| **Total entrada** | **~5.550** |
| Resumen ejecutivo generado | **~700 salida** |

### Costo por corrida

Tarifas vigentes de la Claude API, en dolares por millon de tokens:

| Modelo | Entrada | Salida | Costo por corrida |
|---|---|---|---|
| **Haiku 4.5** | $1 | $5 | **$0,009** |
| Sonnet 5 | $2 | $10 | $0,018 |
| Opus 5 | $5 | $25 | $0,045 |

### Proyeccion

El BCRA publica una edicion por mes. Con un margen de dos reprocesos mensuales
(correcciones, reruns tras una advertencia), son 3 corridas mensuales:

| Horizonte | Haiku 4.5 | Opus 5 |
|---|---|---|
| Por semana | $0,007 | $0,035 |
| Por mes | $0,027 | $0,135 |
| Por anio | **$0,32** | $1,62 |

### Eleccion de modelo

**Haiku 4.5**, siguiendo el criterio del curso: el mas chico que hace bien la tarea.

La justificacion no es el precio —a estos volumenes la diferencia anual entre Haiku y
Opus es de un dolar y medio, economicamente irrelevante— sino que **el modelo no hace
el trabajo dificil**. Todo lo que requiere precision es deterministico. Lo que queda
para el modelo es redactar un resumen a partir de datos ya calculados y validados, y
para eso un modelo mayor no produce una salida mejor: produce la misma salida mas
lenta. Escalar a Opus seria pagar capacidad de razonamiento para una tarea que ya no
tiene razonamiento que hacer.

### La conclusion economica que importa

**El costo de tokens de este sistema es despreciable; el costo real es humano.** A
$0,32 por anio, optimizar el gasto de API no tiene sentido. Lo que si cuesta:

- **Revision del analista:** ~15 minutos por corrida mensual.
- **Mantenimiento del deflactor:** un numero por mes en `ipc_fuente.json`, mientras
  el INDEC no sea accesible desde el entorno de ejecucion (ver `DECISIONES.md`, it. 3).
- **Mantenimiento ante cambios del BCRA:** el patron de URL ya cambio una vez.

Comparado contra el proceso manual actual —entre 2 y 3 horas mensuales de armado y
control— el ahorro esta en las horas, no en la infraestructura. Cualquier discusion
sobre que modelo usar es, en este caso, una discusion sobre nada.

---

## Gobierno y riesgo

### Que sistemas toca y con que permisos

| Sistema | Permiso | Alcance |
|---|---|---|
| `bcra.gob.ar` | Lectura publica, sin credenciales | Descarga de dos archivos por edicion |
| `indec.gob.ar` | Lectura publica (hoy indirecta, via JSON transcripto) | Solo IPC Nivel General |
| Sistemas de Payway | **Ninguno** | El agente no accede a datos internos |
| Disco local | Escritura acotada | Solo `corridas/{edicion}/` |

El agente no maneja credenciales, no lee datos de clientes ni de comercios, y no
escribe en ningun sistema de la organizacion. La superficie de riesgo por acceso
indebido es esencialmente nula. El riesgo esta en otro lado: en que produzca un
numero equivocado que alguien use para decidir.

### Que puede salir mal, y que pasa cuando sale mal

| Riesgo | Deteccion | Respuesta del sistema |
|---|---|---|
| Edicion no publicada o URL cambiada | `content-type` + tamanio minimo | `estado: error`, series vacias, se nombran las URLs probadas |
| PDF 404 devuelto como HTML de 60 KB | Validacion de `content-type` | Se rechaza el archivo; no se parsea basura |
| Corte temporal en conflicto entre PDF y Excel | Comparacion explicita | **La corrida se detiene.** Determina la base de toda la serie |
| Deflactor desactualizado o mal transcripto | Contraste contra las cifras del PDF | Advertencia y marca de revision humana |
| Cambio de estructura del Excel | Mapeo por encabezado, no por posicion | Grupo ausente = serie ausente, nunca una columna equivocada |
| Serie en moneda distinta de pesos | Marca `moneda` por serie | Se excluye de la deflactacion y se publica solo el nominal |
| Redaccion nueva en la nota al pie | — | **Punto ciego conocido:** cae al corte segun Excel sin declarar conflicto |

El principio de diseno es uno solo: **ante ambiguedad, el agente se detiene**. Una
corrida fallida es una salida legitima. Un informe parcial disfrazado de completo, no.

### Que revisa el analista antes de confiar en una salida

1. `corte.coincide_con_excel` es `true`.
2. Las cuatro comparaciones de `validacion_pdf` estan dentro de tolerancia.
3. `advertencias` esta vacio, o cada advertencia tiene explicacion.
4. Si se comparan dos ediciones, que las bases de pesos constantes sean la misma.
5. Que las `notas` estructurales sigan siendo las esperadas y no haya aparecido una nueva.

### Quien firma

La publicacion del dashboard hacia adentro de la organizacion es **L0**: la ejecuta y
la firma el analista de Planeamiento. El agente no publica. `requiere_revision_humana`
en el JSON es una senal para el analista, no una compuerta automatica: la firma es
siempre humana, incluso cuando la corrida sale limpia.

---

## Fuentes

- Informe Mensual de Pagos Minoristas, BCRA —
  <https://www.bcra.gob.ar/informe-de-pagos-minoristas/>
- Indice de precios al consumidor, INDEC — informes de prensa de julio 2025 y julio
  2026; URLs exactas en `agente/ipc_fuente.json`
