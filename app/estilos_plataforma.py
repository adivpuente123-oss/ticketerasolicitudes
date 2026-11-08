"""Estilo de la plataforma de solicitudes: tabla limpia con tarjetas de resumen (inspirado en una ticketera moderna)."""
import html
import base64
from pathlib import Path
from functools import lru_cache
import zlib
from datetime import date

import pandas as pd

AMARILLO, ROJO, NARANJA, VERDE, AZUL, GRIS = "#ffd21f", "#d64545", "#e8803a", "#1f9d55", "#2f6fd1", "#8a8a94"
COLORES_AVATAR = ["#5b7fc7", "#c9774f", "#7b5ea7", "#3a9bb0", "#2f8f5b", "#b5527a", "#8a7a3a", "#4b6cb7"]

CSS = "<style>" + (Path(__file__).parent / "portal.css").read_text(encoding="utf-8") + "</style>"

_S = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">{}</svg>'
ICONO = {
    "solicitudes": _S.format('<rect x="3.5" y="5" width="17" height="14" rx="2.5"/><path d="M9 5v14M13 10h4M13 14h4"/>'),
    "gestionar": _S.format('<path d="M4 7h10M18 7h2M4 17h2M10 17h10"/><circle cx="16" cy="7" r="2"/><circle cx="8" cy="17" r="2"/>'),
    "nueva": _S.format('<circle cx="12" cy="12" r="8.5"/><path d="M12 8.5v7M8.5 12h7"/>'),
    "correo": _S.format('<rect x="3.5" y="5.5" width="17" height="13" rx="2.5"/><path d="M4 8l8 5.5L20 8"/>'),
    "usuarios": _S.format('<circle cx="9" cy="8.5" r="3"/><path d="M3.5 19c0-3 2.4-5 5.5-5s5.5 2 5.5 5"/><path d="M16 5.8a3 3 0 0 1 0 5.4M17.5 14.3c2 .5 3 2 3 4.2"/>'),
    "salir": _S.format('<path d="M14 4.5h3.5A2 2 0 0 1 19.5 6.5v11a2 2 0 0 1-2 2H14"/><path d="M4.5 12H14M10.5 8.5L14 12l-3.5 3.5"/>'),
    "total": _S.format('<rect x="3.5" y="5.5" width="17" height="13" rx="2.5"/><path d="M8 10h8M8 14h5"/>'),
    "abiertas": _S.format('<circle cx="12" cy="12" r="8.5"/><circle cx="12" cy="12" r="2.2"/>'),
    "pendientes": _S.format('<circle cx="12" cy="12" r="8.5"/><path d="M12 7.5V12l3 2"/>'),
    "respondidas": _S.format('<circle cx="12" cy="12" r="8.5"/><path d="M8.5 12.2l2.5 2.5 4.5-5"/>'),
    "tag": _S.format('<path d="M4 12.5V5h7.5l8 8-7.5 7.5-8-8z"/><circle cx="8.5" cy="9.5" r="1"/>'),
    "mail": _S.format('<rect x="3.5" y="5.5" width="17" height="13" rx="2.5"/><path d="M4 8l8 5.5L20 8"/>'),
    "web": _S.format('<circle cx="12" cy="12" r="8.5"/><path d="M3.5 12h17M12 3.5c2.5 2.5 2.5 14.5 0 17M12 3.5c-2.5 2.5-2.5 14.5 0 17"/>'),
    "excel": _S.format('<rect x="4.5" y="3.5" width="15" height="17" rx="2.5"/><path d="M8.5 9h7M8.5 13h7M8.5 17h4"/>'),
    "arriba": _S.format('<path d="M12 18V6M6.5 11.5L12 6l5.5 5.5"/>'),
    "guion": _S.format('<path d="M6 12h12"/>'),
    "circulo": _S.format('<circle cx="12" cy="12" r="7" stroke-dasharray="2.4 3.2"/>'),
}


def esc(x) -> str:
    return html.escape("" if x is None or (isinstance(x, float) and pd.isna(x)) else str(x))


def numero(codigo) -> str:
    return str(codigo).replace("SOL-", "")


def mascara(cuenta) -> str:
    c = "" if cuenta is None or (isinstance(cuenta, float) and pd.isna(cuenta)) else str(cuenta)
    return f"****{c[-4:]}" if c else "—"


def color_avatar(nombre) -> str:
    return COLORES_AVATAR[zlib.crc32(str(nombre).encode()) % len(COLORES_AVATAR)]


