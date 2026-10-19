"""Reuse the local V3 server or launch it with the installed interpreter."""

import json
import subprocess
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
try:
    with urllib.request.urlopen(
        "http://127.0.0.1:50115/api/health", timeout=2
    ) as response:
        data = json.load(response)
    if data.get("version") == "0.3.1" and data.get("name") == "茶候 · 自然情境":
        print("TeaGuard V3 is already running: http://127.0.0.1:50115/")
        raise SystemExit(0)
except (OSError, ValueError):
    pass
raise SystemExit(
    subprocess.call(
        [sys.executable, "-B", str(ROOT / "nature_server.py"), "--port", "50115"],
        cwd=ROOT,
    )
)
