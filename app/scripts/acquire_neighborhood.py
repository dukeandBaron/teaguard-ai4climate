"""One bounded public ERA5 read for spatial references; no training or paid API."""

import csv
import hashlib
import json
import math
import urllib.parse
import urllib.request
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data/neighborhood"
FIELDS = [
    "temperature_2m_max",
    "temperature_2m_min",
    "precipitation_sum",
    "et0_fao_evapotranspiration",
    "shortwave_radiation_sum",
    "wind_speed_10m_max",
]


if __name__ == "__main__":
    OUT.mkdir(exist_ok=True)
    provenance = json.loads((ROOT / "data/PROVENANCE.json").read_text(encoding="utf-8"))
    center = provenance["requested_point"]
    points = [
        (round(center["latitude"] + dy, 3), round(center["longitude"] + dx, 3))
        for dy in (-0.25, 0, 0.25)
        for dx in (-0.25, 0, 0.25)
    ]
    args = {
        "latitude": ",".join(str(p[0]) for p in points),
        "longitude": ",".join(str(p[1]) for p in points),
        "start_date": "2015-01-01",
        "end_date": "2025-12-31",
        "daily": ",".join(FIELDS),
        "timezone": "Asia/Shanghai",
        "models": "era5",
    }
    url = "https://archive-api.open-meteo.com/v1/archive?" + urllib.parse.urlencode(
        args
    )
    receipt = {
        "url": url,
        "requested_points": points,
        "requested_models": "era5",
        "read_only": True,
        "training": False,
        "data_kind": "PUBLIC_REANALYSIS_SPATIAL_REFERENCE_NOT_FIELD_MEASUREMENT",
        "checked_utc": datetime.now(timezone.utc).isoformat(),
    }
    try:
        raw_path = OUT / "era5_neighborhood_2015_2025.json"
        if raw_path.exists():
            raw = raw_path.read_bytes()
            receipt["request_mode"] = "REUSED_FROZEN_LOCAL_RESPONSE"
        else:
            req = urllib.request.Request(
                url, headers={"User-Agent": "TeaGuard local research reference/0.2"}
            )
            with urllib.request.urlopen(req, timeout=40) as response:
                raw = response.read(16 * 1024 * 1024)
                receipt["http_status"] = response.status
            raw_path.write_bytes(raw)
            receipt["request_mode"] = "ONE_PUBLIC_GET"
        grids = json.loads(raw)
        if not isinstance(grids, list) or len(grids) != 9:
            raise ValueError("Expected nine explicit point responses")
        expected_dates = [
            (date(2015, 1, 1) + timedelta(days=i)).isoformat() for i in range(4018)
        ]
        records = []
        for i, grid in enumerate(grids):
            daily = grid["daily"]
            if daily["time"] != expected_dates:
                raise ValueError("Grid date coverage differs from frozen calendar")
            for field in FIELDS:
                if len(daily[field]) != 4018 or any(
                    v is None or not math.isfinite(v) for v in daily[field]
                ):
                    raise ValueError("Missing or nonfinite neighborhood data")
            for j, day in enumerate(expected_dates):
                records.append(
                    {
                        "grid_index": i,
                        "requested_latitude": points[i][0],
                        "requested_longitude": points[i][1],
                        "returned_latitude": grid["latitude"],
                        "returned_longitude": grid["longitude"],
                        "provider_elevation_m": grid.get("elevation"),
                        "date": day,
                        **{f: daily[f][j] for f in FIELDS},
                    }
                )
        csv_path = OUT / "weather_neighborhood.csv"
        with csv_path.open("w", encoding="utf-8", newline="") as stream:
            writer = csv.DictWriter(stream, fieldnames=list(records[0]))
            writer.writeheader()
            writer.writerows(records)
        with (ROOT / "data/weather_daily.csv").open(
            encoding="utf-8", newline=""
        ) as stream:
            original = list(csv.DictReader(stream))
        center_daily = grids[4]["daily"]
        differing = sum(
            any(abs(float(row[f]) - center_daily[f][j]) > 1e-8 for f in FIELDS)
            for j, row in enumerate(original)
        )
        receipt.update(
            status="PASS_PUBLIC_SPATIAL_REFERENCE",
            grid_responses=9,
            unique_returned_grids=len({(g["latitude"], g["longitude"]) for g in grids}),
            days_per_grid=4018,
            grid_day_rows=len(records),
            variables=FIELDS,
            raw_sha256=hashlib.sha256(raw).hexdigest(),
            csv_sha256=hashlib.sha256(csv_path.read_bytes()).hexdigest(),
            center_rows_differing_from_v1=differing,
            real_field_labels=0,
            license="Weather data by Open-Meteo.com; ERA5 by Copernicus/ECMWF; CC BY4.0",
            limit="Neighboring grids and consecutive dates are correlated; not independent plots or ground truth. Provider point elevation adjustments retained. V1 data and predictions were not replaced.",
        )
    except (OSError, ValueError, TypeError, KeyError, IndexError) as exc:
        receipt.update(
            status="PUBLIC_SPATIAL_REFERENCE_UNCONFIRMED",
            error=type(exc).__name__ + ": " + str(exc),
        )
    (OUT / "PROVENANCE.json").write_text(
        json.dumps(receipt, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(
        json.dumps(
            {
                k: v
                for k, v in receipt.items()
                if k not in ("url", "requested_points", "variables")
            },
            ensure_ascii=False,
            indent=2,
        )
    )
