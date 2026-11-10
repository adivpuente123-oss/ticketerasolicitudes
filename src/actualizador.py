"""Inicio opcional: seguir main sin sobrescribir modificaciones locales."""
import os
from pathlib import Path
import signal
import subprocess
import sys
import time

RAIZ = Path(__file__).resolve().parents[1]
REPOSITORIOS = {
    'https://github.com/adivpuente123-oss/ticketerasolicitudes',
    'git@github.com:adivpuente123-oss/ticketerasolicitudes',
}


def git(*args):
    return subprocess.run(['git', *args], cwd=RAIZ, text=True, capture_output=True, timeout=45, check=True).stdout.strip()


def comprobar_actualizacion():
    """Retorna el commit nuevo, o None si no es seguro actualizar esta copia."""
    if git('remote', 'get-url', 'origin').removesuffix('.git') not in REPOSITORIOS:
        raise ValueError('El origen debe ser el repositorio oficial de la ticketera.')
    if git('branch', '--show-current') != 'main':
        raise ValueError('Selecciona la rama main para usar el inicio automático.')
    if git('status', '--porcelain'):
        raise ValueError('Hay archivos locales sin guardar en Git. No se sobrescribirán.')
    git('fetch', 'origin', 'main')
    anterior, nuevo = git('rev-parse', 'HEAD'), git('rev-parse', 'origin/main')
    if anterior == nuevo:
        return None
    git('merge-base', '--is-ancestor', anterior, nuevo)
    if git('show', 'HEAD:requirements.txt') != git('show', 'origin/main:requirements.txt'):
        raise ValueError('La versión nueva cambia dependencias. Cierra el portal, ejecuta git pull origin main e instalar.bat una vez; después vuelve a iniciar este archivo.')
    if git('show', 'HEAD:src/actualizador.py') != git('show', 'origin/main:src/actualizador.py'):
        raise ValueError('La versión nueva cambia el actualizador. Actualiza con git pull origin main y vuelve a abrir el inicio automático.')
    return nuevo


def iniciar_portal():
    opciones = {'creationflags': subprocess.CREATE_NEW_PROCESS_GROUP} if os.name == 'nt' else {'start_new_session': True}
    return subprocess.Popen([sys.executable, 'servidor.py'], cwd=RAIZ, **opciones)


def detener_portal(proceso):
    if proceso.poll() is not None:
        return
    if os.name == 'nt':
        proceso.send_signal(signal.CTRL_BREAK_EVENT)
    else:
        os.killpg(proceso.pid, signal.SIGINT)
    try:
        proceso.wait(timeout=15)
    except subprocess.TimeoutExpired:
        if os.name == 'nt':
            subprocess.run(['taskkill', '/PID', str(proceso.pid), '/T', '/F'], capture_output=True, check=False)
        else:
            os.killpg(proceso.pid, signal.SIGKILL)
        proceso.wait()


def main():
    intervalo = max(30, int(os.getenv('ACTUALIZACION_SEGUNDOS', '60')))
    proceso = None
    try:
        try:
            nuevo = comprobar_actualizacion()
            if nuevo:
                git('merge', '--ff-only', nuevo)
                print('Actualización inicial descargada.', flush=True)
        except (ValueError, subprocess.SubprocessError, OSError):
            print('No se pudo actualizar al inicio. Se usará la copia local; revisa Git, la conexión y las dependencias.', flush=True)
        proceso = iniciar_portal()
        print(f'Actualizaciones de main cada {intervalo} segundos. Deja esta ventana abierta. Ctrl+C para cerrar.', flush=True)
        proxima = time.monotonic() + intervalo
        while proceso.poll() is None:
            time.sleep(1)
            if time.monotonic() < proxima:
                continue
            proxima = time.monotonic() + intervalo
            try:
                nuevo = comprobar_actualizacion()
                if not nuevo:
                    continue
                detener_portal(proceso)
                try:
                    git('merge', '--ff-only', nuevo)
                finally:
                    proceso = iniciar_portal()
                print('Portal actualizado. Recarga tu navegador. La base de datos se conserva.', flush=True)
            except ValueError as exc:
                print(str(exc), flush=True)
            except (subprocess.SubprocessError, OSError):
                print('No se pudo actualizar. Se reintentará; no se sobrescribieron cambios locales.', flush=True)
    except KeyboardInterrupt:
        pass
    finally:
        if proceso is not None:
            detener_portal(proceso)


if __name__ == '__main__':
    main()
