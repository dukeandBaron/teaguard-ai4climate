"""Offline source-package checks without the developer's historical checkout paths."""

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

from verify_engineering import snapshot

ROOT = Path(__file__).resolve().parents[1]


def main():
    frozen = snapshot()
    (ROOT / "artifacts/portable_logs").mkdir(parents=True, exist_ok=True)
    node = shutil.which("node")
    if not node:
        raise SystemExit(
            "Node is required only for the frontend verification step; the app itself uses Python stdlib."
        )
    commands = [
        (
            "python_tests",
            [sys.executable, "-B", "-m", "unittest", "discover", "-s", "tests", "-v"],
        ),
        ("frontend_contracts", [node, "--test", "tests/frontend_contracts.test.mjs"]),
        ("nature_replay", [sys.executable, "-B", "scripts/replay_nature_context.py"]),
        ("coverage_audit", [sys.executable, "-B", "scripts/audit_data_coverage.py"]),
    ]
    stages = []
    for name, command in commands:
        completed = subprocess.run(
            command,
            cwd=ROOT,
            env={**os.environ, "PYTHONUTF8": "1", "PYTHONDONTWRITEBYTECODE": "1"},
            text=True,
            encoding="utf-8",
            errors="replace",
            capture_output=True,
            check=False,
            timeout=120,
        )
        (ROOT / "artifacts/portable_logs" / (name + ".txt")).write_text(
            completed.stdout + completed.stderr, encoding="utf-8"
        )
        stages.append(
            {
                "name": name,
                "exit_code": completed.returncode,
                "fixed_inputs_unchanged": snapshot() == frozen,
            }
        )
    passed = all(
        stage["exit_code"] == 0 and stage["fixed_inputs_unchanged"] for stage in stages
    )
    report = {
        "status": "PASS_PORTABLE_OFFLINE_CHECKS" if passed else "HOLD",
        "stages": stages,
        "source_manifest": frozen,
        "historical_checkout_verification": "NOT_REQUIRING_DEVELOPER_ABSOLUTE_PATHS",
        "real_browser_included": False,
        "training": False,
    }
    (ROOT / "artifacts/PORTABLE_ACCEPTANCE.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(
        json.dumps(
            {k: v for k, v in report.items() if k != "source_manifest"},
            ensure_ascii=False,
        )
    )
    return 0 if passed else 3


if __name__ == "__main__":
    raise SystemExit(main())
