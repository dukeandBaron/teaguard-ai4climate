"""Exercise the real local HTTP application; no model fit is permitted."""

import importlib
import json
import threading
import unittest
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class NatureHttpTests(unittest.TestCase):
    def test_versions_reload_from_local_files(self):
        app = importlib.import_module("nature_server")
        first = app.NatureService()
        record = first.analyze(
            {
                "weather_mode": "synthetic",
                "case_id": "PERSISTENCE_CONTROL",
                "context": {"soil": "dry"},
            }
        )
        second = app.NatureService()
        self.assertEqual(
            second.get_record(record["version_id"])["weather_hash"],
            record["weather_hash"],
        )

    def test_local_application_flow(self):
        try:
            app = importlib.import_module("nature_server")
        except ModuleNotFoundError:
            app = None
        self.assertIsNotNone(app, "V2 HTTP entry is missing")
        service = app.NatureService()
        server = ThreadingHTTPServer(("127.0.0.1", 0), app.make_handler(service))
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        base = f"http://127.0.0.1:{server.server_port}"

        def get(path):
            with urllib.request.urlopen(base + path) as response:
                return response.read()

        def post(path, payload, origin=None):
            headers = {"Content-Type": "application/json"}
            if origin:
                headers["Origin"] = origin
            request = urllib.request.Request(
                base + path, data=json.dumps(payload).encode(), headers=headers
            )
            with urllib.request.urlopen(request) as response:
                return json.load(response)

        try:
            bootstrap = json.loads(get("/api/bootstrap"))
            self.assertEqual(bootstrap["version"], "0.3.1")
            self.assertEqual(bootstrap["coverage"]["real_field_labels"], 0)
            self.assertEqual(len(bootstrap["default"]["applicability"]), 5)
            moist = post(
                "/api/analyze",
                {
                    "weather_mode": "historical",
                    "date": "2025-07-15",
                    "context": {"soil": "moist"},
                },
            )
            dry = post(
                "/api/analyze",
                {
                    "weather_mode": "historical",
                    "date": "2025-07-15",
                    "context": {"soil": "dry"},
                },
            )
            self.assertEqual(moist["weather_hash"], dry["weather_hash"])
            updated = post(
                "/api/feedback",
                {
                    "version_id": dry["version_id"],
                    "task_id": dry["tasks"][0]["task_id"],
                    "completed": True,
                },
            )
            self.assertEqual(updated["tasks"][0]["status"], "SIMULATED_COMPLETION")
            with self.assertRaises(urllib.error.HTTPError) as caught:
                post("/api/analyze", {}, origin="https://example.com")
            self.assertEqual(caught.exception.code, 403)
            self.assertIn(b"app.js", get("/"))
            for path in ["/app.js", "/style.css", "/api/replay-summary"]:
                self.assertTrue(get(path))
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=3)


if __name__ == "__main__":
    unittest.main(verbosity=2)
