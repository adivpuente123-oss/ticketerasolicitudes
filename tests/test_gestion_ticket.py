import sys
import tempfile
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
import db


class GestionTicketTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        db.RUTA_DB = Path(self.tmp.name) / 'gestion.db'
        db.iniciar()
        self.sup = db.crear_usuario('Ana', 'ana@example.com', 'supervisor')
        self.admin = db.crear_usuario('Equipo', 'equipo@example.com', 'backoffice')
        self.agente = db.crear_usuario('Agente', 'agente@example.com', 'backoffice')
        self.tid, _ = db.crear_ticket(self.sup, 'IBK', 'Consulta', '12345678', '00123456')

    def tearDown(self):
        self.tmp.cleanup()

    def propiedades(self, **cambios):
        datos = dict(estado='Recibida', prioridad='Alta', asignado_a=self.agente, cartera='IBK', tipo_consulta='Consulta')
        datos.update(cambios)
        db.actualizar_propiedades(self.tid, self.admin, **datos)

    def test_prioridad_asignacion_persisten_y_notifican_al_agente(self):
        self.propiedades()
        db.iniciar()
        t = db.ticket(self.tid)
        self.assertEqual(t['prioridad'], 'Alta')
        self.assertEqual(t['asignado_a'], self.agente)
        self.assertTrue(any(n['tipo'] == 'asignacion' for n in db.notificaciones_usuario(self.agente)))

    def test_propiedades_validan_roles_y_no_cierra_sin_resultado(self):
        with self.assertRaises(ValueError):
            self.propiedades(asignado_a=self.sup)
        with self.assertRaises(ValueError):
            self.propiedades(prioridad='Inventada')
        with self.assertRaises(ValueError):
            self.propiedades(estado='Respondida')
        with self.assertRaises(PermissionError):
            db.actualizar_propiedades(self.tid, self.sup, 'Recibida', 'Alta', None, 'IBK', 'Consulta')
        self.assertEqual(db.ticket(self.tid)['estado'], 'Recibida')

    def test_notas_no_aparecen_en_conversacion_correo_ni_notificaciones(self):
        with db.conexion() as c:
            correos = c.execute('SELECT count(*) FROM correo_salida').fetchone()[0]
            avisos = c.execute('SELECT count(*) FROM notificaciones').fetchone()[0]
        db.agregar_nota_interna(self.tid, self.admin, 'INFORMACION INTERNA')
        self.assertEqual(db.notas_ticket(self.tid, self.admin)[0]['cuerpo'], 'INFORMACION INTERNA')
        self.assertEqual(db.mensajes(self.tid), [])
        with self.assertRaises(PermissionError):
            db.notas_ticket(self.tid, self.sup)
        with self.assertRaises(PermissionError):
            db.agregar_nota_interna(self.tid, self.sup, 'No autorizado')
        with db.conexion() as c:
            self.assertEqual(c.execute('SELECT count(*) FROM correo_salida').fetchone()[0], correos)
            self.assertEqual(c.execute('SELECT count(*) FROM notificaciones').fetchone()[0], avisos)

    def test_respuesta_publica_con_adjunto_y_borrado_en_cascada(self):
        db.agregar_mensaje(self.tid, self.admin, 'Adjunto constancia.', adjuntos=[{'nombre':'constancia.pdf','datos':b'%PDF-1.4\n%%EOF'}])
        mensaje = db.mensajes(self.tid)[0]
        a = db.adjuntos_ticket(self.tid, self.sup)[0]
        self.assertEqual(a['mensaje_id'], mensaje['id'])
        self.assertEqual(mensaje['autor_rol'], 'backoffice')
        db.agregar_nota_interna(self.tid, self.admin, 'Nota')
        db.eliminar_solicitud(self.tid, self.admin)
        with db.conexion() as c:
            self.assertEqual(c.execute('SELECT count(*) FROM notas_internas').fetchone()[0], 0)
            self.assertEqual(c.execute('SELECT count(*) FROM adjuntos').fetchone()[0], 0)
            self.assertFalse(c.execute('PRAGMA foreign_key_check').fetchall())

    def test_eliminar_asignado_conserva_ticket_y_desasigna(self):
        self.propiedades()
        db.agregar_nota_interna(self.tid, self.agente, 'Contexto interno')
        db.eliminar_usuario(self.agente, self.admin)
        self.assertIsNone(db.ticket(self.tid)['asignado_a'])
        self.assertEqual(len(db.notas_ticket(self.tid, self.admin)), 1)

    def test_guardia_de_respuesta_para_equipo(self):
        with self.assertRaises(PermissionError):
            db.actualizar_ticket(self.tid, self.sup, {'estado':'Respondida'}, 'Respondida', requerir_backoffice=True)
