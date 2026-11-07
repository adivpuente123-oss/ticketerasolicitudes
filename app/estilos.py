"""Estilos del tablero (tema oscuro) y piezas HTML/SVG reutilizables."""
import math

AZUL, VERDE, AMARILLO, NARANJA, ROJO = "#5b63ff", "#3ecf8e", "#fbb629", "#ff9f43", "#ff5d6c"
CYAN, GRIS, TENUE = "#3cc7d9", "#6e7199", "#a3a7cf"
TARJETA, FONDO, REJILLA = "#22234d", "#17183a", "#3a3c70"

CSS = """<style>
.stApp{background:#17183a;color:#fff;font-size:15px}
[data-testid="stHeader"]{background:transparent}
.block-container{padding-top:1.4rem;padding-bottom:3rem;max-width:1500px}
[data-testid="stMarkdownContainer"] p,[data-testid="stCaptionContainer"]{line-height:1.65}
h2,h3{letter-spacing:.03em;margin-top:1.2rem}
.topbar{display:flex;align-items:center;gap:14px;margin:0 0 24px;flex-wrap:wrap}
.topbar .tt{font-size:24px;font-weight:600;letter-spacing:.03em}
.topbar .pill{background:#5b63ff;border-radius:20px;padding:6px 16px;font-size:13px;letter-spacing:.02em}
.topbar .pill.b{background:#2a2c5c;color:#c9ccf0}.topbar .sp{margin-left:auto}
[class*="st-key-card"]{background:#22234d;border-radius:14px;padding:22px 24px}
[data-testid="stMetric"]{background:#22234d;border-radius:12px;padding:16px 20px;border-bottom:3px solid #5b63ff}
[data-testid="stMetricLabel"] p{color:#a3a7cf;font-size:14px}[data-testid="stMetricValue"]{letter-spacing:.02em}
.ct{font-size:15px;font-weight:600;letter-spacing:.05em;margin:0 0 12px}
.big{font-size:40px;font-weight:600;letter-spacing:.03em;line-height:1.2}
.mt{color:#a3a7cf;font-size:14px;margin-top:6px;line-height:1.6}.ac{color:#8c93ff;font-size:14px;margin-top:6px}
.dl{font-size:13.5px;font-weight:600;margin-top:8px}.dl.ok{color:#3ecf8e}.dl.mal{color:#ff5d6c}.dl.n{color:#8c93ff}
.avs{display:flex;margin:4px 0 16px 6px}.avs span{width:36px;height:36px;border-radius:50%;display:flex;align-items:center;justify-content:center;font-size:13px;font-weight:600;color:#17183a;border:3px solid #22234d;margin-left:-8px}
.tp{display:grid;grid-template-columns:28px 1fr auto;gap:14px;align-items:center;margin-bottom:16px;font-size:14px}
.tp .n{width:26px;height:26px;border-radius:50%;border:2px solid;display:flex;align-items:center;justify-content:center;font-size:12.5px}.tp .l{height:5px;border-radius:3px}
.al{margin-bottom:20px}.al .r{display:flex;justify-content:space-between;font-size:14.5px}.al .l{height:5px;border-radius:3px;margin:9px 0 7px}
.dt{display:inline-block;width:13px;height:13px;border-radius:50%;border:2px solid #a3a7cf;vertical-align:-2px;margin-right:7px}
.krow{display:grid;grid-template-columns:repeat(3,1fr);gap:18px;margin-bottom:20px}
.kcard,.pcard,.ficha{background:#22234d;border-radius:14px}
.kcard{padding:18px 22px 20px;border-bottom:5px solid var(--c)}
.kcard .kt{font-weight:600;font-size:14.5px;margin-bottom:8px;letter-spacing:.03em}
.kcard .kb{display:flex;align-items:center;justify-content:space-between}
.kcard .kv{font-size:40px;font-weight:600;color:var(--c);line-height:1.15}.kcard .ks{color:#a3a7cf;font-size:13.5px;margin-top:6px;line-height:1.6}
.kcard .dl{margin-top:8px}
.ring{width:70px;height:70px;border-radius:50%;display:grid;place-items:center;flex:none}
.ring span{width:52px;height:52px;background:#22234d;border-radius:50%;display:grid;place-items:center;font-weight:600;font-size:16px}
.prow{display:grid;grid-template-columns:repeat(4,1fr);gap:18px;margin-bottom:20px}
.pcard{padding:16px 20px}.pcard .pt{display:flex;align-items:center;gap:14px}.pcard .pv{font-size:28px;font-weight:600}.pcard .pv small{font-size:14px;margin-left:2px}
.pcard .pb{flex:1;height:10px;background:#3a3c70;border-radius:6px;overflow:hidden}.pcard .pb i{display:block;height:100%;border-radius:6px}
.pcard .pn{font-size:13px;color:#a3a7cf;margin-top:8px;line-height:1.55}
.cap{display:flex;height:12px;border-radius:6px;overflow:hidden;gap:2px;margin:10px 0 8px}.cap i{display:block}
.fichas{display:grid;grid-template-columns:repeat(4,1fr);gap:18px;margin-bottom:20px}
.ficha{padding:18px 22px}.ficha .ft{font-size:14px;color:#a3a7cf;font-weight:600;letter-spacing:.02em}
.ficha .fv{font-size:40px;font-weight:600;color:var(--c);line-height:1.2}.ficha .fn{font-size:13.5px;color:#a3a7cf;line-height:1.6}
.wf{display:grid;grid-template-columns:repeat(10,1fr);gap:4px;max-width:230px}.wf i{display:block;aspect-ratio:1;border-radius:4px}
.lgd{font-size:14px;line-height:2}.lgd b{display:inline-block;width:12px;height:12px;border-radius:3px;margin-right:8px}.lgd small{color:#a3a7cf}
.pie{text-align:center;color:#a3a7cf;font-size:13px;margin-top:28px}
.logo{display:flex;align-items:center;gap:12px;font-weight:600;font-size:17px;line-height:1.3}
.logo b{width:36px;height:36px;border-radius:10px;background:#5b63ff;color:#fff;display:grid;place-items:center;flex:none}
.chip{display:inline-block;padding:3px 12px;border-radius:12px;font-size:12.5px;font-weight:600;white-space:nowrap}
.chip.rec{background:#2a2c5c;color:#c9ccf0}.chip.env{background:rgba(251,182,41,.18);color:#fbb629}.chip.res{background:rgba(91,99,255,.25);color:#b4b9ff}
.chip.pro{background:rgba(62,207,142,.18);color:#3ecf8e}.chip.imp{background:rgba(255,93,108,.18);color:#ff5d6c}
.tkc{background:#22234d;border-radius:14px;padding:18px 22px;margin-bottom:14px}
.tkc .th{display:flex;align-items:center;gap:10px;flex-wrap:wrap;margin-bottom:8px}.tkc .th b{font-size:16px;letter-spacing:.03em}
.tkc .tm{color:#a3a7cf;font-size:13.5px;line-height:1.7}.tkc .tr{margin-top:10px;padding-top:10px;border-top:1px solid #3a3c70;font-size:14.5px;line-height:1.65}
.tkc .tr small{display:block;color:#a3a7cf;font-size:12.5px;margin-bottom:2px}
.hist{border-left:2px solid #3a3c70;padding-left:14px;margin:6px 0 10px}.hist p{margin:0 0 10px;font-size:14px;line-height:1.55}.hist small{color:#a3a7cf}
@media(max-width:1000px){.krow{grid-template-columns:1fr}.prow,.fichas{grid-template-columns:1fr 1fr}}
</style>"""


