"""Constant application-owned DDL. No user input is interpolated into SQL."""
import sqlite3
import re
from .errors import SchemaError

STAMP = "(strftime('%Y-%m-%dT%H:%M:%fZ','now'))"
DDL = (
    f"""CREATE TABLE notebooks (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL UNIQUE CHECK(length(trim(name)) > 0),
    created_at TEXT NOT NULL DEFAULT {STAMP})""",
    f"""CREATE TABLE notes (
    id INTEGER PRIMARY KEY,
    notebook_id INTEGER NOT NULL REFERENCES notebooks(id) ON DELETE CASCADE,
    title TEXT NOT NULL CHECK(length(trim(title)) > 0),
    body TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL DEFAULT {STAMP},
    updated_at TEXT NOT NULL DEFAULT {STAMP})""",
    'CREATE INDEX notes_notebook_id_id ON notes(notebook_id,id)',
)


def objects(connection):
    return connection.execute("SELECT type,name,tbl_name,sql FROM sqlite_master "
                              "WHERE substr(name,1,7) != 'sqlite_' ORDER BY type,name").fetchall()


def normalize(rows):
    # Deliberately conservative: semantic equivalents with different DDL may fail.
    def canonical(sql):
        # Preserve quoted string/identifier content, including literal spaces.
        tokens = re.findall(r"'(?:''|[^'])*'|\"(?:\"\"|[^\"])*\"|\s+|[^\s'\"]+", sql)
        return ''.join(t for t in tokens if not t.isspace())
    return [(a, b, c, canonical(d)) for a, b, c, d in rows]


def expected():
    # Ephemeral reference solely for structural introspection, never persistence.
    with sqlite3.connect(':memory:') as c:
        for sql in DDL:
            c.execute(sql)
        return normalize(objects(c))


def verify(db):
    if db.execute_sql('PRAGMA user_version').fetchone()[0] != 1:
        raise SchemaError('database is not initialized at supported schema version 1')
    if normalize(objects(db.connection())) != expected():
        raise SchemaError('schema drift: required v1 structure differs')


def initialize(db):
    with db.atomic('IMMEDIATE'):
        version = db.execute_sql('PRAGMA user_version').fetchone()[0]
        if version == 0:
            if objects(db.connection()):
                raise SchemaError('refusing nonempty unversioned database')
            for sql in DDL:
                db.execute_sql(sql)
            db.execute_sql('PRAGMA user_version=1')
        elif version != 1:
            raise SchemaError(f'unsupported schema version {version}')
        verify(db)
