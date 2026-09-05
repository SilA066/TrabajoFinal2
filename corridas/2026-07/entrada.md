# Corrida — edicion 2026-07

- **Fecha de ejecucion:** 2026-09-05
- **Contrato aplicado:** `prompts/system_prompt.md`
- **Variante de user prompt:** A (corrida estandar)

## Proposito

Corrida estandar sobre la edicion vigente al momento de la entrega. Es la referencia
del sistema funcionando de punta a punta.

## Prompt enviado

```
Procesa la edicion 2026-07 del Informe Mensual de Pagos Minoristas del BCRA.

Horizonte: 24 meses hacia atras desde el mes de corte de cada pestania.
Base de pesos constantes: mes de corte de tarjetas de esta edicion.
Pestanias: Tarjetas, TC Modalidad de pago, Tarjeta de credito por canal,
Transferencias de fondos.

Devolve el JSON del contrato. Nada mas.
```

## Comando ejecutado

```
python3 agente/pmr.py 2026-07 --out corridas/2026-07
python3 agente/dashboard.py corridas/2026-07/salida.json
```

## Insumos

- `series-2026-07.xlsx` — 168842 bytes, application/vnd.openxmlformats-officedocument.spreadsheetml.sheet
  desde https://www.bcra.gob.ar/archivos/Pdfs/PublicacionesEstadisticas/informes/series-informe-mensual-pagos-minoristas-2026-07.xlsx
- `informe-2026-07.pdf` — 542928 bytes, application/pdf
  desde https://www.bcra.gob.ar/archivos/Pdfs/PublicacionesEstadisticas/informes/informe-mensual-pagos-minoristas-2026-07.pdf

Ambos quedan guardados en esta carpeta para que la corrida sea reconstruible aunque el BCRA modifique o retire los archivos.

## Resultado

`estado: ok`. `requiere_revision_humana: false`.

Corte de tarjetas **2026-06**, tomado de la nota al pie 1 del PDF y coincidente con la ultima fila de la pestania `Tarjetas`.

Base de pesos constantes: **2026-06**.

Se emitieron **12 series** sobre 4 pestanias.

Contraste contra el PDF: **8 de 8** comparaciones dentro de tolerancia, desvio maximo **0.05 pp**.

**Nota:** Serie en moneda extranjera excluida de la deflactacion: Tarjetas de débito (dólares). El monto nominal esta en dolares (nota 4 del informe); aplicarle el IPC argentino produciria una cifra sin significado. Se publica solo el nominal en USD.

Salida: `salida.json`, `dashboard.html`.

---

*Este archivo lo genera `agente/pmr.py` a partir de la corrida, no se escribe a mano.
Ver DECISIONES.md, iteracion 21.*
