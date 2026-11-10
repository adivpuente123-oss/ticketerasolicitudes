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
from solicitudes import registrar_solicitud, SolicitudDuplicada
from config import CARTERAS, CONCLUSIONES, CORRESPONDE, ESTADOS_TICKET, TIPOS_CONSULTA, DIAS_ALERTA_PENDIENTE, TIPO_TRANSACCION, PRIORIDADES
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
    if p == "Nueva solicitud":
        st.session_state.pop("_solicitud_resultado", None)
    st.session_state["pagina_pf"] = p
    st.session_state.pop("ver_ticket", None)


def cambiar_pag(delta):
    st.session_state["pag_tabla"] = max(0, st.session_state.get("pag_tabla", 0) + delta)


def reiniciar_pag():
    st.session_state["pag_tabla"] = 0


def cerrar_sesion():
    for clave in list(st.session_state):
        if clave.startswith(("nueva_", "reply_", "adj_mens_", "nota_", "conv_version_", "prop_", "resolver_")) or clave in ("_reset_nueva", "_solicitud_resultado", "_form_version"):
            st.session_state.pop(clave, None)
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
        v = v[v[["codigo", "tipo_consulta", "cuenta", "documento", "supervisor", "cartera", "asunto", "nombre_cliente", "numero_expediente"]].fillna("").apply(
            lambda s: s.astype(str).str.lower().str.contains(b, regex=False)).any(axis=1)]
    asc = orden == "Más antiguas primero"
    # las abiertas van primero (son las que hay que atender) y las respondidas al final
    return v.assign(_r=v["estado"] == "Respondida").sort_values(["_r", "fecha_solicitud", "id"], ascending=[True, asc, asc]).drop(columns="_r")


def exportar(v) -> bytes:
    out = pd.DataFrame({"Código": v["codigo"], "Origen": v["origen"], "Supervisor": v["supervisor"], "Cartera": v["cartera"],
                        "Tipo de consulta": v["tipo_consulta"], "Cuenta": v["cuenta"].map(mascara), "Estado": v["estado"],
                        "Solicitada": v["fecha_solicitud"], "Enviada": v["fecha_envio"], "Respondida": v["fecha_respuesta"],
                        "Conclusión": v["conclusion"], "Días abierta": v["dias"], "Asunto": v["asunto"], "Nombre cliente": v["nombre_cliente"], "Expediente": v["numero_expediente"], "Juzgado": v["juzgado"], "Materia": v["materia"]})
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
            columnas = st.columns([1.15, 2.15, 1, 1.5, 1.2, .45, .45], vertical_alignment="center")
            for col, texto in zip(columnas, ["Ticket", "Supervisor / consulta" if modo == "bo" else "Solicitud", "Cartera", "Estado", "Solicitada", "", ""]):
                col.caption(texto)
        for row_index, (_, t) in enumerate(v.iloc[ini:fin].iterrows()):
            with st.container(key=f"ticket_row_{int(t['id'])}_{'odd' if row_index % 2 else 'even'}"):
                codigo, asesor, cartera_col, estado_col, fecha_col, abrir_col, borrar_col = st.columns([1.15, 2.15, 1, 1.5, 1.2, .45, .45], vertical_alignment="center")
                codigo.markdown(f'<span class="table-code">{esc(t["codigo"])}</span><span class="table-origin">{esc({"web":"Web", "correo":"Correo", "excel":"Excel"}.get(t["origen"], t["origen"]))}</span>', unsafe_allow_html=True)
                nombre = str(t["supervisor"] or "Sin usuario") if modo == "bo" else (t["asunto"] or t["tipo_consulta"] or "Solicitud")
                asesor.markdown(f'<div class="table-person">{esc(nombre.title() if modo == "bo" else nombre)}<small>{esc(t["asunto"] or t["tipo_consulta"] or "Por completar") if modo == "bo" else esc(mascara(t["cuenta"]))}</small></div>', unsafe_allow_html=True)
                cartera_col.markdown(f'<span class="table-portfolio">{esc(t["cartera"])}</span>', unsafe_allow_html=True)
                dias = int(t["dias"]) if pd.notna(t["dias"]) else None
                tiempo = "Atendida" if dias is None else "Hoy" if dias == 0 else f"{dias} días abierta"
                demora = dias is not None and dias > DIAS_ALERTA_PENDIENTE
                fecha_col.markdown(f'<div class="table-date">{esc(fecha_txt(t["fecha_solicitud"]))}<small class="{"overdue" if demora else ""}">{tiempo}</small></div>', unsafe_allow_html=True)
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


def limpiar_filtros_solicitudes():
    for clave, valor in {"bo_q": "", "bo_estado": "Todos los estados", "bo_cartera": "Todas", "bo_supervisor": 0, "bo_periodo": "Todo el historial", "bo_orden": "Más antiguas primero", "bo_demora": False}.items():
        st.session_state[clave] = valor
    for clave in ("bo_desde", "bo_hasta"):
        st.session_state.pop(clave, None)
    reiniciar_pag()


