"""
routes/config.py — Threshold configuration endpoints.
"""

import logging
from typing import Optional

import oracledb
from fastapi import APIRouter, Depends, HTTPException, Query

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
        "hostname": row[3],
        "path_label": row[4],
        "warning_threshold": float(row[5]),
        "critical_threshold": float(row[6]),
    }


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.get("/", response_model=list[ThresholdConfigResponse])
def list_configs(
    hostname: Optional[str] = Query(
        None,
        description="Filter by hostname; pass empty string '' to retrieve only global env-level defaults",
    ),
    con: oracledb.Connection = Depends(get_db),
):
    """Return all threshold configurations, optionally filtered by hostname."""
    cursor = con.cursor()
    sql = (
        "SELECT id, metric_type, environment, hostname, path_label, "
        "warning_threshold, critical_threshold FROM config WHERE 1=1"
    )
    params: dict = {}
    if hostname is not None:
        sql += " AND hostname = :hn"
        params["hn"] = hostname
    sql += " ORDER BY environment, metric_type, hostname, path_label"
    cursor.execute(sql, params)
    return [_row_to_config(r) for r in cursor.fetchall()]


@router.get("/{metric_type}/{environment}", response_model=ThresholdConfigResponse)
def get_config(
    metric_type: MetricType,
    environment: Environment,
    hostname: str = Query('', description="Specific server hostname; empty for global"),
    path_label: str = Query('', description="Specific path/label; empty for all"),
    con: oracledb.Connection = Depends(get_db),
):
    """Return a specific threshold config by metric, environment, and optional hostname/path."""
    cursor = con.cursor()
    cursor.execute(
        "SELECT id, metric_type, environment, hostname, path_label, "
        "warning_threshold, critical_threshold "
        "FROM config WHERE metric_type = :mt AND environment = :env "
        "AND hostname = :hn AND path_label = :lbl",
        {"mt": metric_type.value, "env": environment.value, "hn": hostname, "lbl": path_label},
    )
    row = cursor.fetchone()
    if not row:
        raise HTTPException(
            status_code=404,
            detail=(
                f"No config for {metric_type.value}/{environment.value}"
                + (f" hostname='{hostname}'" if hostname else "")
                + (f" path='{path_label}'" if path_label else "")
            ),
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
        "SELECT id FROM config WHERE metric_type = :mt AND environment = :env "
        "AND hostname = :hn AND path_label = :lbl",
        {
            "mt": payload.metric_type.value,
            "env": payload.environment.value,
            "hn": payload.hostname,
            "lbl": payload.path_label,
        },
    )
    row = cursor.fetchone()

    if row:
        cursor.execute(
            """
            UPDATE config
            SET    warning_threshold  = :warn,
                   critical_threshold = :crit
            WHERE  metric_type = :mt AND environment = :env
              AND  hostname = :hn AND path_label = :lbl
            """,
            {
                "warn": payload.warning_threshold,
                "crit": payload.critical_threshold,
                "mt": payload.metric_type.value,
                "env": payload.environment.value,
                "hn": payload.hostname,
                "lbl": payload.path_label,
            },
        )
    else:
        cursor.execute(
            """
            INSERT INTO config
                (metric_type, environment, hostname, path_label,
                 warning_threshold, critical_threshold)
            VALUES (:mt, :env, :hn, :lbl, :warn, :crit)
            """,
            {
                "mt": payload.metric_type.value,
                "env": payload.environment.value,
                "hn": payload.hostname,
                "lbl": payload.path_label,
                "warn": payload.warning_threshold,
                "crit": payload.critical_threshold,
            },
        )

    logger.info(
        "Config updated: %s/%s hostname=%s path=%s warn=%.1f crit=%.1f",
        payload.metric_type.value,
        payload.environment.value,
        payload.hostname or "(global)",
        payload.path_label or "(all)",
        payload.warning_threshold,
        payload.critical_threshold,
    )
    return get_config(
        payload.metric_type, payload.environment,
        payload.hostname, payload.path_label, con,
    )


@router.delete("/{config_id}", status_code=204)
def delete_config(config_id: int, con: oracledb.Connection = Depends(get_db)):
    """
    Delete a threshold override by its numeric ID.
    Use this to remove server/path-specific overrides (global env defaults should be edited, not deleted).
    """
    cursor = con.cursor()
    cursor.execute("SELECT id FROM config WHERE id = :cid", {"cid": config_id})
    if not cursor.fetchone():
        raise HTTPException(status_code=404, detail=f"Config {config_id} not found")
    cursor.execute("DELETE FROM config WHERE id = :cid", {"cid": config_id})
    logger.info("Config %d deleted", config_id)
