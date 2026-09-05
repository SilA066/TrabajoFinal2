#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Agente PMR - generador del dashboard (v4, formato exhibit ejecutivo).

Lee salida.json y escribe dashboard.html. No recalcula nada: los agregados vienen
del bloque `resumen` del JSON (ver DECISIONES.md, iteraciones 5 y 11).

Todas las series se muestran en pesos constantes. Las cifras nominales no se
grafican ni se comparan: la brecha contra la inflacion es una obviedad aritmetica
y ocupaba lugar sin informar (ver DECISIONES.md, iteracion 12).

Uso:
    python3 agente/dashboard.py corridas/2026-07/salida.json
"""

import base64
import html
import json
import math
import os
import sys

AQUI = os.path.dirname(os.path.abspath(__file__))
LOGO = os.path.join(AQUI, "marca", "logo.png")

MESES_AB = ["ene", "feb", "mar", "abr", "may", "jun",
            "jul", "ago", "sep", "oct", "nov", "dic"]
MESES_LARGO = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio",
               "agosto", "septiembre", "octubre", "noviembre", "diciembre"]

QUE_MIDE = {
    "Tarjetas": "Volumen operado con cada tipo de tarjeta.",
    "TC Modalidad de pago": "Del total comprado con tarjeta de credito, cuanto se "
                            "pago en una sola cuota y cuanto en cuotas.",
    "Tarjeta de credito por canal": "Por donde entraron las operaciones de credito.",
    "Transferencias de fondos": "Envios de dinero entre cuentas y pagos iniciados con "
                                "transferencia. Grafico 2 del informe.",
}
EN_FRASE = {
    "Tarjetas": "el consumo con tarjetas",
    "TC Modalidad de pago": "las compras con tarjeta de credito",
    "Tarjeta de credito por canal": "las operaciones de credito",
    "Transferencias de fondos": "las transferencias",
}
# Alcance de cada pestania. Las dos aperturas de credito no cubren el total de
# tarjetas: sin declararlo, un exhibit suelto se puede leer como si lo hiciera.
ALCANCE = {
    "TC Modalidad de pago": "Solo tarjetas de credito, por modalidad de pago",
    "Tarjeta de credito por canal": "Solo tarjetas de credito, por canal",
    "Transferencias de fondos": "Datos al mes de analisis, un mes mas adelante que "
                                "tarjetas",
}

FUENTE = ("Fuente: BCRA, Informe Mensual de Pagos Minoristas, edicion %s. "
          "Deflactado por IPC Nacional Nivel General, INDEC.")


# --------------------------------------------------------------------------
# Formato
# --------------------------------------------------------------------------

def logo_html():
    """El logo se incrusta en base64 para que dashboard.html siga siendo un unico
    archivo portable: se puede mover, adjuntar o versionar sin arrastrar recursos."""
    if not os.path.exists(LOGO):
        return ""
    with open(LOGO, "rb") as f:
        b64 = base64.b64encode(f.read()).decode("ascii")
    return ('<img class="marca" alt="" src="data:image/png;base64,%s">' % b64)


def mes_ab(m):
    return "%s %s" % (MESES_AB[int(m[5:]) - 1], m[2:4])


def mes_largo(m):
    return "%s %s" % (MESES_LARGO[int(m[5:]) - 1], m[:4])


def num(v, dec=2):
    if v is None:
        return "—"
    return ("{:,.{d}f}".format(v, d=dec)
            .replace(",", "\x00").replace(".", ",").replace("\x00", "."))


def pct(v, dec=1, signo=True):
    if v is None:
        return "—"
    f = "%+.*f" if signo else "%.*f"
    return (f % (dec, v)).replace(".", ",") + " %"


def escala(maximo):
    if not maximo:
        return 1.0, "$"
    for corte, txt in ((1e12, "billones de $"), (1e9, "miles de millones de $"),
                       (1e6, "millones de $")):
        if maximo >= corte:
            return corte, txt
    return 1.0, "$"


def cantidad(v):
    if v is None:
        return "—"
    if v >= 1e6:
        return num(v / 1e6, 1) + " M"
    if v >= 1e3:
        return num(v / 1e3, 0) + " mil"
    return num(v, 0)


def verbo(v):
    return "crece" if v is not None and v >= 0 else "cae"


def de(frase):
    """Contraccion: 'de el consumo' -> 'del consumo'."""
    return ("del " + frase[3:]) if frase.startswith("el ") else ("de " + frase)


# --------------------------------------------------------------------------
# Graficos
# --------------------------------------------------------------------------

def ticks(lo, hi, n=4):
    if hi <= lo:
        hi = lo + 1
    bruto = (hi - lo) / n
    mag = 10 ** math.floor(math.log10(bruto)) if bruto > 0 else 1
    paso = min([m * mag for m in (1, 2, 2.5, 5, 10)], key=lambda p: abs(p - bruto))
    out, v = [], math.floor(lo / paso) * paso
    while v <= hi + paso * 0.001:
        if v >= lo - paso * 0.001:
            out.append(v)
        v += paso
    return out


def escala_ticket(maximo):
    """El ticket vive en un orden de magnitud mucho menor que el monto operado."""
    if not maximo:
        return 1.0, "$", 0
    if maximo >= 1e6:
        return 1e6, "millones de $", 2
    if maximo >= 1e3:
        return 1e3, "miles de $", 1
    return 1.0, "$", 0


def barras_campo(periodos, campo, div, unidad, dec=2, alto=250,
                 color="electric", color_ultimo="deep"):
    """Barras mes a mes de cualquier campo del JSON. La ultima barra se destaca
    y se etiqueta con su valor."""
    W, H = 680, alto
    L, R, T, B = 76, 56, 22, 34
    datos = [(p["mes"], (p[campo] / div) if p[campo] is not None else None)
             for p in periodos]
    vals = [v for _, v in datos if v is not None]
    if len(vals) < 2:
        return '<p class="sinserie">Serie insuficiente para graficar.</p>'
    hi = max(vals) * 1.10
    tk = ticks(0.0, hi)
    hi = max(hi, tk[-1])
    n = len(datos)
    ancho = (W - L - R) / n * 0.66

    def px(i):
        return L + (i + 0.5) * (W - L - R) / n

    def py(v):
        return T + (1 - v / hi) * (H - T - B)

    base = py(0)
    grid = "".join(
        '<line x1="%d" y1="%.1f" x2="%d" y2="%.1f" stroke="var(--rejilla)"/>'
        '<text x="%d" y="%.1f" class="ejey">%s</text>'
        % (L, py(t), W - R, py(t), L - 10, py(t) + 4, num(t, dec)) for t in tk)
    barras = "".join(
        '<rect x="%.1f" y="%.1f" width="%.1f" height="%.1f" fill="var(--%s)">'
        "<title>%s: %s %s</title></rect>"
        % (px(i) - ancho / 2, py(v), ancho, max(base - py(v), 1),
           color_ultimo if i == n - 1 else color, mes_ab(ms), num(v, dec), unidad)
        for i, (ms, v) in enumerate(datos) if v is not None)
    ult = datos[-1]
    marca = ('<text x="%.1f" y="%.1f" class="etq" fill="var(--%s)">%s</text>'
             % (px(n - 1) + ancho / 2 + 6, py(ult[1]) + 4, color_ultimo,
                num(ult[1], dec))) if ult[1] is not None else ""
    paso = max(1, n // 6)
    ejex = "".join(
        '<text x="%.1f" y="%d" class="ejex">%s</text>' % (px(i), H - 12, mes_ab(ms))
        for i, (ms, _) in enumerate(datos) if i % paso == 0 or i == n - 1)
    return ('<svg class="gr" viewBox="0 0 %d %d" role="img" aria-label="Evolucion '
            'mes a mes">%s%s%s'
            '<line x1="%d" y1="%.1f" x2="%d" y2="%.1f" stroke="var(--deep)"/>'
            '<text x="2" y="%d" class="ejey rot">%s</text>%s</svg>'
            % (W, H, grid, barras, marca, L, base, W - R, base, T - 6, unidad, ejex))


def barras_ia(periodos):
    """Variacion interanual real: barras divergentes alrededor de cero."""
    W, H = 680, 170
    L, R, T, B = 76, 56, 16, 30
    datos = [(p["mes"], p["var_ia_monto_real"]) for p in periodos]
    vals = [v for _, v in datos if v is not None]
    if not vals:
        return '<p class="sinserie">Sin variacion interanual disponible.</p>'
    m = max(abs(min(vals)), abs(max(vals)), 5) * 1.22
    n = len(datos)
    ancho = (W - L - R) / n * 0.66

    def px(i):
        return L + (i + 0.5) * (W - L - R) / n

    def py(v):
        return T + (1 - (v + m) / (2 * m)) * (H - T - B)

    cero = py(0)
    barras = "".join(
        '<rect x="%.1f" y="%.1f" width="%.1f" height="%.1f" fill="var(--%s)">'
        "<title>%s: %s</title></rect>"
        % (px(i) - ancho / 2, min(py(v), cero), ancho, max(abs(py(v) - cero), 1),
           "verde" if v >= 0 else "rojo", mes_ab(ms), pct(v))
        for i, (ms, v) in enumerate(datos) if v is not None)
    etq = "".join(
        '<text x="%d" y="%.1f" class="ejey">%s</text>' % (L - 10, py(v) + 4, pct(v, 0))
        for v in (m * 0.7, 0, -m * 0.7))
    paso = max(1, n // 6)
    ejex = "".join(
        '<text x="%.1f" y="%d" class="ejex">%s</text>' % (px(i), H - 10, mes_ab(ms))
        for i, (ms, _) in enumerate(datos) if i % paso == 0 or i == n - 1)
    u = datos[-1][1]
    marca = ('<text x="%.1f" y="%.1f" class="etq" fill="var(--%s)">%s</text>'
             % (px(n - 1) + ancho / 2 + 6, py(u) + (4 if u >= 0 else 10),
                "verde" if u >= 0 else "rojo", pct(u))) if u is not None else ""
    return ('<svg class="gr" viewBox="0 0 %d %d" role="img" aria-label="Variacion '
            'interanual real por mes">%s%s'
            '<line x1="%d" y1="%.1f" x2="%d" y2="%.1f" stroke="var(--deep)"/>%s%s'
            "</svg>" % (W, H, barras, etq, L, cero, W - R, cero, ejex, marca))


def barra_mix(series, mes):
    """Composicion del mes. Se arma en HTML y no en SVG: un SVG estirado en
    horizontal deforma la tipografia y las cifras dejan de leerse
    (ver DECISIONES.md, iteracion 12)."""
    trozos = []
    for s in series:
        p = next((x for x in s["periodos"] if x["mes"] == mes), None)
        if p and p.get("participacion"):
            trozos.append((s["metrica"], p["participacion"]))
    if len(trozos) < 2:
        return "", None
    trozos.sort(key=lambda t: -t[1])
    seg, leg = [], []
    for i, (nombre, v) in enumerate(trozos):
        seg.append('<div class="sg m%d" style="width:%.3f%%" title="%s: %s">%s</div>'
                   % (i % 4 + 1, max(v, 1.2), html.escape(nombre), pct(v, 1, False),
                      pct(v, 1, False) if v >= 9 else ""))
        leg.append('<li><span class="pto m%d"></span>%s<b>%s</b></li>'
                   % (i % 4 + 1, html.escape(nombre), pct(v, 1, False)))
    return ('<div class="mixbar">%s</div><ul class="mixleg">%s</ul>'
            % ("".join(seg), "".join(leg))), trozos[0]


# --------------------------------------------------------------------------
# Titulos de accion y sintesis
# --------------------------------------------------------------------------

def _ticket_ia(per):
    ult = per[-1]
    if not ult["ticket_promedio_real"] or len(per) < 13:
        return None
    ant = per[-13]["ticket_promedio_real"]
    return (ult["ticket_promedio_real"] / ant - 1) * 100 if ant else None


def titulo_accion(s, pestania):
    """La cabecera enuncia el hallazgo, no el tema. Escalera de umbrales para que
    dos exhibits contiguos no digan lo mismo con distintos numeros."""
    per = s["periodos"]
    ult = per[-1]
    ia = ult["var_ia_monto_real"]
    nombre = s["metrica"]
    if ia is None:
        return "%s: sin variacion interanual comparable" % nombre

    base = "%s %s %s real interanual" % (nombre, verbo(ia), pct(abs(ia), 1, False))

    iac = ult["var_ia_cantidad"]
    if iac is not None and abs(iac - ia) >= 6:
        if (iac >= 0) != (ia >= 0):
            return "%s pero las operaciones %s %s: cada compra es mas chica" % (
                base, "crecen" if iac >= 0 else "caen", pct(abs(iac), 1, False))
        return "%s, con las operaciones %s %s" % (
            base, "creciendo" if iac >= 0 else "cayendo", pct(abs(iac), 1, False))

    tia = _ticket_ia(per)
    if tia is not None and abs(tia) >= 10:
        return "%s y el ticket promedio real %s %s" % (
            base, "sube" if tia >= 0 else "baja", pct(abs(tia), 1, False))

    if ult.get("participacion"):
        return "%s y explica %s %s" % (
            base, pct(ult["participacion"], 1, False),
            de(EN_FRASE.get(pestania, pestania.lower())))

    return base


def cmp_ticket(d, pestania, a, b, titulo):
    """Compara el ticket promedio real de dos series de la misma pestania en el
    ultimo mes disponible. Ambas comparten corte y base, asi que el cociente es
    directo. El cierre se deriva de los datos: cuanto pesa la serie de ticket alto
    en operaciones frente a cuanto pesa en monto."""
    idx = {x["metrica"]: x for x in d["series"] if x["pestania"] == pestania}
    sa, sb = idx.get(a), idx.get(b)
    if not sa or not sb:
        return None
    pa, pb = sa["periodos"][-1], sb["periodos"][-1]
    ta, tb = pa["ticket_promedio_real"], pb["ticket_promedio_real"]
    if not ta or not tb:
        return None
    alto, bajo = ((sa, pa), (sb, pb)) if ta >= tb else ((sb, pb), (sa, pa))
    t_alto = alto[1]["ticket_promedio_real"]
    t_bajo = bajo[1]["ticket_promedio_real"]

    cierre = ""
    c_alto, c_bajo = alto[1]["cantidad"], bajo[1]["cantidad"]
    m_alto, m_bajo = alto[1]["monto_real"], bajo[1]["monto_real"]
    if c_alto and c_bajo and m_alto and m_bajo:
        cierre = (" Entre las dos, aporta el <b>%s</b> de las operaciones pero el "
                  "<b>%s</b> del monto."
                  % (pct(c_alto / (c_alto + c_bajo) * 100, 1, False),
                     pct(m_alto / (m_alto + m_bajo) * 100, 1, False)))

    return (titulo,
            "En %s, %s promedia <b>$ %s</b> por operacion frente a <b>$ %s</b> de %s: "
            "<b>%s veces</b> mas.%s"
            % (mes_largo(pa["mes"]), alto[0]["metrica"].lower(), num(t_alto, 0),
               num(t_bajo, 0), bajo[0]["metrica"].lower(),
               num(t_alto / t_bajo, 1), cierre))


def sintesis(d):
    """Mensajes clave, compuestos con los agregados del JSON."""
    r = d.get("resumen") or {}
    t = r.get("tarjetas_ars") or {}
    msgs = []

    if t.get("monto_real"):
        div, unidad = escala(t["monto_real"])
        ia = t.get("var_ia_monto_real")
        msgs.append(
            ("El consumo con tarjetas %s en terminos reales"
             % ("se contrae" if (ia or 0) < 0 else "se expande"),
             "En %s se operaron <b>%s %s</b> a precios constantes, <b>%s</b> contra "
             "el mismo mes del ano anterior."
             % (mes_largo(r["mes"]), num(t["monto_real"] / div), unidad, pct(ia))))

    # Contraste entre las dos series mayores de la pestania Tarjetas
    ars = [s for s in d["series"] if s["pestania"] == "Tarjetas"
           and s.get("moneda", "ARS") == "ARS"
           and s["periodos"][-1]["var_ia_monto_real"] is not None]
    ars.sort(key=lambda s: -(s["periodos"][-1]["monto_real"] or 0))
    if len(ars) >= 2:
        a, b = ars[0], ars[1]
        ia_a = a["periodos"][-1]["var_ia_monto_real"]
        ia_b = b["periodos"][-1]["var_ia_monto_real"]
        msgs.append(
            ("El credito resiste mejor que el debito"
             if ia_a > ia_b else "El debito resiste mejor que el credito",
             "%s %s <b>%s</b> real interanual frente a <b>%s</b> de %s, una brecha de "
             "<b>%s puntos</b>."
             % (a["metrica"], verbo(ia_a), pct(abs(ia_a), 1, False), pct(ia_b),
                b["metrica"].lower(), num(abs(ia_a - ia_b), 1))))

    # Transferencias: contraste entre el instrumento masivo y el que mas crece
    tr = {x["metrica"]: x for x in d["series"]
          if x["pestania"] == "Transferencias de fondos"}
    push = tr.get('Transferencias inmediatas "push"')
    pct_i = tr.get("Pagos con transferencia interoperables")
    if push and pct_i:
        pp_, pc = push["periodos"][-1], pct_i["periodos"][-1]
        if pp_["var_ia_monto_real"] is not None and pc["var_ia_monto_real"] is not None:
            msgs.append(
                ("El pago con transferencia crece a otra velocidad",
                 "En %s los PCT interoperables %s <b>%s</b> real interanual, frente a "
                 "<b>%s</b> de las transferencias push. Son datos al mes de analisis, "
                 "un mes mas adelante que tarjetas."
                 % (mes_largo(pc["mes"]),
                    "crecen" if pc["var_ia_monto_real"] >= 0 else "caen",
                    pct(abs(pc["var_ia_monto_real"]), 1, False),
                    pct(pp_["var_ia_monto_real"]))))

    # Volumen contra monto: si divergen, el ticket esta cediendo
    div_qty = [s for s in ars
               if s["periodos"][-1]["var_ia_cantidad"] is not None
               and (s["periodos"][-1]["var_ia_cantidad"] >= 0)
               != (s["periodos"][-1]["var_ia_monto_real"] >= 0)]
    if div_qty:
        s0 = div_qty[0]
        p0 = s0["periodos"][-1]
        msgs.append(
            ("Se opera mas veces por montos mas chicos",
             "En %s las operaciones %s <b>%s</b> mientras el monto real %s <b>%s</b>. "
             "El ticket promedio real se ubica en <b>$ %s</b>."
             % (s0["metrica"].lower(),
                "crecen" if p0["var_ia_cantidad"] >= 0 else "caen",
                pct(abs(p0["var_ia_cantidad"]), 1, False),
                "cae" if p0["var_ia_monto_real"] < 0 else "crece",
                pct(abs(p0["var_ia_monto_real"]), 1, False),
                num(p0["ticket_promedio_real"], 0))))

    # Comparaciones de ticket promedio real dentro de una misma pestania.
    for args in (
        ("Tarjetas", "Tarjetas de crédito", "Tarjetas de débito",
         "El credito mueve tickets del doble que el debito"),
        ("TC Modalidad de pago", "En Cuotas", "Un pago",
         "La cuota se reserva para la compra grande"),
    ):
        m = cmp_ticket(d, *args)
        if m:
            msgs.append(m)

    return "".join('<li><h3>%s</h3><p>%s</p></li>' % (html.escape(t_), c)
                   for t_, c in msgs[:6])


# --------------------------------------------------------------------------
# Bloques
# --------------------------------------------------------------------------

def kpis(d):
    r = d.get("resumen") or {}
    t = r.get("tarjetas_ars") or {}
    if not t.get("monto_real"):
        return ""
    div, unidad = escala(t["monto_real"])
    items = [
        (num(t["monto_real"] / div), unidad,
         "Monto operado con tarjetas, a precios constantes de %s"
         % mes_largo(d["deflactor"]["mes_base"])),
        (pct(t.get("var_ia_monto_real")), "interanual real",
         "Contra el mismo mes del ano anterior, descontada la inflacion"),
        (cantidad(t.get("cantidad")), "operaciones", "Transacciones del mes"),
        ("$ " + num(t.get("ticket_promedio_real"), 0), "ticket promedio real",
         "Monto real sobre cantidad de operaciones"),
    ]
    return ('<section class="kpis">%s</section>' % "".join(
        '<div><b>%s</b><span class="u">%s</span><span class="d">%s</span></div>'
        % (v, html.escape(u), html.escape(dd)) for v, u, dd in items))


def exhibit(n, titulo, contenido, kicker, edicion, extra="", alcance=None):
    cab = '<p class="exnum">Exhibit %d</p>' % n
    if alcance:
        cab += '<p class="alcance">%s</p>' % html.escape(alcance)
    return ('<section id="ex-%d" class="ex%s">%s<h2 class="accion">%s</h2>%s'
            '<p class="kicker">%s</p>'
            '<p class="fuente">%s<a class="arriba" href="#contenido">Volver arriba'
            "</a></p></section>"
            % (n, extra, cab, titulo, contenido, kicker, FUENTE % edicion))


def exhibit_serie(n, s, base, pestania, edicion):
    per = s["periodos"]
    ult = per[-1]
    if s.get("moneda", "ARS") != "ARS":
        return exhibit_usd(n, s, edicion)
    alcance = ALCANCE.get(pestania)
    maxr = max([p["monto_real"] for p in per if p["monto_real"] is not None] or [0])
    div, unidad = escala(maxr)

    filas = "".join(
        "<tr><td>%s</td><td>%s</td><td>%s</td><td>%s</td><td>%s</td></tr>"
        % (mes_ab(p["mes"]),
           num(p["monto_real"] / div) if p["monto_real"] else "—",
           cantidad(p["cantidad"]),
           ("$ " + num(p["ticket_promedio_real"], 0))
           if p["ticket_promedio_real"] else "—",
           pct(p["var_ia_monto_real"]))
        for p in reversed(per))

    tdiv, tunidad, tdec = escala_ticket(
        max([p["ticket_promedio_real"] for p in per
             if p["ticket_promedio_real"] is not None] or [0]))
    cuerpo = (
        '<div class="dosgr">'
        '<figure><figcaption>Monto mensual a precios constantes de %s · %s'
        "</figcaption>%s</figure>"
        '<div class="col">'
        '<figure><figcaption>Variacion interanual real · %%</figcaption>%s</figure>'
        '<figure><figcaption>Ticket promedio real · %s</figcaption>%s</figure>'
        "</div></div>"
        "<details><summary>Ver los %d meses de la serie en numeros</summary>"
        "<table><thead><tr><th>Mes</th><th>Monto real<br><i>%s</i></th>"
        "<th>Operaciones</th><th>Ticket real</th><th>Var. i.a. real</th>"
        "</tr></thead><tbody>%s</tbody></table></details>"
        % (mes_largo(base), unidad, barras_campo(per, "monto_real", div, unidad),
           barras_ia(per), tunidad,
           barras_campo(per, "ticket_promedio_real", tdiv, tunidad, tdec, alto=190,
                        color="gris", color_ultimo="gris_osc"),
           len(per), unidad, filas))

    extra = ""
    if ult["ticket_promedio_real"]:
        extra = " El ticket promedio real del mes es $ %s." % num(
            ult["ticket_promedio_real"], 0)
    kicker = ("Todas las cifras estan en pesos de %s. Arriba a la derecha, cada mes "
              "comparado contra el mismo mes del ano anterior: verde cuando crece, "
              "rojo cuando cae. Abajo, el ticket promedio real, que muestra si "
              "el movimiento del monto viene del tamano de cada compra o de la "
              "cantidad de compras.%s%s" % (mes_largo(base), extra,
                                            (" %s." % alcance) if alcance else ""))
    return exhibit(n, titulo_accion(s, pestania), cuerpo, kicker, edicion,
                   alcance=alcance)


def exhibit_usd(n, s, edicion):
    per = s["periodos"]
    ult = per[-1]
    maxn = max([p["monto_nominal"] for p in per if p["monto_nominal"] is not None]
               or [0])
    div = 1e6 if maxn >= 1e6 else 1.0
    unidad = "millones de USD" if div > 1 else "USD"
    filas = "".join(
        "<tr><td>%s</td><td>%s</td><td>%s</td></tr>"
        % (mes_ab(p["mes"]),
           num(p["monto_nominal"] / div) if p["monto_nominal"] else "—",
           cantidad(p["cantidad"])) for p in reversed(per))
    cuerpo = ('<div class="cifras"><div><b>%s</b><span>%s en %s</span></div>'
              '<div><b>%s</b><span>operaciones</span></div></div>'
              "<details><summary>Ver los %d meses de la serie en numeros</summary>"
              "<table><thead><tr><th>Mes</th><th>Monto<br><i>%s</i></th>"
              "<th>Operaciones</th></tr></thead><tbody>%s</tbody></table></details>"
              % (num(ult["monto_nominal"] / div) if ult["monto_nominal"] else "—",
                 unidad, mes_largo(ult["mes"]), cantidad(ult["cantidad"]),
                 len(per), unidad, filas))
    return exhibit(
        n, "%s se publica sin serie real: esta denominada en dolares" % s["metrica"],
        cuerpo,
        "El monto de esta serie esta en dolares estadounidenses (nota 4 del informe). "
        "Aplicarle el IPC argentino daria una cifra sin significado economico, asi que "
        "queda fuera de la deflactacion.", edicion)


def exhibit_control(n, d):
    """Ultimo exhibit: donde el Excel y el PDF no dicen exactamente lo mismo."""
    vs = d.get("validacion_pdf") or []
    ed = d["edicion"]
    if not vs:
        return exhibit(n, "Esta corrida no pudo contrastarse contra el informe", "",
                       "No se extrajeron del PDF cifras comparables, asi que los "
                       "numeros de este informe no estan verificados contra una "
                       "segunda fuente.", ed, extra=" ctrl")
    filas = "".join(
        '<tr class="%s"><td>%s</td><td>%s</td><td>%s</td><td>%s pp</td>'
        '<td class="vd">%s</td></tr>'
        % ("ok" if v["dentro_de_tolerancia"] else "fuera",
           html.escape(v["concepto"].replace(" — ", ": ")),
           pct(v["valor_bcra"]), pct(v["valor_calculado"]),
           num(v["delta_pp"], 2) if v["delta_pp"] is not None else "—",
           "Coincide" if v["dentro_de_tolerancia"] else "Revisar")
        for v in vs)
    ok = all(v["dentro_de_tolerancia"] for v in vs)
    peor = max([v["delta_pp"] for v in vs if v["delta_pp"] is not None] or [0])
    titulo = ("El calculo sobre el Excel reproduce lo que el PDF declara, dentro de "
              "%s pp" % num(peor, 2)) if ok else (
        "El calculo sobre el Excel no reproduce lo que el PDF declara")
    tabla = ('<table class="tv"><thead><tr><th>Concepto</th>'
             "<th>Declara el PDF</th><th>Calculado sobre el Excel</th>"
             "<th>Diferencia</th><th></th></tr></thead><tbody>%s</tbody></table>"
             % filas)
    return exhibit(n, titulo, tabla,
                   "El BCRA publica los datos en dos formatos: la planilla de series y "
                   "el texto del informe. El agente calcula las variaciones desde la "
                   "planilla y las compara contra las que el PDF enuncia en prosa. Son "
                   "dos fuentes independientes: si el deflactor o la lectura del Excel "
                   "estuvieran mal, no coincidirian. Tolerancia aceptada: 0,5 puntos "
                   "porcentuales.", ed, extra=" ctrl")


GLOSARIO = [
    ("Pesos constantes (real)",
     "Todos los montos de este informe estan llevados al poder adquisitivo de un "
     "unico mes usando el IPC Nivel General del INDEC. Recien asi se pueden comparar "
     "meses entre si."),
    ("Variacion interanual real",
     "Cambio contra el mismo mes del ano anterior. Se compara contra el mismo mes, y "
     "no contra el anterior, para neutralizar la estacionalidad."),
    ("Ticket promedio real",
     "Monto real sobre cantidad de operaciones. Sube cuando cada compra es mas "
     "grande, aunque haya menos compras."),
    ("Participacion",
     "Peso de cada serie en el monto del mes. Se calcula sobre montos nominales: "
     "dentro de un mismo mes, deflactar no altera una participacion."),
    ("Mes de corte de tarjetas",
     "El informe lleva el nombre de un mes, pero los datos de tarjetas llegan un mes "
     "antes. Todo lo que se muestra aca respeta ese corte, no el del titulo."),
    ("Series en moneda extranjera",
     "Las tarjetas de debito en dolares se publican en USD y no se deflactan por IPC "
     "argentino, asi que para esa serie solo hay monto nominal."),
]


def render(d):
    ed = d["edicion"]
    if d["estado"] == "error":
        cuerpo = ('<section class="ex fallo">'
                  '<p class="exnum">Resultado de la corrida</p>'
                  '<h2 class="accion">La corrida se detuvo sin producir datos</h2>'
                  '<p class="kicker">El agente no calculo nada porque la fuente no '
                  "estaba disponible. Es el comportamiento esperado: no sustituye por "
                  "otra edicion ni emite series vacias.</p>%s</section>"
                  % "".join('<p class="det">%s</p>' % html.escape(e)
                            for e in d["errores"]))
    else:
        base = d["deflactor"]["mes_base"]
        avisos = ""
        if d["advertencias"]:
            avisos = ('<section class="avisos"><h3>Advertencias de esta corrida</h3>'
                      "<ul>%s</ul></section>"
                      % "".join("<li>%s</li>" % html.escape(a)
                                for a in d["advertencias"]))
        grupos = {}
        for s in d["series"]:
            grupos.setdefault(s["pestania"], []).append(s)

        mes_ult = d["corte"]["mes_corte_tarjetas"]
        n, bloques, nav = 1, [], []
        for k, (pest, ss) in enumerate(grupos.items()):
            gid = "grp-%d" % k
            mix, lider = barra_mix(ss, mes_ult)
            blq = ('<div class="seccab" id="%s"><h2>%s</h2><p>%s</p></div>'
                   % (gid, html.escape(pest), html.escape(QUE_MIDE.get(pest, ""))))
            items = []
            if mix and lider:
                blq += exhibit(
                    n, "%s concentra %s del monto %s"
                    % (lider[0], pct(lider[1], 1, False),
                       de(EN_FRASE.get(pest, pest.lower()))),
                    '<div class="mix">%s</div>' % mix,
                    "Participacion de cada serie en el monto operado en %s."
                    % mes_largo(mes_ult), ed, alcance=ALCANCE.get(pest))
                items.append(("Composicion", "ex-%d" % n))
                n += 1
            for s in ss:
                blq += exhibit_serie(n, s, base, pest, ed)
                items.append((s["metrica"], "ex-%d" % n))
                n += 1
            # TC Modalidad de pago no entra al indice.
            if pest != "TC Modalidad de pago":
                nav.append((pest, gid, items))
            bloques.append('<div class="grupo">%s</div>' % blq)

        cid = "grp-control"
        bloques.append('<div class="grupo"><div class="seccab" id="%s"><h2>Control de '
                       "consistencia</h2><p>Contraste entre la planilla de series y "
                       "el texto del informe.</p></div>%s</div>"
                       % (cid, exhibit_control(n, d)))
        nav.append(("Control de consistencia", cid, []))

        glos = "".join("<div><b>%s</b><p>%s</p></div>"
                       % (html.escape(t), html.escape(x)) for t, x in GLOSARIO)
        notas = ""
        if d.get("notas"):
            notas = ('<div class="notas"><b>Notas de esta corrida</b><ul>%s</ul></div>'
                     % "".join("<li>%s</li>" % html.escape(x) for x in d["notas"]))
        menu = "".join(
            '<div class="navcol"><a class="navtit" href="#%s">%s</a>%s</div>'
            % (gid, html.escape(titulo),
               ("<ul>%s</ul>" % "".join(
                   '<li><a href="#%s">%s</a></li>' % (i, html.escape(lab))
                   for lab, i in its)) if its else "")
            for titulo, gid, its in nav)
        cuerpo = ('<nav class="indice" id="contenido">'
                  '<p class="navcab">Contenido</p>'
                  '<div class="navgrid">%s</div></nav>'
                  '<section class="sintesis"><h2>Sintesis ejecutiva</h2><ol>%s</ol>'
                  "</section>%s%s%s"
                  '<section class="metodo"><h2>Como leer estas metricas</h2>'
                  '<div class="gl">%s</div>%s</section>'
                  % (menu, sintesis(d), kpis(d), avisos, "".join(bloques),
                     glos, notas))

    c = d["corte"]
    firma = ("Requiere revision del analista antes de publicar"
             if d["requiere_revision_humana"]
             else "Sin observaciones automaticas. La publicacion la firma el analista")
    return TEMPLATE % {
        "edicion": html.escape(ed),
        "estado": html.escape(d["estado"].replace("_", " ")),
        "corte": html.escape(mes_largo(c["mes_corte_tarjetas"])
                             if c.get("mes_corte_tarjetas") else "sin determinar"),
        "analisis": html.escape(mes_largo(c["mes_analisis"])),
        "base": html.escape(mes_largo(d["deflactor"]["mes_base"])
                            if d["deflactor"].get("mes_base") else "—"),
        "generado": html.escape(d["generado_utc"]),
        "firma": html.escape(firma),
        "logo": logo_html(),
        "cuerpo": cuerpo,
    }


TEMPLATE = """<!doctype html>
<html lang="es"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Pagos minoristas en pesos constantes | edicion %(edicion)s</title>
<style>
:root{
  --deep:#051C2C; --electric:#2251FF; --cyan:#00A9F4; --negro:#000000;
  --gris:#9AA3AB; --gris_osc:#6B747C; --verde:#1B7F4B; --rojo:#C0392B;
  --fondo:#E4E6E8; --papel:#FFFFFF;
  --rejilla:#E0E3E6; --borde:#CFD4D8; --texto:#0F1720; --suave:#5F6B75;
  --m1:#051C2C; --m2:#2251FF; --m3:#00A9F4; --m4:#A8DCF7;
  --avisofondo:#FFF6E0; --avisoborde:#E8C877;
}
*{box-sizing:border-box}
html{-webkit-text-size-adjust:100%%}
body{margin:0;background:var(--fondo);color:var(--texto);
  font:15.5px/1.6 "Helvetica Neue",Helvetica,Arial,sans-serif;
  font-variant-numeric:tabular-nums}
