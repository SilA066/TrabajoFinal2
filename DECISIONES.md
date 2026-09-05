# DECISIONES.md

Historia de la construccion del Agente PMR. Se documenta en orden cronologico, con
los errores tal como aparecieron. Las citas de mensajes de error son textuales.

---

## Iteracion 0 — Cambio de caso respecto de la Entrega 1

La Entrega 1 fue el "Vigia de competidores de adquirencia": un agente que relevaba
comunicados y paginas de precios de MercadoLibre, Getnet, Naranja X, Uala y fuentes
como CACE. El trabajo final arranca como su continuacion, pero se cambio de caso.

**Por que.** El Vigia depende de scraping de sitios de terceros que cambian de
estructura sin aviso y no versionan su contenido. Eso hace que el requisito 2 del
enunciado —"un tercero tiene que poder reconstruir que paso en cada corrida"— sea
casi imposible de cumplir con honestidad: la pagina de precios de un competidor
hoy no es la de la semana que viene, y no hay forma de probar que decia antes.

El Informe de Pagos Minoristas del BCRA tiene la propiedad contraria: cada edicion
es un par de archivos inmutables con URL estable. Se puede volver a correr en seis
meses y obtener exactamente lo mismo.

**Costo del cambio.** Se perdio la continuidad narrativa con la Entrega 1. Se
asume: la reproducibilidad pesa mas que la continuidad.

---

## Iteracion 1 — Reduccion de alcance de nueve pestanias a tres

El Excel de series del BCRA trae nueve pestanias: `Cheques`,
`Transferencias de fondos`, `Series push apertura`, `Tarjetas`, `Transporte`,
`TC Modalidad de pago`, `Tarjeta de credito por canal`, `Resto` y
`Cuentas de pago y fondos invert`.

La primera version del contrato las cubria todas. Se recorto a las tres de
tarjetas por dos motivos:

1. **Tecnico.** Las pestanias tienen estructuras de encabezado distintas entre si
   (numero de filas de cabecera, celdas combinadas, grupos con y sin subcolumna de
   monto). Un parser generico para las nueve habria consumido el tiempo disponible
   sin agregar nada al puntaje.
2. **De alcance.** El enunciado dice "mas chico que un producto". Tres pestanias
   alcanzan para demostrar el mecanismo completo.

Tambien se descarto la publicacion automatica del dashboard hacia sistemas
internos: quedo como paso L0, exclusivamente humano.

---

## Iteracion 2 — El patron de URL del PDF cambia entre ediciones

Al buscar los archivos, el PDF de la edicion de julio 2026 devolvia 404 con el
patron que funcionaba para enero 2026.

```
informe-pagos-minoristas-2026-01.pdf   -> 200  925.715 bytes  application/pdf
informe-pagos-minoristas-2026-07.pdf   -> 404   59.917 bytes  text/html
```

El patron vigente resulto ser otro:

```
informe-mensual-pagos-minoristas-2026-07.pdf -> 200  542.928 bytes  application/pdf
```

**Dos lecciones que quedaron en el contrato.**

La primera es obvia: el agente prueba los dos patrones antes de declarar error.

La segunda es la que importa. El servidor del BCRA **no devuelve un error limpio**:
devuelve una pagina HTML de casi 60 KB con codigo 404. Un agente que solo mirara el
tamanio del archivo lo habria aceptado como valido y despues habria fallado al
parsearlo, o peor, habria extraido cero cifras y reportado una serie vacia como si
fuera un mes sin actividad. Por eso el paso 1 valida `content-type` **y** tamanio
minimo, no uno de los dos.

---

## Iteracion 3 — El deflactor resulto ser la parte fragil, no los datos del BCRA

La hipotesis inicial era que la parte dificil seria el BCRA. Fue al reves: los
archivos del BCRA se bajan sin problema y el INDEC resulto inaccesible de forma
programatica. Tres intentos, tres bloqueos distintos:

| Intento | Resultado |
|---|---|
| `www.indec.gob.ar/ftp/cuadros/economia/sh_ipc_aperturas.xls` | `403` — `x-deny-reason: host_not_allowed` (el host no esta en la allowlist de red del entorno) |
| `indec.gob.ar/...` (mismo path, sin `www`) | `500` con pagina de error HTML: el servidor del INDEC rechaza el host sin `www` |
| Serie 7931 del BCRA (republica la variacion mensual del IPC) | La pagina de datos esta detras de un captcha Cloudflare Turnstile |

