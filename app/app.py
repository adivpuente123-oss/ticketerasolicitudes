"""Dashboard de gestión de solicitudes y alícuotas (Streamlit)."""
import sys
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
from config import (CARTERAS, CORTES_RANKING, DIAS_ALERTA_PENDIENTE, NO_SUPERVISORES,
                    REFRESCO_SEGUNDOS, RUTA_EXCEL)
from calidad import revisar
from datos import cargar_todo
from estilos import (AMARILLO, AZUL, CSS, CYAN, FONDO, GRIS, NARANJA, ROJO, VERDE, anillo, area, avatares, barras_finas,
                     capsula, curvas, encabezado, fila_fichas, fila_kpis, fila_progreso, leyenda, lineas_alicuota,
                     lista_top, rgba, waffle)

st.set_page_config(page_title="Gestión de solicitudes", page_icon="📊", layout="wide")
st.markdown(CSS, unsafe_allow_html=True)

try:  # revisa el Excel cada cierto tiempo sin que nadie presione F5
    from streamlit_autorefresh import st_autorefresh
    st_autorefresh(interval=REFRESCO_SEGUNDOS * 1000, key="auto")
except ImportError:
    pass

MESES = ["Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio", "Julio", "Agosto",
         "Setiembre", "Octubre", "Noviembre", "Diciembre"]