.env{max-width:1180px;margin:0 auto;padding:0 30px 90px}

.hero{background:var(--deep);color:#fff;margin:0 -30px 40px;padding:52px 30px 40px}
.hero .in{max-width:1120px;margin:0 auto}
.hero .titulo{display:flex;align-items:flex-start;justify-content:space-between;
  gap:32px;margin-bottom:10px}
.hero h1{font:400 40px/1.15 Georgia,"Times New Roman",serif;margin:0;
  letter-spacing:-.015em;max-width:20ch}
.marca{height:42px;width:auto;flex:0 0 auto;margin-top:4px}
.hero .lead{margin:0 0 30px;font-size:16px;color:#AFC0CC;max-width:66ch}
.hero .ficha{display:flex;flex-wrap:wrap;border-top:1px solid #1D3849;
  padding-top:22px}
.hero .ficha div{flex:1 1 175px;padding:0 24px;border-left:1px solid #1D3849}
.hero .ficha div:first-child{padding-left:0;border-left:0}
.hero .ficha b{display:block;font-size:16px;font-weight:600}
.hero .ficha span{font-size:12.5px;color:#8798A5}
.hero .firma{margin:22px 0 0;font-size:13px;color:#8798A5}

.indice{background:var(--papel);border-top:4px solid var(--deep);
  padding:22px 30px 24px;margin-bottom:26px}
.navcab{margin:0 0 16px;font:600 12.5px/1.3 "Helvetica Neue",Arial,sans-serif;
  letter-spacing:.15em;text-transform:uppercase;color:var(--electric)}
.navgrid{display:grid;grid-template-columns:repeat(auto-fit,minmax(215px,1fr));
  gap:20px 28px}
.navcol{min-width:0}
.navtit{display:block;font:600 14px/1.35 "Helvetica Neue",Arial,sans-serif;
  color:var(--deep);text-decoration:none;padding-bottom:7px;
  border-bottom:1px solid var(--borde)}
.navtit:hover{color:var(--electric)}
.navcol ul{list-style:none;margin:9px 0 0;padding:0}
.navcol li{margin:0 0 5px}
.navcol li a{font-size:13px;color:var(--suave);text-decoration:none}
.navcol li a:hover{color:var(--electric);text-decoration:underline}
.seccab[id],.ex[id]{scroll-margin-top:16px}
.sintesis{background:var(--papel);border-top:4px solid var(--electric);
  padding:28px 30px 30px;margin-bottom:26px}
.sintesis h2,.seccab h2,.metodo h2{font:600 12.5px/1.3 "Helvetica Neue",Arial,
  sans-serif;letter-spacing:.15em;text-transform:uppercase;color:var(--electric);
  margin:0 0 18px}
.sintesis ol{list-style:none;counter-reset:s;margin:0;padding:0;display:grid;
  grid-template-columns:repeat(auto-fit,minmax(290px,1fr));gap:28px}
.sintesis li{counter-increment:s;position:relative;padding-left:42px}
.sintesis li::before{content:counter(s);position:absolute;left:0;top:1px;
  width:28px;height:28px;background:var(--deep);color:#fff;font-size:13px;
  font-weight:600;display:flex;align-items:center;justify-content:center}
.sintesis h3{font:600 17px/1.35 Georgia,serif;margin:0 0 7px}
.sintesis p{margin:0;font-size:14.5px;color:#2C3740}
.sintesis b{font-weight:600;color:var(--deep)}

.kpis{display:grid;grid-template-columns:repeat(auto-fit,minmax(210px,1fr));
  background:var(--papel);margin-bottom:38px}
.kpis div{padding:24px 26px;border-left:1px solid var(--borde)}
.kpis div:first-child{border-left:0}
.kpis b{display:block;font:600 31px/1.1 "Helvetica Neue",Arial,sans-serif;
  color:var(--deep);letter-spacing:-.02em}
.kpis .u{display:block;font-size:12.5px;font-weight:600;color:var(--electric);
  margin-top:5px}
.kpis .d{display:block;font-size:12px;line-height:1.45;color:var(--suave);
  margin-top:5px}

.grupo{margin-bottom:40px}
.seccab{margin:0 0 18px}
.seccab h2{margin-bottom:6px;padding-bottom:9px;border-bottom:2px solid var(--deep)}
.seccab p{margin:0;font-size:14px;color:var(--suave);max-width:74ch}
.ex{background:var(--papel);border-top:3px solid var(--deep);
  padding:24px 28px 20px;margin-bottom:20px}
.ex.ctrl{border-top-color:var(--cyan)}
.exnum{margin:0 0 6px;font-size:11px;font-weight:600;letter-spacing:.16em;
  text-transform:uppercase;color:var(--suave)}
.alcance{display:inline-block;margin:0 0 12px;padding:4px 10px;
  background:var(--deep);color:#fff;font-size:11px;font-weight:600;
  letter-spacing:.06em;text-transform:uppercase}
.accion{font:600 22px/1.32 Georgia,serif;margin:0 0 22px;max-width:54ch;
  color:var(--deep)}
.kicker{margin:16px 0 0;font-size:13px;line-height:1.55;color:#2C3740;max-width:80ch}
.fuente{margin:14px 0 0;padding-top:11px;border-top:1px solid var(--rejilla);
  font-size:11.5px;color:var(--suave);display:flex;flex-wrap:wrap;gap:8px 20px;
  align-items:baseline;justify-content:space-between}
.arriba{color:var(--electric);text-decoration:none;font-weight:600;
  white-space:nowrap}
.arriba:hover{text-decoration:underline}
.indice{scroll-margin-top:16px}

.dosgr{display:grid;gap:24px}
.col{display:grid;gap:22px;min-width:0}
figure{margin:0;min-width:0}
figcaption{font-size:12px;color:var(--suave);margin-bottom:8px;font-weight:600}
.gr{width:100%%;height:auto;display:block}
.ejey{font-size:10.5px;fill:var(--suave);text-anchor:end}
.ejey.rot{text-anchor:start;font-size:10px}
.ejex{font-size:10.5px;fill:var(--suave);text-anchor:middle}
.etq{font-size:11.5px;font-weight:700;text-anchor:start}
.etq.deep{fill:var(--deep)}
.sinserie{font-size:13px;color:var(--suave);padding:18px 0}

/* Composicion: HTML, no SVG. Un SVG estirado deforma la tipografia. */
.mixbar{display:flex;width:100%%;height:38px;overflow:hidden}
.sg{display:flex;align-items:center;justify-content:center;font-size:13px;
  font-weight:700;color:#fff;min-width:0;overflow:hidden}
.sg.m1{background:var(--m1)}.sg.m2{background:var(--m2)}
.sg.m3{background:var(--m3)}.sg.m4{background:var(--m4);color:var(--deep)}
.mixleg{list-style:none;display:flex;flex-wrap:wrap;gap:10px 26px;margin:14px 0 0;
  padding:0;font-size:13.5px}
.mixleg li{display:flex;align-items:center;gap:8px}
.mixleg b{font-weight:600;color:var(--deep)}
.pto{width:12px;height:12px;display:inline-block}
.pto.m1{background:var(--m1)}.pto.m2{background:var(--m2)}
.pto.m3{background:var(--m3)}.pto.m4{background:var(--m4)}

.tv{width:100%%;border-collapse:collapse;font-size:14px}
.tv th{text-align:right;font-weight:600;font-size:11.5px;letter-spacing:.04em;
  text-transform:uppercase;color:var(--suave);padding:0 10px 9px;
  border-bottom:1.5px solid var(--deep)}
.tv th:first-child{text-align:left}
.tv td{text-align:right;padding:10px;border-bottom:1px solid var(--rejilla)}
.tv td:first-child{text-align:left}
.tv .vd{font-size:12px;font-weight:600;color:var(--electric)}
.tv tr.fuera .vd{color:#B3261E}

.cifras{display:flex;gap:48px;flex-wrap:wrap;padding:6px 0}
.cifras b{display:block;font:600 29px/1.1 "Helvetica Neue",Arial,sans-serif;
  color:var(--deep)}
.cifras span{font-size:12.5px;color:var(--suave)}

details{margin-top:20px}
details summary{cursor:pointer;font-size:12.5px;font-weight:600;color:var(--electric)}
details table{width:100%%;border-collapse:collapse;margin-top:12px;font-size:12.5px}
details th,details td{text-align:right;padding:6px 8px;
  border-bottom:1px solid var(--rejilla)}
details th:first-child,details td:first-child{text-align:left}
details th{font-weight:600;color:var(--suave);vertical-align:bottom}
details th i{font-style:normal;font-weight:400;font-size:10.5px}

.avisos{background:var(--avisofondo);border:1px solid var(--avisoborde);
  padding:18px 24px;margin-bottom:28px}
.avisos h3{margin:0;font:600 14px/1.3 "Helvetica Neue",Arial,sans-serif}
.avisos ul{margin:8px 0 0;padding-left:20px;font-size:14px}
.fallo{border-top-color:#B3261E}
.fallo .det{font-size:12.5px;color:#B3261E;margin:14px 0 0;word-break:break-word}

.metodo{background:var(--papel);padding:26px 30px}
.gl{display:grid;grid-template-columns:repeat(auto-fit,minmax(255px,1fr));
  gap:20px 32px}
.gl b{font-size:13.5px}
.gl p{margin:4px 0 0;font-size:13px;line-height:1.55;color:var(--suave)}
.notas{margin-top:26px;padding:16px 20px;background:#F2F4F5;
  border-left:3px solid var(--cyan)}
.notas b{font-size:13px}
.notas ul{margin:6px 0 0;padding-left:20px;font-size:13px;color:var(--suave)}

.pie{margin-top:36px;font-size:11.5px;color:var(--suave)}
@media (min-width:1000px){.dosgr{grid-template-columns:1.1fr 1fr;align-items:start}}
@media (max-width:700px){
  .env{padding:0 16px 60px}.hero{margin:0 -16px 30px;padding:34px 16px 28px}
  .hero h1{font-size:27px}.accion{font-size:19px}
  .hero .titulo{flex-direction:column-reverse;align-items:flex-start;gap:18px}
  .marca{height:32px;margin-top:0}
  .hero .ficha div{flex:1 1 46%%;border-left:0;padding:8px 0}
  .kpis div{border-left:0;border-top:1px solid var(--borde)}
  .kpis div:first-child{border-top:0}
  .sintesis,.metodo,.ex{padding-left:18px;padding-right:18px}
}
@media print{.hero{background:var(--deep)!important;-webkit-print-color-adjust:exact}
  .ex{break-inside:avoid}}
</style></head><body><div class="env">
<header class="hero"><div class="in">
<div class="titulo"><div>
<h1>Pagos minoristas en pesos constantes</h1>
</div>%(logo)s</div>
<p class="lead">Lectura del negocio de tarjetas a partir del Informe Mensual de Pagos
Minoristas del BCRA, edicion %(edicion)s. Todas las series estan deflactadas por IPC
y contrastadas contra la propia fuente.</p>
<div class="ficha">
<div><b>%(analisis)s</b><span>Mes de analisis del informe</span></div>
<div><b>%(corte)s</b><span>Ultimo dato de tarjetas</span></div>
<div><b>%(base)s</b><span>Base de pesos constantes</span></div>
<div><b>%(estado)s</b><span>Estado de la corrida</span></div>
</div>
<p class="firma">%(firma)s</p>
</div></header>
%(cuerpo)s
<footer class="pie">
Generado por el Agente PMR el %(generado)s a partir de salida.json. El dashboard no
recalcula ninguna cifra. Datos: Banco Central de la Republica Argentina; deflactor:
IPC Nacional Nivel General, INDEC.
</footer>
</div></body></html>
"""


def main():
    ruta = sys.argv[1]
    d = json.load(open(ruta, encoding="utf-8"))
    destino = os.path.join(os.path.dirname(ruta), "dashboard.html")
    with open(destino, "w", encoding="utf-8") as f:
        f.write(render(d))
    print("escrito:", destino)


if __name__ == "__main__":
    main()
