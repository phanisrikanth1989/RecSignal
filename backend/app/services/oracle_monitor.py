"""
services/oracle_monitor.py — Oracle DB health metric collection.

Used by oracle_agent.py (run on/near the monitored Oracle instance).
Can also be imported in unit tests without a live DB by mocking the connection.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class TablespaceMetric:
    name: str
    total_mb: float
    used_mb: float
    free_mb: float
    use_percent: float


@dataclass
class BlockingSession:
    blocking_sid: int
    blocking_serial: int
    blocked_count: int
    blocking_user: Optional[str]
    blocking_program: Optional[str]
    wait_event: Optional[str]


@dataclass
class LongRunningQuery:
    sid: int
    serial: int
    username: Optional[str]
    sql_id: Optional[str]
    elapsed_minutes: float
    status: str
    program: Optional[str]


@dataclass
class OracleMetrics:
    tablespaces: list[TablespaceMetric] = field(default_factory=list)
    blocking_sessions: list[BlockingSession] = field(default_factory=list)
    long_running_queries: list[LongRunningQuery] = field(default_factory=list)


# ---------------------------------------------------------------------------
# SQL constants
# ---------------------------------------------------------------------------

_SQL_TABLESPACE = """
SELECT
    df.tablespace_name,
    df.total_mb,
    NVL(df.total_mb - fs.free_mb, df.total_mb) AS used_mb,
    NVL(fs.free_mb, 0)                          AS free_mb,
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
SELECT
    b.sid        AS blocking_sid,
    b.serial#    AS blocking_serial,
    COUNT(w.sid) AS blocked_count,
    b.username   AS blocking_user,
    b.program    AS blocking_program,
    b.event      AS wait_event
FROM
    v$session w
    JOIN v$session b ON b.sid = w.blocking_session
GROUP BY b.sid, b.serial#, b.username, b.program, b.event
ORDER BY blocked_count DESC
"""

_SQL_LONG_RUNNING = """
SELECT
    s.sid,
    s.serial#,
    s.username,
    s.sql_id,
    ROUND(q.elapsed_time / 60000000, 2) AS elapsed_minutes,
    s.status,
    s.program
FROM
    v$session s
    JOIN v$sql q ON q.sql_id = s.sql_id
WHERE
    s.status   = 'ACTIVE'
    AND s.type != 'BACKGROUND'
    AND q.elapsed_time > 300000000   -- > 5 minutes (microseconds)
ORDER BY elapsed_minutes DESC
"""


# ---------------------------------------------------------------------------
# Collector class
# ---------------------------------------------------------------------------

class OracleMonitor:
    """
    Collects health metrics from a target Oracle database.

    Parameters
    ----------
    connection : An active ``oracledb.Connection`` to the target database.
    """

    def __init__(self, connection) -> None:
        self._con = connection

    # ------------------------------------------------------------------
    # Tablespace
    # ------------------------------------------------------------------

    def collect_tablespace_usage(self) -> list[TablespaceMetric]:
        """Query DBA_DATA_FILES / DBA_FREE_SPACE for tablespace fill rates."""
        try:
            cursor = self._con.cursor()
            cursor.execute(_SQL_TABLESPACE)
            results = []
            for row in cursor.fetchall():
                results.append(
                    TablespaceMetric(
                        name=row[0],
                        total_mb=float(row[1]),
                        used_mb=float(row[2]),
                        free_mb=float(row[3]),
                        use_percent=float(row[4]),
                    )
                )
            return results
        except Exception as exc:
            logger.error("Failed to collect tablespace usage: %s", exc)
            return []

    # ------------------------------------------------------------------
    # Blocking sessions
    # ------------------------------------------------------------------

    def collect_blocking_sessions(self) -> list[BlockingSession]:
        """
        Identify sessions that are currently blocking other sessions.
        Returns a list of :class:`BlockingSession` ordered by blocked_count desc.
        """
        try:
            cursor = self._con.cursor()
            cursor.execute(_SQL_BLOCKING)
            results = []
            for row in cursor.fetchall():
                results.append(
                    BlockingSession(
                        blocking_sid=int(row[0]),
                        blocking_serial=int(row[1]),
                        blocked_count=int(row[2]),
                        blocking_user=row[3],
                        blocking_program=row[4],
                        wait_event=row[5],
                    )
                )
            return results
        except Exception as exc:
            logger.error("Failed to collect blocking sessions: %s", exc)
            return []

    # ------------------------------------------------------------------
    # Long running queries
    # ------------------------------------------------------------------

    def collect_long_running_queries(
        self,
        min_elapsed_minutes: float = 5.0,
    ) -> list[LongRunningQuery]:
        """
        Return active queries that have been running longer than
        *min_elapsed_minutes* minutes.
        """
        try:
            cursor = self._con.cursor()
            cursor.execute(_SQL_LONG_RUNNING)
            results = []
            for row in cursor.fetchall():
                elapsed = float(row[4])
                if elapsed >= min_elapsed_minutes:
                    results.append(
                        LongRunningQuery(
                            sid=int(row[0]),
                            serial=int(row[1]),
                            username=row[2],
                            sql_id=row[3],
                            elapsed_minutes=elapsed,
                            status=row[5],
                            program=row[6],
                        )
                    )
            return results
        except Exception as exc:
            logger.error("Failed to collect long running queries: %s", exc)
            return []

    # ------------------------------------------------------------------
    # Full collection
    # ------------------------------------------------------------------

    def collect_all(self) -> OracleMetrics:
        """Collect all Oracle metrics and return as an :class:`OracleMetrics` instance."""
        return OracleMetrics(
            tablespaces=self.collect_tablespace_usage(),
            blocking_sessions=self.collect_blocking_sessions(),
            long_running_queries=self.collect_long_running_queries(),
        )
