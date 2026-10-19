"""Stable domain facade: compose state, applicability, rules and graph projections."""

import hashlib
import json
from copy import deepcopy
from pathlib import Path

from .evidence_catalog import EvidenceCatalog
from .graph_projection import _graph
from .inspection_policy import _tasks
from .nature_state import _context, make_scenario, validate_state
from .scope_policy import _match_cards
from .serialization import stable_hash

__all__ = [
    "analyze_context",
    "complete_task",
    "load_cards",
    "make_scenario",
    "stable_hash",
    "validate_state",
]

ROOT = Path(__file__).resolve().parents[1]
CATALOG = EvidenceCatalog(ROOT)
DOMAIN_FILES = (
    "nature.py",
    "nature_state.py",
    "scope_policy.py",
    "inspection_policy.py",
    "graph_projection.py",
    "serialization.py",
    "evidence_catalog.py",
)
DOMAIN_MANIFEST = {
    name: hashlib.sha256((ROOT / "teaguard" / name).read_bytes()).hexdigest()
    for name in DOMAIN_FILES
}
ENGINE_DIGEST = hashlib.sha256(
    json.dumps(
        {"domain": DOMAIN_MANIFEST, "evidence": CATALOG.manifest}, sort_keys=True
    ).encode()
).hexdigest()


def load_cards():
    return CATALOG.read()


def _questions(state, ctx, weather):
    questions = []
    missing = [
        key for key in ("soil_time", "soil_depth_cm", "soil_method") if ctx[key] is None
    ]
    if ctx["soil"] is not None and missing:
        questions.append(
            {
                "factor": "soil_provenance",
                "question": "土壤反馈的时间、土层深度和观察方法是什么？",
                "missing_fields": missing,
                "branch_task_changes": 0,
                "priority": "PROVENANCE_FIRST",
                "optimality_claim": False,
                "meaning": "已声明的土壤状态先核对观测依据；不是信息增益或农业效果。",
            }
        )
    for key, values, label in [
        ("soil", [None, "dry", "moist"], "先补哪条土壤反馈？"),
        ("shade", ["unknown", "present", "absent"], "遮阴位置和覆盖时段是什么？"),
        ("growth_stage", ["unknown", "young_growth", "mature"], "当前生长阶段是什么？"),
    ]:
        if ctx[key] not in (None, "unknown"):
            continue
        branches = []
        for value in values:
            altered = {**ctx, key: value}
            branches.append(
                {t["focus"] for t in _tasks(state, altered, weather, "full")}
            )
        changes = max(len(a ^ b) for a in branches for b in branches)
        questions.append(
            {
                "factor": key,
                "question": label,
                "branch_task_changes": changes,
                "optimality_claim": False,
                "meaning": "只比较明确规则分支的任务变化，不是信息增益或因果价值。",
            }
        )
    return sorted(
        questions,
        key=lambda q: (
            q.get("priority") != "PROVENANCE_FIRST",
            -q["branch_task_changes"],
        ),
    )


def _task_basis(task, state, weather, matches):
    inputs = {
        item["id"]: item for item in [*state["observations"], *state["context_factors"]]
    }
    requested = set(task["basis_input_ids"])
    pending = list(requested)
    while pending:
        for identifier in inputs[pending.pop()].get("input_ids", []):
            if identifier not in requested:
                requested.add(identifier)
                pending.append(identifier)
    return stable_hash(
        {
            "rule_id": task["rule_id"],
            "inputs": {key: inputs[key] for key in sorted(requested)},
            "weather": weather
            if any(key.startswith("weather_") for key in requested)
            else None,
            "evidence": [
                match
                for match in matches
                if match["card_id"] in task["evidence_card_ids"]
            ],
        }
    )


