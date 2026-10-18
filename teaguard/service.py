"""Evidence-bound scenario decisions. No generated agronomic measurements."""
import hashlib
import json
import math
from datetime import date, timedelta

from .model import FIELDS, ROOT, TeaModel, target

SCENARIOS = {
    "historical": {"label": "公开数据历史回放", "temp_delta": 0., "rain_multiplier": 1.},
    "hot_dry": {"label": "AI模拟：近期升温少雨", "temp_delta": 3., "rain_multiplier": .25},
    "wet": {"label": "AI模拟：近期凉湿", "temp_delta": -1., "rain_multiplier": 1.8},
}


def bounded_number(value, default, low, high):
    if value is None:
        return default
    if isinstance(value, bool):
        raise ValueError("阈值必须是数字")
    try:
        value = float(value)
    except (TypeError, ValueError):
        raise ValueError("阈值必须是数字") from None
    if not math.isfinite(value) or not low <= value <= high:
        raise ValueError(f"阈值范围为 {low}–{high}")
    return value


class TeaService:
    def __init__(self, rows):
        self.rows = rows
        self.model = TeaModel(rows)
        self.provenance = json.loads((ROOT / "data/PROVENANCE.json").read_text(encoding="utf-8"))
        actual_hash = hashlib.sha256((ROOT / "data/weather_daily.csv").read_bytes()).hexdigest()
        if actual_hash != self.provenance["csv_sha256"]:
            raise ValueError("天气CSV与来源凭据哈希不一致")
        self.positions = {r["date"]: i for i, r in enumerate(rows)}

    def analyze(self, args):
        if not isinstance(args, dict):
            raise ValueError("请求必须为JSON对象")
        day = args.get("date", "2025-07-15")
        if not isinstance(day, str):
            raise ValueError("请选择有效日期")
        lower, upper = self.model.report["test_origin_range"]
        if day not in self.positions or not lower <= day <= upper:
            raise ValueError(f"历史回放支持 {lower} 至 {upper}")
        scenario = args.get("scenario", "historical")
        if not isinstance(scenario, str) or scenario not in SCENARIOS:
            raise ValueError("未知模拟情景")
        soil = args.get("soil", "unknown")
        if not isinstance(soil, str) or soil not in ["unknown", "dry", "moist"]:
            raise ValueError("未知模拟墒情")
        heat_threshold = bounded_number(args.get("heat_threshold"), 35., 28., 42.)
        balance_threshold = bounded_number(args.get("balance_threshold"), 15., 5., 50.)
        idx = self.positions[day]
        altered = [dict(r) for r in self.rows[:idx+1]]
        settings = SCENARIOS[scenario]
        for row in altered[-14:]:
            for field in FIELDS[:2]:
                row[field] += settings["temp_delta"]
            row[FIELDS[2]] *= settings["rain_multiplier"]
        pred, explain = self.model.predict_index(idx, altered)
        hist = altered[-14:]
        reference_7d = sum(r[FIELDS[3]]-r[FIELDS[2]] for r in hist[-7:])
        rain_7d = sum(r[FIELDS[2]] for r in hist[-7:])
        et0_7d = sum(r[FIELDS[3]] for r in hist[-7:])
        thresholds = [heat_threshold, balance_threshold]
        outlook = []
        for j, name in enumerate(["未来3日最高气温", "未来7日参考水分收支"]):
            lo, hi = float(pred[j]-self.model.radius[j]), float(pred[j]+self.model.radius[j])
            state = "above" if lo >= thresholds[j] else "below" if hi < thresholds[j] else "uncertain"
            outlook.append({"name": name, "value": round(float(pred[j]),2), "lower": round(lo,2), "upper": round(hi,2), "threshold": thresholds[j], "status": state, "unit": "°C" if j == 0 else "mm", "horizon_days": 3 if j == 0 else 7, "method": self.model.selected[j], "used_for_actions": j == 0})
        heat_possible = outlook[0]["upper"] >= heat_threshold
        water_possible = reference_7d >= balance_threshold
        actions = []
        if heat_possible:
            actions.append({"id": "heat", "title": "优先在清晨巡查热暴露位置", "reason": f"3日气温区间上界 {outlook[0]['upper']}°C 达到情景阈值 {heat_threshold:g}°C；先核对当地预报与地块情况。", "window": "未来1–3日", "priority": "优先核查"})
            actions.append({"id": "shade", "title": "检查已有遮阴设施和人员作业安排", "reason": "气温展望支持提前排查；具体遮阴方式与作业时间由地块管理人员结合现场确认。", "window": "下一次作业前", "priority": "准备"})
        if water_possible:
            if soil == "moist":
                actions.append({"id": "soil", "title": "模拟墒情为湿润：先复查，保留人工判断", "reason": "参考气象收支与模拟现场条件不一致；优先复核土壤记录，当前不生成补水操作。", "window": "下一次巡查", "priority": "现场复核"})
            else:
                actions.append({"id": "soil", "title": "核对土壤墒情、叶片状态与供水条件", "reason": f"过去7日参考收支 {reference_7d:.1f}mm。ET₀−降雨不等于土壤缺水，须用现场记录确认。", "window": "未来24小时", "priority": "先测再决定"})
        if not actions:
            actions.append({"id": "routine", "title": "按常规频次巡查并关注天气更新", "reason": "当前区间未触发所选高温阈值；保留土壤和叶片记录，便于下一次复核。", "window": "常规安排", "priority": "观察"})
        actions.append({"id": "record", "title": "记录本次判断的依据和现场条件", "reason": "保存日期、所用数据、阈值及人工复核结果，让下次巡查可以追溯。", "window": "本次巡查后", "priority": "留存"})
        digest_input = {"date": day, "scenario": scenario, "soil": soil, "heat_threshold": heat_threshold, "balance_threshold": balance_threshold, "data_sha256": self.provenance["csv_sha256"]}
        return {
            "run_id": hashlib.sha256(json.dumps(digest_input,sort_keys=True).encode()).hexdigest()[:16],
            "date": day, "place": "梅家坞周边代表性网格", "scenario": scenario, "scenario_label": settings["label"],
            "evidence_kind": "PUBLIC_REANALYSIS_REPLAY" if scenario == "historical" else "AI_AUTHORED_INPUT_SENSITIVITY_SCENARIO",
            "scenario_assumptions": {**settings, "applies_to": "回放日前14天输入", "physical_climate_projection": False},
            "soil_simulation": soil, "outlook": outlook,
            "history": [{"date": r["date"], "tmax": r[FIELDS[0]], "rain": round(r[FIELDS[2]],2), "et0": r[FIELDS[3]]} for r in hist],
            "recent": {"rain_7d": round(rain_7d,1), "et0_7d": round(et0_7d,1), "balance_7d": round(reference_7d,1)},
            "verification": {"actual_targets": target(self.rows,idx).tolist(), "future_weather": [{"date":r["date"],"tmax":r[FIELDS[0]],"rain":r[FIELDS[2]]} for r in self.rows[idx+1:idx+8]]} if scenario == "historical" else None,
            "actions": actions, "explanations": explain,
            "boundaries": ["历史回放，不是今天的天气预报", "ERA5区域网格，不是茶园传感器测量", "参考收支不等于土壤含水量或灌溉剂量", "区间来自2024残差校准，时间序列覆盖率不作保证", "35°C和15mm为可调情景阈值，不是实测茶树损伤阈值"],
            "data_sha256": self.provenance["csv_sha256"],
        }
