"""Lee la carpeta «Solicitudes» de tu Outlook y crea un ticket por cada correo nuevo de un supervisor registrado.

Uso:   python src\\leer_outlook.py              (una pasada)
       python src\\leer_outlook.py --cada 5     (se repite cada 5 minutos; déjalo abierto en una ventana)

Requiere Windows con Outlook de escritorio abierto y:  pip install pywin32
Antes: crea en Outlook la carpeta «Solicitudes» (dentro de la Bandeja de entrada) y una regla que mueva allí los
correos de tus supervisores. El script solo lee esa carpeta; nunca toca el resto de tu bandeja.
"""
import argparse
import sys
import time
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import db
from correo import crear_ticket_desde_correo


def remitente_de(item) -> str:
    """Dirección de correo del remitente (en Exchange hay que resolverla)."""
    if str(getattr(item, "SenderEmailType", "")).upper() == "EX":
        try:
            return item.Sender.GetExchangeUser().PrimarySmtpAddress
        except Exception:  # noqa: BLE001
            return ""
    return str(getattr(item, "SenderEmailAddress", "") or "")


def fecha_de(item):
    try:
        return item.ReceivedTime.strftime("%Y-%m-%d")
    except Exception:  # noqa: BLE001
        return None


def procesar_item(item) -> str:
    """Convierte un correo en ticket y lo marca. Devuelve un texto con lo que pasó."""
    categorias = str(getattr(item, "Categories", "") or "")
    if "SOL-" in categorias or "SIN TICKET" in categorias:
        return "omitido"
    r = crear_ticket_desde_correo(remitente_de(item), str(item.Subject or ""), str(item.Body or ""),
                                  id_correo=str(item.EntryID), fecha=fecha_de(item))
    if r["ok"]:
        item.Categories = r["codigo"]
        item.UnRead = False
        item.Save()
        faltan = f" (por completar: {', '.join(r['datos']['faltantes'])})" if r["datos"]["faltantes"] else ""
        return f"{r['codigo']} creado para {r['supervisor']}{faltan}"
    if r.get("duplicado"):
        item.UnRead = False
        item.Save()
        return "ya tenía ticket"
    item.Categories = "SIN TICKET: remitente no registrado"
    item.Save()
    return r["motivo"]


def una_pasada(nombre_carpeta: str) -> int:
    import win32com.client  # pip install pywin32
    espacio = win32com.client.Dispatch("Outlook.Application").GetNamespace("MAPI")
    try:
        carpeta = espacio.GetDefaultFolder(6).Folders(nombre_carpeta)   # 6 = Bandeja de entrada
    except Exception:  # noqa: BLE001
        raise SystemExit(f"No encuentro la carpeta «{nombre_carpeta}» dentro de tu Bandeja de entrada.")
    creados = 0
    for item in list(carpeta.Items):
        if getattr(item, "UnRead", False):
            texto = procesar_item(item)
            if texto != "omitido":
                print(f"[{datetime.now():%H:%M:%S}] {item.Subject[:50]!r}: {texto}")
                creados += texto.startswith("SOL-")
    return creados


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--carpeta", default="Solicitudes")
    p.add_argument("--cada", type=float, default=0, help="minutos entre revisiones; 0 = una sola pasada")
    a = p.parse_args()
    db.iniciar()
    while True:
        print(f"[{datetime.now():%H:%M:%S}] Revisando la carpeta «{a.carpeta}»... tickets nuevos: {una_pasada(a.carpeta)}")
        if not a.cada:
            break
        time.sleep(a.cada * 60)