**Solucion adoptada.** Se reconstruyo el indice a partir de las variaciones
mensuales e interanuales publicadas en los informes de prensa del INDEC, que si son
legibles. Dos informes alcanzan para cubrir el horizonte:

- Informe de julio 2025 → variaciones mensuales e interanuales de ago-2024 a jul-2025
- Informe de julio 2026 → variaciones mensuales e interanuales de ago-2025 a jul-2026

El indice se encadena hacia adelante desde un ancla arbitraria (jul-2024 = 100; solo
importan los cocientes) y el tramo anterior se reconstruye dividiendo por las
variaciones interanuales. Las cifras y sus fuentes estan en `agente/ipc_fuente.json`.

**Limitacion que se asume y no se disimula.** El deflactor esta transcripto a mano
en un JSON, no descargado. Cada mes hay que agregar un numero. Es el unico paso del
sistema que no es automatico, y es deliberado: preferimos un paso manual visible a
un scraper que rompa en silencio contra un captcha. En un entorno con salida de red
al INDEC, el reemplazo es directo y esta aislado en un solo archivo.

**Verificacion posterior.** La iteracion 4 termino validando esta reconstruccion
por una via independiente (ver abajo): los desvios contra las cifras que publica el
BCRA quedaron entre 0,01 y 0,04 puntos porcentuales.

---

## Iteracion 4 — La validacion cruzada fallo en la primera corrida

La primera corrida de la edicion 2026-07 termino asi:

```
estado: ok_con_advertencias
advertencias: ["No se pudieron extraer del PDF cifras de tarjetas comparables;
                la validacion cruzada quedo vacia y la salida no esta contrastada."]
validacion_pdf: []
```

Es decir: el sistema calculo las series, no encontro con que compararlas, y lo
dijo. Ese comportamiento es el correcto —no invento una validacion— pero dejaba sin
cumplir la parte mas importante del diseno.

**Causa.** El primer regex buscaba un patron del tipo `(X % i.a.)` entre parentesis.
El PDF real usa dos redacciones distintas, y ninguna de las dos coincide:

```
− Crédito: se observaron variaciones interanuales de 1,6 % en cantidades
  y -10,2 % en montos reales, realizándose 176,2 millones de pagos...

− Débito: se efectuaron 163,7 millones de transacciones por $ 5,2 billones
  en junio (último dato disponible), con disminuciones de 6,9 % i.a. en
  cantidades y de 13,4 % i.a. en montos reales.
```

La segunda es la trampa: **el signo esta en la palabra, no en el numero.** Un parser
que leyera "6,9" y "13,4" tal cual habria comparado `-6,94` calculado contra `+6,9`
declarado y reportado una discrepancia de 13,8 pp que no existe.

**Correccion.** El extractor ahora aisla el parrafo de cada vinieta, busca el par
cantidades/montos reales, y niega los valores si el parrafo contiene
`disminuci|caida|retroced|baja`. Resultado de la corrida siguiente:

| Concepto | Informe BCRA | Calculado | Delta |
|---|---|---|---|
| Credito — var. i.a. cantidad | +1,6 % | +1,57 % | 0,03 pp |
| Credito — var. i.a. monto real | −10,2 % | −10,19 % | 0,01 pp |
| Debito — var. i.a. cantidad | −6,9 % | −6,94 % | 0,04 pp |
| Debito — var. i.a. monto real | −13,4 % | −13,41 % | 0,01 pp |

Esto valida dos cosas a la vez: el parseo del Excel y —sobre todo— la
reconstruccion del IPC de la iteracion 3. Si el deflactor estuviera mal, los montos
reales no cerrarian contra los que publica el BCRA.

---

## Iteracion 5 — El dashboard no calcula

Version inicial: un unico script bajaba, calculaba y renderizaba HTML de corrido.

Se separo en dos: `pmr.py` produce `salida.json`, `dashboard.py` lo lee y renderiza.
El generador de HTML no tiene acceso a los datos crudos ni a la funcion de
deflactacion. Si un numero no esta en el JSON, no puede aparecer en el dashboard.