@st.fragment(run_every="5s")
def pagina_inicio(u):
    if not acceso_vigente(u):
        return
    df = db.tickets_df()
    df["dias"] = dias_abierto(df)
    datos = [
        ("pending", "◷", int((df["estado"] == "Recibida").sum()), "Por atender", "Solicitudes recién recibidas"),
        ("review", "↗", int((df["estado"] == "Enviada a verificar").sum()), "En verificación", "En seguimiento con la entidad"),
        ("approved", "✓", int((df["estado"] == "Respondida").sum()), "Respondidas", "Atenciones completadas"),
        ("rejected", "!", int((df["dias"] > DIAS_ALERTA_PENDIENTE).sum()), "Con demora", f"Abiertas más de {DIAS_ALERTA_PENDIENTE} días"),
    ]
    st.markdown('<div class="summary-grid">' + ''.join(
        f'<div class="summary-card {clase}"><div class="summary-card-top"><span>{etiqueta}</span><span class="summary-icon">{icono}</span></div><strong>{valor}</strong><small>{detalle}</small></div>'
        for clase, icono, valor, etiqueta, detalle in datos) + '</div>', unsafe_allow_html=True)
    with st.container(key="filtros_panel"):
        c1, c2, c3, c4 = st.columns([2.5, 1.3, 1, 1.3])
        buscar = c1.text_input("Buscar solicitud", placeholder="Código, documento, cuenta o supervisor", key="bo_q", on_change=reiniciar_pag)
        estado = c2.selectbox("Estado", FILTRO_ESTADO, key="bo_estado", on_change=reiniciar_pag,
                              format_func=lambda x: "Todos los estados" if x == "Todos los estados" else x)
        cartera = c3.selectbox("Cartera", ["Todas"] + CARTERAS, key="bo_cartera", on_change=reiniciar_pag)
        nombres = {int(r.supervisor_id): str(r.supervisor or "Sin usuario").title() for r in df.itertuples() if pd.notna(r.supervisor_id)}
        supervisor = c4.selectbox("Supervisor", [0] + sorted(nombres, key=lambda x: nombres[x]), format_func=lambda x: "Todos los supervisores" if x == 0 else nombres[x], key="bo_supervisor", on_change=reiniciar_pag)
        c1, c2, c3 = st.columns([1.4, 1.4, 2.8], vertical_alignment="bottom")
        periodo = c1.selectbox("Período de solicitud", ["Todo el historial", "Este mes", "Últimos 7 días", "Últimos 30 días", "Personalizado"], key="bo_periodo", on_change=reiniciar_pag)
        orden = c2.selectbox("Orden", ["Más antiguas primero", "Más recientes primero"], key="bo_orden", on_change=reiniciar_pag)
        demora_col, limpiar_col = c3.columns([1.4, 1], vertical_alignment="center")
        solo_demora = demora_col.checkbox("Solo con demora", help=f"Solicitudes abiertas hace más de {DIAS_ALERTA_PENDIENTE} días", key="bo_demora", on_change=reiniciar_pag)
        limpiar_col.button("Limpiar filtros", icon=":material/filter_alt_off:", key="bo_limpiar", on_click=limpiar_filtros_solicitudes)
        desde = hasta = None
        hoy = pd.Timestamp.now(tz="America/Lima").date()
        if periodo == "Personalizado":
            c1, c2 = st.columns(2)
            desde = c1.date_input("Desde", value=hoy.replace(day=1), key="bo_desde", on_change=reiniciar_pag)
            hasta = c2.date_input("Hasta", value=hoy, key="bo_hasta", on_change=reiniciar_pag)
        v = filtrar(df, buscar, estado, cartera, orden)
        if supervisor:
            v = v[v["supervisor_id"] == supervisor]
        hoy = pd.Timestamp.now(tz="America/Lima").date()
        if periodo == "Este mes":
            desde, hasta = hoy.replace(day=1), hoy
        elif periodo in ("Últimos 7 días", "Últimos 30 días"):
            desde, hasta = hoy - pd.Timedelta(days=6 if periodo == "Últimos 7 días" else 29), hoy
        if desde is not None and hasta is not None:
            fechas = pd.to_datetime(v["fecha_solicitud"], errors="coerce")
            v = v[(fechas >= pd.Timestamp(desde)) & (fechas <= pd.Timestamp(hasta))]
            if desde > hasta:
                st.warning("La fecha Desde debe ser anterior o igual a Hasta.")
        if solo_demora:
            v = v[v["dias"] > DIAS_ALERTA_PENDIENTE]
    with st.container(key="listado_panel"):
        titulo, exportar_col, nueva = st.columns([4, 1.5, 1.5], vertical_alignment="center")
        titulo.markdown(f'<h2 class="panel-heading">Bandeja de solicitudes <span class="result-count">{len(v)} de {len(df)}</span></h2>', unsafe_allow_html=True)
        exportar_col.download_button("Exportar reporte", exportar(v), "solicitudes.csv", "text/csv", key="exp_bo", icon=":material/file_download:")
        if nueva.button("Nueva solicitud", type="primary", key="btn_nueva", icon=":material/add:"):
            cambiar_pagina("Nueva solicitud")
            st.rerun(scope="app")
        render_tabla(v, "bo", abrir_en_gestionar)
    st.caption("Vista actualizada cada 5 segundos · Los indicadores resumen todo el historial; la tabla refleja los filtros seleccionados.")



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
    documentos_solicitud(u, tid)
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
        if st.button("Nueva solicitud", type="primary", key="btn_nueva"):
            cambiar_pagina("Nueva solicitud")
            st.rerun(scope="app")
        return
    df["dias"] = dias_abierto(df)
    a, c = st.columns([8, 2.3], vertical_alignment="center")
    a.markdown('<h1 class="h1">Mis solicitudes</h1>', unsafe_allow_html=True)
    if c.button("Nueva solicitud", type="primary", key="btn_nueva"):
        cambiar_pagina("Nueva solicitud")
        st.rerun(scope="app")
    st.markdown(kpis_html(df, ("Mis solicitudes", "Recibidas", "En verificación", "Respondidas")), unsafe_allow_html=True)
    v = filtrar(df, *barra_filtros("sup"))
    render_tabla(v, "sup", abrir_detalle)
    st.caption("Abre una solicitud para consultar su detalle y conversar con el equipo de atención.")


