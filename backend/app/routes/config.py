"""
routes/config.py — Threshold configuration endpoints.
"""

import logging

import oracledb
from fastapi import APIRouter, Depends, HTTPException

from app.database import get_db
from app.models import Environment, MetricType, ThresholdConfig, ThresholdConfigResponse

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/config", tags=["Config"])


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _row_to_config(row) -> dict:
    return {
        "id": row[0],
        "metric_type": row[1],
        "environment": row[2],
        "warning_threshold": float(row[3]),
        "critical_threshold": float(row[4]),
    }


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.get("/", response_model=list[ThresholdConfigResponse])
def list_configs(con: oracledb.Connection = Depends(get_db)):
    """Return all threshold configurations."""
    cursor = con.cursor()
    cursor.execute(
        "SELECT id, metric_type, environment, warning_threshold, critical_threshold "
        "FROM config ORDER BY environment, metric_type"
    )
    return [_row_to_config(r) for r in cursor.fetchall()]


@router.get("/{metric_type}/{environment}", response_model=ThresholdConfigResponse)
def get_config(
    metric_type: MetricType,
    environment: Environment,
    con: oracledb.Connection = Depends(get_db),
):
    """Return a specific threshold config."""
    cursor = con.cursor()
    cursor.execute(
        "SELECT id, metric_type, environment, warning_threshold, critical_threshold "
        "FROM config WHERE metric_type = :mt AND environment = :env",
        {"mt": metric_type.value, "env": environment.value},
    )
    row = cursor.fetchone()
    if not row:
        raise HTTPException(
            status_code=404,
            detail=f"No config for {metric_type.value}/{environment.value}",
        )
    return _row_to_config(row)


@router.post("/update", response_model=ThresholdConfigResponse)
def update_config(
    payload: ThresholdConfig,
    con: oracledb.Connection = Depends(get_db),
):
    """
    Create or update a threshold configuration for a metric/environment pair.

    Rules:
    - ``warning_threshold`` must be less than ``critical_threshold``.
    """
    if payload.warning_threshold >= payload.critical_threshold:
        raise HTTPException(
            status_code=422,
            detail="warning_threshold must be strictly less than critical_threshold.",
        )

    cursor = con.cursor()

    # Check if record exists
    cursor.execute(
        "SELECT id FROM config WHERE metric_type = :mt AND environment = :env",
        {"mt": payload.metric_type.value, "env": payload.environment.value},
    )
    row = cursor.fetchone()

    if row:
        cursor.execute(
            """
            UPDATE config
            SET    warning_threshold  = :warn,
                   critical_threshold = :crit
            WHERE  metric_type = :mt AND environment = :env
            """,
            {
                "warn": payload.warning_threshold,
                "crit": payload.critical_threshold,
                "mt": payload.metric_type.value,
                "env": payload.environment.value,
            },
        )
    else:
        cursor.execute(
            """
            INSERT INTO config (metric_type, environment, warning_threshold, critical_threshold)
            VALUES (:mt, :env, :warn, :crit)
            """,
            {
                "mt": payload.metric_type.value,
                "env": payload.environment.value,
                "warn": payload.warning_threshold,
                "crit": payload.critical_threshold,
            },
        )

    logger.info(
        "Config updated: %s/%s warn=%.1f crit=%.1f",
        payload.metric_type.value,
        payload.environment.value,
        payload.warning_threshold,
        payload.critical_threshold,
    )
    return get_config(payload.metric_type, payload.environment, con)
