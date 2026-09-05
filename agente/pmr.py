#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Agente PMR (Pagos Minoristas Reales) - capa de herramientas.

Implementa los pasos 1 a 8 del contrato (prompts/system_prompt.md).
El modelo de lenguaje no interviene en el calculo: interviene en la lectura
de la nota al pie del PDF y en la redaccion del resumen. Todo lo demas es
deterministico, para que un tercero pueda reconstruir cualquier corrida.

Uso:
    python3 agente/pmr.py 2026-07 [--base YYYY-MM] [--out DIR]
"""

import argparse
import datetime as dt
import json
import os
import re
import subprocess
import sys
import urllib.request

BASE = "https://www.bcra.gob.ar/archivos/Pdfs/PublicacionesEstadisticas/informes"
URL_XLSX = BASE + "/series-informe-mensual-pagos-minoristas-{ed}.xlsx"
URL_PDF = BASE + "/informe-mensual-pagos-minoristas-{ed}.pdf"
URL_PDF_LEGADO = BASE + "/informe-pagos-minoristas-{ed}.pdf"

MIN_BYTES = 50_000
TOLERANCIA_PP = 0.5
HORIZONTE = 24

# Series que NO estan denominadas en pesos. El informe lo declara en la nota (4):
# "El monto nominal se encuentra expresado en dolares estadounidenses". Deflactarlas
# por IPC argentino y rotularlas en pesos seria un error (ver DECISIONES.md, it. 9).
MONEDA_NO_ARS = {"Tarjetas de débito (dólares)": "USD"}

PESTANIAS = {
    "Tarjetas": ["Tarjetas de crédito", "Tarjetas de débito",
                 "Tarjetas de débito (dólares)", "Tarjetas prepagas"],
    "TC Modalidad de pago": ["Un pago", "En Cuotas"],
    "Tarjeta de credito por canal": ["e-commerce", "POS+QR",
                                     "Debito Automatico", "Otros"],
    # Cuarta pestania (ver DECISIONES.md, it. 17). Ojo: sus datos llegan al mes de
    # analisis, un mes mas adelante que tarjetas. Por eso el rango se calcula por
    # pestania y no una sola vez para todo el informe.
    "Transferencias de fondos": ['Transferencias inmediatas "push"',
                                 "Pagos con transferencia interoperables"],
}

# Pestanias donde una participacion seria enganosa: no se cubren todas sus series,
# asi que los porcentajes no sumarian el universo.
SIN_PARTICIPACION = {"Transferencias de fondos"}

AQUI = os.path.dirname(os.path.abspath(__file__))


# --------------------------------------------------------------------------
# Paso 1 - descarga con validacion de content-type y tamanio
# --------------------------------------------------------------------------

def bajar(url, destino, mime_esperado):
    """Devuelve (ok, detalle). No levanta excepcion: el contrato exige que un
    fallo de descarga sea una salida estructurada, no un stacktrace."""
    req = urllib.request.Request(url, headers={"User-Agent": "agente-pmr/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            ctype = r.headers.get("Content-Type", "")
            datos = r.read()
    except Exception as e:  # incluye HTTPError 404
        return False, "no se pudo descargar %s (%s)" % (url, type(e).__name__)

    if mime_esperado not in ctype:
        return False, "content-type inesperado en %s: %s" % (url, ctype)
    if len(datos) < MIN_BYTES:
        return False, "archivo demasiado chico en %s: %d bytes" % (url, len(datos))

    with open(destino, "wb") as f:
        f.write(datos)
    return True, "%d bytes, %s" % (len(datos), ctype)


def bajar_pdf(ed, destino):
    """Intenta el patron vigente y, si falla, el patron legado.
    El BCRA cambio la nomenclatura entre ediciones (ver DECISIONES.md, it. 2)."""
    ok, det = bajar(URL_PDF.format(ed=ed), destino, "application/pdf")
    if ok:
        return True, URL_PDF.format(ed=ed), det
    ok2, det2 = bajar(URL_PDF_LEGADO.format(ed=ed), destino, "application/pdf")
    if ok2:
        return True, URL_PDF_LEGADO.format(ed=ed), det2 + " (patron legado)"
    return False, None, "%s | %s" % (det, det2)


# --------------------------------------------------------------------------
# Paso 2 - corte temporal declarado por el PDF
# --------------------------------------------------------------------------

MESES = {"enero": 1, "febrero": 2, "marzo": 3, "abril": 4, "mayo": 5, "junio": 6,
         "julio": 7, "agosto": 8, "septiembre": 9, "setiembre": 9, "octubre": 10,
         "noviembre": 11, "diciembre": 12}


def texto_pdf(path):
    try:
        return subprocess.run(["pdftotext", path, "-"], capture_output=True,
                              text=True, timeout=120).stdout
    except Exception:
        return ""


def corte_declarado(texto):
    """Lee la nota al pie 1: '... tarjetas ... corresponde a <mes> de <anio>'."""
    m = re.search(
        r"tarjetas[^.]{0,400}?informaci[oó]n corresponde a\s+([a-zA-Záéíóú]+)\s+de\s+(\d{4})",
        texto, re.I | re.S)
    if not m:
        return None, None
    mes = MESES.get(m.group(1).lower())
    if not mes:
        return None, None
    # pdftotext parte las frases con saltos de linea; la cita se normaliza para que
    # sea legible como texto (auditoria externa, punto 6).
    cita = re.sub(r"\s+", " ", m.group(0)).strip()
    return "%s-%02d" % (m.group(2), mes), cita[:180]


def _num(s):
    return float(s.replace(".", "").replace(",", ".")) if "," in s else float(s)


def _bullet(texto, etiqueta):
    """Aisla el parrafo del resumen que arranca con '<etiqueta>:' (Credito /
    Debito). El BCRA usa vinietas con guion largo; cortamos en la siguiente."""
    m = re.search(r"[−\-]\s*%s\s*:" % etiqueta, texto, re.I)
    if not m:
        return ""
    resto = texto[m.end():m.end() + 900]
    corte = re.search(r"\n\s*[−\-]\s*[A-ZÁÉÍÓÚ]", resto)
    return resto[:corte.start()] if corte else resto


def var_ia_declaradas(texto):
    """Extrae las variaciones i.a. que el BCRA declara para tarjetas en el
    resumen ejecutivo. Devuelve {concepto: valor_pp}.

    Dos redacciones conviven en el informe:
      'variaciones interanuales de 1,6 % en cantidades y -10,2 % en montos reales'
      'disminuciones de 6,9 % i.a. en cantidades y de 13,4 % i.a. en montos reales'
    La segunda expresa el signo en la palabra, no en el numero: hay que negarlo.
    Ausencia de coincidencia = ese concepto no se valida (nunca se inventa)."""
    par = re.compile(
        r"(-?\d+[.,]\d)\s*%[^%]{0,80}?cantidades?\s+y\s+(?:de\s+)?(-?\d+[.,]\d)\s*%"
        r"[^%]{0,80}?montos?\s+reales", re.I | re.S)
    neg = re.compile(r"disminuci|ca[ií]da|retrocec|baja", re.I)

    out = {}
    for etiqueta, nombre in (("cr[eé]dito", "Tarjetas de crédito"),
                             ("d[eé]bito", "Tarjetas de débito")):
        b = _bullet(texto, etiqueta)
        m = par.search(b)
        if not m:
            continue
        cant, monto = _num(m.group(1)), _num(m.group(2))
        if neg.search(b):
            cant, monto = -abs(cant), -abs(monto)
        out["%s — var. i.a. cantidad" % nombre] = cant
        out["%s — var. i.a. monto real" % nombre] = monto

    # Transferencias push: "aumentos interanuales de 22,2 % y 7,4 % en cantidades
    # y en montos reales".
    m = re.search(r"aumentos?\s+interanuales?\s+de\s+(-?\d+[.,]\d)\s*%\s*y\s*"
                  r"(-?\d+[.,]\d)\s*%[^%]{0,60}?cantidades?\s+y\s+en\s+montos?\s+"
                  r"reales", texto, re.I | re.S)
    if m:
        out['Transferencias inmediatas "push" — var. i.a. cantidad'] = _num(m.group(1))
        out['Transferencias inmediatas "push" — var. i.a. monto real'] = _num(m.group(2))

    # PCT interoperables: "operaciones de PCT (70,7 % i.a.) ... ($ 3 billones
    # (66,6 % i.a. en terminos reales))".
    m = re.search(r"operaciones\s+de\s+PCT\s*\(\s*(-?\d+[.,]\d)\s*%\s*i\.a\.[^%]{0,220}?"
                  r"\(\s*(-?\d+[.,]\d)\s*%\s*i\.a\.\s*en\s+t[eé]rminos\s+reales",
                  texto, re.I | re.S)
    if m:
        out["Pagos con transferencia interoperables — var. i.a. cantidad"] = _num(m.group(1))
        out["Pagos con transferencia interoperables — var. i.a. monto real"] = _num(m.group(2))
    return out


# --------------------------------------------------------------------------
# Paso 3 - carga de las tres pestanias, mapeando por encabezado
# --------------------------------------------------------------------------

def mes_de(v):
    if isinstance(v, dt.datetime):
        return "%04d-%02d" % (v.year, v.month)
    if isinstance(v, dt.date):
        return "%04d-%02d" % (v.year, v.month)
    return None


def leer_pestania(ws, grupos):
    """Devuelve {grupo: {mes: (cantidad, monto_nominal)}} mapeando columnas por
    encabezado, no por posicion fija."""
    filas = list(ws.iter_rows(values_only=True))
    # Localizar la fila de encabezado de grupo (la que contiene alguno de ellos)
    fila_grupo = None
    for i, f in enumerate(filas[:6]):
        celdas = [str(c).strip() if c is not None else "" for c in f]
        if any(g in celdas for g in grupos):
            fila_grupo = i
            break
    if fila_grupo is None:
        return {}

    encab = [str(c).strip() if c is not None else "" for c in filas[fila_grupo]]
    # Propagar el nombre de grupo hacia la derecha (celdas combinadas). La
    # propagacion se corta donde una fila superior declara un grupo nuevo: sin ese
    # corte, el ultimo nombre se derrama sobre columnas ajenas (DECISIONES.md, it. 17).
    corte_sup = set()
    if fila_grupo > 0:
        sup = [str(c).strip() if c is not None else "" for c in filas[fila_grupo - 1]]
        corte_sup = {j for j, c in enumerate(sup) if c and j > 0}
    actual, mapa = "", []
    for j, c in enumerate(encab):
        if c:
            actual = c
        elif j in corte_sup:
            actual = ""
        mapa.append(actual)

    # La fila de subencabezado (Cantidad / Monto) es la siguiente no vacia
    fila_sub = None
    for i in range(fila_grupo + 1, min(fila_grupo + 4, len(filas))):
        celdas = [str(c).strip().lower() if c is not None else "" for c in filas[i]]
        if "cantidad" in celdas:
            fila_sub = i
            break
    if fila_sub is None:
        return {}
    sub = [str(c).strip().lower() if c is not None else "" for c in filas[fila_sub]]

    cols = {}
    for j, (g, s) in enumerate(zip(mapa, sub)):
        if g in grupos and s in ("cantidad", "monto nominal", "monto"):
            clave = "cantidad" if s == "cantidad" else "monto"
            # Primera coincidencia gana: si un nombre se repite, la columna valida es
            # la que esta debajo del encabezado, no la ultima del derrame.
            cols.setdefault(g, {}).setdefault(clave, j)

    datos = {g: {} for g in cols}
    for f in filas[fila_sub + 1:]:
        if not f:
            continue
        mes = mes_de(f[0])
        if not mes:
            continue
        for g, cc in cols.items():
            ci, mi = cc.get("cantidad"), cc.get("monto")
            cant = f[ci] if ci is not None and ci < len(f) else None
            mont = f[mi] if mi is not None and mi < len(f) else None
            cant = float(cant) if isinstance(cant, (int, float)) else None
            mont = float(mont) if isinstance(mont, (int, float)) else None
            if cant is None and mont is None:
                continue
            datos[g][mes] = (cant, mont)
    return datos


# --------------------------------------------------------------------------
# Paso 4 - indice IPC encadenado
# --------------------------------------------------------------------------

def construir_ipc():
    """Encadena las variaciones mensuales hacia adelante desde el ancla y
    reconstruye el tramo anterior con las variaciones interanuales."""
    src = json.load(open(os.path.join(AQUI, "ipc_fuente.json"), encoding="utf-8"))
    idx = {src["ancla"]["mes"]: float(src["ancla"]["valor"])}

    for mes in sorted(src["var_mensual_pct"]):
        prev = mes_anterior(mes)
        if prev in idx:
            idx[mes] = idx[prev] * (1 + src["var_mensual_pct"][mes] / 100.0)

    for mes, ia in src["var_interanual_pct"].items():
        if mes in idx:
            idx[mes_menos_12(mes)] = idx[mes] / (1 + ia / 100.0)

    return idx, src


def mes_anterior(m):
    a, b = int(m[:4]), int(m[5:])
    return "%04d-%02d" % (a - 1, 12) if b == 1 else "%04d-%02d" % (a, b - 1)


def mes_menos_12(m):
    return "%04d-%02d" % (int(m[:4]) - 1, int(m[5:]))


def rango(fin, n):
    out, a, b = [], int(fin[:4]), int(fin[5:])
    for _ in range(n):
        out.append("%04d-%02d" % (a, b))
        b -= 1
        if b == 0:
            a, b = a - 1, 12
    return list(reversed(out))


# --------------------------------------------------------------------------
# Pasos 5 a 7 - deflactacion, metricas y validacion
# --------------------------------------------------------------------------

def pct(nuevo, viejo):
    if nuevo is None or viejo in (None, 0):
        return None
    return round((nuevo / viejo - 1) * 100, 2)


def armar_series(datos_por_pestania, ipc, base, meses, horizonte=HORIZONTE):
    ipc_base = ipc.get(base)
    series = []
    for pest, grupos in datos_por_pestania.items():
        # Cada pestania corre hasta su propio ultimo dato disponible.
        propios = sorted({m for d in grupos.values() for m in d})
        meses_p = ([m for m in rango(propios[-1], horizonte) if m in ipc]
                   if propios else meses)
        # Participacion: sobre el total de la pestania, por mes
        total_mes = {}
        if pest not in SIN_PARTICIPACION:
            for g, d in grupos.items():
                for m, (_, mont) in d.items():
                    if mont is not None:
                        total_mes[m] = total_mes.get(m, 0.0) + mont

        for g, d in grupos.items():
            moneda = MONEDA_NO_ARS.get(g, "ARS")
            periodos = []
            for m in meses_p:
                cant, mont = d.get(m, (None, None))
                f = ipc.get(m)
                if moneda != "ARS":
                    real = None          # no se deflacta por IPC argentino
                else:
                    real = (round(mont * (ipc_base / f), 2)
                            if (mont is not None and f) else None)
                real_12 = None
                m12 = mes_menos_12(m)
                c12, mo12 = d.get(m12, (None, None))
                f12 = ipc.get(m12)
                if mo12 is not None and f12 and moneda == "ARS":
                    real_12 = mo12 * (ipc_base / f12)
                periodos.append({
                    "mes": m,
                    "cantidad": int(cant) if cant is not None else None,
                    "monto_nominal": mont,
                    "monto_real": real,
                    "ticket_promedio_real": round(real / cant, 2) if (real and cant) else None,
                    "var_ia_cantidad": pct(cant, c12),
                    "var_ia_monto_real": pct(real, real_12),
                    "participacion": (round(mont / total_mes[m] * 100, 2)
                                      if mont is not None and total_mes.get(m) else None),
                })
            series.append({"pestania": pest, "metrica": g, "moneda": moneda,
                           "mes_corte": meses_p[-1] if meses_p else None,
                           "periodos": periodos})
    return series


def resumir(series, meses):
    """Agregados de nivel informe. Se calculan aca, no en el dashboard: el
    dashboard no recalcula nada (ver DECISIONES.md, it. 5 y 11)."""
    ult = meses[-1]
    ars = [s for s in series
           if s["pestania"] == "Tarjetas" and s.get("moneda", "ARS") == "ARS"]

    def total(mes, campo):
        vs = [p[campo] for s in ars for p in s["periodos"]
              if p["mes"] == mes and p[campo] is not None]
        return sum(vs) if vs else None

    m_real, m_cant = total(ult, "monto_real"), total(ult, "cantidad")
    m12 = mes_menos_12(ult)
    r12 = total(m12, "monto_real")

    return {
        "mes": ult,
        "tarjetas_ars": {
            "monto_real": round(m_real, 2) if m_real else None,
            "cantidad": int(m_cant) if m_cant else None,
            "ticket_promedio_real": (round(m_real / m_cant, 2)
                                     if m_real and m_cant else None),
            "var_ia_monto_real": pct(m_real, r12),
        },
    }


def validar(series, declaradas):
    out = []
    for concepto, valor_bcra in declaradas.items():
        metrica = concepto.split(" — ")[0]
        campo = ("var_ia_cantidad" if "cantidad" in concepto
                 else "var_ia_monto_real")
        calc = None
        for s in series:
            if s["metrica"] == metrica and s["periodos"]:
                calc = s["periodos"][-1][campo]
                break
        delta = round(abs(calc - valor_bcra), 2) if calc is not None else None
        out.append({
            "concepto": concepto,
            "valor_bcra": valor_bcra,
            "valor_calculado": calc,
            "delta_pp": delta,
            "dentro_de_tolerancia": (delta is not None and delta <= TOLERANCIA_PP),
        })
    return out


# --------------------------------------------------------------------------
# Orquestacion
# --------------------------------------------------------------------------

def salida_vacia(ed):
    return {
        "estado": "error", "edicion": ed,
        "generado_utc": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "corte": {"mes_analisis": ed, "mes_corte_tarjetas": None,
                  "fuente_corte": None, "coincide_con_excel": None},
        "deflactor": {"indice": "IPC Nacional Nivel General (INDEC)",
                      "mes_base": None, "valor_base": None},
        "series": [], "resumen": None, "validacion_pdf": [], "notas": [],
        "advertencias": [],
        "errores": [],
        "requiere_revision_humana": True, "puntos_de_firma": ["publicacion_dashboard"],
    }


def correr(ed, base_forzada=None, workdir="."):
    import openpyxl

    out = salida_vacia(ed)
    os.makedirs(workdir, exist_ok=True)
    fx = os.path.join(workdir, "series-%s.xlsx" % ed)
    fp = os.path.join(workdir, "informe-%s.pdf" % ed)

    # Paso 1
    okx, detx = bajar(URL_XLSX.format(ed=ed), fx, "spreadsheetml")
    okp, url_pdf, detp = bajar_pdf(ed, fp)
    out["descarga"] = {"xlsx": detx, "url_xlsx": URL_XLSX.format(ed=ed),
                       "pdf": detp, "url_pdf": url_pdf}
    if not okx or not okp:
        out["errores"].append(
            "Descarga fallida. XLSX: %s. PDF: %s. Se probaron los dos patrones de "
            "URL conocidos del BCRA. La edicion probablemente no esta publicada."
            % (detx, detp))
        return out

    # Paso 2
    txt = texto_pdf(fp)
    corte_pdf, cita = corte_declarado(txt)
    wb = openpyxl.load_workbook(fx, data_only=True)
    datos = {p: leer_pestania(wb[p], g) for p, g in PESTANIAS.items() if p in wb.sheetnames}
    meses_tarjetas = sorted({m for g in datos.get("Tarjetas", {}).values() for m in g})
    corte_xlsx = meses_tarjetas[-1] if meses_tarjetas else None

    out["corte"] = {"mes_analisis": ed, "mes_corte_tarjetas": corte_pdf or corte_xlsx,
                    "fuente_corte": ("nota al pie 1 del PDF" if corte_pdf
                                     else "ultima fila de la pestania Tarjetas"),
                    "cita_pdf": cita, "mes_corte_segun_excel": corte_xlsx,
                    "coincide_con_excel": (corte_pdf == corte_xlsx)}

    if corte_pdf and corte_xlsx and corte_pdf != corte_xlsx:
        out["errores"].append(
            "Conflicto de corte temporal. El PDF (nota al pie 1) indica %s; la "
            "pestania Tarjetas contiene datos hasta %s. No se resuelve "
            "automaticamente porque determina la base de deflactacion de toda la "
            "serie. Requiere decision del analista." % (corte_pdf, corte_xlsx))
        return out

    corte = corte_pdf or corte_xlsx
    if not corte:
        out["errores"].append("No se pudo determinar el mes de corte de tarjetas.")
        return out

    # Pasos 4 a 6
    ipc, src_ipc = construir_ipc()
    base = base_forzada or corte
    if base not in ipc:
        out["errores"].append("Falta el IPC para el mes base %s. La corrida se "
                              "detiene: el contrato prohibe sustituir el deflactor." % base)
        return out
    out["deflactor"] = {"indice": src_ipc["indice"], "mes_base": base,
                        "valor_base": round(ipc[base], 4),
                        "fuentes": [f["url"] for f in src_ipc["fuentes"]]}
    if base_forzada:
        out["advertencias"].append(
            "Base de pesos constantes forzada a %s; no corresponde al mes de corte "
            "de esta edicion (%s). Las cifras no son comparables con una corrida de "
            "base por defecto." % (base_forzada, corte))

    meses = rango(corte, HORIZONTE)
    faltan = [m for m in meses if m not in ipc]
    if faltan:
        meses = [m for m in meses if m in ipc]
        out["advertencias"].append(
            "Horizonte recortado a %d meses: no hay IPC disponible para %s."
            % (len(meses), ", ".join(faltan)))

    out["series"] = armar_series(datos, ipc, base, meses)

    usd = [s["metrica"] for s in out["series"] if s.get("moneda") != "ARS"]
    if usd:
        out["notas"].append(
            "Serie en moneda extranjera excluida de la deflactacion: %s. El monto "
            "nominal esta en dolares (nota 4 del informe); aplicarle el IPC argentino "
            "produciria una cifra sin significado. Se publica solo el nominal en USD."
            % ", ".join(usd))

    out["resumen"] = resumir(out["series"], meses)

    # Paso 7
    out["validacion_pdf"] = validar(out["series"], var_ia_declaradas(txt))
    if not out["validacion_pdf"]:
        out["advertencias"].append(
            "No se pudieron extraer del PDF cifras de tarjetas comparables; la "
            "validacion cruzada quedo vacia y la salida no esta contrastada.")

    fuera = [v for v in out["validacion_pdf"] if not v["dentro_de_tolerancia"]]
    for v in fuera:
        out["advertencias"].append(
            "Discrepancia fuera de tolerancia en '%s': BCRA %s pp vs calculado %s pp "
            "(delta %s pp, tolerancia %s pp). No se ajusto el calculo."
            % (v["concepto"], v["valor_bcra"], v["valor_calculado"],
               v["delta_pp"], TOLERANCIA_PP))

    nulos12 = any(p["monto_real"] is None
                  for s in out["series"] if s.get("moneda") == "ARS"
                  for p in s["periodos"][-12:])
    out["requiere_revision_humana"] = bool(fuera or nulos12 or out["advertencias"])
    out["estado"] = "ok_con_advertencias" if out["advertencias"] else "ok"
    return out


PLANTILLA_ENTRADA = """# {titulo}