def encabezado(titulo: str, fecha: str, actualizado: str, etiqueta: str = "Excel actualizado") -> str:
    return (f'<div class="topbar"><span class="tt">{titulo}</span><span class="pill">{fecha}</span>'
            f'<span class="pill b sp">{etiqueta}: {actualizado}</span></div>')


def rgba(color: str, alfa: float = 0.38) -> str:
    h = color.lstrip("#")
    return f"rgba({int(h[0:2], 16)},{int(h[2:4], 16)},{int(h[4:6], 16)},{alfa})"


# ---------- tarjetas HTML ----------
def fila_kpis(items) -> str:
    """items: (título, valor, % del anillo, nota, color, delta opcional = (texto, clase))"""
    def una(t, v, p, n, c, d=None):
        dl = f'<div class="dl {d[1]}">{d[0]}</div>' if d else ""
        return (f'<div class="kcard" style="--c:{c}"><div class="kt">{t}</div><div class="kb"><div class="kv">{v}</div>'
                f'<div class="ring" style="background:conic-gradient({c} 0 {p}%,#3a3c70 0)"><span>{p}</span></div></div>'
                f'{dl}<div class="ks">{n}</div></div>')
    return f'<div class="krow">{"".join(una(*i) for i in items)}</div>'


def fila_progreso(items) -> str:
    """items: (título, %, nota, color)"""
    return '<div class="prow">' + "".join(
        f'<div class="pcard"><div class="pt"><div class="pv">{p}<small>%</small></div>'
        f'<div class="pb"><i style="width:{min(p, 100)}%;background:{c}"></i></div></div>'
        f'<div class="pn"><b>{t}</b>. {n}</div></div>' for t, p, n, c in items) + "</div>"


