"""
database.py — Database connection management for RecSignal.

Supports two backends controlled by the DB_TYPE environment variable:

  DB_TYPE=sqlite  (default) — uses SQLite via sqlite_adapter.py
                              No Oracle required; great for development.
  DB_TYPE=oracle            — uses oracledb connection pool.
                              Set DB_USER / DB_PASSWORD / DB_DSN as well.
"""

from __future__ import annotations

import logging
import os
from contextlib import contextmanager

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Mode selection
# ---------------------------------------------------------------------------
DB_TYPE = os.getenv("DB_TYPE", "sqlite").lower()  # "sqlite" | "oracle"

# ---------------------------------------------------------------------------
# Oracle configuration (only used when DB_TYPE=oracle)
# ---------------------------------------------------------------------------
DB_USER           = os.getenv("DB_USER",      "recsignal")
DB_PASSWORD       = os.getenv("DB_PASSWORD",  "recsignal123")
DB_DSN            = os.getenv("DB_DSN",       "localhost:1521/XEPDB1")
DB_POOL_MIN       = int(os.getenv("DB_POOL_MIN",  "0"))
DB_POOL_MAX       = int(os.getenv("DB_POOL_MAX",  "10"))
DB_POOL_INCREMENT = int(os.getenv("DB_POOL_INCREMENT", "1"))

_oracle_pool = None  # initialised by init_db() when DB_TYPE=oracle

# ---------------------------------------------------------------------------
# init_db — called once at FastAPI startup
# ---------------------------------------------------------------------------

def init_db() -> None:
    """Initialise the chosen database backend."""
    if DB_TYPE == "sqlite":
        from app.sqlite_adapter import init_sqlite
        init_sqlite()
        logger.info("Using SQLite dev database (DB_TYPE=sqlite).")
    else:
        _init_oracle()


def _init_oracle() -> None:
    global _oracle_pool
    try:
        import oracledb
        _oracle_pool = oracledb.create_pool(
            user=DB_USER,
            password=DB_PASSWORD,
            dsn=DB_DSN,
            min=DB_POOL_MIN,
            max=DB_POOL_MAX,
            increment=DB_POOL_INCREMENT,
        )
        logger.info("Oracle pool initialised (dsn=%s, user=%s)", DB_DSN, DB_USER)
    except Exception as exc:
        logger.warning(
            "Oracle pool creation failed (%s). "
            "DB endpoints will return 503 until Oracle is reachable.", exc
        )
        _oracle_pool = None


# ---------------------------------------------------------------------------
# close_db — called once at FastAPI shutdown
# ---------------------------------------------------------------------------

def close_db() -> None:
    """Release resources on shutdown."""
    global _oracle_pool
    if _oracle_pool:
        _oracle_pool.close()
        logger.info("Oracle connection pool closed.")


# ---------------------------------------------------------------------------
# get_connection — context manager (used during schema bootstrap in main.py)
# ---------------------------------------------------------------------------

@contextmanager
def get_connection():
    """Yield a DB connection (SQLite adapter or Oracle) as a context manager."""
    if DB_TYPE == "sqlite":
        from app.sqlite_adapter import get_sqlite_connection
        with get_sqlite_connection() as con:
            yield con
    else:
        if _oracle_pool is None:
            raise RuntimeError("Oracle pool not initialised.")
        import oracledb
        con = _oracle_pool.acquire()
        try:
            yield con
            con.commit()
        except Exception:
            con.rollback()
            raise
        finally:
            _oracle_pool.release(con)


# ---------------------------------------------------------------------------
# get_db — FastAPI dependency
# ---------------------------------------------------------------------------

def get_db():
    """
    FastAPI dependency that yields a DB connection for the current request.

    Usage::

        @router.get("/example")
        def example(con = Depends(get_db)):
            cursor = con.cursor()
            ...
    """
    if DB_TYPE == "sqlite":
        from app.sqlite_adapter import get_sqlite_db
        yield from get_sqlite_db()
    else:
        yield from _get_oracle_db()


def _get_oracle_db():
    if _oracle_pool is None:
        from fastapi import HTTPException
        raise HTTPException(503, "Database unavailable — Oracle pool not initialised.")
    import oracledb
    try:
        con = _oracle_pool.acquire()
    except Exception as exc:
        from fastapi import HTTPException
        raise HTTPException(503, f"Database unavailable: {exc}")
    try:
        yield con
        con.commit()
    except Exception:
        con.rollback()
        raise
    finally:
        _oracle_pool.release(con)

