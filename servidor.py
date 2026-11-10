"""Portal con sesión HTTP persistente y lector de correo opcional."""
import asyncio
import os
import signal
import socket
from pathlib import Path
import subprocess
import sys

from aiohttp import ClientSession, web

RAIZ = Path(__file__).resolve().parent
sys.path.insert(0, str(RAIZ / "src"))
import db
from servidor_sesion import crear_app


def url_publica(puerto):
    return (os.getenv("PORTAL_URL", "").strip() or os.getenv("RENDER_EXTERNAL_URL", "").strip()).rstrip("/") or f"http://localhost:{puerto}"


def comprobar_puertos(puerto, interno):
    for nombre, numero in (("publico", puerto), ("interno", interno)):
        with socket.socket() as comprobacion:
            comprobacion.settimeout(.5)
            if comprobacion.connect_ex(("127.0.0.1", numero)) == 0:
                raise RuntimeError(f"El puerto {nombre} {numero} ya esta ocupado. Si el portal esta abierto, usa {url_publica(puerto)}. Para reiniciarlo, cierra su ventana anterior. No se elegira otro enlace ni puerto.")


def linea_visible(linea):
    texto = linea.strip()
    return bool(texto) and texto != "You can now view your Streamlit app in your browser." and not texto.startswith(("URL: http://", "URL: https://", "Local URL:", "Network URL:", "External URL:"))


async def mostrar_salida(portal):
    while True:
        linea = await asyncio.to_thread(portal.stdout.readline)
        if not linea:
            return
        if linea_visible(linea):
            print(linea.rstrip(), flush=True)


async def esperar_backend(portal, interno):
    async with ClientSession() as cliente:
        for _ in range(120):
            if portal.poll() is not None:
                raise RuntimeError("El servicio interno se cerro antes de iniciar. Revisa el error mostrado arriba.")
            try:
                async with cliente.get(f"http://127.0.0.1:{interno}/_stcore/health", timeout=1) as respuesta:
                    if respuesta.status == 200:
                        return
            except (OSError, asyncio.TimeoutError):
                pass
            await asyncio.sleep(.25)
    raise RuntimeError("El servicio interno no termino de iniciar; no se cambio de puerto.")


async def main():
    if os.getenv("PORTAL_CLOUD") == "1" and len(os.getenv("SETUP_TOKEN", "")) < 24:
        raise SystemExit("Configura SETUP_TOKEN con al menos 24 caracteres aleatorios en el alojamiento.")
    db.iniciar()
    puerto = int(os.getenv("PORT", "8502"))
    interno = int(os.getenv("PORT_INTERNO", str(puerto + 1)))
    if interno == puerto:
        raise SystemExit("PORT_INTERNO debe ser distinto de PORT.")
    comprobar_puertos(puerto, interno)
    entorno = dict(os.environ, PORTAL_AUTH_HTTP="1", BROWSER="none")
    portal = subprocess.Popen([sys.executable, "-m", "streamlit", "run", "app/plataforma.py",
        "--server.address=127.0.0.1", f"--server.port={interno}", "--server.headless=true", "--theme.base=light"], cwd=RAIZ, env=entorno, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1)
    salida = asyncio.create_task(mostrar_salida(portal))
    correo = None
    runner = web.AppRunner(crear_app(f"http://127.0.0.1:{interno}"), access_log=None, shutdown_timeout=3)
    try:
        await esperar_backend(portal, interno)
        await runner.setup()
        direccion = "0.0.0.0" if os.getenv("PORTAL_CLOUD") == "1" or os.getenv("PORTAL_RED") == "1" else "127.0.0.1"
        await web.TCPSite(runner, direccion, puerto).start()
        print(f"Portal disponible: {url_publica(puerto)} — utiliza siempre esta misma direccion.", flush=True)
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
        await salida
        portal.stdout.close()


if __name__ == "__main__":
    signal.signal(signal.SIGTERM, signal.default_int_handler)
    if hasattr(signal, "SIGBREAK"):
        def interrumpir(_signum, _frame):
            raise KeyboardInterrupt
        signal.signal(signal.SIGBREAK, interrumpir)
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
    except (OSError, RuntimeError) as exc:
        print(f"No se pudo iniciar el portal: {exc}", file=sys.stderr, flush=True)
        raise SystemExit(1)
