import sys
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
import db


class RenderTests(unittest.TestCase):
    def test_avisos_usan_el_enlace_del_alojamiento(self):
        with tempfile.TemporaryDirectory() as tmp, patch.object(db, 'RUTA_DB', Path(tmp) / 'portal.db'), patch.dict(os.environ, {'PORTAL_URL': '', 'RENDER_EXTERNAL_URL': 'https://ticketera.onrender.com/'}):
            db.iniciar()
            sup = db.crear_usuario('Ana', 'ana@example.com', 'supervisor')
            admin = db.crear_usuario('Equipo', 'equipo@example.com', 'backoffice')
            tid, _ = db.crear_ticket(sup, 'IBK', 'Consulta', '', '')
            db.actualizar_ticket(tid, admin, {'estado': 'Enviada a verificar'}, 'Enviada')
            with db.conexion() as con:
                aviso = con.execute('SELECT cuerpo FROM correo_salida ORDER BY id DESC LIMIT 1').fetchone()[0]
            self.assertIn('https://ticketera.onrender.com', aviso)
            self.assertNotIn('localhost', aviso)
