"""Puente bidireccional. Outlook clásico, sesión Windows y una sola instancia.

No usa contraseñas. Solo lee la subcarpeta Solicitudes del buzón seleccionado.
Los avisos se guardan en Borradores. Solo el usuario puede enviarlos desde Outlook.
"""
import argparse
import os
import time
import logging
import sqlite3
import re
from html import escape

import db
from leer_outlook import remitente_de, fecha_de
from correo import crear_ticket_desde_correo

BUZON = os.getenv("BUZON_ATENCION", "adiv.puente@goexpertis.com").lower()


def abrir_outlook():
    import win32com.client
    app = win32com.client.Dispatch("Outlook.Application")
    ns = app.GetNamespace("MAPI")
    cuenta = next((a for a in ns.Accounts if str(a.SmtpAddress).lower() == BUZON), None)
    if cuenta is None:
        raise RuntimeError(f"Configura {BUZON} como cuenta en Outlook clásico. No se usará otro buzón.")
    entrada = cuenta.DeliveryStore.GetDefaultFolder(6)
    try:
        carpeta = entrada.Folders.Item("Solicitudes")
    except Exception as exc:
        raise RuntimeError("Crea la carpeta Solicitudes en la Bandeja de entrada del buzón de atención y una regla para los correos de supervisores.") from exc
    return app, cuenta, carpeta


def identificador(item):
    try:
        return str(item.PropertyAccessor.GetProperty("http://schemas.microsoft.com/mapi/proptag/0x1035001F") or item.EntryID)
    except Exception:
        return str(item.EntryID)


def codigo_respuesta(item):
    try:
        responde_a = item.PropertyAccessor.GetProperty("http://schemas.microsoft.com/mapi/proptag/0x1042001F")
    except Exception:
        return None
    if not isinstance(responde_a, str) or not responde_a:
        return None
    return db.codigo_por_correo(responde_a) or db.codigo_por_hilo("outlook", BUZON, getattr(item, "ConversationID", ""))


def recibir(carpeta):
    # Reconstruir primero los hilos conocidos, incluso si Outlook ordena del más nuevo al más antiguo.
    items = list(carpeta.Items)
    for item in items:
        if getattr(item, "Class", None) == 43:
            db.registrar_hilo_correo("outlook", BUZON, getattr(item, "ConversationID", ""), identificador(item))
    # Revisar también leídos: abrir un mensaje antes del servicio no debe perderlo.
    for item in items:
        if getattr(item, "Class", None) != 43:
            continue
        if "SIN TICKET" in str(getattr(item, "Categories", "")):
            continue
        try:
            ident = item.PropertyAccessor.GetProperty("http://schemas.microsoft.com/mapi/proptag/0x1035001F") or item.EntryID
        except Exception:
            ident = item.EntryID
        hilo = getattr(item, "ConversationID", "")
        if db.existe_id_correo(str(ident)):
            db.registrar_hilo_correo("outlook", BUZON, hilo, str(ident))
            continue
        try:
            r = crear_ticket_desde_correo(remitente_de(item), str(item.Subject or ""), str(item.Body or ""), str(ident), fecha_de(item), codigo_ticket=codigo_respuesta(item))
            if r["ok"]:
                db.registrar_hilo_correo("outlook", BUZON, hilo, str(ident))
                item.Categories = r["codigo"]
                item.UnRead = False
            else:
                item.Categories = "SIN TICKET"
                logging.warning("Correo no importado: %s", r["motivo"])
            item.Save()
        except sqlite3.IntegrityError:
            pass  # Another receiver committed this Message-ID first.


def respuesta_original(app, cuenta, fila):
    original, interno = db.origen_borrador(fila["ticket_id"], fila["destinatario"], BUZON)
    if interno:
        return None
    if not original:
        mail = app.CreateItem(0)
        mail.To, mail.Subject, mail.Body = fila["destinatario"], fila["asunto"], fila["cuerpo"]
        return mail
    carpeta = cuenta.DeliveryStore.GetDefaultFolder(6).Folders.Item("Solicitudes")
    for item in list(carpeta.Items):
        if getattr(item, "Class", None) != 43:
            continue
        try:
            ident = item.PropertyAccessor.GetProperty("http://schemas.microsoft.com/mapi/proptag/0x1035001F") or item.EntryID
        except Exception:
            ident = item.EntryID
        if str(ident) == original:
            mail = item.Reply()
            # Respetar Subject, destinatarios y metadatos que Outlook genera con Responder.
            anterior = getattr(mail, "HTMLBody", "")
            if isinstance(anterior, str) and anterior:
                texto = '<div>' + escape(fila["cuerpo"]).replace('\n', '<br>') + '</div><br>'
                mail.HTMLBody = re.sub(r'(<body\b[^>]*>)', lambda m: m[1] + texto, anterior, count=1, flags=re.IGNORECASE) if re.search(r'<body\b', anterior, re.IGNORECASE) else texto + anterior
            else:
                citado = getattr(mail, "Body", "")
                mail.Body = fila["cuerpo"] + "\r\n\r\n" + (citado if isinstance(citado, str) else "")
            return mail
    raise RuntimeError("No se encontró el correo original en Solicitudes; revisa antes de reintentar.")


def enviar(app, cuenta):
    """Nombre conservado por compatibilidad: solo crea borradores, nunca envía."""
    while True:
        with db.conexion() as con:
            con.execute("BEGIN IMMEDIATE")
            r = con.execute("SELECT * FROM correo_salida WHERE estado='pendiente' ORDER BY id LIMIT 1").fetchone()
            if not r:
                return
            con.execute("UPDATE correo_salida SET estado='procesando' WHERE id=?", (r["id"],))
        try:
            mail = respuesta_original(app, cuenta, r)
            if mail is None:
                with db.conexion() as con:
                    con.execute("UPDATE correo_salida SET estado='omitido',error='Aviso interno: no se crea un borrador adicional' WHERE id=?", (r["id"],))
                continue
            mail.SendUsingAccount = cuenta
            mail.Save()
            borradores = cuenta.DeliveryStore.GetDefaultFolder(16)
            if mail.Parent.EntryID != borradores.EntryID:
                mail.Move(borradores)
            with db.conexion() as con:
                con.execute("UPDATE correo_salida SET estado='borrador',error=NULL WHERE id=?", (r["id"],))
        except Exception:
            # No repetir automáticamente: el borrador puede haberse guardado.
            with db.conexion() as con:
                con.execute("UPDATE correo_salida SET estado='revisar',error='Revisar Borradores antes de reintentar' WHERE id=?", (r["id"],))
            logging.exception("No se pudo confirmar el borrador %s", r["id"])


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--cada", type=int, default=15, help="Segundos entre revisiones, mínimo 5")
    p.add_argument("--una-vez", action="store_true")
    args = p.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    db.iniciar()
    while True:
        try:
            app, cuenta, carpeta = abrir_outlook()
            recibir(carpeta)
            enviar(app, cuenta)
            db.servicio_actualizar("Conectado · revisión completada")
        except Exception:
            db.servicio_actualizar("Error de conexión: revisar servicio y Outlook clásico")
            logging.exception("Error del servicio de correo")
        if args.una_vez:
            break
        time.sleep(max(5, args.cada))


if __name__ == "__main__":
    main()
