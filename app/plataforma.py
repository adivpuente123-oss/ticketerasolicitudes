"""Plataforma de solicitudes: los supervisores crean tickets y el back office los gestiona."""
import re
import os
import hmac
import sqlite3
import sys
import time
import uuid
from datetime import date, datetime
from pathlib import Path

import pandas as pd
import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
import db
from correo import crear_ticket_desde_correo
from config import CARTERAS, CONCLUSIONES, CORRESPONDE, ESTADOS_TICKET, TIPOS_CONSULTA
from estilos_plataforma import (CSS, cabecera, cabecera_tabla, esc, fila_html, kpi, logo_y, mascara, nav_item, numero, acceso_visual, fondo_acceso, ticket_resumen)

st.set_page_config(page_title="Plataforma de solicitudes", initial_sidebar_state="expanded", layout="wide")
st.markdown("<style>" + (Path(__file__).parent / "portal.css").read_text(encoding="utf-8") + "</style>", unsafe_allow_html=True)
db.iniciar()

MES_CORTO = ["ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "set", "oct", "nov", "dic"]
CLASE_ESTADO = {"Recibida": "rec", "Enviada a verificar": "env", "Respondida": "res"}
BACK = ["Inicio", "Gestionar", "Nueva solicitud", "Correo", "Prueba de correo", "Usuarios"]
SUP = ["Mis solicitudes", "Nueva solicitud"]
NAV_INFO = {"Inicio": ("solicitudes", "Solicitudes"), "Gestionar": ("gestionar", "Gestionar ticket"),
            "Nueva solicitud": ("nueva", "Nueva solicitud"), "Prueba de correo": ("correo", "Prueba de correo"),
            "Usuarios": ("usuarios", "Usuarios"), "Mis solicitudes": ("solicitudes", "Mis solicitudes")}
TAM_PAGINA = 20
NAV_INFO["Correo"] = ("correo", "Correo de atención")
FILTRO_ESTADO = ["Todos los estados", "Recibida", "En verificación", "Respondida", "Atrasadas (más de 30 días)"]


# ---------- utilidades ----------
def fecha_txt(s) -> str:
    try:
        d = date.fromisoformat(str(s)[:10])
        return f"{d.day:02d} {MES_CORTO[d.month - 1]} {d.year}"
    except ValueError:
        return "—"


def a_fecha(s):
    try:
        return date.fromisoformat(str(s)[:10]) if s else None
    except ValueError:
        return None


def chip_estado(estado) -> str:
    return f'<span class="chip {CLASE_ESTADO.get(estado, "rec")}">{esc(estado)}</span>'


def chip_conclusion(c) -> str:
    if c == "PROCEDENTE":
        return '<span class="chip pro">Procedente (positiva)</span>'
    if c == "IMPROCEDENTE":
        return '<span class="chip imp">Improcedente (negativa)</span>'
    return ""


def dias_abierto(df):
    abiertas = df["estado"] != "Respondida"
    hoy = pd.Timestamp.today().normalize()
    return (hoy - pd.to_datetime(df["fecha_solicitud"], errors="coerce")).dt.days.where(abiertas)


def ir_a(destino, tid):
    st.session_state["_ir_a"] = (destino, tid)


def abrir_en_gestionar(tid):
    ir_a("Gestionar", tid)


def abrir_detalle(tid):
    st.session_state["ver_ticket"] = tid


def cerrar_detalle():
    st.session_state.pop("ver_ticket", None)


def cambiar_pagina(p):
    st.session_state["pagina_pf"] = p
    st.session_state.pop("ver_ticket", None)


def cambiar_pag(delta):
    st.session_state["pag_tabla"] = max(0, st.session_state.get("pag_tabla", 0) + delta)


def reiniciar_pag():
    st.session_state["pag_tabla"] = 0


def cerrar_sesion():
    if os.getenv("PORTAL_AUTH_HTTP") == "1":
        db.revocar_sesion(st.context.cookies.get("portal_session"))
    for k in ("usuario", "pagina_pf", "ticket_sel", "_ir_a", "ver_ticket", "pag_tabla"):
        st.session_state.pop(k, None)


def titulo_pagina(texto, sub=""):
    st.markdown(f'<h1 class="h1">{esc(texto)}</h1>' + (f'<p class="sub">{esc(sub)}</p>' if sub else ""), unsafe_allow_html=True)


def metricas(items):
    for c, (etiqueta, valor) in zip(st.columns(len(items)), items):
        c.metric(etiqueta, f"{int(valor):,}")


# ---------- acceso ----------
def pantalla_acceso():
    st.markdown(fondo_acceso(), unsafe_allow_html=True)
    visual, centro = st.columns([1.15, 1], gap="large", vertical_alignment="center")
    with visual:
        st.markdown(acceso_visual(), unsafe_allow_html=True)
    with centro, st.container(key="access_form"):
        st.markdown('<div class="access-kicker">Acceso al portal</div>', unsafe_allow_html=True)
        if not db.hay_backoffice():
            st.markdown('<h2 class="access-heading">Configura tu espacio.</h2>', unsafe_allow_html=True)
            st.caption("Será el back office que gestiona todos los tickets.")
            with st.form("setup"):
                token = st.text_input("Código de instalación del servidor", type="password") if os.getenv("SETUP_TOKEN") else ""
                nombre = st.text_input("Nombre")
                correo = st.text_input("Correo")
                clave = st.text_input("Contraseña (mínimo 8 caracteres)", type="password")
                clave2 = st.text_input("Repite la contraseña", type="password")
                if st.form_submit_button("Crear administrador", type="primary"):
                    if os.getenv("SETUP_TOKEN") and not hmac.compare_digest(token, os.environ["SETUP_TOKEN"]):
                        st.error("Código de instalación incorrecto.")
                    elif not nombre.strip() or not re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", correo.strip()):
                        st.error("Escribe tu nombre y un correo válido.")
                    elif len(clave) < 8 or clave != clave2:
                        st.error("La contraseña debe tener 8 caracteres o más y coincidir en los dos campos.")
                    else:
                        try:
                            existente = db.usuario_por_correo(correo)
                            if existente:
                                db.actualizar_usuario(existente["id"], nombre, correo, "backoffice", 1, clave)
                            else:
                                db.crear_usuario(nombre, correo, "backoffice", clave)
                            st.rerun()
                        except sqlite3.IntegrityError:
                            st.error("Ese nombre ya existe como usuario. Usa otro nombre.")
            return
        st.markdown('<h2 class="access-heading">Bienvenido de nuevo.</h2><p class="access-copy">Ingresa con tu correo corporativo para consultar y gestionar tus solicitudes.</p>', unsafe_allow_html=True)
        if os.getenv("PORTAL_AUTH_HTTP") == "1":
            st.link_button("Iniciar sesión", "/_portal/login", type="primary", use_container_width=True)
            return
        with st.form("login"):
            correo = st.text_input("Correo")
            clave = st.text_input("Contraseña", type="password")
            if st.form_submit_button("Entrar", type="primary", use_container_width=True):
                u = db.usuario_por_correo(correo)
                if u and u["activo"] and db.verificar_clave(clave, u["clave_hash"]):
                    st.session_state["usuario"] = {k: u[k] for k in ("id", "nombre", "correo", "rol")}
                    st.rerun()
                time.sleep(1)  # frena los intentos repetidos
                st.error("Correo o contraseña incorrectos, o el usuario está inactivo.")
        st.markdown('<div class="access-note">¿Necesitas acceso? Contacta al administrador de tu equipo.<br>Tu cuenta y tus solicitudes se conservan en el portal.</div>', unsafe_allow_html=True)


# ---------- listado de solicitudes: tarjetas de resumen, filtros y tabla ----------
def variacion_semanal(df, base, sube_es_malo):
    """Texto y color de «vs semana pasada»: tickets creados en los últimos 7 días contra los 7 anteriores."""
    hoy = pd.Timestamp.today().normalize()
    f = pd.to_datetime(df["fecha_solicitud"], errors="coerce")
    ult = int((base & (f > hoy - pd.Timedelta(days=7)) & (f <= hoy)).sum())
    ant = int((base & (f > hoy - pd.Timedelta(days=14)) & (f <= hoy - pd.Timedelta(days=7))).sum())
    dif = ult - ant
    if not ult and not ant:
        return "Sin movimiento esta semana", "neu"
    if dif == 0:
        return f"→ Igual que la semana pasada ({ult})", "neu"
    pct = f" ({abs(dif) / ant * 100:.1f}%)" if ant else ""
    return f"{'↗' if dif > 0 else '↘'} {abs(dif)}{pct} vs semana pasada", ("mal" if (dif > 0) == sube_es_malo else "bien")


def kpis_html(df, titulos) -> str:
    todos = pd.Series(True, index=df.index)
    datos = [(titulos[0], "total", todos, True), (titulos[1], "abiertas", df["estado"] == "Recibida", True),
             (titulos[2], "pendientes", df["estado"] == "Enviada a verificar", True), (titulos[3], "respondidas", df["estado"] == "Respondida", False)]
    return '<div class="kpis">' + "".join(kpi(t, ic, int(m.sum()), *variacion_semanal(df, m, malo)) for t, ic, m, malo in datos) + "</div>"


def filtrar(df, buscar, estado, cartera, orden):
    v = df
    if estado == "Recibida":
        v = v[v["estado"] == "Recibida"]
    elif estado == "En verificación":
        v = v[v["estado"] == "Enviada a verificar"]
    elif estado == "Respondida":
        v = v[v["estado"] == "Respondida"]
    elif estado.startswith("Atrasadas"):
        v = v[v["dias"] > 30]
    if cartera != "Todas":
        v = v[v["cartera"] == cartera]
    if buscar and buscar.strip():
        b = buscar.strip().lower()
        v = v[v[["codigo", "tipo_consulta", "cuenta", "documento", "supervisor", "cartera"]].fillna("").apply(
            lambda s: s.astype(str).str.lower().str.contains(b, regex=False)).any(axis=1)]
    asc = orden == "Más antiguas primero"
    # las abiertas van primero (son las que hay que atender) y las respondidas al final
    return v.assign(_r=v["estado"] == "Respondida").sort_values(["_r", "fecha_solicitud", "id"], ascending=[True, asc, asc]).drop(columns="_r")


def exportar(v) -> bytes:
    out = pd.DataFrame({"Código": v["codigo"], "Origen": v["origen"], "Supervisor": v["supervisor"], "Cartera": v["cartera"],
                        "Tipo de consulta": v["tipo_consulta"], "Cuenta": v["cuenta"].map(mascara), "Estado": v["estado"],
                        "Solicitada": v["fecha_solicitud"], "Enviada": v["fecha_envio"], "Respondida": v["fecha_respuesta"],
                        "Conclusión": v["conclusion"], "Días abierta": v["dias"]})
    return out.to_csv(index=False).encode("utf-8-sig")


def confirmar_borrado_solicitud(tid):
    u = st.session_state.get("usuario")
    if not u or not acceso_vigente(u):
        return
    t = db.ticket(tid)
    if t is None:
        st.info("La solicitud ya no existe.")
        return
    st.write(f"¿Borrar {t['codigo']} y todos sus mensajes, historial y avisos de correo de la plataforma?")
    si, no = st.columns(2)
    if si.button("Sí, borrar solicitud", type="primary"):
        try:
            db.eliminar_solicitud(tid, u["id"])
            st.session_state.pop("ticket_sel", None)
            st.session_state.pop("borrar_ticket", None)
            st.rerun(scope="app")
        except (ValueError, PermissionError) as exc:
            st.error(str(exc))
    if no.button("Cancelar"):
        st.session_state.pop("borrar_ticket", None)
        st.rerun(scope="app")


def render_tabla(v, modo, al_abrir):
    total = len(v)
    paginas = max(1, -(-total // TAM_PAGINA))
    pag = min(st.session_state.get("pag_tabla", 0), paginas - 1)
    ini, fin = pag * TAM_PAGINA, min((pag + 1) * TAM_PAGINA, total)
    if v.empty:
        st.markdown('<div class="vacio">No hay solicitudes con estos filtros.<br>Prueba con otro estado o una búsqueda diferente.</div>', unsafe_allow_html=True)
    with st.container(key="solicitudes_grid"):
        with st.container(key="solicitudes_cabecera"):
            columnas = st.columns([1.2, 2.6, 1.6, .45, .45], vertical_alignment="center")
            for col, texto in zip(columnas, ["Ticket", "Supervisor" if modo == "bo" else "Solicitud", "Estado", "", ""]):
                col.caption(texto)
        for _, t in v.iloc[ini:fin].iterrows():
            with st.container(key=f"ticket_row_{int(t['id'])}"):
                codigo, asesor, estado_col, abrir_col, borrar_col = st.columns([1.2, 2.6, 1.6, .45, .45], vertical_alignment="center")
                codigo.markdown(f'<span class="table-code">{esc(t["codigo"])}</span>', unsafe_allow_html=True)
                nombre = str(t["supervisor"] or "Sin usuario") if modo == "bo" else (t["tipo_consulta"] or "Solicitud")
                asesor.markdown(f'<div class="table-person">{esc(nombre.title() if modo == "bo" else nombre)}<small>{esc(t["cartera"])} · {esc(t["tipo_consulta"] or "Por completar") if modo == "bo" else esc(fecha_txt(t["fecha_solicitud"]))}</small></div>', unsafe_allow_html=True)
                estado = t["estado"]
                clase, etiqueta = {"Recibida": ("pending", "Pendiente"), "Enviada a verificar": ("review", "En verificación"), "Respondida": ("approved", "Respondida")}[estado]
                if estado == "Respondida" and t["conclusion"]:
                    clase, etiqueta = ("approved", "Aprobada") if t["conclusion"] == "PROCEDENTE" else ("rejected", "Rechazada")
                estado_col.markdown(f'<span class="table-status {clase}">{etiqueta}</span>', unsafe_allow_html=True)
                if abrir_col.button("Abrir", icon=":material/visibility:", key=f"abrir_{int(t['id'])}", help="Ver solicitud"):
                    al_abrir(int(t["id"]))
                    st.rerun(scope="app")
                if modo == "bo" and borrar_col.button("Borrar", icon=":material/delete_outline:", key=f"borrar_{int(t['id'])}", help="Borrar solicitud"):
                    st.session_state["borrar_ticket"] = int(t["id"])
                if modo == "bo" and st.session_state.get("borrar_ticket") == int(t["id"]):
                    confirmar_borrado_solicitud(int(t["id"]))
    c1, c2, c3 = st.columns([4, 1.3, 1.3], vertical_alignment="center")
    c1.markdown(f'<div class="pie-tabla">{ini + 1 if total else 0}–{fin} de {total:,} solicitudes · página {pag + 1} de {paginas}</div>', unsafe_allow_html=True)
    c2.button("Anterior", key="pag_ant", on_click=cambiar_pag, args=(-1,), disabled=pag == 0, use_container_width=True)
    c3.button("Siguiente", key="pag_sig", on_click=cambiar_pag, args=(1,), disabled=pag >= paginas - 1, use_container_width=True)


def barra_filtros(prefijo):
    f1 = st.container()
    f2, f3, f4 = st.columns([1.1, 1, 1.2])
    buscar = f1.text_input("Buscar", placeholder="Código, cuenta o supervisor", label_visibility="visible",
                           key=f"{prefijo}_q", on_change=reiniciar_pag)
    estado = f2.selectbox("Estado", FILTRO_ESTADO, label_visibility="visible", key=f"{prefijo}_estado", on_change=reiniciar_pag)
    cartera = f3.selectbox("Cartera", ["Todas"] + CARTERAS, label_visibility="visible", key=f"{prefijo}_cartera",
                           format_func=lambda x: "Todas las carteras" if x == "Todas" else x, on_change=reiniciar_pag)
    orden = f4.selectbox("Orden", ["Más antiguas primero", "Más recientes primero"], label_visibility="visible",
                         key=f"{prefijo}_orden", on_change=reiniciar_pag)
    return buscar, estado, cartera, orden


@st.fragment(run_every="5s")
def pagina_inicio(u):
    if not acceso_vigente(u):
        return
    titulo_pagina("Panel de solicitudes", "Administración y seguimiento de solicitudes")
    df = db.tickets_df()
    df["dias"] = dias_abierto(df)
    pendientes = int((df["estado"] != "Respondida").sum())
    aprobadas = int(((df["estado"] == "Respondida") & (df["conclusion"] == "PROCEDENTE")).sum())
    rechazadas = int(((df["estado"] == "Respondida") & (df["conclusion"] == "IMPROCEDENTE")).sum())
    st.markdown('<div class="summary-grid">' + ''.join(
        f'<div class="summary-card {clase}"><span class="summary-icon">{icono}</span><strong>{valor}</strong><small>{etiqueta}</small></div>'
        for clase, icono, valor, etiqueta in [("pending", "◷", pendientes, "Pendientes"), ("approved", "✓", aprobadas, "Aprobadas"), ("rejected", "×", rechazadas, "Rechazadas")]) + '</div>', unsafe_allow_html=True)
    with st.container(key="listado_panel"):
        cabecera_panel = st.container()
        buscar_col, estado_col = st.columns([4, 1])
        buscar = buscar_col.text_input("Buscar solicitudes", placeholder="Buscar solicitudes", label_visibility="collapsed", key="bo_q", on_change=reiniciar_pag)
        estado = estado_col.selectbox("Estado", FILTRO_ESTADO, label_visibility="collapsed", key="bo_estado", on_change=reiniciar_pag,
                                      format_func=lambda x: "Todas" if x == "Todos los estados" else x)
        with st.expander("Más filtros"):
            c1, c2 = st.columns(2)
            cartera = c1.selectbox("Cartera", ["Todas"] + CARTERAS, key="bo_cartera", on_change=reiniciar_pag)
            orden = c2.selectbox("Orden", ["Más antiguas primero", "Más recientes primero"], key="bo_orden", on_change=reiniciar_pag)
        v = filtrar(df, buscar, estado, cartera, orden)
        with cabecera_panel:
            titulo, exportar_col, nueva = st.columns([4, 1.4, 1.4], vertical_alignment="center")
            titulo.markdown('<h2 class="panel-heading">Gestión de solicitudes</h2>', unsafe_allow_html=True)
            exportar_col.download_button("Exportar reporte", exportar(v), "solicitudes.csv", "text/csv", key="exp_bo", icon=":material/file_download:")
            nueva.button("Nueva solicitud", key="btn_nueva", on_click=cambiar_pagina, args=("Nueva solicitud",), icon=":material/add:")
        render_tabla(v, "bo", abrir_en_gestionar)
    st.caption("Actualización automática cada 5 segundos · Las aprobaciones y rechazos corresponden a la conclusión de las solicitudes respondidas.")



# ---------- páginas del supervisor ----------
def detalle_supervisor(u, tid):
    t = db.ticket(tid)
    st.button("← Volver a mis solicitudes", on_click=cerrar_detalle, key="volver")
    if t is None or t["supervisor_id"] != u["id"]:        # un supervisor solo puede ver sus propias solicitudes
        st.error("No encontré esa solicitud.")
        return
    if t["estado"] == "Respondida":
        cuando = fecha_txt(t["fecha_respuesta"]) if t["fecha_respuesta"] else "fecha no registrada"
        pie = (f'<p class="rp"><small>Respuesta de la entidad, {cuando}</small>{chip_conclusion(t["conclusion"])}<br>'
               f'{esc(t["respuesta"]) or "Sin descripción registrada."}</p>')
    elif t["estado"] == "Enviada a verificar":
        pie = f'<p class="rp"><small>En verificación</small>Enviada a la entidad el {fecha_txt(t["fecha_envio"])}. Esperando respuesta.</p>'
    else:
        pie = '<p class="rp"><small>Recibida</small>Ya la tenemos. Todavía no se envía a la entidad.</p>'
    st.markdown(f'<div class="sk"><div style="display:flex;gap:10px;align-items:center;flex-wrap:wrap"><b style="font-size:22px">{esc(t["codigo"])}</b>'
                f'{chip_estado(t["estado"])}</div><p class="tt">{esc(t["tipo_consulta"])}</p>'
                f'<p class="sm">{esc(t["cartera"])} · cuenta {mascara(t["cuenta"])} · solicitada el {fecha_txt(t["fecha_solicitud"])}</p>'
                + (f'<p class="rp"><small>Tu consulta</small>{esc(t["descripcion"])}</p>' if t["descripcion"] else "") + pie + "</div>", unsafe_allow_html=True)
    conversacion(u, tid)


@st.fragment(run_every="5s")
def pagina_mis_solicitudes(u):
    if not acceso_vigente(u):
        return
    st.caption("Estado actualizado automáticamente cada 5 segundos")
    if st.session_state.get("ver_ticket"):
        detalle_supervisor(u, st.session_state["ver_ticket"])
        return
    df = db.tickets_df(u["id"])          # siempre filtrado por el supervisor que inició sesión
    if df.empty:
        titulo_pagina("Mis solicitudes")
        st.info("Todavía no tienes solicitudes. Crea la primera con el botón «Nueva solicitud».")
        st.button("Nueva solicitud", type="primary", key="btn_nueva", on_click=cambiar_pagina, args=("Nueva solicitud",))
        return
    df["dias"] = dias_abierto(df)
    a, c = st.columns([8, 2.3], vertical_alignment="center")
    a.markdown('<h1 class="h1">Mis solicitudes</h1>', unsafe_allow_html=True)
    c.button("Nueva solicitud", type="primary", key="btn_nueva", on_click=cambiar_pagina, args=("Nueva solicitud",))
    st.markdown(kpis_html(df, ("Mis solicitudes", "Recibidas", "En verificación", "Respondidas")), unsafe_allow_html=True)
    v = filtrar(df, *barra_filtros("sup"))
    render_tabla(v, "sup", abrir_detalle)
    st.caption("Abre una solicitud para consultar su detalle y conversar con el equipo de atención.")


def pagina_nueva(u):
    titulo_pagina("Nueva solicitud", "El back office la verá de inmediato y te avisará aquí cuando la entidad responda.")
    supervisor_id = u["id"]
    if u["rol"] == "backoffice":
        sups = db.usuarios_df()
        sups = sups[(sups["rol"] == "supervisor") & (sups["activo"] == 1)]
        nombre = st.selectbox("Supervisor que la solicita", sups["nombre"].tolist())
        supervisor_id = int(sups.loc[sups["nombre"] == nombre, "id"].iloc[0]) if len(sups) else None
    with st.form("nueva", clear_on_submit=True):
        c1, c2 = st.columns(2)
        cartera = c1.selectbox("Cartera", CARTERAS)
        tipo = c2.selectbox("Tipo de consulta", TIPOS_CONSULTA)
        documento = c1.text_input("Documento (DNI)")
        cuenta = c2.text_input("Número de cuenta")
        descripcion = st.text_area("Descripción de la consulta", height=120)
        forzar = st.checkbox("Crear aunque ya exista una solicitud abierta con el mismo documento y cuenta")
        if st.form_submit_button("Crear solicitud", type="primary"):
            doc, cta = documento.strip(), cuenta.strip()
            repetidas = db.abiertas_por_documento(doc, cta) if doc else []
            if supervisor_id is None:
                st.error("No hay supervisores activos. Créalos en «Usuarios».")
            elif not doc or not cta:
                st.error("El documento y la cuenta son obligatorios.")
            elif not re.fullmatch(r"[0-9A-Za-z]{6,15}", doc):
                st.error("El documento solo debe tener letras y números (entre 6 y 15 caracteres).")
            elif repetidas and not forzar:
                st.warning(f"Ya hay solicitudes abiertas con ese documento y cuenta: {', '.join(repetidas)}. "
                           "Si es otra consulta, marca la casilla y vuelve a crear.")
            else:
                _, codigo = db.crear_ticket(supervisor_id, cartera, tipo, doc, cta, descripcion.strip(), origen="web", usuario_id=u["id"])
                st.success(f"Solicitud {codigo} creada. Puedes seguirla en «Mis solicitudes»." if u["rol"] == "supervisor"
                           else f"Solicitud {codigo} creada. Ábrela desde «Inicio» o «Gestionar».")


# ---------- gestión de un ticket (back office) ----------
def pagina_gestionar(u):
    df = db.tickets_df()
    titulo_pagina("Gestionar ticket", "Revisa la solicitud, envíala a verificar y registra la respuesta de la entidad.")
    if df.empty:
        st.info("No hay tickets para gestionar.")
        return
    ids = df["id"].tolist()
    if st.session_state.get("ticket_sel") not in ids:
        st.session_state["ticket_sel"] = ids[0]
    etiquetas = {r.id: f"{r.codigo} · {r.supervisor} · {r.cartera} · {r.estado}" for r in df.itertuples()}
    tid = st.selectbox("Ticket", ids, key="ticket_sel", format_func=lambda i: etiquetas[i])
    t = db.ticket(tid)

    izq, der = st.columns([1, 1.15], gap="large")
    with izq, st.container(key=f"card_det_{tid}"):
        st.markdown(f'<div style="display:flex;gap:10px;align-items:center;flex-wrap:wrap"><b style="font-size:22px">{esc(t["codigo"])}</b>'
                    f'{chip_estado(t["estado"])}{chip_conclusion(t["conclusion"])}</div>'
                    f'<div style="color:#6b7890;line-height:2;margin-top:12px">'
                    f'Supervisor: <b style="color:#26334a">{esc(t["supervisor"])}</b><br>Cartera: {esc(t["cartera"])} · {esc(t["tipo_consulta"])}<br>'
                    f'Documento: {esc(t["documento"])} · Cuenta: {esc(t["cuenta"])}<br>Origen: {esc(t["origen"])}<br>'
                    f'Solicitada: {fecha_txt(t["fecha_solicitud"])} · Enviada: {fecha_txt(t["fecha_envio"]) if t["fecha_envio"] else "—"}'
                    f' · Respondida: {fecha_txt(t["fecha_respuesta"]) if t["fecha_respuesta"] else "—"}</div>', unsafe_allow_html=True)
        if t["descripcion"]:
            st.markdown(f'<div style="margin-top:14px;border-top:1px solid #dde2ea;padding-top:12px"><small style="color:#6b7890">Consulta del supervisor</small><br>{esc(t["descripcion"])}</div>', unsafe_allow_html=True)
        h = db.historial_df(tid)
        st.markdown("**Historial**")
        st.markdown('<div class="hist">' + "".join(
            f'<p><b>{esc(r.evento)}</b> <small>{esc(r.fecha)} · {esc(r.usuario)}</small>'
            + (f"<br>{esc(r.detalle)}" if r.detalle else "") + "</p>" for r in h.itertuples()) + "</div>", unsafe_allow_html=True)

    with der, st.container(key=f"card_form_{tid}"):
        st.markdown("**Gestionar el ticket**")
        with st.form(f"form_{tid}"):
            c1, c2 = st.columns(2)
            estado = c1.selectbox("Estado", ESTADOS_TICKET, index=ESTADOS_TICKET.index(t["estado"]))
            f_envio = c2.date_input("Fecha de envío a la entidad", value=a_fecha(t["fecha_envio"]))
            opciones_c = ["(sin conclusión)"] + CONCLUSIONES
            conclusion = c1.selectbox("Conclusión de la entidad", opciones_c,
                                      index=opciones_c.index(t["conclusion"]) if t["conclusion"] in CONCLUSIONES else 0)
            opciones_k = ["(sin definir)"] + CORRESPONDE
            corresponde = c2.selectbox("Estado corresponde", opciones_k,
                                       index=opciones_k.index(t["estado_corresponde"]) if t["estado_corresponde"] in CORRESPONDE else 0)
            respuesta = st.text_area("Descripción de la respuesta (la verá el supervisor)", value=t["respuesta"] or "", height=130)
            sustento = st.text_input("Sustento", value=t["sustento"] or "")
            b1, b2, b3 = st.columns(3)
            enviar = b1.form_submit_button("Enviar a verificar")
            responder = b2.form_submit_button("Registrar respuesta", type="primary")
            guardar = b3.form_submit_button("Guardar cambios")
            if enviar or responder or guardar:
                concl = None if conclusion == opciones_c[0] else conclusion
                corr = None if corresponde == opciones_k[0] else corresponde
                if responder and (not concl or not respuesta.strip()):
                    st.error("Para registrar la respuesta indica la conclusión (procedente o improcedente) y escribe la descripción.")
                else:
                    hoy = db.hoy_iso()
                    comunes = dict(estado_corresponde=corr, sustento=sustento.strip() or None)
                    if enviar:
                        cambios = dict(estado="Enviada a verificar", fecha_envio=f_envio.isoformat() if f_envio else hoy, **comunes)
                        evento, detalle = "Enviada a verificar", ""
                    elif responder:
                        cambios = dict(estado="Respondida", fecha_envio=f_envio.isoformat() if f_envio else (t["fecha_envio"] or hoy),
                                       fecha_respuesta=t["fecha_respuesta"] or hoy, conclusion=concl, respuesta=respuesta.strip(), **comunes)
                        evento, detalle = "Respondida", concl
                    else:
                        cambios = dict(estado=estado, fecha_envio=f_envio.isoformat() if f_envio else None, conclusion=concl,
                                       respuesta=respuesta.strip() or None, **comunes)
                        evento, detalle = "Edición", f"Estado: {estado}"
                    db.actualizar_ticket(tid, u["id"], cambios, evento, detalle)
                    st.toast("Ticket actualizado · aviso de correo en cola")
                    st.rerun()

    conversacion(u, tid)


def acceso_vigente(u):
    actual = db.usuario_por_sesion(st.context.cookies.get("portal_session")) if os.getenv("PORTAL_AUTH_HTTP") == "1" else db.usuario_por_id(u["id"])
    if actual and actual["id"] != u["id"]:
        actual = None
    if not actual or not actual["activo"] or actual["rol"] != u["rol"]:
        cerrar_sesion()
        st.rerun(scope="app")
        return False
    return True


def conversacion(u, tid):
    st.subheader("Conversación del ticket")
    for m in db.mensajes(tid):
        with st.container(border=True):
            st.caption(f"{m['nombre']} · {m['creado_en']} · {'Correo' if m['id_correo'] else 'Web'}")
            st.text(m["cuerpo"])
    with st.form(f"mensaje_{tid}", clear_on_submit=True):
        texto = st.text_area("Agregar mensaje", max_chars=20000)
        if st.form_submit_button("Enviar mensaje"):
            try:
                db.agregar_mensaje(tid, u["id"], texto)
                st.rerun(scope="app")
            except (ValueError, PermissionError) as exc:
                st.error(str(exc))


@st.fragment(run_every="10s")
def pagina_buzon(u):
    if not acceso_vigente(u):
        return
    titulo_pagina("Correo de atención", "adiv.puente@goexpertis.com · Microsoft 365 / Outlook")
    with db.conexion() as con:
        servicio = con.execute("SELECT * FROM servicio WHERE nombre='outlook'").fetchone()
        cola = pd.read_sql_query("SELECT id,ticket_id,destinatario,asunto,estado,error,creado_en FROM correo_salida ORDER BY id DESC LIMIT 100", con)
    if servicio:
        st.info(f"Última revisión: {servicio['actualizado_en']} · {servicio['detalle']}")
    else:
        st.warning("El servicio de correo todavía no se ha conectado. Configura Microsoft 365 en el alojamiento o inicia el puente de Outlook clásico.")
    st.caption("Los avisos se guardan en Borradores del buzón de atención. Revísalos y envíalos manualmente desde Outlook. El estado borrador no confirma un envío.")
    st.dataframe(cola, hide_index=True, width="stretch")
    revisar = cola[cola["estado"].isin(["revisar", "procesando"])]
    if not revisar.empty:
        elegido = st.selectbox("Envío que requiere revisión", revisar["id"].tolist())
        confirmado = st.checkbox("Revisé Borradores, Enviados y Bandeja de salida: este correo no existe ni se envió")
        if st.button("Volver a poner en cola", disabled=not confirmado):
            with db.conexion() as con:
                con.execute("UPDATE correo_salida SET estado='pendiente',error=NULL WHERE id=? AND estado IN ('revisar','procesando')", (int(elegido),))
            st.rerun(scope="app")


CORREO_EJEMPLO = """Hola, necesito validar una cancelación.

Cartera: IBK
Tipo de consulta: Canceló con entidad original
DNI: 45871236
Cuenta: 0047318822

El cliente indica que canceló el 05/10 en ventanilla."""


def pagina_correo(u):
    titulo_pagina("Prueba de correo", "Simula la llegada de un correo de un supervisor y mira cómo se convierte en ticket.")
    st.caption("Así funciona el script que lee tu Outlook (src/leer_outlook.py): solo se aceptan correos de supervisores registrados, "
               "y el ticket se llena con las líneas «Cartera:», «DNI:» y «Cuenta:» que escriba el supervisor.")
    sups = db.usuarios_df()
    sups = sups[(sups["rol"] == "supervisor") & (sups["activo"] == 1) & sups["correo"].notna()]
    if sups.empty:
        st.info("Para probar, asígnale un correo a algún supervisor en «Usuarios».")
        return
    with st.form("correo_demo"):
        remitente = st.selectbox("De (supervisor)", sups["correo"].tolist(),
                                 format_func=lambda c: f"{sups.loc[sups['correo'] == c, 'nombre'].iloc[0]} <{c}>")
        asunto = st.text_input("Asunto", value="Validar cancelación de cuenta")
        cuerpo = st.text_area("Cuerpo del correo", value=CORREO_EJEMPLO, height=240)
        enviar = st.form_submit_button("Simular llegada del correo", type="primary")
    if enviar:
        r = crear_ticket_desde_correo(remitente, asunto, cuerpo, id_correo=f"demo-{uuid.uuid4().hex[:12]}")
        if not r["ok"]:
            st.error(r["motivo"])
            return
        d = r["datos"]
        st.success(f"Llegó el correo y se creó el ticket {r['codigo']} para {r['supervisor']}.")
        st.markdown(
            '<div class="sk"><p class="tt">Datos detectados en el correo</p>'
            f'<p class="sm">Cartera: <b>{esc(d["cartera"])}</b> · Tipo: <b>{esc(d["tipo_consulta"])}</b><br>'
            f'Documento: <b>{esc(d["documento"] or "—")}</b> · Cuenta: <b>{esc(d["cuenta"] or "—")}</b></p>'
            + (f'<p class="rp" style="color:#8a6410">Faltó detectar: {esc(", ".join(d["faltantes"]))}. Complétalo al gestionar el ticket.</p>'
               if d["faltantes"] else '<p class="rp" style="color:#23724a">Se detectaron todos los datos.</p>') + "</div>", unsafe_allow_html=True)
        st.button("Abrir ticket", on_click=ir_a, args=("Gestionar", r["tid"]))


def pagina_usuarios(u):
    if not acceso_vigente(u):
        return
    if u["rol"] != "backoffice":
        st.error("Solo back office puede gestionar usuarios.")
        return
    titulo_pagina("Usuarios", "Los supervisores importados del Excel no tienen correo ni contraseña: asígnalos aquí para que puedan entrar.")
    df = db.usuarios_df()
    st.caption("ENTIDAD, CLIENTE y ASESORIA no son personas y quedaron inactivos.")
    mostrar = df.assign(rol=df["rol"].map({"supervisor": "Supervisor", "backoffice": "Back office"}),
                        activo=df["activo"].map({1: "Sí", 0: "No"}), con_clave=df["con_clave"].map({1: "Sí", 0: "No"}))
    st.dataframe(mostrar.rename(columns={"nombre": "Nombre", "correo": "Correo", "rol": "Rol", "activo": "Activo",
                                         "con_clave": "Puede entrar", "tickets": "Tickets"}).drop(columns="id"),
                 hide_index=True, width="stretch")
    nuevo = "Nuevo usuario"
    elegido = st.selectbox("Crear o editar usuario", [nuevo] + df["nombre"].tolist())
    st.caption("Selecciona un usuario para cambiar su correo o contraseña. Deja la contraseña vacía para conservar la actual.")
    fila = None if elegido == nuevo else df[df["nombre"] == elegido].iloc[0]
    with st.form(f"usuario_{elegido}"):
        c1, c2 = st.columns(2)
        nombre = c1.text_input("Nombre (igual que en la columna SOLICITUD)", value="" if fila is None else fila["nombre"])
        correo = c2.text_input("Correo", value="" if fila is None or pd.isna(fila["correo"]) else fila["correo"])
        rol = c1.selectbox("Rol", ["supervisor", "backoffice"], index=0 if fila is None or fila["rol"] == "supervisor" else 1)
        activo = c2.checkbox("Activo", value=True if fila is None else bool(fila["activo"]))
        clave = st.text_input("Contraseña nueva (déjala vacía para no cambiarla)", type="password")
        clave2 = st.text_input("Repite la contraseña nueva", type="password")
        if st.form_submit_button("Guardar usuario", type="primary"):
            if not nombre.strip():
                st.error("El nombre es obligatorio.")
            elif correo.strip() and not re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", correo.strip()):
                st.error("El correo no es válido.")
            elif clave and len(clave) < 8:
                st.error("La contraseña debe tener al menos 8 caracteres.")
            elif clave != clave2:
                st.error("Las contraseñas no coinciden.")
            elif fila is not None and int(fila["id"]) == u["id"] and (rol != "backoffice" or not activo):
                st.error("No puedes quitarte tu propio acceso de back office.")
            else:
                try:
                    if fila is None:
                        db.crear_usuario(nombre, correo, rol, clave or None, int(activo))
                    else:
                        db.actualizar_usuario(int(fila["id"]), nombre, correo, rol, activo, clave or None)
                    if fila is not None and int(fila["id"]) == u["id"]:
                        st.session_state["usuario"] = {"id": u["id"], "nombre": nombre.strip().upper(), "correo": correo.strip().lower(), "rol": rol}
                    st.toast("Usuario guardado")
                    st.rerun()
                except sqlite3.IntegrityError:
                    st.error("Ya existe un usuario con ese nombre o correo.")


    if fila is not None:
        st.subheader("Eliminar usuario")
        if int(fila["id"]) == u["id"]:
            st.info("No puedes eliminar tu propia cuenta.")
        else:
            st.caption("Puedes conservar sus solicitudes o borrarlas junto con todos sus mensajes, historial y avisos de correo de la plataforma.")
            with st.form(f"eliminar_usuario_{int(fila['id'])}"):
                borrar = st.radio("¿Borrar también todas sus solicitudes?", ["No, conservar solicitudes", "Sí, borrar todas sus solicitudes"], key=f"borrar_solicitudes_{int(fila['id'])}")
                confirmado = st.checkbox(f"Confirmo eliminar a {fila['nombre']}")
                if st.form_submit_button("Eliminar usuario"):
                    if not confirmado:
                        st.error("Marca la confirmación para eliminar este usuario.")
                    else:
                        try:
                            db.eliminar_usuario(int(fila["id"]), u["id"], borrar_solicitudes=borrar.startswith("Sí"))
                            st.toast("Usuario eliminado")
                            st.rerun()
                        except (ValueError, PermissionError) as exc:
                            st.error(str(exc))


@st.fragment(run_every="5s")
def centro_notificaciones(u):
    if not acceso_vigente(u):
        return
    avisos = db.notificaciones_usuario(u["id"])
    pendientes = db.contar_notificaciones(u["id"])
    ultimo = max((n["id"] for n in avisos), default=0)
    clave = f"notificacion_vista_{u['id']}"
    anterior = st.session_state.get(clave, ultimo)
    if ultimo > anterior:
        nuevos = [n for n in avisos if n["id"] > anterior and not n["leida"]]
        if nuevos:
            texto = f"{nuevos[0]['titulo']} · {nuevos[0]['codigo']}"
            if len(nuevos) > 1:
                texto += f" · y {len(nuevos) - 1} avisos más"
            st.toast(texto, icon=":material/notifications_active:", duration="long")
    st.session_state[clave] = ultimo
    estado, campana = st.columns([3, 2], vertical_alignment="center")
    estado.markdown('<div class="live-status"><span></span> Centro de atención · En línea</div>', unsafe_allow_html=True)
    with campana.container(key="campana_notificaciones"):
        if pendientes:
            contador = str(pendientes) if pendientes < 100 else "99+"
            st.markdown(f'<span class="notification-badge" aria-hidden="true">{contador}</span>', unsafe_allow_html=True)
        with st.popover(f"Notificaciones ({pendientes} sin leer)", icon=":material/notifications:", use_container_width=True):
            st.markdown("### Notificaciones pendientes")
            st.caption("Solicitudes, mensajes y cambios de estado. Actualización cada 5 segundos con el portal abierto.")
            if pendientes and st.button("Marcar todas como leídas", key="leer_notificaciones"):
                db.marcar_notificaciones(u["id"])
                st.rerun(scope="app")
            if not avisos:
                st.info("Estás al día. Los nuevos avisos aparecerán aquí.")
            for n in avisos:
                with st.container(border=True):
                    st.markdown(f"{'● ' if not n['leida'] else ''}**{n['codigo']} · {n['titulo']}**")
                    st.caption(pd.Timestamp(n["creado_en"], tz="UTC").tz_convert("America/Lima").strftime("%d/%m/%Y · %H:%M"))
                    if st.button("Ver ticket", key=f"aviso_{n['id']}"):
                        db.marcar_notificaciones(u["id"], n["id"])
                        if u["rol"] == "backoffice":
                            ir_a("Gestionar", n["ticket_id"])
                        else:
                            st.session_state["pagina_pf"] = "Mis solicitudes"
                            abrir_detalle(n["ticket_id"])
                        st.rerun(scope="app")
            if len(avisos) == 30:
                st.caption("Mostrando hasta 30 avisos pendientes. Los leídos desaparecen de este menú.")


# ---------- aplicación ----------
if os.getenv("PORTAL_AUTH_HTTP") == "1":
    sesion = db.usuario_por_sesion(st.context.cookies.get("portal_session"))
    if sesion:
        st.session_state["usuario"] = {k: sesion[k] for k in ("id", "nombre", "correo", "rol")}
    else:
        st.session_state.pop("usuario", None)
usuario = st.session_state.get("usuario")
if not usuario:
    pantalla_acceso()
    st.stop()
acceso_vigente(usuario)

paginas = BACK if usuario["rol"] == "backoffice" else SUP
if "_ir_a" in st.session_state:                       # salto desde una fila, antes de dibujar el menú
    destino, tid_destino = st.session_state.pop("_ir_a")
    st.session_state["pagina_pf"], st.session_state["ticket_sel"] = destino, tid_destino
if st.session_state.get("pagina_pf") not in paginas:
    st.session_state["pagina_pf"] = paginas[0]
pagina = st.session_state["pagina_pf"]

with st.sidebar:
    st.markdown(logo_y(), unsafe_allow_html=True)
    st.markdown('<div class="sidebar-label">ESPACIO DE TRABAJO</div>', unsafe_allow_html=True)
    iconos = {"solicitudes":"view_list", "gestionar":"tune", "nueva":"add_circle", "correo":"mail", "usuarios":"group"}
    for i, p in enumerate(paginas):
        icono, titulo = NAV_INFO[p]
        st.button(titulo, key=f"navb_{i}", icon=f":material/{iconos[icono]}:",
                  type="primary" if p == pagina else "secondary", use_container_width=True,
                  on_click=cambiar_pagina, args=(p,))
    st.divider()
    st.markdown(f'<div class="sidebar-profile">{esc(usuario["nombre"].title())}<small>{"Equipo de atención" if usuario["rol"] == "backoffice" else "Supervisor"}</small></div>', unsafe_allow_html=True)
    st.button("Cerrar sesión", key="navb_salir", icon=":material/logout:", use_container_width=True, on_click=cerrar_sesion)

centro_notificaciones(usuario)

st.markdown(cabecera(NAV_INFO[pagina][1], usuario["nombre"], "Equipo de atención" if usuario["rol"] == "backoffice" else "Supervisor"), unsafe_allow_html=True)
{"Mis solicitudes": pagina_mis_solicitudes, "Nueva solicitud": pagina_nueva, "Inicio": pagina_inicio,
 "Gestionar": pagina_gestionar, "Correo": pagina_buzon, "Prueba de correo": pagina_correo, "Usuarios": pagina_usuarios}[pagina](usuario)
