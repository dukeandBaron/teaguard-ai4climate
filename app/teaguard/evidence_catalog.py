"""Freeze the evidence bundle and source registry together for one process."""

import hashlib
import json
from copy import deepcopy
from pathlib import Path


class EvidenceCatalog:
    def __init__(self, root: Path):
        names = (
            "data/mechanism_cards.json",
            "research/SOURCE_REGISTER.json",
            "data/nature_state_schema.json",
        )
        raw = {name: (root / name).read_bytes() for name in names}
        self.manifest = {
            name: hashlib.sha256(value).hexdigest() for name, value in raw.items()
        }
        self._cards = json.loads(raw[names[0]])["cards"]
        self._sources = {s["id"]: s for s in json.loads(raw[names[1]])["sources"]}
        if len(self._cards) != 5 or len({c["card_id"] for c in self._cards}) != 5:
            raise ValueError("Expected five distinct mechanism cards")
        for card in self._cards:
            if any(source not in self._sources for source in card["source_ids"]):
                raise ValueError("Unresolved mechanism source")

    def read(self) -> tuple[list[dict], dict]:
        return deepcopy(self._cards), deepcopy(self._sources)
