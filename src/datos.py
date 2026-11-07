"""Lectura y limpieza del Excel. Aquí vive la lógica de negocio del dashboard."""
import shutil
import tempfile
import unicodedata
from pathlib import Path

import numpy as np
import pandas as pd

from config import CARTERAS, DIAS_ALERTA_ACUERDO


def clave(valor) -> str:
    """Mayúsculas y sin tildes, para comparar sin errores ('ALÍCUOTA' == 'ALICUOTA')."""
    if pd.isna(valor):
        return ""
    texto = unicodedata.normalize("NFD", str(valor)).encode("ascii", "ignore").decode()
    return texto.strip().upper()


def texto(serie: pd.Series) -> pd.Series:
    """Convierte a texto limpio; los vacíos quedan como ''."""
    return serie.map(lambda x: "" if pd.isna(x) else str(x).strip())


def col(df: pd.DataFrame, nombre: str) -> pd.Series:
    """Devuelve la columna si existe; si no, una columna vacía (así un cambio en el Excel no rompe todo)."""
    return df[nombre] if nombre in df.columns else pd.Series(np.nan, index=df.index, dtype=object)


def leer_hoja(xl: pd.ExcelFile, hoja: str, columna_clave: str) -> pd.DataFrame:
    """Lee una hoja encontrando sola la fila de encabezados (a veces hay filas vacías arriba)."""
    bruto = pd.read_excel(xl, sheet_name=hoja, header=None, dtype=object)
    for i in range(min(10, len(bruto))):
        encabezados = bruto.iloc[i].astype(str).str.strip().tolist()
        if columna_clave in encabezados:
            df = bruto.iloc[i + 1:].copy()
            df.columns = encabezados
            df["fila_excel"] = df.index + 1   # número de fila en el Excel, para ubicar errores
            return df.reset_index(drop=True)
    raise ValueError(f"No encontré la columna '{columna_clave}' en la hoja '{hoja}'")


def cargar_solicitudes(xl: pd.ExcelFile) -> pd.DataFrame:
    partes = []
    for cartera in CARTERAS:
        df = leer_hoja(xl, cartera, "DOCUMENTO")
        df = df[df["DOCUMENTO"].notna()]
        dup = pd.DataFrame({k: col(df, k) for k in ("DOCUMENTO", "CUENTA", "FECHA DE SOLICITUD", "TIPO DE CONSULTA")}).duplicated()
        partes.append(pd.DataFrame({
            "cartera": cartera,
            "fila_excel": df["fila_excel"],
            "duplicada": dup,
            "supervisor": col(df, "SOLICITUD"),
            "tipo_consulta": col(df, "TIPO DE CONSULTA"),
            "cuenta": col(df, "CUENTA"),
            "dk": col(df, "DK"),
            "fecha_solicitud": col(df, "FECHA DE SOLICITUD"),
            "fecha_envio": col(df, "FECHA DE ENVÍO"),
            "resuelto": col(df, "RESUELTO"),
            "conclusion": col(df, "CONCLUSIÓN"),
            "cosecha": col(df, "COSECHA"),
            "estado_corresponde": col(df, "ESTADO CORRESPONDE"),
        }))
    s = pd.concat(partes, ignore_index=True)

    s["resuelto_vacio"] = texto(s["resuelto"]) == ""
    s["supervisor"] = texto(s["supervisor"]).str.upper().replace("", "SIN ASIGNAR")
    s["tipo_consulta"] = texto(s["tipo_consulta"]).replace("", "Sin tipo")
    s["dk"] = pd.to_numeric(s["dk"], errors="coerce").fillna(0.0)
    for c in ("fecha_solicitud", "fecha_envio"):
        s[c] = pd.to_datetime(s[c], errors="coerce")

    # Estado: la regla de negocio principal
    # RESUELTO = SI significa que la entidad YA RESPONDIÓ (respuesta positiva o negativa).
    # Si la respuesta fue favorable o no, se ve en CONCLUSIÓN (PROCEDENTE / IMPROCEDENTE).
    resuelto = s["resuelto"].map(clave) == "SI"
    s["estado"] = np.select([resuelto, s["fecha_envio"].isna()],
                            ["Respondida", "Por enviar"], default="Enviada sin respuesta")
    concl = s["conclusion"].map(clave)
    s["conclusion"] = np.where(concl.isin(["PROCEDENTE", "IMPROCEDENTE"]), concl, "SIN CONCLUSIÓN")
    s["estado_corresponde"] = s["estado_corresponde"].map(clave).map({
        "ALICUOTA": "Alícuota", "POSIBLE ALICUOTA": "Posible alícuota", "NO APLICA": "No aplica",
    }).fillna("Sin dato")
    cos = texto(s["cosecha"])
    s["cosecha"] = np.where(cos.str.upper().str.startswith("COSECHA"), cos, "Sin cosecha")

    # Indicadores listos para sumar
    s["es_respondida"] = s["estado"] == "Respondida"
    s["es_sin_resp"] = s["estado"] == "Enviada sin respuesta"
    s["es_por_enviar"] = s["estado"] == "Por enviar"
    s["es_proc"] = s["conclusion"] == "PROCEDENTE"
    s["es_improc"] = s["conclusion"] == "IMPROCEDENTE"

    # Fechas y antigüedad
    hoy = pd.Timestamp.today().normalize()
    s["anio"] = s["fecha_solicitud"].dt.year
    s["mes"] = s["fecha_solicitud"].dt.month
    s["periodo"] = s["fecha_solicitud"].dt.strftime("%Y-%m")
    base = s["fecha_envio"].where(s["es_sin_resp"], s["fecha_solicitud"])
    s["dias_pendiente"] = (hoy - base).dt.days.where(~s["es_respondida"])

    # Privacidad: no se conserva el DNI ni el nombre; la cuenta solo con sus últimos 4 dígitos
    cuenta = texto(s["cuenta"]).str.replace(r"\.0$", "", regex=True)
    s["cuenta_oculta"] = "****" + cuenta.str[-4:]
    return s.drop(columns=["cuenta"])


