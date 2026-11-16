"""Adaptador pequeño para las consultas parametrizadas del portal (psycopg 3)."""
import re
import sqlite3

import psycopg
from psycopg.conninfo import conninfo_to_dict
from psycopg.rows import dict_row

TABLAS_ID = {'usuarios', 'tickets', 'historial', 'adjuntos', 'mensajes',
             'correo_salida', 'notificaciones', 'notas_internas'}


class Fila(dict):
    def __getitem__(self, key):
        return list(self.values())[key] if isinstance(key, int) else super().__getitem__(key)


class Resultado:
    def __init__(self, cursor, lastrowid=None):
        self.cursor, self.lastrowid = cursor, lastrowid
        self.description = cursor.description
        self.rowcount = cursor.rowcount

    def fetchone(self):
        r = self.cursor.fetchone()
        return Fila(r) if r is not None else None

    def fetchall(self):
        return [Fila(r) for r in self.cursor.fetchall()]

    def __iter__(self):
        return iter(self.fetchall())


def conectar(url):
    opciones = conninfo_to_dict(url)
    # Solo se permite omitir TLS para pruebas locales explícitas.
    if opciones.get('host') not in {'127.0.0.1', 'localhost'}:
        if opciones.get('sslmode', 'require') not in {'require', 'verify-ca', 'verify-full'}:
            raise ValueError('DATABASE_URL requiere TLS (sslmode=require o verify-full).')
        opciones.setdefault('sslmode', 'require')
    opciones.setdefault('connect_timeout', '15')
    try:
        con = psycopg.connect(**opciones, row_factory=dict_row, prepare_threshold=None)
    except psycopg.Error:
        raise sqlite3.DatabaseError('No se pudo conectar a PostgreSQL. Verifica DATABASE_URL y el estado del proyecto.') from None
    con.execute("SET LOCAL search_path TO ticketera")
    return Conexion(con)


class Conexion:
    def __init__(self, con):
        self.con = con

    def execute(self, sql, params=()):
        if self.con.info.transaction_status == psycopg.pq.TransactionStatus.IDLE:
            self.con.execute("SET LOCAL search_path TO ticketera")
        if sql == 'BEGIN IMMEDIATE':
            # Un mismo bloqueo transaccional para operaciones de varios pasos.
            sql = 'SELECT pg_advisory_xact_lock(8742019)'
        elif sql.startswith('PRAGMA table_info('):
            tabla = sql.split('(')[1].split(')')[0]
            sql = "SELECT column_name AS name FROM information_schema.columns WHERE table_schema='ticketera' AND table_name=%s"
            return Resultado(self.con.execute(sql, (tabla,)))
        ignorar = sql.startswith('INSERT OR IGNORE INTO ')
        sql = sql.replace('INSERT OR IGNORE INTO ', 'INSERT INTO ')
        if sql.startswith('INSERT OR REPLACE INTO servicio '):
            sql = sql.replace('INSERT OR REPLACE', 'INSERT') + ' ON CONFLICT(nombre) DO UPDATE SET actualizado_en=excluded.actualizado_en,detalle=excluded.detalle'
        if ignorar:
            sql += ' ON CONFLICT DO NOTHING'
        insercion = re.match(r'INSERT INTO (\w+)', sql)
        devolver = insercion and insercion[1] in TABLAS_ID and 'RETURNING' not in sql.upper()
        if devolver:
            sql += ' RETURNING id'
        # Las consultas del portal no contienen signos ? dentro de literales.
        sql = sql.replace('?', '%s')
        valores = tuple(bytes(p) if isinstance(p, memoryview) else p for p in params)
        try:
            cursor = self.con.execute(sql, valores or None)
            lastrowid = cursor.fetchone()['id'] if devolver else None
            return Resultado(cursor, lastrowid)
        except psycopg.IntegrityError as exc:
            raise sqlite3.IntegrityError('El registro incumple una restricción de la base de datos.') from exc
        except psycopg.Error as exc:
            raise sqlite3.DatabaseError('No se pudo completar la operación en PostgreSQL.') from exc

    def executescript(self, sql):
        for sentencia in sql.split(';'):
            if sentencia.strip():
                self.con.execute(sentencia)

    def commit(self):
        self.con.commit()

    def rollback(self):
        self.con.rollback()

    def close(self):
        self.con.close()
