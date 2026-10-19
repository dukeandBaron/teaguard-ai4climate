"""Small explicit request contracts and stable application error categories."""

from dataclasses import dataclass
from datetime import date
from typing import Any


class AppError(ValueError):
    def __init__(self, message: str, *, code: str = "INVALID_INPUT", status: int = 400):
        super().__init__(message)
        self.code = code
        self.status = status


def version_key(value: Any) -> str:
    if (
        not isinstance(value, str)
        or len(value) != 24
        or any(c not in "0123456789abcdef" for c in value)
    ):
        raise AppError("版本编号格式不正确。")
    return value


def object_fields(value: Any, allowed: set[str]) -> dict:
    if not isinstance(value, dict):
        raise AppError("请求须为对象。")
    extra = set(value) - allowed
    if extra:
        raise AppError("不支持的请求字段：" + ", ".join(sorted(extra)))
    return value


@dataclass(frozen=True)
class AnalyzeRequest:
    weather_mode: str
    date: str
    case_id: str
    context: dict
    previous_version_id: str | None

    @classmethod
    def parse(cls, payload: Any):
        args = object_fields(
            payload,
            {"weather_mode", "date", "case_id", "context", "previous_version_id"},
        )
        mode = args.get("weather_mode", "historical")
        if mode not in ("historical", "synthetic"):
            raise AppError("未知天气模式。")
        day = args.get("date", "2025-07-15")
        if not isinstance(day, str) or len(day) != 10:
            raise AppError("日期须为YYYY-MM-DD。")
        try:
            date.fromisoformat(day)
        except ValueError as exc:
            raise AppError("日期不是有效的日历日期。") from exc
        if mode == "synthetic" and day != "2025-07-15":
            raise AppError("固定AI情境日期为2025-07-15，请载入情境或选择对应日期。")
        case = args.get("case_id", "LOCAL_CONTEXT")
        if not isinstance(case, str) or not case or len(case) > 60:
            raise AppError("情境编号无效。")
        context = args.get("context", {})
        if not isinstance(context, dict):
            raise AppError("情境须为对象。")
        previous = args.get("previous_version_id")
        if previous is not None:
            previous = version_key(previous)
        return cls(mode, day, case, context.copy(), previous)


@dataclass(frozen=True)
class FeedbackRequest:
    version_id: str
    task_id: str
    completed: bool

    @classmethod
    def parse(cls, payload: Any):
        args = object_fields(payload, {"version_id", "task_id", "completed"})
        if type(args.get("completed")) is not bool:
            raise AppError("需要明确的模拟勾选状态。")
        task = args.get("task_id")
        if not isinstance(task, str) or not task or len(task) > 100:
            raise AppError("核查事项编号无效。")
        return cls(version_key(args.get("version_id")), task, args["completed"])
