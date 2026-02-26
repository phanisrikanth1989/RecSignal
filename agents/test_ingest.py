#!/usr/bin/env python3
"""
Quick connectivity + ingest test for RecSignal backend.
Run on the Unix server:
    python3 test_ingest.py
"""
import json
import sys
import urllib.request
import urllib.error
import os

API_URL = os.getenv("RECSIGNAL_API_URL", "http://localhost:8000")

def test(label, url, data=None):
    print(f"\n[TEST] {label}")
    print(f"       URL: {url}")
    try:
        if data:
            body = json.dumps(data).encode()
            req = urllib.request.Request(
                url, data=body,
                headers={"Content-Type": "application/json"},
                method="POST"
            )
        else:
            req = urllib.request.Request(url)
        with urllib.request.urlopen(req, timeout=10) as resp:
            result = resp.read().decode()
            print(f"  ✓ HTTP {resp.status}: {result}")
            return True
    except urllib.error.HTTPError as e:
        print(f"  ✗ HTTP {e.code}: {e.read().decode()}")
    except urllib.error.URLError as e:
        print(f"  ✗ Connection failed: {e.reason}")
    except Exception as e:
        print(f"  ✗ Error: {e}")
    return False

# ── 1. Health check ────────────────────────────────────────────────────────
ok = test("Health check", f"{API_URL}/health")
if not ok:
    print("\n  Backend is NOT reachable. Check uvicorn is running:")
    print("    ps aux | grep uvicorn")
    print("    uvicorn app.main:app --host 0.0.0.0 --port 8000")
    sys.exit(1)

# ── 2. Dummy metric ingest ─────────────────────────────────────────────────
payload = {
    "hostname": "test-host",
    "environment": "DEV",
    "server_type": "UNIX",
    "metrics": [
        {"metric_type": "CPU_LOAD",    "value": 55.0, "label": "LOAD_1M"},
        {"metric_type": "MEMORY_USAGE","value": 60.0, "label": "RAM"},
        {"metric_type": "DISK_USAGE",  "value": 45.0, "label": "/"},
    ]
}
test("POST /metrics/ingest (dummy data)", f"{API_URL}/metrics/ingest", payload)

print("\nDone.")
