"""Persistência em SQLite (um arquivo). Troque por PostgreSQL ao escalar."""
from __future__ import annotations

import json
import os
import sqlite3
import time
from contextlib import contextmanager
from pathlib import Path

DATA_DIR = Path(os.environ.get('SEGRESS_DATA', Path(__file__).resolve().parents[2] / 'data'))
DB_PATH = DATA_DIR / 'segress.db'
UPLOAD_DIR = DATA_DIR / 'uploads'
JSON_COLS = {'classification', 'results', 'report'}

SCHEMA = '''
CREATE TABLE IF NOT EXISTS evaluations (
  id TEXT PRIMARY KEY, filename TEXT, pdf_path TEXT, status TEXT, progress REAL DEFAULT 0,
  study_type TEXT, tertiary INTEGER DEFAULT 0, classification TEXT, results TEXT, report TEXT,
  error TEXT, created_at REAL, updated_at REAL
);
'''


def init() -> None:
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    with conn() as c:
        c.executescript(SCHEMA)


@contextmanager
def conn():
    c = sqlite3.connect(DB_PATH, timeout=30)
    c.row_factory = sqlite3.Row
    try:
        yield c
        c.commit()
    finally:
        c.close()


def _row(r: sqlite3.Row | None) -> dict | None:
    if r is None:
        return None
    d = dict(r)
    for k in JSON_COLS:
        if d.get(k):
            d[k] = json.loads(d[k])
    d['tertiary'] = bool(d.get('tertiary'))
    return d


def create(eid: str, filename: str, pdf_path: str) -> None:
    now = time.time()
    with conn() as c:
        c.execute('INSERT INTO evaluations (id, filename, pdf_path, status, created_at, updated_at) VALUES (?,?,?,?,?,?)',
                  (eid, filename, pdf_path, 'queued', now, now))


def get(eid: str) -> dict | None:
    with conn() as c:
        return _row(c.execute('SELECT * FROM evaluations WHERE id=?', (eid,)).fetchone())


def update(eid: str, **fields) -> None:
    for k in JSON_COLS & fields.keys():
        fields[k] = json.dumps(fields[k], ensure_ascii=False)
    if 'tertiary' in fields:
        fields['tertiary'] = int(bool(fields['tertiary']))
    fields['updated_at'] = time.time()
    cols = ', '.join(f'{k}=?' for k in fields)
    with conn() as c:
        c.execute(f'UPDATE evaluations SET {cols} WHERE id=?', (*fields.values(), eid))
