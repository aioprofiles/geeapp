"""Postgres backend (Supabase / Neon) with the SAME synchronous interface as db.DB, so no handler changes.
The SQL in this code base is written in a portable subset; the few SQLite-isms are translated here.
Blocking driver on purpose: with the DB in the same region as the bot (Render Singapore <-> Supabase ap-southeast-1)
a query is a few ms. If you outgrow that, move the hot paths to an async pool.
NOT exercised against a real Postgres server in my sandbox: run the connection test in the README first."""
import logging
import re
import threading

from .db import DB, SCHEMA

log = logging.getLogger("pgdb")
SERIAL_TABLES = ("playlists", "dedications", "contribs", "reports", "jobs", "diary")
_cache: dict[str, str] = {}
_INS = re.compile(r"^\s*INSERT\s+(?:OR\s+IGNORE\s+)?INTO\s+(\w+)", re.I)


def translate_sql(sql: str) -> str:
    if sql in _cache:
        return _cache[sql]
    s = sql
    ignore = bool(re.match(r"^\s*INSERT\s+OR\s+IGNORE\s+INTO", s, re.I))
    if ignore:
        s = re.sub(r"INSERT\s+OR\s+IGNORE\s+INTO", "INSERT INTO", s, count=1, flags=re.I)
        s = s.rstrip().rstrip(";") + " ON CONFLICT DO NOTHING"
    s = re.sub(r"\browid\b", "id", s)
    if "%" in s:
        raise ValueError("literal % in SQL is not supported by the translator")
    s = s.replace("?", "%s")
    _cache[sql] = s
    return s


def translate_schema(schema: str) -> list[str]:
    s = schema.replace("INTEGER PRIMARY KEY AUTOINCREMENT", "BIGSERIAL PRIMARY KEY")
    s = re.sub(r"\bINTEGER\b", "BIGINT", s)
    s = re.sub(r"\bREAL\b", "DOUBLE PRECISION", s)
    return [x.strip() for x in s.split(";") if x.strip()]


class PgDB(DB):
    def __init__(self, url: str):
        self.url, self.c, self.lock = url, None, threading.Lock()
        self._connect()
        for stmt in translate_schema(SCHEMA):
            self._run(stmt, (), fetch=False)
        # additive migration for databases created before the privacy flag
        self._run("ALTER TABLE users ADD COLUMN IF NOT EXISTS privacy BIGINT DEFAULT 0", (), fetch=False)

    def _connect(self):
        import psycopg
        from psycopg.rows import dict_row
        # prepare_threshold=None: required behind Supabase's transaction-mode pooler (port 6543)
        self.c = psycopg.connect(self.url, autocommit=True, row_factory=dict_row, prepare_threshold=None)

    def _run(self, sql, args, fetch=True):
        import psycopg
        with self.lock:
            for attempt in (1, 2):
                try:
                    cur = self.c.execute(sql, args)
                    return cur.fetchall() if (fetch and cur.description) else None
                except (psycopg.OperationalError, psycopg.InterfaceError):
                    if attempt == 2:
                        raise
                    log.warning("db connection lost, reconnecting")
                    self._connect()

    def q(self, sql, *a) -> list[dict]:
        return [dict(r) for r in (self._run(translate_sql(sql), a) or [])]

    def x(self, sql, *a) -> int:
        t = translate_sql(sql)
        m = _INS.match(sql)
        if m and m.group(1).lower() in SERIAL_TABLES and "RETURNING" not in t.upper():
            rows = self._run(t + " RETURNING id", a)
            return int(rows[0]["id"]) if rows else 0
        self._run(t, a, fetch=False)
        return 0
