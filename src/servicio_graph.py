"""Recepción y salida en Microsoft 365 para el servidor, sin Outlook instalado."""
import json
import logging
import os
import time
from urllib.parse import quote, urlencode
from urllib.request import Request, urlopen
from urllib.error import HTTPError

import db
from correo import crear_ticket_desde_correo

GRAPH = "https://graph.microsoft.com/v1.0"


class Graph:
    def __init__(self):
        self.tenant = os.environ["MS_TENANT_ID"]
        self.client = os.environ["MS_CLIENT_ID"]
        self.secret = os.environ["MS_CLIENT_SECRET"]
        self.buzon = os.getenv("BUZON_ATENCION", "adiv.puente@goexpertis.com")
        self.base = "/users/" + quote(self.buzon, safe="")
        self.token, self.expira = None, 0

    def autorizar(self):
        if self.token and time.time() < self.expira:
            return
        data = urlencode({"client_id": self.client, "client_secret": self.secret,
                          "scope": "https://graph.microsoft.com/.default", "grant_type": "client_credentials"}).encode()
        req = Request(f"https://login.microsoftonline.com/{quote(self.tenant, safe='')}/oauth2/v2.0/token", data=data,
                      headers={"Content-Type": "application/x-www-form-urlencoded"})
        with urlopen(req, timeout=30) as response:
            r = json.load(response)
        self.token, self.expira = r["access_token"], time.time() + int(r["expires_in"]) - 120

    def request(self, path, method="GET", data=None):
        self.autorizar()
        url = path if path.startswith("https://") else GRAPH + path
        # Pagination URLs may originate in responses; never forward credentials to another origin.
        if not url.startswith(GRAPH + "/"):
            raise ValueError("URL de Graph no válida")
        req = Request(url, method=method, data=json.dumps(data).encode() if data is not None else None,
                      headers={"Authorization": "Bearer " + self.token, "Content-Type": "application/json",
                               "Prefer": 'outlook.body-content-type="text", IdType="ImmutableId"'})
        with urlopen(req, timeout=30) as response:
            raw = response.read()
            return json.loads(raw) if raw else {}

    def coleccion(self, path):
        while path:
            result = self.request(path)
            yield from result.get("value", [])
            path = result.get("@odata.nextLink")

    def recibir(self):
        carpeta_id = os.getenv("MS_FOLDER_ID")
        if not carpeta_id:
            carpetas = self.coleccion(self.base + "/mailFolders/inbox/childFolders?$select=id,displayName")
            carpeta_id = next((f["id"] for f in carpetas if f["displayName"].casefold() == "solicitudes"), None)
        if not carpeta_id:
            raise RuntimeError("Crea la subcarpeta Solicitudes en Bandeja de entrada y una regla de recepción.")
        query = urlencode({"$top": 100, "$select": "id,internetMessageId,subject,body,from,receivedDateTime,categories,conversationId,internetMessageHeaders"})
        mensajes = list(self.coleccion(self.base + "/mailFolders/" + quote(carpeta_id, safe="") + "/messages?" + query))
        for m in mensajes:
            db.registrar_hilo_correo("graph", self.buzon, m.get("conversationId", ""), m.get("internetMessageId") or m["id"])
        for m in mensajes:
            if "SIN TICKET" in m.get("categories", []):
                continue
            mid = m.get("internetMessageId") or m["id"]
            hilo = m.get("conversationId", "")
            if db.existe_id_correo(mid):
                db.registrar_hilo_correo("graph", self.buzon, hilo, mid)
                continue
            headers = {h["name"].lower(): h["value"] for h in m.get("internetMessageHeaders", [])}
            responde_a = headers.get("in-reply-to", "").strip()
            codigo = (db.codigo_por_correo(responde_a) or db.codigo_por_hilo("graph", self.buzon, hilo)) if responde_a else None
            remitente = (m.get("from") or {}).get("emailAddress", {}).get("address", "")
            r = crear_ticket_desde_correo(remitente, m.get("subject", ""), (m.get("body") or {}).get("content", ""), mid,
                                          m.get("receivedDateTime", "")[:10] or None, codigo_ticket=codigo)
            if r["ok"]:
                db.registrar_hilo_correo("graph", self.buzon, hilo, mid)
            categorias = list(m.get("categories", [])) + ([r["codigo"]] if r["ok"] else ["SIN TICKET"])
            self.request(self.base + "/messages/" + quote(m["id"], safe=""), "PATCH",
                         {"categories": list(dict.fromkeys(categorias)), **({"isRead": True} if r["ok"] else {})})

    def enviar(self):
        while True:
            with db.conexion() as con:
                con.execute("BEGIN IMMEDIATE")
                r = con.execute("SELECT * FROM correo_salida WHERE estado='pendiente' ORDER BY id LIMIT 1").fetchone()
                if not r:
                    return
                con.execute("UPDATE correo_salida SET estado='procesando' WHERE id=?", (r["id"],))
            try:
                original, interno = db.origen_borrador(r["ticket_id"], r["destinatario"], self.buzon)
                if interno:
                    with db.conexion() as con:
                        con.execute("UPDATE correo_salida SET estado='omitido',error='Aviso interno: no se crea un borrador adicional' WHERE id=?", (r["id"],))
                    continue
                if original:
                    if original.startswith("<"):
                        query = urlencode({"$filter": "internetMessageId eq '" + original.replace("'", "''") + "'", "$select": "id"})
                        mensaje = next(self.coleccion(self.base + "/messages?" + query), None)
                    else:
                        mensaje = self.request(self.base + "/messages/" + quote(original, safe=""))
                    if not mensaje or not mensaje.get("id"):
                        raise RuntimeError("No se encontró el correo original; no se creará un correo nuevo.")
                    borrador = self.request(self.base + "/messages/" + quote(mensaje["id"], safe="") + "/createReply", "POST", {"comment": r["cuerpo"]})
                    if not borrador.get("id"):
                        raise RuntimeError("No se pudo confirmar el borrador de respuesta; revisar Borradores.")
                else:
                    self.request(self.base + "/messages", "POST", {
                        "subject": r["asunto"], "body": {"contentType": "Text", "content": r["cuerpo"]},
                        "toRecipients": [{"emailAddress": {"address": r["destinatario"]}}]})
            except Exception as exc:
                # Retry throttling/auth rejection safely; ambiguous send failures require human review.
                seguro = isinstance(exc, HTTPError) and exc.code in (401, 403, 429)
                with db.conexion() as con:
                    con.execute("UPDATE correo_salida SET estado=?,error=? WHERE id=?",
                                ("pendiente" if seguro else "revisar", "Envío rechazado; revisar configuración" if seguro else "Revisar Borradores antes de reintentar", r["id"]))
                raise
            else:
                with db.conexion() as con:
                    con.execute("UPDATE correo_salida SET estado='borrador',error=NULL WHERE id=?", (r["id"],))


def main():
    logging.basicConfig(level=logging.INFO)
    db.iniciar()
    while True:
        try:
            g = Graph()
            g.recibir()
            g.enviar()
            db.servicio_actualizar("Microsoft 365 conectado · revisión completada")
        except Exception as exc:
            # Do not log OAuth bodies or secrets.
            db.servicio_actualizar("Microsoft 365 sin conexión: revisar credenciales y permisos en el servidor")
            logging.error("Error de correo: %s", type(exc).__name__)
        time.sleep(max(15, int(os.getenv("CORREO_INTERVALO", "15"))))


if __name__ == "__main__":
    main()
