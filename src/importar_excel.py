"""Importa las solicitudes del Excel a la plataforma (se hace una vez, para empezar con tu historial).

Uso:  python src/importar_excel.py "data/raw/REGISTRO SOLICITUDES.xlsm"
      python src/importar_excel.py "data/raw/REGISTRO SOLICITUDES.xlsm" --reemplazar   (borra lo importado antes y vuelve a importar)
"""
import argparse
import re
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
import db
from config import CARTERAS, NO_SUPERVISORES
from datos import clave, leer_hoja, texto

CORRESPONDE = {"ALICUOTA": "Alícuota", "POSIBLE ALICUOTA": "Posible alícuota", "NO APLICA": "No aplica"}


def _fecha(v):
    f = pd.to_datetime(v, errors="coerce")
    return None if pd.isna(f) else f.strftime("%Y-%m-%d")


def _limpio(v) -> str:
    return re.sub(r"\.0$", "", "" if pd.isna(v) else str(v).strip())


def leer_filas(ruta) -> list:
    filas = []
    with pd.ExcelFile(ruta) as xl:
        for cartera in CARTERAS:
            df = leer_hoja(xl, cartera, "DOCUMENTO")
            for _, r in df[df["DOCUMENTO"].notna()].iterrows():
                v = lambda n: r[n] if n in r.index else None
                fe, conc = _fecha(v("FECHA DE ENVÍO")), clave(v("CONCLUSIÓN"))
                respondida = clave(v("RESUELTO")) == "SI"      # SI = la entidad ya respondió (positiva o negativa)
                filas.append(dict(
                    cartera=cartera, supervisor=texto(pd.Series([v("SOLICITUD")]))[0].upper() or "SIN ASIGNAR",
                    tipo_consulta=texto(pd.Series([v("TIPO DE CONSULTA")]))[0] or "Sin tipo",
                    documento=_limpio(v("DOCUMENTO")), cuenta=_limpio(v("CUENTA")),
                    fecha_solicitud=_fecha(v("FECHA DE SOLICITUD")), fecha_envio=fe,
                    estado="Respondida" if respondida else ("Enviada a verificar" if fe else "Recibida"),
                    conclusion=conc if conc in ("PROCEDENTE", "IMPROCEDENTE") else None,
                    estado_corresponde=CORRESPONDE.get(clave(v("ESTADO CORRESPONDE"))),
                    sustento=texto(pd.Series([v("SUSTENTO")]))[0] or None, fila=int(r["fila_excel"])))
    return sorted(filas, key=lambda f: (f["fecha_solicitud"] or "9999", f["cartera"], f["fila"]))


def importar(ruta, reemplazar=False) -> int:
    db.iniciar()
    with db.conexion() as con:
        ya = con.execute("SELECT COUNT(*) FROM tickets WHERE origen = 'excel'").fetchone()[0]
        if ya and not reemplazar:
            raise SystemExit(f"Ya hay {ya} tickets importados. Usa --reemplazar para volver a importar.")
        if ya:
            con.execute("DELETE FROM tickets WHERE origen = 'excel'")
    ids = {}
    filas = leer_filas(ruta)
    for f in filas:
        if f["supervisor"] not in ids:
            ids[f["supervisor"]] = db.id_supervisor(f["supervisor"], activo=0 if f["supervisor"] in NO_SUPERVISORES else 1)
        extra = {k: f[k] for k in ("fecha_envio", "conclusion", "estado_corresponde", "sustento") if f[k]}
        db.crear_ticket(ids[f["supervisor"]], f["cartera"], f["tipo_consulta"], f["documento"], f["cuenta"], "",
                        origen="excel", fecha_solicitud=f["fecha_solicitud"], estado=f["estado"],
                        detalle=f"Importado del Excel (hoja {f['cartera']}, fila {f['fila']})"
                                + ("" if f["fecha_solicitud"] else ". El Excel no traía fecha de solicitud: se usó la de hoy"), **extra)
    return len(filas)


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("excel")
    p.add_argument("--reemplazar", action="store_true")
    a = p.parse_args()
    print(f"Importados {importar(Path(a.excel), a.reemplazar)} tickets en {db.RUTA_DB}")
