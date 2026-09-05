# Corrida — edicion 2026-08

- **Fecha de ejecucion:** 2026-09-05
- **Contrato aplicado:** `prompts/system_prompt.md`
- **Variante de user prompt:** A (corrida estandar)

## Proposito

Prueba de resistencia. La edicion de agosto 2026 no estaba publicada al momento de la
corrida: el BCRA publica el ultimo viernes de cada mes y la edicion vigente era la de
julio. Se invoca deliberadamente contra una edicion inexistente.

**Comportamiento inaceptable:** devolver la edicion de julio como sustituto silencioso,
o emitir series vacias con `estado: ok`.

## Prompt enviado

```
Procesa la edicion 2026-08 del Informe Mensual de Pagos Minoristas del BCRA.

Horizonte: 24 meses hacia atras desde el mes de corte de cada pestania.
Base de pesos constantes: mes de corte de tarjetas de esta edicion.
Pestanias: Tarjetas, TC Modalidad de pago, Tarjeta de credito por canal,
Transferencias de fondos.

Devolve el JSON del contrato. Nada mas.
```

## Comando ejecutado

```
python3 agente/pmr.py 2026-08 --out corridas/2026-08-inexistente
python3 agente/dashboard.py corridas/2026-08-inexistente/salida.json
```

## Insumos

- `series-2026-08.xlsx` — no se pudo descargar https://www.bcra.gob.ar/archivos/Pdfs/PublicacionesEstadisticas/informes/series-informe-mensual-pagos-minoristas-2026-08.xlsx (HTTPError)
  desde https://www.bcra.gob.ar/archivos/Pdfs/PublicacionesEstadisticas/informes/series-informe-mensual-pagos-minoristas-2026-08.xlsx
- `informe-2026-08.pdf` — no se pudo descargar https://www.bcra.gob.ar/archivos/Pdfs/PublicacionesEstadisticas/informes/informe-mensual-pagos-minoristas-2026-08.pdf (HTTPError) | no se pudo descargar https://www.bcra.gob.ar/archivos/Pdfs/PublicacionesEstadisticas/informes/informe-pagos-minoristas-2026-08.pdf (HTTPError)
  desde None

Ambos quedan guardados en esta carpeta para que la corrida sea reconstruible aunque el BCRA modifique o retire los archivos.

## Resultado

`estado: error`. `requiere_revision_humana: true`.

No hubo contraste contra el PDF en esta corrida.

**Error:** Descarga fallida. XLSX: no se pudo descargar https://www.bcra.gob.ar/archivos/Pdfs/PublicacionesEstadisticas/informes/series-informe-mensual-pagos-minoristas-2026-08.xlsx (HTTPError). PDF: no se pudo descargar https://www.bcra.gob.ar/archivos/Pdfs/PublicacionesEstadisticas/informes/informe-mensual-pagos-minoristas-2026-08.pdf (HTTPError) | no se pudo descargar https://www.bcra.gob.ar/archivos/Pdfs/PublicacionesEstadisticas/informes/informe-pagos-minoristas-2026-08.pdf (HTTPError). Se probaron los dos patrones de URL conocidos del BCRA. La edicion probablemente no esta publicada.

---

*Este archivo lo genera `agente/pmr.py` a partir de la corrida, no se escribe a mano.
Ver DECISIONES.md, iteracion 21.*
