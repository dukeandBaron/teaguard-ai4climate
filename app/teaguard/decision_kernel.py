"""Offline numerical/semantic/evidence separation inspired by DualSG and GeoGPT-RAG.

This is an independently authored engineering adaptation, not either published
model. All forecast examples and intervals in this candidate are synthetic.
"""

from __future__ import annotations

import hashlib
import json
import math
from copy import deepcopy
from datetime import datetime
from pathlib import Path
from typing import Any

from .forecast_contract import PASS, validate_forecast


def _number(value: Any) -> float:
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        raise TypeError("A numeric measurement is required")
    result = float(value)
    if not math.isfinite(result):
        raise ValueError("Nonfinite values are not accepted")
    return result


def load_evidence_bank(path: Path) -> dict:
    """Bind evidence-card metadata to the exact locally read source file."""
    bank = json.loads(path.read_text(encoding="utf-8"))
    root = path.resolve().parent.parent
    if not isinstance(bank, dict) or not isinstance(bank.get("sources"), list):
        raise TypeError("Invalid evidence-bank structure")
    if not isinstance(bank.get("cards"), list):
        raise TypeError("Evidence cards must be a list")
    for source in bank["sources"]:
        if not isinstance(source, dict):
            raise TypeError("Source metadata must be an object")
        relative = source.get("local_file")
        if not isinstance(relative, str):
            raise TypeError("Missing local source file")
        reference = (root / relative).resolve()
        if not reference.is_relative_to(root):
            raise ValueError("Source reference escapes candidate directory")
        digest = hashlib.sha256(reference.read_bytes()).hexdigest()
        if digest != source.get("sha256"):
            raise ValueError("Source reference hash mismatch")
        source["binding_verified"] = True
    return bank


def summarize_history(observations: list, expected_dates: list[str]) -> dict:
    """Calculate descriptive summaries from exactly the permitted past dates."""
    if not isinstance(observations, list) or len(observations) != 14:
        raise ValueError("Exactly14 history days are required")
    if not all(isinstance(row, dict) for row in observations):
        raise TypeError("History rows must be objects")
    if [row.get("date") for row in observations] != expected_dates:
        raise ValueError("History dates differ from the audited14-day window")
    temperatures, rainfall, et0 = [], [], []
    for row in observations:
        if row.get("evidence_kind") != "AI_AUTHORED_SYNTHETIC":
            raise ValueError(
                "This preview accepts explicitly synthetic observations only"
            )
        temperatures.append(_number(row.get("tmax_c")))
        rainfall.append(_number(row.get("rain_mm")))
        et0.append(_number(row.get("et0_mm")))
    if min(rainfall + et0) < 0:
        raise ValueError("Rainfall and referenceET0 must be nonnegative")
    delta = sum(temperatures[-3:]) / 3 - sum(temperatures[-6:-3]) / 3
    raw = {
        "temperature_recent3_minus_previous3_c": delta,
        "rain_7d_mm": sum(rainfall[-7:]),
        "et0_7d_mm": sum(et0[-7:]),
        "reference_balance_7d_mm": sum(et0[-7:]) - sum(rainfall[-7:]),
    }
    return {
        **{key: round(value, 2) for key, value in raw.items()},
        "raw": raw,
        "trend": "warming" if delta > 0.5 else "cooling" if delta < -0.5 else "stable",
        "trend_tolerance_c": 0.5,
        "trend_tolerance_role": "DESCRIPTIVE_ONLY_NOT_AN_AGRONOMIC_THRESHOLD",
        "interpretation": "ET0-minus-rain is a reference climatic summary, not soil water or irrigation dose.",
    }