**Por que importa.** El dashboard es lo que una persona mira; el JSON es lo que se
audita. Si el dashboard pudiera recalcular, existiria la posibilidad de que muestre
algo distinto de lo auditado, y la revision humana perderia sentido.

---

## Iteracion 6 — La nota al pie cambia de redaccion entre ediciones

Con el corte de tarjetas resuelto para 2026-07 se corrio 2026-04 para verificar que
el mes no estuviera cableado. Aparecio una diferencia de redaccion:

```
2026-07: "...tarjetas de crédito, tarjetas de débito, tarjetas de transporte y
          tarjetas prepagas que la información corresponde a junio de 2026"
2026-04: "...tarjetas de crédito, tarjetas de débito y tarjetas de transporte que
          la información corresponde a marzo de 2026"
```

La edicion de abril no menciona prepagas. El patron de extraccion tuvo que
flexibilizarse para no depender de la enumeracion exacta, sino de la estructura
`tarjetas ... informacion corresponde a <mes> de <anio>`. Ambas ediciones se leen
bien y el corte da junio 2026 y marzo 2026 respectivamente.

---

## Iteracion 7 — Que hace el modelo y que no

Version inicial del diseno: el modelo leia la nota al pie del PDF y decidia el mes
de corte.

Se movio a extraccion deterministica. La razon es de gobierno, no de costo: el mes
de corte determina la base de deflactacion **de toda la serie**, y un paso del que
depende todo el resultado no deberia tener varianza entre corridas. Un regex que
falla es visible y se arregla; un modelo que interpreta distinto el mismo texto en
dos corridas es mucho mas dificil de detectar.

El modelo queda a cargo de lo que si es interpretacion: redactar el resumen
ejecutivo a partir del JSON, y resolver la lectura de la nota al pie cuando el
patron deterministico no encuentra coincidencia —caso en el que, ademas, la salida
se marca para revision humana.

---

## Lo que quedo afuera

- **Las otras seis pestanias del Excel.** Cheques, transferencias, PCT y cuentas de
  pago. Es la extension natural y no cambia la arquitectura.
- **Descarga automatica del IPC.** Bloqueada por el entorno, no por diseno.
- **Comparacion automatica entre ediciones.** El agente procesa una edicion por
  corrida. Comparar dos requiere la variante B del user prompt (base forzada) y
  cruzar los JSON a mano.
- **Publicacion.** El dashboard se genera como archivo; distribuirlo es manual y
  deliberadamente L0.

---

## Errores que el sistema todavia puede cometer

1. Si el BCRA cambia por tercera vez el patron de URL, el agente reporta error y no
   procesa. Falla ruidosa, que es la buscada.
2. Si el BCRA cambia la redaccion de la nota al pie mas alla de lo previsto, el
   agente cae al corte segun Excel sin declararlo como conflicto. Es el punto ciego
   mas serio que queda abierto.
3. Si el INDEC corrige una variacion del IPC ya publicada, el JSON del deflactor
   queda desactualizado sin que nada lo detecte.
4. Si una edicion trae una serie nueva dentro de una pestania conocida, se ignora en
   silencio: el mapeo por encabezado solo levanta los grupos declarados en
   `PESTANIAS`.

---

## Iteracion 8 — El dashboard no se entendia

Primera version del dashboard: una cifra grande por serie, una linea sin ejes y una
tabla plegada. Se rehizo entero tras una revision. Los tres problemas:

**No se podia leer magnitud.** La linea no tenia eje y, ni marcas, ni unidad. Se veia
la forma de la serie pero no su nivel. Ahora todos los graficos tienen eje y con
marcas redondas, unidad declarada y eje x con meses.

**Las metricas aparecian sin decir que significaban.** "Participacion", "ticket
promedio real" y "var. i.a." estaban como rotulos sueltos. Ahora cada metrica lleva
su explicacion en una linea al lado del numero, y hay un glosario al pie que define
pesos corrientes contra constantes, variacion interanual y mes de corte.

**Faltaba lo unico que justifica el sistema.** El dashboard mostraba solo la serie
real, sin la nominal. Pero el argumento entero del proyecto es que las dos difieren:
sin verlas juntas, el trabajo de deflactar es invisible. El grafico principal ahora
superpone ambas y sombrea la franja entre ellas. En tarjetas de credito esa franja
dice todo: los montos corrientes subieron 72 % en 24 meses y el movimiento real cayo
4 %.

