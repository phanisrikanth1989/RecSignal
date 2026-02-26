"""
models.py — Pydantic schemas + Oracle DDL for RecSignal.

Sections
--------
1. Pydantic request / response models used by FastAPI routes.
2. DDL strings used to bootstrap the schema in Oracle.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Enumerations
# ---------------------------------------------------------------------------

class Environment(str, Enum):
    DEV = "DEV"
    UAT = "UAT"
    PROD = "PROD"


class ServerType(str, Enum):
    UNIX = "UNIX"
    ORACLE = "ORACLE"


class MetricType(str, Enum):
    # Unix
    DISK_USAGE = "DISK_USAGE"
    INODE_USAGE = "INODE_USAGE"
    MEMORY_USAGE = "MEMORY_USAGE"
    CPU_LOAD = "CPU_LOAD"
    # Oracle
    TABLESPACE_USAGE = "TABLESPACE_USAGE"
    BLOCKING_SESSIONS = "BLOCKING_SESSIONS"
    LONG_RUNNING_QUERIES = "LONG_RUNNING_QUERIES"


class Severity(str, Enum):
    OK = "OK"
    WARNING = "WARNING"
    CRITICAL = "CRITICAL"


class AlertStatus(str, Enum):
    OPEN = "OPEN"
    ACKNOWLEDGED = "ACKNOWLEDGED"
    RESOLVED = "RESOLVED"


# ---------------------------------------------------------------------------
# Server
# ---------------------------------------------------------------------------

class ServerBase(BaseModel):
    hostname: str = Field(..., max_length=255)
    environment: Environment
    type: ServerType
    active: bool = True


class ServerCreate(ServerBase):
    pass


class ServerResponse(ServerBase):
    id: int

    class Config:
        from_attributes = True


# ---------------------------------------------------------------------------
# Metrics
# ---------------------------------------------------------------------------

class MetricBase(BaseModel):
    server_id: int
    metric_type: MetricType
    value: float = Field(..., description="Numeric metric value (e.g. percentage)")
    label: Optional[str] = Field(None, max_length=255, description="Mount point, tablespace name, etc.")
    timestamp: Optional[datetime] = None


class MetricCreate(MetricBase):
    pass


class MetricResponse(MetricBase):
    id: int
    timestamp: datetime

    class Config:
        from_attributes = True


# ---------------------------------------------------------------------------
# Bulk metric ingestion (agent payload)
# ---------------------------------------------------------------------------

class MetricPayload(BaseModel):
    """
    Payload sent by Unix / Oracle agents.
    Contains server identification plus a list of metrics collected.
    """
    hostname: str
    environment: Environment
    server_type: ServerType
    metrics: list[MetricCreate]


# ---------------------------------------------------------------------------
# Alerts
# ---------------------------------------------------------------------------

class AlertBase(BaseModel):
    server_id: int
    metric: MetricType
    severity: Severity
    label: Optional[str] = None
    value: float
    message: Optional[str] = None


class AlertCreate(AlertBase):
    pass


class AlertResponse(AlertBase):
    id: int
    status: AlertStatus
    created_at: datetime
    resolved_at: Optional[datetime] = None
    acknowledged_by: Optional[str] = None

    class Config:
        from_attributes = True


class AlertAcknowledge(BaseModel):
    alert_id: int
    acknowledged_by: str = Field(..., max_length=100)


# ---------------------------------------------------------------------------
# Config (threshold management)
# ---------------------------------------------------------------------------

class ThresholdConfig(BaseModel):
    metric_type: MetricType
    environment: Environment
    hostname: str = Field(
        '',
        max_length=255,
        description="Specific server hostname; leave empty to apply to all servers in this environment",
    )
    path_label: str = Field(
        '',
        max_length=255,
        description="Specific mount point / tablespace / label; leave empty to apply to all paths",
    )
    warning_threshold: float = Field(..., ge=0)
    critical_threshold: float = Field(..., ge=0)


class ThresholdConfigResponse(ThresholdConfig):
    id: int

    class Config:
        from_attributes = True


# ---------------------------------------------------------------------------
# Dashboard composite response
# ---------------------------------------------------------------------------

class DashboardStats(BaseModel):
    total_servers: int
    active_alerts: int
    critical_alerts: int
    warning_alerts: int
    servers_by_env: dict[str, int]
    recent_alerts: list[AlertResponse]


# ---------------------------------------------------------------------------
# Oracle DDL — run once to bootstrap the schema
# ---------------------------------------------------------------------------

DDL_STATEMENTS = [
    # servers
    """
    CREATE TABLE servers (
        id          NUMBER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
        hostname    VARCHAR2(255) NOT NULL,
        environment VARCHAR2(10)  NOT NULL CHECK (environment IN ('DEV','UAT','PROD')),
        type        VARCHAR2(10)  NOT NULL CHECK (type IN ('UNIX','ORACLE')),
        active      NUMBER(1)     DEFAULT 1 NOT NULL,
        created_at  TIMESTAMP     DEFAULT CURRENT_TIMESTAMP,
        CONSTRAINT uq_server_hostname UNIQUE (hostname)
    )
    """,
    # metrics
    """
    CREATE TABLE metrics (
        id          NUMBER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
        server_id   NUMBER        NOT NULL REFERENCES servers(id),
        metric_type VARCHAR2(50)  NOT NULL,
        value       NUMBER(10,4)  NOT NULL,
        label       VARCHAR2(255),
        timestamp   TIMESTAMP     DEFAULT CURRENT_TIMESTAMP
    )
    """,
    # index for fast metric history queries
    "CREATE INDEX idx_metrics_server_ts ON metrics(server_id, timestamp DESC)",
    # alerts
    """
    CREATE TABLE alerts (
        id              NUMBER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
        server_id       NUMBER       NOT NULL REFERENCES servers(id),
        metric          VARCHAR2(50) NOT NULL,
        severity        VARCHAR2(10) NOT NULL CHECK (severity IN ('WARNING','CRITICAL')),
        label           VARCHAR2(255),
        value           NUMBER(10,4),
        message         VARCHAR2(1000),
        status          VARCHAR2(20) DEFAULT 'OPEN' NOT NULL
                            CHECK (status IN ('OPEN','ACKNOWLEDGED','RESOLVED')),
        acknowledged_by VARCHAR2(100),
        created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        resolved_at     TIMESTAMP
    )
    """,
    # config / thresholds
    """
    CREATE TABLE config (
        id                  NUMBER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
        metric_type         VARCHAR2(50)  NOT NULL,
        environment         VARCHAR2(10)  NOT NULL CHECK (environment IN ('DEV','UAT','PROD')),
        hostname            VARCHAR2(255) DEFAULT '' NOT NULL,
        path_label          VARCHAR2(255) DEFAULT '' NOT NULL,
        warning_threshold   NUMBER(6,2)   NOT NULL,
        critical_threshold  NUMBER(6,2)   NOT NULL,
        CONSTRAINT uq_config_path UNIQUE (metric_type, environment, hostname, path_label)
    )
    """,
    # ── Migration: add hostname / path_label to existing config tables ──────
    # ORA-01430 (column already exists) and ORA-02443 (constraint not found)
    # are silently ignored by _bootstrap_schema so these are safe to re-run.
    "ALTER TABLE config ADD (hostname VARCHAR2(255) DEFAULT '' NOT NULL)",
    "ALTER TABLE config ADD (path_label VARCHAR2(255) DEFAULT '' NOT NULL)",
    "ALTER TABLE config DROP CONSTRAINT uq_config_metric_env",
    "ALTER TABLE config ADD CONSTRAINT uq_config_path UNIQUE (metric_type, environment, hostname, path_label)",
    # seed sensible defaults
    """
    INSERT INTO config (metric_type, environment, warning_threshold, critical_threshold)
    SELECT * FROM (
        SELECT 'DISK_USAGE',            'DEV',  70, 90 FROM DUAL UNION ALL
        SELECT 'DISK_USAGE',            'UAT',  70, 85 FROM DUAL UNION ALL
        SELECT 'DISK_USAGE',            'PROD', 75, 90 FROM DUAL UNION ALL
        SELECT 'INODE_USAGE',           'DEV',  70, 90 FROM DUAL UNION ALL
        SELECT 'INODE_USAGE',           'UAT',  70, 85 FROM DUAL UNION ALL
        SELECT 'INODE_USAGE',           'PROD', 75, 90 FROM DUAL UNION ALL
        SELECT 'MEMORY_USAGE',          'DEV',  75, 90 FROM DUAL UNION ALL
        SELECT 'MEMORY_USAGE',          'UAT',  75, 90 FROM DUAL UNION ALL
        SELECT 'MEMORY_USAGE',          'PROD', 80, 95 FROM DUAL UNION ALL
        SELECT 'CPU_LOAD',              'DEV',  70, 90 FROM DUAL UNION ALL
        SELECT 'CPU_LOAD',              'UAT',  70, 90 FROM DUAL UNION ALL
        SELECT 'CPU_LOAD',              'PROD', 75, 95 FROM DUAL UNION ALL
        SELECT 'TABLESPACE_USAGE',      'DEV',  75, 90 FROM DUAL UNION ALL
        SELECT 'TABLESPACE_USAGE',      'UAT',  75, 90 FROM DUAL UNION ALL
        SELECT 'TABLESPACE_USAGE',      'PROD', 80, 95 FROM DUAL UNION ALL
        SELECT 'BLOCKING_SESSIONS',     'DEV',   5, 20 FROM DUAL UNION ALL
        SELECT 'BLOCKING_SESSIONS',     'UAT',   5, 20 FROM DUAL UNION ALL
        SELECT 'BLOCKING_SESSIONS',     'PROD',  2, 10 FROM DUAL UNION ALL
        SELECT 'LONG_RUNNING_QUERIES',  'DEV',  30, 120 FROM DUAL UNION ALL
        SELECT 'LONG_RUNNING_QUERIES',  'UAT',  30, 120 FROM DUAL UNION ALL
        SELECT 'LONG_RUNNING_QUERIES',  'PROD', 15,  60 FROM DUAL
    )
    """,
]