def capsula(partes) -> str:
    """Barra horizontal dividida. partes: (valor, color)."""
    return '<div class="cap">' + "".join(f'<i style="flex:{v};background:{c}"></i>' for v, c in partes if v > 0) + "</div>"


def fila_fichas(items) -> str:
    """items: (título, total, respondidas, pendientes, color)"""
    return '<div class="fichas">' + "".join(
        f'<div class="ficha" style="--c:{c}"><div class="ft">{t}</div><div class="fv">{n:,}</div>'
        f'{capsula([(r, AZUL), (p, GRIS)])}<div class="fn">{r:,} respondidas · {p:,} pendientes</div></div>'
        for t, n, r, p, c in items) + "</div>"


def waffle(partes) -> str:
    """Cuadrícula de 100 cuadros proporcional a las cantidades. partes: (cantidad, color)."""
    total = sum(n for n, _ in partes)
    if total == 0:
        return ""
    brutos = [n / total * 100 for n, _ in partes]
    base = [int(b) for b in brutos]
    for i in sorted(range(len(partes)), key=lambda i: brutos[i] - base[i], reverse=True)[:100 - sum(base)]:
        base[i] += 1
    return '<div class="wf">' + "".join(f'<i style="background:{c}"></i>' * k for k, (_, c) in zip(base, partes)) + "</div>"


def leyenda(items) -> str:
    """items: (color, texto, nota opcional)"""
    return '<div class="lgd">' + "<br>".join(
        f'<b style="background:{c}"></b>{t}' + (f" <small>{n}</small>" if n else "") for c, t, n in items) + "</div>"


def avatares(nombres, colores) -> str:
    return '<div class="avs">' + "".join(
        f'<span style="background:{c}" title="{n}">{n[:1]}</span>' for n, c in zip(nombres, colores)) + "</div>"


def lista_top(items, colores) -> str:
    """items: (nombre, cantidad). Líneas horizontales numeradas."""
    mx = max((n for _, n in items), default=1) or 1
    return "".join(
        f'<div class="tp"><span class="n" style="color:{c};border-color:{c}">{i}</span>'
        f'<div class="l" style="width:{max(n / mx * 100, 10):.0f}%;background:{c}"></div><span>{nom} {n}</span></div>'
        for i, ((nom, n), c) in enumerate(zip(items, colores), start=1))


def lineas_alicuota(items) -> str:
    """items: (nombre, total, respondidas, color)"""
    mx = max((t for _, t, _, _ in items), default=1) or 1
    return "".join(
        f'<div class="al"><div class="r"><span>{nom}</span><b>{t:,}</b></div>'
        f'<div class="l" style="width:{max(t / mx * 100, 10):.0f}%;background:{c}"></div>'
        f'<span class="mt">{r:,} de {t:,} respondidas</span></div>' for nom, t, r, c in items)


