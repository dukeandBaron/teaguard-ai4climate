"""Transactional, append-only, content-checked local versions using stdlib SQLite."""

import hashlib
import json
import sqlite3
import threading
from contextlib import closing
from copy import deepcopy
from pathlib import Path

from .contracts import AppError, version_key


def content(record: dict) -> tuple[str, str]:
    body = {key: value for key, value in record.items() if key != "version_id"}
    raw = json.dumps(
        body, sort_keys=True, ensure_ascii=False, allow_nan=False, separators=(",", ":")
    )
    return raw, hashlib.sha256(raw.encode("utf-8")).hexdigest()


class RecordStore:
    def __init__(self, path: Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._write_lock = threading.RLock()
        with closing(self._connect()) as connection, connection:
            connection.execute(
                "CREATE TABLE IF NOT EXISTS records (sequence INTEGER PRIMARY KEY AUTOINCREMENT, version_id TEXT UNIQUE NOT NULL, content_sha256 TEXT NOT NULL, payload TEXT NOT NULL, parent_id TEXT REFERENCES records(version_id))"
            )

    def _connect(self):
        connection = sqlite3.connect(self.path, timeout=30)
        connection.execute("PRAGMA foreign_keys=ON")
        return connection

    @staticmethod
    def _decode(row):
        if row is None:
            raise AppError(
                "未找到前序记录，请选择已有版本或明确开始新记录。",
                code="RECORD_NOT_FOUND",
                status=404,
            )
        identifier, digest, payload = row
        try:
            record = json.loads(payload)
            if not isinstance(record, dict):
                raise TypeError("Record container must be an object")
            _, actual = content(record)
        except (TypeError, ValueError) as exc:
            raise AppError(
                "本机记录内容无法校验。", code="RECORD_INTEGRITY", status=409
            ) from exc
        if (
            digest != actual
            or record.get("version_id") != identifier
            or actual[:24] != identifier
        ):
            raise AppError(
                "本机记录内容校验失败，已停止使用该记录。",
                code="RECORD_INTEGRITY",
                status=409,
            )
        return record

    def save(self, result: dict) -> dict:
        record = deepcopy(result)
        _, digest = content(record)
        identifier = digest[:24]
        record["version_id"] = identifier
        payload = json.dumps(
            record,
            sort_keys=True,
            ensure_ascii=False,
            allow_nan=False,
            separators=(",", ":"),
        )
        lineage = record.get("lineage", [])
        parent = version_key(lineage[-1]) if lineage else None
        with self._write_lock, closing(self._connect()) as connection, connection:
            connection.execute("BEGIN IMMEDIATE")
            if parent:
                self._decode(
                    connection.execute(
                        "SELECT version_id,content_sha256,payload FROM records WHERE version_id=?",
                        (parent,),
                    ).fetchone()
                )
            connection.execute(
                "INSERT OR IGNORE INTO records(version_id,content_sha256,payload,parent_id) VALUES(?,?,?,?)",
                (identifier, digest, payload, parent),
            )
            saved = self._decode(
                connection.execute(
                    "SELECT version_id,content_sha256,payload FROM records WHERE version_id=?",
                    (identifier,),
                ).fetchone()
            )
            if saved != record:
                raise AppError(
                    "版本内容冲突，原记录已保留。", code="RECORD_CONFLICT", status=409
                )
        return saved

    def get(self, identifier: str) -> dict:
        identifier = version_key(identifier)
        with closing(self._connect()) as connection:
            return self._decode(
                connection.execute(
                    "SELECT version_id,content_sha256,payload FROM records WHERE version_id=?",
                    (identifier,),
                ).fetchone()
            )

    def list_recent(self, limit: int = 20) -> list[dict]:
        if (
            isinstance(limit, bool)
            or not isinstance(limit, int)
            or not 1 <= limit <= 100
        ):
            raise AppError("记录条数应为1至100。")
        with closing(self._connect()) as connection:
            rows = connection.execute(
                "SELECT version_id,content_sha256,payload FROM records ORDER BY sequence DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [self._decode(row) for row in rows]