def reiniciar_formulario_nueva():
    for clave in list(st.session_state):
        if clave.startswith("nueva_"):
            st.session_state.pop(clave, None)
    st.session_state["_form_version"] = st.session_state.get("_form_version", 0) + 1


def pagina_nueva(u):
    if not acceso_vigente(u):
        return
    if st.session_state.pop("_reset_nueva", False):
        reiniciar_formulario_nueva()
    st.markdown('<div class="request-heading"><div class="request-title" role="heading" aria-level="1">Nueva solicitud</div><p>Cuéntanos qué necesitas. El equipo revisará los datos y documentos de tu solicitud.</p></div>', unsafe_allow_html=True)
    resultado = st.session_state.get("_solicitud_resultado")
    if resultado:
        with st.container(key="solicitud_confirmacion"):
            st.success(f"Solicitud {resultado['codigo']} registrada correctamente.")
            if st.button("Ver solicitud registrada", icon=":material/arrow_forward:"):
                st.session_state.pop("_solicitud_resultado", None)
                if u["rol"] == "backoffice":
                    ir_a("Gestionar", resultado["id"])
                else:
                    cambiar_pagina("Mis solicitudes")
                    abrir_detalle(resultado["id"])
                st.rerun(scope="app")
    contenido, ayuda = st.columns([2.05, 1], gap="large", vertical_alignment="top")
    with contenido, st.container(key="nueva_detalles"):
        st.markdown('<div class="request-card-heading"><span class="request-step">01</span><div><div class="request-card-title" role="heading" aria-level="2">Detalles de la solicitud</div><p>Los campos con * son obligatorios.</p></div></div>', unsafe_allow_html=True)
        asunto = st.text_input("Asunto *", placeholder="Resume brevemente la atención que necesitas", max_chars=160, key="nueva_asunto")
        supervisor_id = u["id"]
        if u["rol"] == "backoffice":
            sups = db.usuarios_df()
            sups = sups[(sups["rol"] == "supervisor") & (sups["activo"] == 1)]
            nombres = {int(r.id): r.nombre.title() for r in sups.itertuples()}
            supervisor_id = st.selectbox("Supervisor que solicita *", list(nombres), format_func=lambda i: nombres[i], key="nueva_supervisor") if nombres else None
            if supervisor_id is None:
                st.warning("Crea un supervisor activo en Usuarios antes de registrar la solicitud.")
        c1, c2 = st.columns(2)
        cartera = c1.selectbox("Cartera *", CARTERAS, key="nueva_cartera")
        tipo = c2.selectbox("Tipo de consulta *", TIPOS_CONSULTA, key="nueva_tipo")
        transaccion = tipo == TIPO_TRANSACCION
        incompletos = False
        nombre_cliente = expediente = juzgado = materia = cuenta = ""
        if transaccion:
            st.markdown('<div class="request-section"><span class="request-step">02</span><div><div class="request-section-title" role="heading" aria-level="3">Datos del expediente</div><p>Información para preparar la transacción extrajudicial.</p></div></div>', unsafe_allow_html=True)
            incompletos = st.checkbox("No dispongo de todos los datos; adjuntaré los documentos del expediente", key="nueva_incompletos")
            if incompletos:
                st.info("Completa lo que conozcas y adjunta al menos un documento. El equipo extraerá la información que falte.")
            marca = "" if incompletos else " *"
            c1, c2 = st.columns(2)
            documento = c1.text_input("DNI" + marca, placeholder="8 dígitos", max_chars=8, key="nueva_documento")
            nombre_cliente = c2.text_input("Nombre completo" + marca, placeholder="Nombres y apellidos", max_chars=160, key="nueva_nombre")
            expediente = c1.text_input("Nº de expediente" + marca, placeholder="Número del expediente judicial", max_chars=100, key="nueva_expediente")
            juzgado = c2.text_input("Juzgado" + marca, placeholder="Órgano jurisdiccional", max_chars=200, key="nueva_juzgado")
            materia = st.text_input("Materia" + marca, placeholder="Materia del proceso", max_chars=200, key="nueva_materia")
        else:
            c1, c2 = st.columns(2)
            documento = c1.text_input("Documento (DNI) *", placeholder="Documento del cliente", max_chars=15, key="nueva_documento")
            cuenta = c2.text_input("Número de cuenta *", placeholder="Cuenta relacionada con la solicitud", max_chars=30, key="nueva_cuenta")
        descripcion = st.text_area("Descripción *", placeholder="Describe la atención que necesitas y cualquier información que ayude a revisarla.", height=150, max_chars=5000, key="nueva_descripcion")
        st.markdown('<div class="request-section"><span class="request-step">' + ("03" if transaccion else "02") + '</span><div><div class="request-section-title" role="heading" aria-level="3">Documentos de respaldo' + (' *' if incompletos else '') + '</div><p>Adjunta el expediente o los documentos que ayuden a resolver la solicitud.</p></div></div>', unsafe_allow_html=True)
        archivos = st.file_uploader("Selecciona o arrastra tus documentos", type=["pdf", "png", "jpg", "jpeg"], accept_multiple_files=True, max_upload_size=10,
                                    help="Hasta 5 archivos, máximo 10 MB por archivo y 30 MB en total.", key=f"nueva_archivos_{st.session_state.get('_form_version', 0)}")
        st.caption("PDF, PNG o JPG · Hasta 5 archivos · 10 MB por archivo · 30 MB en total")
        forzar = st.checkbox("Registrar otra solicitud aunque exista una abierta para el mismo DNI y expediente" if transaccion else "Registrar otra solicitud aunque exista una abierta para el mismo documento y cuenta", key="nueva_forzar")
        st.divider()
        pie, cancelar, enviar = st.columns([1.2, .8, 1.2], vertical_alignment="center")
        pie.markdown('<span class="required-note">* Campos obligatorios</span>', unsafe_allow_html=True)
        if cancelar.button("Cancelar", key="nueva_cancelar", use_container_width=True):
            st.session_state["_reset_nueva"] = True
            st.session_state.pop("_solicitud_resultado", None)
            cambiar_pagina("Inicio" if u["rol"] == "backoffice" else "Mis solicitudes")
            st.rerun(scope="app")
        if enviar.button("Enviar solicitud", type="primary", icon=":material/arrow_forward:", key="nueva_enviar", use_container_width=True):
            try:
                tid, codigo = registrar_solicitud(u["id"], supervisor_id, asunto=asunto, cartera=cartera, tipo=tipo,
                    documento=documento, cuenta=cuenta, descripcion=descripcion, nombre_cliente=nombre_cliente,
                    numero_expediente=expediente, juzgado=juzgado, materia=materia, datos_incompletos=incompletos,
                    adjuntos=[{"nombre": f.name, "datos": f.getvalue()} for f in archivos], forzar=forzar)
                st.session_state["_solicitud_resultado"] = {"id": tid, "codigo": codigo}
                st.session_state["_reset_nueva"] = True
                st.rerun(scope="app")
            except SolicitudDuplicada as exc:
                st.warning(str(exc))
            except (ValueError, PermissionError) as exc:
                st.error(str(exc))
            except sqlite3.Error:
                st.error("No se pudo guardar la solicitud. Revisa el almacenamiento y vuelve a intentar; no se registró una solicitud parcial.")
    with ayuda, st.container(key="nueva_ayuda"):
        st.markdown('<div class="help-heading"><span>?</span><div class="request-help-title" role="heading" aria-level="2">Te ayudamos a completarla</div></div><p class="help-intro">Una solicitud clara permite revisar tu caso con toda la información necesaria.</p><div class="help-divider"></div><div class="request-help-section-title" role="heading" aria-level="3">Antes de enviar</div><ul class="help-list"><li>Escribe un asunto breve y específico.</li><li>Verifica la cartera y los datos del cliente.</li><li>Explica qué atención necesitas.</li><li>Adjunta documentos legibles cuando corresponda.</li></ul>', unsafe_allow_html=True)
        if transaccion:
            st.markdown('<div class="case-help"><strong>Transacción extrajudicial</strong><p>Necesitamos DNI, nombre, número de expediente, juzgado y materia. Si falta información, marca la opción del expediente y adjunta los documentos disponibles.</p></div>', unsafe_allow_html=True)
        st.markdown('<div class="request-security"><span>✓</span><p>Los documentos quedan disponibles para el supervisor de esta solicitud y el equipo de atención. No incluyas contraseñas.</p></div>', unsafe_allow_html=True)


