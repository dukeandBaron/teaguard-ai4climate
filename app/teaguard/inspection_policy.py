"""Explicit inspection rules; no agricultural dose or benefit prediction."""

from .serialization import stable_hash


def _tasks(state, ctx, weather, policy):
    tasks = []
    place = state["spatial_context"]["name"]
    window = weather["date"]
    heat = weather["heat_upper_c"] >= weather["heat_threshold_c"]
    full = policy == "full"

    def add(
        focus, title, why, task_type="CHECK_CONTEXT", inputs=None, cards=None, rule=None
    ):
        key = stable_hash([place, window, task_type, focus])[:20]
        tasks.append(
            {
                "task_id": "task_" + key,
                "task_type": task_type,
                "basis_input_ids": inputs or ["weather_heat"],
                "evidence_card_ids": cards if policy != "weather_rules" else [],
                "status": "PROPOSED",
                "proposal_basis": "ENGINEERING_CHECKLIST",
                "next_check": why,
                "deduplication_key": key,
                "previous_version_id": None,
                "focus": focus,
                "title": title,
                "rule_id": rule or "R_" + focus.upper(),
            }
        )

    if heat:
        add(
            "heat",
            "核对区域高温线索与现场热暴露",
            "区域估计仅支持复核线索；核对当地预报、位置和作业时段。",
            "REVIEW_HEAT",
            cards=["E01", "E04"],
        )
    if policy == "weather_rules":
        if weather["reference_balance_mm"] >= weather["balance_threshold_mm"]:
            add(
                "water_reference",
                "核对参考气象收支",
                "参考收支不是土壤含水量，结合现场记录。",
                inputs=["weather_balance"],
                cards=[],
            )
        return tasks
    if not full:
        add(
            "source_scope",
            "核对资料适用范围",
            "对照作物、实验环境和测量终点，不跨场景推断。",
            cards=["E02", "E03", "E05"],
        )
        return tasks
    soil = ctx["soil"]
    if soil is None:
        add(
            "request_soil",
            "补充土壤状态与记录方法",
            "目前土壤状态未知；先记录时间、位置、深度与观察方式。",
            inputs=["factor_soil"],
            cards=["E01", "E04"],
        )
    elif (
        soil == "moist"
        and weather["reference_balance_mm"] >= weather["balance_threshold_mm"]
    ):
        add(
            "reconcile_soil",
            "复核气象线索与湿润土壤反馈的差异",
            "保留两条信息，先核对时间、位置、土层和记录方法，不平均为一个干旱分数。",
            "RECONCILE_CONFLICT",
            ["weather_balance", "obs_soil"],
            ["E04", "E05"],
        )
    elif soil == "dry":
        add(
            "verify_soil_method",
            "核对偏干反馈的时间、位置和方法",
            "描述性反馈不能单独诊断根区缺水，也不能给出灌溉剂量。",
            inputs=["obs_soil"],
            cards=["E01", "E04"],
        )
        if heat:
            add(
                "joint_context_review",
                "联合核查热与水分条件",
                "这是待核查的情境假设；不输出联合损伤、产量或灌溉量。",
                inputs=["weather_heat", "obs_soil"],
                cards=["E01", "E02"],
            )
    if ctx["shade"] == "present":
        add(
            "shade_coverage",
            "核对遮阴覆盖位置与时段",
            "记录实际覆盖范围；不假定遮阴降低多少摄氏度。",
            inputs=["factor_shade"],
            cards=["E01", "E04"],
        )
    elif ctx["shade"] == "absent":
        add(
            "exposed_position",
            "标记需复核的无遮阴位置",
            "核对暴露位置和作业安排；当前没有地块温差测量。",
            inputs=["factor_shade"],
            cards=["E01", "E04"],
        )
    else:
        add(
            "request_shade",
            "补充遮阴与暴露条件",
            "遮阴状态未知；核对覆盖位置和时段后再判断。",
            inputs=["factor_shade"],
            cards=["E01", "E04"],
        )
    if ctx["growth_stage"] == "unknown":
        add(
            "request_stage",
            "补充品种与生长阶段",
            "品种/阶段未知时，不套用其它实验的敏感性系数。",
            inputs=["factor_growth_stage", "factor_cultivar"],
            cards=["E02"],
        )
    elif ctx["growth_stage"] == "young_growth":
        add(
            "verify_growth_stage",
            "核对嫩梢阶段与品种记录",
            "保留生长阶段情境；文献基因表达不换算成田间损伤阈值。",
            inputs=["factor_growth_stage", "factor_cultivar"],
            cards=["E02"],
        )
    else:
        add(
            "record_stage",
            "保留成熟阶段与品种记录",
            "当前阶段与证据条件分别保存，不添加未测的耐受系数。",
            inputs=["factor_growth_stage", "factor_cultivar"],
            cards=["E02"],
        )
    if ctx["requested_claim"] != "context_review":
        add(
            "source_claim_check",
            "核对所请求结论与论文方法",
            "该来源不支持直接田间处理或联合损伤定量结论；回到方法与测量终点。",
            "CHECK_DATA_PROVENANCE",
            cards=["E03"]
            if ctx["requested_claim"] == "hydrogel_treatment"
            else ["E02"],
        )
    return list({t["deduplication_key"]: t for t in tasks}.values())
