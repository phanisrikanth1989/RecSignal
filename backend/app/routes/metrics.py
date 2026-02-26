"""
routes/metrics.py — Metric ingestion and retrieval endpoints.

Agents POST payloads here; frontend GETs historical data for charts.
"""

import logging
from datetime import datetime, timedelta
from typing import Optional

import oracledb
from fastapi import APIRouter, Depends, HTTPException, Query

from app.database import get_db
from app.models import MetricPayload, MetricResponse, MetricType
from app.services.alert_engine import AlertEngine

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/metrics", tags=["Metrics"])


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _row_to_metric(row) -> dict:
    return {
        "id": row[0],
        "server_id": row[1],
        "metric_type": row[2],
        "value": float(row[3]),
        "label": row[4],
        "timestamp": row[5],
    }


def _get_or_create_server(cursor: oracledb.Cursor, hostname: str, env: str, stype: str) -> int:
    """Return existing server ID or insert a new record."""
    cursor.execute(
        "SELECT id FROM servers WHERE hostname = :hn",
        {"hn": hostname},
    )
    row = cursor.fetchone()
    if row:
        return int(row[0])

    new_id_var = cursor.var(int)
    cursor.execute(
        """
        INSERT INTO servers (hostname, environment, type, active)
        VALUES (:hn, :env, :stype, 1)
        RETURNING id INTO :new_id
        """,
        {"hn": hostname, "env": env, "stype": stype, "new_id": new_id_var},
    )
    val = new_id_var.getvalue()
    return int(val[0] if isinstance(val, list) else val)


# ---------------------------------------------------------------------------
# Ingest endpoint (used by agents)
# ---------------------------------------------------------------------------

@router.post("/ingest", status_code=201)
def ingest_metrics(
    payload: MetricPayload,
    con: oracledb.Connection = Depends(get_db),
):
    """
    Accept a batch of metrics from a Unix or Oracle agent.

    - Auto-registers the server if it is not yet known.
    - Persists every metric to the ``metrics`` table.
    - Runs the alert engine for each metric.

    Returns a summary of how many metrics were stored and alerts generated.
    """
    cursor = con.cursor()

    server_id = _get_or_create_server(
        cursor,
        hostname=payload.hostname,
        env=payload.environment.value,
        stype=payload.server_type.value,
    )

    engine = AlertEngine(cursor, server_id, payload.environment.value, payload.hostname)
    alerts_generated = 0
    metrics_stored = 0

    for metric in payload.metrics:
        now = metric.timestamp or datetime.utcnow()
        cursor.execute(
            """
            INSERT INTO metrics (server_id, metric_type, value, label, timestamp)
            VALUES (:sid, :mtype, :val, :lbl, :ts)
            """,
            {
                "sid": server_id,
                "mtype": metric.metric_type.value,
                "val": metric.value,
                "lbl": metric.label,
                "ts": now,
            },
        )
        metrics_stored += 1

        # Evaluate alert thresholds
        alert_created = engine.evaluate(
            metric_type=metric.metric_type.value,
            value=metric.value,
            label=metric.label,
        )
        if alert_created:
            alerts_generated += 1

    logger.info(
        "Ingested %d metrics from %s; %d alerts generated",
        metrics_stored,
        payload.hostname,
        alerts_generated,
    )
    return {
        "server_id": server_id,
        "metrics_stored": metrics_stored,
        "alerts_generated": alerts_generated,
    }


# ---------------------------------------------------------------------------
# Query endpoints (used by frontend)
# ---------------------------------------------------------------------------

@router.get("/", response_model=list[MetricResponse])
def get_metrics(
    server_id: Optional[int] = Query(None, description="Filter by server"),
    metric_type: Optional[MetricType] = Query(None, description="Filter by metric type"),
    hours: int = Query(24, ge=1, le=720, description="Look-back window in hours"),
    limit: int = Query(500, ge=1, le=5000),
    con: oracledb.Connection = Depends(get_db),
):
    """
    Retrieve historical metrics.  Used by the frontend trend charts.
    """
    since = datetime.utcnow() - timedelta(hours=hours)
    sql = (
        "SELECT id, server_id, metric_type, value, label, timestamp "
        "FROM metrics WHERE timestamp >= :since"
    )
    params: dict = {"since": since}

    if server_id is not None:
        sql += " AND server_id = :sid"
        params["sid"] = server_id

    if metric_type is not None:
        sql += " AND metric_type = :mtype"
        params["mtype"] = metric_type.value

    sql += " ORDER BY timestamp DESC FETCH FIRST :lim ROWS ONLY"
    params["lim"] = limit

    cursor = con.cursor()
    cursor.execute(sql, params)
    return [_row_to_metric(r) for r in cursor.fetchall()]


@router.get("/latest", response_model=list[MetricResponse])
def get_latest_metrics(
    server_id: int = Query(..., description="Server ID"),
    con: oracledb.Connection = Depends(get_db),
):
    """
    Return the single most-recent reading for every metric type on a server.
    Used by the dashboard "current status" cards.
    """
    sql = """
        SELECT id, server_id, metric_type, value, label, timestamp
        FROM (
            SELECT id, server_id, metric_type, value, label, timestamp,
                   ROW_NUMBER() OVER (PARTITION BY metric_type, label ORDER BY timestamp DESC) AS rn
            FROM   metrics
            WHERE  server_id = :sid
        ) WHERE rn = 1
        ORDER BY metric_type
    """
    cursor = con.cursor()
    cursor.execute(sql, {"sid": server_id})
    rows = cursor.fetchall()
    if not rows:
        raise HTTPException(status_code=404, detail=f"No metrics found for server {server_id}")
    return [_row_to_metric(r) for r in rows]