Se agrego ademas un titular en palabras arriba de todo, armado con plantilla a partir
de las cifras del JSON —no generado por un modelo—, y una barra de composicion por
pestania.

---

## Iteracion 9 — Una serie estaba en dolares y se estaba deflactando por IPC argentino

Al revisar la escala de los graficos aparecio que `Tarjetas de débito (dólares)` se
mostraba como "0,00 billones". Al corregir la unidad quedo expuesto el error de
fondo: **esa serie no esta en pesos.** La nota (4) del informe lo dice:

```
(4) El monto nominal se encuentra expresado en dólares estadounidenses.
```

El agente le estaba aplicando el IPC argentino y rotulando el resultado como "pesos
de junio de 2026". El numero resultante no significa nada: deflactar dolares por
inflacion argentina no produce dolares constantes ni pesos constantes.

**Correccion.** Las series con moneda distinta de ARS se marcan con un campo
`moneda`, quedan excluidas de la deflactacion (`monto_real` y `var_ia_monto_real` en
`null`) y se publican solo en nominal, en su moneda de origen. El dashboard les da un
panel distinto que explica por que no hay serie real.

**Por que no lo detecto la validacion cruzada.** El control contra el PDF cubre
credito y debito en pesos, que son las cifras que el BCRA declara en el texto. La
serie en dolares no entra en ese contraste, asi que el error paso por un mecanismo
disenado justamente para atrapar errores. Es una limitacion real de la validacion:
solo verifica lo que el informe declara en prosa, y no todo lo que se calcula esta
declarado.

---

## Iteracion 10 — Notas contra advertencias

La correccion anterior genero una advertencia en todas las corridas, lo que ponia
`requiere_revision_humana: true` de forma permanente. Una senal que se enciende
siempre deja de ser una senal.

Se separo en dos campos. **Nota:** condicion estructural y permanente que el lector
debe conocer y que no requiere accion —la serie en dolares queda fuera de la
deflactacion—. **Advertencia:** algo que salio distinto de lo esperado en esta
corrida y que alguien tiene que mirar. Solo las advertencias disparan revision.

---

## Iteracion 11 — De tablero a exhibits: titulos de accion

Segunda revision del dashboard. La observacion fue que no era ejecutivo: los graficos
estaban bien pero cada bloque se titulaba con el nombre de la serie, no con lo que la
serie decia. Un lector tenia que deducir el hallazgo.

Se reescribio con formato de exhibit. Los tres cambios de fondo:

**Titulos de accion.** Cada bloque se encabeza con una afirmacion, no con un rotulo.
`Tarjetas de crédito` paso a ser `Tarjetas de crédito cae 10,2 % real interanual pero
las operaciones crecen 1,6 %: cada compra es mas chica`. El titulo se compone con
plantilla desde el JSON.

El primer intento produjo catorce titulos con la misma estructura —"cae X % real,
pese a subir Y % en pesos corrientes"— porque la brecha nominal/real es grande en
todas las series. Titulos identicos con numeros distintos no informan. Se reemplazo
por una escalera de umbrales que elige el hallazgo dominante de cada serie: primero
la divergencia entre cantidad y monto real, despues el movimiento del ticket, despues
la brecha nominal, y recien al final la participacion. Con eso los catorce titulos
dicen cosas distintas.

**Sintesis ejecutiva arriba de todo.** Tres mensajes numerados antes de cualquier
grafico, seguidos de una franja de cuatro indicadores de nivel informe.

**Agregados calculados en `pmr.py`, no en el dashboard.** La sintesis necesita totales
de nivel informe (monto de tarjetas, variacion interanual del agregado, brecha de la
serie lider). Se agrego un bloque `resumen` a `salida.json` en vez de sumarlos en el
generador de HTML, para no romper la separacion de la iteracion 5.

**Paleta.** Se reemplazo el verde por azul profundo con acento cian y rojo solo para
valores negativos.

Un detalle de idioma que salio en la revision: las frases se arman por concatenacion y
producian "del monto de el consumo con tarjetas". Se agrego una funcion de contraccion.
Es menor, pero en un informe que va a leer un directorio, la gramatica es parte del
producto.

