"""Derive a runtime schema without modifying the research design contract."""

import json
from copy import deepcopy
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
schema = json.loads(
    (ROOT / "research/NATURE_STATE_SCHEMA.json").read_text(encoding="utf-8")
)
schema = deepcopy(schema)
schema["$id"] = "urn:teaguard:runtime:nature-state:0.2"
schema["title"] = "TeaGuard local nature context runtime"
schema["description"] = (
    "Local historical/simulation context; no physiological causal model or operational forecast claim."
)
schema["x-design-status"] = "RUNTIME_IMPLEMENTED_LOCAL_V2"
schema["properties"]["schema_version"] = {"const": "0.2"}
schema["required"].append("organism_context")
schema["properties"]["organism_context"] = {
    "type": "object",
    "additionalProperties": False,
    "required": ["species", "cultivar", "setting", "treatment", "endpoint"],
    "properties": {
        key: {"type": ["string", "null"]}
        for key in ["species", "cultivar", "setting", "treatment", "endpoint"]
    },
}
schema["$defs"]["observation"]["properties"]["depth_cm"] = {
    "type": ["number", "null"],
    "minimum": 0,
    "maximum": 300,
}
tasks = schema["properties"]["review_tasks"]["items"]
for field in ("focus", "title", "rule_id"):
    tasks["properties"][field] = {"type": "string", "minLength": 1}
    tasks["required"].append(field)
(ROOT / "data/nature_state_schema.json").write_text(
    json.dumps(schema, ensure_ascii=False, indent=2), encoding="utf-8"
)
print("Runtime schema0.2 generated; research schema preserved")