def documentos_solicitud(u, tid, mostrar_asunto=True):
    t = db.ticket(tid)
    if not t or (u["rol"] != "backoffice" and t["supervisor_id"] != u["id"]):
        return
    if t["asunto"] and mostrar_asunto:
        st.markdown(f'<div class="ticket-subject"><small>ASUNTO</small><strong>{esc(t["asunto"])}</strong></div>', unsafe_allow_html=True)
    if t["tipo_consulta"] == TIPO_TRANSACCION:
        with st.container(border=True):
            st.markdown("### Datos del expediente")
            if t["datos_incompletos"]:
                st.info("El solicitante indicó que falta información. Revisa los documentos adjuntos para completarla.")
            campos = [("DNI", t["documento"]), ("Nombre", t["nombre_cliente"]), ("Nº de expediente", t["numero_expediente"]), ("Juzgado", t["juzgado"]), ("Materia", t["materia"])]
            st.markdown('<div class="case-data-grid">' + ''.join(f'<div><small>{etiqueta}</small><strong>{esc(valor or "Por completar")}</strong></div>' for etiqueta, valor in campos) + '</div>', unsafe_allow_html=True)
        if u["rol"] == "backoffice":
            with st.expander("Completar o editar datos del expediente"):
                with st.form(f"expediente_{tid}"):
                    c1, c2 = st.columns(2)
                    dni = c1.text_input("DNI", value=t["documento"] or "", max_chars=8)
                    nombre = c2.text_input("Nombre completo", value=t["nombre_cliente"], max_chars=160)
                    expediente = c1.text_input("Nº de expediente", value=t["numero_expediente"], max_chars=100)
                    juzgado = c2.text_input("Juzgado", value=t["juzgado"], max_chars=200)
                    materia = st.text_input("Materia", value=t["materia"], max_chars=200)
                    if st.form_submit_button("Guardar datos del expediente", type="primary"):
                        try:
                            db.actualizar_expediente(tid, u["id"], dni, nombre, expediente, juzgado, materia)
                            st.toast("Datos del expediente guardados")
                            st.rerun(scope="app")
                        except (ValueError, PermissionError) as exc:
                            st.error(str(exc))
    try:
        adjuntos = db.adjuntos_ticket(tid, u["id"])
    except PermissionError:
        return
    if any(a["mensaje_id"] is None for a in adjuntos):
        st.markdown("### Documentos adjuntos")
    for a in [a for a in adjuntos if a["mensaje_id"] is None]:
        with st.container(border=True):
            nombre, accion = st.columns([3, 1], vertical_alignment="center")
            nombre.markdown(f'<div class="document-label"><span>{esc(a["nombre"].rsplit(".", 1)[-1].upper())}</span><div><strong>{esc(a["nombre"])}</strong><small>{a["tamano"] / 1024:.0f} KB · Documento de respaldo</small></div></div>', unsafe_allow_html=True)
            if os.getenv("PORTAL_AUTH_HTTP") == "1":
                accion.link_button("Descargar", f"/_portal/adjuntos/{a['id']}", icon=":material/download:")
            else:
                archivo = db.obtener_adjunto(a["id"], u["id"])
                accion.download_button("Descargar", archivo["datos"], file_name=a["nombre"], mime=a["tipo_mime"], key=f"descargar_adjunto_{a['id']}")


