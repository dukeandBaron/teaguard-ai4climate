"""Normalize declared inputs and preserve their explicit evidence roles."""

import math
from copy import deepcopy
from datetime import datetime

from .serialization import stable_hash

DEFAULT_CONTEXT = {
    "soil": None,
    "shade": "unknown",
    "growth_stage": "unknown",
    "cultivar": None,
    "species": "Camellia sinensis",
    "setting": "field",
    "treatment": "unknown",
    "endpoint": "inspection",
    "soil_time": None,
    "soil_depth_cm": None,
    "soil_method": None,
    "requested_claim": "context_review",
}

FACTOR_KEYS = {
    "soil": "SOIL_MOISTURE_DESCRIPTION",
    "shade": "SHADE_STATUS",
    "growth_stage": "GROWTH_STAGE",
    "cultivar": "CULTIVAR",
}


def _number(value):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TypeError("Weather fields must be numeric")
    try:
        if not math.isfinite(value):
            raise ValueError("Weather value must be finite")
    except OverflowError as exc:
        raise ValueError("Weather numeric overflow") from exc
    return float(value)


def _context(value):
    if not isinstance(value, dict):
        raise TypeError("Context must be an object")
    result = {**DEFAULT_CONTEXT, **value}
    if set(result) - set(DEFAULT_CONTEXT):
        raise ValueError("Unknown context field")
    for key, allowed in {
        "soil": (None, "unknown", "moist", "dry"),
        "shade": ("unknown", "present", "absent"),
        "growth_stage": ("unknown", "young_growth", "mature"),
        "requested_claim": (
            "context_review",
            "field_combined_damage",
            "hydrogel_treatment",
        ),
    }.items():
        if result[key] not in allowed:
            raise ValueError("Invalid context: " + key)
    for key in ("soil", "cultivar", "soil_method", "soil_time"):
        if result[key] in ("unknown", ""):
            result[key] = None
    for key in (
        "cultivar",
        "species",
        "setting",
        "treatment",
        "endpoint",
        "soil_method",
    ):
        if result[key] is not None and (
            not isinstance(result[key], str) or len(result[key]) > 100
        ):
            raise ValueError("Invalid declared context string: " + key)
    if (
        result["soil_depth_cm"] is not None
        and not 0 <= _number(result["soil_depth_cm"]) <= 300
    ):
        raise ValueError("Invalid soil depth")
    if result["soil_time"] is not None:
        if not isinstance(result["soil_time"], str):
            raise TypeError("Soil time must be a timezone-aware text value")
        parsed = datetime.fromisoformat(result["soil_time"].replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            raise ValueError("Soil time needs a timezone")
    return result


def make_scenario(
    *,
    context=None,
    weather=None,
    case_id="AI-context",
    decision_time="2025-07-15T12:00:00+08:00",
):
    ctx = _context({} if context is None else context)
    numeric = deepcopy(
        weather
        or {
            "heat_point_c": 34.5,
            "heat_lower_c": 32.5,
            "heat_upper_c": 36.5,
            "reference_balance_mm": 24.5,
            "heat_threshold_c": 35.0,
            "balance_threshold_mm": 15.0,
            "date": "2025-07-15",
            "source_kind": "AI_AUTHORED_SCENARIO",
            "source_sha256": stable_hash("fixed-weather-fixture"),
        }
    )
    for key in (
        "heat_point_c",
        "heat_lower_c",
        "heat_upper_c",
        "reference_balance_mm",
        "heat_threshold_c",
        "balance_threshold_mm",
    ):
        numeric[key] = _number(numeric[key])
    if (
        not numeric["heat_lower_c"]
        <= numeric["heat_point_c"]
        <= numeric["heat_upper_c"]
    ):
        raise ValueError("Invalid weather interval")
    if numeric.get("source_kind") not in (
        "AI_AUTHORED_SCENARIO",
        "PUBLIC_REANALYSIS_REPLAY",
    ):
        raise ValueError(
            "Only labelled scenarios or frozen historical replay are supported"
        )
    synthetic = numeric["source_kind"] == "AI_AUTHORED_SCENARIO"

    def observation(identifier, kind, value, *, field=False):
        is_ai = field or synthetic
        return {
            "id": identifier,
            "kind": kind,
            "value": value,
            "unit": "°C"
            if kind in ("GRID_TEMPERATURE", "SIMULATED_WEATHER_INDICATOR")
            else "mm"
            if kind == "REFERENCE_ET0_MINUS_PRECIP"
            else None,
            "valid_start_utc": None,
            "valid_end_utc": None,
            "available_at_utc": None,
            "availability_status": "UNKNOWN",
            "availability_evidence": None,
            "retrieved_at_utc": numeric.get("retrieved_at", "2026-10-19T02:00:00Z"),
            "spatial_support": "SCENARIO" if is_ai else "REGIONAL_GRID",
            "evidence_origin": "AI_AUTHORED_SCENARIO"
            if is_ai
            else "PUBLIC_GRID_REANALYSIS",
            "source_id": "DECLARED_AI_CONTEXT" if field else numeric["source_kind"],
            "source_sha256": stable_hash({"id": identifier, "value": value})
            if is_ai
            else numeric["source_sha256"],
            "measurement_method": "AI情境假设"
            if field
            else "冻结历史模型/区域资料回放；非业务预报"
            if not synthetic
            else "固定AI数值情境",
            "use_scope": "SCENARIO_ONLY" if is_ai else "HISTORICAL_REFERENCE",
        }

    observations = [
        observation(
            "weather_heat",
            "SIMULATED_WEATHER_INDICATOR" if synthetic else "GRID_TEMPERATURE",
            numeric["heat_point_c"],
        ),
        observation(
            "weather_balance",
            "REFERENCE_ET0_MINUS_PRECIP",
            numeric["reference_balance_mm"],
        ),
    ]
    factors = []
    for key, factor in FACTOR_KEYS.items():
        value = ctx[key]
        value = None if value == "unknown" else value
        obs = observation(
            "obs_" + key,
            "SOIL_DESCRIPTION" if key == "soil" else "MANAGEMENT_NOTE",
            value,
            field=True,
        )
        if key == "soil":
            obs.update(
                valid_start_utc=ctx["soil_time"],
                valid_end_utc=ctx["soil_time"],
                measurement_method=ctx["soil_method"],
                depth_cm=ctx["soil_depth_cm"],
            )
        observations.append(obs)
        factors.append(
            {
                "id": "factor_" + key,
                "factor": factor,
                "state": value,
                "input_ids": [obs["id"]],
                "status": "UNKNOWN" if value is None else "AI_SCENARIO",
            }
        )
    state = {
        "schema_version": "0.2",
        "case_id": case_id,
        "mode": "AI_SCENARIO",
        "decision_time_utc": decision_time,
        "spatial_context": {
            "name": "梅家坞周边代表性区域与模拟地块",
            "support_type": "AI_SCENARIO" if synthetic else "REGIONAL_GRID",
            "latitude": 30.201,
            "longitude": 120.103,
            "resolution_m": 25000,
            "spatial_claim": "SCENARIO_ASSUMPTION"
            if synthetic
            else "REGIONAL_REFERENCE",
        },
        "observations": observations,
        "context_factors": factors,
        "organism_context": {
            k: ctx[k]
            for k in ("species", "cultivar", "setting", "treatment", "endpoint")
        },
        "evidence_matches": [],
        "review_tasks": [],
    }
    return {"nature_state": state, "context": ctx, "weather": numeric}


def validate_state(state):
    errors = []
    if not isinstance(state, dict):
        return ["state must be an object"]
    ids = [o.get("id") for o in state.get("observations", [])] + [
        f.get("id") for f in state.get("context_factors", [])
    ]
    if len(ids) != len(set(ids)) or None in ids:
        errors.append("duplicate or missing input ids")
    for obs in state.get("observations", []):
        if obs.get("evidence_origin") == "AI_AUTHORED_SCENARIO" and (
            obs.get("spatial_support") != "SCENARIO"
            or obs.get("use_scope") != "SCENARIO_ONLY"
        ):
            errors.append(
                "synthetic origin promoted to measurement or operational input"
            )
        if obs.get("availability_status") == "UNKNOWN" and (
            obs.get("available_at_utc") is not None
            or obs.get("use_scope") == "OPERATIONAL_INPUT_CANDIDATE"
        ):
            errors.append("unknown availability promoted to operational")
        if (
            obs.get("evidence_origin") == "PUBLIC_GRID_REANALYSIS"
            and obs.get("spatial_support") != "REGIONAL_GRID"
        ):
            errors.append("regional reanalysis promoted to field observation")
    origins = {
        o.get("id"): o.get("evidence_origin") for o in state.get("observations", [])
    }
    for factor in state.get("context_factors", []):
        if factor.get("status") == "MEASURED_WITH_PROVENANCE" and any(
            origins.get(i) == "AI_AUTHORED_SCENARIO"
            for i in factor.get("input_ids", [])
        ):
            errors.append("AI context factor relabelled as measured")
    keys = []
    for task in state.get("review_tasks", []):
        keys.append(task.get("deduplication_key"))
        if not set(task.get("basis_input_ids", [])) <= set(ids):
            errors.append("task input reference unresolved")
    if len(keys) != len(set(keys)):
        errors.append("duplicate active task key")
    for match in state.get("evidence_matches", []):
        if not set(match.get("input_ids", [])) <= set(ids):
            errors.append("evidence input reference unresolved")
    return errors
