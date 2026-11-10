import os
from pathlib import Path
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
import db
from servidor_sesion import crear_app, COOKIE, CSRF
from aiohttp import CookieJar, web
from aiohttp.test_utils import TestClient, TestServer


class SesionDBTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        db.RUTA_DB = Path(self.tmp.name) / 'sesiones.db'
        db.iniciar()
        self.uid = db.crear_usuario('Ana', 'ana@example.com', 'backoffice', 'clave-prueba')

    def tearDown(self):
        self.tmp.cleanup()

    def test_token_opaco_expira_y_no_se_guarda_en_claro(self):
        token = db.crear_sesion(self.uid)
        self.assertEqual(db.usuario_por_sesion(token)['id'], self.uid)
        with db.conexion() as con:
            self.assertNotEqual(con.execute('SELECT huella FROM sesiones').fetchone()[0], token)
        with patch.object(db.time, 'time', return_value=time.time() + db.DURACION_SESION + 1):
            self.assertIsNone(db.usuario_por_sesion(token))
        self.assertIsNone(db.usuario_por_sesion('inventado'))

    def test_revocacion_y_persistencia_de_usuarios(self):
        token = db.crear_sesion(self.uid)
        db.iniciar()
        self.assertEqual(db.usuario_por_sesion(token)['id'], self.uid)
        db.revocar_sesion(token)
        self.assertIsNone(db.usuario_por_sesion(token))
        self.assertTrue(db.verificar_clave('clave-prueba', db.usuario_por_id(self.uid)['clave_hash']))

    def test_terminal_actualiza_la_misma_base(self):
        from administrar_usuarios import main
        with patch('sys.argv', ['administrar_usuarios.py', 'editar', str(self.uid), '--correo', 'nuevo@example.com', '--cambiar-clave']), patch('getpass.getpass', side_effect=['clave-terminal', 'clave-terminal']):
            main()
        db.iniciar()
        u = db.usuario_por_correo('nuevo@example.com')
        self.assertEqual(u['id'], self.uid)
        self.assertTrue(db.verificar_clave('clave-terminal', u['clave_hash']))

    def test_cambios_de_acceso_revocan_sesiones(self):
        for campo, valor in [('clave', 'otra-clave'), ('correo', 'otra@example.com'), ('activo', False), ('rol', 'supervisor')]:
            with self.subTest(campo=campo):
                db.actualizar_usuario(self.uid, 'Ana', 'ana@example.com', 'backoffice', True, 'clave-prueba')
                token = db.crear_sesion(self.uid)
                cambios = dict(nombre='Ana', correo='ana@example.com', rol='backoffice', activo=True)
                cambios[campo] = valor
                db.actualizar_usuario(self.uid, **cambios)
                self.assertIsNone(db.usuario_por_sesion(token))


class SesionHTTPTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        db.RUTA_DB = Path(self.tmp.name) / 'http.db'
        db.iniciar()
        self.uid = db.crear_usuario('Ana', 'ana@example.com', 'backoffice', 'clave-prueba')
        backend = web.Application()
        async def pagina(request):
            return web.Response(text='portal protegido')
        async def ws(request):
            socket = web.WebSocketResponse()
            await socket.prepare(request)
            async for msg in socket:
                await socket.send_str(msg.data)
            return socket
        backend.router.add_get('/', pagina)
        backend.router.add_get('/static/login.js', pagina)
        backend.router.add_get('/_stcore/stream', ws)
        self.backend = TestServer(backend)
        await self.backend.start_server()
        self.cliente = TestClient(TestServer(crear_app(str(self.backend.make_url('')).rstrip('/'))), cookie_jar=CookieJar(unsafe=True))
        await self.cliente.start_server()

    async def asyncTearDown(self):
        await self.cliente.close()
        await self.backend.close()
        self.tmp.cleanup()

    async def entrar(self, clave='clave-prueba'):
        form = await self.cliente.get('/_portal/login')
        csrf = form.cookies[CSRF].value
        return await self.cliente.post('/_portal/login', data={'csrf': csrf, 'correo': 'ana@example.com', 'clave': clave}, allow_redirects=False)

    async def test_cookie_y_recarga_proxy_y_logout(self):
        bloqueado = await self.cliente.get('/', allow_redirects=False)
        self.assertEqual(bloqueado.status, 303)
        self.assertEqual(bloqueado.headers['Location'], '/_portal/login')
        response = await self.entrar()
        self.assertEqual(response.status, 303)
        cookie = response.cookies[COOKIE]
        self.assertTrue(cookie['httponly'])
        self.assertEqual(cookie['samesite'], 'Lax')
        self.assertEqual(int(cookie['max-age']), db.DURACION_SESION)
        for _ in range(2):
            response = await self.cliente.get('/')
            self.assertEqual(await response.text(), 'portal protegido')
        async with self.cliente.ws_connect('/_stcore/stream') as ws:
            await ws.send_str('prueba')
            self.assertEqual((await ws.receive()).data, 'prueba')
        db.revocar_sesion(cookie.value)
        self.assertEqual((await self.cliente.get('/', allow_redirects=False)).status, 303)
        self.assertEqual((await self.cliente.get('/static/login.js')).status, 200)

    async def test_csrf_credenciales_y_cookie_secure(self):
        response = await self.cliente.post('/_portal/login', data={'correo': 'ana@example.com', 'clave': 'clave-prueba'}, allow_redirects=False)
        self.assertEqual(response.status, 403)
        self.assertEqual((await self.entrar('incorrecta')).status, 401)
        form = await self.cliente.get('/_portal/login')
        csrf = form.cookies[CSRF].value
        with patch.dict(os.environ, {'PORTAL_CLOUD': '1'}):
            response = await self.cliente.post('/_portal/login', data={'csrf': csrf, 'correo': 'ana@example.com', 'clave': 'clave-prueba'}, allow_redirects=False)
            self.assertTrue(response.cookies[COOKIE]['secure'])
