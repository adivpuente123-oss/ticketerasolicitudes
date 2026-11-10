"""Base de datos de la plataforma de solicitudes (SQLite). Aquí vive todo el acceso a los datos."""
import hashlib
import hmac
import os
import sqlite3
import secrets
import time
from contextlib import contextmanager
from datetime import date, datetime

import pandas as pd

from config import RUTA_DB

ESQUEMA = """
CREATE TABLE IF NOT EXISTS usuarios (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    nombre TEXT NOT NULL UNIQUE,                 -- como aparece en la columna SOLICITUD del Excel (ej. KENNETH)
    correo TEXT UNIQUE,
    rol TEXT NOT NULL CHECK (rol IN ('supervisor', 'backoffice')),
    clave_hash TEXT,                             -- vacío = todavía no puede entrar
    activo INTEGER NOT NULL DEFAULT 1,
    creado_en TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS sesiones (
    huella TEXT PRIMARY KEY,
    usuario_id INTEGER NOT NULL REFERENCES usuarios(id) ON DELETE CASCADE,
    expira_en INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_sesiones_usuario ON sesiones(usuario_id);
CREATE TABLE IF NOT EXISTS tickets (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    codigo TEXT UNIQUE,                          -- SOL-0001
    origen TEXT NOT NULL DEFAULT 'web',          -- web | correo | excel
    supervisor_id INTEGER REFERENCES usuarios(id),
    cartera TEXT NOT NULL,
    tipo_consulta TEXT,
    documento TEXT,
    cuenta TEXT,
    descripcion TEXT,                            -- lo que escribe el supervisor
    estado TEXT NOT NULL DEFAULT 'Recibida' CHECK (estado IN ('Recibida', 'Enviada a verificar', 'Respondida')),
    fecha_solicitud TEXT NOT NULL,
    fecha_envio TEXT,
    fecha_respuesta TEXT,
    conclusion TEXT CHECK (conclusion IN ('PROCEDENTE', 'IMPROCEDENTE') OR conclusion IS NULL),
    estado_corresponde TEXT,
    respuesta TEXT,                              -- descripción de la respuesta: la ve el supervisor
    sustento TEXT,
    id_correo TEXT UNIQUE,                       -- para no duplicar un correo (Fase 2)
    creado_en TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    actualizado_en TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS historial (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ticket_id INTEGER NOT NULL REFERENCES tickets(id) ON DELETE CASCADE,
    fecha TEXT NOT NULL,
    usuario_id INTEGER REFERENCES usuarios(id),
    evento TEXT NOT NULL,
    detalle TEXT
);
CREATE INDEX IF NOT EXISTS ix_tickets_sup ON tickets(supervisor_id);
CREATE INDEX IF NOT EXISTS ix_tickets_estado ON tickets(estado);
CREATE TABLE IF NOT EXISTS mensajes (
    id INTEGER PRIMARY KEY, ticket_id INTEGER NOT NULL REFERENCES tickets(id),
    usuario_id INTEGER REFERENCES usuarios(id), cuerpo TEXT NOT NULL,
    id_correo TEXT UNIQUE, creado_en TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS correo_salida (
    id INTEGER PRIMARY KEY, ticket_id INTEGER NOT NULL REFERENCES tickets(id),
    destinatario TEXT NOT NULL, asunto TEXT NOT NULL, cuerpo TEXT NOT NULL,
    estado TEXT NOT NULL DEFAULT 'pendiente', error TEXT,
    creado_en TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS notificaciones (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    usuario_id INTEGER NOT NULL REFERENCES usuarios(id) ON DELETE CASCADE,
    ticket_id INTEGER NOT NULL REFERENCES tickets(id) ON DELETE CASCADE,
    tipo TEXT NOT NULL,
    titulo TEXT NOT NULL,
    leida INTEGER NOT NULL DEFAULT 0,
    creado_en TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS ix_notificaciones_usuario ON notificaciones(usuario_id, leida, id);
CREATE TABLE IF NOT EXISTS correos_eliminados (
    huella TEXT PRIMARY KEY
);
CREATE TABLE IF NOT EXISTS servicio (
    nombre TEXT PRIMARY KEY, actualizado_en TEXT NOT NULL, detalle TEXT
);
"""

PERMITIDAS = {"estado", "fecha_envio", "fecha_respuesta", "conclusion", "estado_corresponde", "respuesta",
              "sustento", "cartera", "tipo_consulta"}


