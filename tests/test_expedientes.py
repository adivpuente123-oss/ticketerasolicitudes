import sys
import tempfile
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
import db
from config import TIPO_TRANSACCION, TIPOS_CONSULTA
from solicitudes import registrar_solicitud
from archivos import validar_adjuntos, MAX_POR_ARCHIVO

PDF = b'%PDF-1.4\n1 0 obj<</Type/Catalog>>endobj\n%%EOF'


class ExpedientesTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        db.RUTA_DB = Path(self.tmp.name) / 'datos.db'
        db.iniciar()
        self.sup = db.crear_usuario('Ana', 'ana@example.com', 'supervisor')
        self.otro = db.crear_usuario('Luis', 'luis@example.com', 'supervisor')
        self.admin = db.crear_usuario('Equipo', 'equipo@example.com', 'backoffice')

    def tearDown(self):
        self.tmp.cleanup()

    def crear(self, **cambios):
        datos = dict(asunto='Preparar transacción', cartera='IBK', tipo=TIPO_TRANSACCION, documento='12345678',
                     nombre_cliente='Cliente de prueba', numero_expediente='00123-2026', juzgado='Juzgado civil', materia='Obligación de dar suma de dinero', descripcion='Solicito revisar el expediente.')
        datos.update(cambios)
        return registrar_solicitud(self.sup, self.sup, **datos)

    def test_guarda_datos_legales_y_migracion_conserva_datos(self):
        tid, _ = self.crear()
        db.iniciar()
        t = db.ticket(tid)
        self.assertEqual(t['tipo_consulta'], TIPO_TRANSACCION)
        self.assertEqual(t['numero_expediente'], '00123-2026')
        self.assertEqual(t['nombre_cliente'], 'Cliente de prueba')
        self.assertEqual(t['datos_incompletos'], 0)
        self.assertEqual(len(db.tickets_df()), 1)

    def test_campos_completos_o_documentos_obligatorios(self):
        with self.assertRaisesRegex(ValueError, 'Completa DNI'):
            self.crear(juzgado='')
        with self.assertRaisesRegex(ValueError, 'Adjunta al menos'):
            self.crear(juzgado='', datos_incompletos=True)
        self.assertEqual(len(db.tickets_df()), 0)

    def test_admite_documentos_sin_datos_y_respeta_permisos(self):
        tid, _ = self.crear(documento='', nombre_cliente='', numero_expediente='', juzgado='', materia='', datos_incompletos=True,
                            adjuntos=[{'nombre': 'expediente.pdf', 'datos': PDF}])
        a = db.adjuntos_ticket(tid, self.sup)[0]
        self.assertEqual(db.ticket(tid)['datos_incompletos'], 1)
        self.assertEqual(db.obtener_adjunto(a['id'], self.admin)['datos'], PDF)
        self.assertEqual(db.obtener_adjunto(a['id'], self.sup)['datos'], PDF)
        with self.assertRaises(PermissionError):
            db.obtener_adjunto(a['id'], self.otro)
        with self.assertRaises(PermissionError):
            db.adjuntos_ticket(tid, self.otro)

    def test_adjuntos_invalidos_no_crean_ticket(self):
        for archivo in [{'nombre': 'falso.pdf', 'datos': b'<script>no es pdf</script>'}, {'nombre': 'vacio.pdf', 'datos': b''},
                        {'nombre': 'grande.pdf', 'datos': b'%PDF-' + b'0' * MAX_POR_ARCHIVO}]:
            with self.subTest(nombre=archivo['nombre']), self.assertRaises(ValueError):
                self.crear(adjuntos=[archivo])
        self.assertEqual(len(db.tickets_df()), 0)
        self.assertEqual(validar_adjuntos([{'nombre': '../../expediente.pdf', 'datos': PDF}])[0]['nombre'], 'expediente.pdf')

    def test_borrado_de_ticket_y_usuario_elimina_documentos(self):
        tid, _ = self.crear(adjuntos=[{'nombre': 'expediente.pdf', 'datos': PDF}])
        db.eliminar_solicitud(tid, self.admin)
        with db.conexion() as con:
            self.assertEqual(con.execute('SELECT count(*) FROM adjuntos').fetchone()[0], 0)
        tid, _ = self.crear(adjuntos=[{'nombre': 'expediente.pdf', 'datos': PDF}])
        db.eliminar_usuario(self.sup, self.admin, borrar_solicitudes=True)
        with db.conexion() as con:
            self.assertEqual(con.execute('SELECT count(*) FROM adjuntos').fetchone()[0], 0)
            self.assertFalse(con.execute('PRAGMA foreign_key_check').fetchall())

    def test_equipo_completa_datos_pendientes(self):
        tid, _ = self.crear(juzgado='', datos_incompletos=True, adjuntos=[{'nombre': 'expediente.pdf', 'datos': PDF}])
        with self.assertRaises(PermissionError):
            db.actualizar_expediente(tid, self.sup, '12345678', 'Cliente', 'EXP-1', 'Juzgado', 'Materia')
        db.actualizar_expediente(tid, self.admin, '12345678', 'Cliente', 'EXP-1', 'Juzgado', 'Materia')
        self.assertEqual(db.ticket(tid)['datos_incompletos'], 0)
        self.assertEqual(db.ticket(tid)['juzgado'], 'Juzgado')

    def test_solicitud_normal_sigue_exigiendo_cuenta(self):
        with self.assertRaisesRegex(ValueError, 'cuenta'):
            self.crear(tipo=TIPOS_CONSULTA[0])
        tid, _ = self.crear(tipo=TIPOS_CONSULTA[0], cuenta='00123456')
        self.assertEqual(db.ticket(tid)['cuenta'], '00123456')

    def test_no_crea_para_otro_supervisor(self):
        with self.assertRaises(PermissionError):
            registrar_solicitud(self.otro, self.sup, asunto='Ajeno', cartera='IBK', tipo=TIPOS_CONSULTA[0], documento='12345678', cuenta='00123456', descripcion='Prueba')

    def test_expediendes_distintos_no_se_confunden_por_dni(self):
        from solicitudes import SolicitudDuplicada
        self.crear()
        self.crear(numero_expediente='OTRO-2026')
        self.assertEqual(len(db.tickets_df()), 2)
        with self.assertRaises(SolicitudDuplicada):
            self.crear()

    def test_limites_de_cantidad_y_total(self):
        from unittest.mock import patch
        with self.assertRaisesRegex(ValueError, 'hasta 5'):
            validar_adjuntos([{'nombre': 'a.pdf', 'datos': PDF}] * 6)
        with patch('archivos.MAX_TOTAL', len(PDF) * 2 - 1), self.assertRaisesRegex(ValueError, 'total'):
            validar_adjuntos([{'nombre': 'a.pdf', 'datos': PDF}] * 2)
