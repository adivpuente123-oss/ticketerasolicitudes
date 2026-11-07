"""Puente bidireccional. Outlook clásico, sesión Windows y una sola instancia.

No usa contraseñas. Solo lee la subcarpeta Solicitudes del buzón seleccionado.
Los envíos quedan en Outlook; enviado aquí significa entregado a Outlook, no entrega al destinatario.
"""
import argparse
import os
import time
import logging
import sqlite3

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


def recibir(carpeta):
    # Revisar también leídos: abrir un mensaje antes del servicio no debe perderlo.
    for item in list(carpeta.Items):
        if getattr(item, "Class", None) != 43:
            continue
        if "SIN TICKET" in str(getattr(item, "Categories", "")):
            continue
        try:
            ident = item.PropertyAccessor.GetProperty("http://schemas.microsoft.com/mapi/proptag/0x1035001F") or item.EntryID
        except Exception:
            ident = item.EntryID
        if db.existe_id_correo(str(ident)):
            continue
        try:
            r = crear_ticket_desde_correo(remitente_de(item), str(item.Subject or ""), str(item.Body or ""), str(ident), fecha_de(item))
            if r["ok"]:
                item.Categories = r["codigo"]
                item.UnRead = False
            else:
                item.Categories = "SIN TICKET"
                logging.warning("Correo no importado: %s", r["motivo"])
            item.Save()
        except sqlite3.IntegrityError:
            pass  # Another receiver committed this Message-ID first.


def enviar(app, cuenta):
    while True:
        with db.conexion() as con:
            con.execute("BEGIN IMMEDIATE")
            r = con.execute("SELECT * FROM correo_salida WHERE estado='pendiente' ORDER BY id LIMIT 1").fetchone()
            if not r:
                return
            con.execute("UPDATE correo_salida SET estado='procesando' WHERE id=?", (r["id"],))
        try:
            mail = app.CreateItem(0)
            mail.SendUsingAccount = cuenta
            mail.To, mail.Subject, mail.Body = r["destinatario"], r["asunto"], r["cuerpo"]
            mail.Send()
            with db.conexion() as con:
                con.execute("UPDATE correo_salida SET estado='entregado_outlook',error=NULL WHERE id=?", (r["id"],))
        except Exception:
            # No auto-retry: Send might have queued before the connection failed.
            with db.conexion() as con:
                con.execute("UPDATE correo_salida SET estado='revisar',error='Revisar Bandeja de salida y Enviados antes de reintentar' WHERE id=?", (r["id"],))
            logging.exception("No se pudo confirmar envío %s", r["id"])


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
