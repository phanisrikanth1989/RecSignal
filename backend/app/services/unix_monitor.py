"""
services/unix_monitor.py — Utility functions for parsing Unix system metrics.

These helpers are used by unix_agent.py (deployed on monitored servers).
They can also be imported here on the backend for integration tests.
"""

from __future__ import annotations

import shutil
import subprocess
from dataclasses import dataclass, field
from typing import Generator


@dataclass
class DiskMetric:
    mount_point: str
    total_gb: float
    used_gb: float
    free_gb: float
    use_percent: float
    inode_use_percent: float = 0.0


@dataclass
class SystemMetric:
    cpu_load_1m: float       # 1-minute load average (expressed as %)
    memory_use_percent: float
    swap_use_percent: float
    disks: list[DiskMetric] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Disk usage
# ---------------------------------------------------------------------------

def collect_disk_usage(exclude_fs: tuple[str, ...] = ("tmpfs", "devtmpfs", "udev")) -> list[DiskMetric]:
    """
    Run ``df -Ph`` and parse each filesystem entry.

    Excludes pseudo-filesystems listed in *exclude_fs*.
    Returns a list of :class:`DiskMetric` instances.
    """
    result = subprocess.run(
        ["df", "-Ph"], capture_output=True, text=True, timeout=15
    )
    metrics: list[DiskMetric] = []
    lines = result.stdout.strip().splitlines()

    for line in lines[1:]:           # skip header
        parts = line.split()
        if len(parts) < 6:
            continue
        fs_type_cmd = subprocess.run(
            ["stat", "-f", "-c", "%T", parts[5]], capture_output=True, text=True
        )
        fs_label = fs_type_cmd.stdout.strip() if fs_type_cmd.returncode == 0 else ""
        if any(ex in fs_label for ex in exclude_fs):
            continue

        try:
            use_pct = float(parts[4].replace("%", ""))
        except ValueError:
            continue

        def _to_gb(s: str) -> float:
            s = s.upper()
            if s.endswith("G"):
                return float(s[:-1])
            if s.endswith("M"):
                return float(s[:-1]) / 1024
            if s.endswith("T"):
                return float(s[:-1]) * 1024
            return float(s) / (1024 ** 3)  # assume bytes

        metrics.append(
            DiskMetric(
                mount_point=parts[5],
                total_gb=_to_gb(parts[1]),
                used_gb=_to_gb(parts[2]),
                free_gb=_to_gb(parts[3]),
                use_percent=use_pct,
            )
        )

    # Inode usage
    inode_result = subprocess.run(
        ["df", "-Pi"], capture_output=True, text=True, timeout=15
    )
    inode_map: dict[str, float] = {}
    for line in inode_result.stdout.strip().splitlines()[1:]:
        parts = line.split()
        if len(parts) < 6 or parts[4] == "-":
            continue
        try:
            inode_map[parts[5]] = float(parts[4].replace("%", ""))
        except ValueError:
            pass

    for dm in metrics:
        dm.inode_use_percent = inode_map.get(dm.mount_point, 0.0)

    return metrics


# ---------------------------------------------------------------------------
# CPU / Memory
# ---------------------------------------------------------------------------

def collect_cpu_load() -> float:
    """
    Return 1-minute load average as a rough CPU usage percentage.
    Divides raw load average by number of logical CPUs.
    """
    with open("/proc/loadavg") as f:
        load_1m = float(f.read().split()[0])

    cpu_count = len([
        ln for ln in open("/proc/cpuinfo").readlines()
        if ln.startswith("processor")
    ]) or 1

    return min(round((load_1m / cpu_count) * 100, 2), 100.0)


def collect_memory_usage() -> tuple[float, float]:
    """
    Returns (memory_use_percent, swap_use_percent) from /proc/meminfo.
    """
    mem_info: dict[str, int] = {}
    with open("/proc/meminfo") as f:
        for line in f:
            key, _, val = line.partition(":")
            mem_info[key.strip()] = int(val.split()[0])  # kB

    mem_total = mem_info.get("MemTotal", 1)
    mem_avail = mem_info.get("MemAvailable", 0)
    mem_pct = round((1 - mem_avail / mem_total) * 100, 2)

    swap_total = mem_info.get("SwapTotal", 0)
    swap_free = mem_info.get("SwapFree", 0)
    swap_pct = round((1 - swap_free / swap_total) * 100, 2) if swap_total else 0.0

    return mem_pct, swap_pct


# ---------------------------------------------------------------------------
# Full collection
# ---------------------------------------------------------------------------

def collect_all() -> SystemMetric:
    """
    Collect all system metrics in one call.
    Returns a :class:`SystemMetric` dataclass.
    """
    disks = collect_disk_usage()
    cpu = collect_cpu_load()
    mem, swap = collect_memory_usage()
    return SystemMetric(cpu_load_1m=cpu, memory_use_percent=mem, swap_use_percent=swap, disks=disks)
