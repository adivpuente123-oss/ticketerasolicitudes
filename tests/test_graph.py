import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
import db
from servicio_graph import Graph


class GraphTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        db.RUTA_DB = Path(self.tmp.name) / "graph.db"
        db.iniciar()
        self.sup = db.crear_usuario("Supervisor", "supervisor@example.com", "supervisor")
        with patch.dict(os.environ, {"MS_TENANT_ID": "prueba", "MS_CLIENT_ID": "prueba", "MS_CLIENT_SECRET": "prueba"}):
            self.g = Graph()

    def tearDown(self):
        self.tmp.cleanup()

    def test_importa_y_responde_sin_duplicar(self):
        mensaje = {"id": "id-1", "internetMessageId": "<mail-1>", "from": {"emailAddress": {"address": "supervisor@example.com"}},
                   "subject": "IBK", "body": {"content": "Cartera: IBK\nDNI: 12345678\nCuenta: 00012345"}, "receivedDateTime": "2026-11-07T12:00:00Z"}
        with patch.dict(os.environ, {"MS_FOLDER_ID": "solicitudes"}), patch.object(self.g, "coleccion", return_value=iter([mensaje])), patch.object(self.g, "request") as req:
            self.g.recibir()
            self.assertEqual(req.call_args.args[1], "PATCH")
        with patch.dict(os.environ, {"MS_FOLDER_ID": "solicitudes"}), patch.object(self.g, "coleccion", return_value=iter([mensaje])), patch.object(self.g, "request") as req:
            self.g.recibir()
            req.assert_not_called()
        with patch.object(self.g, "request", return_value={}) as req:
            self.g.enviar()
            self.assertEqual(req.call_count, 2)
            for llamada in req.call_args_list:
                self.assertTrue(llamada.args[0].endswith("/messages"))
                self.assertEqual(llamada.args[1], "POST")
        with db.conexion() as con:
            self.assertEqual(con.execute("SELECT count(*) FROM correo_salida WHERE estado='borrador'").fetchone()[0], 2)

    def test_no_reenvia_automaticamente_timeout_ambiguo(self):
        db.crear_ticket(self.sup, "IBK", "Consulta", "12345678", "00123456")
        with patch.object(self.g, "request", side_effect=TimeoutError()):
            with self.assertRaises(TimeoutError):
                self.g.enviar()
        with db.conexion() as con:
            self.assertEqual(con.execute("SELECT count(*) FROM correo_salida WHERE estado='revisar'").fetchone()[0], 1)

    def test_no_envia_token_a_url_de_paginacion_externa(self):
        with patch.object(self.g, "autorizar"):
            with self.assertRaises(ValueError):
                self.g.request("https://ejemplo.com/v1.0/mensajes")
