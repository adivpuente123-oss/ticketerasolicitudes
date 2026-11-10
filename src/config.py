"""Configuración del proyecto. Aquí cambias rutas y reglas de negocio."""
import os
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent



def _buscar_excel() -> Path:
    """Usa el Excel (.xlsx o .xlsm) más reciente de data/raw, con cualquier nombre."""
    carpeta = RAIZ / "data" / "raw"
    candidatos = [p for p in carpeta.glob("*.xls[xm]") if not p.name.startswith("~$")]
    if candidatos:
        return max(candidatos, key=lambda p: p.stat().st_mtime)
    return carpeta / "REGISTRO SOLICITUDES.xlsx"


# Ruta del Excel. Por defecto se detecta sola. Para fijarla (incluso una carpeta compartida de la red),
# escribe la ruta aquí, por ejemplo: Path(r"\\SERVIDOR\carpeta\REGISTRO SOLICITUDES.xlsm")
# También puedes definir la variable de entorno RUTA_EXCEL.
RUTA_EXCEL = Path(os.getenv("RUTA_EXCEL", _buscar_excel()))

CARTERAS = ["IBK", "BBVA", "OTROS"]
NO_SUPERVISORES = ["ENTIDAD", "CLIENTE", "ASESORIA", "SIN ASIGNAR"]   # no entran al ranking
CORTES_RANKING = (90, 70, 40)       # % de solicitudes respondidas que separa los 4 niveles
DIAS_ALERTA_PENDIENTE = 30          # enviadas sin respuesta con más días que esto se marcan
DIAS_ALERTA_ACUERDO = 45            # acuerdo con cuotas pendientes y sin pago hace más días que esto
REFRESCO_SEGUNDOS = 60              # cada cuánto la página revisa si guardaste el Excel

# ---------- Plataforma de solicitudes (tickets) ----------
RUTA_DB = Path(os.getenv("RUTA_DB", RAIZ / "db" / "plataforma.db"))
TIPO_TRANSACCION = "Transacción Extrajudicial"
TIPOS_CONSULTA = ["Canceló con entidad original", "Actualización de centrales", "Acuerdo con entidad", TIPO_TRANSACCION]
ESTADOS_TICKET = ["Recibida", "Enviada a verificar", "Respondida"]
CONCLUSIONES = ["PROCEDENTE", "IMPROCEDENTE"]      # Respondida puede ser positiva (procedente) o negativa (improcedente)
CORRESPONDE = ["Alícuota", "Posible alícuota", "No aplica"]