---

## Iteracion 12 — Cifras ilegibles, grafico de mas y paleta

Tercera revision del dashboard, sobre capturas de pantalla. Cuatro correcciones.

**Las barras de composicion no se leian.** Los porcentajes salian deformados,
estirados en horizontal hasta volverse ilegibles. La causa: la barra estaba hecha en
SVG con `viewBox="0 0 100 30"` y `preserveAspectRatio="none"`, que es lo que hace que
la barra ocupe todo el ancho disponible. Ese estirado se aplica tambien a la
tipografia, asi que la letra se deforma junto con el rectangulo.

Se reemplazo por HTML: un contenedor `flex` con un `div` por segmento y el ancho en
porcentaje. Misma barra, sin distorsion, y ademas accesible. **Leccion general:** un
SVG con `preserveAspectRatio="none"` no debe contener texto nunca.

**Se elimino el grafico de brecha nominal contra real.** Era el grafico principal de
la version anterior. La observacion fue que la diferencia entre pesos corrientes y
constantes es obvia y no necesita ocupar el exhibit principal. Se reemplazo por
barras del monto real mes a mes. Con eso desaparecieron tambien las comparaciones
nominal/real de los titulos de accion, de la sintesis y de la tabla de detalle: el
informe entero esta en pesos constantes y no discute mas el punto.

El efecto sobre los titulos fue bueno. Antes, la brecha nominal ganaba la escalera de
umbrales en varias series y producia titulos repetidos; al sacarla, esas series pasan
a titularse por la divergencia entre operaciones y monto, que es un hallazgo real:
"cae 10,2 % real pero las operaciones crecen 1,6 %: cada compra es mas chica".

**El contraste PDF contra Excel se movio al final.** Estaba como Exhibit 1. Es un
control de consistencia, no un hallazgo de negocio: va despues de los datos, en su
propia seccion.

**Paleta.** Se adopto la paleta corporativa indicada: azul profundo, azul electrico,
cian y negro sobre fondo gris claro, con los exhibits en blanco.

---

## Iteracion 13 — Ticket promedio real como tercer grafico

Cada exhibit de serie en pesos pasa a tener tres graficos: monto real mes a mes a la
izquierda, y en columna a la derecha la variacion interanual real y, debajo, el ticket
promedio real mes a mes.

**Por que agrega.** El monto real puede caer por dos motivos distintos: porque se
opera menos veces o porque cada operacion es mas chica. Los dos primeros graficos no
distinguen entre ambos. El ticket lo resuelve de un vistazo, y en esta edicion resulta
ser el hallazgo: en tarjetas de credito el monto real cae 10,2 % interanual mientras
las operaciones crecen 1,6 %, asi que toda la caida viene del tamano de cada compra.

**Implementacion.** Se generalizo el generador de barras: antes leia `monto_real` de
forma fija, ahora recibe el nombre del campo, su escala y sus decimales. El mismo
codigo dibuja monto y ticket. Se agrego una escala propia para el ticket porque vive
en un orden de magnitud muy distinto del monto operado: billones de pesos contra
decenas de miles.

Las barras arrancan en cero, tambien en el ticket. Truncar el eje habria hecho mas
visible la variacion mes a mes, pero exagera diferencias pequenas; en un grafico de
barras el area es la que comunica, y un area truncada miente.

---

## Iteracion 14 — Codificacion de color de los graficos

Ajuste de lectura sobre los graficos de la iteracion 13.

**Variacion interanual real:** verde para valores positivos, rojo para negativos, en
lugar de cian y azul oscuro. La convencion contable es inmediata y no obliga a leer la
referencia.

**Ticket promedio real:** gris intermedio, con la ultima barra en un gris mas oscuro.
El ticket es contexto que explica el movimiento del monto, no un indicador principal;
dejarlo en la misma intensidad que el monto operado competia por la atencion sin
motivo.

Queda entonces una jerarquia de color deliberada: azul electrico para el monto real,
que es la serie protagonista; verde y rojo para el juicio sobre esa serie; gris para
el dato de apoyo.

---

## Iteracion 15 — Declarar el alcance de las aperturas de credito