# ---------- gráficos SVG ----------
def _suave(p):
    if len(p) < 2:
        return f"M{p[0][0]:.1f},{p[0][1]:.1f}"
    d = f"M{p[0][0]:.1f},{p[0][1]:.1f}"
    for i in range(len(p) - 1):
        a, b, c = p[i - 1] if i > 0 else p[i], p[i], p[i + 1]
        e = p[i + 2] if i + 2 < len(p) else c
        d += (f" C{b[0] + (c[0] - a[0]) / 6:.1f},{b[1] + (c[1] - a[1]) / 6:.1f} "
              f"{c[0] - (e[0] - b[0]) / 6:.1f},{c[1] - (e[1] - b[1]) / 6:.1f} {c[0]:.1f},{c[1]:.1f}")
    return d


def _paso(v):
    if v <= 0:
        return 1
    exp = 10 ** math.floor(math.log10(v))
    return next((b * exp for b in (1, 1.5, 2, 2.5, 3, 4, 5, 6, 8, 10) if b * exp >= v), 10 * exp)


def _fmt(v, mx):
    return f"{v / 1000:g}k" if mx >= 4000 else f"{v:g}"


def curvas(series, colores, w=240, h=92) -> str:
    """Curvas suaves de una o más series. La primera lleva el punto final resaltado."""
    n = len(series[0])
    if n < 2:
        return ""
    mx = max(max(s) for s in series) or 1
    pts = [[(8 + i * (w - 16) / (n - 1), h - 10 - v / mx * (h - 24)) for i, v in enumerate(s)] for s in series]
    cuerpo = "".join(f'<path d="{_suave(p)}" fill="none" stroke="{c}" stroke-width="3" stroke-linecap="round"/>'
                     for p, c in reversed(list(zip(pts, colores))))
    x, y = pts[0][-1]
    cuerpo += f'<circle cx="{x:.1f}" cy="{y:.1f}" r="5.5" fill="#fff" stroke="{colores[0]}" stroke-width="2.5"/>'
    return f'<svg viewBox="0 0 {w} {h}" width="100%" role="img" aria-label="Curvas por mes">{cuerpo}</svg>'


def _etiquetas_x(n):
    paso = max(1, math.ceil(n / 7))
    mostrar = set(range(0, n, paso)) | {n - 1}
    previos = [i for i in mostrar if i != n - 1]
    if previos and (n - 1) - max(previos) < paso * 0.7:
        mostrar.discard(max(previos))
    return mostrar


def area(valores, etiquetas, color=AZUL, w=560, h=250) -> str:
    n = len(valores)
    if n < 2:
        return ""
    izq, der, arriba, abajo = 46, 14, 16, 40
    yb, alto, ancho = h - abajo, h - abajo - arriba, w - izq - der
    paso = _paso(max(valores) / 4)
    mx = paso * 4
    pts = [[izq + i * ancho / (n - 1), yb - v / mx * alto] for i, v in enumerate(valores)]
    g = "".join(f'<line x1="{izq}" y1="{yb - k * alto / 4:.1f}" x2="{w - der}" y2="{yb - k * alto / 4:.1f}" stroke="{REJILLA}" stroke-dasharray="3 4"/>'
                f'<text x="{izq - 8}" y="{yb - k * alto / 4 + 4:.1f}" text-anchor="end" font-size="12" fill="{TENUE}">{_fmt(paso * k, mx)}</text>' for k in range(5))
    x, y = pts[-1]
    texto = f"{valores[-1]:g} en {etiquetas[-1]}"
    ancho_tip = 7.2 * len(texto) + 18
    tip = (f'<circle cx="{x:.1f}" cy="{y:.1f}" r="6" fill="#fff" stroke="{color}" stroke-width="3"/>'
           f'<rect x="{x - ancho_tip - 12:.1f}" y="{max(y - 34, 2):.1f}" width="{ancho_tip:.0f}" height="26" rx="5" fill="{AMARILLO}"/>'
           f'<text x="{x - ancho_tip / 2 - 12:.1f}" y="{max(y - 34, 2) + 17:.1f}" text-anchor="middle" font-size="12.5" font-weight="600" fill="{FONDO}">{texto}</text>')
    lab = "".join(f'<text x="{pts[i][0]:.1f}" y="{h - 12}" text-anchor="middle" font-size="12" fill="{TENUE}">{etiquetas[i]}</text>' for i in sorted(_etiquetas_x(n)))
    return (f'<svg viewBox="0 0 {w} {h}" width="100%" role="img" aria-label="Solicitudes por mes">{g}'
            f'<path d="{_suave(pts)} L{x:.1f},{yb} L{izq},{yb} Z" fill="{color}" fill-opacity="0.22"/>'
            f'<path d="{_suave(pts)}" fill="none" stroke="{color}" stroke-width="3.5" stroke-linecap="round"/>{tip}{lab}</svg>')


