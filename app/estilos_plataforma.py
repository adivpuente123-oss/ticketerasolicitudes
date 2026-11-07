"""Estilo de la plataforma de solicitudes: tabla limpia con tarjetas de resumen (inspirado en una ticketera moderna)."""
import html
import zlib
from datetime import date

import pandas as pd

AMARILLO, ROJO, NARANJA, VERDE, AZUL, GRIS = "#ffd21f", "#d64545", "#e8803a", "#1f9d55", "#2f6fd1", "#8a8a94"
COLORES_AVATAR = ["#5b7fc7", "#c9774f", "#7b5ea7", "#3a9bb0", "#2f8f5b", "#b5527a", "#8a7a3a", "#4b6cb7"]

CSS = """<style>
.stApp{background:#fff;color:#1b1b1f;font-size:14px}
[data-testid="stHeader"]{background:transparent}
.block-container{padding-top:1.1rem;padding-bottom:3rem;max-width:1500px;padding-left:2.2rem;padding-right:2.2rem}
[data-testid="stMarkdownContainer"] p,[data-testid="stCaptionContainer"]{line-height:1.6}
/* campos y botones con esquinas redondeadas y borde fino */
[data-baseweb="input"],[data-baseweb="select"]>div,[data-baseweb="textarea"]{border-radius:10px !important;border-color:#e4e4e8 !important;background:#fff !important}
.stButton button,.stDownloadButton button,.stFormSubmitButton button{border-radius:10px;border:1px solid #e4e4e8;background:#fff;color:#1b1b1f;font-weight:500}
.stButton button:hover,.stDownloadButton button:hover{border-color:#bdbdc6;color:#1b1b1f}
button[kind="primary"],button[kind="primaryFormSubmit"]{background:#ffd21f !important;border-color:#ffd21f !important;color:#1b1b1f !important;font-weight:600}
button[kind="primary"]:hover,button[kind="primaryFormSubmit"]:hover{background:#f5c400 !important;border-color:#f5c400 !important}
/* barra lateral angosta, blanca, solo íconos */
[data-testid="stSidebar"]{width:64px !important;min-width:64px !important;max-width:64px !important;background:#fff !important;border-right:1px solid #ececef}
[data-testid="stSidebar"]>div:first-child{width:64px !important}
[data-testid="stSidebarHeader"],[data-testid="stSidebarCollapseButton"],[data-testid="stSidebarCollapsedControl"],[data-testid="collapsedControl"]{display:none !important}
[data-testid="stSidebarContent"]{padding:0 !important;overflow-x:hidden}
[data-testid="stSidebarUserContent"]{padding:0 !important;min-height:100vh}
[data-testid="stSidebarUserContent"]>[data-testid="stVerticalBlock"]{gap:0 !important;min-height:100vh;align-items:center}
[data-testid="stSidebar"] [data-testid="stVerticalBlock"]{gap:0 !important}
.logo-y{width:36px;height:36px;border-radius:10px;background:#ffd21f;display:grid;place-items:center;margin:16px auto 18px}
.nv{height:42px;width:42px;margin:7px auto;border-radius:10px;display:flex;align-items:center;justify-content:center;color:#80808c}
.nv svg{width:20px;height:20px}.nv.on{background:#f0f0f2;color:#1b1b1f}
[class*="st-key-nav_"]{position:relative;width:42px;margin:0 auto}
[class*="st-key-navb_"]{position:static !important}
[class*="st-key-nav_"] [data-testid="stButton"]{position:absolute;inset:0;margin:0}
[class*="st-key-nav_"] button{width:100%;height:100%;min-height:0;opacity:0;cursor:pointer;padding:0}
.st-key-nav_salir{margin-top:auto !important;margin-bottom:18px !important}
[class*="st-key-btn_"],[class*="st-key-exp_"]{display:flex !important;flex-direction:row !important;justify-content:flex-end !important;width:100% !important}
[data-testid="stForm"]{border:0 !important;padding:0 !important}
[class*="st-key-btn_"] [data-testid="stButton"]{width:210px !important;flex:0 0 210px}
[class*="st-key-btn_"] button{width:100% !important}
/* cabecera */
.mig{display:flex;align-items:center;gap:10px;color:#80808c;font-size:13.5px;margin:0 0 22px;padding-bottom:14px;border-bottom:1px solid #f0f0f2}
.mig b{color:#1b1b1f;font-weight:500}.mig .yo{margin-left:auto;display:flex;align-items:center;gap:10px;color:#1b1b1f}
.h1{font-size:30px;font-weight:700;letter-spacing:-.01em;margin:0 0 2px;line-height:1.2}.sub{color:#6e6e78;margin:0 0 20px}
/* tarjetas de resumen */
.kpis{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:16px;margin:6px 0 24px}
.kp{background:#f6f6f7;border:1px solid #ececef;border-radius:16px;padding:14px 14px 14px}
.kp .et{display:flex;align-items:center;gap:8px;color:#6e6e78;font-size:12px;font-weight:500;letter-spacing:.05em;margin:0 0 12px 4px;text-transform:uppercase}
.kp .et svg{width:15px;height:15px}
.kp .in{background:#fff;border:1px solid #ececef;border-radius:12px;padding:18px 20px}
.kp .n{font-size:32px;font-weight:600;line-height:1.1;margin:0 0 10px}.kp .d{font-size:12.5px;display:flex;align-items:center;gap:6px}
.d.mal{color:#d64545}.d.bien{color:#1f9d55}.d.neu{color:#6e6e78}
/* tabla */
.st-key-tabla [data-testid="stVerticalBlock"]{gap:0 !important}
.tr{display:grid;align-items:center;padding:0 14px;min-height:50px;font-size:13.5px;border-bottom:1px solid #f0f0f2;column-gap:12px}
.tr.bo{grid-template-columns:72px minmax(220px,2.8fr) 140px 130px 170px 90px 110px 110px}
.tr.sup{grid-template-columns:72px minmax(200px,1.6fr) 140px minmax(220px,2.4fr) 110px 110px}
.tr.cab{background:#f7f7f8;color:#80808c;font-size:12.5px;min-height:40px;border-top:1px solid #ececef;border-radius:10px 10px 0 0}
.tr>div{overflow:hidden;text-overflow:ellipsis;white-space:nowrap;display:flex;align-items:center;gap:8px}
.tr .id{color:#80808c}.tr .asu{font-weight:500}.tr .asu small{color:#9a9aa5;font-weight:400;margin-left:8px}
[class*="st-key-fila_"]{position:relative;cursor:pointer}[class*="st-key-fila_"]:hover{background:#fafafb}
[class*="st-key-abrir_"]{position:static !important}
[class*="st-key-fila_"] [data-testid="stButton"]{position:absolute;inset:0;margin:0}
[class*="st-key-fila_"] button{width:100%;height:100%;min-height:0;opacity:0;cursor:pointer;padding:0}
.pie-tabla{display:flex;align-items:center;justify-content:space-between;color:#6e6e78;font-size:13px;padding:14px 4px 0}
.pill{display:inline-flex;align-items:center;gap:7px;padding:3px 12px;border-radius:12px;font-size:12.5px;font-weight:500;white-space:nowrap}
.pill i{width:7px;height:7px;border-radius:50%;display:inline-block}
.p-azul{background:#e4efff;color:#1f5fc9}.p-amar{background:#fff1c2;color:#8a6a00}.p-gris{background:#eeeef1;color:#5a5a66}
.p-rojo{background:#fde6e6;color:#b83232}.p-verde{background:#e0f5e8;color:#1b7a45}
.pr{display:flex;align-items:center;gap:6px}.pr svg{width:14px;height:14px}
.av{width:26px;height:26px;border-radius:50%;display:inline-flex;align-items:center;justify-content:center;color:#fff;font-size:11px;font-weight:600;flex:none}
.ic{display:inline-flex;align-items:center;gap:7px;color:#3a3a44}.ic svg{width:15px;height:15px;color:#80808c;flex:none}
.vacio{color:#6e6e78;text-align:center;padding:36px 0}
/* tarjetas de detalle y formularios */
[class*="st-key-card"]{background:#fff;border:1px solid #ececef;border-radius:16px;padding:24px 26px}
[data-testid="stMetric"]{background:#f6f6f7;border:1px solid #ececef;border-radius:14px;padding:14px 18px}
.chip{display:inline-block;padding:3px 12px;border-radius:12px;font-size:12.5px;font-weight:500;white-space:nowrap}
.chip.rec{background:#e4efff;color:#1f5fc9}.chip.env{background:#fff1c2;color:#8a6a00}.chip.res{background:#eeeef1;color:#5a5a66}
.chip.pro{background:#e0f5e8;color:#1b7a45}.chip.imp{background:#fde6e6;color:#b83232}
.sk{background:#fff;border:1px solid #ececef;border-radius:16px;padding:24px 26px}
.sk .tt{font-size:17px;font-weight:600;margin:12px 0 4px}.sk .sm{color:#6e6e78;margin:0}.sk .rp{margin:16px 0 0;font-size:14.5px;line-height:1.7}
.sk .rp small{display:block;color:#80808c;font-size:12.5px;margin-bottom:4px}
.hist{border-left:2px solid #ececef;padding-left:14px;margin:6px 0 10px}.hist p{margin:0 0 10px;font-size:14px;line-height:1.55}.hist small{color:#80808c}
@media(max-width:1100px){.kpis{grid-template-columns:repeat(2,minmax(0,1fr))}}
</style>"""

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
    return ('<div class="logo-y"><svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="#1b1b1f" stroke-width="2.2" stroke-linecap="round" aria-hidden="true">'
            '<path d="M8 8l8 8M16 8l-8 8"/></svg></div>')


def cabecera(pagina: str, nombre: str, rol: str) -> str:
    return (f'<div class="mig"><span>Plataforma</span><span>/</span><b>{esc(pagina)}</b>'
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
            "Respondida": pill("Respondida", "p-gris", False)}.get(estado, pill(str(estado), "p-gris", False))


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
