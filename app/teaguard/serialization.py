"""Deterministic JSON identity shared by the domain policies."""

import hashlib
import json


def stable_hash(value):
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, ensure_ascii=False, allow_nan=False).encode(
            "utf-8"
        )
    ).hexdigest()
