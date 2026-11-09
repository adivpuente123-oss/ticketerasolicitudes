import sys
import tempfile
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
import db
from correo import crear_ticket_desde_correo


class NotificacionesTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        db.RUTA_DB = Path(self.tmp.name) / 'avisos.db'
        db.iniciar()
        self.admin = db.crear_usuario('Equipo', 'equipo@example.com', 'backoffice')
        self.sup = db.crear_usuario('Ana', 'ana@example.com', 'supervisor')
        self.otro = db.crear_usuario('Luis', 'luis@example.com', 'supervisor')

    def tearDown(self):
        self.tmp.cleanup()

    def test_solicitud_notifica_equipo_y_no_autor_ni_ajenos(self):
        tid, _ = db.crear_ticket(self.sup, 'IBK', 'Consulta', '12345678', '00123456', usuario_id=self.sup)
        self.assertEqual(db.contar_notificaciones(self.admin), 1)
        self.assertEqual(db.contar_notificaciones(self.sup), 0)
        self.assertEqual(db.contar_notificaciones(self.otro), 0)
        db.agregar_mensaje(tid, self.admin, 'Respuesta del equipo')
        self.assertEqual(db.contar_notificaciones(self.sup), 1)
        self.assertEqual(db.contar_notificaciones(self.admin), 1)
        db.agregar_mensaje(tid, self.sup, 'Gracias')
        self.assertEqual(db.contar_notificaciones(self.admin), 2)
        self.assertEqual(db.contar_notificaciones(self.otro), 0)

    def test_lectura_independiente_y_borrado_en_cascada(self):
        tid, _ = db.crear_ticket(self.sup, 'IBK', 'Consulta', '', '')
        aviso = db.notificaciones_usuario(self.admin)[0]
        db.marcar_notificaciones(self.otro, aviso['id'])
        self.assertEqual(db.contar_notificaciones(self.admin), 1)
        db.marcar_notificaciones(self.admin, aviso['id'])
        self.assertEqual(db.contar_notificaciones(self.admin), 0)
        db.agregar_mensaje(tid, self.sup, 'Más detalle')
        db.eliminar_solicitud(tid, self.admin)
        self.assertEqual(db.notificaciones_usuario(self.admin), [])

    def test_correo_y_estado_generan_avisos_sin_duplicar(self):
        r = crear_ticket_desde_correo('ana@example.com', 'Consulta', 'Detalle', 'mail-1')
        crear_ticket_desde_correo('ana@example.com', 'Consulta', 'Detalle', 'mail-1')
        self.assertEqual(db.contar_notificaciones(self.admin), 1)
        crear_ticket_desde_correo('ana@example.com', f"Re: [{r['codigo']}]", 'Mensaje adicional', 'mail-2')
        self.assertEqual(db.contar_notificaciones(self.admin), 2)
        db.actualizar_ticket(r['tid'], self.admin, {'estado': 'Enviada a verificar'}, 'Enviada')
        self.assertEqual(db.contar_notificaciones(self.sup), 1)
        db.actualizar_usuario(self.sup, 'Ana', 'ana@example.com', 'supervisor', False)
        self.assertEqual(db.notificaciones_usuario(self.sup), [])

    def test_eliminar_usuario_borra_sus_notificaciones(self):
        tid, _ = db.crear_ticket(self.sup, 'IBK', 'Consulta', '', '')
        db.agregar_mensaje(tid, self.admin, 'Respuesta')
        db.eliminar_usuario(self.sup, self.admin, borrar_solicitudes=True)
        with db.conexion() as con:
            self.assertEqual(con.execute('SELECT count(*) FROM notificaciones').fetchone()[0], 0)
            self.assertFalse(con.execute('PRAGMA foreign_key_check').fetchall())
