"""Causal features, purged chronological evaluation and transparent baselines."""
from __future__ import annotations

import csv
import hashlib
import json
import math
from datetime import date, timedelta
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
FIELDS = ["temperature_2m_max", "temperature_2m_min", "precipitation_sum", "et0_fao_evapotranspiration", "shortwave_radiation_sum", "wind_speed_10m_max"]
TARGETS = ["heat_3d", "balance_7d"]


def load_weather(path: Path | None = None) -> list[dict]:
    with (path or ROOT / "data/weather_daily.csv").open(encoding="utf-8", newline="") as stream:
        rows = [{"date": r["date"], **{k: float(r[k]) for k in FIELDS}} for r in csv.DictReader(stream)]
    for i, row in enumerate(rows):
        day = date.fromisoformat(row["date"])
        if i and day != date.fromisoformat(rows[i-1]["date"]) + timedelta(days=1):
            raise ValueError("weather data has a date gap")
        if not all(math.isfinite(row[k]) for k in FIELDS):
            raise ValueError("weather data has a nonfinite value")
        if row[FIELDS[0]] < row[FIELDS[1]] or row[FIELDS[2]] < 0 or row[FIELDS[3]] < 0:
            raise ValueError("invalid physical weather value")
    return rows


def day_phase(day: str) -> float:
    parsed = date.fromisoformat(day)
    return ((parsed - date(parsed.year, 1, 1)).days / (366 if parsed.year % 4 == 0 else 365)) * 2 * math.pi


def features(rows: list[dict], index: int) -> tuple[np.ndarray, list[str]]:
    if index < 13 or index >= len(rows):
        raise ValueError("14 days of history required")
    phase = day_phase(rows[index]["date"])
    vals, names = [], []
    for k in (1, 2, 3):
        vals.extend([math.sin(k*phase), math.cos(k*phase)])
        names.extend([f"season_sin_{k}", f"season_cos_{k}"])
    for field in FIELDS:
        for lag in (0, 1, 2, 3, 6, 13):
            vals.append(rows[index-lag][field])
            names.append(f"{field}_lag{lag}")
        for window in (3, 7, 14):
            arr = [r[field] for r in rows[index-window+1:index+1]]
            vals.extend([float(np.mean(arr)), float(np.std(arr))])
            names.extend([f"{field}_mean{window}", f"{field}_std{window}"])
    for window in (3, 7, 14):
        hist = rows[index-window+1:index+1]
        vals.extend([sum(r[FIELDS[3]]-r[FIELDS[2]] for r in hist), sum(r[FIELDS[2]] < 1 for r in hist)])
        names.extend([f"reference_balance_{window}", f"dry_day_count_{window}"])
    return np.array(vals, dtype=float), names


def target(rows: list[dict], index: int) -> np.ndarray:
    if index+7 >= len(rows):
        raise ValueError("future labels incomplete")
    return np.array([max(r[FIELDS[0]] for r in rows[index+1:index+4]), sum(r[FIELDS[3]]-r[FIELDS[2]] for r in rows[index+1:index+8])])


def split_name(origin: str, label_end: str) -> str:
    for name, start, end in [("train", "2015-01-01", "2021-12-31"), ("validation", "2022-01-01", "2023-12-31"), ("calibration", "2024-01-01", "2024-12-31"), ("test", "2025-01-01", "2025-12-31")]:
        if start <= origin and label_end <= end and origin <= end:
            return name
    return "purged"


def persistence(rows: list[dict], index: int) -> np.ndarray:
    return np.array([rows[index][FIELDS[0]], sum(r[FIELDS[3]]-r[FIELDS[2]] for r in rows[index-6:index+1])])


def fit_ridge(x: np.ndarray, y: np.ndarray, alpha: float) -> dict:
    mean, scale = x.mean(axis=0), x.std(axis=0)
    scale[scale < 1e-8] = 1
    z = (x-mean)/scale
    center = y.mean(axis=0)
    coef = np.linalg.solve(z.T@z + np.eye(z.shape[1])*alpha, z.T@(y-center))
    return {"mean": mean, "scale": scale, "coef": coef, "center": center}


