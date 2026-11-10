"""Convierte el correo de un supervisor en un ticket de la plataforma (parte de la Fase 2).

Reglas:
  - Solo se aceptan correos de supervisores registrados y activos (el correo se asigna en «Usuarios»).
  - Si el supervisor escribe líneas con el formato «Cartera: IBK», «DNI: 12345678», «Cuenta: 00123»...
    el ticket se llena solo. Lo que no se detecta queda para que lo completes tú al gestionarlo.
  - Cada correo crea un solo ticket (se guarda su identificador para no duplicarlo).
"""
import re
import unicodedata
from datetime import date

import db
from config import TIPOS_CONSULTA

PALABRAS_TIPO = [("cancel", TIPOS_CONSULTA[0]), ("central", TIPOS_CONSULTA[1]), ("acuerdo", TIPOS_CONSULTA[2])]
PALABRAS_CARTERA = [("ibk", "IBK"), ("interbank", "IBK"), ("bbva", "BBVA")]


def _plano(texto: str) -> str:
    return unicodedata.normalize("NFD", texto or "").encode("ascii", "ignore").decode().lower()


def _buscar(patron: str, texto: str):
    m = re.search(patron, texto, re.IGNORECASE | re.MULTILINE)
    return m.group(1).strip() if m else None


def _cartera(texto_etiqueta, plano_total):
    for fuente in (_plano(texto_etiqueta or ""), plano_total):
        for palabra, cartera in PALABRAS_CARTERA:
            if palabra in fuente:
                return cartera
    return "OTROS" if _plano(texto_etiqueta or "").strip() == "otros" else None


def _tipo(texto_etiqueta, plano_total):
    for fuente in (_plano(texto_etiqueta or ""), plano_total):
        for palabra, tipo in PALABRAS_TIPO:
            if palabra in fuente:
                return tipo
    return None


def analizar(asunto: str, cuerpo: str) -> dict:
    """Detecta cartera, tipo de consulta, documento y cuenta dentro del texto del correo."""
    plano = _plano(f"{asunto}\n{cuerpo}")
    cartera = _cartera(_buscar(r"^\s*(?:cartera|entidad|banco)\s*[:=\-]\s*(.+?)\s*$", cuerpo), plano)
    tipo = _tipo(_buscar(r"^\s*tipo(?:\s+de\s+consulta)?\s*[:=\-]\s*(.+?)\s*$", cuerpo), plano)
    documento = (_buscar(r"^\s*(?:dni|documento|doc\.?)\s*[:=\-]\s*([0-9A-Za-z]{6,15})\s*$", cuerpo)
                 or _buscar(r"\b(\d{8})\b", cuerpo))
    cuenta = _buscar(r"^\s*(?:n[uú]mero\s+de\s+cuenta|nro\.?\s+de\s+cuenta|n[°º]\s*de\s+cuenta|cuenta)\s*[:=\-]\s*([0-9A-Za-z\-]{4,25})\s*$", cuerpo)
    faltantes = [n for n, v in (("cartera", cartera), ("tipo de consulta", tipo), ("documento", documento), ("cuenta", cuenta)) if not v]
    return {"cartera": cartera or "OTROS", "tipo_consulta": tipo or "Sin tipo", "documento": documento or "", "cuenta": cuenta or "",
            "faltantes": faltantes}


def crear_ticket_desde_correo(remitente: str, asunto: str, cuerpo: str, id_correo=None, fecha=None, codigo_ticket=None) -> dict:
    """Crea el ticket. Devuelve {'ok': True, 'codigo', 'tid', 'datos', 'supervisor'} o {'ok': False, 'motivo'}."""
    u = db.usuario_por_correo(remitente)
    if not u or not u["activo"]:
        return {"ok": False, "motivo": f"El remitente {remitente or '(desconocido)'} no es un supervisor registrado y activo."}
    if id_correo and db.existe_id_correo(id_correo):
        return {"ok": False, "duplicado": True, "motivo": "Este correo ya se había convertido en ticket."}
    referencia = re.search(r"\[(SOL-\d+)\]", asunto or "", re.IGNORECASE)
    codigo_referencia = referencia[1] if referencia else codigo_ticket
    if codigo_referencia:
        with db.conexion() as con:
            t = con.execute("SELECT id,supervisor_id,codigo FROM tickets WHERE codigo=?", (codigo_referencia.upper(),)).fetchone()
        if not t:
            return {"ok": False, "motivo": "La referencia del ticket no existe."}
        try:
            db.agregar_mensaje(t["id"], u["id"], cuerpo or "(Correo sin texto)", id_correo)
        except PermissionError:
            return {"ok": False, "motivo": "El remitente no tiene acceso a este ticket."}
        return {"ok": True, "codigo": t["codigo"], "tid": t["id"], "datos": {"faltantes": []}, "supervisor": u["nombre"], "respuesta": True}
    if u["rol"] != "supervisor":
        return {"ok": False, "motivo": "Un correo nuevo debe venir de un supervisor; para responder conserva [SOL-0001] en el asunto."}
    datos = analizar(asunto or "", cuerpo or "")
    descripcion = f"Asunto: {(asunto or '').strip()}\n\n{(cuerpo or '').strip()}"[:3000]
    detalle = f"Llegó por correo de {remitente}." + (f" Datos por completar: {', '.join(datos['faltantes'])}." if datos["faltantes"] else "")
    tid, codigo = db.crear_ticket(u["id"], datos["cartera"], datos["tipo_consulta"], datos["documento"], datos["cuenta"], descripcion,
                                  origen="correo", fecha_solicitud=fecha or date.today().isoformat(), usuario_id=u["id"],
                                  detalle=detalle, id_correo=id_correo)
    return {"ok": True, "codigo": codigo, "tid": tid, "datos": datos, "supervisor": u["nombre"]}
