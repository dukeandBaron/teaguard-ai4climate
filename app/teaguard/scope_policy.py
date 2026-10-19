"""Mechanism applicability across species, setting, treatment and endpoint."""

from copy import deepcopy


def _match_cards(ctx, cards, sources):
    matches = []
    expected = {
        "species": "Camellia sinensis",
        "cultivar": "Tieguanyin",
        "setting": "artificial_chamber",
        "treatment": "heat_or_PEG",
        "endpoint": "gene_expression",
    }
    for card in cards:
        key = card["card_id"]
        dims = {}
        applicability = "MATCH"
        reason = "支持信息组织与工程核查；不提供田间效果估计。"
        if key == "E02":
            dims = {
                name: "UNKNOWN"
                if ctx.get(name) in (None, "unknown")
                else "MATCH"
                if ctx.get(name) == value
                else "MISMATCH"
                for name, value in expected.items()
            }
            applicability = (
                "MATCH" if all(v == "MATCH" for v in dims.values()) else "PARTIAL"
            )
            reason = "铁观音受控高温/PEG处理的基因表达研究；保留物种、品种、环境、处理和测量终点边界。"
            if ctx["species"] != "Camellia sinensis":
                applicability = "MISMATCH"
                reason = "当前物种与茶树受控实验不同；保留原物种、品种与实验条件，不直接迁移结论。"
            elif ctx["requested_claim"] == "field_combined_damage":
                applicability = "MISMATCH"
                reason = "原文方法/图9不支持请求的田间联合胁迫定量结论，基因表达不是损伤或产量。"
        elif key == "E03":
            dims = {
                "species": "MATCH"
                if ctx["species"] == "Brassica napus"
                else "MISMATCH",
                "cultivar": "UNKNOWN",
                "setting": "MISMATCH" if ctx["setting"] == "field" else "UNKNOWN",
                "treatment": "MATCH"
                if ctx["treatment"] == "hydrogel_Ensifer_C5"
                else "MISMATCH",
                "endpoint": "MATCH"
                if ctx["endpoint"] == "original_root_response"
                else "MISMATCH",
            }
            applicability = "MISMATCH" if "MISMATCH" in dims.values() else "PARTIAL"
            reason = (
                "油菜—Ensifer C5—水凝胶及酸性土壤体系；不迁为茶园处理、剂量或增产结论。"
            )
        source_refs = [
            {
                "id": sid,
                "title": sources[sid]["title"],
                "url": sources[sid]["url"],
                "access": sources[sid].get("access"),
            }
            for sid in card["source_ids"]
        ]
        matches.append(
            {
                "card_id": key,
                "input_ids": [
                    "weather_heat",
                    "weather_balance",
                    "factor_soil",
                    "factor_cultivar",
                ],
                "applicability": applicability,
                "reason": reason,
                "dimension_checks": dims,
                "conditions": deepcopy(card["conditions"]),
                "source_anchor": card["source_anchor"],
                "sources": source_refs,
                "supports": card["supports"],
                "does_not_support": card["does_not_support"],
                "action_evidence_class": card["action_evidence_class"],
            }
        )
    return matches
