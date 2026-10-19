"""Independent descriptive coverage audit. No fitting or new effectiveness score."""

import csv
import hashlib
import json
import statistics
from collections import defaultdict
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


if __name__ == "__main__":
    with (ROOT / "data/weather_daily.csv").open(encoding="utf-8", newline="") as stream:
        center = list(csv.DictReader(stream))
    dates = [r["date"] for r in center]
    assert dates == [
        (date(2015, 1, 1) + timedelta(days=i)).isoformat() for i in range(4018)
    ]
    grids = defaultdict(list)
    path = ROOT / "data/neighborhood/weather_neighborhood.csv"
    if path.is_file():
        with path.open(encoding="utf-8", newline="") as stream:
            for row in csv.DictReader(stream):
                grids[int(row["grid_index"])].append(row)
    correlations = {}
    central = [float(r["temperature_2m_max"]) for r in center]
    for key, rows in grids.items():
        assert [r["date"] for r in rows] == dates
        correlations[str(key)] = statistics.correlation(
            central, [float(r["temperature_2m_max"]) for r in rows]
        )
    yearly = {}
    for year in range(2015, 2026):
        rows = [r for r in center if r["date"].startswith(str(year))]
        values = [float(r["temperature_2m_max"]) for r in rows]
        yearly[str(year)] = {
            "days": len(rows),
            "mean_daily_max_c": statistics.mean(values),
            "grid_days_ge35c": sum(v >= 35 for v in values),
        }
    report = {
        "status": "PASS_DESCRIPTIVE_DATA_COVERAGE",
        "center_rows": len(center),
        "center_years": 11,
        "regional_grids": len(grids) or 1,
        "grid_day_rows": sum(len(v) for v in grids.values()) or len(center),
        "real_plot_soil_damage_yield_labels": 0,
        "independent_provider_families": 1,
        "daily_max_pearson_with_center": correlations,
        "yearly_center_summary": yearly,
        "weather_csv_sha256": hashlib.sha256(
            (ROOT / "data/weather_daily.csv").read_bytes()
        ).hexdigest(),
        "meaning": "Descriptive counts only. Spatial and temporal dependence is not corrected into a fictional effective independent sample size. No field diagnosis labels or operational forecast availability proof were added.",
        "recommendations": [
            "More regional grids add context, not measured plots",
            "For real weather prediction compare same-origin archived forecasts and simple correction first",
            "For agricultural damage models obtain corresponding cultivar/stage/soil/outcome labels; AI cases cannot replace them",
            "Keep2025 as already-inspected diagnostics for new designs",
        ],
        "training": False,
    }
    (ROOT / "data/DATA_AUDIT.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(
        json.dumps(
            {
                k: v
                for k, v in report.items()
                if k not in ("yearly_center_summary", "recommendations")
            },
            ensure_ascii=False,
            indent=2,
        )
    )
