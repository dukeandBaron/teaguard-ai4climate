"""Application use cases; domain policy, frozen inputs and storage stay separate."""

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

from .contracts import AnalyzeRequest, AppError, FeedbackRequest
from .nature import ENGINE_DIGEST, analyze_context, complete_task, make_scenario
from .record_store import RecordStore
from .weather_repository import WeatherRepository

ROOT = Path(__file__).resolve().parents[1]
VERSION = "0.3.1"
PRESETS = {
    "N01": {"soil": "moist"},
    "N02": {"soil": "dry"},
    "N03": {"soil": None},
    "N04": {"shade": "present"},
    "N05": {"growth_stage": "young_growth"},
    "N06": {"requested_claim": "hydrogel_treatment"},
    "N07": {"requested_claim": "field_combined_damage"},
    "N08": {"soil": "moist", "soil_time": None, "soil_depth_cm": None},
    "N09": {},
    "N10": {"soil": "dry"},
}


class NatureService:
    def __init__(
        self,
        *,
        store: RecordStore | None = None,
        weather: WeatherRepository | None = None,
    ):
        self.store = (
            store
            if store is not None
            else RecordStore(ROOT / "runtime/records.sqlite3")
        )
        self.weather_source = weather if weather is not None else WeatherRepository()
        self.replay = json.loads(
            (ROOT / "artifacts/nature_replay.json").read_text(encoding="utf-8")
        )
        self.project_status = json.loads(
            (ROOT / "data/project_status.json").read_text(encoding="utf-8")
        )

    def get_record(self, identifier: str) -> dict:
        return self.store.get(identifier)

    def list_records(self) -> list[dict]:
        return [
            {
                "id": r["version_id"],
                "date": r["weather"]["date"],
                "soil": r["context"]["soil"] or "unknown",
                "tasks": len(r["tasks"]),
            }
            for r in self.store.list_recent()
        ]

    def analyze(self, payload) -> dict:
        request = AnalyzeRequest.parse(payload)
        previous = (
            self.get_record(request.previous_version_id)
            if request.previous_version_id
            else None
        )
        if previous and previous["engine_sha256"] != ENGINE_DIGEST:
            raise AppError(
                "该记录来自旧判断版本，可查看或导出；继续分析请明确开始新记录。",
                code="VERSION_INCOMPATIBLE",
                status=409,
            )
        weather = (
            self.weather_source.weather(request.date)
            if request.weather_mode == "historical"
            else None
        )
        decision = (
            datetime.fromisoformat(request.date)
            .replace(hour=12, tzinfo=timezone(timedelta(hours=8)))
            .isoformat()
            if weather is not None
            else "2025-07-15T12:00:00+08:00"
        )
        scenario = make_scenario(
            context=request.context,
            weather=weather,
            case_id=request.case_id,
            decision_time=decision,
        )
        generated = (
            {"temperature_c": 99, "card_ids": ["E-NONEXISTENT-INJECTED"]}
            if request.case_id == "N09"
            else None
        )
        result = analyze_context(
            scenario, previous=previous, candidate_explanation=generated
        )
        result.update(
            {
                "weather_mode": request.weather_mode,
                "case_id": request.case_id,
                "record_format": "TEAGUARD_RECORD_V1",
                "data_role_label": "公开天气历史回放 + AI地块情境"
                if weather is not None
                else "固定AI天气与地块情境",
                "weather_history": self.weather_source.history(request.date)
                if weather is not None
                else [],
            }
        )
        return self.store.save(result)

    def feedback(self, payload) -> dict:
        request = FeedbackRequest.parse(payload)
        old = self.get_record(request.version_id)
        if old["engine_sha256"] != ENGINE_DIGEST:
            raise AppError(
                "旧判断版本仅支持查看和导出。", code="VERSION_INCOMPATIBLE", status=409
            )
        task = next((t for t in old["tasks"] if t["task_id"] == request.task_id), None)
        if task is None:
            raise AppError("未找到该核查事项。", code="TASK_NOT_FOUND", status=404)
        unchanged = task["status"] == (
            "SIMULATED_COMPLETION" if request.completed else "PROPOSED"
        )
        return (
            old
            if unchanged
            else self.store.save(
                complete_task(old, request.task_id, completed=request.completed)
            )
        )

    def bootstrap(self) -> dict:
        default = self.analyze({})
        return {
            "version": VERSION,
            "default": default,
            "coverage": self.weather_source.coverage(),
            "dates": self.weather_source.dates,
            "presets": PRESETS,
            "records": self.list_records(),
            "project_status": self.project_status,
            "replay": {k: v for k, v in self.replay.items() if k != "outputs"},
            "frozen_evaluation": self.weather_source.evaluation,
        }
