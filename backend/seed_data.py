#!/usr/bin/env python3
"""
seed_data.py — Populate RecSignal SQLite dev database with realistic mock data.

Run from the backend/ directory:
    python seed_data.py

Creates:
  - 9 servers  (3 Unix + 3 Oracle, spread across DEV / UAT / PROD)
  - 72 h of historical metrics  (every 15 min per server/metric)
  - Mix of OK, WARNING and CRITICAL alerts
"""

import os
import random
import sqlite3
import sys
from datetime import datetime, timedelta
from pathlib import Path

# ── locate the DB ────────────────────────────────────────────────────────────
SQLITE_PATH = os.getenv("SQLITE_PATH", "recsignal_dev.db")

if not Path(SQLITE_PATH).exists():
    print(f"[ERROR] {SQLITE_PATH} not found. Start the backend once first so the schema is created.")
    sys.exit(1)

random.seed(42)          # reproducible

# ── connect ──────────────────────────────────────────────────────────────────
con = sqlite3.connect(SQLITE_PATH)
con.row_factory = sqlite3.Row
con.execute("PRAGMA foreign_keys = ON")
cur = con.cursor()

# ── wipe existing mock data ───────────────────────────────────────────────────
cur.execute("DELETE FROM alerts")
cur.execute("DELETE FROM metrics")
cur.execute("DELETE FROM servers")
con.commit()
print("Cleared existing server / metric / alert rows.")

# ── SERVERS ───────────────────────────────────────────────────────────────────
SERVERS = [
    # hostname,                env,    type
    ("dev-unix-01.internal",   "DEV",  "UNIX"),
    ("dev-ora-01.internal",    "DEV",  "ORACLE"),
    ("uat-unix-01.internal",   "UAT",  "UNIX"),
    ("uat-unix-02.internal",   "UAT",  "UNIX"),
    ("uat-ora-01.internal",    "UAT",  "ORACLE"),
    ("prod-unix-01.internal",  "PROD", "UNIX"),
    ("prod-unix-02.internal",  "PROD", "UNIX"),
    ("prod-ora-01.internal",   "PROD", "ORACLE"),
    ("prod-ora-02.internal",   "PROD", "ORACLE"),
]

server_ids: dict[str, int] = {}
for hostname, env, stype in SERVERS:
    cur.execute(
        "INSERT INTO servers (hostname, environment, type, active) VALUES (?,?,?,1)",
        (hostname, env, stype),
    )
    server_ids[hostname] = cur.lastrowid
    print(f"  Server: {hostname} [{env}/{stype}] id={cur.lastrowid}")

con.commit()

# ── METRIC PROFILES ───────────────────────────────────────────────────────────
# Each entry: (metric_type, label, base_value, noise, trend_per_hour)
# trend_per_hour > 0 means the metric slowly rises over the 72 h window.

UNIX_PROFILES = [
    ("DISK_USAGE",   "/",         55.0, 2.0,  0.10),
    ("DISK_USAGE",   "/var",      40.0, 3.0,  0.05),
    ("DISK_USAGE",   "/opt",      30.0, 1.5,  0.02),
    ("INODE_USAGE",  "/",         25.0, 1.0,  0.01),
    ("MEMORY_USAGE", "RAM",       60.0, 5.0,  0.08),
    ("MEMORY_USAGE", "SWAP",       5.0, 2.0,  0.02),
    ("CPU_LOAD",     "LOAD_1M",   35.0, 8.0,  0.05),
]

ORACLE_PROFILES = [
    ("TABLESPACE_USAGE", "SYSTEM",   45.0, 1.0, 0.02),
    ("TABLESPACE_USAGE", "SYSAUX",   38.0, 1.0, 0.03),
    ("TABLESPACE_USAGE", "USERS",    60.0, 4.0, 0.15),
    ("TABLESPACE_USAGE", "UNDOTBS1", 22.0, 2.0, 0.05),
    ("BLOCKING_SESSIONS",  "TOTAL",   0.0, 0.5, 0.0),
    ("LONG_RUNNING_QUERIES","TOTAL",  0.0, 0.3, 0.0),
]

# Specific overrides to ensure some servers breach thresholds
OVERRIDES: dict[str, dict[tuple, float]] = {
    # server hostname  →  {(metric_type, label): final_value}
    "prod-unix-01.internal": {
        ("DISK_USAGE",  "/var"):     88.0,   # CRITICAL
        ("MEMORY_USAGE","RAM"):      82.0,   # WARNING
    },
    "prod-unix-02.internal": {
        ("CPU_LOAD",    "LOAD_1M"):  91.0,   # CRITICAL
        ("DISK_USAGE",  "/"):        76.0,   # WARNING
    },
    "prod-ora-01.internal": {
        ("TABLESPACE_USAGE", "USERS"):  93.0,  # CRITICAL
        ("BLOCKING_SESSIONS", "TOTAL"): 14.0,  # WARNING
    },
    "prod-ora-02.internal": {
        ("TABLESPACE_USAGE", "USERS"):  81.0,  # WARNING
        ("LONG_RUNNING_QUERIES","TOTAL"): 6.0, # WARNING
    },
    "uat-unix-01.internal": {
        ("DISK_USAGE",  "/opt"):     71.0,   # WARNING
    },
    "uat-ora-01.internal": {
        ("TABLESPACE_USAGE", "USERS"):  78.0,  # WARNING
    },
}

