"""Exporta PostgreSQL y los documentos privados a una SQLite restaurable local.

Bloquea escrituras durante la copia. Guardar el resultado fuera de GitHub.
"""
import argparse
from contextlib import closing
import os
from pathlib import Path
import shutil
import sqlite3
import tempfile
from unittest.mock import patch

import db
from migrar_supabase import TABLAS


def respaldar(destino):
    if not db.es_postgres():
        raise ValueError('Configura DATABASE_URL del servidor.')
    destino = Path(destino)
    if destino.exists():
        raise ValueError('El archivo de destino ya existe.')
    from almacenamiento import descargar
    with tempfile.TemporaryDirectory() as tmp:
        copia = Path(tmp) / 'respaldo.db'
        with patch.dict(os.environ, {'DATABASE_URL': '', 'EXIGIR_DB_REMOTA': '0'}), patch.object(db, 'RUTA_DB', copia):
            db.iniciar()
        with closing(sqlite3.connect(copia)) as local, db.conexion() as fuente, local:
            fuente.execute('LOCK TABLE ' + ','.join(TABLAS) + ' IN SHARE MODE')
            local.execute('PRAGMA foreign_keys=ON')
            for tabla in TABLAS:
                for original in fuente.execute(f'SELECT * FROM {tabla}').fetchall():
                    fila = dict(original)
                    if tabla == 'adjuntos' and fila['objeto_storage']:
                        fila['datos'] = descargar(fila['objeto_storage'])
                        fila['objeto_storage'] = None
                    elif tabla == 'adjuntos' and isinstance(fila['datos'], memoryview):
                        fila['datos'] = bytes(fila['datos'])
                    columnas = ','.join(fila)
                    marcas = ','.join('?' for _ in fila)
                    local.execute(f'INSERT INTO {tabla} ({columnas}) VALUES ({marcas})', tuple(fila.values()))
            if local.execute('PRAGMA foreign_key_check').fetchall():
                raise RuntimeError('No se pudo verificar el respaldo.')
        # xb evita sobrescribir otra copia, incluso si aparece durante la exportación.
        with destino.open('xb') as salida, copia.open('rb') as entrada:
            shutil.copyfileobj(entrada, salida)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('destino', type=Path)
    args = parser.parse_args()
    try:
        respaldar(args.destino)
    except Exception:
        raise SystemExit('No se completó el respaldo. Verifica la conexión, almacenamiento y ruta de destino.') from None
    print('Respaldo completado con documentos. Contiene información privada: guárdalo fuera del repositorio.')
