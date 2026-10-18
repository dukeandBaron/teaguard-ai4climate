"""Fetch bounded public ERA5 weather; preserve raw response and provenance."""
import csv
import hashlib
import importlib.util
import json
import math
import sys
import urllib.request
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlencode

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw"
RAW.mkdir(parents=True, exist_ok=True)
FIELDS = ["temperature_2m_max", "temperature_2m_min", "precipitation_sum", "et0_fao_evapotranspiration", "shortwave_radiation_sum", "wind_speed_10m_max"]
PARAMS = dict(latitude=30.201, longitude=120.103, start_date="2015-01-01", end_date="2025-12-31", daily=",".join(FIELDS), timezone="Asia/Shanghai", models="era5")
URL = "https://archive-api.open-meteo.com/v1/archive?" + urlencode(PARAMS)
raw_path = RAW / "meijiawu_era5_2015_2025.json"
if raw_path.exists():
    raw = raw_path.read_bytes()
else:
    req = urllib.request.Request(URL, headers={"User-Agent": "TeaGuard-research-demo/0.1"})
    with urllib.request.urlopen(req, timeout=45) as response:
        raw = response.read(3_000_001)
    if len(raw) > 3_000_000:
        raise ValueError("bounded read exceeded")
    parsed = json.loads(raw)
    if parsed.get("error"):
        raise ValueError(parsed.get("reason"))
    raw_path.write_bytes(raw)
payload = json.loads(raw)
daily = payload["daily"]
days = daily["time"]
expected = (date(2025, 12, 31) - date(2015, 1, 1)).days + 1
assert len(days) == expected
rows = []
for i, day in enumerate(days):
    assert day == (date(2015, 1, 1) + timedelta(days=i)).isoformat(), "date gap"
    row = {"date": day}
    for field in FIELDS:
        value = daily[field][i]
        if value is None or isinstance(value, bool) or not math.isfinite(float(value)):
            raise ValueError(f"missing/nonfinite {day} {field}")
        row[field] = float(value)
    assert row[FIELDS[0]] >= row[FIELDS[1]]
    assert row["precipitation_sum"] >= 0 and row["et0_fao_evapotranspiration"] >= 0
    rows.append(row)
csv_path = ROOT / "data" / "weather_daily.csv"
with csv_path.open("w", encoding="utf-8", newline="") as f:
    writer = csv.DictWriter(f, fieldnames=["date", *FIELDS])
    writer.writeheader()
    writer.writerows(rows)
receipt = {
    "downloaded_at": datetime.now(timezone(timedelta(hours=8))).isoformat(),
    "url": URL, "provider": "Open-Meteo Historical Weather API", "model": "ERA5",
    "requested_point": {"latitude": 30.201, "longitude": 120.103, "role": "approximate Meijiawu representative point"},
    "returned_grid": {k: payload[k] for k in ["latitude", "longitude", "elevation", "timezone", "utc_offset_seconds"]},
    "data_kind": "PUBLIC_REANALYSIS_GRID_NOT_FIELD_SENSOR",
    "units": payload["daily_units"], "start": days[0], "end": days[-1], "rows": len(rows),
    "raw_sha256": hashlib.sha256(raw).hexdigest(),
    "csv_sha256": hashlib.sha256(csv_path.read_bytes()).hexdigest(),
    "license": "CC BY 4.0; Weather data by Open-Meteo.com, ERA5 by Copernicus/ECMWF",
    "license_url": "https://open-meteo.com/en/licence",
    "commercial_note": "Free API access used here for noncommercial research/demo; deployment must review provider terms",
    "dependencies_available": {name: importlib.util.find_spec(name) is not None for name in ["numpy", "sklearn", "pytest", "PIL", "playwright"]},
}
(ROOT / "data" / "PROVENANCE.json").write_text(json.dumps(receipt, ensure_ascii=False, indent=2), encoding="utf-8")
print(json.dumps(receipt, ensure_ascii=False, indent=2))
