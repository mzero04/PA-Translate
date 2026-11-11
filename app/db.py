import json
import os
import secrets
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from flask import current_app, g
from werkzeug.security import generate_password_hash

try:  # Postgres bersifat opsional (dipakai di Vercel / produksi)
    import psycopg
    from psycopg.rows import dict_row
    INTEGRITY_ERRORS = (sqlite3.IntegrityError, psycopg.IntegrityError)
except ImportError:  # pragma: no cover
    psycopg = None
    INTEGRITY_ERRORS = (sqlite3.IntegrityError,)

DATA_DIR = Path(__file__).resolve().parent.parent / "data"

_NOW_PG = "to_char(now() at time zone 'utc','YYYY-MM-DD HH24:MI:SS')"

SCHEMA_SQLITE = [
    """CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT NOT NULL UNIQUE COLLATE NOCASE,
        full_name TEXT NOT NULL,
        password_hash TEXT NOT NULL,
        role TEXT NOT NULL DEFAULT 'user' CHECK (role IN ('admin','user')),
        is_active INTEGER NOT NULL DEFAULT 1,
        created_at TEXT NOT NULL DEFAULT (datetime('now')),
        last_login TEXT)""",
    """CREATE TABLE IF NOT EXISTS dictionary (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        position INTEGER NOT NULL,
        remove_text TEXT NOT NULL,
        replace_text TEXT NOT NULL,
        updated_by INTEGER REFERENCES users(id) ON DELETE SET NULL,
        updated_at TEXT NOT NULL DEFAULT (datetime('now')))""",
    "CREATE INDEX IF NOT EXISTS idx_dictionary_position ON dictionary(position)",
    """CREATE TABLE IF NOT EXISTS history (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        title TEXT NOT NULL, source TEXT NOT NULL, result TEXT NOT NULL,
        line_count INTEGER NOT NULL,
        created_at TEXT NOT NULL DEFAULT (datetime('now')))""",
    "CREATE INDEX IF NOT EXISTS idx_history_user ON history(user_id, id DESC)",
    """CREATE TABLE IF NOT EXISTS login_attempts (
        id INTEGER PRIMARY KEY AUTOINCREMENT, key TEXT NOT NULL, ts REAL NOT NULL)""",
    "CREATE INDEX IF NOT EXISTS idx_login_attempts_key ON login_attempts(key, ts)",
]

SCHEMA_PG = [
    f"""CREATE TABLE IF NOT EXISTS users (
        id BIGSERIAL PRIMARY KEY,
        username TEXT NOT NULL,
        full_name TEXT NOT NULL,
        password_hash TEXT NOT NULL,
        role TEXT NOT NULL DEFAULT 'user' CHECK (role IN ('admin','user')),
        is_active INTEGER NOT NULL DEFAULT 1,
        created_at TEXT NOT NULL DEFAULT {_NOW_PG},
        last_login TEXT)""",
    "CREATE UNIQUE INDEX IF NOT EXISTS idx_users_username ON users (lower(username))",
    f"""CREATE TABLE IF NOT EXISTS dictionary (
        id BIGSERIAL PRIMARY KEY,
        position INTEGER NOT NULL,
        remove_text TEXT NOT NULL,
        replace_text TEXT NOT NULL,
        updated_by BIGINT REFERENCES users(id) ON DELETE SET NULL,
        updated_at TEXT NOT NULL DEFAULT {_NOW_PG})""",
    "CREATE INDEX IF NOT EXISTS idx_dictionary_position ON dictionary(position)",
    f"""CREATE TABLE IF NOT EXISTS history (
        id BIGSERIAL PRIMARY KEY,
        user_id BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        title TEXT NOT NULL, source TEXT NOT NULL, result TEXT NOT NULL,
        line_count INTEGER NOT NULL,
        created_at TEXT NOT NULL DEFAULT {_NOW_PG})""",
    "CREATE INDEX IF NOT EXISTS idx_history_user ON history(user_id, id DESC)",
    """CREATE TABLE IF NOT EXISTS login_attempts (
        id BIGSERIAL PRIMARY KEY, key TEXT NOT NULL, ts DOUBLE PRECISION NOT NULL)""",
    "CREATE INDEX IF NOT EXISTS idx_login_attempts_key ON login_attempts(key, ts)",
]


