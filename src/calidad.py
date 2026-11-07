"""Revisión de calidad de los datos: encuentra errores del Excel antes de que distorsionen los números."""
from difflib import SequenceMatcher

import pandas as pd

from config import NO_SUPERVISORES


def posibles_tipeos(nombres: pd.Series) -> dict:
    """Nombres casi iguales (ej. MELITA / MELINA). Devuelve {nombre_raro: nombre_común}."""
    veces = nombres.value_counts()
    lista = [n for n in veces.index if n not in NO_SUPERVISORES]
    raros = {}
    for i, a in enumerate(lista):
        for b in lista[i + 1:]:
            if SequenceMatcher(None, a, b).ratio() >= 0.8:
                raro, comun = (a, b) if veces[a] <= veces[b] else (b, a)
                raros[raro] = comun
    return raros


def revisar(sol: pd.DataFrame, ali: pd.DataFrame, acu: pd.DataFrame):
    """Devuelve (resumen por revisión, detalle fila por fila, % de filas sin observaciones, total de filas)."""
    hoy = pd.Timestamp.today().normalize()
    tip = posibles_tipeos(sol["supervisor"])
    hoja_a = pd.Series("ALÍCUOTA", index=ali.index)
    hoja_k = pd.Series("CASOS", index=acu.index)
    sup = sol["supervisor"]
    otros = sup.isin(NO_SUPERVISORES) & (sup != "SIN ASIGNAR")
    # (tabla, hoja, condición, problema, gravedad, dónde corregirlo, dato a mostrar)
    reglas = [
        (sol, sol["cartera"], sup == "SIN ASIGNAR", "Solicitud sin supervisor", "Media", "Columna SOLICITUD", sup),
        (sol, sol["cartera"], sup.isin(tip.keys()), "Posible error de tipeo en el supervisor", "Media", "Columna SOLICITUD",
         sup.map(lambda s: f"{s} (¿{tip[s]}?)" if s in tip else s)),
        (sol, sol["cartera"], sol["fecha_solicitud"].isna(), "Sin fecha de solicitud", "Alta", "Columna FECHA DE SOLICITUD", sup),
        (sol, sol["cartera"], sol["fecha_envio"] < sol["fecha_solicitud"], "Envío anterior a la solicitud", "Alta",
         "Columnas FECHA DE SOLICITUD y FECHA DE ENVÍO", sup),
        (sol, sol["cartera"], (sol["fecha_solicitud"] > hoy) | (sol["fecha_envio"] > hoy), "Fecha en el futuro", "Media",
         "Columnas de fechas", sup),
        (sol, sol["cartera"], sol["resuelto_vacio"], "RESUELTO vacío", "Media", "Columna RESUELTO", sup),
        (sol, sol["cartera"], sol["es_respondida"] & sol["fecha_envio"].isna(), "Respondida sin fecha de envío", "Media",
         "Columna FECHA DE ENVÍO", sup),
        (sol, sol["cartera"], sol["es_respondida"] & (sol["conclusion"] == "SIN CONCLUSIÓN"), "Respondida sin conclusión (falta indicar si fue positiva o negativa)", "Alta",
         "Columna CONCLUSIÓN", sup),
        (sol, sol["cartera"], ~sol["es_respondida"] & sol["conclusion"].isin(["PROCEDENTE", "IMPROCEDENTE"]),
         "Tiene conclusión pero no figura como respondida", "Media", "Columnas RESUELTO y CONCLUSIÓN", sup),
        (sol, sol["cartera"], sol["duplicada"], "Solicitud duplicada", "Media", "Fila repetida", sup),
        (sol, sol["cartera"], sol["tipo_consulta"] == "Sin tipo", "Sin tipo de consulta", "Media", "Columna TIPO DE CONSULTA", sup),
        (sol, sol["cartera"], otros, "Solicitante que no es supervisor (ENTIDAD, CLIENTE, ASESORIA)", "Info",
         "Columna SOLICITUD (no se rankean)", sup),
        (ali, hoja_a, (ali["alicuota_calculada"] > 0) & (ali["pagado_entidad"] > ali["alicuota_calculada"] * 1.01),
         "Pagado mayor que la alícuota calculada (confirmar si es normal)", "Info", "Columnas PAY_BD y PAY_ENTIDAD", ali["cartera"]),
        (ali, hoja_a, (ali["alicuota_calculada"] == 0) & (ali["dk"] > 0), "Alícuota en cero con deuda (confirmar si corresponde)", "Info",
         "Columna PAY_BD", ali["cartera"]),
        (ali, hoja_a, (ali["estado_alicuota"] == "Pagado") & (ali["pagado_entidad"] == 0),
         "Marcado como PAGADO pero sin monto pagado (infla el 'por recuperar')", "Alta",
         "Columna PAY_ENTIDAD", ali["cartera"]),
        (ali, hoja_a, (ali["pagado_entidad"] > 0) & ali["fecha_pago"].isna(), "Pagado sin fecha de pago", "Media",
         "Columna FECHA DE PAGO", ali["cartera"]),
        (ali, hoja_a, ali["estado_alicuota"] == "Sin sustento de pago", "Pago sin sustento", "Info",
         "Pedir el sustento a la entidad", ali["cartera"]),
        (acu, hoja_k, acu["ultimo_pago"].isna() & (acu["total_pagado"] > 0), "Acuerdo con pagos pero sin fecha de último pago",
         "Media", "Columna ultimo pago", acu["producto"]),
        (acu, hoja_k, (acu["plazo"] > 0) & ((acu["cuotas_pagadas"] + acu["cuotas_restantes"]) > acu["plazo"]),
         "Cuotas pagadas más restantes exceden el plazo", "Media", "Columnas de cuotas", acu["producto"]),
    ]
    filas, detalle = [], []
    for df, hoja, mask, problema, gravedad, donde, dato in reglas:
        mask = mask.fillna(False)
        filas.append({"Gravedad": gravedad, "Revisión": problema, "Dónde corregirlo": donde, "Cantidad": int(mask.sum())})
        if mask.any():
            detalle.append(pd.DataFrame({"Hoja": hoja[mask], "Fila Excel": df["fila_excel"][mask], "Problema": problema,
                                         "Gravedad": gravedad, "Dato": dato[mask].astype(str)}))
    resumen = pd.DataFrame(filas)
    detalle = (pd.concat(detalle, ignore_index=True) if detalle else
               pd.DataFrame(columns=["Hoja", "Fila Excel", "Problema", "Gravedad", "Dato"]))
    total = len(sol) + len(ali) + len(acu)
    con_error = detalle[detalle["Gravedad"].isin(["Alta", "Media"])].drop_duplicates(["Hoja", "Fila Excel"])
    puntaje = round((1 - len(con_error) / total) * 100) if total else 100
    return resumen, detalle, puntaje, total
