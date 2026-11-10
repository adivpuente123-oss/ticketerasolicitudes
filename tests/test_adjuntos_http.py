import sys
import tempfile
import unittest
from pathlib import Path
from aiohttp.test_utils import TestClient, TestServer
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
import db
from servidor_sesion import COOKIE, crear_app


class AdjuntosHTTPTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        db.RUTA_DB = Path(self.tmp.name) / 'adjuntos.db'
        db.iniciar()
        self.sup = db.crear_usuario('Ana', 'ana@example.com', 'supervisor')
        self.otro = db.crear_usuario('Luis', 'luis@example.com', 'supervisor')
        self.admin = db.crear_usuario('Equipo', 'equipo@example.com', 'backoffice')
        self.pdf = b'%PDF-1.4\n%%EOF'
        self.tid, _ = db.crear_ticket(self.sup, 'IBK', 'Consulta', '12345678', '00123456', adjuntos=[{'nombre': 'expediente.pdf', 'datos': self.pdf}])
        self.aid = db.adjuntos_ticket(self.tid, self.sup)[0]['id']
        self.cliente = TestClient(TestServer(crear_app('http://127.0.0.1:1')))
        await self.cliente.start_server()

    async def asyncTearDown(self):
        await self.cliente.close()
        self.tmp.cleanup()

    async def test_descarga_autorizada_y_acceso_ajeno_bloqueado(self):
        ruta = f'/_portal/adjuntos/{self.aid}'
        self.assertEqual((await self.cliente.get(ruta)).status, 401)
        for uid in (self.sup, self.admin):
            response = await self.cliente.get(ruta, headers={'Cookie': f'{COOKIE}={db.crear_sesion(uid)}'})
            self.assertEqual(response.status, 200)
            self.assertEqual(await response.read(), self.pdf)
            self.assertIn('attachment', response.headers['Content-Disposition'])
            self.assertEqual(response.headers['Cache-Control'], 'private, no-store')
        response = await self.cliente.get(ruta, headers={'Cookie': f'{COOKIE}={db.crear_sesion(self.otro)}'})
        self.assertEqual(response.status, 404)
        db.eliminar_solicitud(self.tid, self.admin)
        response = await self.cliente.get(ruta, headers={'Cookie': f'{COOKIE}={db.crear_sesion(self.admin)}'})
        self.assertEqual(response.status, 404)
