"""Small DB-API adapter. Production uses MySQL; SQLite supports local tools/tests.

All statements are authored by this application; values always use parameters.
The write lock serializes lease/version transactions across API workers.
"""
import os
import sqlite3
from contextlib import contextmanager


class Row(dict):
    def __getitem__(self, key):
        return tuple(self.values())[key] if isinstance(key, int) else super().__getitem__(key)


class Cursor:
    def __init__(self, cursor):
        self.cursor = cursor

    def fetchone(self):
        row = self.cursor.fetchone()
        return Row(row) if row is not None else None

    def fetchall(self):
        return [Row(r) for r in self.cursor.fetchall()]


class MySQLConnection:
    def __init__(self, raw):
        self.raw = raw
        self.locked = False
        self.lock_name='aetherloom-write:'+os.environ.get('AETHERLOOM_MYSQL_DATABASE','aetherloom')

    def execute(self, sql, args=()):
        cursor = self.raw.cursor()
        if sql.strip().upper() == 'BEGIN IMMEDIATE':
            cursor.execute("SELECT GET_LOCK(%s,15) AS acquired",(self.lock_name,))
            if cursor.fetchone()['acquired'] != 1:
                raise TimeoutError('Database write lock timeout')
            self.locked = True
            self.raw.begin()
        else:
            try:cursor.execute(sql.replace('?', '%s'), args)
            except Exception as e:
                import pymysql
                if isinstance(e,pymysql.IntegrityError):raise sqlite3.IntegrityError('Record already exists') from None
                raise
        return Cursor(cursor)

    def executescript(self, sql):
        for statement in sql.split(';'):
            statement = statement.strip()
            if not statement or statement.startswith('PRAGMA'):
                continue
            # Only static, application-owned schema definitions pass here.
            statement = statement.replace(' TEXT PRIMARY KEY', ' VARCHAR(191) PRIMARY KEY')
            for field in ('room', 'actor'):
                statement = statement.replace(field+' TEXT', field+' VARCHAR(191)')
            statement = statement.replace('manifest TEXT', 'manifest LONGTEXT').replace('detail TEXT', 'detail LONGTEXT')
            import re
            statement = re.sub(r'\bTEXT\b', 'VARCHAR(255)', statement)
            self.execute(statement)


@contextmanager
def connect(path):
    if not os.environ.get('AETHERLOOM_MYSQL_HOST'):
        connection = sqlite3.connect(path, timeout=15)
        connection.row_factory = sqlite3.Row
        try:
            with connection:
                yield connection
        finally:
            connection.close()
        return
    import pymysql
    raw = pymysql.connect(host=os.environ['AETHERLOOM_MYSQL_HOST'],
        port=int(os.environ.get('AETHERLOOM_MYSQL_PORT', '3306')),
        user=os.environ['AETHERLOOM_MYSQL_USER'], password=os.environ['AETHERLOOM_MYSQL_PASSWORD'],
        database=os.environ.get('AETHERLOOM_MYSQL_DATABASE', 'aetherloom'),
        charset='utf8mb4', cursorclass=pymysql.cursors.DictCursor, autocommit=False,
        connect_timeout=15)
    connection = MySQLConnection(raw)
    try:
        yield connection
        raw.commit()
    except BaseException:
        raw.rollback()
        raise
    finally:
        if connection.locked:
            with raw.cursor() as cursor:
                cursor.execute("SELECT RELEASE_LOCK(%s)",(connection.lock_name,))
        raw.close()
