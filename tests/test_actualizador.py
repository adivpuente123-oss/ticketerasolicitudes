import sys
import unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from actualizador import comprobar_actualizacion


class ActualizadorTests(unittest.TestCase):
    def test_main_limpio_y_cambios_compatibles(self):
        with patch('actualizador.git', side_effect=['https://github.com/adivpuente123-oss/ticketerasolicitudes.git', 'main', '', '', 'viejo', 'nuevo', '', 'deps', 'deps', 'script', 'script']) as git:
            self.assertEqual(comprobar_actualizacion(), 'nuevo')
            self.assertFalse(any(c.args[0] in ('reset', 'checkout', 'merge') for c in git.call_args_list))

    def test_no_sobrescribe_modificaciones(self):
        with patch('actualizador.git', side_effect=['https://github.com/adivpuente123-oss/ticketerasolicitudes.git', 'main', ' M app/plataforma.py']) as git:
            with self.assertRaisesRegex(ValueError, 'locales'):
                comprobar_actualizacion()
            self.assertFalse(any(c.args[0] == 'fetch' for c in git.call_args_list))

    def test_cambio_de_dependencias_requiere_instalacion(self):
        with patch('actualizador.git', side_effect=['https://github.com/adivpuente123-oss/ticketerasolicitudes.git', 'main', '', '', 'viejo', 'nuevo', '', 'deps1', 'deps2']):
            with self.assertRaisesRegex(ValueError, 'dependencias'):
                comprobar_actualizacion()

    def test_otra_rama_no_se_actualiza(self):
        with patch('actualizador.git', side_effect=['https://github.com/adivpuente123-oss/ticketerasolicitudes.git', 'otra-rama']):
            with self.assertRaisesRegex(ValueError, 'main'):
                comprobar_actualizacion()
