"""Explicitly synthetic fixtures, authored before the contract implementation."""

from copy import deepcopy
from datetime import datetime, timedelta, timezone

UTC = timezone.utc
BEIJING = timezone(timedelta(hours=8))


def stamp(value: datetime) -> str:
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def valid_record() -> dict:
    """A declared synthetic scenario, never a real provider receipt."""
    decision = datetime(2025, 7, 14, 20, tzinfo=BEIJING)
    initialized = decision - timedelta(hours=6)
    available = decision - timedelta(hours=2)
    start = datetime(2025, 7, 15, tzinfo=BEIJING)
    end = start + timedelta(days=3)
    history = []
    for offset in range(14, 0, -1):
        day = decision.date() - timedelta(days=offset)
        period_end = datetime.combine(
            day + timedelta(days=1), datetime.min.time(), BEIJING
        )
        history.append(
            {
                "date": day.isoformat(),
                "period_end_utc": stamp(period_end),
                "available_at": stamp(period_end + timedelta(hours=2)),
                "availability_evidence": {
                    "kind": "SYNTHETIC_ASSUMPTION",
                    "reference": "fixture://known-history-availability",
                    "available_at": stamp(period_end + timedelta(hours=2)),
                },
            }
        )
    return {
        "record_id": "synthetic-known-valid",
        "evidence_kind": "AI_AUTHORED_SYNTHETIC",
        "source_kind": "FORECAST",
        "claimed_real_field_measurement": False,
        "provider": "SYNTHETIC_PROVIDER",
        "model": "SYNTHETIC_MODEL",
        "model_version": "fixture-v1",
        "run_id": "synthetic-run-20250714-06",
        "source_sha256": "a" * 64,
        "init_time_utc": stamp(initialized),
        "available_at": stamp(available),
        "availability_evidence": {
            "kind": "SYNTHETIC_ASSUMPTION",
            "reference": "fixture://known-forecast-availability",
            "available_at": stamp(available),
        },
        "retrieved_at": "2026-10-18T15:00:00Z",
        "ingested_at": "2026-10-18T15:01:00Z",
        "decision_time_utc": stamp(decision),
        "location": {"latitude": 30.25, "longitude": 120.0, "elevation_m": 140},
        "grid_id": "SYNTHETIC_GRID",
        "target": {
            "kind": "NEXT_THREE_BEIJING_DAYS",
            "timezone": "Asia/Shanghai",
            "start_utc": stamp(start),
            "end_exclusive_utc": stamp(end),
            "sampling": "HOURLY_INSTANTS_START_INCLUSIVE_END_EXCLUSIVE",
            "quantity": "temperature_2m",
            "unit": "C",
        },
        "samples": [
            {
                "valid_time_utc": stamp(start + timedelta(hours=i)),
                "lead_hours": (start + timedelta(hours=i) - initialized).total_seconds()
                / 3600,
                "run_id": "synthetic-run-20250714-06",
                "grid_id": "SYNTHETIC_GRID",
                "unit": "C",
                "value": 29.0 + (i % 12) * 0.5,
            }
            for i in range(72)
        ],
        "history_days": history,
    }


def matured_label(record: dict | None = None) -> dict:
    record = record or valid_record()
    return {
        "target_start_utc": record["target"]["start_utc"],
        "target_end_exclusive_utc": record["target"]["end_exclusive_utc"],
        "available_at": "2025-07-17T18:00:00Z",
        "checked_at": "2025-07-17T19:00:00Z",
        "completed_samples": 72,
        "evidence_kind": "AI_AUTHORED_SYNTHETIC",
        "availability_evidence": {
            "kind": "SYNTHETIC_ASSUMPTION",
            "reference": "fixture://matured-label",
            "available_at": "2025-07-17T18:00:00Z",
        },
    }


def fixture_cases() -> list[dict]:
    """Boundary cases cover the agreed seven scenario classes plus controls."""
    cases = []

    def add(case_id, state, mutate):
        record = deepcopy(valid_record())
        mutate(record)
        record["record_id"] = case_id
        cases.append({"case_id": case_id, "expected_state": state, "record": record})

    add("CONTROL_VALID", "PASS_KNOWN_AVAILABLE", lambda r: None)
    add("S02_LATE", "REJECT", lambda r: r.update(available_at="2025-07-14T13:00:00Z"))
    add(
        "UNKNOWN_AVAILABILITY",
        "UNKNOWN_AVAILABILITY",
        lambda r: r.update(available_at=None),
    )
    add(
        "UNKNOWN_EVIDENCE",
        "UNKNOWN_AVAILABILITY",
        lambda r: r.update(availability_evidence=None),
    )
    add(
        "S03_UNFINISHED_DAY",
        "REJECT",
        lambda r: r["history_days"][-1].update(period_end_utc="2025-07-14T16:00:00Z"),
    )
    add("S04_MISSING_HISTORY", "REJECT", lambda r: r["history_days"].pop(5))
    add(
        "S06_SIMULATION_REAL_CLAIM",
        "REJECT",
        lambda r: r.update(claimed_real_field_measurement=True),
    )
    add("S11_KELVIN_UNDECLARED", "REJECT", lambda r: r["samples"][3].update(unit="K"))
    add(
        "S11_NAIVE_TIME",
        "REJECT",
        lambda r: r.update(decision_time_utc="2025-07-14T12:00:00"),
    )
    add(
        "S12_MIXED_RUN",
        "REJECT",
        lambda r: r["samples"][20].update(run_id="another-run"),
    )
    add("MISSING_FORECAST_HOUR", "REJECT", lambda r: r["samples"].pop(20))
    add(
        "REANALYSIS_IS_NOT_FORECAST",
        "REJECT",
        lambda r: r.update(source_kind="REANALYSIS"),
    )
    add(
        "UNKNOWN_HISTORY_RELEASE",
        "UNKNOWN_AVAILABILITY",
        lambda r: r["history_days"][0].update(available_at=None),
    )
    return cases
