"""Run the actual A0 audit on local JSON; no model, network or installation."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from teaguard.forecast_contract import audit_batch, validate_calibration_label


def reject_constant(value: str) -> None:
    raise ValueError(f"Nonfinite JSON constant is not accepted: {value}")


def run_payload(payload: dict) -> tuple[dict, int]:
    """Ordinary inputs require every record to qualify; fixture suites compare states."""
    if not isinstance(payload, dict):
        raise TypeError("Input must be a JSON object")
    is_suite = payload.get("kind") == "AI_AUTHORED_SYNTHETIC_CONTRACT_SUITE"
    forecasts = payload.get("forecasts", []) if is_suite else None
    if is_suite:
        if not isinstance(forecasts, list) or not all(
            isinstance(c, dict) for c in forecasts
        ):
            raise TypeError("forecasts must contain case objects")
        records = [case.get("record") for case in forecasts]
    else:
        records = payload.get("records")
    report = audit_batch(records)
    report["created_utc"] = datetime.now(timezone.utc).isoformat()
    if not is_suite:
        report["status"] = (
            "PASS_OFFLINE_INPUTS" if report["all_inputs_eligible"] else "HOLD_INPUTS"
        )
        return report, 0 if report["all_inputs_eligible"] else 3
    report["mode"] = "AI_AUTHORED_SYNTHETIC_CONTRACT_SUITE"
    matches = []
    for case, result in zip(forecasts, report["records"], strict=True):
        matches.append(
            {
                "case_id": case.get("case_id"),
                "expected": case.get("expected_state"),
                "observed": result["state"],
                "matched": result["state"] == case.get("expected_state"),
            }
        )
    labels = payload.get("calibration_cases", [])
    if not isinstance(labels, list):
        raise TypeError("calibration_cases must be a list")
    label_results = []
    for case in labels:
        if not isinstance(case, dict):
            raise TypeError("Calibration case must be an object")
        result = validate_calibration_label(case.get("record"), case.get("label"))
        label_results.append(
            {
                "case_id": case.get("case_id"),
                "expected": case.get("expected_state"),
                "matched": result["state"] == case.get("expected_state"),
                "result": result,
            }
        )
    passed = (
        report["has_nonempty_positive_control"]
        and bool(matches)
        and all(c["matched"] for c in matches)
        and all(c["matched"] for c in label_results)
    )
    report.update(
        {
            "scenario_checks": matches,
            "calibration_checks": label_results,
            "scenario_expectations_matched": passed,
            "status": "PASS_SYNTHETIC_CONTRACT_SUITE"
            if passed
            else "HOLD_SYNTHETIC_CONTRACT_SUITE",
            "boundary": "A fixture suite pass tests software behavior only; no real forecast or farm effect is established.",
        }
    )
    return report, 0 if passed else 3


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--input", type=Path)
    source.add_argument("--demo", action="store_true")
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    input_path = ROOT / "fixtures/demo_records.json" if args.demo else args.input
    if input_path.resolve() == args.output.resolve():
        parser.error("Input and output must be different files")
    try:
        raw = input_path.read_bytes()
        payload = json.loads(raw.decode("utf-8-sig"), parse_constant=reject_constant)
        report, exit_code = run_payload(payload)
        report["input_file_sha256"] = hashlib.sha256(raw).hexdigest()
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(
            json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False),
            encoding="utf-8",
        )
    except (OSError, TypeError, ValueError) as exc:
        print(f"Audit input error: {exc}", file=sys.stderr)
        return 2
    print(
        json.dumps(
            {
                "status": report["status"],
                "counts": report["counts"],
                "production_admission": False,
            },
            ensure_ascii=False,
        )
    )
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
