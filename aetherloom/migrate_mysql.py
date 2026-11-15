"""Offline, fail-closed SQLite -> MySQL migration. Stop API before invoking."""
import json
import os
import sqlite3
import sys
from pathlib import Path
from .server import create_app


def main():
    if not os.environ.get('AETHERLOOM_MYSQL_HOST'):
        raise SystemExit('MySQL environment is required')
    path=Path(sys.argv[1] if len(sys.argv)>1 else '/data/authority.db')
    if not path.is_file():raise SystemExit('SQLite source is absent; refusing migration')
    source=sqlite3.connect(f'file:{path.as_posix()}?mode=ro',uri=True)
    source.row_factory=sqlite3.Row
    app=create_app(path.parent)
    tables=('accounts','sessions','rooms','managers','versions','account_settings','room_settings','members','audit')
    present={r[0] for r in source.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    counts={}
    with app.state.store.connect() as target:
        target.execute('BEGIN IMMEDIATE')
        if any(target.execute(f'SELECT COUNT(*) FROM {t}').fetchone()[0] for t in tables):
            raise SystemExit('Target is nonempty; refusing overwrite. Restore backup or review migration manually.')
        for table in tables:
            if table not in present:continue
            rows=source.execute(f'SELECT * FROM {table}').fetchall()
            for row in rows:
                columns=list(row.keys())
                target.execute(f'INSERT INTO {table} ({",".join(columns)}) VALUES ({",".join("?" for _ in columns)})',tuple(row))
            counts[table]=len(rows)
            if target.execute(f'SELECT COUNT(*) FROM {table}').fetchone()[0]!=len(rows):
                raise RuntimeError('Count verification failed: '+table)
    source.close()
    print(json.dumps({'migrated_counts':counts,'sqlite_preserved':True}))


if __name__=='__main__':main()
