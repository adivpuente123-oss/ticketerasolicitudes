"""Acceso HTTP con cookie HttpOnly y proxy local de Streamlit (incluye WebSocket)."""
import asyncio
import hmac
import os
import secrets
import time
from collections import defaultdict
from urllib.parse import quote

from aiohttp import ClientSession, WSMsgType, web
import db

COOKIE = "portal_session"
CSRF = "portal_login_csrf"
HOP = {"connection", "keep-alive", "proxy-authenticate", "proxy-authorization", "te", "trailer", "transfer-encoding", "upgrade", "host", "content-length"}


def cookie_segura(request):
    return os.getenv("PORTAL_CLOUD") == "1" or request.secure


def login_html(token, error=""):
    return '''<!doctype html><html lang="es"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Acceso · Solicitudes</title>
<style>*{box-sizing:border-box}body{margin:0;background:#f3f6fb;color:#1e3657;font:15px 'Segoe UI',sans-serif;min-height:100vh;display:grid;place-items:center;padding:24px}.panel{background:white;padding:40px;border-radius:20px;width:100%;max-width:420px;box-shadow:0 15px 50px #1e365712}h1{font-size:27px;margin:8px 0 14px}p{color:#61738d;line-height:1.6}.brand{font-size:12px;color:#315d9d;font-weight:700;letter-spacing:.1em}label{display:block;margin:18px 0 7px}input{width:100%;padding:13px;border:1px solid #ccd7e6;border-radius:9px;font:inherit}button{width:100%;margin-top:24px;background:#315d9d;color:white;border:0;border-radius:9px;padding:14px;font:600 15px 'Segoe UI',sans-serif;cursor:pointer}.error{color:#b4233c}small{display:block;margin-top:20px;color:#71829b;line-height:1.6}input:focus,button:focus-visible{outline:3px solid #a7c6f3;outline-offset:2px}</style>
<main class="panel"><div class="brand">SOLICITUDES</div><h1>Bienvenido de nuevo.</h1><p>Ingresa para consultar y gestionar tus solicitudes.</p>''' + (f'<p class="error" role="alert">{error}</p>' if error else '') + '''<form method="post" action="/_portal/login"><input type="hidden" name="csrf" value="''' + token + '''"><label for="correo">Correo</label><input id="correo" name="correo" type="email" autocomplete="username" required><label for="clave">Contraseña</label><input id="clave" name="clave" type="password" autocomplete="current-password" required><button type="submit">Entrar</button></form><small>Tu sesión se mantiene durante 12 horas, incluso al recargar. En un equipo compartido, cierra la sesión al terminar.</small></main></html>'''


def formulario(request, error="", status=200):
    token = secrets.token_urlsafe(32)
    response = web.Response(text=login_html(token, error), content_type="text/html", status=status,
                            headers={"Cache-Control": "no-store", "X-Content-Type-Options": "nosniff", "Content-Security-Policy": "default-src 'none'; style-src 'unsafe-inline'; form-action 'self'; frame-ancestors 'none'; base-uri 'none'"})
    response.set_cookie(CSRF, token, httponly=True, secure=cookie_segura(request), samesite="Strict", path="/_portal/login", max_age=600)
    return response


async def login(request):
    if not db.hay_backoffice():
        raise web.HTTPSeeOther("/")
    if request.method == "GET":
        if db.usuario_por_sesion(request.cookies.get(COOKIE)):
            raise web.HTTPSeeOther("/")
        response = formulario(request)
        response.del_cookie(COOKIE, path="/")
        return response
    datos = await request.post()
    csrf = datos.get("csrf", "")
    if not isinstance(csrf, str) or not csrf or not hmac.compare_digest(csrf, request.cookies.get(CSRF, "")):
        return formulario(request, "El formulario venció. Vuelve a ingresar.", 403)
    ip = request.remote or "desconocido"
    ahora = time.monotonic()
    intentos = request.app["intentos"]
    intentos[ip] = [t for t in intentos[ip] if ahora - t < 60]
    if len(intentos[ip]) >= 5:
        return formulario(request, "Demasiados intentos. Espera un minuto y vuelve a intentar.", 429)
    correo, clave = datos.get("correo", ""), datos.get("clave", "")
    if not isinstance(correo, str) or not isinstance(clave, str) or len(correo) > 320 or len(clave) > 1024:
        return formulario(request, "Correo o contraseña incorrectos.", 400)
    u = db.usuario_por_correo(correo)
    if not u or not u["activo"] or not db.verificar_clave(clave, u["clave_hash"]):
        intentos[ip].append(ahora)
        return formulario(request, "Correo o contraseña incorrectos, o el usuario está inactivo.", 401)
    db.revocar_sesion(request.cookies.get(COOKIE))
    response = web.HTTPSeeOther("/")
    response.set_cookie(COOKIE, db.crear_sesion(u["id"]), max_age=db.DURACION_SESION,
                        httponly=True, secure=cookie_segura(request), samesite="Lax", path="/")
    response.del_cookie(CSRF, path="/_portal/login")
    response.headers["Cache-Control"] = "no-store"
    return response


