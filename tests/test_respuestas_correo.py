import os
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
import db
from correo import crear_ticket_desde_correo
from servicio_outlook import recibir, enviar
from servicio_graph import Graph


class RespuestasCorreoTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        db.RUTA_DB = Path(self.tmp.name) / 'correo.db'
        db.iniciar()
        self.sup = db.crear_usuario('Ana', 'ana@example.com', 'supervisor')
        self.otro = db.crear_usuario('Luis', 'luis@example.com', 'supervisor')
        self.r = crear_ticket_desde_correo('ana@example.com', 'Consulta original', 'Detalle', '<original>')

    def tearDown(self):
        self.tmp.cleanup()

    def item(self, mid, responde_a=''):
        props = Mock()
        props.GetProperty.side_effect = lambda prop: responde_a if '1042001F' in prop else mid
        return SimpleNamespace(Class=43, PropertyAccessor=props, ConversationID='hilo', EntryID=mid,
                               Subject='RE: Consulta original' if responde_a else 'Consulta original', Body='Más detalle', Categories='', Save=Mock())

    def test_outlook_borrador_conserva_asunto_citado_y_no_crea_mensaje(self):
        item = self.item('<original>')
        mail = SimpleNamespace(Subject='RE: Consulta original', To='ana@example.com',
                               HTMLBody='<html><body><blockquote>Mensaje del supervisor</blockquote></body></html>', Save=Mock(), Send=Mock(), Parent=SimpleNamespace(EntryID='drafts'))
        item.Reply = Mock(return_value=mail)
        app, cuenta = Mock(), Mock()
        cuenta.DeliveryStore.GetDefaultFolder.return_value.Folders.Item.return_value.Items = [item]
        cuenta.DeliveryStore.GetDefaultFolder.return_value.EntryID = 'drafts'
        enviar(app, cuenta)
        item.Reply.assert_called_once()
        app.CreateItem.assert_not_called()
        self.assertEqual(mail.Subject, 'RE: Consulta original')
        self.assertIn('<blockquote>Mensaje del supervisor</blockquote>', mail.HTMLBody)
        self.assertIn('Tu solicitud', mail.HTMLBody)
        mail.Save.assert_called_once()
        mail.Send.assert_not_called()

    def test_outlook_original_no_encontrado_no_crea_correo_nuevo(self):
        app, cuenta = Mock(), Mock()
        cuenta.DeliveryStore.GetDefaultFolder.return_value.Folders.Item.return_value.Items = []
        enviar(app, cuenta)
        app.CreateItem.assert_not_called()
        with db.conexion() as con:
            self.assertEqual(con.execute('SELECT estado FROM correo_salida').fetchone()[0], 'revisar')

    def test_outlook_reply_sin_codigo_se_agrega_al_ticket_y_nuevo_asunto_no(self):
        root, respuesta = self.item('<original>'), self.item('<respuesta>', '<original>')
        with patch('servicio_outlook.remitente_de', return_value='ana@example.com'), patch('servicio_outlook.fecha_de', return_value='2026-11-10'):
            recibir(SimpleNamespace(Items=[respuesta, root]))
        self.assertEqual(len(db.tickets_df()), 1)
        self.assertEqual(len(db.mensajes(self.r['tid'])), 1)
        with patch('servicio_outlook.remitente_de', return_value='ana@example.com'), patch('servicio_outlook.fecha_de', return_value='2026-11-10'):
            recibir(SimpleNamespace(Items=[self.item('<nuevo>')]))
        self.assertEqual(len(db.tickets_df()), 2)

    def test_hilo_no_da_permiso_a_otro_supervisor(self):
        root, respuesta = self.item('<original>'), self.item('<respuesta>', '<original>')
        with patch('servicio_outlook.remitente_de', return_value='luis@example.com'), patch('servicio_outlook.fecha_de', return_value='2026-11-10'):
            recibir(SimpleNamespace(Items=[respuesta, root]))
        self.assertEqual(len(db.mensajes(self.r['tid'])), 0)
        self.assertEqual(respuesta.Categories, 'SIN TICKET')

    def test_graph_respuesta_sin_codigo_y_original_no_encontrado(self):
        with patch.dict(os.environ, {'MS_TENANT_ID': 'x', 'MS_CLIENT_ID': 'x', 'MS_CLIENT_SECRET': 'x', 'MS_FOLDER_ID': 'solicitudes'}):
            graph = Graph()
            respuesta = {'id': 'nuevo-id', 'internetMessageId': '<respuesta>', 'conversationId': 'hilo',
                         'internetMessageHeaders': [{'name': 'In-Reply-To', 'value': '<original>'}],
                         'from': {'emailAddress': {'address': 'ana@example.com'}}, 'subject': 'RE: Consulta original', 'body': {'content': 'Detalle'}}
            with patch.object(graph, 'coleccion', return_value=iter([respuesta])), patch.object(graph, 'request'):
                graph.recibir()
            self.assertEqual(len(db.tickets_df()), 1)
            self.assertEqual(len(db.mensajes(self.r['tid'])), 1)
            with patch.object(graph, 'coleccion', return_value=iter([])), patch.object(graph, 'request') as req:
                with self.assertRaises(RuntimeError):
                    graph.enviar()
                req.assert_not_called()

    def test_no_genera_borrador_interno_pendiente_de_version_anterior(self):
        with db.conexion() as con:
            con.execute("DELETE FROM correo_salida")
            con.execute("INSERT INTO correo_salida(ticket_id,destinatario,asunto,cuerpo) VALUES(?,?,?,?)", (self.r['tid'], 'adiv.puente@goexpertis.com', 'Aviso', 'Texto'))
        app, cuenta = Mock(), Mock()
        enviar(app, cuenta)
        app.CreateItem.assert_not_called()
        with db.conexion() as con:
            self.assertEqual(con.execute('SELECT estado FROM correo_salida').fetchone()[0], 'omitido')