Los exhibits de la pestania `Tarjeta de credito por canal` se titulan con el nombre
del canal: "e-commerce cae 3,9 % real interanual...". Leido suelto, fuera de su
seccion, se entiende como si cubriera todo el e-commerce con tarjetas. Cubre solo la
apertura de credito: el debito tiene su propia distribucion por canal y no esta en
esa pestania.

Se agrego una etiqueta de alcance debajo del numero de exhibit —"Solo tarjetas de
credito, por canal"— y la misma aclaracion al cierre del texto al pie. Aplica tambien
a `TC Modalidad de pago`, que tiene exactamente el mismo problema: "un pago" y "en
cuotas" son aperturas de credito, no del total de tarjetas.

**Por que importa mas de lo que parece.** Un exhibit de este informe puede terminar
pegado en un mail o en una presentacion, separado de la seccion que lo encabeza. El
titulo de accion, que es lo que lo hace legible aislado, es tambien lo que lo hace
peligroso aislado: afirma algo sin declarar sobre que universo. La etiqueta viaja con
el exhibit.

---

## Iteracion 16 — Marca en el encabezado

Se agrego el logo institucional al margen superior derecho de la portada. Es blanco
sobre transparente, asi que apoya bien sobre el azul profundo del encabezado sin
necesidad de version alternativa.

Tres decisiones de implementacion:

**Recortado al contenido.** El PNG original tenia 990 x 330 px con margenes
transparentes amplios: el arte ocupaba 706 x 119 px en el centro. Insertado tal cual,
la caja del logo habria sido casi tres veces mas alta que el logo visible y habria
descolocado la alineacion. Se recorto al bounding box del canal alfa y se
redimensiono a 96 px de alto, que da nitidez en pantallas de densidad doble.

**Incrustado en base64.** El logo va dentro del HTML, no como archivo aparte.
`dashboard.html` sigue siendo un unico archivo portable: se puede adjuntar a un mail o
mover de carpeta sin que se rompa la imagen. Costo: unos 26 KB por dashboard, que a
esta escala no es nada.

**El archivo fuente vive en `agente/marca/logo.png`.** Reemplazarlo ahi alcanza para
cambiar la marca en todos los dashboards; el generador lo lee en cada corrida. Si el
archivo no esta, el encabezado se arma igual sin logo en vez de fallar.

---

## Iteracion 17 — Cuarta pestania, y el bug que aparecio con ella

Se amplio el alcance a `Transferencias de fondos`, tomando las dos series del Grafico
2 del informe: transferencias inmediatas "push" y pagos con transferencia
interoperables (PCT). Ademas se extendieron las tablas de detalle de 12 a 24 meses y se
agrego un indice navegable.

**El horizonte pasa a calcularse por pestania.** Las transferencias llegan al mes de
analisis; tarjetas, un mes antes. Con un unico rango para todo el informe, julio 2026
se habria descartado en silencio. Ahora cada pestania corre hasta su propio ultimo
dato y cada serie declara su `mes_corte`. La base de pesos constantes sigue siendo una
sola para todo el informe —el corte de tarjetas—, porque si cada bloque tuviera su
propia base las cifras dejarian de ser comparables entre secciones.

**El bug.** La primera corrida con la pestania nueva dio, para PCT, una caida
interanual de 23,2 % en cantidades. El PDF declara un crecimiento de **70,7 %**. Los
signos ni siquiera coincidian.

La causa esta en como se propagan los encabezados. Esa pestania tiene tres filas de
cabecera: la primera declara familias ("Transferencias de alto valor entre empresas"),
la segunda los grupos ("Pagos con transferencia interoperables"), la tercera
Cantidad/Monto. El parser propagaba el nombre de grupo de la fila 2 hacia la derecha
para cubrir celdas combinadas, pero como PCT es el ultimo nombre declarado en esa
fila, su nombre se derramaba sobre las columnas 9 a 16, que pertenecen a familias
declaradas recien en la fila 1. Y como el mapeo se quedaba con la ultima coincidencia,
PCT terminaba leyendo "Transferencias en lote (dolares)".

Dos correcciones, ambas en `leer_pestania`:

1. La propagacion se corta donde la fila superior declara un grupo nuevo.
2. Ante nombres repetidos gana la **primera** coincidencia, no la ultima.

Corregido, PCT da 70,72 % contra 70,7 % declarado.

