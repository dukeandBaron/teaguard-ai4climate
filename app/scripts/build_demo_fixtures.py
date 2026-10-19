"""Materialize the frozen, explicitly synthetic behavioral test scenarios."""

import json
import sys
from copy import deepcopy
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from tests.cases import fixture_cases, matured_label, valid_record


def main() -> None:
    positive = matured_label()
    incomplete = deepcopy(positive)
    incomplete["completed_samples"] = 48
    unreleased = deepcopy(positive)
    unreleased["checked_at"] = "2025-07-17T17:00:00Z"
    unknown = deepcopy(positive)
    unknown["available_at"] = None
    payload = {
        "kind": "AI_AUTHORED_SYNTHETIC_CONTRACT_SUITE",
        "description": "Every timestamp and value is an authored fixture. No real participants, provider receipts or farm measurements.",
        "forecasts": fixture_cases(),
        "calibration_cases": [
            {
                "case_id": name,
                "expected_state": expected,
                "record": valid_record(),
                "label": label,
            }
            for name, expected, label in [
                ("CONTROL_LABEL_MATURED", "PASS_KNOWN_AVAILABLE", positive),
                ("S09_INCOMPLETE_LABEL", "REJECT", incomplete),
                ("S09_NOT_RELEASED", "REJECT", unreleased),
                ("UNKNOWN_LABEL_RELEASE", "UNKNOWN_AVAILABILITY", unknown),
            ]
        ],
    }
    target = ROOT / "fixtures/demo_records.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    record = valid_record()
    decision = {
        "record": record,
        "observations": [
            {
                "date": day["date"],
                "tmax_c": 20.0 + i,
                "rain_mm": 0.5,
                "et0_mm": 4.0,
                "evidence_kind": "AI_AUTHORED_SYNTHETIC",
            }
            for i, day in enumerate(record["history_days"])
        ],
        "interval": {
            "lower_c": 32.5,
            "upper_c": 36.5,
            "run_id": record["run_id"],
            "target_start_utc": record["target"]["start_utc"],
            "target_end_exclusive_utc": record["target"]["end_exclusive_utc"],
            "unit": "C",
            "statistic": "MAX_OF_72_HOURLY_INSTANTS",
            "kind": "AI_AUTHORED_SYNTHETIC_INTERVAL_NOT_EMPIRICAL",
        },
        "soil_simulation": "moist",
        "semantic_hint": {"trend": "cooling", "temperature_c": 99},
    }
    (ROOT / "fixtures/decision_demo.json").write_text(
        json.dumps(decision, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print("Synthetic fixtures generated: 13 forecast cases and 4 label cases")


if __name__ == "__main__":
    main()
