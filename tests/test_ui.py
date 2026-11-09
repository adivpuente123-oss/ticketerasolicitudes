import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from streamlit.testing.v1 import AppTest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
import db

APP = Path(__file__).resolve().parents[1] / "app" / "plataforma.py"


class UITests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        db.RUTA_DB = Path(self.tmp.name) / "ui.db"
        db.iniciar()
        self.admin = db.crear_usuario("Equipo", "equipo@example.com", "backoffice", "clave-prueba")
        self.sup = db.crear_usuario("Supervisor", "supervisor@example.com", "supervisor", "clave-prueba")
        self.otro = db.crear_usuario("Otro", "otro@example.com", "supervisor", "clave-prueba")
        self.tid, _ = db.crear_ticket(self.sup, "IBK", "Consulta propia", "12345678", "00012345")
        db.crear_ticket(self.otro, "BBVA", "Consulta ajena", "87654321", "00098765")

    def tearDown(self):
        self.tmp.cleanup()

    def app(self, uid, pagina=None):
        at = AppTest.from_file(str(APP), default_timeout=20)
        u = db.usuario_por_id(uid)
        at.session_state["usuario"] = {k: u[k] for k in ("id", "nombre", "correo", "rol")}
        if pagina:
            at.session_state["pagina_pf"] = pagina
        return at.run()

    def test_supervisor_solo_ve_su_ticket_y_detalle(self):
        at = self.app(self.sup)
        self.assertEqual(len(at.exception), 0)
        abrir = [b for b in at.button if b.label == "Abrir"]
        self.assertEqual(len(abrir), 1)
        abrir[0].click().run()
        self.assertEqual(len(at.exception), 0)
        self.assertTrue(any("Consulta propia" in x.value for x in at.markdown))
        self.assertFalse(any("Consulta ajena" in x.value for x in at.markdown))

    def test_gestion_y_buzon_cargan(self):
        for pagina in ["Inicio", "Gestionar", "Correo", "Nueva solicitud", "Usuarios"]:
            with self.subTest(pagina=pagina):
                at = self.app(self.admin, pagina)
                self.assertEqual(len(at.exception), 0)

    def test_login_rechaza_clave_incorrecta(self):
        at = AppTest.from_file(str(APP), default_timeout=20).run()
        at.text_input[0].set_value("supervisor@example.com")
        at.text_input[1].set_value("incorrecta")
        at.button[0].click().run()
        self.assertTrue(at.error)
        self.assertEqual(len(at.exception), 0)

    def test_edita_correo_y_contrasena(self):
        at = self.app(self.admin, "Usuarios")
        next(x for x in at.selectbox if x.label == "Crear o editar usuario").select("SUPERVISOR").run()
        next(x for x in at.text_input if x.label == "Correo").set_value("actualizado@example.com")
        next(x for x in at.text_input if x.label.startswith("Contraseña nueva")).set_value("clave-actualizada")
        next(x for x in at.text_input if x.label == "Repite la contraseña nueva").set_value("clave-actualizada")
        next(x for x in at.button if x.label == "Guardar usuario").click().run()
        self.assertEqual(len(at.exception), 0)
        u = db.usuario_por_id(self.sup)
        self.assertEqual(u["correo"], "actualizado@example.com")
        self.assertTrue(db.verificar_clave("clave-actualizada", u["clave_hash"]))

    def test_elimina_con_confirmacion_y_solicitudes(self):
        libre = db.crear_usuario("Libre", "libre@example.com", "supervisor")
        at = self.app(self.admin, "Usuarios")
        next(x for x in at.selectbox if x.label == "Crear o editar usuario").select("LIBRE").run()
        next(x for x in at.button if x.label == "Eliminar usuario").click().run()
        self.assertIsNotNone(db.usuario_por_id(libre))
        next(x for x in at.checkbox if x.label.startswith("Confirmo eliminar")).check()
        next(x for x in at.button if x.label == "Eliminar usuario").click().run()
        self.assertIsNone(db.usuario_por_id(libre))
        self.assertEqual(len(at.exception), 0)
        next(x for x in at.selectbox if x.label == "Crear o editar usuario").select("SUPERVISOR").run()
        next(x for x in at.radio if x.label == "¿Borrar también todas sus solicitudes?").set_value("Sí, borrar todas sus solicitudes")
        next(x for x in at.checkbox if x.label.startswith("Confirmo eliminar")).check()
        next(x for x in at.button if x.label == "Eliminar usuario").click().run()
        self.assertIsNone(db.usuario_por_id(self.sup))
        self.assertIsNone(db.ticket(self.tid))
        self.assertEqual(len(at.exception), 0)

    def test_borra_solicitud_desde_listado(self):
        at = self.app(self.admin, "Inicio")
        at.button(key=f"borrar_{self.tid}").click().run()
        self.assertIsNotNone(db.ticket(self.tid))
        next(x for x in at.button if x.label == "Sí, borrar solicitud").click().run()
        self.assertIsNone(db.ticket(self.tid))
        self.assertEqual(len(at.exception), 0)

    def test_notificacion_abre_ticket_y_marca_leida(self):
        db.agregar_mensaje(self.tid, self.admin, 'Mensaje nuevo para supervisor')
        at = self.app(self.sup)
        aviso = db.notificaciones_usuario(self.sup)[0]
        at.button(key=f"aviso_{aviso['id']}").click().run()
        self.assertEqual(len(at.exception), 0)
        self.assertEqual(db.contar_notificaciones(self.sup), 0)
        self.assertTrue(any('Consulta propia' in x.value for x in at.markdown))
        self.assertFalse(any('Consulta ajena' in x.value for x in at.markdown))

    def test_notificaciones_marca_todas_leidas(self):
        at = self.app(self.admin, 'Inicio')
        self.assertEqual(db.contar_notificaciones(self.admin), 2)
        at.button(key='leer_notificaciones').click().run()
        self.assertEqual(db.contar_notificaciones(self.admin), 0)
        self.assertEqual(len(at.exception), 0)

    def test_aviso_flotante_y_contador(self):
        at = self.app(self.admin, 'Inicio')
        self.assertTrue(any('notification-badge' in m.value and '>2<' in m.value for m in at.markdown))
        db.agregar_mensaje(self.tid, self.sup, 'Nueva consulta')
        at.run()
        self.assertEqual(len(at.exception), 0)
        self.assertTrue(any('Nuevo mensaje' in t.value for t in at.toast))
        self.assertTrue(any('notification-badge' in m.value and '>3<' in m.value for m in at.markdown))
        at.button(key='leer_notificaciones').click().run()
        self.assertFalse(any('class="notification-badge"' in m.value for m in at.markdown))