**Lo importante no es el bug: es que lo encontro el mecanismo de control.** En la
iteracion 9 quedo registrado que la validacion cruzada no habia detectado el error de
la serie en dolares, porque el PDF no declara esa cifra en prosa. Aca paso lo
contrario. El PDF si declara las variaciones de push y PCT, se agregaron al set de
validacion, y el contraste marco la diferencia de inmediato. La corrida de julio 2026
pasa ahora **ocho** comparaciones —cuatro de tarjetas, cuatro de transferencias— con
un desvio maximo de 0,05 pp.

Eso confirma la tesis del diseno y tambien su limite: el control vale exactamente para
lo que el informe enuncia en prosa. Cada cifra que el BCRA declara y se agrega al set
es superficie protegida; el resto sigue sin verificar.

**Indice navegable.** Debajo del encabezado se agrego un menu con un enlace por
exhibit, agrupado por seccion. `TC Modalidad de pago` entra con un unico enlace a la
seccion en lugar de uno por exhibit, segun lo pedido.

---

## Iteracion 18 — Navegacion

Dos ajustes de uso sobre el indice de la iteracion 17.

`TC Modalidad de pago` salio del indice por completo. En la iteracion anterior entraba
con un unico enlace a la seccion; ahora no aparece. Sus exhibits siguen en el
documento y se llegan desplazandose.

Cada exhibit cierra con un enlace "Volver arriba" que lleva al indice, alineado a la
derecha de la linea de fuente. Con dieciseis exhibits y tablas de veinticuatro meses,
el documento es largo y volver al indice sin ese enlace obliga a un desplazamiento
incomodo.

En la corrida en error no se dibuja indice, y por lo tanto tampoco enlaces a el: no
habria a donde volver. Se verifico que ninguna de las tres corridas quede con anclas
apuntando a un destino inexistente.

---

## Iteracion 19 — Dos mensajes de ticket, y una cifra inventada

La sintesis ejecutiva pasa de cuatro a seis mensajes. Los dos nuevos comparan el
ticket promedio real de dos series de la misma pestania en el ultimo mes: credito
contra debito, y cuotas contra un pago. Ambas comparaciones son limpias porque las
series comparadas comparten corte y base, asi que el cociente es directo.

**El error que se colo y como se corrigio.** La primera version cerraba cada mensaje
con una frase interpretativa escrita a mano. La de cuotas decia: "las cuotas explican
una de cada cinco operaciones de credito". El dato real es una de cada ocho: 20,9
millones sobre 176,2 millones, un 11,9 %.

Nadie lo habia calculado. Era una frase plausible escrita junto al numero, y por eso
mismo dificil de ver: no contradecia nada visible en la misma pantalla.

Se elimino el texto fijo. El cierre de ambos mensajes se deriva ahora de los datos:
cuanto pesa la serie de ticket alto en operaciones frente a cuanto pesa en monto. Da
"11,9 % de las operaciones pero 35,2 % del monto", que ademas dice mas que la frase
original.

**La regla que queda.** Ninguna afirmacion cuantitativa del dashboard puede ser texto
fijo. Si menciona una proporcion, sale del JSON. Es la misma separacion de la
iteracion 5 —el dashboard no recalcula— llevada un paso mas: el dashboard tampoco
afirma nada que no pueda mostrar.

---

## Iteracion 20 — La flecha que se leia como "91"

El enlace "Volver arriba" se dibujaba con una flecha hacia arriba puesta con
`content:"\2191"` en un pseudoelemento `::before`. En pantalla salia un cuadrado vacio
seguido de "91".

La causa es de escapes anidados. La hoja de estilos vive dentro de una cadena de
Python, asi que la barra invertida hay que escribirla doblada para que llegue una sola
al CSS. Con el nivel de escape mal contado, el navegador recibio algo que no
interpreto como el caracter U+2191 y termino tomando parte de la secuencia como texto
literal.

Se elimino la flecha. El enlace dice solo "Volver arriba", que era lo unico que hacia
falta. Un caracter decorativo no justifica una construccion fragil, y menos una que
depende de contar barras invertidas entre dos lenguajes.

---

## Iteracion 21 — Auditoria externa: siete hallazgos, siete correcciones

