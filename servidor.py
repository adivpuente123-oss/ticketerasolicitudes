"""Portal con sesión HTTP persistente y lector de correo opcional."""
import asyncio
import os
from pathlib import Path
import subprocess
import sys

from aiohttp import web

RAIZ = Path(__file__).resolve().parent
sys.path.insert(0, str(RAIZ / "src"))
import db
from servidor_sesion import crear_app


async def main():
    if os.getenv("PORTAL_CLOUD") == "1" and len(os.getenv("SETUP_TOKEN", "")) < 24:
        raise SystemExit("Configura SETUP_TOKEN con al menos 24 caracteres aleatorios en el alojamiento.")
    db.iniciar()
    puerto = int(os.getenv("PORT", "8502"))
    interno = int(os.getenv("PORT_INTERNO", str(puerto + 1)))
    if interno == puerto:
        raise SystemExit("PORT_INTERNO debe ser distinto de PORT.")
    entorno = dict(os.environ, PORTAL_AUTH_HTTP="1")
    portal = subprocess.Popen([sys.executable, "-m", "streamlit", "run", "app/plataforma.py",
        "--server.address=127.0.0.1", f"--server.port={interno}", "--server.headless=true", "--theme.base=light"], cwd=RAIZ, env=entorno)
    correo = None
    runner = web.AppRunner(crear_app(f"http://127.0.0.1:{interno}"), access_log=None)
    try:
        await runner.setup()
        direccion = "0.0.0.0" if os.getenv("PORTAL_CLOUD") == "1" or os.getenv("PORTAL_RED") == "1" else "127.0.0.1"
        await web.TCPSite(runner, direccion, puerto).start()
        print(f"Portal: http://localhost:{puerto}", flush=True)
        while portal.poll() is None:
            if os.getenv("CORREO_MODO") == "graph" and (correo is None or correo.poll() is not None):
                correo = subprocess.Popen([sys.executable, "src/servicio_graph.py"], cwd=RAIZ)
            await asyncio.sleep(1)
    finally:
        await runner.cleanup()
        for proceso in (correo, portal):
            if proceso and proceso.poll() is None:
                proceso.terminate()
                try:
                    await asyncio.to_thread(proceso.wait, timeout=10)
                except subprocess.TimeoutExpired:
                    proceso.kill()
                    await asyncio.to_thread(proceso.wait)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