def ridge_predict(model: dict, x: np.ndarray) -> np.ndarray:
    return ((x-model["mean"])/model["scale"]) @ model["coef"] + model["center"]


def seasonal_predict(train_phases: np.ndarray, train_y: np.ndarray, phase: float) -> np.ndarray:
    dist = np.abs(np.angle(np.exp(1j*(train_phases-phase))))
    return train_y[dist <= 2*math.pi*15/365].mean(axis=0)


def metrics(y: np.ndarray, pred: np.ndarray, threshold: float) -> dict:
    actual, issued = y >= threshold, pred >= threshold
    tp, fp, fn = int(np.sum(actual & issued)), int(np.sum(~actual & issued)), int(np.sum(actual & ~issued))
    return {"mae": float(np.abs(y-pred).mean()), "rmse": float(np.sqrt(np.mean((y-pred)**2))), "rows": len(y), "threshold": threshold, "events": int(actual.sum()), "true_positive": tp, "false_positive": fp, "false_negative": fn, "precision": tp/(tp+fp) if tp+fp else None, "recall": tp/(tp+fn) if tp+fn else None}


class TeaModel:
    def __init__(self, rows: list[dict]):
        self.rows = rows
        self.indices = list(range(13, len(rows)-7))
        self.x = np.array([features(rows, i)[0] for i in self.indices])
        self.y = np.array([target(rows, i) for i in self.indices])
        self.phases = np.array([day_phase(rows[i]["date"]) for i in self.indices])
        self.splits = np.array([split_name(rows[i]["date"], rows[i+7]["date"]) for i in self.indices])
        tr, va, ca, te = [self.splits == k for k in ("train", "validation", "calibration", "test")]
        if min(int(s.sum()) for s in [tr, va, ca, te]) < 300:
            raise ValueError("insufficient chronological evaluation coverage")
        p = np.array([persistence(rows, i) for i in self.indices])
        seasonal_val = np.array([seasonal_predict(self.phases[tr], self.y[tr], phase) for phase in self.phases[va]])
        candidates = {"persistence": p[va], "seasonal": seasonal_val}
        for alpha in [1., 10., 100., 1000.]:
            candidates[f"ridge_{int(alpha)}"] = ridge_predict(fit_ridge(self.x[tr], self.y[tr], alpha), self.x[va])
        losses = {name: np.abs(pred-self.y[va]).mean(axis=0).tolist() for name, pred in candidates.items()}
        self.selected = [min(losses, key=lambda name: losses[name][j]) for j in range(2)]
        self.fit_mask = tr | va
        self.models = {alpha: fit_ridge(self.x[self.fit_mask], self.y[self.fit_mask], alpha) for alpha in [1., 10., 100., 1000.]}
        calpred = np.array([self.predict_index(i)[0] for i, flag in zip(self.indices, ca) if flag])
        errors = np.abs(calpred-self.y[ca])
        quantile = min(1., math.ceil((len(errors)+1)*.9)/len(errors))
        self.radius = np.quantile(errors, quantile, axis=0, method="higher")
        testpred = np.array([self.predict_index(i)[0] for i, flag in zip(self.indices, te) if flag])
        testseasonal = np.array([seasonal_predict(self.phases[self.fit_mask], self.y[self.fit_mask], phase) for phase in self.phases[te]])
        coverage = np.mean(np.abs(testpred-self.y[te]) <= self.radius, axis=0)
        thresholds = [35., 15.]
        self.report = {
            "evaluation_kind": "PUBLIC_REANALYSIS_RETROSPECTIVE_NOT_OPERATIONAL_FORECAST",
            "split_counts": {k: int(np.sum(self.splits == k)) for k in ["train", "validation", "calibration", "test", "purged"]},
            "protocol": "train2015-2021; select on2022-2023 MAE; refit through2023; residual calibration2024; untouched2025 test; all7-day labels purged at split boundaries",
            "feature_count": self.x.shape[1], "validation_mae": losses, "selected_by_target": dict(zip(TARGETS, self.selected)),
            "interval": {"method": "2024 absolute-residual finite-sample 90% quantile; temporal dependence means no exchangeability coverage guarantee", "radius": dict(zip(TARGETS, self.radius.tolist())), "test_coverage": dict(zip(TARGETS, coverage.tolist()))},
            "test_metrics": {},
            "test_origin_range": [rows[i]["date"] for i in [self.indices[np.flatnonzero(te)[0]], self.indices[np.flatnonzero(te)[-1]]]],
            "model_freeze_before_test": "2023-12-31 fitted parameters; 2024 residual calibration only",
        }
        for j, name in enumerate(TARGETS):
            self.report["test_metrics"][name] = {"selected": metrics(self.y[te,j], testpred[:,j], thresholds[j]), "persistence": metrics(self.y[te,j], p[te,j], thresholds[j]), "seasonal": metrics(self.y[te,j], testseasonal[:,j], thresholds[j])}
        self.report["screening_policy"] = {"rule": "heat point estimate + fixed2024 residual radius >= user threshold; triggers verification, not automated operation", "heat_35C_test": metrics(self.y[te,0], testpred[:,0]+self.radius[0], 35.)}
        self.report["product_admission"] = {"heat_3d": "RETROSPECTIVE_SCREENING_WITH_INTERVAL_AND_MANUAL_REVIEW", "balance_7d": "EXPLORATORY_ONLY_NOT_USED_FOR_ACTIONS", "balance_reason": "2025 held-out threshold recall is zero and MAE does not beat seasonal baseline; retain failure, do not retune against test", "recent_balance": "Observed public reanalysis ET0-minus-rain summary used only to request field verification"}
        self.prediction_rows = [{"origin": rows[i]["date"], "label_end": rows[i+7]["date"], "split": "test", **{f"{name}_{key}": float(arr[j]) for j, name in enumerate(TARGETS) for key, arr in [("actual", target(rows,i)), ("selected", testpred[n]), ("persistence", p[te][n]), ("seasonal", testseasonal[n])]}} for n, i in enumerate(np.array(self.indices)[te])]

    def predict_index(self, index: int, rows: list[dict] | None = None) -> tuple[np.ndarray, list[dict]]:
        rows = rows if rows is not None else self.rows
        x, names = features(rows, index)
        values, explanations = [], []
        for j, selected in enumerate(self.selected):
            if selected == "persistence":
                values.append(persistence(rows,index)[j])
                explanations.append({"method": selected, "drivers": [{"feature": "recent_weather", "contribution": float(values[-1])}]})
            elif selected == "seasonal":
                values.append(seasonal_predict(self.phases[self.fit_mask], self.y[self.fit_mask], day_phase(rows[index]["date"]))[j])
                explanations.append({"method": selected, "drivers": [{"feature": "historical_seasonal_mean", "contribution": float(values[-1])}]})
            else:
                m = self.models[float(selected.split("_")[1])]
                values.append(ridge_predict(m, x)[j])
                contributions = ((x-m["mean"])/m["scale"]) * m["coef"][:,j]
                top = np.argsort(np.abs(contributions))[-5:][::-1]
                explanations.append({"method": selected, "intercept": float(m["center"][j]), "drivers": [{"feature": names[k], "contribution": float(contributions[k])} for k in top], "interpretation": "linear feature contributions, not causal effects"})
        return np.array(values), explanations

    def save_report(self) -> None:
        out = ROOT / "artifacts"
        out.mkdir(exist_ok=True)
        report = {**self.report, "weather_csv_sha256": hashlib.sha256((ROOT / "data/weather_daily.csv").read_bytes()).hexdigest()}
        (out / "evaluation.json").write_text(json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False), encoding="utf-8")
        (out / "test_predictions.json").write_text(json.dumps(self.prediction_rows, ensure_ascii=False, indent=2, allow_nan=False), encoding="utf-8")


if __name__ == "__main__":
    model = TeaModel(load_weather())
    model.save_report()
    print(json.dumps(model.report, ensure_ascii=False, indent=2, allow_nan=False))