Se sometio el repo completo a un agente evaluador externo, junto con la consigna de la
materia. Devolvio siete criticas. **Las siete eran ciertas.** Ninguna era un falso
positivo. Se verificaron una por una contra el repo antes de corregir.

Comparten una sola causa de fondo, que la auditoria no nombra: **veinte iteraciones
actualizando el codigo y este archivo, sin volver sobre el contrato ni sobre los
`entrada.md`.** Deriva documental. La ironia es que el proyecto entero existe para que
dos fuentes que deberian decir lo mismo digan lo mismo, y fallo exactamente ahi.

### 1 · `entrada.md` describia una version anterior del sistema

Decia "las cuatro comparaciones cerraron dentro de tolerancia" cuando el `salida.json`
de la misma carpeta ya tenia ocho, desde la iteracion 17. Un tercero leyendo la carpeta
se llevaba una descripcion desactualizada del resultado que tenia al lado.

**Correccion estructural, no cosmetica.** Corregir el texto a mano habria repetido el
problema en la proxima iteracion. Ahora `entrada.md` **lo genera `pmr.py`** a partir de
la corrida: estado, corte, base, cantidad de series, resultado del contraste, notas y
advertencias salen del JSON. Lo unico escrito a mano es el proposito, que se pasa por
`--proposito`. La deriva pasa a ser imposible por construccion.

### 2 · El contrato no declaraba su propia salida

El ejemplo del §5 no incluia `resumen`, `descarga`, `cita_pdf`,
`mes_corte_segun_excel`, `moneda` ni `mes_corte`: seis campos que el sistema emitia
desde iteraciones anteriores. El contrato es la vara contra la que un evaluador valida
el formato; si validaba literalmente, encontraba campos "no contractuales".

Se completo el esquema en los nueve niveles y se agrego la regla: no se agregan claves
sin actualizar antes el contrato.

### 3 · El estado `ok_con_advertencias` nunca se demostraba

El contrato declara tres estados y una tabla L0-L4 donde la supervision L1 depende del
tercero. Las corridas eran `ok`, `ok`, `error`.

Se agrego una cuarta corrida, `2026-04-base-forzada`, con la variante B del user prompt.
Produce `ok_con_advertencias`, `requiere_revision_humana: true` y el banner visible en
el dashboard.

**Lo que no se hizo:** bajar la tolerancia hasta que algo disparara. Eso seria fabricar
evidencia. Y queda dicho en el `entrada.md` de esa corrida: ninguna edicion real probada
produjo una discrepancia mayor a 0,5 pp, los desvios observados van de 0,00 a 0,05 pp,
asi que ese otro disparador de L1 no se puede demostrar sin inventar el dato.

### 4 · La "serie lider" no era la de mayor brecha

`resumen.brecha_nominal_real` fijaba tarjetas de credito, que con 76,1 pp es la de
**menor** brecha entre las siete principales; PCT interoperables tiene 194,6. El nombre
del campo sugeria un criterio de magnitud que no era el usado.

Aca la correccion fue mas alla de lo senalado: desde la iteracion 12, cuando se
eliminaron las comparaciones nominal contra real, **el dashboard ya no lee ese campo**.
Era codigo muerto. No habia que renombrarlo ni documentarlo: habia que borrarlo.

### 5 · `participacion: null` sin regla escrita

Las dos series de transferencias traen `null` en los 24 periodos. Era intencional
—se cubren dos series de una pestania que tiene muchas mas, y un porcentaje entre ellas
no representaria nada— pero la decision vivia solo en un comentario del codigo. Se
escribio la regla en el contrato: `null` ahi es una decision declarada, no un calculo
pendiente.

### 6 y 7 · Higiene

`cita_pdf` conservaba los saltos de linea que mete `pdftotext`; se normaliza el
espaciado. `descarga` registraba `url_pdf` pero no `url_xlsx`; ahora registra las dos.

### Lo que deja esta iteracion

Un sistema que valida dos fuentes entre si puede desincronizarse internamente sin que
ninguno de sus controles lo note. Los ocho contrastes contra el PDF seguian pasando con
0,05 pp mientras el contrato describia una salida que ya no existia. **El control
cubria los numeros y no cubria los documentos.**

Por eso la correccion del punto 1 fue generar `entrada.md` en vez de reescribirlo: la
unica defensa duradera contra la deriva documental es que el documento no se escriba
a mano.
