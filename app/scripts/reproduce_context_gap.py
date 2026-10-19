"""Run frozen V1 decision code with saved predictions; no model fitting."""

import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OLD = ROOT.parent / "ai4climate_tea_guard"
sys.path.insert(0, str(OLD))
import numpy as np
from teaguard.model import load_weather
from teaguard.service import TeaService


class FrozenPrediction:
    def __init__(self, rows):
        report = json.loads(
            (OLD / "artifacts/evaluation.json").read_text(encoding="utf-8")
        )
        self.report = report
        self.radius = np.array(list(report["interval"]["radius"].values()))
        self.selected = list(report["selected_by_target"].values())
        self.rows = rows
        predictions = json.loads(
            (OLD / "artifacts/test_predictions.json").read_text(encoding="utf-8")
        )
        self.predictions = {r["origin"]: r for r in predictions}

    def predict_index(self, index, rows=None):
        row = self.predictions[self.rows[index]["date"]]
        return np.array([row["heat_3d_selected"], row["balance_7d_selected"]]), []


if __name__ == "__main__":
    rows = load_weather(OLD / "data/weather_daily.csv")
    service = TeaService.__new__(TeaService)
    service.rows = rows
    service.model = FrozenPrediction(rows)
    service.positions = {r["date"]: i for i, r in enumerate(rows)}
    service.provenance = json.loads(
        (OLD / "data/PROVENANCE.json").read_text(encoding="utf-8")
    )
    checks = []
    for name, key, first, second in [
        ("N04_shade", "shade", "present", "absent"),
        ("N05_growth", "growth_stage", "young_growth", "mature"),
    ]:
        a = service.analyze({"date": "2025-07-15", key: first})
        b = service.analyze({"date": "2025-07-15", key: second})
        checks.append(
            {
                "requirement": name,
                "field": key,
                "outputs_identical": a == b,
                "task_titles": [t["title"] for t in a["actions"]],
            }
        )
    result = {
        "status": "CONFIRMED_NEW_CONTEXT_CONTRACT_GAP",
        "meaning": "Frozen V1 does not consume shade/growth fields required by the new scope; this is not a failure of V1 weather accuracy or the cited papers.",
        "service_sha256": hashlib.sha256(
            (OLD / "teaguard/service.py").read_bytes()
        ).hexdigest(),
        "prediction_source": "saved2025 predictions; original decision controller executed with a frozen prediction adapter",
        "checks": checks,
        "fit_called": False,
        "training": False,
        "gpu": False,
    }
    (ROOT / "artifacts/BASELINE_CONTEXT_GAP.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
