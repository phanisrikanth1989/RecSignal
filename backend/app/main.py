"""
main.py — RecSignal FastAPI application entry point.

Startup sequence
----------------
1. Initialise Oracle connection pool.
2. Bootstrap DB schema (idempotent — skips existing tables).
3. Mount all route modules.
4. Expose /dashboard aggregate endpoint.
"""

from __future__ import annotations

import logging
import sys
from contextlib import asynccontextmanager

import oracledb
from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.database import close_db, get_db, init_db
from app.models import DDL_STATEMENTS, DashboardStats
from app.routes import alerts, config, metrics, servers

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

logging.basicConfig(
    stream=sys.stdout,
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
)
logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# DB schema bootstrap (idempotent)
# ---------------------------------------------------------------------------

def _bootstrap_schema(con: oracledb.Connection) -> None:
    """
    Execute all DDL statements defined in models.DDL_STATEMENTS.
    ORA-00955 (name already used) is silently ignored so the function
    is safe to run on every startup.
    """
    cursor = con.cursor()
    for stmt in DDL_STATEMENTS:
        try:
            cursor.execute(stmt.strip())
            con.commit()
        except oracledb.DatabaseError as exc:
            (error,) = exc.args
            if error.code in (955, 1):  # 955=already exists, 1=unique constraint
                pass
            else:
                logger.warning("DDL warning (code %d): %s", error.code, error.message)


# ---------------------------------------------------------------------------
# Application lifespan
# ---------------------------------------------------------------------------

@asynccontextmanager
async def lifespan(app: FastAPI):
    """FastAPI lifespan: runs setup on startup, teardown on shutdown."""
    logger.info("RecSignal starting up …")
    try:
        init_db()
    except Exception as exc:
        logger.error("init_db failed: %s", exc)

    # Oracle mode: bootstrap schema via DDL_STATEMENTS
    # SQLite mode: schema already created inside init_sqlite()
    from app.database import DB_TYPE
    if DB_TYPE == "oracle":
        try:
            from app.database import get_connection
            with get_connection() as con:
                _bootstrap_schema(con)
            logger.info("Oracle schema bootstrap complete.")
        except Exception as exc:
            logger.warning("Oracle schema bootstrap skipped: %s", exc)

    yield  # application is running

    logger.info("RecSignal shutting down …")
    close_db()


# ---------------------------------------------------------------------------
# FastAPI app
# ---------------------------------------------------------------------------

app = FastAPI(
    title="RecSignal",
    description="Monitoring Platform — Unix & Oracle DB health",
    version="1.0.0",
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
)

# CORS — allow the React dev server and production origin
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://localhost:5173", "*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------------------------------------------------------
# Routers
# ---------------------------------------------------------------------------

app.include_router(servers.router)
app.include_router(metrics.router)
app.include_router(alerts.router)
app.include_router(config.router)


# ---------------------------------------------------------------------------
# Dashboard aggregate endpoint
# ---------------------------------------------------------------------------

@app.get("/dashboard", response_model=DashboardStats, tags=["Dashboard"])
def dashboard(con: oracledb.Connection = Depends(get_db)):
    """
    Returns a high-level dashboard summary:
    - total server count
    - open alert counts by severity
    - server counts per environment
    - 10 most-recent open/acknowledged alerts
    """
    cursor = con.cursor()

    # Total servers
    cursor.execute("SELECT COUNT(*) FROM servers WHERE active = 1")
    total_servers = cursor.fetchone()[0]

    # Alert counts
    cursor.execute(
        """
        SELECT severity, COUNT(*)
        FROM   alerts
        WHERE  status IN ('OPEN', 'ACKNOWLEDGED')
        GROUP BY severity
        """
    )
    alert_counts: dict[str, int] = {}
    for row in cursor.fetchall():
        alert_counts[row[0]] = row[1]

    # Servers by environment
    cursor.execute(
        "SELECT environment, COUNT(*) FROM servers WHERE active = 1 GROUP BY environment"
    )
    servers_by_env: dict[str, int] = {}
    for row in cursor.fetchall():
        servers_by_env[row[0]] = row[1]

    # Recent alerts
    cursor.execute(
        """
        SELECT a.id, a.server_id, a.metric, a.severity, a.label,
               a.value, a.message, a.status, a.acknowledged_by,
               a.created_at, a.resolved_at
        FROM   alerts a
        WHERE  a.status IN ('OPEN', 'ACKNOWLEDGED')
        ORDER BY a.created_at DESC
        FETCH FIRST 10 ROWS ONLY
        """
    )
    recent_alerts = [
        {
            "id": r[0], "server_id": r[1], "metric": r[2], "severity": r[3],
            "label": r[4], "value": float(r[5]) if r[5] else 0.0, "message": r[6],
            "status": r[7], "acknowledged_by": r[8], "created_at": r[9], "resolved_at": r[10],
        }
        for r in cursor.fetchall()
    ]

    return DashboardStats(
        total_servers=total_servers,
        active_alerts=sum(alert_counts.values()),
        critical_alerts=alert_counts.get("CRITICAL", 0),
        warning_alerts=alert_counts.get("WARNING", 0),
        servers_by_env=servers_by_env,
        recent_alerts=recent_alerts,
    )


# ---------------------------------------------------------------------------
# Health check
# ---------------------------------------------------------------------------

@app.get("/health", tags=["Health"])
def health():
    """Simple liveness probe."""
    return {"status": "ok", "service": "recsignal"}