- **Fecha de ejecucion:** {fecha}
- **Contrato aplicado:** `prompts/system_prompt.md`
- **Variante de user prompt:** {variante}

{proposito}## Prompt enviado

```
Procesa la edicion {ed} del Informe Mensual de Pagos Minoristas del BCRA.

Horizonte: {horizonte} meses hacia atras desde el mes de corte de cada pestania.
Base de pesos constantes: {base_txt}
Pestanias: Tarjetas, TC Modalidad de pago, Tarjeta de credito por canal,
Transferencias de fondos.

Devolve el JSON del contrato. Nada mas.
```

## Comando ejecutado

```
python3 agente/pmr.py {ed}{arg_base} --out corridas/{carpeta}
python3 agente/dashboard.py corridas/{carpeta}/salida.json
```

## Insumos

{insumos}

## Resultado

{resultado}

---

*Este archivo lo genera `agente/pmr.py` a partir de la corrida, no se escribe a mano.
Ver DECISIONES.md, iteracion 21.*
"""


def escribir_entrada(res, carpeta, base_forzada, proposito=""):
    """Escribe entrada.md derivandolo de la corrida. Se genera en vez de redactarse
    para que no pueda desincronizarse del salida.json que tiene al lado: esa deriva
    fue justamente el hallazgo 1 de la auditoria externa (DECISIONES.md, it. 21)."""
    d = res
    ed = d["edicion"]
    dec = d.get("descarga") or {}
    if dec.get("url_xlsx"):
        insumos = ("- `%s` — %s\n  desde %s\n- `%s` — %s\n  desde %s\n\nAmbos quedan "
                   "guardados en esta carpeta para que la corrida sea reconstruible "
                   "aunque el BCRA modifique o retire los archivos."
                   % ("series-%s.xlsx" % ed, dec.get("xlsx", ""), dec["url_xlsx"],
                      "informe-%s.pdf" % ed, dec.get("pdf", ""),
                      dec.get("url_pdf", "")))
    else:
        insumos = ("No hay archivos descargados en esta carpeta: esa ausencia es el "
                   "resultado.\n\n- Excel: %s\n- PDF: %s"
                   % (dec.get("xlsx", "no intentado"), dec.get("pdf", "no intentado")))

    lineas = ["`estado: %s`. `requiere_revision_humana: %s`."
              % (d["estado"], str(d["requiere_revision_humana"]).lower())]
    c = d["corte"]
    if c.get("mes_corte_tarjetas"):
        lineas.append("Corte de tarjetas **%s**, tomado de la %s%s."
                      % (c["mes_corte_tarjetas"], c.get("fuente_corte", "fuente"),
                         " y coincidente con la ultima fila de la pestania `Tarjetas`"
                         if c.get("coincide_con_excel") else
                         " **sin** coincidir con el Excel"))
    if d.get("deflactor", {}).get("mes_base"):
        lineas.append("Base de pesos constantes: **%s**." % d["deflactor"]["mes_base"])
    if d["series"]:
        lineas.append("Se emitieron **%d series** sobre %d pestanias."
                      % (len(d["series"]),
                         len({x["pestania"] for x in d["series"]})))
    vs = d.get("validacion_pdf") or []
    if vs:
        ok = sum(1 for v in vs if v["dentro_de_tolerancia"])
        peor = max(v["delta_pp"] for v in vs if v["delta_pp"] is not None)
        lineas.append("Contraste contra el PDF: **%d de %d** comparaciones dentro de "
                      "tolerancia, desvio maximo **%s pp**." % (ok, len(vs), peor))
    else:
        lineas.append("No hubo contraste contra el PDF en esta corrida.")
    for k, t in (("notas", "Nota"), ("advertencias", "Advertencia"),
                 ("errores", "Error")):
        for x in d.get(k) or []:
            lineas.append("**%s:** %s" % (t, x))
    if d["series"]:
        lineas.append("Salida: `salida.json`, `dashboard.html`.")

    with open(os.path.join(carpeta, "entrada.md"), "w", encoding="utf-8") as f:
        f.write(PLANTILLA_ENTRADA.format(
            titulo="Corrida — edicion %s%s"
                   % (ed, " (base forzada)" if base_forzada else ""),
            fecha=d["generado_utc"][:10],
            variante=("B (base forzada)" if base_forzada else "A (corrida estandar)"),
            proposito=(proposito + "\n\n") if proposito else "",
            ed=ed, horizonte=HORIZONTE,
            base_txt=("FORZADA a %s." % base_forzada if base_forzada
                      else "mes de corte de tarjetas de esta edicion."),
            arg_base=(" --base %s" % base_forzada if base_forzada else ""),
            carpeta=os.path.basename(carpeta.rstrip("/")),
            insumos=insumos, resultado="\n\n".join(lineas)))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("edicion")
    ap.add_argument("--base", default=None)
    ap.add_argument("--out", default=".")
    ap.add_argument("--proposito", default="")
    a = ap.parse_args()
    res = correr(a.edicion, a.base, a.out)
    p = os.path.join(a.out, "salida.json")
    with open(p, "w", encoding="utf-8") as f:
        json.dump(res, f, ensure_ascii=False, indent=2)
    escribir_entrada(res, a.out, a.base, a.proposito)
    print(json.dumps({k: res[k] for k in
                      ("estado", "edicion", "corte", "requiere_revision_humana")},
                     ensure_ascii=False, indent=2))
    return 0 if res["estado"] != "error" else 1


if __name__ == "__main__":
    sys.exit(main())