def hoy_iso() -> str:
    return date.today().isoformat()


def ahora_iso() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


@contextmanager
def conexion():
    RUTA_DB.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(RUTA_DB, timeout=15)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys = ON")
    con.execute("PRAGMA journal_mode = WAL")
    try:
        yield con
        con.commit()
    except Exception:
        con.rollback()
        raise
    finally:
        con.close()


def iniciar():
    with conexion() as con:
        con.executescript(ESQUEMA)


# ---------- contraseñas (solo librería estándar: PBKDF2-SHA256) ----------
def hash_clave(clave: str) -> str:
    sal = os.urandom(16)
    h = hashlib.pbkdf2_hmac("sha256", clave.encode(), sal, 200_000)
    return f"pbkdf2$200000${sal.hex()}${h.hex()}"


def verificar_clave(clave: str, guardado) -> bool:
    try:
        _, vueltas, sal, h = (guardado or "").split("$")
        calc = hashlib.pbkdf2_hmac("sha256", clave.encode(), bytes.fromhex(sal), int(vueltas))
    except ValueError:
        return False
    return hmac.compare_digest(calc.hex(), h)


# ---------- usuarios ----------
def hay_backoffice() -> bool:
    with conexion() as con:
        return con.execute("SELECT COUNT(*) FROM usuarios WHERE rol='backoffice' AND clave_hash IS NOT NULL").fetchone()[0] > 0


def crear_usuario(nombre, correo, rol, clave=None, activo=1) -> int:
    with conexion() as con:
        return con.execute(
            "INSERT INTO usuarios (nombre, correo, rol, clave_hash, activo) VALUES (?,?,?,?,?)",
            (nombre.strip().upper(), (correo or "").strip().lower() or None, rol, hash_clave(clave) if clave else None, activo)).lastrowid


def actualizar_usuario(uid, nombre, correo, rol, activo, clave=None):
    with conexion() as con:
        anterior = con.execute("SELECT * FROM usuarios WHERE id=?", (uid,)).fetchone()
        if anterior and (clave or anterior["correo"] != ((correo or "").strip().lower() or None) or anterior["rol"] != rol or not activo):
            con.execute("DELETE FROM sesiones WHERE usuario_id=?", (uid,))
        con.execute("UPDATE usuarios SET nombre=?, correo=?, rol=?, activo=? WHERE id=?",
                    (nombre.strip().upper(), (correo or "").strip().lower() or None, rol, int(activo), uid))
        if clave:
            con.execute("UPDATE usuarios SET clave_hash=? WHERE id=?", (hash_clave(clave), uid))



def _autorizar_borrado(con, actor_id):
    actor = con.execute("SELECT * FROM usuarios WHERE id=?", (actor_id,)).fetchone()
    if not actor or not actor["activo"] or actor["rol"] != "backoffice":
        raise PermissionError("Solo back office puede eliminar usuarios o solicitudes.")


def _borrar_ticket(con, tid):
    # Solo conservar huellas para impedir la reimportación del mismo correo.
    correos = con.execute("SELECT id_correo FROM tickets WHERE id=? UNION SELECT id_correo FROM mensajes WHERE ticket_id=?", (tid, tid)).fetchall()
    for correo in correos:
        if correo["id_correo"]:
            huella = hashlib.sha256(correo["id_correo"].encode()).hexdigest()
            con.execute("INSERT OR IGNORE INTO correos_eliminados(huella) VALUES(?)", (huella,))
    con.execute("DELETE FROM correo_salida WHERE ticket_id=?", (tid,))
    con.execute("DELETE FROM mensajes WHERE ticket_id=?", (tid,))
    con.execute("DELETE FROM historial WHERE ticket_id=?", (tid,))
    con.execute("DELETE FROM tickets WHERE id=?", (tid,))


def eliminar_solicitud(tid, actor_id):
    with conexion() as con:
        con.execute("BEGIN IMMEDIATE")
        _autorizar_borrado(con, actor_id)
        if not con.execute("SELECT 1 FROM tickets WHERE id=?", (tid,)).fetchone():
            raise ValueError("La solicitud ya no existe.")
        _borrar_ticket(con, tid)


