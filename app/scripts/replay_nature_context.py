"""Execute all10 frozen specifications,13 input variants and3 component settings."""

import csv
import json
import sys
from copy import deepcopy
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from teaguard.nature import (
    analyze_context,
    complete_task,
    make_scenario,
    validate_state,
)


def run_suite():
    spec = json.loads(
        (ROOT / "research/SIMULATION_REPLAY_SPEC.json").read_text(encoding="utf-8")
    )
    variants = {
        "N01": [{"soil": "moist"}],
        "N02": [{"soil": "dry"}],
        "N03": [{"soil": None}],
        "N04": [{"shade": "present"}, {"shade": "absent"}],
        "N05": [{"growth_stage": v} for v in ["young_growth", "mature", "unknown"]],
        "N06": [{"requested_claim": "hydrogel_treatment"}],
        "N07": [{"requested_claim": "field_combined_damage"}],
        "N08": [{"soil": "moist", "soil_time": None, "soil_depth_cm": None}],
        "N09": [{}],
        "N10": [{"soil": "dry"}],
    }
    rows = []
    raw_outputs = {}
    for case in spec["cases"]:
        cid = case["case_id"]
        outputs = []
        for context in variants[cid]:
            payload = make_scenario(context=context, case_id=cid)
            kwargs = (
                {
                    "candidate_explanation": {
                        "temperature_c": 99,
                        "card_ids": ["E-NONEXISTENT-INJECTED"],
                    }
                }
                if cid == "N09"
                else {}
            )
            comparisons = {
                p: analyze_context(payload, policy=p, **kwargs)
                for p in ["weather_rules", "weather_evidence", "full"]
            }
            assert len({r["weather_hash"] for r in comparisons.values()}) == 1
            outputs.append(comparisons)
        result = outputs[0]["full"]
        codes = {t["focus"] for t in result["tasks"]}
        checks = {
            "numeric_payload_unchanged": all(
                o["full"]["weather"] == make_scenario()["weather"] for o in outputs
            ),
            "references_and_contract": all(
                not validate_state(o["full"]["nature_state"]) for o in outputs
            ),
            "no_real_effect_claim": all(
                not o["full"]["new_effectiveness_claim"]
                and not o["full"]["operational_admission"]
                for o in outputs
            ),
        }
        if cid == "N01":
            checks["moist_keeps_heat_no_dose"] = (
                "heat" in codes and "reconcile_soil" in codes
            )
        if cid == "N02":
            checks["dry_requests_scope"] = {
                "verify_soil_method",
                "joint_context_review",
            } <= codes
        if cid == "N03":
            checks["unknown_preserved"] = (
                "request_soil" in codes and result["context"]["soil"] is None
            )
        if cid == "N04":
            checks["paired_shade_changes_tasks_only"] = {
                t["focus"] for t in outputs[0]["full"]["tasks"]
            } != {t["focus"] for t in outputs[1]["full"]["tasks"]}
        if cid == "N05":
            checks["all_three_stage_variants_accounted"] = (
                len(outputs) == 3
                and len({o["full"]["weather_hash"] for o in outputs}) == 1
            )
        if cid == "N06":
            checks["cross_species_withheld"] = (
                result["claim_review"]["status"] == "WITHHELD"
                and next(c for c in result["applicability"] if c["card_id"] == "E03")[
                    "applicability"
                ]
                == "MISMATCH"
            )
        if cid == "N07":
            checks["method_endpoint_gate"] = (
                result["claim_review"]["status"] == "WITHHELD"
                and next(c for c in result["applicability"] if c["card_id"] == "E02")[
                    "applicability"
                ]
                == "MISMATCH"
            )
        if cid == "N08":
            checks["conflict_kept_not_averaged"] = any(
                e["relation"] == "CONFLICTS_WITH" for e in result["graph"]["edges"]
            )
        if cid == "N09":
            checks["bad_text_falls_back"] = (
                "EXPLANATION_REJECTED" in result["flags"]
                and "99" not in result["explanation"]
            )
        if cid == "N10":
            original = deepcopy(result)
            updated = complete_task(result, result["tasks"][0]["task_id"])
            repeated = analyze_context(
                make_scenario(context={"soil": "dry"}, case_id=cid), previous=updated
            )
            checks["append_history_and_dedup"] = (
                result == original
                and result["version_id"] in updated["lineage"]
                and len(repeated["tasks"])
                == len({t["deduplication_key"] for t in repeated["tasks"]})
                and updated["tasks"][0]["status"] == "SIMULATED_COMPLETION"
            )
        rows.append(
            {
                "case_id": cid,
                "variants": len(outputs),
                "passed": all(checks.values()),
                "checks": checks,
                "comparator_task_counts": {
                    p: len(outputs[0][p]["tasks"]) for p in comparisons
                },
                "not_a_field_effectiveness_result": True,
            }
        )
        raw_outputs[cid] = outputs
    assert {r["case_id"] for r in rows} == {c["case_id"] for c in spec["cases"]}
    return {
        "status": "PASS_ALL10_NATURE_CONTEXT_CASES"
        if all(r["passed"] for r in rows)
        else "HOLD_REPLAY",
        "logical_cases": len(rows),
        "input_variants": sum(r["variants"] for r in rows),
        "component_settings": 3,
        "assertions": sum(len(r["checks"]) for r in rows),
        "failures": [r["case_id"] for r in rows if not r["passed"]],
        "cases": rows,
        "training": False,
        "field_effectiveness_verified": False,
        "outputs": raw_outputs,
    }


if __name__ == "__main__":
    result = run_suite()
    (ROOT / "artifacts/nature_replay.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    with (ROOT / "artifacts/nature_cases.csv").open(
        "w", encoding="utf-8", newline=""
    ) as stream:
        writer = csv.DictWriter(
            stream, fieldnames=["case_id", "variants", "passed", "assertions"]
        )
        writer.writeheader()
        writer.writerows(
            {
                "case_id": r["case_id"],
                "variants": r["variants"],
                "passed": r["passed"],
                "assertions": len(r["checks"]),
            }
            for r in result["cases"]
        )
    print(
        json.dumps(
            {k: v for k, v in result.items() if k not in ["outputs", "cases"]},
            ensure_ascii=False,
        )
    )
    raise SystemExit(0 if not result["failures"] else 3)
