# Corrida — edicion 2026-04 (base forzada)

- **Fecha de ejecucion:** 2026-09-05
- **Contrato aplicado:** `prompts/system_prompt.md`
- **Variante de user prompt:** B (base forzada)

## Proposito

Ejercitar la ruta de advertencia y el nivel de supervision L1. Se fuerza la base de
pesos constantes a un mes que no es el corte de esta edicion, que es exactamente el
caso que el contrato manda declarar.

**Comportamiento esperado:** `estado: ok_con_advertencias`, `requiere_revision_humana:
true`, y la advertencia visible en el encabezado del dashboard, no en una nota al pie.

Sin esta corrida el estado `ok_con_advertencias` quedaba declarado en el contrato pero
nunca demostrado. Aclaracion honesta: **ninguna edicion real probada produjo una
discrepancia mayor a 0,5 pp contra el PDF**, asi que ese otro disparador de L1 no se
puede demostrar sin fabricar el dato. Los desvios observados van de 0,00 a 0,05 pp.

## Prompt enviado

```
Procesa la edicion 2026-04 del Informe Mensual de Pagos Minoristas del BCRA.

Horizonte: 24 meses hacia atras desde el mes de corte de cada pestania.
Base de pesos constantes: FORZADA a 2026-06.
Pestanias: Tarjetas, TC Modalidad de pago, Tarjeta de credito por canal,
Transferencias de fondos.

Devolve el JSON del contrato. Nada mas.
```

## Comando ejecutado

```
python3 agente/pmr.py 2026-04 --base 2026-06 --out corridas/2026-04-base-forzada
python3 agente/dashboard.py corridas/2026-04-base-forzada/salida.json
```

## Insumos

- `series-2026-04.xlsx` — 166809 bytes, application/vnd.openxmlformats-officedocument.spreadsheetml.sheet
  desde https://www.bcra.gob.ar/archivos/Pdfs/PublicacionesEstadisticas/informes/series-informe-mensual-pagos-minoristas-2026-04.xlsx
- `informe-2026-04.pdf` — 615293 bytes, application/pdf
  desde https://www.bcra.gob.ar/archivos/Pdfs/PublicacionesEstadisticas/informes/informe-mensual-pagos-minoristas-2026-04.pdf

Ambos quedan guardados en esta carpeta para que la corrida sea reconstruible aunque el BCRA modifique o retire los archivos.

## Resultado

`estado: ok_con_advertencias`. `requiere_revision_humana: true`.

Corte de tarjetas **2026-03**, tomado de la nota al pie 1 del PDF y coincidente con la ultima fila de la pestania `Tarjetas`.

Base de pesos constantes: **2026-06**.

Se emitieron **12 series** sobre 4 pestanias.

Contraste contra el PDF: **6 de 6** comparaciones dentro de tolerancia, desvio maximo **0.03 pp**.

**Nota:** Serie en moneda extranjera excluida de la deflactacion: Tarjetas de débito (dólares). El monto nominal esta en dolares (nota 4 del informe); aplicarle el IPC argentino produciria una cifra sin significado. Se publica solo el nominal en USD.

**Advertencia:** Base de pesos constantes forzada a 2026-06; no corresponde al mes de corte de esta edicion (2026-03). Las cifras no son comparables con una corrida de base por defecto.

Salida: `salida.json`, `dashboard.html`.

---

*Este archivo lo genera `agente/pmr.py` a partir de la corrida, no se escribe a mano.
Ver DECISIONES.md, iteracion 21.*