def barras_finas(valores, etiquetas, linea1, linea2, color=AZUL, w=560, h=230) -> str:
    """Barras finas con globo amarillo sobre la barra más alta."""
    n = len(valores)
    if n == 0:
        return ""
    izq, der, arriba, abajo = 52, 16, 16, 42
    yb, alto = h - abajo, h - abajo - arriba
    paso = _paso((max(valores) or 1) / 4)
    mx = paso * 4
    gx = (w - izq - der) / n
    g = "".join(f'<line x1="{izq}" y1="{yb - k * alto / 4:.1f}" x2="{w - der}" y2="{yb - k * alto / 4:.1f}" stroke="{REJILLA}" stroke-dasharray="3 4"/>'
                f'<text x="{izq - 8}" y="{yb - k * alto / 4 + 4:.1f}" text-anchor="end" font-size="12" fill="{TENUE}">{_fmt(paso * k, mx)}</text>' for k in range(5))
    mejor = valores.index(max(valores))
    barras = ""
    for i, v in enumerate(valores):
        x, hb = izq + gx * (i + 0.5), max(v / mx * alto, 3)
        if i == mejor:
            barras += f'<circle cx="{x:.1f}" cy="{yb - hb:.1f}" r="11" fill="{color}" fill-opacity="0.3"/>'
        barras += (f'<rect x="{x - 3:.1f}" y="{yb - hb:.1f}" width="6" height="{hb:.1f}" rx="3" fill="{color}"/>'
                   f'<text x="{x:.1f}" y="{h - 14}" text-anchor="middle" font-size="12" fill="{TENUE}">{etiquetas[i]}</text>')
    xb = izq + gx * (mejor + 0.5)
    ancho_tip = 7.4 * max(len(linea1), len(linea2)) + 20
    tx = xb + 16 if xb + 16 + ancho_tip < w else xb - 16 - ancho_tip
    yt = max(yb - max(valores[mejor] / mx * alto, 3) - 8, 6)
    tip = (f'<rect x="{tx:.1f}" y="{yt:.1f}" width="{ancho_tip:.0f}" height="44" rx="5" fill="{AMARILLO}"/>'
           f'<text x="{tx + 10:.1f}" y="{yt + 18:.1f}" font-size="12.5" font-weight="600" fill="{FONDO}">{linea1}</text>'
           f'<text x="{tx + 10:.1f}" y="{yt + 35:.1f}" font-size="12" fill="{FONDO}">{linea2}</text>')
    return f'<svg viewBox="0 0 {w} {h}" width="100%" role="img" aria-label="Pagos por mes">{g}{barras}{tip}</svg>'


def anillo(pct, color, texto, tam=150) -> str:
    r = 34
    c = 2 * math.pi * r
    return (f'<svg viewBox="0 0 90 90" width="{tam}" style="display:block;margin:6px auto 10px" role="img" aria-label="{texto}">'
            f'<circle cx="45" cy="45" r="{r}" fill="none" stroke="#c9ccd8" stroke-width="9"/>'
            f'<circle cx="45" cy="45" r="{r}" fill="none" stroke="{color}" stroke-width="9" stroke-linecap="round" '
            f'stroke-dasharray="{c * max(min(pct, 100), 0) / 100:.1f} {c:.1f}" transform="rotate(-90 45 45)"/>'
            f'<text x="45" y="52" text-anchor="middle" font-size="19" font-weight="600" fill="#fff">{texto}</text></svg>')
