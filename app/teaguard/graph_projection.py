"""Project domain evidence and inspection tasks into a typed display graph."""

import json


def _graph(state, matches, tasks, conflict):
    nodes = [
        {
            "id": "region",
            "label": "区域天气",
            "kind": "region",
            "detail": "区域网格参照，不是地块传感器。",
        },
        {
            "id": "plot",
            "label": "模拟地块情境",
            "kind": "plot",
            "detail": "地块条件由AI情境声明，未知项不自动补齐。",
        },
    ]
    edges = [
        {
            "source": "region",
            "target": "plot",
            "relation": "REGIONAL_REFERENCE",
            "label": "区域参照",
        }
    ]
    for f in state["context_factors"]:
        label = {
            "SOIL_MOISTURE_DESCRIPTION": "土壤反馈",
            "SHADE_STATUS": "遮阴条件",
            "GROWTH_STAGE": "生长阶段",
            "CULTIVAR": "品种",
        }[f["factor"]]
        nodes.append(
            {
                "id": f["id"],
                "label": label,
                "kind": "observation",
                "detail": json.dumps(f, ensure_ascii=False),
            }
        )
        edges.append(
            {
                "source": f["id"],
                "target": "plot",
                "relation": "DECLARED_CONTEXT",
                "label": "情境条件",
            }
        )
    for match in matches:
        nodes.append(
            {
                "id": match["card_id"],
                "label": match["card_id"]
                + " · "
                + {
                    "E01": "风险结构",
                    "E02": "茶树实验",
                    "E03": "跨物种边界",
                    "E04": "尺度与模态",
                    "E05": "来源与版本",
                }[match["card_id"]],
                "kind": "evidence",
                "status": match["applicability"],
                "detail": match["reason"],
            }
        )
    for task in tasks:
        nodes.append(
            {
                "id": task["task_id"],
                "label": task["title"],
                "kind": "task",
                "status": task["status"],
                "detail": task["next_check"],
            }
        )
        edges.append(
            {
                "source": "plot",
                "target": task["task_id"],
                "relation": "REQUIRES_CHECK",
                "label": "待核查",
            }
        )
        for cid in task["evidence_card_ids"]:
            if any(m["card_id"] == cid for m in matches):
                edges.append(
                    {
                        "source": cid,
                        "target": task["task_id"],
                        "relation": "SUPPORTS_CHECKLIST",
                        "label": "核查依据",
                    }
                )
    if conflict:
        edges.append(
            {
                "source": "region",
                "target": "factor_soil",
                "relation": "CONFLICTS_WITH",
                "label": "条件待对齐",
            }
        )
    for edge in edges:
        edge["causal_effect_measured"] = False
    return {
        "nodes": nodes,
        "edges": edges,
        "meaning": "可追溯关系图；未训练图神经网络，也不表示测得因果效应。",
    }
