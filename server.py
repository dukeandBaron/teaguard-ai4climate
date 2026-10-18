"""Loopback-only standalone TeaGuard web application."""
from __future__ import annotations

import argparse
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

from teaguard.model import ROOT, load_weather
from teaguard.service import TeaService


def make_handler(service):
    class Handler(BaseHTTPRequestHandler):
        def send_bytes(self, content, content_type, status=200):
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(content)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Content-Security-Policy", "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'")
            self.end_headers()
            if self.command != "HEAD":
                self.wfile.write(content)

        def send_json(self, payload, status=200):
            self.send_bytes(json.dumps(payload,ensure_ascii=False,allow_nan=False).encode(),"application/json; charset=utf-8",status)

        def do_HEAD(self):
            self.do_GET()

        def do_GET(self):
            path = urlparse(self.path).path
            if path == "/api/health":
                return self.send_json({"status":"ok","name":"茶候 TeaGuard","mode":"historical_replay","version":"0.1.0"})
            if path == "/api/bootstrap":
                return self.send_json({"default":service.analyze({}),"evaluation":service.model.report,"provenance":service.provenance,"date_range":service.model.report["test_origin_range"]})
            if path == "/api/evidence":
                return self.send_json({"evaluation":service.model.report,"provenance":service.provenance})
            known = {"/":("index.html","text/html; charset=utf-8"),"/app.js":("app.js","text/javascript; charset=utf-8"),"/style.css":("style.css","text/css; charset=utf-8"),"/favicon.svg":("favicon.svg","image/svg+xml")}
            if path not in known:
                return self.send_json({"error":"页面不存在"},404)
            file, mime = known[path]
            return self.send_bytes((ROOT/"web"/file).read_bytes(),mime)

        def do_POST(self):
            if urlparse(self.path).path != "/api/analyze":
                return self.send_json({"error":"接口不存在"},404)
            if self.headers.get("Origin") not in [None, f"http://127.0.0.1:{self.server.server_port}", f"http://localhost:{self.server.server_port}"]:
                return self.send_json({"error":"请求来源不匹配"},403)
            if self.headers.get("Content-Type","").split(";")[0] != "application/json":
                return self.send_json({"error":"请使用JSON请求"},415)
            try:
                length = int(self.headers.get("Content-Length","0"))
                if not 0 < length <= 16384:
                    return self.send_json({"error":"请求大小应为1–16384字节"},413)
                raw = self.rfile.read(length)
                args = json.loads(raw,parse_constant=lambda _: (_ for _ in ()).throw(ValueError("不接受NaN或Infinity")))
                return self.send_json(service.analyze(args))
            except (ValueError, TypeError, UnicodeDecodeError) as exc:
                return self.send_json({"error":str(exc)},400)

        def log_message(self, fmt, *args):
            print(f"[{self.log_date_time_string()}] {fmt % args}",flush=True)
    return Handler


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--port",type=int,default=50112)
    args = parser.parse_args()
    service = TeaService(load_weather())
    service.model.save_report()
    with ThreadingHTTPServer(("127.0.0.1",args.port),make_handler(service)) as app:
        print(f"TeaGuard ready: http://127.0.0.1:{args.port}/",flush=True)
        app.serve_forever()
