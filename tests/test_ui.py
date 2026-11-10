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

    def test_solicitudes_sin_banner_y_notificaciones_sin_historial(self):
        at = self.app(self.admin, 'Inicio')
        self.assertFalse(any('<section class="workspace-banner"' in m.value for m in at.markdown))
        aviso = db.notificaciones_usuario(self.admin)[0]
        at.button(key=f"aviso_{aviso['id']}").click().run()
        self.assertFalse(any(b.key == f"aviso_{aviso['id']}" for b in at.button))
        self.assertEqual(db.contar_notificaciones(self.admin), 1)
        at.button(key='leer_notificaciones').click().run()
        self.assertEqual(db.notificaciones_usuario(self.admin), [])
        self.assertFalse(any(str(b.key).startswith('aviso_') for b in at.button))
        self.assertEqual(len(at.exception), 0)

    def test_panel_compacto_filtros_y_contadores(self):
        db.actualizar_ticket(self.tid, self.admin, {"estado": "Respondida", "conclusion": "PROCEDENTE"}, "Respondida")
        at = self.app(self.admin, 'Inicio')
        self.assertEqual(len(at.exception), 0)
        self.assertTrue(any('summary-grid' in m.value and 'En verificación' in m.value for m in at.markdown))
        at.text_input(key='bo_q').set_value('Consulta propia').run()
        self.assertEqual(len([b for b in at.button if str(b.key).startswith('abrir_')]), 1)
        at.selectbox(key='bo_estado').select('Recibida').run()
        self.assertEqual(len([b for b in at.button if str(b.key).startswith('abrir_')]), 0)
        self.assertEqual(len(at.exception), 0)

    def test_filtros_de_supervisor_periodo_y_demora(self):
        from datetime import date, timedelta
        vieja, _ = db.crear_ticket(self.sup, 'IBK', 'Solicitud antigua', '12345678', '00123456', fecha_solicitud=(date.today()-timedelta(days=45)).isoformat())
        at = self.app(self.admin, 'Inicio')
        at.selectbox(key='bo_supervisor').select(self.sup).run()
        self.assertEqual(len([b for b in at.button if str(b.key).startswith('abrir_')]), 2)
        at.checkbox(key='bo_demora').check().run()
        self.assertEqual(len([b for b in at.button if str(b.key).startswith('abrir_')]), 1)
        self.assertTrue(any(b.key == f'abrir_{vieja}' for b in at.button))
        at.selectbox(key='bo_periodo').select('Últimos 7 días').run()
        self.assertEqual(len([b for b in at.button if str(b.key).startswith('abrir_')]), 0)
        self.assertEqual(len(at.exception), 0)

    def test_periodo_personalizado_invalido_no_falla(self):
        from datetime import date, timedelta
        at = self.app(self.admin, 'Inicio')
        at.selectbox(key='bo_periodo').select('Personalizado').run()
        at.date_input(key='bo_desde').set_value(date.today()+timedelta(days=1))
        at.date_input(key='bo_hasta').set_value(date.today())
        at.run()
        self.assertTrue(any('Desde' in w.value for w in at.warning))
        self.assertEqual(len(at.exception), 0)

    def test_limpiar_filtros_restaura_la_bandeja(self):
        at = self.app(self.admin, 'Inicio')
        at.text_input(key='bo_q').set_value('inexistente').run()
        self.assertEqual(len([b for b in at.button if str(b.key).startswith('abrir_')]), 0)
        at.button(key='bo_limpiar').click().run()
        self.assertEqual(at.text_input(key='bo_q').value, '')
        self.assertEqual(len([b for b in at.button if str(b.key).startswith('abrir_')]), 2)
        self.assertEqual(len(at.exception), 0)

    def test_boton_nueva_solicitud_abre_formulario(self):
        at = self.app(self.admin, 'Inicio')
        at.button(key='btn_nueva').click().run()
        self.assertTrue(any(x.key == 'nueva_asunto' for x in at.text_input))
        self.assertEqual(len(at.exception), 0)

    def test_transaccion_muestra_campos_y_valida_documentos(self):
        from config import TIPO_TRANSACCION
        at = self.app(self.sup, 'Nueva solicitud')
        at.selectbox(key='nueva_tipo').select(TIPO_TRANSACCION).run()
        for key in ['nueva_nombre','nueva_expediente','nueva_juzgado','nueva_materia']:
            self.assertTrue(any(x.key == key for x in at.text_input))
        at.text_input(key='nueva_asunto').set_value('Transacción de prueba')
        at.text_area(key='nueva_descripcion').set_value('Necesito preparar una transacción.')
        at.checkbox(key='nueva_incompletos').check().run()
        at.button(key='nueva_enviar').click().run()
        self.assertTrue(any('Adjunta al menos' in x.value for x in at.error))
        self.assertEqual(len(at.exception), 0)

    def test_envia_transaccion_con_datos_y_reinicia_formulario(self):
        from config import TIPO_TRANSACCION
        at = self.app(self.sup, 'Nueva solicitud')
        at.selectbox(key='nueva_tipo').select(TIPO_TRANSACCION).run()
        for clave, valor in {'nueva_asunto':'Preparar transacción', 'nueva_documento':'34567890','nueva_nombre':'Cliente ficticio','nueva_expediente':'123-2026','nueva_juzgado':'Juzgado civil','nueva_materia':'Obligación de dar suma'}.items():
            at.text_input(key=clave).set_value(valor)
        at.text_area(key='nueva_descripcion').set_value('Solicito la revisión del expediente.')
        at.button(key='nueva_enviar').click().run()
        self.assertEqual(len(at.exception), 0)
        self.assertTrue(any('registrada correctamente' in x.value for x in at.success))
        self.assertEqual(at.text_input(key='nueva_asunto').value, '')
        with db.conexion() as con:
            self.assertEqual(con.execute("SELECT numero_expediente FROM tickets ORDER BY id DESC LIMIT 1").fetchone()[0], '123-2026')

    def test_gestion_guarda_propiedades_y_vuelve_al_listado(self):
        at = self.app(self.admin, 'Gestionar')
        tid = at.selectbox(key='ticket_sel').value
        at.selectbox(key=f'prop_prioridad_{tid}').select('Alta')
        next(b for b in at.button if b.label == 'Guardar cambios').click().run()
        self.assertEqual(db.ticket(tid)['prioridad'], 'Alta')
        at.button(key='gestion_volver').click().run()
        self.assertTrue(any(b.key == 'btn_nueva' for b in at.button))
        self.assertEqual(len(at.exception), 0)

    def test_notas_internas_solo_para_equipo_y_respuesta_publica(self):
        at = self.app(self.admin, 'Gestionar')
        tid = at.selectbox(key='ticket_sel').value
        at.text_area(key=f'nota_texto_{tid}').set_value('NOTA PRIVADA DEL EQUIPO')
        next(b for b in at.button if b.label == 'Guardar nota interna').click().run()
        self.assertEqual(len(db.notas_ticket(tid, self.admin)), 1)
        at.text_area(key=f'reply_{tid}_0').set_value('Respuesta para el supervisor')
        next(b for b in at.button if b.label == 'Enviar respuesta').click().run()
        self.assertEqual(db.mensajes(tid)[0]['cuerpo'], 'Respuesta para el supervisor')
        self.assertEqual(len(at.exception), 0)
        propietario = db.ticket(tid)['supervisor_id']
        sup = self.app(propietario)
        next(b for b in sup.button if b.label == 'Abrir').click().run()
        self.assertFalse(any('NOTA PRIVADA DEL EQUIPO' in m.value for m in sup.markdown))
        self.assertFalse(any(t.label == 'Nota interna' for t in sup.tabs))
