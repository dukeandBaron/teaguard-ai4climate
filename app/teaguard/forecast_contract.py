"""Audit forecast metadata without learning, network access or deployment claims.

A0 checks consistency against a frozen, explicitly synthetic contract. It cannot
independently authenticate a provider's historical release time. Public records
therefore remain UNKNOWN until a separate source adapter verifies their evidence.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
from datetime import date, datetime, time, timedelta, timezone
from typing import Any

UTC = timezone.utc
BEIJING = timezone(timedelta(hours=8), "Asia/Shanghai")
PASS = "PASS_KNOWN_AVAILABLE"
REJECT = "REJECT"
UNKNOWN = "UNKNOWN_AVAILABILITY"


class _Audit:
    """Collect independent failures; rejection takes precedence over unknown."""

    def __init__(self) -> None:
        self.reasons: list[dict[str, str]] = []

    def add(self, code: str, field: str, message: str, *, unknown=False) -> None:
        self.reasons.append(
            {
                "code": code,
                "field": field,
                "message": message,
                "severity": "UNKNOWN" if unknown else "ERROR",
            }
        )

    def instant(
        self, value: Any, field: str, *, unknown_if_missing: bool = False
    ) -> datetime | None:
        if value is None and unknown_if_missing:
            self.add("AVAILABILITY_UNKNOWN", field, "发布时间未知。", unknown=True)
            return None
        try:
            if not isinstance(value, str):
                raise TypeError("timestamp must be a string")
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
            if parsed.tzinfo is None or parsed.utcoffset() is None:
                raise ValueError("explicit timezone required")
            return parsed.astimezone(UTC)
        except (ValueError, TypeError, OverflowError):
            self.add("TIMESTAMP_INVALID", field, "时间须含明确时区。")
            return None

    def availability(self, owner: dict, field: str, synthetic: bool) -> datetime | None:
        available = self.instant(
            owner.get("available_at"),
            field + ".available_at",
            unknown_if_missing=True,
        )
        proof = owner.get("availability_evidence")
        reference = proof.get("reference") if isinstance(proof, dict) else None
        if not isinstance(reference, str) or not reference.strip():
            self.add(
                "AVAILABILITY_PROOF_MISSING",
                field + ".availability_evidence",
                "缺少发布时间来源；当前取数时间不能替代历史发布时间。",
                unknown=True,
            )
            return available
        supported = synthetic and proof.get("kind") == "SYNTHETIC_ASSUMPTION"
        if not supported:
            self.add(
                "PROOF_NOT_VERIFIED_BY_A0",
                field + ".availability_evidence",
                "A0未验证该真实来源；保留未知，不自动采信声明。",
                unknown=True,
            )
        claimed = self.instant(
            proof.get("available_at"),
            field + ".availability_evidence.available_at",
            unknown_if_missing=True,
        )
        if available and claimed and available != claimed:
            self.add(
                "AVAILABILITY_EVIDENCE_MISMATCH",
                field,
                "声明的发布时间与引用证据时间不一致。",
            )
        return available

    def finish(self, record_id: Any, record: Any) -> dict:
        errors = any(r["severity"] == "ERROR" for r in self.reasons)
        state = REJECT if errors else UNKNOWN if self.reasons else PASS
        try:
            encoded = json.dumps(
                record, sort_keys=True, ensure_ascii=False, allow_nan=False
            ).encode("utf-8")
            digest = hashlib.sha256(encoded).hexdigest()
        except (ValueError, TypeError, RecursionError):
            digest = None
        return {
            "record_id": record_id if isinstance(record_id, str) else None,
            "state": state,
            "reasons": self.reasons,
            "input_sha256": digest,
            "eligible_for_offline_simulation": state == PASS,
            "deployable": False,
            "evidence_scope": "A0_METADATA_AND_SYNTHETIC_CONSISTENCY_ONLY",
        }


def _finite_number(value: Any) -> bool:
    try:
        return (
            isinstance(value, (int, float))
            and not isinstance(value, bool)
            and math.isfinite(value)
        )
    except OverflowError:
        return False


def _target_window(
    record: dict, decision: datetime | None, audit: _Audit
) -> tuple[datetime | None, datetime | None]:
    target = record.get("target")
    if not isinstance(target, dict):
        audit.add("TARGET_INVALID", "target", "缺少完整预测目标合同。")
        return None, None
    if target.get("kind") != "NEXT_THREE_BEIJING_DAYS":
        audit.add(
            "TARGET_KIND_UNSUPPORTED", "target.kind", "A0固定随后三个北京时间日。"
        )
    if target.get("timezone") != "Asia/Shanghai":
        audit.add("TARGET_TIMEZONE_MISMATCH", "target.timezone", "目标须明确北京时间。")
    if target.get("unit") != "C" or target.get("quantity") != "temperature_2m":
        audit.add("TARGET_UNIT_OR_QUANTITY", "target", "须明确摄氏度和2米气温。")
    sampling = "HOURLY_INSTANTS_START_INCLUSIVE_END_EXCLUSIVE"
    if target.get("sampling") != sampling:
        audit.add("SAMPLING_MISMATCH", "target.sampling", "须明确逐时瞬时值采样口径。")
    start = audit.instant(target.get("start_utc"), "target.start_utc")
    end = audit.instant(target.get("end_exclusive_utc"), "target.end_exclusive_utc")
    if decision and start and end:
        try:
            next_day = decision.astimezone(BEIJING).date() + timedelta(days=1)
            expected_start = datetime.combine(next_day, time.min, BEIJING)
            expected_end = expected_start + timedelta(days=3)
        except OverflowError:
            audit.add("TARGET_WINDOW_MISMATCH", "target", "目标日期超出可表示范围。")
            return start, end
        if start != expected_start or end != expected_end:
            audit.add(
                "TARGET_WINDOW_MISMATCH",
                "target",
                "目标须为决策日之后三个完整北京时间日，不能换成未来72小时。",
            )
    return start, end


def _history(record: dict, decision: datetime | None, audit: _Audit) -> None:
    history = record.get("history_days")
    if not isinstance(history, list):
        audit.add("HISTORY_INVALID", "history_days", "历史日数据须为列表。")
        return
    dates = []
    synthetic = record.get("evidence_kind") == "AI_AUTHORED_SYNTHETIC"
    for index, row in enumerate(history):
        field = f"history_days[{index}]"
        if not isinstance(row, dict):
            audit.add("HISTORY_ROW_INVALID", field, "历史日记录须为对象。")
            continue
        try:
            day = date.fromisoformat(row.get("date", ""))
            dates.append(day)
        except (ValueError, TypeError):
            audit.add("HISTORY_DATE_INVALID", field, "无效历史日期。")
            continue
        period_end = audit.instant(row.get("period_end_utc"), field + ".period_end_utc")
        try:
            expected_end = datetime.combine(day + timedelta(days=1), time.min, BEIJING)
        except OverflowError:
            audit.add("HISTORY_DATE_INVALID", field, "历史日期超出可表示范围。")
            continue
        if period_end and period_end != expected_end:
            audit.add(
                "HISTORY_PERIOD_MISMATCH", field, "日聚合结束时间与北京时间日期不符。"
            )
        available = audit.availability(row, field, synthetic)
        if decision and period_end and period_end > decision:
            audit.add("HISTORY_DAY_UNFINISHED", field, "出单时该完整自然日尚未结束。")
        if available and period_end and available < period_end:
            audit.add(
                "HISTORY_RELEASE_BEFORE_END", field, "完整日聚合声明在日结前发布。"
            )
        if decision and available and available > decision:
            audit.add(
                "HISTORY_RELEASE_AFTER_DECISION", field, "历史日记录出单后才发布。"
            )
    if decision:
        try:
            day = decision.astimezone(BEIJING).date()
            expected_dates = [day - timedelta(days=i) for i in range(14, 0, -1)]
        except OverflowError:
            audit.add(
                "HISTORY_DATE_COVERAGE", "history_days", "历史窗口超出可表示范围。"
            )
            return
        if dates != expected_dates:
            audit.add(
                "HISTORY_DATE_COVERAGE",
                "history_days",
                "须恰好覆盖此前14个完整日且无重复缺测。",
            )


def _samples(
    record: dict,
    initialized: datetime | None,
    start: datetime | None,
    end: datetime | None,
    audit: _Audit,
) -> None:
    samples = record.get("samples")
    if not isinstance(samples, list):
        audit.add("SAMPLES_INVALID", "samples", "预报样本须为列表。")
        return
    valid_times = []
    for index, sample in enumerate(samples):
        field = f"samples[{index}]"
        if not isinstance(sample, dict):
            audit.add("SAMPLE_INVALID", field, "逐时样本须为对象。")
            continue
        valid = audit.instant(sample.get("valid_time_utc"), field + ".valid_time_utc")
        if valid:
            valid_times.append(valid)
        if sample.get("run_id") != record.get("run_id"):
            audit.add("MIXED_RUN", field, "同一目标混入不同起报。")
        if sample.get("grid_id") != record.get("grid_id"):
            audit.add("MIXED_GRID", field, "同一目标混入不同网格。")
        if sample.get("unit") != "C":
            audit.add("SAMPLE_UNIT_MISMATCH", field, "未显式转换的单位不得混合。")
        if not _finite_number(sample.get("value")):
            audit.add(
                "INVALID_SAMPLE_VALUE", field, "预报值须为有限数值且不能是布尔或文本。"
            )
        lead = sample.get("lead_hours")
        if not _finite_number(lead):
            audit.add("LEAD_TIME_MISMATCH", field, "预报时效必须是明确有限数值。")
        elif valid and initialized:
            actual_lead = (valid - initialized).total_seconds() / 3600
            if abs(lead - actual_lead) > 1e-8 or actual_lead < 0:
                audit.add("LEAD_TIME_MISMATCH", field, "声明时效与起报/有效时间不符。")
    if start and end:
        if end - start != timedelta(days=3):
            audit.add("FORECAST_TIME_COVERAGE", "samples", "预报窗口必须完整覆盖三日。")
            return
        expected = [start + timedelta(hours=i) for i in range(72)]
        if valid_times != expected:
            audit.add(
                "FORECAST_TIME_COVERAGE",
                "samples",
                "须按顺序覆盖目标内72个逐时点，无缺测、重复或越界。",
            )


def validate_forecast(record: Any) -> dict:
    """Classify one forecast input; no provider claim is authenticated by A0."""
    audit = _Audit()
    if not isinstance(record, dict):
        audit.add("RECORD_INVALID", "record", "输入须为JSON对象。")
        return audit.finish(None, record)
    record_id = record.get("record_id")
    for field in (
        "record_id",
        "provider",
        "model",
        "model_version",
        "run_id",
        "grid_id",
    ):
        if not isinstance(record.get(field), str) or not record[field].strip():
            audit.add("METADATA_MISSING", field, "缺少非空来源身份字段。")
    if record.get("source_kind") != "FORECAST":
        audit.add(
            "SOURCE_IS_NOT_FORECAST", "source_kind", "再分析或观测不得冒充已发布预报。"
        )
    evidence_kind = record.get("evidence_kind")
    if evidence_kind not in ("AI_AUTHORED_SYNTHETIC", "PUBLIC_ARCHIVED_FORECAST"):
        audit.add("PROVENANCE_UNSUPPORTED", "evidence_kind", "未知或未声明的资料类型。")
    synthetic = evidence_kind == "AI_AUTHORED_SYNTHETIC"
    if record.get("claimed_real_field_measurement") is not False:
        audit.add(
            "REAL_FIELD_CLAIM_INVALID",
            "claimed_real_field_measurement",
            "此候选不接受真实地块测量声明。",
        )
    source_hash = record.get("source_sha256")
    if not isinstance(source_hash, str) or not re.fullmatch(
        r"[a-fA-F0-9]{64}", source_hash
    ):
        audit.add("SOURCE_HASH_INVALID", "source_sha256", "缺少完整SHA-256来源摘要。")
    for forbidden in (
        "verification",
        "actual_targets",
        "future_labels",
        "ground_truth",
    ):
        if forbidden in record:
            audit.add("FUTURE_LABEL_IN_INPUT", forbidden, "事后真值不得进入预报输入。")
    decision = audit.instant(record.get("decision_time_utc"), "decision_time_utc")
    initialized = audit.instant(record.get("init_time_utc"), "init_time_utc")
    available = audit.availability(record, "forecast", synthetic)
    retrieved = audit.instant(record.get("retrieved_at"), "retrieved_at")
    ingested = audit.instant(record.get("ingested_at"), "ingested_at")
    if retrieved and ingested and ingested < retrieved:
        audit.add(
            "INGEST_BEFORE_RETRIEVAL", "ingested_at", "当前入库时间早于当前取数时间。"
        )
    if initialized and decision and initialized > decision:
        audit.add("INIT_AFTER_DECISION", "init_time_utc", "出单时尚未起报。")
    if available and initialized and available < initialized:
        audit.add("AVAILABLE_BEFORE_INIT", "available_at", "发布时间早于初始化时间。")
    if available and decision and available > decision:
        audit.add("RELEASE_AFTER_DECISION", "available_at", "出单时预报尚未公开。")
    location = record.get("location")
    if not isinstance(location, dict):
        audit.add("LOCATION_INVALID", "location", "缺少网格位置与海拔。")
    else:
        for key, low, high in (
            ("latitude", -90, 90),
            ("longitude", -180, 180),
            ("elevation_m", -500, 10000),
        ):
            value = location.get(key)
            if not _finite_number(value) or not low <= value <= high:
                audit.add(
                    "LOCATION_INVALID", "location." + key, "网格坐标或海拔不合法。"
                )
    start, end = _target_window(record, decision, audit)
    _history(record, decision, audit)
    _samples(record, initialized, start, end, audit)
    return audit.finish(record_id, record)


def validate_calibration_label(record: Any, label: Any) -> dict:
    """Only a complete, released label can be considered for a later update."""
    forecast = validate_forecast(record)
    audit = _Audit()
    audit.reasons.extend(forecast["reasons"])
    if not isinstance(label, dict):
        audit.add("LABEL_INVALID", "label", "标签元数据须为对象。")
        return audit.finish(None, label)
    target = record.get("target", {}) if isinstance(record, dict) else {}
    if not isinstance(target, dict):
        target = {}
    end = audit.instant(target.get("end_exclusive_utc"), "target.end_exclusive_utc")
    checked = audit.instant(label.get("checked_at"), "label.checked_at")
    synthetic = label.get("evidence_kind") == "AI_AUTHORED_SYNTHETIC"
    available = audit.availability(label, "label", synthetic)
    completed = label.get("completed_samples")
    if type(completed) is not int or completed != 72:
        audit.add(
            "LABEL_INCOMPLETE",
            "label.completed_samples",
            "三日标签尚未覆盖全部72个逐时点。",
        )
    for field in ("start_utc", "end_exclusive_utc"):
        label_time = audit.instant(
            label.get("target_" + field), "label.target_" + field
        )
        target_time = audit.instant(target.get(field), "target." + field)
        if label_time and target_time and label_time != target_time:
            audit.add("LABEL_TARGET_MISMATCH", "label", "标签目标与已发预报不一致。")
    if end and checked and checked < end:
        audit.add("LABEL_NOT_MATURED", "label.checked_at", "三日目标结束前不得校准。")
    if available and checked and available > checked:
        audit.add("LABEL_NOT_RELEASED", "label.available_at", "更新时标签尚未公开。")
    if available and end and available < end:
        audit.add(
            "LABEL_RELEASE_BEFORE_END",
            "label.available_at",
            "完整标签不能在目标结束前发布。",
        )
    if synthetic != (
        isinstance(record, dict)
        and record.get("evidence_kind") == "AI_AUTHORED_SYNTHETIC"
    ):
        audit.add(
            "LABEL_PROVENANCE_MISMATCH",
            "label.evidence_kind",
            "模拟与真实资料的标签不能混用。",
        )
    return audit.finish("calibration-label", label)


def audit_batch(records: list) -> dict:
    """Return every record outcome, including rejection and unknown denominators."""
    if not isinstance(records, list):
        raise TypeError("records must be a list")
    results = [validate_forecast(record) for record in records]
    counts = {
        "total_input": len(results),
        "qualified": sum(r["state"] == PASS for r in results),
        "rejected": sum(r["state"] == REJECT for r in results),
        "unknown": sum(r["state"] == UNKNOWN for r in results),
    }
    return {
        "mode": "OFFLINE_A0_SYNTHETIC_CONTRACT_AUDIT",
        "counts": counts,
        "has_nonempty_positive_control": counts["qualified"] > 0,
        "all_inputs_eligible": bool(results) and counts["qualified"] == len(results),
        "production_admission": False,
        "provider_availability_independently_verified": False,
        "records": results,
    }
