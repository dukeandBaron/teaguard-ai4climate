"""Run the integrated candidate on explicitly synthetic local input."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from teaguard.decision_kernel import analyze_offline, load_evidence_bank


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--demo", action="store_true")
    source.add_argument("--input", type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    source_path = ROOT / "fixtures/decision_demo.json" if args.demo else args.input
    if source_path.resolve() == args.output.resolve():
        parser.error("Input and output must differ")
    try:
        raw = source_path.read_bytes()
        payload = json.loads(raw.decode("utf-8-sig"))
        if not isinstance(payload, dict):
            raise TypeError("Input must be an object")
        bank = load_evidence_bank(ROOT / "data/evidence_cards.json")
        result = analyze_offline(
            record=payload.get("record"),
            observations=payload.get("observations"),
            interval=payload.get("interval"),
            evidence_bank=bank,
            soil_simulation=payload.get("soil_simulation", "unknown"),
            semantic_hint=payload.get("semantic_hint"),
            heat_threshold_c=payload.get("heat_threshold_c", 35.0),
            balance_threshold_mm=payload.get("balance_threshold_mm", 15.0),
        )
        result["input_file_sha256"] = hashlib.sha256(raw).hexdigest()
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(
            json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False),
            encoding="utf-8",
        )
    except (OSError, TypeError, ValueError) as exc:
        print(f"Kernel input error: {exc}", file=sys.stderr)
        return 2
    print(
        json.dumps(
            {
                "state": result["state"],
                "actions": len(result["actions"]),
                "flags": result["flags"],
                "production_admission": False,
            },
            ensure_ascii=False,
        )
    )
    return 0 if result["state"] == "PASS_OFFLINE_DECISION_REPLAY" else 3


if __name__ == "__main__":
    raise SystemExit(main())
