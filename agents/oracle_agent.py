#!/usr/bin/env python3
"""
agents/oracle_agent.py — RecSignal Oracle DB Monitoring Agent.

Deploy on any host that has network access to the target Oracle database.
Run via cron every 5–10 minutes:

    */5 * * * * /usr/bin/python3 /opt/recsignal/oracle_agent.py >> /var/log/recsignal-oracle-agent.log 2>&1

Required environment variables
--------------------------------
ORA_USER        : Oracle database username          (e.g. monitor_user)
ORA_PASSWORD    : Oracle database password
ORA_DSN         : Oracle DSN  host:port/service     (e.g. ora-prod:1521/PRODDB)
ORA_HOSTNAME    : Logical name for this DB server   (default: ORA_DSN host part)
RECSIGNAL_API_URL : RecSignal backend URL           (default: http://recsignal-backend:8000)
RECSIGNAL_ENV   : DEV | UAT | PROD                 (default: DEV)
RECSIGNAL_API_KEY : Optional bearer token
"""

from __future__ import annotations

import logging
import os
import sys

import oracledb
import requests

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

ORA_USER = os.environ["ORA_USER"]
ORA_PASSWORD = os.environ["ORA_PASSWORD"]
ORA_DSN = os.environ["ORA_DSN"]

# Derive a human-readable hostname from DSN if not explicitly set
_dsn_host = ORA_DSN.split(":")[0] if ":" in ORA_DSN else ORA_DSN
ORA_HOSTNAME = os.getenv("ORA_HOSTNAME", f"oracle-{_dsn_host}")

API_URL = os.getenv("RECSIGNAL_API_URL", "http://recsignal-backend:8000")
ENVIRONMENT = os.getenv("RECSIGNAL_ENV", "DEV").upper()
API_KEY = os.getenv("RECSIGNAL_API_KEY", "")
TIMEOUT_SECONDS = int(os.getenv("AGENT_TIMEOUT", "30"))

logging.basicConfig(
    stream=sys.stdout,
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | oracle_agent | %(message)s",
)
logger = logging.getLogger("oracle_agent")


# ---------------------------------------------------------------------------
# SQL queries
# ---------------------------------------------------------------------------

_SQL_TABLESPACE = """
SELECT
    df.tablespace_name,
    ROUND(NVL(df.total_mb - fs.free_mb, df.total_mb) / df.total_mb * 100, 2) AS pct_used
FROM
    (SELECT tablespace_name, ROUND(SUM(bytes) / 1048576, 2) AS total_mb
     FROM dba_data_files GROUP BY tablespace_name) df
    LEFT JOIN
    (SELECT tablespace_name, ROUND(SUM(bytes) / 1048576, 2) AS free_mb
     FROM dba_free_space GROUP BY tablespace_name) fs
    ON df.tablespace_name = fs.tablespace_name
ORDER BY pct_used DESC
"""

_SQL_BLOCKING = """
SELECT COUNT(w.sid) AS blocked_sessions
FROM   v$session w
WHERE  w.blocking_session IS NOT NULL
"""

_SQL_LONG_RUNNING = """
SELECT COUNT(*) AS long_queries
FROM   v$session s
JOIN   v$sql q ON q.sql_id = s.sql_id
WHERE  s.status   = 'ACTIVE'
  AND  s.type    != 'BACKGROUND'
  AND  q.elapsed_time > 300000000
"""


# ---------------------------------------------------------------------------
# Collection functions
# ---------------------------------------------------------------------------

def collect_tablespace(cursor: oracledb.Cursor) -> list[dict]:
    """Return TABLESPACE_USAGE metrics for every tablespace."""
    metrics = []
    try:
        cursor.execute(_SQL_TABLESPACE)
        for ts_name, pct_used in cursor.fetchall():
            metrics.append({
                "metric_type": "TABLESPACE_USAGE",
                "value": float(pct_used),
                "label": ts_name,
            })
    except oracledb.DatabaseError as exc:
        logger.error("Tablespace query failed: %s", exc)
    return metrics


def collect_blocking_sessions(cursor: oracledb.Cursor) -> list[dict]:
    """Return BLOCKING_SESSIONS count as a single metric."""
    try:
        cursor.execute(_SQL_BLOCKING)
        count = cursor.fetchone()[0]
        return [{"metric_type": "BLOCKING_SESSIONS", "value": float(count), "label": "TOTAL"}]
    except oracledb.DatabaseError as exc:
        logger.error("Blocking session query failed: %s", exc)
        return []


def collect_long_running_queries(cursor: oracledb.Cursor) -> list[dict]:
    """Return LONG_RUNNING_QUERIES count (> 5 min) as a single metric."""
    try:
        cursor.execute(_SQL_LONG_RUNNING)
        count = cursor.fetchone()[0]
        return [{"metric_type": "LONG_RUNNING_QUERIES", "value": float(count), "label": "TOTAL"}]
    except oracledb.DatabaseError as exc:
        logger.error("Long running query failed: %s", exc)
        return []


# ---------------------------------------------------------------------------
# API submission
# ---------------------------------------------------------------------------

def post_metrics(metrics: list[dict]) -> bool:
    """POST collected metrics to RecSignal backend."""
    payload = {
        "hostname": ORA_HOSTNAME,
        "environment": ENVIRONMENT,
        "server_type": "ORACLE",
        "metrics": metrics,
    }
    url = f"{API_URL.rstrip('/')}/metrics/ingest"
    headers = {"Content-Type": "application/json"}
    if API_KEY:
        headers["Authorization"] = f"Bearer {API_KEY}"

    try:
        resp = requests.post(url, json=payload, headers=headers, timeout=TIMEOUT_SECONDS)
        resp.raise_for_status()
        data = resp.json()
        logger.info(
            "Submitted %d metrics → %d stored, %d alerts generated",
            len(metrics),
            data.get("metrics_stored", 0),
            data.get("alerts_generated", 0),
        )
        return True
    except requests.RequestException as exc:
        logger.error("Failed to post metrics: %s", exc)
        return False


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    logger.info("=== RecSignal Oracle Agent — %s [%s] ===", ORA_HOSTNAME, ENVIRONMENT)

    try:
        con = oracledb.connect(user=ORA_USER, password=ORA_PASSWORD, dsn=ORA_DSN)
        logger.info("Connected to Oracle at %s", ORA_DSN)
    except oracledb.DatabaseError as exc:
        logger.critical("Cannot connect to Oracle: %s", exc)
        sys.exit(3)

    cursor = con.cursor()
    all_metrics: list[dict] = []

    try:
        all_metrics.extend(collect_tablespace(cursor))
        all_metrics.extend(collect_blocking_sessions(cursor))
        all_metrics.extend(collect_long_running_queries(cursor))
    finally:
        cursor.close()
        con.close()

    if not all_metrics:
        logger.warning("No metrics collected.")
        sys.exit(1)

    logger.info("Collected %d metric readings.", len(all_metrics))
    success = post_metrics(all_metrics)
    sys.exit(0 if success else 2)


if __name__ == "__main__":
    main()