# ── GENERATE METRICS (72 h, every 15 min = 288 samples per series) ───────────
HOURS_BACK = 72
INTERVAL_MIN = 15
NOW = datetime.utcnow()

def _clamp(v: float) -> float:
    return max(0.0, min(100.0, v))


def _generate_series(base: float, noise: float, trend: float, n: int,
                     override_final: float | None) -> list[float]:
    """Generate n data points. If override_final is set, the last value equals it."""
    values = []
    v = base
    for i in range(n):
        v = v + trend * (INTERVAL_MIN / 60) + random.gauss(0, noise * 0.3)
        values.append(_clamp(v))
    if override_final is not None:
        # Smoothly steer the last 20 % of points toward override_final
        ramp_start = max(0, n - n // 5)
        for i in range(ramp_start, n):
            frac = (i - ramp_start) / max(1, n - 1 - ramp_start)
            values[i] = _clamp(values[ramp_start - 1] * (1 - frac) + override_final * frac)
        values[-1] = override_final
    return values


metric_rows = []
for hostname, env, stype in SERVERS:
    sid = server_ids[hostname]
    profiles = UNIX_PROFILES if stype == "UNIX" else ORACLE_PROFILES
    server_overrides = OVERRIDES.get(hostname, {})
    n = int((HOURS_BACK * 60) / INTERVAL_MIN)

    for metric_type, label, base, noise, trend in profiles:
        override_val = server_overrides.get((metric_type, label))
        series = _generate_series(base, noise, trend, n, override_val)

        for i, val in enumerate(series):
            ts = NOW - timedelta(minutes=(n - 1 - i) * INTERVAL_MIN)
            metric_rows.append((sid, metric_type, round(val, 2), label, ts))

cur.executemany(
    "INSERT INTO metrics (server_id, metric_type, value, label, timestamp) VALUES (?,?,?,?,?)",
    metric_rows,
)
con.commit()
print(f"\nInserted {len(metric_rows):,} metric rows across {len(SERVERS)} servers.")

# ── FETCH THRESHOLDS ──────────────────────────────────────────────────────────
cur.execute("SELECT metric_type, environment, warning_threshold, critical_threshold FROM config")
thresholds: dict[tuple, tuple] = {}
for row in cur.fetchall():
    thresholds[(row["metric_type"], row["environment"])] = (
        row["warning_threshold"], row["critical_threshold"]
    )

# ── GENERATE ALERTS ───────────────────────────────────────────────────────────
ALERT_SCENARIOS = [
    # (hostname,                  metric,              label,    status,         ack_by)
    ("prod-unix-01.internal",  "DISK_USAGE",          "/var",   "OPEN",         None),
    ("prod-unix-01.internal",  "MEMORY_USAGE",        "RAM",    "ACKNOWLEDGED", "ops-team"),
    ("prod-unix-02.internal",  "CPU_LOAD",            "LOAD_1M","OPEN",         None),
    ("prod-unix-02.internal",  "DISK_USAGE",          "/",      "OPEN",         None),
    ("prod-ora-01.internal",   "TABLESPACE_USAGE",   "USERS",   "OPEN",         None),
    ("prod-ora-01.internal",   "BLOCKING_SESSIONS",  "TOTAL",   "ACKNOWLEDGED", "dba-oncall"),
    ("prod-ora-02.internal",   "TABLESPACE_USAGE",   "USERS",   "OPEN",         None),
    ("prod-ora-02.internal",   "LONG_RUNNING_QUERIES","TOTAL",  "OPEN",         None),
    ("uat-unix-01.internal",   "DISK_USAGE",          "/opt",   "OPEN",         None),
    ("uat-ora-01.internal",    "TABLESPACE_USAGE",   "USERS",   "RESOLVED",     None),
    ("dev-unix-01.internal",   "CPU_LOAD",            "LOAD_1M","RESOLVED",     None),
]

alert_count = 0
for hostname, metric, label, status, ack_by in ALERT_SCENARIOS:
    sid  = server_ids[hostname]
    env  = next(e for h, e, _ in SERVERS if h == hostname)
    warn, crit = thresholds.get((metric, env), (75, 90))

    # Look up the most recent actual value for this metric/label
    cur.execute(
        "SELECT value FROM metrics WHERE server_id=? AND metric_type=? AND label=? "
        "ORDER BY timestamp DESC LIMIT 1",
        (sid, metric, label),
    )
    row = cur.fetchone()
    value = float(row["value"]) if row else crit + 1

    severity = "CRITICAL" if value >= crit else "WARNING"
    message  = (
        f"{metric.replace('_',' ')} is {value:.1f} on [{label}] "
        f"({severity} threshold: {crit if severity == 'CRITICAL' else warn})"
    )

    created_at  = NOW - timedelta(hours=random.randint(1, 12))
    resolved_at = (NOW - timedelta(minutes=random.randint(10, 60))
                   if status == "RESOLVED" else None)

    cur.execute(
        """INSERT INTO alerts
           (server_id, metric, severity, label, value, message,
            status, acknowledged_by, created_at, resolved_at)
           VALUES (?,?,?,?,?,?,?,?,?,?)""",
        (sid, metric, severity, label, round(value, 2),
         message, status, ack_by, created_at, resolved_at),
    )
    alert_count += 1
    print(f"  Alert: [{severity}] {hostname} / {metric} / {label} → {status}")

con.commit()
print(f"\nInserted {alert_count} alerts.")

con.close()
print("\n✅  Seed complete. Restart the backend and refresh the dashboard.")