def _evidence(
    bank: dict, claim: str, crop: str, region: str
) -> tuple[list, str | None]:
    sources = {s.get("id"): s for s in bank.get("sources", []) if isinstance(s, dict)}
    matching, citations = [], {}
    for card in bank.get("cards", []):
        if not isinstance(card, dict) or claim not in card.get("claim_ids", []):
            continue
        matching.append(card)
        if claim in card.get("does_not_support", []):
            continue
        if not any(c in card.get("crop", []) for c in ("*", crop)):
            continue
        if not any(r in card.get("regions", []) for r in ("*", region)):
            continue
        source = sources.get(card.get("source_id"), {})
        if source.get("binding_verified") is not True:
            continue
        if not card.get("locator") or not source.get("url"):
            continue
        card_id = card.get("id")
        citations[card_id] = {
            "card_id": card_id,
            "claim_id": claim,
            "title": source["title"],
            "url": source["url"],
            "locator": card["locator"],
            "source_sha256": source["sha256"],
            "scope": card.get("scope"),
            "summary_zh": card.get("summary_zh"),
        }
    if citations:
        return [citations[k] for k in sorted(citations)], None
    return [], "EVIDENCE_NOT_APPLICABLE" if matching else "EVIDENCE_MISSING"


def analyze_offline(
    *,
    record: Any,
    observations: Any,
    interval: Any,
    evidence_bank: dict,
    soil_simulation: str = "unknown",
    semantic_hint: dict | None = None,
    heat_threshold_c: float = 35.0,
    balance_threshold_mm: float = 15.0,
    crop: str = "tea",
    region: str = "Meijiawu",
) -> dict:
    """Run the integrated preview with gate, deterministic numbers and cited tasks."""
    admission = validate_forecast(record)
    result = {
        "state": "HOLD_INPUT",
        "admission": admission,
        "actions": [],
        "flags": [],
        "production_admission": False,
        "evidence_kind": "AI_AUTHORED_SYNTHETIC_DECISION_REPLAY",
        "knowledge_scope": "CURRENT_REFERENCE_FOR_RETROSPECTIVE_SIMULATION",
        "threshold_role": "USER_SCENARIO_NOT_MEASURED_TEA_DAMAGE",
    }
    if admission["state"] != PASS:
        return result
    if not isinstance(evidence_bank, dict) or not all(
        isinstance(evidence_bank.get(key, []), list) for key in ("sources", "cards")
    ):
        result.update(state="HOLD_EVIDENCE", error="Invalid evidence bank")
        return result
    try:
        heat_threshold = _number(heat_threshold_c)
        balance_threshold = _number(balance_threshold_mm)
        if not 28 <= heat_threshold <= 42 or not 5 <= balance_threshold <= 50:
            raise ValueError("Scenario threshold outside the V1 display range")
        if soil_simulation not in ("unknown", "dry", "moist"):
            raise ValueError("Invalid simulated soil state")
    except (TypeError, ValueError, OverflowError) as exc:
        result.update(state="HOLD_SCENARIO", error=str(exc))
        return result
    try:
        expected = [row["date"] for row in record["history_days"]]
        summary = summarize_history(observations, expected)
    except (TypeError, ValueError, OverflowError) as exc:
        result.update(state="HOLD_HISTORY", error=str(exc))
        return result
    result["history_summary"] = summary
    try:
        if not isinstance(interval, dict):
            raise TypeError("Explicitly synthetic interval metadata is required")
        if interval.get("run_id") != record["run_id"]:
            raise ValueError("Interval belongs to another forecast run")
        if interval.get("kind") != "AI_AUTHORED_SYNTHETIC_INTERVAL_NOT_EMPIRICAL":
            raise ValueError(
                "No calibrated provider interval is implemented in this preview"
            )
        if (
            interval.get("unit") != "C"
            or interval.get("statistic") != "MAX_OF_72_HOURLY_INSTANTS"
        ):
            raise ValueError("Interval unit or target statistic does not match")
        for field in ("start_utc", "end_exclusive_utc"):
            value = interval.get("target_" + field)
            if not isinstance(value, str):
                raise TypeError("Interval target time is required")
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
            expected = datetime.fromisoformat(
                record["target"][field].replace("Z", "+00:00")
            )
            if parsed.tzinfo is None or parsed != expected:
                raise ValueError("Interval belongs to another target window")
        lower, upper = (
            _number(interval.get("lower_c")),
            _number(interval.get("upper_c")),
        )
        point = max(_number(s["value"]) for s in record["samples"])
        if not lower <= point <= upper:
            raise ValueError("Interval does not contain the frozen forecast maximum")
    except (TypeError, ValueError, OverflowError) as exc:
        result.update(state="HOLD_INTERVAL", error=str(exc))
        return result
    result["numeric"] = {
        "sampled_hourly_max_c": point,
        "lower_c": lower,
        "upper_c": upper,
        "interval_kind": interval["kind"],
        "coverage_guarantee": False,
        "aggregation": "max of72 forecast hourly instants; not measured daily-maximum truth",
    }
    if isinstance(semantic_hint, dict):
        if semantic_hint.get("trend", summary["trend"]) != summary["trend"]:
            result["flags"].append("SEMANTIC_CONFLICT_FALLBACK")
        if set(semantic_hint) - {"trend"}:
            result["flags"].append("SEMANTIC_NUMERIC_OVERRIDE_IGNORED")
    identity = {
        "forecast_input_sha256": admission["input_sha256"],
        "history_summary": summary,
        "numeric": result["numeric"],
        "evidence_bank": evidence_bank,
        "soil": soil_simulation,
        "heat_threshold_c": heat_threshold,
        "balance_threshold_mm": balance_threshold,
        "semantic_flags": result["flags"],
        "crop": crop,
        "region": region,
    }
    try:
        encoded = json.dumps(
            identity, sort_keys=True, ensure_ascii=False, allow_nan=False
        )
    except (TypeError, ValueError) as exc:
        result.update(state="HOLD_EVIDENCE", error=str(exc))
        return result
    result["analysis_id"] = hashlib.sha256(encoded.encode("utf-8")).hexdigest()[:20]
    actions = []

    def task(code: str, title: str, reason: str, citations: list) -> None:
        identity = {
            "analysis_id": result["analysis_id"],
            "run_id": record["run_id"],
            "target": record["target"],
            "code": code,
            "citations": sorted(c["card_id"] for c in citations),
        }
        task_id = hashlib.sha256(
            json.dumps(identity, sort_keys=True).encode()
        ).hexdigest()[:16]
        actions.append(
            {
                "task_id": task_id,
                "code": code,
                "title": title,
                "reason": reason,
                "citations": citations,
                "evidence_kind": "AI_AUTHORED_SYNTHETIC_TASK",
            }
        )

    # Compare raw values. Rounded display values never determine action admission.
    if lower >= heat_threshold:
        result["heat_state"] = "INTERVAL_ABOVE_SCENARIO"
    elif upper >= heat_threshold:
        result["heat_state"] = "REVIEW_POSSIBLE"
    else:
        result["heat_state"] = "BELOW_SCENARIO"
    if upper >= heat_threshold:
        task(
            "heat_verify",
            "核对当地预报和现场温度条件",
            f"合成区间上界达到{heat_threshold:g}°C情景阈值；该阈值不表示茶树损伤。",
            [],
        )
    balance = summary["raw"]["reference_balance_7d_mm"]
    if balance >= balance_threshold:
        citations, problem = _evidence(
            evidence_bank, "REFERENCE_ET0_NOT_FIELD_SOIL_WATER", crop, region
        )
        if problem:
            result["flags"].append(problem)
        else:
            if soil_simulation == "moist":
                result["flags"].append("SOIL_WEATHER_CONFLICT")
                reason = "参考气象收支与模拟湿润土壤信息不一致，先核对来源和现场条件。"
            else:
                reason = "参考收支达到情景阈值，但不能据此推断根区缺水或灌溉剂量。"
            task("soil_recheck", "核对土壤、叶片与供水条件", reason, citations)
    tasks = {a["task_id"]: a for a in actions}
    result.update(
        state="PASS_OFFLINE_DECISION_REPLAY",
        actions=list(tasks.values()),
        flags=sorted(set(result["flags"])),
        soil_simulation=soil_simulation,
        explanation_zh=(
            f"过去3日相对前3日最高温均值变化{summary['temperature_recent3_minus_previous3_c']:.2f}°C；"
            f"过去7日参考ET₀减降雨为{summary['reference_balance_7d_mm']:.2f}mm。"
            "这是可复算的输入说明，不能解释为因果效应或真实茶园收益。"
        ),
    )
    return deepcopy(result)
