"""Read-only local diagnostics; never start, repair, migrate or install anything."""

import json
import sqlite3
import sys
import urllib.request
from contextlib import closing
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from teaguard.weather_repository import WeatherRepository


def main():
    failures = []
    WeatherRepository()
    database = ROOT / "runtime/records.sqlite3"
    database_status = "NOT_CREATED"
    if database.is_file():
        with closing(
            sqlite3.connect(database.as_uri() + "?mode=ro", uri=True)
        ) as connection:
            database_status = connection.execute("PRAGMA quick_check").fetchone()[0]
        if database_status != "ok":
            failures.append("database_quick_check")
    try:
        with urllib.request.urlopen(
            "http://127.0.0.1:50115/api/health", timeout=3
        ) as response:
            health = json.load(response)
        if health.get("version") != "0.3.1":
            failures.append("unexpected_service_version")
    except (OSError, ValueError):
        failures.append("local_service_unavailable")
    result = {
        "status": "PASS_READ_ONLY_DIAGNOSTICS" if not failures else "HOLD",
        "frozen_weather_inputs": "HASH_VERIFIED",
        "database_quick_check": database_status,
        "failures": failures,
        "repairs_attempted": False,
    }
    print(json.dumps(result, ensure_ascii=False))
    return 0 if not failures else 3


if __name__ == "__main__":
    raise SystemExit(main())