def utcnow() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


class Conn:
    """Pembungkus tipis agar SQLite (lokal) dan Postgres (Vercel) dipakai dengan API yang sama.
    Gunakan placeholder `?`; baris bisa diakses lewat nama kolom."""

    def __init__(self, raw, pg):
        self.raw, self.pg = raw, pg

    def _sql(self, sql):
        return sql.replace("?", "%s") if self.pg else sql

    def execute(self, sql, params=()):
        return self.raw.execute(self._sql(sql), params)

    def executemany(self, sql, seq):
        if self.pg:
            with self.raw.cursor() as cur:
                cur.executemany(self._sql(sql), list(seq))
        else:
            self.raw.executemany(sql, list(seq))

    def scalar(self, sql, params=()):
        row = self.execute(sql, params).fetchone()
        return row[0] if not self.pg else next(iter(row.values()))

    def insert(self, sql, params=()):
        """INSERT dan kembalikan id baris baru."""
        if self.pg:
            return self.execute(sql + " RETURNING id", params).fetchone()["id"]
        return self.execute(sql, params).lastrowid

    def commit(self):
        self.raw.commit()

    def rollback(self):
        self.raw.rollback()

    def close(self):
        self.raw.close()


def database_url():
    return current_app.config.get("DATABASE_URL")


def get_db() -> Conn:
    if "db" not in g:
        url = database_url()
        if url:
            if psycopg is None:
                raise RuntimeError("DATABASE_URL diatur tetapi paket 'psycopg' belum terpasang.")
            raw = psycopg.connect(url, row_factory=dict_row, connect_timeout=10, prepare_threshold=None)
            g.db = Conn(raw, True)
        else:
            raw = sqlite3.connect(current_app.config["DATABASE"], timeout=15)
            raw.row_factory = sqlite3.Row
            raw.execute("PRAGMA foreign_keys = ON")
            raw.execute("PRAGMA journal_mode = WAL")
            g.db = Conn(raw, False)
    return g.db


def close_db(_exc=None):
    conn = g.pop("db", None)
    if conn is not None:
        conn.close()


def init_app(app):
    app.teardown_appcontext(close_db)


def seed_dictionary(conn):
    pairs = json.loads((DATA_DIR / "seed_dictionary.json").read_text(encoding="utf-8"))
    conn.executemany(
        "INSERT INTO dictionary (position, remove_text, replace_text) VALUES (?,?,?)",
        [(i, p["remove"].strip(), p["replace"].strip()) for i, p in enumerate(pairs, 1)],
    )


def ensure_ready(announce=False):
    """Idempotent: buat skema, isi kamus awal, dan buat admin pertama."""
    conn = get_db()
    for stmt in (SCHEMA_PG if conn.pg else SCHEMA_SQLITE):
        conn.execute(stmt)
    conn.commit()
    if conn.scalar("SELECT COUNT(*) FROM dictionary") == 0:
        seed_dictionary(conn)
    if conn.scalar("SELECT COUNT(*) FROM users") == 0:
        username = os.environ.get("ADMIN_USERNAME", "admin")
        password = os.environ.get("ADMIN_PASSWORD")
        generated = password is None
        if generated:
            password = secrets.token_urlsafe(9)
        try:
            conn.execute(
                "INSERT INTO users (username, full_name, password_hash, role) VALUES (?,?,?,'admin')",
                (username, "Administrator", generate_password_hash(password)),
            )
            conn.commit()
            if announce:
                bar = "=" * 60
                print(f"\n{bar}\n Akun admin pertama dibuat\n   username : {username}")
                print(f"   password : {password}" if generated else "   password : (dari ADMIN_PASSWORD)")
                print(f" Segera ganti password lewat menu Akun.\n{bar}\n", flush=True)
        except INTEGRITY_ERRORS:  # proses lain sudah membuatnya
            conn.rollback()
    conn.commit()