C_ESTADO = {"Respondida": AZUL, "Enviada sin respuesta": AMARILLO, "Por enviar": CYAN}
C_CONCL = {"PROCEDENTE": VERDE, "IMPROCEDENTE": ROJO, "SIN CONCLUSIÓN": GRIS}
C_ALIC = {"Alícuota": VERDE, "Posible alícuota": AMARILLO, "No aplica": CYAN, "Sin dato": GRIS}
C_CAT = {"Alícuota": VERDE, "Posible alícuota": AMARILLO, "No aplica": CYAN, "Sin dato": GRIS}
NOMBRE_CAT = {"Alícuota": "Alícuota confirmada", "Posible alícuota": "Posible alícuota", "No aplica": "No corresponde", "Sin dato": "Sin dato"}
C_PAGO = {"Pagado": VERDE, "Sin sustento de pago": ROJO, "Sin dato": GRIS}
NAV = ["🏠 Resumen", "🏆 Ranking", "📋 Solicitudes", "💰 Alícuotas", "⏳ Pendientes", "🤝 Acuerdos de pago", "🧹 Calidad de datos"]
MES_CORTO = ["ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "set", "oct", "nov", "dic"]
_n = [0]


# ---------- utilidades de presentación ----------
def moneda(x) -> str:
    return f"S/ {x:,.0f}"


def metricas(items):
    for c, (etiqueta, valor) in zip(st.columns(len(items)), items):
        c.metric(etiqueta, f"{int(valor):,}" if isinstance(valor, (int, np.integer)) else valor)


def tarjeta():
    """Caja blanca con esquinas redondeadas (el estilo está en estilos.py)."""
    _n[0] += 1
    return st.container(key=f"card_{_n[0]}")


def estilo_fig(fig, alto=320):
    """Estilo oscuro común y globo amarillo al pasar el mouse."""
    fig.update_layout(height=alto, margin=dict(l=4, r=4, t=46, b=4), legend_title_text="",
                      paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                      font=dict(color="#ffffff", size=13), title=dict(x=0.01, font=dict(size=16)),
                      legend=dict(orientation="h", y=-0.2, font=dict(size=13)),
                      hoverlabel=dict(bgcolor=AMARILLO, bordercolor=AMARILLO, font=dict(color=FONDO, size=13), align="left"))
    fig.update_xaxes(gridcolor="#3a3c70", zerolinecolor="#3a3c70")
    fig.update_yaxes(gridcolor="#3a3c70", zerolinecolor="#3a3c70")
    return fig


def mostrar(fig, alto=320):
    st.plotly_chart(estilo_fig(fig, alto), width="stretch", config={"displayModeBar": False})


def grafico(fig, alto=320):
    with tarjeta():
        mostrar(fig, alto)


def tabla(df, **kw):
    with tarjeta():
        st.dataframe(df, hide_index=True, width="stretch", **kw)


def apilado(df, eje, color, mapa, titulo, horizontal=False):
    t = df.groupby([eje, color]).size().reset_index(name="n")
    return px.bar(t, x="n" if horizontal else eje, y=eje if horizontal else "n", color=color,
                  color_discrete_map=mapa, orientation="h" if horizontal else "v",
                  title=titulo, text_auto=True, labels={"n": "Solicitudes"})


def barras(t, x, y, titulo, color=AZUL, horizontal=True):
    fig = px.bar(t, x=y if horizontal else x, y=x if horizontal else y, title=titulo,
                 orientation="h" if horizontal else "v", text_auto=".3s")
    fig.update_traces(marker_color=color)
    return fig


# ---------- datos ----------
if not RUTA_EXCEL.exists():
    st.error(f"No encuentro el Excel en: {RUTA_EXCEL}")
    st.info("Copia tu archivo ahí con ese nombre, o cambia RUTA_EXCEL en src/config.py.")
    st.stop()

modificado = RUTA_EXCEL.stat().st_mtime  # cambia cada vez que guardas el Excel


@st.cache_data(show_spinner="Leyendo el Excel...")
def datos(ruta: str, modificado: float):
    return cargar_todo(Path(ruta))


try:
    sol, ali, acu = datos(str(RUTA_EXCEL), modificado)
except Exception as e:  # noqa: BLE001
    st.error(f"No pude leer el Excel: {e}")
    st.stop()

# ---------- barra lateral ----------
with st.sidebar:
    st.markdown('<div class="logo"><b>◎</b><span>Gestión de<br>solicitudes</span></div>', unsafe_allow_html=True)
    anios = ["Todos"] + sorted(sol["anio"].dropna().astype(int).unique().tolist())
    anio = st.selectbox("Año", anios, key="anio")
    mes = st.selectbox("Mes", list(range(0, 13)), key="mes",
                       format_func=lambda m: "Todos" if m == 0 else MESES[m - 1])
    anio_ef = anio
    if mes != 0 and anio == "Todos":
        con_datos = sol.loc[sol["mes"] == mes, "anio"].dropna()
        if not con_datos.empty:
            anio_ef = int(con_datos.max())
            st.caption(f"Año aplicado: {anio_ef}, el más reciente con datos de {MESES[mes - 1].lower()}.")
    cartera = st.radio("Cartera", ["Todas"] + CARTERAS, horizontal=True, key="cartera")
    supervisores = ["Todos"] + sorted(sol["supervisor"].unique())
    supervisor = st.selectbox("Supervisor", supervisores, key="supervisor")
    st.divider()
    pagina = st.radio("Espacio de análisis", NAV, key="pagina")
    if st.button("Actualizar ahora"):
        st.cache_data.clear()
        st.rerun()

f = sol
if anio_ef != "Todos":
    f = f[f["anio"] == anio_ef]
if mes != 0:
    f = f[f["mes"] == mes]
if cartera != "Todas":
    f = f[f["cartera"] == cartera]
if supervisor != "Todos":
    f = f[f["supervisor"] == supervisor]


# ---------- páginas ----------
def delta_texto(act, ant, sube_bien, ref, prev):
    """Texto ▲▼ comparando el mes de referencia con el anterior. sube_bien: True, False o None (neutro)."""
    if ant == 0:
        return None
    d = (act - ant) / ant * 100
    clase = "n" if sube_bien is None else ("ok" if (d >= 0) == sube_bien else "mal")
    parcial = " (mes en curso)" if ref == pd.Period(datetime.now(), "M") else ""
    return (f"{'▲' if d >= 0 else '▼'} {abs(d):.0f}% vs {MES_CORTO[prev.month - 1]}{parcial}", clase)


def comparacion_mensual():
    """Cuenta solicitudes, sin respuesta y procedentes del mes de referencia y del anterior (respeta cartera y supervisor)."""
    g = sol if cartera == "Todas" else sol[sol["cartera"] == cartera]
    if supervisor != "Todos":
        g = g[g["supervisor"] == supervisor]
    g = g.dropna(subset=["fecha_solicitud"])
    if g.empty:
        return None
    per = g["fecha_solicitud"].dt.to_period("M")
    ref = pd.Period(f"{anio_ef}-{mes:02d}") if anio_ef != "Todos" and mes != 0 else per.max()
    prev = ref - 1
    cuenta = lambda p, c=None: int((per == p).sum() if c is None else g.loc[per == p, c].sum())
    return ref, prev, {k: (cuenta(ref, c), cuenta(prev, c)) for k, c in
                       (("n", None), ("sr", "es_sin_resp"), ("pro", "es_proc"))}


def fig_dinero(a):
    t = a.groupby("cartera")[["alicuota_calculada", "pagado_entidad", "por_recuperar"]].sum().reset_index()
    t = t.melt(id_vars="cartera", var_name="concepto", value_name="soles")
    t["concepto"] = t["concepto"].map({"alicuota_calculada": "Calculada", "pagado_entidad": "Pagada", "por_recuperar": "Por recuperar"})
    return px.bar(t, x="cartera", y="soles", color="concepto", barmode="group", text_auto=".3s",
                  color_discrete_map={"Calculada": AZUL, "Pagada": VERDE, "Por recuperar": NARANJA},
                  title="Alícuota por cartera: calculada, pagada y por recuperar (S/)", labels={"soles": "S/", "cartera": ""})


AVATAR_COL = [CYAN, AMARILLO, "#c9ccd8", "#f78fb3", "#b5a8ff"]


def etiqueta_mes(periodo: str) -> str:
    anio_, mes_ = periodo.split("-")
    return f"{MES_CORTO[int(mes_) - 1]} {anio_[2:]}"


DIAS = ["lun", "mar", "mié", "jue", "vie", "sáb", "dom"]


def resumen_por(base, clave):
    """Cuenta solicitudes y estados por mes o por día."""
    return base.groupby(clave).agg(n=("estado", "size"), res=("es_respondida", "sum"), sr=("es_sin_resp", "sum"),
                                   pe=("es_por_enviar", "sum"), pro=("es_proc", "sum"), imp=("es_improc", "sum"))


def serie_diaria(base):
    """Todos los días del mes elegido (hasta hoy si es el mes en curso), con ceros donde no hubo solicitudes."""
    inicio = pd.Timestamp(int(anio_ef), mes, 1)
    fin = min(inicio + pd.offsets.MonthEnd(0), pd.Timestamp.today().normalize())
    dias = pd.date_range(inicio, max(fin, inicio))
    g = resumen_por(base, base["fecha_solicitud"].dt.normalize()).reindex(dias, fill_value=0).astype(int)
    return g, [f"{DIAS[d.weekday()]} {d.day} {MES_CORTO[d.month - 1]}" for d in dias], [str(d.day) for d in dias]


def fig_solicitudes(g, titulos, ticks):
    """Segmento 4: área suave con información de cada punto al pasar el mouse."""
    x = list(range(len(g)))
    pct = [round(r / n * 100) if n else 0 for r, n in zip(g["res"], g["n"])]
    custom = [[t, int(r), int(s), int(p), int(c), int(i), q] for t, r, s, p, c, i, q in
              zip(titulos, g["res"], g["sr"], g["pe"], g["pro"], g["imp"], pct)]
    fig = go.Figure(go.Scatter(
        x=x, y=g["n"].tolist(), mode="lines+markers", line=dict(color=AZUL, width=3, shape="spline"),
        marker=dict(size=7, color=AZUL, line=dict(color="#fff", width=1.5)), fill="tozeroy", fillcolor=rgba(AZUL, 0.22),
        customdata=custom,
        hovertemplate=("<b>%{customdata[0]}</b><br>Solicitudes: <b>%{y}</b><br>Respondidas: %{customdata[1]} (%{customdata[6]}%)"
                       "<br>Sin respuesta: %{customdata[2]}<br>Por enviar: %{customdata[3]}"
                       "<br>Procedentes: %{customdata[4]}<br>Improcedentes: %{customdata[5]}<extra></extra>")))
    paso = max(1, -(-len(g) // 8))
    fig.update_xaxes(tickvals=x[::paso], ticktext=ticks[::paso], showgrid=False)
    fig.update_yaxes(rangemode="tozero")
    fig.update_layout(hovermode="x", showlegend=False)
    return fig


def fig_pagos(pagos):
    """Segmento 6: barras finas con información de cada mes al pasar el mouse."""
    g = pagos.groupby(pagos["fecha_pago"].dt.to_period("M")).agg(
        monto=("pagado_entidad", "sum"), n=("pagado_entidad", "size"), calc=("alicuota_calculada", "sum")).tail(10)
    total = float(g["monto"].sum()) or 1.0
    etiquetas = [f"{MES_CORTO[p.month - 1]} {str(p.year)[2:]}" for p in g.index]
    custom = [[e, int(n), m / n if n else 0, m / total * 100, c, m / c * 100 if c else 0]
              for e, n, m, c in zip(etiquetas, g["n"], g["monto"], g["calc"])]
    x = list(range(len(g)))
    fig = go.Figure(go.Bar(
        x=x, y=g["monto"].tolist(), width=0.12, marker=dict(color=AZUL, cornerradius=3), customdata=custom,
        hovertemplate=("<b>%{customdata[0]}</b><br>Pagado: <b>S/ %{y:,.0f}</b><br>Registros pagados: %{customdata[1]}"
                       "<br>Promedio por registro: S/ %{customdata[2]:,.0f}<br>Del total pagado: %{customdata[3]:.1f}%"
                       "<br>Alícuota calculada de esos registros: S/ %{customdata[4]:,.0f}"
                       "<br>Cobrado sobre lo calculado: %{customdata[5]:.0f}%<extra></extra>")))
    i = int(np.argmax(g["monto"].values))
    fig.add_annotation(x=i, y=float(g["monto"].iloc[i]), text=f"<b>{moneda(g['monto'].iloc[i])}</b>", showarrow=False,
                       yshift=20, bgcolor=AMARILLO, font=dict(color=FONDO, size=13), borderpad=4)
    fig.update_xaxes(tickvals=x, ticktext=etiquetas, showgrid=False)
    fig.update_yaxes(rangemode="tozero")
    fig.update_layout(hovermode="x", showlegend=False, bargap=0.3)
    return fig


def fig_cobrado(a):
    """Segmento 7: anillo con información de cada parte al pasar el mouse."""
    calc, pag = a["alicuota_calculada"].sum(), a["pagado_entidad"].sum()
    falta, por = max(calc - pag, 0.0), a["por_recuperar"].sum()
    p = round(pag / calc * 100) if calc else 0
    textos = [[f"<b>Pagada</b><br>{moneda(pag)} ({p}% de lo calculado)<br>{int((a['pagado_entidad'] > 0).sum())} registros con pago"
               f"<br>Alícuota calculada: {moneda(calc)}"],
              [f"<b>Falta por cobrar</b><br>{moneda(falta)} (calculada menos pagada)"
               f"<br>Por recuperar sumando solo los saldos: {moneda(por)}<br>{int((a['por_recuperar'] > 0).sum())} registros con saldo"]]
    fig = go.Figure(go.Pie(labels=["Pagada", "Falta por cobrar"], values=[pag, falta], hole=0.74, sort=False,
                           direction="clockwise", marker=dict(colors=[AMARILLO, "#c9ccd8"], line=dict(width=0)),
                           textinfo="none", showlegend=False, customdata=textos, hovertemplate="%{customdata[0]}<extra></extra>"))
    fig.add_annotation(text=f"<b>{p}%</b>", x=0.5, y=0.5, showarrow=False, font=dict(size=32, color="#ffffff"))
    fig.update_layout(title_text="")
    return fig


def pagina_resumen():
    n, res = len(f), int(f["es_respondida"].sum())
    env, pro = int(f["fecha_envio"].notna().sum()), int(f["es_proc"].sum())
    pct = lambda a, b: round(a / b * 100) if b else 0
    cm = comparacion_mensual()
    d = delta_texto(*cm[2]["n"], None, cm[0], cm[1]) if cm else None
    con_fecha = f.dropna(subset=["fecha_solicitud"])
    por_dias = mes != 0 and not con_fecha.empty
    if por_dias:
        mensual, tit_dias, tick_dias = serie_diaria(con_fecha)
    else:
        mensual = resumen_por(f.dropna(subset=["periodo"]), "periodo").sort_index()
    pers = f[~f["supervisor"].isin(NO_SUPERVISORES)]

    c1, c2, c3 = st.columns(3)
    with c1, tarjeta():
        top = pers["supervisor"].value_counts().head(5)
        st.markdown(f'<div class="ct">Solicitudes</div>{avatares(list(top.index), AVATAR_COL)}'
                    f'<div class="big">{n:,}</div><div class="mt">Solicitudes registradas</div>'
                    f'<div class="ac">{pct(res, n)}% ya fueron respondidas por la entidad</div>'
                    f'<div class="mt">{pro:,} procedentes (positivas) y {int(f["es_improc"].sum()):,} improcedentes (negativas)</div>', unsafe_allow_html=True)
    with c2, tarjeta():
        if mensual.empty:
            st.markdown('<div class="ct">Solicitudes del mes</div><div class="mt">Sin fechas de solicitud con estos filtros.</div>', unsafe_allow_html=True)
        else:
            mes_nom = MESES[mes - 1] if por_dias else MESES[int(mensual.index[-1][5:7]) - 1]
            total_mes = int(mensual["n"].sum()) if por_dias else int(mensual["n"].iloc[-1])
            dl = f'<div class="dl {d[1]}">{d[0]}</div>' if d else ""
            if por_dias:
                mejor = int(np.argmax(mensual["n"].values))
                nota = (f'Por día. Azul: solicitudes. Amarillo: respondidas.<br>Día con más solicitudes: '
                        f'{tit_dias[mejor]} ({int(mensual["n"].iloc[mejor])})')
                series = [mensual["n"].tolist(), mensual["res"].tolist()]
            else:
                nota = "Azul: solicitudes. Amarillo: respondidas."
                series = [mensual["n"].tail(9).tolist(), mensual["res"].tail(9).tolist()]
            st.markdown(f'<div class="ct">Solicitudes de {mes_nom.lower()}</div><div class="big">{total_mes:,}</div>{dl}'
                        + curvas(series, [AZUL, AMARILLO]) + f'<div class="mt">{nota}</div>', unsafe_allow_html=True)
    with c3, tarjeta():
        pend = pers[pers["es_sin_resp"] | pers["es_por_enviar"]]["supervisor"].value_counts().head(5)
        cuerpo = lista_top([(k, int(v)) for k, v in pend.items()], [AZUL, CYAN, AMARILLO, GRIS, GRIS]) if len(pend) else '<div class="mt">No hay pendientes.</div>'
        st.markdown('<div class="ct">Top 5 con más pendientes</div>' + cuerpo, unsafe_allow_html=True)

    ca, cb = st.columns([2, 1])
    with ca, tarjeta():
        if por_dias:
            st.markdown(f'<div class="ct">Solicitudes por día en {MESES[mes - 1].lower()} {anio_ef}</div>', unsafe_allow_html=True)
            mostrar(fig_solicitudes(mensual, tit_dias, tick_dias), 300)
        else:
            st.markdown('<div class="ct">Solicitudes por mes</div>', unsafe_allow_html=True)
            if len(mensual) >= 2:
                etiquetas = [etiqueta_mes(p) for p in mensual.index]
                mostrar(fig_solicitudes(mensual, etiquetas, etiquetas), 300)
            else:
                st.caption("Con estos filtros hay un solo mes con datos.")
        st.caption("Pasa el mouse sobre la curva para ver el detalle de cada punto.")
    with cb, tarjeta():
        cat = f.groupby("estado_corresponde").agg(t=("estado", "size"), r=("es_respondida", "sum"))
        filas = [(NOMBRE_CAT[c], int(cat.loc[c, "t"]), int(cat.loc[c, "r"]), col)
                 for c, col in (("Alícuota", AZUL), ("Posible alícuota", AMARILLO), ("No aplica", CYAN)) if c in cat.index]
        st.markdown('<div class="ct">Alícuotas</div>' + lineas_alicuota(filas), unsafe_allow_html=True)

    a = ali if cartera == "Todas" else ali[ali["cartera"] == cartera]
    pagos = a[a["fecha_pago"].notna()]
    cc, cd = st.columns([2, 1])
    with cc, tarjeta():
        st.markdown('<div class="ct">Pagos de alícuotas por mes</div>', unsafe_allow_html=True)
        if pagos.empty:
            st.caption("No hay pagos con fecha en esta cartera.")
        else:
            mostrar(fig_pagos(pagos), 300)
            st.caption("Pasa el mouse sobre cada mes para ver el detalle de los pagos.")
    with cd, tarjeta():
        st.markdown('<div class="ct">Cobrado</div>', unsafe_allow_html=True)
        if a.empty:
            st.caption("No hay registros de alícuota en esta cartera.")
        else:
            mostrar(fig_cobrado(a), 250)
            calc, pag = a["alicuota_calculada"].sum(), a["pagado_entidad"].sum()
            st.markdown(f'<div class="mt" style="text-align:center">{moneda(pag)} de {moneda(calc)}</div>'
                        f'<div class="mt" style="text-align:center"><span class="dt" style="background:{AMARILLO}"></span>Pagada'
                        f' <span class="dt" style="background:#c9ccd8;margin-left:12px"></span>Falta por cobrar</div>', unsafe_allow_html=True)

    c4, c5 = st.columns(2)
    with c4:
        fig = go.Figure(go.Funnel(y=["Solicitudes", "Enviadas", "Respondidas", "Procedentes"], x=[n, env, res, pro],
                                  textinfo="value+percent initial", marker={"color": [AZUL, CYAN, AMARILLO, VERDE]}))
        fig.update_layout(title_text="Embudo de gestión (% sobre el total de solicitudes)")
        grafico(fig, 340)
    with c5:
        grafico(fig_dinero(a), 340)


def pagina_calidad():
    st.caption("Revisa el Excel completo (sin filtros) y te dice en qué hoja y fila corregir cada observación. No incluye nombres ni documentos.")
    resumen, detalle, puntaje, total = revisar(sol, ali, acu)
    graves = int(resumen.loc[resumen["Gravedad"] == "Alta", "Cantidad"].sum())
    medias = int(resumen.loc[resumen["Gravedad"] == "Media", "Cantidad"].sum())
    color = VERDE if puntaje >= 95 else AMARILLO if puntaje >= 85 else ROJO
    st.markdown(fila_kpis([
        ("Calidad de los datos", f"{puntaje}%", puntaje, f"{total:,} filas revisadas en 5 hojas", color),
        ("Observaciones altas", f"{graves}", min(100, graves), "Cambian los números: corregir primero", ROJO),
        ("Observaciones medias", f"{medias}", min(100, medias), "Conviene revisarlas", AMARILLO),
    ]), unsafe_allow_html=True)
    resumen = resumen.assign(Estado=resumen["Cantidad"].map(lambda x: "✓ Sin observaciones" if x == 0 else "Revisar"),
                             _o=resumen["Gravedad"].map({"Alta": 0, "Media": 1, "Info": 2}))
    resumen = resumen.sort_values(["_o", "Cantidad"], ascending=[True, False]).drop(columns="_o")
    st.subheader("Revisiones")
    tabla(resumen[["Gravedad", "Revisión", "Dónde corregirlo", "Cantidad", "Estado"]])
    st.subheader("Detalle: hoja y fila del Excel")
    problemas = ["Todos"] + sorted(detalle["Problema"].unique())
    elegido = st.selectbox("Mostrar", problemas, key="problema")
    vista = detalle if elegido == "Todos" else detalle[detalle["Problema"] == elegido]
    vista = vista.assign(_o=vista["Gravedad"].map({"Alta": 0, "Media": 1, "Info": 2})).sort_values(["_o", "Hoja", "Fila Excel"]).drop(columns="_o")
    tabla(vista.head(300))
    st.download_button("Descargar la lista (CSV)", vista.to_csv(index=False).encode("utf-8-sig"), "calidad_de_datos.csv", "text/csv")


def tabla_ranking(df, **kw):
    tabla(df, **kw)


def pagina_ranking():
    g = f.groupby("supervisor").agg(
        total=("estado", "size"), respondidas=("es_respondida", "sum"), sin_respuesta=("es_sin_resp", "sum"),
        por_enviar=("es_por_enviar", "sum"), procedentes=("es_proc", "sum"),
        improcedentes=("es_improc", "sum"), dk=("dk", "sum")).reset_index()
    g["pct"] = (g["respondidas"] / g["total"] * 100).round(0)
    pers = g[~g["supervisor"].isin(NO_SUPERVISORES)].sort_values(["pct", "total"], ascending=False)

    concluidas = int(f["es_proc"].sum() + f["es_improc"].sum())
    metricas([("Solicitudes", len(f)), ("Respondidas", int(f["es_respondida"].sum())),
              ("Sin respuesta", int(f["es_sin_resp"].sum())), ("Por enviar", int(f["es_por_enviar"].sum())),
              ("Procedencia", f"{(f['es_proc'].sum() / concluidas * 100 if concluidas else 0):.0f}%"),
              ("Deuda (DK)", moneda(f["dk"].sum()))])

    a, b, c = CORTES_RANKING
    niveles = [(f"{a}% o más", VERDE), (f"{b}% a {a - 1}%", AMARILLO),
               (f"{c}% a {b - 1}%", NARANJA), (f"Menos de {c}%", ROJO)]
    pers = pers.assign(nivel=pers["pct"].map(lambda p: 0 if p >= a else 1 if p >= b else 2 if p >= c else 3))
    st.write("")
    for k, (col, (etiqueta, color)) in enumerate(zip(st.columns(4), niveles)):
        sub = pers[pers["nivel"] == k]
        with col:
            st.markdown(f"<div style='background:{color};color:#17183a;padding:10px;border-radius:8px;"
                        f"text-align:center;font-weight:700'>{etiqueta}</div>", unsafe_allow_html=True)
            st.metric("Supervisores", len(sub))
            st.caption(", ".join(f"{r.supervisor} {r.pct:.0f}%" for r in sub.itertuples()) or "Ninguno")

    st.subheader("Detalle por supervisor")
    st.caption("ENTIDAD, CLIENTE, ASESORIA y SIN ASIGNAR no se rankean porque no son supervisores.")
    tabla = pers.drop(columns="nivel").rename(columns={
        "supervisor": "Supervisor", "total": "Total", "respondidas": "Respondidas", "pct": "% respondido",
        "sin_respuesta": "Sin respuesta", "por_enviar": "Por enviar", "procedentes": "Procedentes",
        "improcedentes": "Improcedentes", "dk": "Deuda DK"})
    tabla_ranking(tabla, column_config={
        "% respondido": st.column_config.ProgressColumn("% respondido", min_value=0, max_value=100, format="%d%%"),
        "Deuda DK": st.column_config.NumberColumn(format="S/ %.0f")})


def pagina_solicitudes():
    metricas([("Total", len(f)), ("Respondidas", int(f["es_respondida"].sum())),
              ("Enviadas", int(f["fecha_envio"].notna().sum())), ("Sin respuesta", int(f["es_sin_resp"].sum())),
              ("Por enviar", int(f["es_por_enviar"].sum())), ("Procedentes", int(f["es_proc"].sum())),
              ("Improcedentes", int(f["es_improc"].sum()))])
    c1, c2 = st.columns(2)
    with c1:
        grafico(apilado(f, "cartera", "estado", C_ESTADO, "Estado por cartera", True))
    with c2:
        grafico(apilado(f, "cartera", "conclusion", C_CONCL, "Conclusión por cartera", True))
    c3, c4 = st.columns(2)
    with c3:
        grafico(apilado(f, "cartera", "estado_corresponde", C_ALIC, "Estado corresponde por cartera", True))
    with c4:
        t = f["tipo_consulta"].value_counts().reset_index()
        t.columns = ["tipo", "n"]
        grafico(barras(t.sort_values("n"), "tipo", "n", "Tipo de consulta"))
    grafico(apilado(f.dropna(subset=["periodo"]).sort_values("periodo"), "periodo", "estado", C_ESTADO,
                    "Solicitudes por mes (fecha de solicitud)"), 360)


def seccion_solicitudes_alicuota():
    st.subheader("Solicitudes: ¿corresponde alícuota?")
    st.caption("Según la columna ESTADO CORRESPONDE de las hojas IBK, BBVA y OTROS. Respeta año, mes, cartera y supervisor.")
    if f.empty:
        st.info("No hay solicitudes con estos filtros.")
        return
    cat = f.groupby("estado_corresponde").agg(total=("estado", "size"), respondidas=("es_respondida", "sum"))
    cats = [c for c in ["Alícuota", "Posible alícuota", "No aplica", "Sin dato"] if c in cat.index]
    res_total = int(f["es_respondida"].sum())
    fichas = [("Total de solicitudes", len(f), res_total, len(f) - res_total, AZUL)]
    for c in ["Alícuota", "Posible alícuota", "No aplica"]:
        n, r = (int(cat.loc[c, "total"]), int(cat.loc[c, "respondidas"])) if c in cat.index else (0, 0)
        fichas.append((NOMBRE_CAT[c], n, r, n - r, C_CAT[c]))
    st.markdown(fila_fichas(fichas), unsafe_allow_html=True)
    if "Sin dato" in cat.index:
        st.caption(f"{int(cat.loc['Sin dato', 'total'])} solicitudes no tienen dato en ESTADO CORRESPONDE.")

    estados = ["Respondida", "Enviada sin respuesta", "Por enviar"]
    etiquetas = ([f"Solicitudes {len(f)}"] + [f"{NOMBRE_CAT[c]} {int(cat.loc[c, 'total'])}" for c in cats]
                 + [f"{e} {int((f['estado'] == e).sum())}" for e in estados])
    colores = [AZUL] + [C_CAT[c] for c in cats] + [C_ESTADO[e] for e in estados]
    src, dst, val, col = [], [], [], []
    for i, c in enumerate(cats, start=1):
        src.append(0); dst.append(i); val.append(int(cat.loc[c, "total"])); col.append(rgba(C_CAT[c]))
        for j, e in enumerate(estados):
            n = int(((f["estado_corresponde"] == c) & (f["estado"] == e)).sum())
            if n:
                src.append(i); dst.append(1 + len(cats) + j); val.append(n); col.append(rgba(C_CAT[c]))
    fig = go.Figure(go.Sankey(arrangement="snap", node=dict(label=etiquetas, color=colores, pad=18, thickness=16),
                              link=dict(source=src, target=dst, value=val, color=col)))
    fig.update_layout(title_text="Río de solicitudes: si corresponde alícuota y en qué estado están", font=dict(size=14, color="#ffffff"))
    grafico(fig, 360)


def seccion_hoja_alicuota():
    a = ali if cartera == "Todas" else ali[ali["cartera"] == cartera]
    st.subheader("Hoja ALÍCUOTA: estado de la alícuota")
    st.caption("Filtra solo por cartera. Por recuperar = alícuota calculada (PAY_BD) menos lo pagado por la entidad (PAY_ENTIDAD), registro por registro y sin contar saldos a favor.")
    if a.empty:
        st.info("No hay registros de esta cartera en la hoja ALÍCUOTA.")
        return
    est = ["Pagado", "Sin sustento de pago", "Sin dato"]
    cuenta = a["estado_alicuota"].value_counts().reindex(est, fill_value=0)
    calc, pag, por = a["alicuota_calculada"].sum(), a["pagado_entidad"].sum(), a["por_recuperar"].sum()
    metricas([("Registros", len(a)), ("Pagados", int(cuenta["Pagado"])), ("Sin sustento de pago", int(cuenta["Sin sustento de pago"])),
              ("Sin dato", int(cuenta["Sin dato"])), ("Deuda (DK)", moneda(a["dk"].sum()))])
    c1, c2 = st.columns(2)
    with c1, tarjeta():
        st.markdown("**Estado de alícuota**")
        st.caption(f"{len(a):,} registros. Cada cuadro vale cerca de {len(a) / 100:.1f} registros.")
        izq, der = st.columns([1, 1.25])
        izq.markdown(waffle([(int(cuenta[e]), C_PAGO[e]) for e in est]), unsafe_allow_html=True)
        por_cartera = a.groupby(["cartera", "estado_alicuota"]).size().unstack(fill_value=0).reindex(columns=est, fill_value=0)
        der.markdown(leyenda([(C_PAGO[e], f"{int(cuenta[e]):,} {e.lower()} ({cuenta[e] / len(a) * 100:.0f}%)", "") for e in est]
                             + [("transparent", f"{c}: " + " / ".join(str(int(v)) for v in r), "") for c, r in por_cartera.iterrows()]),
                     unsafe_allow_html=True)
    with c2, tarjeta():
        pct = round(pag / calc * 100) if calc else 0
        fig = go.Figure(go.Indicator(mode="gauge+number", value=pct, number={"suffix": "%", "font": {"color": "#ffffff"}},
                                     title={"text": "Cobrado sobre lo calculado", "font": {"color": "#ffffff"}},
                                     gauge={"axis": {"range": [0, 100]}, "bar": {"color": VERDE}, "bgcolor": "#3a3c70"}))
        fig.update_layout(height=230, margin=dict(l=10, r=10, t=50, b=0), paper_bgcolor="rgba(0,0,0,0)")
        st.plotly_chart(fig, width="stretch")
        metricas([("Calculada", moneda(calc)), ("Pagada", moneda(pag)), ("Por recuperar", moneda(por))])
        pe = a.groupby("estado_alicuota")["por_recuperar"].sum().reindex(est, fill_value=0)
        st.markdown(capsula([(float(pe[e]), C_PAGO[e]) for e in est]) + leyenda(
            [(C_PAGO[e], f"{moneda(pe[e])} por recuperar en {e.lower()}", "") for e in est]), unsafe_allow_html=True)

    pagos = a[a["fecha_pago"].notna()]
    if not pagos.empty:
        g = pagos.groupby(pagos["fecha_pago"].dt.to_period("M")).agg(monto=("pagado_entidad", "sum"), n=("pagado_entidad", "size")).reset_index()
        g["mes"] = g["fecha_pago"].map(lambda p: f"{MES_CORTO[p.month - 1]} {str(p.year)[2:]}")
        fig = go.Figure()
        fig.add_bar(x=g["mes"], y=g["monto"], width=0.06, marker_color=VERDE, hoverinfo="skip")
        fig.add_scatter(x=g["mes"], y=g["monto"], mode="markers+text", customdata=g["n"],
                        marker=dict(size=(10 + 2.4 * np.sqrt(g["n"])).tolist(), color=VERDE, opacity=0.6, line=dict(color=VERDE, width=1.5)),
                        text=[moneda(m) if m > 600 else "" for m in g["monto"]], textposition="top center",
                        hovertemplate="%{x}<br>S/ %{y:,.0f}<br>%{customdata} registros<extra></extra>")
        fig.update_layout(title_text="Pagos por mes: la altura es el monto y el tamaño del círculo, la cantidad de registros", showlegend=False)
        fig.update_xaxes(categoryorder="array", categoryarray=g["mes"].tolist())
        grafico(fig, 340)

    c3, c4 = st.columns(2)
    with c3:
        z = pd.crosstab(a["blacklist"], a["estado_alicuota"]).reindex(
            index=["Alícuota", "Posible alícuota", "Otro o sin dato"], columns=est, fill_value=0)
        fig = go.Figure(go.Heatmap(z=z.values, x=est, y=z.index.tolist(), colorscale=[[0, "#2a2c5c"], [1, VERDE]],
                                   texttemplate="%{z}", showscale=False, xgap=3, ygap=3))
        fig.update_layout(title_text="Blacklist por estado de alícuota")
        fig.update_yaxes(autorange="reversed")
        grafico(fig, 300)
    with c4, tarjeta():
        st.markdown("**Origen de los registros**")
        origen = a["origen"].value_counts()
        pal = [AZUL, AMARILLO, CYAN, NARANJA, GRIS]
        st.markdown(capsula([(int(n), pal[i % 5]) for i, n in enumerate(origen)]) + leyenda(
            [(pal[i % 5], f"{o} {int(n):,} ({n / len(a) * 100:.0f}%)", "") for i, (o, n) in enumerate(origen.items())]), unsafe_allow_html=True)

    c5, c6 = st.columns(2)
    with c5:
        t = a.groupby("cosecha")["por_recuperar"].sum().nlargest(8).reset_index().sort_values("por_recuperar")
        grafico(barras(t, "cosecha", "por_recuperar", "Cosechas con más por recuperar (S/)", NARANJA))
    with c6:
        grafico(fig_dinero(a))
    st.subheader("Los 15 registros con más por recuperar")
    top = a.sort_values("por_recuperar", ascending=False).head(15)[
        ["cartera", "cuenta_oculta", "cosecha", "estado_alicuota", "alicuota_calculada", "pagado_entidad", "por_recuperar"]]
    tabla(top.rename(columns={"cartera": "Cartera", "cuenta_oculta": "Cuenta", "cosecha": "Cosecha", "estado_alicuota": "Estado",
                              "alicuota_calculada": "Calculada", "pagado_entidad": "Pagada", "por_recuperar": "Por recuperar"}),
          column_config={c: st.column_config.NumberColumn(format="S/ %.0f") for c in ("Calculada", "Pagada", "Por recuperar")})


def pagina_alicuotas():
    seccion_solicitudes_alicuota()
    seccion_hoja_alicuota()


def pagina_pendientes():
    sr, pe = f[f["es_sin_resp"]], f[f["es_por_enviar"]]
    metricas([("Enviadas sin respuesta", len(sr)),
              (f"Con más de {DIAS_ALERTA_PENDIENTE} días", int((sr["dias_pendiente"] > DIAS_ALERTA_PENDIENTE).sum())),
              ("Por enviar", len(pe)), ("Por enviar con más de 15 días", int((pe["dias_pendiente"] > 15).sum())),
              ("Deuda (DK) en espera", moneda(sr["dk"].sum()))])
    rangos, etiquetas = [-1, 15, 30, 60, 10**6], ["0 a 15 días", "16 a 30 días", "31 a 60 días", "Más de 60 días"]
    colores = dict(zip(etiquetas, [VERDE, AMARILLO, NARANJA, ROJO]))
    for col, df, titulo in zip(st.columns(2), (sr, pe), ("Enviadas sin respuesta: días desde el envío",
                                                          "Por enviar: días desde la solicitud")):
        t = pd.cut(df["dias_pendiente"], bins=rangos, labels=etiquetas).value_counts().reindex(etiquetas).reset_index()
        t.columns = ["rango", "n"]
        with col:
            grafico(px.bar(t, x="n", y="rango", color="rango", color_discrete_map=colores, orientation="h",
                           title=titulo, text_auto=True).update_layout(showlegend=False))
    st.subheader("Las 15 enviadas sin respuesta más antiguas")
    top = sr.sort_values("dias_pendiente", ascending=False).head(15)[
        ["supervisor", "cartera", "tipo_consulta", "cuenta_oculta", "fecha_envio", "dias_pendiente", "dk"]].copy()
    top["fecha_envio"] = top["fecha_envio"].dt.strftime("%d/%m/%Y")
    tabla(top.rename(columns={"supervisor": "Supervisor", "cartera": "Cartera", "tipo_consulta": "Tipo de consulta",
                                     "cuenta_oculta": "Cuenta", "fecha_envio": "Enviada", "dias_pendiente": "Días esperando",
                                     "dk": "Deuda DK"}),
          column_config={"Deuda DK": st.column_config.NumberColumn(format="S/ %.0f")})


def pagina_acuerdos():
    k = acu
    st.caption("Hoja CASOS (acuerdos de pago). No tiene cartera ni fecha de solicitud, así que los filtros no aplican.")
    pg, mo = k["total_pagado"].sum(), k["monto_acuerdo"].sum()
    metricas([("Acuerdos", len(k)), ("Monto acordado", moneda(mo)), ("Total pagado", moneda(pg)),
              ("Pendiente de pago", moneda(k["pendiente"].sum())), ("Cumplimiento", f"{(pg / mo * 100 if mo else 0):.0f}%"),
              ("En riesgo", int(k["en_riesgo"].sum()))])
    c1, c2 = st.columns(2)
    with c1:
        t = k.groupby("producto")["pendiente"].sum().reset_index().sort_values("pendiente")
        grafico(barras(t, "producto", "pendiente", "Pendiente de pago por producto"))
    with c2:
        tramos = pd.cut(k["cuotas_restantes"], bins=[-1, 0, 3, 8, 10**6],
                        labels=["Sin pendientes", "1 a 3 cuotas", "4 a 8 cuotas", "Más de 8 cuotas"]).value_counts().sort_index().reset_index()
        tramos.columns = ["tramo", "n"]
        grafico(barras(tramos, "tramo", "n", "Acuerdos según cuotas pendientes"))
    st.subheader("Acuerdos en riesgo")
    st.caption("Con cuotas pendientes y último pago hace más de 45 días. No se muestran nombres ni documentos.")
    r = k[k["en_riesgo"]].sort_values("pendiente", ascending=False).head(15)[
        ["producto", "plazo", "cuotas_pagadas", "cuotas_restantes", "pendiente", "ultimo_pago", "dias_sin_pago"]].copy()
    r["ultimo_pago"] = r["ultimo_pago"].dt.strftime("%d/%m/%Y")
    tabla(r.rename(columns={"producto": "Producto", "plazo": "Plazo", "cuotas_pagadas": "Cuotas pagadas",
                                   "cuotas_restantes": "Cuotas restantes", "pendiente": "Pendiente",
                                   "ultimo_pago": "Último pago", "dias_sin_pago": "Días sin pagar"}),
          column_config={"Pendiente": st.column_config.NumberColumn(format="S/ %.0f")})


hoy = datetime.now()
st.markdown(encabezado("Resumen general" if pagina == NAV[0] else pagina.split(" ", 1)[1], f"{hoy.day} {MES_CORTO[hoy.month - 1]} {hoy.year}",
                       f"{datetime.fromtimestamp(modificado):%d/%m/%Y %H:%M}"), unsafe_allow_html=True)
if f.empty and pagina not in ("💰 Alícuotas", "🤝 Acuerdos de pago", "🧹 Calidad de datos"):
    st.warning("No hay solicitudes con estos filtros. Prueba con otro mes, cartera o supervisor.")
else:
    dict(zip(NAV, [pagina_resumen, pagina_ranking, pagina_solicitudes, pagina_alicuotas,
                   pagina_pendientes, pagina_acuerdos, pagina_calidad]))[pagina]()
st.markdown(f'<div class="pie">Gestión de solicitudes y alícuotas. La página revisa el Excel cada {REFRESCO_SEGUNDOS} segundos.</div>',
            unsafe_allow_html=True)