def iniciales(nombre) -> str:
    partes = str(nombre).split()
    return (partes[0][:1] + (partes[1][:1] if len(partes) > 1 else "")).upper() if partes else "?"


def _nulo(d) -> bool:
    return d is None or pd.isna(d)


def prioridad(dias):
    """Prioridad según los días que lleva abierta (mismos cortes del dashboard: 15, 30 y 60)."""
    if _nulo(dias):
        return "—", "guion", GRIS
    return (("Crítica", "arriba", ROJO) if dias > 60 else ("Urgente", "arriba", NARANJA) if dias > 30 else
            ("Atención", "guion", "#d6a500") if dias > 15 else ("Normal", "circulo", GRIS))


def plazo(dias):
    """Salud del plazo de 30 días: al día, por vencer o vencido."""
    if _nulo(dias):
        return "—", None
    return (("Vencido", "rojo") if dias > 30 else ("Por vencer", "amar") if dias > 15 else ("Al día", "gris"))


# ---------- piezas ----------
def nav_item(icono: str, titulo: str, activo: bool = False) -> str:
    return f'<div class="nv{" on" if activo else ""}" title="{esc(titulo)}">{ICONO[icono]}</div>'


def logo_y() -> str:
    return ('<div class="brand"><span class="brand-mark">' + ICONO["total"] + '</span>'
            '<div><strong>Solicitudes</strong><small>Centro de atención</small></div></div>')


@lru_cache(maxsize=1)
def foto_uri():
    archivo = Path(__file__).parent / "assets" / "arquitectura.webp"
    return "data:image/webp;base64," + base64.b64encode(archivo.read_bytes()).decode() if archivo.exists() else ""


def acceso_visual():
    fondo = f"background-image:linear-gradient(180deg,rgba(9,25,48,.18),rgba(9,25,48,.93)),url('{foto_uri()}')"
    return (f'<section class="access-art" style="{fondo}">' + logo_y()
            + '<div><div class="eyebrow">Gestión de solicitudes</div><h1>Cada solicitud.<br>Un paso adelante.</h1>'
              '<p>Coordina la atención de tu equipo con información clara, seguimiento continuo y todas las respuestas en un solo lugar.</p></div>'
              '<div class="access-foot">Un espacio de trabajo para supervisores y equipo de atención.</div></section>')


def banner_trabajo():
    fondo = f"background-image:linear-gradient(90deg,#142945 20%,rgba(20,41,69,.78) 65%,rgba(20,41,69,.45)),url('{foto_uri()}')"
    return (f'<section class="workspace-banner" style="{fondo}"><div><div class="eyebrow">Centro de atención</div>'
            '<h1>Una visión clara de cada solicitud.</h1><p>Organiza la atención, consulta los avances y mantén a tu equipo informado.</p></div></section>')


def ticket_resumen(t, dias, modo):
    prioridad_texto = prioridad(dias)[0] if t["estado"] != "Respondida" else "Cerrada"
    canal = {"web":"Web", "correo":"Correo", "excel":"Excel"}.get(t["origen"], t["origen"])
    encabezado = ('<div class="ticket-heading"><span class="ticket-code">' + esc(t["codigo"]) + '</span>'
                  + pill_estado(t["estado"]) + _celda_plazo(dias,t["estado"]) + '</div>')
    campos = [("Supervisor",str(t["supervisor"]).title())] if modo == "bo" else [("Solicitada",_fecha_corta(t["fecha_solicitud"]))]
    campos += [("Cartera",t["cartera"]),("Cuenta",mascara(t["cuenta"])),("Canal",canal),("Prioridad",prioridad_texto)]
    metadata = '<div class="ticket-meta">' + ''.join(f'<span>{esc(k)} <strong>{esc(v)}</strong></span>' for k,v in campos) + '</div>'
    respuesta = ('<div class="ticket-answer">' + esc(t["respuesta"]) + '</div>') if modo=="sup" and t["respuesta"] else ""
    return encabezado + '<div class="ticket-title">' + esc(t["tipo_consulta"] or "Solicitud por completar") + '</div>' + metadata + respuesta


def cabecera(pagina: str, nombre: str, rol: str) -> str:
    return (f'<div class="mig"><span class="breadcrumbs"><span>Plataforma</span><span>/</span><b>{esc(pagina)}</b></span>'
            f'<span class="yo"><span class="av" style="background:{color_avatar(nombre)}">{esc(iniciales(nombre))}</span>{esc(nombre.title())} · {esc(rol)}</span></div>')


