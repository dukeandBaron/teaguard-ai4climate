"""HTTP adapter: route, validate transport, translate errors, log request outcomes."""

import hashlib
import json
import logging
import threading
import time
import uuid
from http.server import BaseHTTPRequestHandler
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from .contracts import AppError
from .nature import ENGINE_DIGEST
from .nature_service import VERSION

ROOT = Path(__file__).resolve().parents[1]
MAX_BODY_BYTES = 262144
LOG_LOCK = threading.Lock()
LOGGER = logging.getLogger(__name__)
ASSETS = {"/": (ROOT / "web/index.html").read_bytes()}
ASSETS.update(
    {
        "/" + p.name: p.read_bytes()
        for p in (ROOT / "web").iterdir()
        if p.suffix in (".js", ".css")
    }
)
SOURCE_PATHS = [
    ROOT / "nature_server.py",
    *sorted((ROOT / "teaguard").glob("*.py")),
    *sorted((ROOT / "web").glob("*")),
]
SOURCE_PATHS += [
    ROOT / name
    for name in (
        "data/mechanism_cards.json",
        "data/nature_state_schema.json",
        "data/project_status.json",
        "research/SOURCE_REGISTER.json",
        "data/weather_daily.csv",
        "data/PROVENANCE.json",
        "artifacts/test_predictions.json",
        "artifacts/evaluation.json",
    )
]
STARTUP_SOURCES = {
    p.relative_to(ROOT).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
    for p in SOURCE_PATHS
    if p.is_file()
}


def health():
    return {
        "status": "ok",
        "version": VERSION,
        "model_fit": False,
        "name": "茶候 · 自然情境",
        "engine_sha256": ENGINE_DIGEST,
        "startup_sources": STARTUP_SOURCES,
        "storage": "sqlite_content_checked",
    }


def make_handler(service):
    class Handler(BaseHTTPRequestHandler):
        def dispatch(self, method):
            self.request_id = uuid.uuid4().hex[:16]
            self.started = time.monotonic()
            try:
                self.route(method)
            except AppError as exc:
                self.send(
                    {
                        "error": str(exc),
                        "code": exc.code,
                        "request_id": self.request_id,
                    },
                    status=exc.status,
                )
            except (
                ValueError,
                TypeError,
                UnicodeError,
                KeyError,
                RecursionError,
            ) as exc:
                self.send(
                    {
                        "error": str(exc),
                        "code": "INVALID_INPUT",
                        "request_id": self.request_id,
                    },
                    status=400,
                )
            except (BrokenPipeError, ConnectionResetError):
                LOGGER.info("Client disconnected: %s", self.request_id)
            except Exception:
                LOGGER.exception("Unhandled local request %s", self.request_id)
                self.send(
                    {
                        "error": "本机请求未完成，请保留请求编号后重试。",
                        "code": "INTERNAL_ERROR",
                        "request_id": self.request_id,
                    },
                    status=500,
                )

        def send(self, data, mime="application/json; charset=utf-8", status=200):
            raw = (
                json.dumps(data, ensure_ascii=False, allow_nan=False).encode()
                if isinstance(data, (dict, list))
                else data
            )
            self.send_response(status)
            for name, value in {
                "Content-Type": mime,
                "Content-Length": str(len(raw)),
                "Cache-Control": "no-store",
                "X-Content-Type-Options": "nosniff",
                "X-Request-ID": self.request_id,
                "Content-Security-Policy": "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'",
            }.items():
                self.send_header(name, value)
            self.end_headers()
            self.wfile.write(raw)
            event = {
                "request_id": self.request_id,
                "method": self.command,
                "path": urlparse(self.path).path,
                "status": status,
                "duration_ms": round((time.monotonic() - self.started) * 1000, 2),
            }
            try:
                with (
                    LOG_LOCK,
                    (ROOT / "runtime/requests.jsonl").open(
                        "a", encoding="utf-8"
                    ) as stream,
                ):
                    stream.write(json.dumps(event) + "\n")
            except OSError:
                LOGGER.exception("Could not write request diagnostic")

        def read_json(self):
            if self.headers.get("Origin") not in (
                None,
                f"http://127.0.0.1:{self.server.server_port}",
                f"http://localhost:{self.server.server_port}",
            ):
                raise AppError("请求来源不匹配。", code="ORIGIN_MISMATCH", status=403)
            if self.headers.get("Content-Type", "").split(";")[0] != "application/json":
                raise AppError("请使用JSON请求。", code="CONTENT_TYPE", status=415)
            length = int(self.headers.get("Content-Length", "0"))
            if not 0 < length <= MAX_BODY_BYTES:
                raise AppError(
                    "请求大小应为1至262144字节。", code="BODY_SIZE", status=413
                )
            self.connection.settimeout(5)

            def reject_constant(value):
                raise ValueError("不接受非有限JSON数值：" + value)

            return json.loads(self.rfile.read(length), parse_constant=reject_constant)

        def route(self, method):
            path = urlparse(self.path).path
            if method == "POST":
                if path not in ("/api/analyze", "/api/feedback"):
                    raise AppError("接口不存在。", code="NOT_FOUND", status=404)
                payload = self.read_json()
                return self.send(
                    service.analyze(payload)
                    if path == "/api/analyze"
                    else service.feedback(payload)
                )
            if path == "/api/health":
                return self.send(health())
            if path == "/api/bootstrap":
                return self.send(service.bootstrap())
            if path == "/api/records":
                return self.send({"records": service.list_records()})
            if path == "/api/record":
                identifier = parse_qs(urlparse(self.path).query).get(
                    "version_id", [None]
                )[0]
                return self.send(service.get_record(identifier))
            if path == "/api/project-status":
                return self.send(service.project_status)
            if path == "/api/replay-summary":
                return self.send(
                    {k: v for k, v in service.replay.items() if k != "outputs"}
                )
            if path not in ASSETS:
                raise AppError("页面不存在。", code="NOT_FOUND", status=404)
            mime = (
                "text/javascript"
                if path.endswith(".js")
                else "text/css"
                if path.endswith(".css")
                else "text/html"
            )
            return self.send(ASSETS[path], mime + "; charset=utf-8")

        def do_GET(self):
            self.dispatch("GET")

        def do_POST(self):
            self.dispatch("POST")

        def log_message(self, format, *args):
            return

    return Handler
