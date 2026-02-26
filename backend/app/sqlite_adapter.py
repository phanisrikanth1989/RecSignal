"""
sqlite_adapter.py — SQLite-backed development database for RecSignal.

Activated automatically when Oracle is unavailable (DB_TYPE=sqlite, the default).
Provides adapter classes that mimic the oracledb cursor/connection interface
so all route and service code works unchanged.

SQL translation (automatic):
  FETCH FIRST N ROWS ONLY  →  LIMIT N
  FROM DUAL                →  (removed)
  RETURNING id INTO :var   →  (removed; lastrowid is used instead)
"""

from __future__ import annotations

import logging
import os
import re
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger(__name__)

SQLITE_PATH = os.getenv("SQLITE_PATH", "recsignal_dev.db")

# ---------------------------------------------------------------------------
# SQLite DDL (CREATE TABLE IF NOT EXISTS — fully idempotent)
# ---------------------------------------------------------------------------

SQLITE_DDL = [
    """CREATE TABLE IF NOT EXISTS servers (
        id          INTEGER  PRIMARY KEY AUTOINCREMENT,
        hostname    TEXT     NOT NULL UNIQUE,
        environment TEXT     NOT NULL,
        type        TEXT     NOT NULL,
        active      INTEGER  DEFAULT 1,
        created_at  DATETIME DEFAULT CURRENT_TIMESTAMP
    )""",
    """CREATE TABLE IF NOT EXISTS metrics (
        id          INTEGER  PRIMARY KEY AUTOINCREMENT,
        server_id   INTEGER  NOT NULL REFERENCES servers(id),
        metric_type TEXT     NOT NULL,
        value       REAL     NOT NULL,
        label       TEXT,
        timestamp   DATETIME DEFAULT CURRENT_TIMESTAMP
    )""",
    "CREATE INDEX IF NOT EXISTS idx_metrics_server_ts ON metrics(server_id, timestamp)",
    """CREATE TABLE IF NOT EXISTS alerts (
        id              INTEGER  PRIMARY KEY AUTOINCREMENT,
        server_id       INTEGER  NOT NULL REFERENCES servers(id),
        metric          TEXT     NOT NULL,
        severity        TEXT     NOT NULL,
        label           TEXT,
        value           REAL,
        message         TEXT,
        status          TEXT     DEFAULT 'OPEN',
        acknowledged_by TEXT,
        created_at      DATETIME DEFAULT CURRENT_TIMESTAMP,
        resolved_at     DATETIME
    )""",
    """CREATE TABLE IF NOT EXISTS config (
        id                  INTEGER PRIMARY KEY AUTOINCREMENT,
        metric_type         TEXT    NOT NULL,
        environment         TEXT    NOT NULL,
        hostname            TEXT    NOT NULL DEFAULT '',
        path_label          TEXT    NOT NULL DEFAULT '',
        warning_threshold   REAL    NOT NULL,
        critical_threshold  REAL    NOT NULL,
        UNIQUE(metric_type, environment, hostname, path_label)
    )""",
    # ── Migration: add columns to existing dev databases (safe to re-run) ────────
    # init_sqlite() catches sqlite3.Error so these silently no-op on new DBs.
    "ALTER TABLE config ADD COLUMN hostname   TEXT NOT NULL DEFAULT ''",
    "ALTER TABLE config ADD COLUMN path_label TEXT NOT NULL DEFAULT ''",
    # Seed default thresholds (INSERT OR IGNORE = no-op if already present)
    """INSERT OR IGNORE INTO config
        (metric_type, environment, warning_threshold, critical_threshold)
    SELECT 'DISK_USAGE',           'DEV',  70,  90 UNION ALL
    SELECT 'DISK_USAGE',           'UAT',  70,  85 UNION ALL
    SELECT 'DISK_USAGE',           'PROD', 75,  90 UNION ALL
    SELECT 'INODE_USAGE',          'DEV',  70,  90 UNION ALL
    SELECT 'INODE_USAGE',          'UAT',  70,  85 UNION ALL
    SELECT 'INODE_USAGE',          'PROD', 75,  90 UNION ALL
    SELECT 'MEMORY_USAGE',         'DEV',  75,  90 UNION ALL
    SELECT 'MEMORY_USAGE',         'UAT',  75,  90 UNION ALL
    SELECT 'MEMORY_USAGE',         'PROD', 80,  95 UNION ALL
    SELECT 'CPU_LOAD',             'DEV',  70,  90 UNION ALL
    SELECT 'CPU_LOAD',             'UAT',  70,  90 UNION ALL
    SELECT 'CPU_LOAD',             'PROD', 75,  95 UNION ALL
    SELECT 'TABLESPACE_USAGE',     'DEV',  75,  90 UNION ALL
    SELECT 'TABLESPACE_USAGE',     'UAT',  75,  90 UNION ALL
    SELECT 'TABLESPACE_USAGE',     'PROD', 80,  95 UNION ALL
    SELECT 'BLOCKING_SESSIONS',    'DEV',   5,  20 UNION ALL
    SELECT 'BLOCKING_SESSIONS',    'UAT',   5,  20 UNION ALL
    SELECT 'BLOCKING_SESSIONS',    'PROD',  2,  10 UNION ALL
    SELECT 'LONG_RUNNING_QUERIES', 'DEV',  30, 120 UNION ALL
    SELECT 'LONG_RUNNING_QUERIES', 'UAT',  30, 120 UNION ALL
    SELECT 'LONG_RUNNING_QUERIES', 'PROD', 15,  60""",
]