def eliminar_usuario(uid, actor_id, borrar_solicitudes=False):
    """Borra la cuenta y, si se confirma, sus solicitudes con todos sus registros."""
    with conexion() as con:
        con.execute("BEGIN IMMEDIATE")
        _autorizar_borrado(con, actor_id)
        if uid == actor_id:
            raise ValueError("No puedes eliminar tu propia cuenta.")
        if not con.execute("SELECT 1 FROM usuarios WHERE id=?", (uid,)).fetchone():
            raise ValueError("El usuario ya no existe.")
        if borrar_solicitudes:
            ids = con.execute("SELECT id FROM tickets WHERE supervisor_id=?", (uid,)).fetchall()
            for t in ids:
                _borrar_ticket(con, t["id"])
        # Conservar solicitudes ajenas y, si se elige No, las del usuario sin cuenta asociada.
        con.execute("UPDATE tickets SET supervisor_id=NULL WHERE supervisor_id=?", (uid,))
        con.execute("UPDATE historial SET usuario_id=NULL WHERE usuario_id=?", (uid,))
        con.execute("UPDATE mensajes SET usuario_id=NULL WHERE usuario_id=?", (uid,))
        con.execute("DELETE FROM usuarios WHERE id=?", (uid,))


def usuario_por_correo(correo):
    with conexion() as con:
        return con.execute("SELECT * FROM usuarios WHERE correo = ?", ((correo or "").strip().lower(),)).fetchone()


def id_supervisor(nombre, activo=1) -> int:
    """Devuelve el id del supervisor; lo crea (sin clave) si no existe."""
    with conexion() as con:
        fila = con.execute("SELECT id FROM usuarios WHERE nombre = ?", (nombre.strip().upper(),)).fetchone()
    return fila["id"] if fila else crear_usuario(nombre, None, "supervisor", None, activo)


def usuarios_df() -> pd.DataFrame:
    with conexion() as con:
        return pd.read_sql_query(
            """SELECT u.id, u.nombre, u.correo, u.rol, u.activo, (u.clave_hash IS NOT NULL) AS con_clave,
                      (SELECT COUNT(*) FROM tickets t WHERE t.supervisor_id = u.id) AS tickets
               FROM usuarios u ORDER BY u.rol, u.nombre""", con)


# ---------- tickets ----------
_SELECT = """SELECT t.id, t.codigo, t.origen, t.cartera, t.tipo_consulta, t.documento, t.cuenta, t.descripcion, t.estado,
                    t.fecha_solicitud, t.fecha_envio, t.fecha_respuesta, t.conclusion, t.estado_corresponde,
                    t.respuesta, t.sustento, t.supervisor_id, u.nombre AS supervisor
             FROM tickets t LEFT JOIN usuarios u ON u.id = t.supervisor_id"""


def crear_ticket(supervisor_id, cartera, tipo_consulta, documento, cuenta, descripcion="", origen="web",
                 fecha_solicitud=None, estado="Recibida", usuario_id=None, detalle="Ticket creado", **extra):
    campos = {"supervisor_id": supervisor_id, "cartera": cartera, "tipo_consulta": tipo_consulta, "documento": documento,
              "cuenta": cuenta, "descripcion": descripcion, "origen": origen,
              "fecha_solicitud": fecha_solicitud or hoy_iso(), "estado": estado, **extra}
    with conexion() as con:
        tid = con.execute(f"INSERT INTO tickets ({', '.join(campos)}) VALUES ({', '.join('?' for _ in campos)})",
                          list(campos.values())).lastrowid
        codigo = f"SOL-{tid:04d}"
        con.execute("UPDATE tickets SET codigo = ? WHERE id = ?", (codigo, tid))
        con.execute("INSERT INTO historial (ticket_id, fecha, usuario_id, evento, detalle) VALUES (?,?,?,?,?)",
                    (tid, ahora_iso(), usuario_id, "Creado", detalle))
        _crear_notificaciones(con, tid, "solicitud", "Nueva solicitud", usuario_id or supervisor_id)
        _notificar(con, tid, "Solicitud recibida", f"Tu solicitud {codigo} fue recibida. La revisaremos pronto.", avisar_equipo=True)
    return tid, codigo


def tickets_df(supervisor_id=None) -> pd.DataFrame:
    with conexion() as con:
        if supervisor_id is None:
            return pd.read_sql_query(_SELECT + " ORDER BY t.id DESC", con)
        return pd.read_sql_query(_SELECT + " WHERE t.supervisor_id = ? ORDER BY t.id DESC", con, params=(supervisor_id,))


