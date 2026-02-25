"""
routes/alerts.py — Alert listing, acknowledgement and resolution.
"""

import logging
from datetime import datetime
from typing import Optional

import oracledb
from fastapi import APIRouter, Depends, HTTPException, Query

from app.database import get_db
from app.models import AlertAcknowledge, AlertResponse, AlertStatus

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/alerts", tags=["Alerts"])


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _row_to_alert(row) -> dict:
    return {
        "id": row[0],
        "server_id": row[1],
        "metric": row[2],
        "severity": row[3],
        "label": row[4],
        "value": float(row[5]) if row[5] is not None else 0.0,
        "message": row[6],
        "status": row[7],
        "acknowledged_by": row[8],
        "created_at": row[9],
        "resolved_at": row[10],
    }


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.get("/", response_model=list[AlertResponse])
def list_alerts(
    status: Optional[AlertStatus] = Query(None, description="Filter by alert status"),
    server_id: Optional[int] = Query(None, description="Filter by server"),
    severity: Optional[str] = Query(None, description="Filter by severity: WARNING|CRITICAL"),
    environment: Optional[str] = Query(None, description="Filter by environment: DEV|UAT|PROD"),
    limit: int = Query(200, ge=1, le=1000),
    con: oracledb.Connection = Depends(get_db),
):
    """
    Retrieve alerts with optional filters.
    """
    sql = """
        SELECT a.id, a.server_id, a.metric, a.severity, a.label,
               a.value, a.message, a.status, a.acknowledged_by,
               a.created_at, a.resolved_at
        FROM   alerts a
        JOIN   servers s ON s.id = a.server_id
        WHERE  1=1
    """
    params: dict = {}

    if status:
        sql += " AND a.status = :status"
        params["status"] = status.value

    if server_id is not None:
        sql += " AND a.server_id = :sid"
        params["sid"] = server_id

    if severity:
        sql += " AND a.severity = :sev"
        params["sev"] = severity.upper()

    if environment:
        sql += " AND s.environment = :env"
        params["env"] = environment.upper()

    sql += " ORDER BY a.created_at DESC FETCH FIRST :lim ROWS ONLY"
    params["lim"] = limit

    cursor = con.cursor()
    cursor.execute(sql, params)
    return [_row_to_alert(r) for r in cursor.fetchall()]


@router.get("/{alert_id}", response_model=AlertResponse)
def get_alert(alert_id: int, con: oracledb.Connection = Depends(get_db)):
    """Return a single alert by ID."""
    cursor = con.cursor()
    cursor.execute(
        """
        SELECT id, server_id, metric, severity, label, value, message,
               status, acknowledged_by, created_at, resolved_at
        FROM   alerts
        WHERE  id = :aid
        """,
        {"aid": alert_id},
    )
    row = cursor.fetchone()
    if not row:
        raise HTTPException(status_code=404, detail=f"Alert {alert_id} not found")
    return _row_to_alert(row)


@router.post("/acknowledge", response_model=AlertResponse)
def acknowledge_alert(
    payload: AlertAcknowledge,
    con: oracledb.Connection = Depends(get_db),
):
    """
    Acknowledge an open alert.
    Transitions status: OPEN → ACKNOWLEDGED.
    """
    cursor = con.cursor()
    cursor.execute(
        "SELECT status FROM alerts WHERE id = :aid",
        {"aid": payload.alert_id},
    )
    row = cursor.fetchone()
    if not row:
        raise HTTPException(status_code=404, detail=f"Alert {payload.alert_id} not found")
    if row[0] != AlertStatus.OPEN.value:
        raise HTTPException(
            status_code=400,
            detail=f"Alert is already {row[0]}. Only OPEN alerts can be acknowledged.",
        )

    cursor.execute(
        """
        UPDATE alerts
        SET    status = 'ACKNOWLEDGED',
               acknowledged_by = :by
        WHERE  id = :aid
        """,
        {"by": payload.acknowledged_by, "aid": payload.alert_id},
    )
    logger.info("Alert %d acknowledged by %s", payload.alert_id, payload.acknowledged_by)
    return get_alert(payload.alert_id, con)


@router.post("/{alert_id}/resolve", response_model=AlertResponse)
def resolve_alert(alert_id: int, con: oracledb.Connection = Depends(get_db)):
    """
    Manually resolve an alert.
    Transitions status: OPEN|ACKNOWLEDGED → RESOLVED.
    """
    cursor = con.cursor()
    cursor.execute("SELECT status FROM alerts WHERE id = :aid", {"aid": alert_id})
    row = cursor.fetchone()
    if not row:
        raise HTTPException(status_code=404, detail=f"Alert {alert_id} not found")
    if row[0] == AlertStatus.RESOLVED.value:
        raise HTTPException(status_code=400, detail="Alert is already resolved.")

    cursor.execute(
        """
        UPDATE alerts
        SET    status = 'RESOLVED',
               resolved_at = :now
        WHERE  id = :aid
        """,
        {"now": datetime.utcnow(), "aid": alert_id},
    )
    logger.info("Alert %d resolved.", alert_id)
    return get_alert(alert_id, con)


@router.get("/summary/counts")
def alert_summary(con: oracledb.Connection = Depends(get_db)):
    """
    Return alert counts grouped by environment, severity and status.
    Used by the Dashboard header stats.
    """
    sql = """
        SELECT s.environment, a.severity, a.status, COUNT(*) AS cnt
        FROM   alerts a
        JOIN   servers s ON s.id = a.server_id
        GROUP BY s.environment, a.severity, a.status
        ORDER BY s.environment, a.severity
    """
    cursor = con.cursor()
    cursor.execute(sql)
    result: dict = {}
    for env, sev, status, cnt in cursor.fetchall():
        result.setdefault(env, {}).setdefault(sev, {})[status] = cnt
    return result
