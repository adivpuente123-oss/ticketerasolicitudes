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
from estilos_plataforma import (CSS, cabecera, cabecera_tabla, esc, fila_html, kpi, logo_y, mascara, nav_item, numero)

st.set_page_config(page_title="Plataforma de solicitudes", page_icon="🎫", layout="wide")
st.markdown(CSS, unsafe_allow_html=True)
db.iniciar()

MES_CORTO = ["ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "set", "oct", "nov", "dic"]
CLASE_ESTADO = {"Recibida": "rec", "Enviada a verificar": "env", "Respondida": "res"}
BACK = ["🏠 Inicio", "🛠 Gestionar", "➕ Nueva solicitud", "📬 Correo", "📧 Prueba de correo", "👥 Usuarios"]
SUP = ["📋 Mis solicitudes", "➕ Nueva solicitud"]
NAV_INFO = {"🏠 Inicio": ("solicitudes", "Solicitudes"), "🛠 Gestionar": ("gestionar", "Gestionar ticket"),
            "➕ Nueva solicitud": ("nueva", "Nueva solicitud"), "📧 Prueba de correo": ("correo", "Prueba de correo"),
            "👥 Usuarios": ("usuarios", "Usuarios"), "📋 Mis solicitudes": ("solicitudes", "Mis solicitudes")}
TAM_PAGINA = 20
NAV_INFO["📬 Correo"] = ("correo", "Correo de atención")
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
    ir_a("🛠 Gestionar", tid)


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
    for k in ("usuario", "pagina_pf", "ticket_sel", "_ir_a", "ver_ticket", "pag_tabla"):
        st.session_state.pop(k, None)


def titulo_pagina(texto, sub=""):
    st.markdown(f'<h1 class="h1">{esc(texto)}</h1>' + (f'<p class="sub">{esc(sub)}</p>' if sub else ""), unsafe_allow_html=True)


def metricas(items):
    for c, (etiqueta, valor) in zip(st.columns(len(items)), items):
        c.metric(etiqueta, f"{int(valor):,}")


# ---------- acceso ----------
def pantalla_acceso():
    st.markdown('<div style="font-size:26px;font-weight:600;margin:40px 0 24px;text-align:center">🎫 Plataforma de solicitudes</div>', unsafe_allow_html=True)
    _, centro, _ = st.columns([1, 1.3, 1])
    with centro:
        if not db.hay_backoffice():
            st.subheader("Primer uso: crea al administrador")
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
        st.subheader("Iniciar sesión")
        with st.form("login"):
            correo = st.text_input("Correo")
            clave = st.text_input("Contraseña", type="password")
            if st.form_submit_button("Entrar", type="primary"):
                u = db.usuario_por_correo(correo)
                if u and u["activo"] and db.verificar_clave(clave, u["clave_hash"]):
                    st.session_state["usuario"] = {k: u[k] for k in ("id", "nombre", "correo", "rol")}
                    st.rerun()
                time.sleep(1)  # frena los intentos repetidos
                st.error("Correo o contraseña incorrectos, o el usuario está inactivo.")


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


def render_tabla(v, modo, al_abrir):
    total = len(v)
    paginas = max(1, -(-total // TAM_PAGINA))
    pag = min(st.session_state.get("pag_tabla", 0), paginas - 1)
    ini, fin = pag * TAM_PAGINA, min((pag + 1) * TAM_PAGINA, total)
    with st.container(key="tabla"):
        st.markdown(cabecera_tabla(modo), unsafe_allow_html=True)
        if v.empty:
            st.markdown('<div class="vacio">No hay solicitudes con estos filtros.</div>', unsafe_allow_html=True)
        for _, t in v.iloc[ini:fin].iterrows():
            with st.container(key=f"fila_{int(t['id'])}"):
                st.markdown(fila_html(t, t["dias"], modo), unsafe_allow_html=True)
                st.button("Abrir", key=f"abrir_{int(t['id'])}", on_click=al_abrir, args=(int(t["id"]),))
    c1, c2, c3 = st.columns([6, 1, 1], vertical_alignment="center")
    c1.markdown(f'<div class="pie-tabla">Mostrando {ini + 1 if total else 0}–{fin} de {total:,} · página {pag + 1} de {paginas}</div>', unsafe_allow_html=True)
    c2.button("← Anterior", key="pag_ant", on_click=cambiar_pag, args=(-1,), disabled=pag == 0)
    c3.button("Siguiente →", key="pag_sig", on_click=cambiar_pag, args=(1,), disabled=pag >= paginas - 1)


def barra_filtros(prefijo):
    f1, f2, f3, f4 = st.columns([3, 1.6, 1.2, 1.6])
    buscar = f1.text_input("Buscar", placeholder="Buscar por asunto, cuenta, documento, supervisor o ID", label_visibility="collapsed",
                           key=f"{prefijo}_q", on_change=reiniciar_pag)
    estado = f2.selectbox("Estado", FILTRO_ESTADO, label_visibility="collapsed", key=f"{prefijo}_estado", on_change=reiniciar_pag)
    cartera = f3.selectbox("Cartera", ["Todas"] + CARTERAS, label_visibility="collapsed", key=f"{prefijo}_cartera",
                           format_func=lambda x: "Todas las carteras" if x == "Todas" else x, on_change=reiniciar_pag)
    orden = f4.selectbox("Orden", ["Más antiguas primero", "Más recientes primero"], label_visibility="collapsed",
                         key=f"{prefijo}_orden", on_change=reiniciar_pag)
    return buscar, estado, cartera, orden


@st.fragment(run_every="5s")
def pagina_inicio(u):
    if not acceso_vigente(u):
        return
    st.caption("● Actualización automática cada 5 segundos")
    df = db.tickets_df()
    if df.empty:
        st.info("No hay solicitudes todavía. Importa tu Excel con `python src/importar_excel.py` o crea una en «Nueva solicitud».")
        return
    df["dias"] = dias_abierto(df)
    cab = st.container()                      # se completa abajo, cuando ya están los filtros (el botón Exportar necesita la lista filtrada)
    st.markdown(kpis_html(df, ("Total de solicitudes", "Por atender", "En verificación", "Respondidas")), unsafe_allow_html=True)
    v = filtrar(df, *barra_filtros("bo"))
    with cab:
        a, b, c = st.columns([7, 1.4, 2.3], vertical_alignment="center")
        a.markdown('<h1 class="h1">Solicitudes</h1>', unsafe_allow_html=True)
        b.download_button("Exportar", exportar(v), "solicitudes.csv", "text/csv", key="exp_bo")
        c.button("＋ Nueva solicitud", type="primary", key="btn_nueva", on_click=cambiar_pagina, args=("➕ Nueva solicitud",))
    render_tabla(v, "bo", abrir_en_gestionar)


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
    st.caption("● Estado actualizado automáticamente cada 5 segundos")
    if st.session_state.get("ver_ticket"):
        detalle_supervisor(u, st.session_state["ver_ticket"])
        return
    df = db.tickets_df(u["id"])          # siempre filtrado por el supervisor que inició sesión
    if df.empty:
        titulo_pagina("Mis solicitudes")
        st.info("Todavía no tienes solicitudes. Crea la primera con el botón «Nueva solicitud».")
        st.button("＋ Nueva solicitud", type="primary", key="btn_nueva", on_click=cambiar_pagina, args=("➕ Nueva solicitud",))
        return
    df["dias"] = dias_abierto(df)
    a, c = st.columns([8, 2.3], vertical_alignment="center")
    a.markdown('<h1 class="h1">Mis solicitudes</h1>', unsafe_allow_html=True)
    c.button("＋ Nueva solicitud", type="primary", key="btn_nueva", on_click=cambiar_pagina, args=("➕ Nueva solicitud",))
    st.markdown(kpis_html(df, ("Mis solicitudes", "Recibidas", "En verificación", "Respondidas")), unsafe_allow_html=True)
    v = filtrar(df, *barra_filtros("sup"))
    render_tabla(v, "sup", abrir_detalle)
    st.caption("Haz clic en una fila para ver la respuesta completa de la entidad.")


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
    actual = db.usuario_por_id(u["id"])
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
    st.caption("Los tickets se guardan aunque el correo esté desconectado. Los avisos quedan en cola. Aceptado por Microsoft o entregado a Outlook no confirma entrega al destinatario.")
    st.dataframe(cola, hide_index=True, width="stretch")
    revisar = cola[cola["estado"].isin(["revisar", "procesando"])]
    if not revisar.empty:
        elegido = st.selectbox("Envío que requiere revisión", revisar["id"].tolist())
        confirmado = st.checkbox("Revisé Enviados y Bandeja de salida: este correo no se envió ni está en cola en Outlook")
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
        st.button("Abrir ticket", on_click=ir_a, args=("🛠 Gestionar", r["tid"]))


def pagina_usuarios(u):
    titulo_pagina("Usuarios", "Los supervisores importados del Excel no tienen correo ni contraseña: asígnalos aquí para que puedan entrar.")
    df = db.usuarios_df()
    st.caption("ENTIDAD, CLIENTE y ASESORIA no son personas y quedaron inactivos.")
    mostrar = df.assign(rol=df["rol"].map({"supervisor": "Supervisor", "backoffice": "Back office"}),
                        activo=df["activo"].map({1: "Sí", 0: "No"}), con_clave=df["con_clave"].map({1: "Sí", 0: "No"}))
    st.dataframe(mostrar.rename(columns={"nombre": "Nombre", "correo": "Correo", "rol": "Rol", "activo": "Activo",
                                         "con_clave": "Puede entrar", "tickets": "Tickets"}).drop(columns="id"),
                 hide_index=True, width="stretch")
    nuevo = "➕ Nuevo usuario"
    elegido = st.selectbox("Editar", [nuevo] + df["nombre"].tolist())
    fila = None if elegido == nuevo else df[df["nombre"] == elegido].iloc[0]
    with st.form(f"usuario_{elegido}"):
        c1, c2 = st.columns(2)
        nombre = c1.text_input("Nombre (igual que en la columna SOLICITUD)", value="" if fila is None else fila["nombre"])
        correo = c2.text_input("Correo", value="" if fila is None or pd.isna(fila["correo"]) else fila["correo"])
        rol = c1.selectbox("Rol", ["supervisor", "backoffice"], index=0 if fila is None or fila["rol"] == "supervisor" else 1)
        activo = c2.checkbox("Activo", value=True if fila is None else bool(fila["activo"]))
        clave = st.text_input("Contraseña nueva (déjala vacía para no cambiarla)", type="password")
        if st.form_submit_button("Guardar usuario", type="primary"):
            if not nombre.strip():
                st.error("El nombre es obligatorio.")
            elif correo.strip() and not re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", correo.strip()):
                st.error("El correo no es válido.")
            elif clave and len(clave) < 8:
                st.error("La contraseña debe tener al menos 8 caracteres.")
            elif fila is not None and int(fila["id"]) == u["id"] and (rol != "backoffice" or not activo):
                st.error("No puedes quitarte tu propio acceso de back office.")
            else:
                try:
                    if fila is None:
                        db.crear_usuario(nombre, correo, rol, clave or None, int(activo))
                    else:
                        db.actualizar_usuario(int(fila["id"]), nombre, correo, rol, activo, clave or None)
                    st.toast("Usuario guardado")
                    st.rerun()
                except sqlite3.IntegrityError:
                    st.error("Ya existe un usuario con ese nombre o correo.")


# ---------- aplicación ----------
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

with st.sidebar:                                      # barra angosta: solo íconos, el nombre aparece al pasar el mouse
    st.markdown(logo_y(), unsafe_allow_html=True)
    for i, p in enumerate(paginas):
        icono, titulo = NAV_INFO[p]
        with st.container(key=f"nav_{i}"):
            st.markdown(nav_item(icono, titulo, p == pagina), unsafe_allow_html=True)
            st.button("Ir", key=f"navb_{i}", on_click=cambiar_pagina, args=(p,))
    with st.container(key="nav_salir"):
        st.markdown(nav_item("salir", "Cerrar sesión"), unsafe_allow_html=True)
        st.button("Salir", key="navb_salir", on_click=cerrar_sesion)

st.markdown(cabecera(NAV_INFO[pagina][1], usuario["nombre"], "Back office" if usuario["rol"] == "backoffice" else "Supervisor"), unsafe_allow_html=True)
{"📋 Mis solicitudes": pagina_mis_solicitudes, "➕ Nueva solicitud": pagina_nueva, "🏠 Inicio": pagina_inicio,
 "🛠 Gestionar": pagina_gestionar, "📬 Correo": pagina_buzon, "📧 Prueba de correo": pagina_correo, "👥 Usuarios": pagina_usuarios}[pagina](usuario)