def cargar_alicuotas(xl: pd.ExcelFile) -> pd.DataFrame:
    df = leer_hoja(xl, "ALÍCUOTA", "DOCUMENTO")
    df = df[df["DOCUMENTO"].notna()]
    ent = col(df, "ENTIDAD").map(clave)
    a = pd.DataFrame({
        "fila_excel": df["fila_excel"],
        "cuenta_oculta": "****" + texto(col(df, "CUENTA")).str.replace(r"\.0$", "", regex=True).str[-4:],
        "cartera": np.select([ent == "INTERBANK", ent == "BBVA"], ["IBK", "BBVA"], default="OTROS"),
        "origen": texto(col(df, "ORIGEN")).replace("", "Sin dato"),
        "dk": pd.to_numeric(col(df, "DK"), errors="coerce").fillna(0.0),
        "alicuota_calculada": pd.to_numeric(col(df, "PAY_BD"), errors="coerce").fillna(0.0),
        "pagado_entidad": pd.to_numeric(col(df, "PAY_ENTIDAD"), errors="coerce").fillna(0.0),
        "blacklist": col(df, "ESTADO DE BLACKLIST").map(clave).map(
            {"ALICUOTA": "Alícuota", "POSIBLE ALICUOTA": "Posible alícuota"}).fillna("Otro o sin dato"),
        "estado_alicuota": col(df, "ESTADO DE ALÍCUOTA").map(clave).map(
            {"PAGADO": "Pagado", "SIN SUSTENTOS DE PAGO": "Sin sustento de pago"}).fillna("Sin dato"),
        "fecha_pago": pd.to_datetime(col(df, "FECHA DE PAGO"), errors="coerce"),
        "cosecha": texto(col(df, "COSECHA")).replace("", "Sin cosecha"),
    })
    a["por_recuperar"] = (a["alicuota_calculada"] - a["pagado_entidad"]).clip(lower=0)
    return a.reset_index(drop=True)


def cargar_acuerdos(xl: pd.ExcelFile) -> pd.DataFrame:
    df = leer_hoja(xl, "CASOS", "MONTO ACUERDO")
    num = lambda nombre: pd.to_numeric(col(df, nombre), errors="coerce").fillna(0.0)
    k = pd.DataFrame({
        "fila_excel": df["fila_excel"],
        "producto": texto(col(df, "PRODUCTO")).replace("", "Sin producto"),
        "monto_acuerdo": num("MONTO ACUERDO"),
        "plazo": num("PLAZO"),
        "total_pagado": num("TOTAL PAGADO"),
        "cuotas_pagadas": num("CUOTAS PAGADAS"),
        "cuotas_restantes": num("CUOTAS RESTANTES"),
        "pendiente": num("IMPORTE RESTANTE A PAGAR"),
        "ultimo_pago": pd.to_datetime(col(df, "ultimo pago"), errors="coerce"),
    })
    k = k[k["monto_acuerdo"] > 0].reset_index(drop=True)
    hoy = pd.Timestamp.today().normalize()
    k["dias_sin_pago"] = (hoy - k["ultimo_pago"]).dt.days
    k["en_riesgo"] = (k["cuotas_restantes"] > 0) & (k["dias_sin_pago"] > DIAS_ALERTA_ACUERDO)
    return k


def cargar_todo(ruta: Path):
    """Copia el Excel a una carpeta temporal (así no falla si alguien lo tiene abierto) y lo procesa."""
    with tempfile.TemporaryDirectory() as tmp:
        copia = Path(tmp) / ("copia" + ruta.suffix)  # conserva .xlsx o .xlsm
        shutil.copy2(ruta, copia)
        with pd.ExcelFile(copia) as xl:
            return cargar_solicitudes(xl), cargar_alicuotas(xl), cargar_acuerdos(xl)
