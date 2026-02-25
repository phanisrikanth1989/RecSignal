#!/usr/bin/env python3
"""
agents/unix_agent.py — RecSignal Unix Monitoring Agent.

Deploy this script on every Unix server you want to monitor.
Run via cron every 5 minutes:

    */5 * * * * /usr/bin/python3 /opt/recsignal/unix_agent.py >> /var/log/recsignal-agent.log 2>&1

Environment variables
---------------------
RECSIGNAL_API_URL   : URL of the RecSignal backend  (default: http://recsignal-backend:8000)
RECSIGNAL_ENV       : DEV | UAT | PROD               (default: DEV)
RECSIGNAL_API_KEY   : Optional bearer token
AGENT_HOSTNAME      : Override auto-detected hostname
"""

from __future__ import annotations

import logging
import os
import platform
import socket
import subprocess
import sys
from dataclasses import dataclass, field
from typing import Optional

import requests

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

API_URL = os.getenv("RECSIGNAL_API_URL", "http://recsignal-backend:8000")
ENVIRONMENT = os.getenv("RECSIGNAL_ENV", "DEV").upper()
API_KEY = os.getenv("RECSIGNAL_API_KEY", "")
HOSTNAME = os.getenv("AGENT_HOSTNAME", socket.getfqdn())
TIMEOUT_SECONDS = int(os.getenv("AGENT_TIMEOUT", "30"))

logging.basicConfig(
    stream=sys.stdout,
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | unix_agent | %(message)s",
)
logger = logging.getLogger("unix_agent")


# ---------------------------------------------------------------------------
# Metric collection helpers
# ---------------------------------------------------------------------------

def _run(cmd: list[str], timeout: int = 10) -> str:
    """Run a shell command and return stdout. Returns '' on failure."""
    try:
        return subprocess.check_output(cmd, stderr=subprocess.DEVNULL, timeout=timeout).decode()
    except Exception as exc:
        logger.warning("Command %s failed: %s", cmd, exc)
        return ""


def collect_disk_usage() -> list[dict]:
    """
    Parse ``df -Ph`` output.
    Returns list of {metric_type, value, label} dicts.
    """
    output = _run(["df", "-Ph"])
    metrics = []
    for line in output.splitlines()[1:]:
        parts = line.split()
        if len(parts) < 6:
            continue
        try:
            pct = float(parts[4].replace("%", ""))
        except ValueError:
            continue
        mount = parts[5]
        # Skip pseudo-filesystems
        if any(skip in parts[0] for skip in ["tmpfs", "devtmpfs", "udev", "none"]):
            continue
        metrics.append({"metric_type": "DISK_USAGE", "value": pct, "label": mount})
    return metrics


def collect_inode_usage() -> list[dict]:
    """Parse ``df -Pi`` for inode usage percentages."""
    output = _run(["df", "-Pi"])
    metrics = []
    for line in output.splitlines()[1:]:
        parts = line.split()
        if len(parts) < 6 or parts[4] == "-":
            continue
        try:
            pct = float(parts[4].replace("%", ""))
        except ValueError:
            continue
        mount = parts[5]
        metrics.append({"metric_type": "INODE_USAGE", "value": pct, "label": mount})
    return metrics


def collect_memory() -> list[dict]:
    """Read /proc/meminfo for RAM and swap percentages."""
    try:
        mem: dict[str, int] = {}
        with open("/proc/meminfo") as f:
            for line in f:
                k, _, v = line.partition(":")
                mem[k.strip()] = int(v.split()[0])

        total = mem.get("MemTotal", 1)
        avail = mem.get("MemAvailable", 0)
        mem_pct = round((1 - avail / total) * 100, 2)

        swap_total = mem.get("SwapTotal", 0)
        swap_free = mem.get("SwapFree", 0)
        swap_pct = round((1 - swap_free / swap_total) * 100, 2) if swap_total else 0.0

        return [
            {"metric_type": "MEMORY_USAGE", "value": mem_pct, "label": "RAM"},
            {"metric_type": "MEMORY_USAGE", "value": swap_pct, "label": "SWAP"},
        ]
    except Exception as exc:
        logger.error("Memory collection failed: %s", exc)
        return []


def collect_cpu_load() -> list[dict]:
    """Return 1-minute load average as CPU percentage."""
    try:
        with open("/proc/loadavg") as f:
            load_1m = float(f.read().split()[0])
        cpu_count = int(_run(["nproc"]).strip() or "1")
        pct = min(round((load_1m / cpu_count) * 100, 2), 100.0)
        return [{"metric_type": "CPU_LOAD", "value": pct, "label": "LOAD_1M"}]
    except Exception as exc:
        logger.error("CPU load collection failed: %s", exc)
        return []


# ---------------------------------------------------------------------------
# API submission
# ---------------------------------------------------------------------------

def build_payload(metrics: list[dict]) -> dict:
    """Wrap collected metrics into the backend ingest schema."""
    return {
        "hostname": HOSTNAME,
        "environment": ENVIRONMENT,
        "server_type": "UNIX",
        "metrics": metrics,
    }


def post_metrics(payload: dict) -> bool:
    """HTTP POST payload to /metrics/ingest. Returns True on success."""
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
            len(payload["metrics"]),
            data.get("metrics_stored", 0),
            data.get("alerts_generated", 0),
        )
        return True
    except requests.RequestException as exc:
        logger.error("Failed to post metrics to %s: %s", url, exc)
        return False


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    logger.info("=== RecSignal Unix Agent — %s [%s] ===", HOSTNAME, ENVIRONMENT)

    all_metrics: list[dict] = []
    all_metrics.extend(collect_disk_usage())
    all_metrics.extend(collect_inode_usage())
    all_metrics.extend(collect_memory())
    all_metrics.extend(collect_cpu_load())

    if not all_metrics:
        logger.warning("No metrics collected. Exiting.")
        sys.exit(1)

    logger.info("Collected %d metric readings.", len(all_metrics))
    payload = build_payload(all_metrics)
    success = post_metrics(payload)
    sys.exit(0 if success else 2)


if __name__ == "__main__":
    main()
