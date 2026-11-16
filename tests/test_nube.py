import os
from pathlib import Path
import sqlite3
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
import db
import almacenamiento


class StorageTests(unittest.TestCase):
    def test_bucket_publico_rechazado(self):
        with patch.dict(os.environ, {'SUPABASE_URL': 'https://prueba.supabase.co', 'SUPABASE_SERVICE_ROLE_KEY': 'solo-prueba'}), patch.object(almacenamiento, 'peticion', return_value=b'{"public":true}'):
            with self.assertRaises(almacenamiento.ErrorAlmacenamiento):
                almacenamiento.comprobar()

    def test_cloud_no_recurre_a_sqlite(self):
        with patch.dict(os.environ, {'DATABASE_URL': '', 'EXIGIR_DB_REMOTA': '1'}):
            with self.assertRaises(RuntimeError), db.conexion():
                pass


@unittest.skipUnless(os.getenv('TEST_DATABASE_URL'), 'Requiere PostgreSQL de pruebas aislado')
class PostgresTests(unittest.TestCase):
    def setUp(self):
        import psycopg
        self.env = patch.dict(os.environ, {'DATABASE_URL': os.environ['TEST_DATABASE_URL']})
        self.env.start()
        self.addCleanup(self.env.stop)
        # TEST_DATABASE_URL solo puede apuntar a una base desechable local.
        from psycopg.conninfo import conninfo_to_dict
        self.assertIn(conninfo_to_dict(os.environ['TEST_DATABASE_URL'])['host'], {'localhost', '127.0.0.1'})
        with psycopg.connect(os.environ['TEST_DATABASE_URL'], autocommit=True) as con:
            con.execute('DROP SCHEMA IF EXISTS ticketera CASCADE')
        self.objetos = {}
        def subir(clave, datos, tipo):
            self.objetos[clave] = datos
        for nombre, efecto in [('subir', subir), ('descargar', lambda clave: self.objetos[clave]), ('borrar', lambda clave: self.objetos.pop(clave, None))]:
            mock = patch.object(almacenamiento, nombre, side_effect=efecto)
            mock.start()
            self.addCleanup(mock.stop)
        db.iniciar()

    def usuarios(self):
        admin = db.crear_usuario('Equipo', 'equipo@example.com', 'backoffice', 'clave-prueba')
        sup = db.crear_usuario('Ana', 'ana@example.com', 'supervisor', 'clave-prueba')
        return admin, sup

    def test_flujo_persistencia_permisos_y_borrado(self):
        a, s = self.usuarios()
        datos = b'%PDF-prueba'
        tid, codigo = db.crear_ticket(s, 'IBK', 'Consulta', '', '', adjuntos=[{'nombre': 'caso.pdf', 'datos': datos}])
        db.actualizar_propiedades(tid, a, 'Enviada a verificar', 'Alta', a, 'IBK', 'Consulta')
        db.agregar_nota_interna(tid, a, 'Nota privada')
        db.agregar_mensaje(tid, a, 'Respuesta', adjuntos=[{'nombre': 'respuesta.pdf', 'datos': datos}])
        db.iniciar()
        self.assertEqual(db.ticket(tid)['prioridad'], 'Alta')
        self.assertEqual(db.tickets_df(s).iloc[0]['codigo'], codigo)
        self.assertFalse(db.historial_df(tid).empty)
        self.assertEqual(len(db.mensajes(tid)), 1)
        self.assertEqual(len(db.notas_ticket(tid, a)), 1)
        with self.assertRaises(PermissionError):
            db.notas_ticket(tid, s)
        aid = db.adjuntos_ticket(tid, s)[0]['id']
        self.assertEqual(db.obtener_adjunto(aid, s)['datos'], datos)
        otro = db.crear_usuario('Otro', 'otro@example.com', 'supervisor')
        with self.assertRaises(PermissionError):
            db.obtener_adjunto(aid, otro)
        token = db.crear_sesion(s)
        self.assertEqual(db.usuario_por_sesion(token)['id'], s)
        db.revocar_sesion(token)
        self.assertIsNone(db.usuario_por_sesion(token))
        db.servicio_actualizar('conectado')
        db.servicio_actualizar('actualizado')
        db.eliminar_solicitud(tid, a)
        with patch.object(almacenamiento, 'borrar', side_effect=RuntimeError('sin conexión')):
            with self.assertRaises(RuntimeError):
                db.limpiar_objetos()
        self.assertEqual(len(self.objetos), 2)
        db.limpiar_objetos()
        self.assertFalse(self.objetos)

    def test_subida_se_compensa_si_falla_transaccion(self):
        a, s = self.usuarios()
        with patch.object(db, '_crear_notificaciones', side_effect=RuntimeError('fallo')):
            with self.assertRaises(RuntimeError):
                db.crear_ticket(s, 'IBK', 'Consulta', '', '', adjuntos=[{'nombre': 'caso.pdf', 'datos': b'%PDF-prueba'}])
        self.assertFalse(self.objetos)
        self.assertTrue(db.tickets_df().empty)
        with db.conexion() as con:
            self.assertEqual(con.execute('SELECT COUNT(*) FROM objetos_por_borrar').fetchone()[0], 0)

    def test_error_integridad_y_borrado_usuario(self):
        a, s = self.usuarios()
        with self.assertRaises(sqlite3.IntegrityError):
            db.crear_usuario('Ana', 'otro@example.com', 'supervisor')
        tid, _ = db.crear_ticket(s, 'IBK', 'Consulta', '', '')
        db.actualizar_propiedades(tid, a, 'Recibida', 'Media', a, 'IBK', 'Consulta')
        db.eliminar_usuario(s, a, True)
        self.assertIsNone(db.ticket(tid))

    def test_migracion_conserva_ids_claves_adjuntos_y_secuencias(self):
        from migrar_supabase import migrar
        with tempfile.TemporaryDirectory() as tmp:
            ruta = Path(tmp) / 'origen.db'
            with patch.dict(os.environ, {'DATABASE_URL': ''}), patch.object(db, 'RUTA_DB', ruta):
                db.iniciar()
                a, s = self.usuarios()
                tid, codigo = db.crear_ticket(s, 'IBK', 'Consulta', '12345678', '', adjuntos=[{'nombre': 'caso.pdf', 'datos': b'%PDF-prueba'}])
                db.agregar_mensaje(tid, a, 'Respuesta')
                db.agregar_nota_interna(tid, a, 'Privada')
            original = ruta.read_bytes()
            with patch.object(almacenamiento, 'comprobar'):
                conteos = migrar(ruta)
                with self.assertRaises(ValueError):
                    migrar(ruta)
            self.assertEqual(original, ruta.read_bytes())
            self.assertEqual(conteos['usuarios'], 2)
            self.assertEqual(db.ticket(tid)['codigo'], codigo)
            self.assertTrue(db.verificar_clave('clave-prueba', db.usuario_por_id(s)['clave_hash']))
            self.assertEqual(db.obtener_adjunto(db.adjuntos_ticket(tid, s)[0]['id'], s)['datos'], b'%PDF-prueba')
            nuevo, _ = db.crear_ticket(s, 'IBK', 'Consulta', '', '')
            self.assertGreater(nuevo, tid)
            with db.conexion() as con:
                self.assertEqual(con.execute("SELECT COUNT(*) FROM correo_salida WHERE estado='pendiente'").fetchone()[0], 2)

    def test_respaldo_incluye_documentos_y_puede_abrirse_localmente(self):
        from respaldar_supabase import respaldar
        a, s = self.usuarios()
        tid, _ = db.crear_ticket(s, 'IBK', 'Consulta', '', '', adjuntos=[{'nombre': 'caso.pdf', 'datos': b'%PDF-prueba'}])
        with tempfile.TemporaryDirectory() as tmp:
            ruta = Path(tmp) / 'respaldo.db'
            respaldar(ruta)
            with self.assertRaises(ValueError):
                respaldar(ruta)
            with patch.dict(os.environ, {'DATABASE_URL': ''}), patch.object(db, 'RUTA_DB', ruta):
                self.assertEqual(db.ticket(tid)['supervisor_id'], s)
                aid = db.adjuntos_ticket(tid, s)[0]['id']
                self.assertEqual(db.obtener_adjunto(aid, s)['datos'], b'%PDF-prueba')

    def test_reserva_de_subida_expirada_se_limpia(self):
        with db.conexion() as con:
            db.preparar_subida(con, 'tickets/reserva')
        self.objetos['tickets/reserva'] = b'pendiente'
        db.limpiar_objetos()
        self.assertIn('tickets/reserva', self.objetos)
        with db.conexion() as con:
            con.execute('UPDATE objetos_por_borrar SET expira_en=0')
        db.limpiar_objetos()
        self.assertNotIn('tickets/reserva', self.objetos)

    def test_paginas_con_postgresql(self):
        from streamlit.testing.v1 import AppTest
        a, s = self.usuarios()
        tid, _ = db.crear_ticket(s, 'IBK', 'Consulta', '', '')
        app = Path(__file__).resolve().parents[1] / 'app' / 'plataforma.py'
        for uid, pagina in [(a, 'Inicio'), (a, 'Gestionar'), (a, 'Correo'), (a, 'Usuarios'), (a, 'Nueva solicitud'), (s, 'Mis solicitudes')]:
            with self.subTest(pagina=pagina):
                at = AppTest.from_file(str(app), default_timeout=20)
                at.session_state['usuario'] = dict(db.usuario_por_id(uid))
                at.session_state['pagina_pf'] = pagina
                at.run()
                self.assertEqual(len(at.exception), 0)
