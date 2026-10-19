"""Read-only frozen weather adapter; no fitting and no network operations."""

import csv
import hashlib
import json
from copy import deepcopy
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class WeatherRepository:
    def __init__(self, root: Path = ROOT):
        self.root = root
        manifest = json.loads(
            (root / "PARENT_V2_BINDING.json").read_text(encoding="utf-8")
        )["source_manifest"]
        for name in (
            "data/weather_daily.csv",
            "data/PROVENANCE.json",
            "artifacts/test_predictions.json",
            "artifacts/evaluation.json",
        ):
            if hashlib.sha256((root / name).read_bytes()).hexdigest() != manifest[name]:
                raise ValueError("Frozen weather input hash mismatch: " + name)
        self._provenance = json.loads(
            (root / "data/PROVENANCE.json").read_text(encoding="utf-8")
        )
        with (root / "data/weather_daily.csv").open(
            encoding="utf-8", newline=""
        ) as stream:
            self._rows = [
                {k: v if k == "date" else float(v) for k, v in row.items()}
                for row in csv.DictReader(stream)
            ]
        self._positions = {row["date"]: i for i, row in enumerate(self._rows)}
        self._predictions = {
            row["origin"]: row
            for row in json.loads(
                (root / "artifacts/test_predictions.json").read_text(encoding="utf-8")
            )
        }
        self._evaluation = json.loads(
            (root / "artifacts/evaluation.json").read_text(encoding="utf-8")
        )
        self.binding = hashlib.sha256(
            (root / "data/weather_daily.csv").read_bytes()
            + (root / "artifacts/test_predictions.json").read_bytes()
        ).hexdigest()

    @property
    def dates(self) -> list[str]:
        return sorted(self._predictions)

    @property
    def evaluation(self) -> dict:
        return deepcopy(self._evaluation)

    def weather(self, day: str) -> dict:
        if day not in self._predictions:
            raise ValueError("日期不在冻结2025回放范围内。")
        row = self._predictions[day]
        i = self._positions[day]
        radius = self._evaluation["interval"]["radius"]["heat_3d"]
        recent = self._rows[i - 6 : i + 1]
        return {
            "heat_point_c": row["heat_3d_selected"],
            "heat_lower_c": row["heat_3d_selected"] - radius,
            "heat_upper_c": row["heat_3d_selected"] + radius,
            "reference_balance_mm": sum(
                r["et0_fao_evapotranspiration"] - r["precipitation_sum"] for r in recent
            ),
            "heat_threshold_c": 35.0,
            "balance_threshold_mm": 15.0,
            "date": day,
            "source_kind": "PUBLIC_REANALYSIS_REPLAY",
            "source_sha256": self.binding,
            "retrieved_at": self._provenance["downloaded_at"],
        }

    def history(self, day: str) -> list[dict]:
        self.weather(day)
        i = self._positions[day]
        return [
            {
                "date": r["date"],
                "tmax": r["temperature_2m_max"],
                "rain": r["precipitation_sum"],
            }
            for r in self._rows[i - 13 : i + 1]
        ]

    def coverage(self) -> dict:
        record = json.loads(
            (self.root / "data/neighborhood/PROVENANCE.json").read_text(
                encoding="utf-8"
            )
        )
        return {
            "center_days": len(self._rows),
            "years": 11,
            "center_start": self._rows[0]["date"],
            "center_end": self._rows[-1]["date"],
            "historical_test_origins": len(self._predictions),
            "grids": record["unique_returned_grids"],
            "grid_day_rows": record["grid_day_rows"],
            "variables": 6,
            "real_field_labels": 0,
            "new_grid_model_fitted": False,
            "weather_source": "ERA5再分析；不是现场传感器或当时发布的业务预报",
            "synthetic_replay_cases": 10,
            "synthetic_input_variants": 13,
            "neighborhood_status": record["status"],
            "center_rows_differing_from_v1": record["center_rows_differing_from_v1"],
            "data_sha256": self._provenance["csv_sha256"],
            "neighborhood_sha256": record["csv_sha256"],
        }
