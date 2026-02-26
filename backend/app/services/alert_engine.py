"""
services/alert_engine.py — Core alert evaluation and deduplication logic.

The AlertEngine is instantiated once per metrics-ingest request.
It:
  1. Fetches threshold config for (metric_type, environment).
  2. Classifies the metric value as OK / WARNING / CRITICAL.
  3. Suppresses duplicate open alerts for the same (server, metric, label).
  4. Auto-resolves previously open alerts when value returns to OK.
  5. Inserts new alert rows when thresholds are breached.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Optional

import oracledb

logger = logging.getLogger(__name__)

# Larger-is-worse metrics (percentage-based).  BLOCKING_SESSIONS and
# LONG_RUNNING_QUERIES are count/duration-based — still larger-is-worse.
_LARGER_IS_WORSE = {
    "DISK_USAGE", "INODE_USAGE", "MEMORY_USAGE", "CPU_LOAD",
    "TABLESPACE_USAGE", "BLOCKING_SESSIONS", "LONG_RUNNING_QUERIES",
}


@dataclass
class Threshold:
    warning: float
    critical: float


class AlertEngine:
    """
    Stateless alert evaluator that operates within an existing DB transaction.

    Parameters
    ----------
    cursor      : Active Oracle cursor (within a committed transaction).
    server_id   : ID of the server being evaluated.
    environment : DEV | UAT | PROD — used to look up the correct threshold.
    """

    def __init__(self, cursor: oracledb.Cursor, server_id: int, environment: str, hostname: str = '') -> None:
        self._cursor = cursor
        self._server_id = server_id
        self._environment = environment
        self._hostname = hostname or ''
        self._threshold_cache: dict[str, Threshold | None] = {}

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def evaluate(
        self,
        metric_type: str,
        value: float,
        label: Optional[str] = None,
    ) -> bool:
        """
        Evaluate a single metric reading against its configured thresholds.

        Returns True  if a new alert was created.
        Returns False if no alert action was taken (OK or duplicate suppressed).
        """
        threshold = self._get_threshold(metric_type, label)
        if threshold is None:
            # No config defined — skip silently
            return False

        severity = self._classify(value, threshold)

        if severity == "OK":
            self._auto_resolve(metric_type, label)
            return False

        # Check for existing open/acknowledged alert to suppress duplicates
        if self._has_open_alert(metric_type, label):
            logger.debug(
                "Suppressed duplicate alert: server=%d metric=%s label=%s",
                self._server_id,
                metric_type,
                label,
            )
            return False

        # Create new alert
        message = (
            f"{metric_type} is {value:.1f}% on "
            f"{'[' + label + ']' if label else 'server'} "
            f"({severity} threshold: "
            f"{threshold.critical if severity == 'CRITICAL' else threshold.warning})"
        )
        self._cursor.execute(
            """
            INSERT INTO alerts
                (server_id, metric, severity, label, value, message, status)
            VALUES
                (:sid, :metric, :sev, :lbl, :val, :msg, 'OPEN')
            """,
            {
                "sid": self._server_id,
                "metric": metric_type,
                "sev": severity,
                "lbl": label,
                "val": value,
                "msg": message,
            },
        )
        logger.warning(
            "ALERT created: server=%d metric=%s severity=%s value=%.1f label=%s",
            self._server_id,
            metric_type,
            severity,
            value,
            label,
        )
        return True

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _get_threshold(self, metric_type: str, label: Optional[str] = None) -> Optional[Threshold]:
        """
        Look up the most-specific threshold for this metric + value label.

        Priority (highest wins):
          1. hostname + path_label  — per-server, per-path
          2. hostname only          — per-server, any path
          3. environment global     — any server, any path
        """
        lbl = label or ''
        hn  = self._hostname
        cache_key = f"{metric_type}:{hn}:{lbl}"
        if cache_key not in self._threshold_cache:
            self._cursor.execute(
                """
                SELECT warning_threshold, critical_threshold
                FROM   config
                WHERE  metric_type = :mt
                  AND  environment  = :env
                  AND  hostname    IN (:hn, '')
                  AND  path_label  IN (:lbl, '')
                ORDER BY
                    CASE WHEN hostname   = :hn  AND hostname   <> '' THEN 0 ELSE 1 END +
                    CASE WHEN path_label = :lbl AND path_label <> '' THEN 0 ELSE 1 END
                FETCH FIRST 1 ROWS ONLY
                """,
                {"mt": metric_type, "env": self._environment, "hn": hn, "lbl": lbl},
            )
            row = self._cursor.fetchone()
            self._threshold_cache[cache_key] = (
                Threshold(warning=float(row[0]), critical=float(row[1])) if row else None
            )
        return self._threshold_cache[cache_key]

    def _classify(self, value: float, threshold: Threshold) -> str:
        """Return 'OK', 'WARNING', or 'CRITICAL'."""
        if value >= threshold.critical:
            return "CRITICAL"
        if value >= threshold.warning:
            return "WARNING"
        return "OK"

    def _has_open_alert(self, metric_type: str, label: Optional[str]) -> bool:
        """Check whether an open / acknowledged alert already exists."""
        self._cursor.execute(
            """
            SELECT COUNT(*)
            FROM   alerts
            WHERE  server_id = :sid
              AND  metric    = :metric
              AND  (label    = :lbl OR (:lbl IS NULL AND label IS NULL))
              AND  status   IN ('OPEN', 'ACKNOWLEDGED')
            """,
            {"sid": self._server_id, "metric": metric_type, "lbl": label},
        )
        count = self._cursor.fetchone()[0]
        return count > 0

    def _auto_resolve(self, metric_type: str, label: Optional[str]) -> None:
        """Resolve any open alerts for this metric now that the value is OK."""
        from datetime import datetime  # local import avoids circular deps

        self._cursor.execute(
            """
            UPDATE alerts
            SET    status      = 'RESOLVED',
                   resolved_at = :now
            WHERE  server_id = :sid
              AND  metric    = :metric
              AND  (label    = :lbl OR (:lbl IS NULL AND label IS NULL))
              AND  status   IN ('OPEN', 'ACKNOWLEDGED')
            """,
            {
                "now": datetime.utcnow(),
                "sid": self._server_id,
                "metric": metric_type,
                "lbl": label,
            },
        )
        if self._cursor.rowcount:
            logger.info(
                "Auto-resolved %d alert(s): server=%d metric=%s label=%s",
                self._cursor.rowcount,
                self._server_id,
                metric_type,
                label,
            )