# ---------- gestión de un ticket (back office) ----------
def hora_local(valor):
    marca = pd.to_datetime(valor, errors="coerce", utc=True)
    return "—" if pd.isna(marca) else marca.tz_convert("America/Lima").strftime("%d/%m/%Y · %H:%M")


def iniciales_persona(nombre):
    return ''.join(p[:1] for p in (nombre or "Usuario").split()[:2]).upper()


def pagina_gestionar(u):
    if not acceso_vigente(u):
        return
    if u["rol"] != "backoffice":
        st.error("Solo el equipo de atención puede gestionar solicitudes.")
        return
    encabezado, volver = st.columns([4, 1.35], vertical_alignment="center")
    encabezado.markdown('<div class="request-heading gestion-heading"><div class="request-title" role="heading" aria-level="1">Gestionar solicitud</div><p>Consulta el detalle, responde y actualiza el ticket.</p></div>', unsafe_allow_html=True)
    if volver.button("Volver al listado", icon=":material/arrow_back:", key="gestion_volver", use_container_width=True):
        cambiar_pagina("Inicio")
        st.rerun(scope="app")
    df = db.tickets_df()
    if df.empty:
        st.info("Todavía no hay solicitudes para gestionar.")
        return
    ids = df["id"].tolist()
    if st.session_state.get("ticket_sel") not in ids:
        st.session_state["ticket_sel"] = ids[0]
    etiquetas = {r.id: f"{r.codigo} · {r.supervisor or 'Sin usuario'} · {r.tipo_consulta}" for r in df.itertuples()}
    with st.expander("Cambiar de solicitud", icon=":material/search:"):
        tid = st.selectbox("Ticket", ids, key="ticket_sel", format_func=lambda i: etiquetas[i])
    t = db.ticket(tid)
    izquierda, derecha = st.columns([2.05, 1], gap="large", vertical_alignment="top")
    with izquierda:
        with st.container(key="gestion_resumen"):
            st.markdown(f'<div class="gestion-badges"><span class="gestion-code">{esc(t["codigo"])}</span>{chip_estado(t["estado"])}{chip_conclusion(t["conclusion"])}</div><div class="gestion-subject" role="heading" aria-level="2">{esc(t["asunto"] or t["tipo_consulta"] or "Solicitud de atención")}</div><p class="gestion-created">Creada por <strong>{esc((t["supervisor"] or "Sin cuenta asociada").title())}</strong> · {hora_local(t["creado_en"])}</p>', unsafe_allow_html=True)
            st.markdown('<div class="gestion-section-title" role="heading" aria-level="3">Descripción</div><div class="gestion-description">' + esc(t["descripcion"] or "Sin descripción registrada.").replace('\n', '<br>') + '</div>', unsafe_allow_html=True)
            st.markdown(f'<div class="gestion-metadata"><span>Cartera <strong>{esc(t["cartera"])}</strong></span><span>Documento <strong>{esc(t["documento"] or "Por completar")}</strong></span><span>Cuenta <strong>{esc(t["cuenta"] or "No indicada")}</strong></span></div>', unsafe_allow_html=True)
            if t["respuesta"]:
                st.markdown('<div class="gestion-resolution"><strong>Respuesta registrada</strong><p>' + esc(t["respuesta"]).replace('\n', '<br>') + '</p></div>', unsafe_allow_html=True)
            documentos_solicitud(u, tid, mostrar_asunto=False)
        conversacion(u, tid)
        with st.expander("Historial de la solicitud", icon=":material/history:"):
            h = db.historial_df(tid)
            st.markdown('<div class="hist">' + ''.join(f'<p><b>{esc(r.evento)}</b><small>{hora_local(r.fecha)} · {esc(r.usuario)}</small>{esc(r.detalle or "")}</p>' for r in h.itertuples()) + '</div>', unsafe_allow_html=True)
    with derecha:
        with st.container(key="gestion_propiedades"):
            st.markdown('<div class="gestion-card-title" role="heading" aria-level="2">Propiedades del ticket</div>', unsafe_allow_html=True)
            usuarios = db.usuarios_df()
            equipo = usuarios[(usuarios["rol"] == "backoffice") & (usuarios["activo"] == 1)]
            nombres = {int(r.id): r.nombre.title() for r in equipo.itertuples()}
            if t["asignado_a"] and t["asignado_a"] not in nombres:
                anterior = db.usuario_por_id(t["asignado_a"])
                nombres[t["asignado_a"]] = (anterior["nombre"].title() if anterior else "Usuario") + " (inactivo)"
            opciones_asignado = [None] + list(nombres)
            tipos = TIPOS_CONSULTA + ([t["tipo_consulta"] or "Sin tipo"] if t["tipo_consulta"] not in TIPOS_CONSULTA else [])
            carteras = CARTERAS + ([t["cartera"]] if t["cartera"] not in CARTERAS else [])
            with st.form(f"propiedades_{tid}"):
                estado = st.selectbox("Estado", ESTADOS_TICKET, index=ESTADOS_TICKET.index(t["estado"]), key=f"prop_estado_{tid}")
                prioridad = st.selectbox("Prioridad", PRIORIDADES, index=PRIORIDADES.index(t["prioridad"]) if t["prioridad"] in PRIORIDADES else 1, key=f"prop_prioridad_{tid}")
                asignado = st.selectbox("Asignado a", opciones_asignado, index=opciones_asignado.index(t["asignado_a"]) if t["asignado_a"] in opciones_asignado else 0, format_func=lambda i: "Sin asignar" if i is None else nombres[i], key=f"prop_asignado_{tid}")
                tipo = st.selectbox("Tipo de consulta", tipos, index=tipos.index(t["tipo_consulta"] or "Sin tipo"), key=f"prop_tipo_{tid}")
                cartera = st.selectbox("Cartera", carteras, index=carteras.index(t["cartera"]), key=f"prop_cartera_{tid}")
                if st.form_submit_button("Guardar cambios", type="primary", use_container_width=True):
                    try:
                        db.actualizar_propiedades(tid, u["id"], estado, prioridad, asignado, cartera, tipo)
                        st.toast("Propiedades guardadas")
                        st.rerun(scope="app")
                    except (ValueError, PermissionError) as exc:
                        st.error(str(exc))
        with st.container(key="gestion_solicitante"):
            solicitante = db.usuario_por_id(t["supervisor_id"]) if t["supervisor_id"] else None
            nombre = (t["supervisor"] or "Sin cuenta asociada").title()
            correo = solicitante["correo"] if solicitante and solicitante["correo"] else "Sin correo registrado"
            st.markdown('<div class="gestion-card-title" role="heading" aria-level="2">Solicitante</div>' + f'<div class="requester-profile"><span>{esc(iniciales_persona(nombre))}</span><div><strong>{esc(nombre)}</strong><small>{esc(correo)}</small></div></div><div class="requester-row"><span>Canal de recepción</span><strong>{esc({"web":"Portal web", "correo":"Correo", "excel":"Importación de Excel"}.get(t["origen"], t["origen"]))}</strong></div>', unsafe_allow_html=True)
        with st.container(key="gestion_tiempos"):
            primeros = [m for m in db.mensajes(tid) if m["autor_rol"] == "backoffice"]
            primera = "No registrada en la conversación"
            if primeros:
                segundos = max(0, (pd.Timestamp(primeros[0]["creado_en"]) - pd.Timestamp(t["creado_en"])).total_seconds())
                minutos = int(segundos // 60)
                primera = "Menos de 1 minuto" if minutos == 0 else f"{minutos} min" if minutos < 60 else f"{minutos // 60} h {minutos % 60} min"
            st.markdown('<div class="gestion-card-title" role="heading" aria-level="2">Seguimiento de atención</div>' + f'<div class="tracking-row"><span>Solicitada</span><strong>{fecha_txt(t["fecha_solicitud"])}</strong></div><div class="tracking-row"><span>Último cambio</span><strong>{hora_local(t["actualizado_en"])}</strong></div><div class="tracking-row"><span>Primera respuesta pública</span><strong>{esc(primera)}</strong></div>', unsafe_allow_html=True)
        with st.container(key="gestion_resultado"):
            with st.expander("Verificación y resultado", icon=":material/task_alt:"):
                with st.form(f"resolver_{tid}"):
                    f_envio = st.date_input("Fecha de envío a la entidad", value=a_fecha(t["fecha_envio"]))
                    opciones_c = ["(sin conclusión)"] + CONCLUSIONES
                    conclusion = st.selectbox("Conclusión de la entidad", opciones_c, index=opciones_c.index(t["conclusion"]) if t["conclusion"] in CONCLUSIONES else 0)
                    opciones_k = ["(sin definir)"] + CORRESPONDE
                    corresponde = st.selectbox("Estado corresponde", opciones_k, index=opciones_k.index(t["estado_corresponde"]) if t["estado_corresponde"] in CORRESPONDE else 0)
                    respuesta = st.text_area("Respuesta final para el supervisor", value=t["respuesta"] or "", height=120)
                    sustento = st.text_input("Sustento", value=t["sustento"] or "")
                    b1, b2 = st.columns(2)
                    enviar = b1.form_submit_button("Enviar a verificar")
                    responder = b2.form_submit_button("Registrar respuesta", type="primary")
                    guardar = st.form_submit_button("Guardar datos de respuesta", use_container_width=True)
                    if enviar or responder or guardar:
                        concl = None if conclusion == opciones_c[0] else conclusion
                        corr = None if corresponde == opciones_k[0] else corresponde
                        if responder and (not concl or not respuesta.strip()):
                            st.error("Indica la conclusión y escribe la respuesta para registrar el resultado.")
                        else:
                            hoy = db.hoy_iso()
                            comunes = dict(estado_corresponde=corr, sustento=sustento.strip() or None)
                            if enviar:
                                cambios = dict(estado="Enviada a verificar", fecha_envio=f_envio.isoformat() if f_envio else hoy, **comunes)
                                evento, detalle = "Enviada a verificar", ""
                            elif responder:
                                cambios = dict(estado="Respondida", fecha_envio=f_envio.isoformat() if f_envio else (t["fecha_envio"] or hoy), fecha_respuesta=t["fecha_respuesta"] or hoy, conclusion=concl, respuesta=respuesta.strip(), **comunes)
                                evento, detalle = "Respondida", concl
                            else:
                                cambios = dict(fecha_envio=f_envio.isoformat() if f_envio else t["fecha_envio"], conclusion=concl, respuesta=respuesta.strip() or None, **comunes)
                                evento, detalle = "Edición de respuesta", ""
                            try:
                                db.actualizar_ticket(tid, u["id"], cambios, evento, detalle, requerir_backoffice=True)
                                st.toast("Resultado guardado · aviso en cola para revisión")
                                st.rerun(scope="app")
                            except (ValueError, PermissionError) as exc:
                                st.error(str(exc))

def acceso_vigente(u):
    actual = db.usuario_por_sesion(st.context.cookies.get("portal_session")) if os.getenv("PORTAL_AUTH_HTTP") == "1" else db.usuario_por_id(u["id"])
    if actual and actual["id"] != u["id"]:
        actual = None
    if not actual or not actual["activo"] or actual["rol"] != u["rol"]:
        cerrar_sesion()
        st.rerun(scope="app")
        return False
    return True


def enlace_adjunto(u, archivo, clave):
    if os.getenv("PORTAL_AUTH_HTTP") == "1":
        st.link_button(f"Descargar {archivo['nombre']}", f"/_portal/adjuntos/{archivo['id']}", icon=":material/attach_file:")
    else:
        datos = db.obtener_adjunto(archivo["id"], u["id"])
        st.download_button(archivo["nombre"], datos["datos"], file_name=archivo["nombre"], mime=archivo["tipo_mime"], key=clave)


def conversacion(u, tid):
    t = db.ticket(tid)
    if not t or (u["rol"] != "backoffice" and t["supervisor_id"] != u["id"]):
        return
    with st.container(key=f"gestion_conversacion_{tid}"):
        st.markdown('<div class="gestion-card-title" role="heading" aria-level="2">Conversación</div>', unsafe_allow_html=True)
        pestañas = st.tabs(["Respuesta pública", "Nota interna"]) if u["rol"] == "backoffice" else [st.container()]
        with pestañas[0]:
            mensajes = db.mensajes(tid)
            archivos = db.adjuntos_ticket(tid, u["id"])
            if not mensajes:
                st.markdown('<p class="chat-empty">Todavía no hay mensajes. Escribe una respuesta para continuar la atención.</p>', unsafe_allow_html=True)
            for m in mensajes:
                equipo = m["autor_rol"] == "backoffice"
                nombre = (m["nombre"] or "Usuario eliminado").title()
                st.markdown(f'<div class="chat-message {"team" if equipo else "client"}"><span class="chat-avatar">{esc(iniciales_persona(nombre))}</span><div class="chat-content"><div class="chat-author"><strong>{esc(nombre)}</strong><small>{hora_local(m["creado_en"])} · {"Correo" if m["id_correo"] else "Portal"}</small></div><div class="chat-bubble">{esc(m["cuerpo"]).replace(chr(10), "<br>")}</div></div></div>', unsafe_allow_html=True)
                for archivo in archivos:
                    if archivo["mensaje_id"] == m["id"]:
                        enlace_adjunto(u, archivo, f"adj_reply_{archivo['id']}")
            version = st.session_state.get(f"conv_version_{tid}", 0)
            with st.form(f"publico_{tid}_{version}"):
                texto = st.text_area("Respuesta pública", placeholder="Escribe una respuesta para el solicitante...", height=115, max_chars=20000, key=f"reply_{tid}_{version}")
                with st.expander("Adjuntar archivos", icon=":material/attach_file:"):
                    adjuntos = st.file_uploader("Documentos de la respuesta", type=["pdf","png","jpg","jpeg"], accept_multiple_files=True, max_upload_size=10, key=f"adj_mens_{tid}_{version}")
                    st.caption("Hasta 5 archivos · 10 MB por archivo · 30 MB en total")
                aviso, boton_respuesta = st.columns([2, 1.2], vertical_alignment="center")
                aviso.caption("Esta respuesta será visible para el solicitante.")
                if boton_respuesta.form_submit_button("Enviar respuesta", type="primary", use_container_width=True):
                    try:
                        db.agregar_mensaje(tid, u["id"], texto, adjuntos=[{"nombre": a.name, "datos": a.getvalue()} for a in adjuntos])
                        st.session_state[f"conv_version_{tid}"] = version + 1
                        st.rerun(scope="app")
                    except (ValueError, PermissionError) as exc:
                        st.error(str(exc))
        if u["rol"] == "backoffice":
            with pestañas[1]:
                st.caption("Solo visible para el equipo de atención. No se envía al supervisor ni por correo.")
                for nota in db.notas_ticket(tid, u["id"]):
                    st.markdown(f'<div class="internal-note"><div><strong>{esc((nota["nombre"] or "Usuario eliminado").title())}</strong><small>{hora_local(nota["creado_en"])}</small></div><p>{esc(nota["cuerpo"]).replace(chr(10), "<br>")}</p></div>', unsafe_allow_html=True)
                with st.form(f"nota_{tid}", clear_on_submit=True):
                    nota = st.text_area("Nota interna", placeholder="Agrega contexto para el equipo...", max_chars=10000, key=f"nota_texto_{tid}")
                    if st.form_submit_button("Guardar nota interna", type="primary", use_container_width=True):
                        try:
                            db.agregar_nota_interna(tid, u["id"], nota)
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
    with st.container(key="topbar"):
        estado, revision, campana = st.columns([7, 4, .7], vertical_alignment="center")
        pagina_actual = NAV_INFO.get(st.session_state.get("pagina_pf", "Inicio"), ("", "Solicitudes"))[1]
        if st.session_state.get("pagina_pf") == "Nueva solicitud":
            estado.markdown('<div class="request-breadcrumb"><span>Solicitudes</span><i>/</i><strong>Nueva solicitud</strong></div>', unsafe_allow_html=True)
        elif st.session_state.get("pagina_pf") == "Gestionar":
            seleccion = db.ticket(st.session_state["ticket_sel"]) if st.session_state.get("ticket_sel") else None
            codigo = seleccion["codigo"] if seleccion else "Gestionar solicitud"
            estado.markdown(f'<div class="request-breadcrumb"><span>Solicitudes</span><i>/</i><strong>{esc(codigo)}</strong></div>', unsafe_allow_html=True)
        else:
            estado.markdown(f'<div class="topbar-path"><h1>{esc(pagina_actual)}</h1></div>', unsafe_allow_html=True)
        revision.markdown(f'<div class="header-sync"><span class="online-dot"></span> En línea <span class="sync-time">· Última revisión {pd.Timestamp.now(tz="America/Lima").strftime("%H:%M:%S")}</span></div>', unsafe_allow_html=True)
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
    st.markdown(logo_y().replace("<strong>Solicitudes</strong>", "<strong>Gestión de<br>solicitudes</strong>"), unsafe_allow_html=True)
    iconos = {"solicitudes":"view_list", "gestionar":"tune", "nueva":"add_circle", "correo":"mail", "usuarios":"group"}
    grupos = [("ATENCIÓN", ["Inicio", "Mis solicitudes", "Nueva solicitud"]), ("SEGUIMIENTO", ["Gestionar", "Correo"]), ("ADMINISTRACIÓN", ["Usuarios", "Prueba de correo"])]
    for grupo, opciones in grupos:
        visibles = [p for p in opciones if p in paginas]
        if not visibles:
            continue
        st.markdown(f'<div class="sidebar-label">{grupo}</div>', unsafe_allow_html=True)
        for p in visibles:
            icono, titulo = NAV_INFO[p]
            st.button(titulo, key=f"navb_{paginas.index(p)}", icon=f":material/{iconos[icono]}:",
                      type="primary" if p == pagina else "secondary", use_container_width=True,
                      on_click=cambiar_pagina, args=(p,))
    st.divider()
    st.markdown(f'<div class="sidebar-profile">{esc(usuario["nombre"].title())}<small>{"Equipo de atención" if usuario["rol"] == "backoffice" else "Supervisor"}</small></div>', unsafe_allow_html=True)
    st.button("Cerrar sesión", key="navb_salir", icon=":material/logout:", use_container_width=True, on_click=cerrar_sesion)

centro_notificaciones(usuario)

{"Mis solicitudes": pagina_mis_solicitudes, "Nueva solicitud": pagina_nueva, "Inicio": pagina_inicio,
 "Gestionar": pagina_gestionar, "Correo": pagina_buzon, "Prueba de correo": pagina_correo, "Usuarios": pagina_usuarios}[pagina](usuario)