# ---------------------------------------------------------------------------
# SQL translator — Oracle → SQLite
# ---------------------------------------------------------------------------

_FETCH_RE     = re.compile(r'FETCH\s+FIRST\s+(\S+)\s+ROWS\s+ONLY', re.IGNORECASE)
_DUAL_RE      = re.compile(r'\bFROM\s+DUAL\b', re.IGNORECASE)
_RETURNING_RE = re.compile(r'\s*RETURNING\s+\w+\s+INTO\s+:\w+', re.IGNORECASE)


def _translate(sql: str, params: Optional[dict]) -> tuple[str, Optional[dict]]:
    """Translate Oracle-specific SQL to SQLite-compatible SQL."""
    sql = _DUAL_RE.sub('', sql)
    sql = _FETCH_RE.sub(r'LIMIT \1', sql)
    sql = _RETURNING_RE.sub('', sql)           # handled via lastrowid
    if params and isinstance(params, dict):
        params = {k: v for k, v in params.items() if not isinstance(v, _VarProxy)}
    return sql.strip(), params


# ---------------------------------------------------------------------------
# VarProxy — mimics oracledb cursor.var() for RETURNING INTO patterns
# ---------------------------------------------------------------------------

class _VarProxy:
    """
    Returned by CursorAdapter.var().
    After execute(), its internal value is set to cursor.lastrowid.
    Routes call: val = proxy.getvalue(); id = val[0] if isinstance(val, list) else val
    """
    def __init__(self) -> None:
        self._value: Optional[int] = None

    def getvalue(self) -> list:
        return [self._value]


# ---------------------------------------------------------------------------
# Cursor adapter
# ---------------------------------------------------------------------------

class _CursorAdapter:
    """Wraps sqlite3.Cursor with an oracledb-compatible interface."""

    def __init__(self, cur: sqlite3.Cursor, con_adapter: "_ConnectionAdapter") -> None:
        self._cur = cur
        self._con = con_adapter
        self.rowcount: int = 0

    def var(self, typ: Any) -> _VarProxy:
        """Create a VarProxy — populated with lastrowid after execute()."""
        proxy = _VarProxy()
        self._con._pending_proxies.append(proxy)
        return proxy

    def execute(self, sql: str, params: Optional[dict] = None) -> None:
        sql, params = _translate(sql, params)
        try:
            if params:
                self._cur.execute(sql, params)
            else:
                self._cur.execute(sql)
        except sqlite3.IntegrityError:
            raise  # let callers handle constraint errors
        except sqlite3.Error as exc:
            logger.error("SQLite execute error: %s | SQL: %.200s", exc, sql)
            raise

        self.rowcount = self._cur.rowcount
        # Populate VarProxies with the inserted row id
        for proxy in self._con._pending_proxies:
            proxy._value = self._cur.lastrowid
        self._con._pending_proxies.clear()

    def fetchone(self) -> Optional[tuple]:
        row = self._cur.fetchone()
        if row is None:
            return None
        return tuple(row)          # sqlite3.Row → plain tuple (matches oracledb)

    def fetchall(self) -> list[tuple]:
        return [tuple(r) for r in self._cur.fetchall()]


# ---------------------------------------------------------------------------
# Connection adapter
# ---------------------------------------------------------------------------

class _ConnectionAdapter:
    """Wraps sqlite3.Connection to match the oracledb.Connection interface."""

    def __init__(self, con: sqlite3.Connection) -> None:
        self._con = con
        self._pending_proxies: list[_VarProxy] = []

    def cursor(self) -> _CursorAdapter:
        return _CursorAdapter(self._con.cursor(), self)

    def commit(self) -> None:
        self._con.commit()

    def rollback(self) -> None:
        self._con.rollback()

    def close(self) -> None:
        self._con.close()


# ---------------------------------------------------------------------------
# Bootstrap
# ---------------------------------------------------------------------------

def init_sqlite() -> None:
    """Create schema + seed data in the SQLite dev database."""
    con = sqlite3.connect(SQLITE_PATH)
    con.row_factory = sqlite3.Row
    cur = con.cursor()
    cur.execute("PRAGMA foreign_keys = ON")
    for stmt in SQLITE_DDL:
        try:
            cur.execute(stmt.strip())
        except sqlite3.Error as exc:
            logger.warning("SQLite DDL: %s", exc)
    con.commit()
    con.close()
    logger.info("SQLite dev DB ready → %s", Path(SQLITE_PATH).resolve())


# ---------------------------------------------------------------------------
# Connection helpers
# ---------------------------------------------------------------------------

@contextmanager
def get_sqlite_connection():
    """Context manager that yields a wrapped SQLite connection."""
    con = sqlite3.connect(SQLITE_PATH, detect_types=sqlite3.PARSE_DECLTYPES)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys = ON")
    adapter = _ConnectionAdapter(con)
    try:
        yield adapter
        con.commit()
    except Exception:
        con.rollback()
        raise
    finally:
        con.close()


def get_sqlite_db():
    """FastAPI dependency — yields a wrapped SQLite connection."""
    with get_sqlite_connection() as con:
        yield con
