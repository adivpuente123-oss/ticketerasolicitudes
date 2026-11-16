"""Migración de una copia consistente SQLite a un destino PostgreSQL vacío.

Credenciales por variables de entorno. Nunca modifica el archivo de origen.
"""
import argparse
from contextlib import closing
import os
from pathlib import Path
import sqlite3
import tempfile
from unittest.mock import patch
import uuid

import db
from postgres import TABLAS_ID

TABLAS = ['usuarios', 'tickets', 'mensajes', 'historial', 'notas_internas',
          'adjuntos', 'correo_salida', 'notificaciones', 'correos_eliminados', 'servicio']


def migrar(origen):
    if not db.es_postgres():
        raise ValueError('Configura DATABASE_URL del destino PostgreSQL.')
    origen = Path(origen).resolve(strict=True)
    from almacenamiento import comprobar, subir
    comprobar()
    db.iniciar()
    with tempfile.TemporaryDirectory() as tmp:
        copia = Path(tmp) / 'copia.db'
        with closing(sqlite3.connect(origen.as_uri() + '?mode=ro', uri=True)) as fuente, closing(sqlite3.connect(copia)) as destino:
            fuente.backup(destino)
        # Completar migraciones locales sobre la copia, jamás sobre el original.
        with patch.dict(os.environ, {'DATABASE_URL': '', 'EXIGIR_DB_REMOTA': '0'}), patch.object(db, 'RUTA_DB', copia):
            db.iniciar()
        fuente = sqlite3.connect(copia)
        fuente.row_factory = sqlite3.Row
        try:
            with db.conexion() as con:
                con.execute('BEGIN IMMEDIATE')
                con.execute('LOCK TABLE ' + ','.join(TABLAS + ['sesiones']) + ' IN ACCESS EXCLUSIVE MODE')
                if any(con.execute(f'SELECT COUNT(*) FROM {t}').fetchone()[0] for t in TABLAS + ['sesiones', 'objetos_por_borrar']):
                    raise ValueError('El destino no está vacío. No se reemplazó ningún registro.')
                conteos = {}
                for tabla in TABLAS:
                    cantidad = 0
                    for original in fuente.execute(f'SELECT * FROM {tabla}'):
                        cantidad += 1
                        fila = dict(original)
                        if tabla == 'adjuntos':
                            if fila['objeto_storage'] or fila['datos'] is None:
                                raise ValueError('El origen debe ser una base local con todos sus adjuntos.')
                            clave = f"tickets/{fila['ticket_id']}/{uuid.uuid4().hex}"
                            db.preparar_subida(con, clave)
                            subir(clave, fila['datos'], fila['tipo_mime'])
                            fila['datos'], fila['objeto_storage'] = None, clave
                        if tabla == 'correo_salida' and fila['estado'] in {'pendiente', 'procesando'}:
                            fila['estado'] = 'revisar'
                            fila['error'] = 'Migrado: revisar Outlook antes de reactivar esta entrada.'
                        columnas = ','.join(fila)
                        marcas = ','.join('?' for _ in fila)
                        con.execute(f'INSERT INTO {tabla} ({columnas}) VALUES ({marcas})', tuple(fila.values()))
                        if tabla == 'adjuntos':
                            con.execute('DELETE FROM objetos_por_borrar WHERE clave=?', (fila['objeto_storage'],))
                    conteos[tabla] = cantidad
                    if tabla in TABLAS_ID:
                        con.execute(f"SELECT setval(pg_get_serial_sequence('{tabla}','id'), COALESCE((SELECT MAX(id) FROM {tabla}),1), EXISTS(SELECT 1 FROM {tabla}))")
                # Sesiones anteriores se revocan: cada persona volverá a iniciar sesión.
                for tabla, esperado in conteos.items():
                    if con.execute(f'SELECT COUNT(*) FROM {tabla}').fetchone()[0] != esperado:
                        raise RuntimeError('Los conteos no coinciden; se canceló la migración.')
                return conteos
        finally:
            fuente.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('sqlite', type=Path)
    args = parser.parse_args()
    try:
        conteos = migrar(args.sqlite)
    except Exception:
        # No imprimir URLs, contraseñas ni detalles de conexión del proveedor.
        raise SystemExit('No se completó la migración. Verifica configuración, bucket privado y destino vacío. El archivo original se conserva.') from None
    print('Migración completada. Registros por tabla:')
    for tabla, cantidad in conteos.items():
        print(f'  {tabla}: {cantidad}')
    print('Inicia sesión y verifica los adjuntos antes de retirar la instalación local. El correo queda sujeto a revisión.')


if __name__ == '__main__':
    main()
