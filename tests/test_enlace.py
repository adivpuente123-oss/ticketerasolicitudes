import os
from pathlib import Path
import socket
import sys
import tempfile
import unittest
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from servidor import comprobar_puertos, linea_visible, url_publica
from actualizador import adquirir_bloqueo, iniciar_portal


class EnlaceTests(unittest.TestCase):
    def test_url_publica_fija_o_dominio_configurado(self):
        with patch.dict(os.environ, {'PORTAL_URL': '', 'RENDER_EXTERNAL_URL': ''}):
            self.assertEqual(url_publica(8502), 'http://localhost:8502')
        with patch.dict(os.environ, {'PORTAL_URL': 'https://solicitudes.example.com/'}):
            self.assertEqual(url_publica(8502), 'https://solicitudes.example.com')

    def test_render_usa_url_asignada_y_prioriza_dominio_propio(self):
        with patch.dict(os.environ, {'PORTAL_URL': '', 'RENDER_EXTERNAL_URL': 'https://ticketera.onrender.com/'}):
            self.assertEqual(url_publica(10000), 'https://ticketera.onrender.com')
        with patch.dict(os.environ, {'PORTAL_URL': 'https://tickets.example.com', 'RENDER_EXTERNAL_URL': 'https://ticketera.onrender.com'}):
            self.assertEqual(url_publica(10000), 'https://tickets.example.com')

    def test_no_anuncia_url_interna_y_conserva_errores(self):
        self.assertFalse(linea_visible('  URL: http://127.0.0.1:8503'))
        self.assertFalse(linea_visible('  Network URL: http://192.0.2.1:8503'))
        self.assertTrue(linea_visible('Traceback (most recent call last):'))
        self.assertTrue(linea_visible('OSError: puerto ocupado'))

    def test_no_cambia_de_puerto_si_esta_ocupado(self):
        with socket.socket() as ocupado:
            ocupado.bind(('127.0.0.1', 0))
            ocupado.listen()
            puerto = ocupado.getsockname()[1]
            with self.assertRaisesRegex(RuntimeError, 'publico'):
                comprobar_puertos(puerto, puerto + 1)
            with socket.socket() as libre:
                libre.bind(('127.0.0.1', 0))
                otro = libre.getsockname()[1]
            with self.assertRaisesRegex(RuntimeError, 'interno'):
                comprobar_puertos(otro, puerto)

    def test_reinicio_conserva_puerto_y_no_abre_navegador(self):
        with patch.dict(os.environ, {'PORT': '8502', 'PORT_INTERNO': '8503', 'BROWSER': 'browser', 'PORTAL_ABRIR_NAVEGADOR': '1'}), patch('actualizador.subprocess.Popen') as proceso:
            iniciar_portal()
            iniciar_portal()
            for llamada in proceso.call_args_list:
                env = llamada.kwargs['env']
                self.assertEqual(env['PORT'], '8502')
                self.assertEqual(env['PORT_INTERNO'], '8503')
                self.assertEqual(env['BROWSER'], 'none')
                self.assertEqual(env['PORTAL_ABRIR_NAVEGADOR'], '0')
                self.assertNotIn('cmd', llamada.args[0])

    def test_un_solo_actualizador_y_libera_bloqueo(self):
        with tempfile.TemporaryDirectory() as tmp, patch('config.RUTA_DB', Path(tmp) / 'plataforma.db'):
            primero = adquirir_bloqueo()
            try:
                with self.assertRaisesRegex(RuntimeError, 'Ya hay un actualizador'):
                    adquirir_bloqueo()
            finally:
                primero.close()
            adquirir_bloqueo().close()
