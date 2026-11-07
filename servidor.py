"""Arranque conjunto web + correo, una instancia y una base persistente local."""
import os
import subprocess
import sys
import time

if os.getenv("PORTAL_CLOUD") == "1" and len(os.getenv("SETUP_TOKEN", "")) < 24:
    raise SystemExit("Configura SETUP_TOKEN con al menos 24 caracteres aleatorios en el alojamiento.")

web = subprocess.Popen([sys.executable, "-m", "streamlit", "run", "app/plataforma.py", "--server.address=0.0.0.0",
                        "--server.port=" + os.getenv("PORT", "8502"), "--server.headless=true", "--theme.base=light"])
correo = None
try:
    while web.poll() is None:
        if os.getenv("CORREO_MODO") == "graph" and (correo is None or correo.poll() is not None):
            correo = subprocess.Popen([sys.executable, "src/servicio_graph.py"])
        time.sleep(2)
finally:
    if correo and correo.poll() is None:
        correo.terminate()
        correo.wait(timeout=15)
    if web.poll() is None:
        web.terminate()