def ticket(tid):
    with conexion() as con:
        return con.execute(_SELECT + " WHERE t.id = ?", (tid,)).fetchone()


def actualizar_ticket(tid, usuario_id, cambios: dict, evento: str, detalle: str = ""):
    cambios = {k: v for k, v in cambios.items() if k in PERMITIDAS}
    with conexion() as con:
        if cambios:
            con.execute(f"UPDATE tickets SET {', '.join(f'{k} = ?' for k in cambios)}, actualizado_en = ? WHERE id = ?",
                        [*cambios.values(), ahora_iso(), tid])
        con.execute("INSERT INTO historial (ticket_id, fecha, usuario_id, evento, detalle) VALUES (?,?,?,?,?)",
                    (tid, ahora_iso(), usuario_id, evento, detalle))
        if cambios:
            _crear_notificaciones(con, tid, "estado", "Solicitud actualizada", usuario_id)
            _notificar(con, tid, "Actualización de solicitud", cambios.get("respuesta") or "El equipo actualizó el estado de tu solicitud.")


def historial_df(tid) -> pd.DataFrame:
    with conexion() as con:
        return pd.read_sql_query(
            """SELECT h.fecha, COALESCE(u.nombre, 'Sistema') AS usuario, h.evento, h.detalle
               FROM historial h LEFT JOIN usuarios u ON u.id = h.usuario_id WHERE h.ticket_id = ? ORDER BY h.id""", con, params=(tid,))


def existe_id_correo(id_correo) -> bool:
    with conexion() as con:
        return (con.execute("SELECT 1 FROM correos_eliminados WHERE huella=?", (hashlib.sha256(id_correo.encode()).hexdigest(),)).fetchone() is not None
                or con.execute("SELECT 1 FROM tickets WHERE id_correo = ?", (id_correo,)).fetchone() is not None
                or con.execute("SELECT 1 FROM mensajes WHERE id_correo = ?", (id_correo,)).fetchone() is not None)


def _notificar(con, tid, asunto, texto, avisar_equipo=False):
    """Transactional outbox: ticket and pending mail always commit together."""
    t = con.execute("SELECT t.*, u.correo FROM tickets t JOIN usuarios u ON u.id=t.supervisor_id WHERE t.id=?", (tid,)).fetchone()
    if not t:
        return
    destinatarios = {t["correo"]} if t["correo"] else set()
    if avisar_equipo:
        destinatarios.add(os.getenv("BUZON_ATENCION", "adiv.puente@goexpertis.com"))
    cuerpo = f"{t['codigo']} · {t['estado']}\n\n{texto}\n\nResponde conservando [{t['codigo']}] en el asunto para continuar la conversación."
    if asunto == "Solicitud recibida":
        cuerpo = texto
    url = (os.getenv("PORTAL_URL", "").strip() or os.getenv("RENDER_EXTERNAL_URL", "").strip()).rstrip("/")
    if url and asunto != "Solicitud recibida":
        cuerpo += f"\nConsulta tus solicitudes en {url}"
    for correo in destinatarios:
        con.execute("INSERT INTO correo_salida(ticket_id,destinatario,asunto,cuerpo) VALUES(?,?,?,?)",
                    (tid, correo, f"[{t['codigo']}] {asunto}", cuerpo))


def agregar_mensaje(tid, uid, cuerpo, id_correo=None):
    if not cuerpo.strip():
        raise ValueError("Escribe un mensaje.")
    with conexion() as con:
        u = con.execute("SELECT * FROM usuarios WHERE id=? AND activo=1", (uid,)).fetchone()
        t = con.execute("SELECT * FROM tickets WHERE id=?", (tid,)).fetchone()
        if not u or not t or (u["rol"] != "backoffice" and t["supervisor_id"] != uid):
            raise PermissionError("No tienes acceso a esta solicitud.")
        con.execute("INSERT INTO mensajes(ticket_id,usuario_id,cuerpo,id_correo) VALUES(?,?,?,?)", (tid, uid, cuerpo[:20000], id_correo))
        con.execute("INSERT INTO historial(ticket_id,fecha,usuario_id,evento,detalle) VALUES(?,?,?,?,?)",
                    (tid, ahora_iso(), uid, "Mensaje recibido" if id_correo else "Mensaje", "Por correo" if id_correo else "Desde la web"))
        _crear_notificaciones(con, tid, "mensaje", "Nuevo mensaje en la conversación", uid)
        if not id_correo:
            _notificar(con, tid, "Nuevo mensaje", cuerpo[:20000], avisar_equipo=u["rol"] == "supervisor")