def analyze_context(
    payload, *, cards=None, policy="full", previous=None, candidate_explanation=None
):
    if policy not in ("weather_rules", "weather_evidence", "full"):
        raise ValueError("Unknown comparator")
    state = deepcopy(payload["nature_state"])
    errors = validate_state(state)
    if errors:
        raise ValueError("; ".join(errors))
    ctx = _context(payload["context"])
    weather = deepcopy(payload["weather"])
    loaded, sources = load_cards()
    bank = cards if cards is not None else loaded
    matches = _match_cards(ctx, bank, sources) if policy != "weather_rules" else []
    tasks = _tasks(state, ctx, weather, policy)
    flags = []
    for task in tasks:
        task["basis_sha256"] = _task_basis(task, state, weather, matches)
    if candidate_explanation is not None:
        cited = candidate_explanation.get("card_ids", [])
        if candidate_explanation.get(
            "temperature_c", weather["heat_point_c"]
        ) != weather["heat_point_c"] or any(
            cid not in {c["card_id"] for c in loaded} for cid in cited
        ):
            flags.append("EXPLANATION_REJECTED")
    if previous:
        prior = {t["deduplication_key"]: t for t in previous["tasks"]}
        for task in tasks:
            old = prior.get(task["deduplication_key"])
            task["previous_version_id"] = previous["version_id"]
            if old and old["status"] == "SIMULATED_COMPLETION":
                if old.get("basis_sha256") == task["basis_sha256"]:
                    task["status"] = "SIMULATED_COMPLETION"
                elif "TASK_BASIS_CHANGED" not in flags:
                    flags.append("TASK_BASIS_CHANGED")
    state["evidence_matches"] = [
        {key: match[key] for key in ("card_id", "input_ids", "applicability", "reason")}
        for match in matches
    ]
    state["review_tasks"] = deepcopy(tasks)
    issues = validate_state(state)
    if issues:
        raise ValueError("; ".join(issues))
    conflict = (
        ctx["soil"] == "moist"
        and weather["reference_balance_mm"] >= weather["balance_threshold_mm"]
    )
    if conflict and policy == "full":
        flags.append("CONTEXT_CONFLICT_RETAINED")
    explanation = f"区域气温估计{weather['heat_point_c']:.2f}°C；过去七日参考收支{weather['reference_balance_mm']:.2f}mm。"
    explanation += {
        None: "土壤状态未知，先补充记录。",
        "moist": "模拟湿润反馈与区域气象线索分别保留，先对齐时间、位置和土层。",
        "dry": "模拟偏干反馈仅形成联合核查假设，需要核对观察方法。",
    }[ctx["soil"]]
    review = {
        "status": "WITHHELD"
        if ctx["requested_claim"] != "context_review"
        else "CONTEXT_CHECK_ONLY",
        "reason": "适用范围按物种、品种、环境、处理和测量终点分别核对；不生成损伤概率、处理剂量或产量收益。",
    }
    lineage = [*previous.get("lineage", []), previous["version_id"]] if previous else []
    version_id = stable_hash(
        {
            "engine": ENGINE_DIGEST,
            "state": state,
            "weather": weather,
            "policy": policy,
            "flags": flags,
            "previous": lineage[-1:],
        }
    )[:24]
    return {
        "nature_state": state,
        "context": ctx,
        "weather": weather,
        "weather_hash": stable_hash(weather),
        "tasks": tasks,
        "applicability": matches,
        "graph": _graph(state, matches, tasks, conflict and policy == "full"),
        "questions": _questions(state, ctx, weather) if policy == "full" else [],
        "claim_review": review,
        "explanation": explanation,
        "flags": flags,
        "used_card_ids": sorted({cid for t in tasks for cid in t["evidence_card_ids"]}),
        "version_id": version_id,
        "engine_sha256": ENGINE_DIGEST,
        "lineage": lineage,
        "policy": policy,
        "operational_admission": False,
        "knowledge_scope": "CURRENT_SOURCE_INTERPRETATION_OF_HISTORICAL_OR_AI_SCENARIO",
        "new_effectiveness_claim": False,
    }


def complete_task(result, task_id, *, completed=True):
    if type(completed) is not bool:
        raise TypeError("Task completion must be a boolean")
    updated = deepcopy(result)
    task = next((t for t in updated["tasks"] if t["task_id"] == task_id), None)
    if task is None:
        raise ValueError("Task not found")
    task["status"] = "SIMULATED_COMPLETION" if completed else "PROPOSED"
    updated["nature_state"]["review_tasks"] = deepcopy(updated["tasks"])
    updated["lineage"] = [*result["lineage"], result["version_id"]]
    updated["version_id"] = stable_hash(
        {"previous": result["version_id"], "tasks": updated["tasks"]}
    )[:24]
    updated["graph"] = _graph(
        updated["nature_state"],
        updated["applicability"],
        updated["tasks"],
        "CONTEXT_CONFLICT_RETAINED" in updated["flags"],
    )
    return updated
