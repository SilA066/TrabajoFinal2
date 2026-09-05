# user_prompt.md — Agente PMR

> Plantilla de invocación. Se completa `{EDICION}` y se ejecuta sin más contexto: todo lo demás vive en el system prompt.

---

## Plantilla base

```
Procesá la edición {EDICION} del Informe Mensual de Pagos Minoristas del BCRA.

Horizonte: 24 meses hacia atrás desde el mes de corte de tarjetas.
Base de pesos constantes: mes de corte de tarjetas de esta edición.
Pestañas: Tarjetas, TC Modalidad de pago, Tarjeta de credito por canal, Transferencias de fondos.

Devolvé el JSON del contrato. Nada más.
```

---

## Variante A — Corrida estándar

Uso: procesamiento mensual de la edición nueva.

```
Procesá la edición 2026-07 del Informe Mensual de Pagos Minoristas del BCRA.

Horizonte: 24 meses hacia atrás desde el mes de corte de tarjetas.
Base de pesos constantes: mes de corte de tarjetas de esta edición.
Pestañas: Tarjetas, TC Modalidad de pago, Tarjeta de credito por canal, Transferencias de fondos.

Devolvé el JSON del contrato. Nada más.
```

---

## Variante B — Corrida con base forzada

Uso: cuando se necesita comparar dos ediciones en la misma unidad de medida. Rompe la regla por defecto de "base = mes de corte", y por eso el contrato exige que quede registrado en las advertencias.

```
Procesá la edición 2026-04 del Informe Mensual de Pagos Minoristas del BCRA.

Horizonte: 24 meses hacia atrás desde el mes de corte de tarjetas.
Base de pesos constantes: FORZADA a 2026-06.
Pestañas: Tarjetas, TC Modalidad de pago, Tarjeta de credito por canal, Transferencias de fondos.

Registrá en `advertencias` que la base fue forzada y no corresponde
al mes de corte de esta edición.

Devolvé el JSON del contrato. Nada más.
```

---

## Variante C — Prueba de resistencia

Uso: verificar que el agente detiene la corrida en vez de improvisar. Se invoca contra una edición inexistente.

```
Procesá la edición 2026-08 del Informe Mensual de Pagos Minoristas del BCRA.

Horizonte: 24 meses hacia atrás desde el mes de corte de tarjetas.
Base de pesos constantes: mes de corte de tarjetas de esta edición.
Pestañas: Tarjetas, TC Modalidad de pago, Tarjeta de credito por canal, Transferencias de fondos.

Devolvé el JSON del contrato. Nada más.
```

Salida esperada: `estado: "error"`, con el diagnóstico de que ambos archivos devolvieron HTTP 404 bajo los dos patrones de URL conocidos. **No** debe devolver la edición anterior como sustituto silencioso.

---

## Notas de uso

El user prompt no repite reglas del system prompt. Si una corrida necesita una regla nueva, esa regla va al system prompt y queda versionada en `DECISIONES.md` — no se parcha desde acá. Es la razón por la que estas tres variantes son casi idénticas: el contrato hace el trabajo, la invocación solo aporta parámetros.
