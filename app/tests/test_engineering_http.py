"""Real HTTP contracts for recovery, diagnostics and server-owned history."""

import json
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path

import nature_server
from teaguard.nature_service import NatureService
from teaguard.record_store import RecordStore

ROOT = Path(__file__).resolve().parents[1]


class EngineeringHttpTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.folder = tempfile.TemporaryDirectory(
            dir=ROOT / "artifacts/engineering", prefix="http_"
        )
        cls.service = NatureService(
            store=RecordStore(Path(cls.folder.name) / "records.sqlite3")
        )
        cls.server = ThreadingHTTPServer(
            ("127.0.0.1", 0), nature_server.make_handler(cls.service)
        )
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.base = f"http://127.0.0.1:{cls.server.server_port}"

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join(timeout=3)
        cls.folder.cleanup()

    def request(self, path, payload=None):
        request = urllib.request.Request(
            self.base + path,
            data=None if payload is None else json.dumps(payload).encode(),
            headers={"Content-Type": "application/json"},
        )
        try:
            response = urllib.request.urlopen(request, timeout=5)
        except urllib.error.HTTPError as error:
            response = error
        with response:
            return response.status, json.load(response)

    def test_unknown_parent_has_recoverable_code_and_request_id(self):
        status, data = self.request("/api/analyze", {"previous_version_id": "f" * 24})
        self.assertEqual(status, 404)
        self.assertEqual(data["code"], "RECORD_NOT_FOUND")
        self.assertTrue(data["request_id"])

    def test_invalid_nested_input_is_json_error_not_disconnect(self):
        status, data = self.request("/api/analyze", {"context": {"soil_time": 123}})
        self.assertEqual(status, 400)
        self.assertEqual(data["code"], "INVALID_INPUT")

    def test_record_history_is_server_owned(self):
        _, record = self.request(
            "/api/analyze", {"weather_mode": "synthetic", "context": {"soil": "dry"}}
        )
        status, history = self.request("/api/records")
        self.assertEqual(status, 200)
        self.assertIn(record["version_id"], [item["id"] for item in history["records"]])

    def test_project_status_separates_local_from_field_evidence(self):
        status, data = self.request("/api/project-status")
        self.assertEqual(status, 200)
        self.assertEqual(data["field_effectiveness_verified"], False)
        self.assertTrue(
            any(item["status"] == "IMPLEMENTED_LOCAL" for item in data["capabilities"])
        )

    def test_feedback_retry_does_not_append_duplicate_event(self):
        _, first = self.request("/api/analyze", {"weather_mode": "synthetic"})
        request = {
            "version_id": first["version_id"],
            "task_id": first["tasks"][0]["task_id"],
            "completed": True,
        }
        status, updated = self.request("/api/feedback", request)
        _, retried = self.request("/api/feedback", request)
        self.assertEqual(status, 200)
        self.assertEqual(updated["version_id"], retried["version_id"])
        _, same = self.request(
            "/api/feedback", {**request, "version_id": updated["version_id"]}
        )
        self.assertEqual(same["version_id"], updated["version_id"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
