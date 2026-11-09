import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
import db
from correo import crear_ticket_desde_correo
from servicio_outlook import enviar


class PortalTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        db.RUTA_DB = Path(self.tmp.name) / "prueba.db"
        db.iniciar()
        self.sup = db.crear_usuario("Supervisor", "supervisor@example.com", "supervisor", "clave-prueba")
        self.otro = db.crear_usuario("Otro", "otro@example.com", "supervisor")
        self.admin = db.crear_usuario("Equipo", "equipo@example.com", "backoffice")

    def tearDown(self):
        self.tmp.cleanup()

    def nuevo(self, mid="correo-1"):
        return crear_ticket_desde_correo("supervisor@example.com", "Cancelación IBK", "Cartera: IBK\nDNI: 12345678\nCuenta: 00123456", mid)

    def test_correo_crea_un_ticket_y_dos_avisos(self):
        r = self.nuevo()
        self.assertTrue(r["ok"])
        self.assertEqual(r["datos"]["cuenta"], "00123456")
        self.assertTrue(self.nuevo().get("duplicado"))
        with db.conexion() as con:
            self.assertEqual(con.execute("SELECT count(*) FROM tickets").fetchone()[0], 1)
            self.assertEqual(con.execute("SELECT count(*) FROM correo_salida").fetchone()[0], 2)

    def test_remitente_desconocido_o_inactivo_no_crea_ticket(self):
        self.assertFalse(crear_ticket_desde_correo("extra@example.com", "Hola", "Consulta")["ok"])
        db.actualizar_usuario(self.sup, "Supervisor", "supervisor@example.com", "supervisor", False)
        self.assertFalse(self.nuevo()["ok"])

    def test_respuesta_no_duplica_ticket_y_no_permite_otro_supervisor(self):
        r = self.nuevo()
        asunto = f"RE: [{r['codigo']}] Consulta"
        self.assertFalse(crear_ticket_desde_correo("otro@example.com", asunto, "Ajeno", "r-0")["ok"])
        self.assertTrue(crear_ticket_desde_correo("supervisor@example.com", asunto, "Más información", "r-1")["ok"])
        self.assertTrue(crear_ticket_desde_correo("supervisor@example.com", asunto, "Más información", "r-1").get("duplicado"))
        self.assertEqual(len(db.mensajes(r["tid"])), 1)
        self.assertEqual(len(db.tickets_df()), 1)
        self.assertEqual(len(db.tickets_df(self.otro)), 0)
        with self.assertRaises(PermissionError):
            db.agregar_mensaje(r["tid"], self.otro, "No autorizado")

    def test_cambio_de_estado_persiste_y_encola_respuesta(self):
        r = self.nuevo()
        db.actualizar_ticket(r["tid"], self.admin, {"estado": "Respondida", "respuesta": "Atendida", "conclusion": "PROCEDENTE"}, "Respondida")
        self.assertEqual(db.ticket(r["tid"])["estado"], "Respondida")
        with db.conexion() as con:
            mail = con.execute("SELECT * FROM correo_salida ORDER BY id DESC LIMIT 1").fetchone()
            self.assertIn("Atendida", mail["cuerpo"])
            self.assertEqual(mail["destinatario"], "supervisor@example.com")

    def test_borradores_responden_al_original_sin_enviar_ni_duplicar(self):
        self.nuevo()
        app, cuenta = Mock(), Mock()
        original = Mock()
        original.Class = 43
        original.PropertyAccessor.GetProperty.return_value = "correo-1"
        cuenta.DeliveryStore.GetDefaultFolder.return_value.Folders.Item.return_value.Items = [original]
        enviar(app, cuenta)
        original.Reply.assert_called_once()
        original.Reply.return_value.Save.assert_called_once()
        original.Reply.return_value.Send.assert_not_called()
        self.assertEqual(original.Reply.return_value.Body, "Tu solicitud SOL-0001 fue recibida. La revisaremos pronto.")
        self.assertEqual(app.CreateItem.return_value.Save.call_count, 1)
        app.CreateItem.return_value.Send.assert_not_called()
        enviar(app, cuenta)
        self.assertEqual(app.CreateItem.return_value.Save.call_count, 1)
        self.nuevo("correo-2")
        original.PropertyAccessor.GetProperty.return_value = "correo-2"
        original.Reply.return_value.Save.side_effect = RuntimeError("Outlook desconectado")
        app.CreateItem.return_value.Save.side_effect = RuntimeError("Outlook desconectado")
        enviar(app, cuenta)
        with db.conexion() as con:
            self.assertEqual(con.execute("SELECT count(*) FROM correo_salida WHERE estado='revisar'").fetchone()[0], 2)


    def test_edita_correo_y_clave_sin_cambiar_id(self):
        db.actualizar_usuario(self.sup, "Renombrado", "NUEVO@example.com", "supervisor", True, "nueva-clave")
        self.assertIsNone(db.usuario_por_correo("supervisor@example.com"))
        u = db.usuario_por_correo("nuevo@example.com")
        self.assertEqual(u["id"], self.sup)
        self.assertTrue(db.verificar_clave("nueva-clave", u["clave_hash"]))
        self.assertFalse(db.verificar_clave("clave-prueba", u["clave_hash"]))
        db.actualizar_usuario(self.sup, "Renombrado", "nuevo@example.com", "supervisor", True)
        self.assertTrue(db.verificar_clave("nueva-clave", db.usuario_por_id(self.sup)["clave_hash"]))

    def test_elimina_cuenta_sin_registros(self):
        db.eliminar_usuario(self.otro, self.admin)
        self.assertIsNone(db.usuario_por_id(self.otro))

    def test_eliminar_protege_historial_y_acceso(self):
        self.nuevo()
        with self.assertRaises(ValueError):
            db.eliminar_usuario(self.admin, self.admin)
        with self.assertRaises(PermissionError):
            db.eliminar_usuario(self.otro, self.sup)
        self.assertIsNotNone(db.usuario_por_id(self.sup))
        self.assertEqual(len(db.tickets_df(self.sup)), 1)

    def test_borra_solicitud_con_dependencias_sin_tocar_otras(self):
        r = self.nuevo()
        db.agregar_mensaje(r["tid"], self.sup, "Detalle")
        otra, _ = db.crear_ticket(self.otro, "IBK", "Consulta", "12345678", "00123456")
        with self.assertRaises(PermissionError):
            db.eliminar_solicitud(r["tid"], self.sup)
        db.eliminar_solicitud(r["tid"], self.admin)
        self.assertIsNone(db.ticket(r["tid"]))
        self.assertTrue(db.existe_id_correo("correo-1"))
        self.assertTrue(self.nuevo().get("duplicado"))
        self.assertIsNotNone(db.ticket(otra))
        with db.conexion() as con:
            for tabla in ("mensajes", "historial", "correo_salida"):
                self.assertEqual(con.execute(f"SELECT count(*) FROM {tabla} WHERE ticket_id=?", (r["tid"],)).fetchone()[0], 0)
            self.assertFalse(con.execute("PRAGMA foreign_key_check").fetchall())

    def test_elimina_usuario_y_todas_sus_solicitudes(self):
        r = self.nuevo()
        db.agregar_mensaje(r["tid"], self.sup, "Detalle")
        otra, _ = db.crear_ticket(self.otro, "IBK", "Consulta", "12345678", "00123456")
        db.agregar_mensaje(otra, self.admin, "Respuesta del equipo")
        db.eliminar_usuario(self.sup, self.admin, borrar_solicitudes=True)
        self.assertIsNone(db.usuario_por_id(self.sup))
        self.assertIsNone(db.ticket(r["tid"]))
        self.assertIsNotNone(db.ticket(otra))
        with db.conexion() as con:
            self.assertFalse(con.execute("PRAGMA foreign_key_check").fetchall())
            for tabla in ("mensajes", "historial", "correo_salida"):
                self.assertEqual(con.execute(f"SELECT count(*) FROM {tabla} WHERE ticket_id=?", (r["tid"],)).fetchone()[0], 0)

    def test_elimina_usuario_conservando_solicitudes(self):
        r = self.nuevo()
        db.agregar_mensaje(r["tid"], self.sup, "Detalle")
        db.eliminar_usuario(self.sup, self.admin, borrar_solicitudes=False)
        self.assertIsNone(db.usuario_por_id(self.sup))
        self.assertIsNotNone(db.ticket(r["tid"]))
        self.assertIsNone(db.ticket(r["tid"])["supervisor_id"])
        self.assertEqual(len(db.mensajes(r["tid"])), 1)
        with db.conexion() as con:
            self.assertFalse(con.execute("PRAGMA foreign_key_check").fetchall())


if __name__ == "__main__":
    unittest.main()