def mensajes(tid):
    with conexion() as con:
        return con.execute("SELECT m.*,u.nombre FROM mensajes m LEFT JOIN usuarios u ON u.id=m.usuario_id WHERE ticket_id=? ORDER BY m.id", (tid,)).fetchall()


def usuario_por_id(uid):
    with conexion() as con:
        return con.execute("SELECT * FROM usuarios WHERE id=?", (uid,)).fetchone()


def servicio_actualizar(detalle):
    with conexion() as con:
        con.execute("INSERT OR REPLACE INTO servicio VALUES('outlook',?,?)", (ahora_iso(), detalle))


def abiertas_por_documento(documento, cuenta):
    with conexion() as con:
        return [f["codigo"] for f in con.execute(
            "SELECT codigo FROM tickets WHERE documento = ? AND COALESCE(cuenta,'') = ? AND estado <> 'Respondida'",
            (documento, cuenta or ""))]


def _crear_notificaciones(con, tid, tipo, titulo, autor_id):
    t = con.execute("SELECT supervisor_id FROM tickets WHERE id=?", (tid,)).fetchone()
    if not t:
        return
    destinatarios = con.execute("SELECT id FROM usuarios WHERE activo=1 AND (rol='backoffice' OR id=?)", (t["supervisor_id"],)).fetchall()
    for u in destinatarios:
        if u["id"] != autor_id:
            con.execute("INSERT INTO notificaciones(usuario_id,ticket_id,tipo,titulo) VALUES(?,?,?,?)", (u["id"], tid, tipo, titulo))


def notificaciones_usuario(uid, limite=30):
    with conexion() as con:
        return con.execute("""SELECT n.*,t.codigo FROM notificaciones n
            JOIN tickets t ON t.id=n.ticket_id JOIN usuarios u ON u.id=n.usuario_id
            WHERE n.usuario_id=? AND n.leida=0 AND u.activo=1 AND (u.rol='backoffice' OR t.supervisor_id=u.id)
            ORDER BY n.id DESC LIMIT ?""", (uid, limite)).fetchall()


def contar_notificaciones(uid):
    with conexion() as con:
        return con.execute("""SELECT count(*) FROM notificaciones n
            JOIN tickets t ON t.id=n.ticket_id JOIN usuarios u ON u.id=n.usuario_id
            WHERE n.usuario_id=? AND n.leida=0 AND u.activo=1 AND (u.rol='backoffice' OR t.supervisor_id=u.id)""", (uid,)).fetchone()[0]


def marcar_notificaciones(uid, nid=None):
    with conexion() as con:
        con.execute("UPDATE notificaciones SET leida=1 WHERE usuario_id=?" + (" AND id=?" if nid is not None else ""), (uid, nid) if nid is not None else (uid,))


DURACION_SESION = 12 * 60 * 60


def crear_sesion(uid):
    token = secrets.token_urlsafe(32)
    huella = hashlib.sha256(token.encode()).hexdigest()
    expira = int(time.time()) + DURACION_SESION
    with conexion() as con:
        con.execute("DELETE FROM sesiones WHERE expira_en<=?", (int(time.time()),))
        u = con.execute("SELECT activo FROM usuarios WHERE id=?", (uid,)).fetchone()
        if not u or not u["activo"]:
            raise PermissionError("El usuario no está activo.")
        con.execute("INSERT INTO sesiones(huella,usuario_id,expira_en) VALUES(?,?,?)", (huella, uid, expira))
    return token


def usuario_por_sesion(token):
    if not token or not isinstance(token, str) or len(token) > 256:
        return None
    with conexion() as con:
        return con.execute("""SELECT u.* FROM sesiones s JOIN usuarios u ON u.id=s.usuario_id
            WHERE s.huella=? AND s.expira_en>? AND u.activo=1""",
            (hashlib.sha256(token.encode()).hexdigest(), int(time.time()))).fetchone()


def revocar_sesion(token):
    if token:
        with conexion() as con:
            con.execute("DELETE FROM sesiones WHERE huella=?", (hashlib.sha256(token.encode()).hexdigest(),))