async def descargar_adjunto(request):
    usuario = db.usuario_por_sesion(request.cookies.get(COOKIE))
    if not usuario:
        raise web.HTTPUnauthorized(text="Inicia sesión para descargar el documento.")
    try:
        archivo = db.obtener_adjunto(int(request.match_info["id"]), usuario["id"])
    except (PermissionError, ValueError):
        raise web.HTTPNotFound(text="Documento no disponible.")
    return web.Response(body=archivo["datos"], content_type=archivo["tipo_mime"], headers={
        "Content-Disposition": "attachment; filename*=UTF-8''" + quote(archivo["nombre"], safe=""),
        "Cache-Control": "private, no-store", "X-Content-Type-Options": "nosniff"})


async def proxy(request):
    if request.path != "/_stcore/health" and not request.path.startswith("/static/") and db.hay_backoffice() and not db.usuario_por_sesion(request.cookies.get(COOKIE)):
        raise web.HTTPSeeOther("/_portal/login")
    destino = request.app["backend"] + request.rel_url.raw_path_qs
    headers = {k: v for k, v in request.headers.items() if k.lower() not in HOP}
    headers["Host"] = request.host
    client = request.app["client"]
    if request.headers.get("Upgrade", "").lower() == "websocket":
        protocols = [p.strip() for p in request.headers.get("Sec-WebSocket-Protocol", "").split(",") if p.strip()]
        ws_headers = {k: v for k, v in headers.items() if not k.lower().startswith("sec-websocket-")}
        try:
            upstream = await client.ws_connect(destino, headers=ws_headers, protocols=protocols, max_msg_size=32 * 1024 * 1024)
        except Exception:
            return web.Response(status=502, text="No se pudo conectar al portal. Recarga la página.")
        downstream = web.WebSocketResponse(protocols=protocols, max_msg_size=32 * 1024 * 1024)
        await downstream.prepare(request)

        async def relay(origen, objetivo):
            async for msg in origen:
                if msg.type == WSMsgType.TEXT:
                    await objetivo.send_str(msg.data)
                elif msg.type == WSMsgType.BINARY:
                    await objetivo.send_bytes(msg.data)
                elif msg.type in (WSMsgType.CLOSE, WSMsgType.CLOSED, WSMsgType.ERROR):
                    break
        tareas = [asyncio.create_task(relay(upstream, downstream)), asyncio.create_task(relay(downstream, upstream))]
        try:
            await asyncio.wait(tareas, return_when=asyncio.FIRST_COMPLETED)
        finally:
            for tarea in tareas:
                tarea.cancel()
            await asyncio.gather(*tareas, return_exceptions=True)
            await upstream.close()
            await downstream.close()
        return downstream
    try:
        async with client.request(request.method, destino, headers=headers, data=await request.read(), allow_redirects=False) as response:
            salida = web.Response(status=response.status, body=await response.read())
            for k, v in response.headers.items():
                if k.lower() not in HOP:
                    salida.headers.add(k, v)
            return salida
    except (OSError, asyncio.TimeoutError):
        return web.Response(status=502, text="El portal está iniciando. Recarga la página en unos segundos.")


def crear_app(backend):
    app = web.Application(client_max_size=32 * 1024 * 1024)
    app["backend"] = backend
    app["intentos"] = defaultdict(list)

    async def ciclo(app):
        async with ClientSession(auto_decompress=False) as client:
            app["client"] = client
            yield
    app.cleanup_ctx.append(ciclo)
    app.router.add_get("/_portal/adjuntos/{id}", descargar_adjunto)
    app.router.add_route("GET", "/_portal/login", login)
    app.router.add_route("POST", "/_portal/login", login)
    app.router.add_route("*", "/{path:.*}", proxy)
    return app
