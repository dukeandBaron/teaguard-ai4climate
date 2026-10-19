"""Run bounded local acceptance with immutable inputs checked around every stage."""

import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def snapshot():
    selected = [
        ROOT / "nature_server.py",
        ROOT / "BUILD_BINDING.json",
        ROOT / "PARENT_V2_BINDING.json",
        ROOT / "package.json",
    ]
    for name in (
        "teaguard",
        "scripts",
        "tests",
        "fixtures",
        "references",
        "research",
        "web",
        "docs",
        "data",
        "submission",
        "reference_baseline",
    ):
        for path in (ROOT / name).rglob("*"):
            if path.is_file() and not any(
                part in ("__pycache__", ".ruff_cache", "local_records")
                for part in path.relative_to(ROOT).parts
            ):
                selected.append(path)
    selected.extend(ROOT.glob("*.md"))
    selected.extend(ROOT.glob("*.cmd"))
    selected.extend(ROOT.glob("requirements*.txt"))
    for name in ("evaluation.json", "test_predictions.json"):
        selected.append(ROOT / "artifacts" / name)
    return {p.relative_to(ROOT).as_posix(): digest(p) for p in sorted(set(selected))}


def verify():
    start = snapshot()
    binding = json.loads((ROOT / "BUILD_BINDING.json").read_text(encoding="utf-8"))
    old_root = Path(binding["frozen_v1_root"])
    old_expected = binding["frozen_v1_expected"]
    parent = json.loads((ROOT / "PARENT_V2_BINDING.json").read_text(encoding="utf-8"))
    parent_root = Path(parent["parent_root"])
    stages = []
    failures = []
    artifacts = ROOT / "artifacts"
    log_dir = artifacts / "acceptance_logs"
    log_dir.mkdir(exist_ok=True)

    def guard():
        current = snapshot()
        changed = sorted(
            k for k in set(start) | set(current) if start.get(k) != current.get(k)
        )
        old_changed = [
            k
            for k, expected in old_expected.items()
            if not (old_root / k).is_file() or digest(old_root / k) != expected
        ]
        return {
            "v2_changed": changed,
            "frozen_v1_changed": old_changed,
            "parent_v2_changed": [
                k
                for k, v in parent["source_manifest"].items()
                if digest(parent_root / k) != v
            ],
            "passed": not changed
            and not old_changed
            and all(
                digest(parent_root / k) == v
                for k, v in parent["source_manifest"].items()
            ),
        }

    def run(name, command):
        before = guard()
        if not before["passed"]:
            failures.append(name + ":pre_stage_hash_guard")
            return
        env = {**os.environ, "PYTHONDONTWRITEBYTECODE": "1", "PYTHONUTF8": "1"}
        result = subprocess.run(
            command,
            cwd=ROOT,
            env=env,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=120,
            check=False,
            shell=False,
        )
        output = result.stdout + result.stderr
        (log_dir / (name + ".txt")).write_text(output, encoding="utf-8")
        after = guard()
        record = {
            "stage": name,
            "exit_code": result.returncode,
            "before": before,
            "after": after,
            "log": f"artifacts/acceptance_logs/{name}.txt",
        }
        if name == "unittest":
            match = re.search(r"Ran (\d+) tests", output)
            record["tests_run"] = int(match.group(1)) if match else None
        stages.append(record)
        if result.returncode or not after["passed"]:
            failures.append(name)
        print(
            json.dumps(
                {
                    "stage": name,
                    "exit_code": result.returncode,
                    "hashes_unchanged": after["passed"],
                }
            ),
            flush=True,
        )

    ruff = shutil.which("ruff") or str(Path.home() / ".local/bin/ruff.exe")
    run(
        "unittest",
        [sys.executable, "-B", "-m", "unittest", "discover", "-s", "tests", "-v"],
    )
    run(
        "ruff_check",
        [ruff, "check", "nature_server.py", "teaguard", "scripts", "tests"],
    )
    run(
        "ruff_format",
        [ruff, "format", "--check", "nature_server.py", "teaguard", "scripts", "tests"],
    )
    for js_file in sorted((ROOT / "web").glob("*.js")):
        run(
            "javascript_" + js_file.stem,
            [shutil.which("node") or "node", "--check", str(js_file)],
        )
    run(
        "frontend_contracts",
        [shutil.which("node") or "node", "--test", "tests/frontend_contracts.test.mjs"],
    )
    run("doctor", [sys.executable, "-B", "scripts/doctor_local.py"])
    run("nature_replay", [sys.executable, "-B", "scripts/replay_nature_context.py"])
    run("data_audit", [sys.executable, "-B", "scripts/audit_data_coverage.py"])
    syntax = []
    for name in start:
        if name.endswith(".py"):
            compile((ROOT / name).read_text(encoding="utf-8"), name, "exec")
            syntax.append(name)
    from teaguard.nature import ENGINE_DIGEST

    with urllib.request.urlopen(
        "http://127.0.0.1:50115/api/health", timeout=5
    ) as response:
        health = json.load(response)
    server_matches = (
        health.get("engine_sha256") == ENGINE_DIGEST
        and all(start.get(k) == v for k, v in health.get("startup_sources", {}).items())
        and len(health.get("startup_sources", {})) >= 25
    )
    if not server_matches:
        failures.append("live_server_source_mismatch")
    browser_path = artifacts / "BROWSER_ACCEPTANCE.json"
    browser = (
        json.loads(browser_path.read_text(encoding="utf-8"))
        if browser_path.is_file()
        else {}
    )
    browser_matches = (
        browser.get("status") == "PASS"
        and browser.get("health") == health
        and bool(browser.get("checks"))
        and all(c.get("passed") for c in browser.get("checks", []))
        and not browser.get("page_errors")
    )
    if not browser_matches:
        failures.append("browser_acceptance_missing_or_stale")
    final_guard = guard()
    if not final_guard["passed"]:
        failures.append("final_hash_guard")
    result = {
        "status": "PASS_LOCAL_V3_ENGINEERING_ACCEPTANCE" if not failures else "HOLD",
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "source_manifest": start,
        "engine_sha256": ENGINE_DIGEST,
        "frozen_v1_files_checked": len(old_expected),
        "parent_v2_files_checked": len(parent["source_manifest"]),
        "stage_checks": stages,
        "syntax_files_checked": len(syntax),
        "live_server_matches": server_matches,
        "browser_receipt_matches": browser_matches,
        "final_guard": final_guard,
        "failures": failures,
        "training": False,
        "paid_api_calls": False,
        "field_effectiveness_verified": False,
        "official_submission": False,
    }
    (artifacts / "ENGINEERING_ACCEPTANCE.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(
        json.dumps(
            {
                k: v
                for k, v in result.items()
                if k not in ("source_manifest", "stage_checks")
            },
            ensure_ascii=False,
        )
    )
    return 0 if not failures else 3


if __name__ == "__main__":
    raise SystemExit(verify())