def kpi(etiqueta: str, icono: str, valor: int, delta: str, clase: str) -> str:
    return (f'<div class="kp"><div class="et">{ICONO[icono]}{esc(etiqueta)}</div><div class="in"><div class="n">{valor:,}</div>'
            f'<div class="d {clase}">{delta}</div></div></div>')


def pill(texto, clase, punto=True) -> str:
    colores = {"p-azul": "#2f6fd1", "p-amar": "#e0a800", "p-gris": "#9a9aa5", "p-rojo": "#d64545", "p-verde": "#1f9d55"}
    p = f'<i style="background:{colores[clase]}"></i>' if punto else ""
    return f'<span class="pill {clase}">{p}{esc(texto)}</span>'


def pill_estado(estado) -> str:
    return {"Recibida": pill("Recibida", "p-azul", False), "Enviada a verificar": pill("En verificación", "p-amar", False),
            "Respondida": pill("Respondida", "p-verde", False)}.get(estado, pill(str(estado), "p-gris", False))


def _celda_plazo(dias, estado) -> str:
    if estado == "Respondida":
        return pill("Cerrada", "p-gris")
    txt, clase = plazo(dias)
    return pill(txt, f"p-{clase}") if clase else "—"


def _canal(origen) -> str:
    icono, nombre = {"correo": ("mail", "Correo"), "web": ("web", "Web"), "excel": ("excel", "Excel")}.get(str(origen), ("web", str(origen)))
    return f'<span class="ic">{ICONO[icono]}{nombre}</span>'


def cabecera_tabla(modo: str) -> str:
    if modo == "sup":
        cols = ["ID", "Asunto", "Estado", "Respuesta de la entidad", "Solicitada", "Plazo"]
    else:
        cols = ["ID", "Asunto", "Estado", "Prioridad", "Supervisor", "Cartera", "Canal", "Plazo"]
    return f'<div class="tr cab {modo}">' + "".join(f"<div>{c}</div>" for c in cols) + "</div>"


def _fecha_corta(s) -> str:
    try:
        d = date.fromisoformat(str(s)[:10])
        return f"{d.day:02d}/{d.month:02d}/{d.year}"
    except ValueError:
        return "—"


def fila_html(t, dias, modo: str = "bo") -> str:
    """Una fila de la tabla. En el modo 'sup' (supervisor) muestra la respuesta en vez del supervisor y la cartera."""
    id_ = f'<div class="id">#{esc(numero(t["codigo"]))}</div>'
    asunto = f'<div class="asu">{esc(t["tipo_consulta"])}<small>{mascara(t["cuenta"])}</small></div>'
    if modo == "sup":
        if t["estado"] == "Respondida":
            c = {"PROCEDENTE": pill("Procedente", "p-verde"), "IMPROCEDENTE": pill("Improcedente", "p-rojo")}.get(t["conclusion"], "")
            texto = esc(t["respuesta"]) if t["respuesta"] else "Sin descripción registrada"
            resp = f'<div title="{texto}">{c}<span style="margin-left:6px;color:#3a3a44">{texto}</span></div>'
        elif t["estado"] == "Enviada a verificar":
            resp = '<div style="color:#80808c">Enviada a la entidad. Esperando respuesta</div>'
        else:
            resp = '<div style="color:#80808c">Recibida, aún sin enviar</div>'
        return (f'<div class="tr sup">{id_}{asunto}<div>{pill_estado(t["estado"])}</div>{resp}'
                f'<div>{_fecha_corta(t["fecha_solicitud"])}</div><div>{_celda_plazo(dias, t["estado"])}</div></div>')
    if t["estado"] == "Respondida":
        pr = f'<span class="pr" style="color:#80808c">{ICONO["guion"]}Sin prioridad</span>'
    else:
        txt, ico, col = prioridad(dias)
        pr = f'<span class="pr" style="color:{col}">{ICONO[ico]}{txt}</span>'
    sup = f'<span class="av" style="background:{color_avatar(t["supervisor"])}">{esc(iniciales(t["supervisor"]))}</span>{esc(str(t["supervisor"]).title())}'
    return (f'<div class="tr bo">{id_}{asunto}<div>{pill_estado(t["estado"])}</div><div>{pr}</div><div>{sup}</div>'
            f'<div class="ic">{ICONO["tag"]}{esc(t["cartera"])}</div><div>{_canal(t["origen"])}</div><div>{_celda_plazo(dias, t["estado"])}</div></div>')
