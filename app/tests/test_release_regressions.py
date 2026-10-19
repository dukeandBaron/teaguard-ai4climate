"""Release defects are reproduced before fixing their domain and input contracts."""

import json
import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path

from teaguard.contracts import AnalyzeRequest, AppError
from teaguard.nature import analyze_context, complete_task, make_scenario
from teaguard.record_store import RecordStore

TEMP = Path(__file__).resolve().parents[1] / "artifacts/engineering"


class ReleaseRegressionTests(unittest.TestCase):
    def complete(self, result, focus):
        task = next(t for t in result["tasks"] if t["focus"] == focus)
        return complete_task(result, task["task_id"])

    def status(self, result, focus):
        return next(t["status"] for t in result["tasks"] if t["focus"] == focus)

    def test_changed_soil_observation_reopens_joint_review(self):
        old = self.complete(
            analyze_context(make_scenario(context={"soil": "dry"})),
            "joint_context_review",
        )
        new = analyze_context(
            make_scenario(
                context={
                    "soil": "dry",
                    "soil_method": "visual_description",
                    "soil_depth_cm": 20,
                }
            ),
            previous=old,
        )
        self.assertEqual(self.status(new, "joint_context_review"), "PROPOSED")
        self.assertIn("TASK_BASIS_CHANGED", new["flags"])
        self.assertEqual(
            self.status(old, "joint_context_review"), "SIMULATED_COMPLETION"
        )

    def test_changed_weather_interval_reopens_heat_review(self):
        payload = make_scenario()
        old = self.complete(analyze_context(payload), "heat")
        weather = {**payload["weather"], "heat_upper_c": 38.0}
        new = analyze_context(make_scenario(weather=weather), previous=old)
        self.assertEqual(self.status(new, "heat"), "PROPOSED")

    def test_identical_basis_retains_completion(self):
        payload = make_scenario()
        old = self.complete(analyze_context(payload), "heat")
        new = analyze_context(payload, previous=old)
        self.assertEqual(self.status(new, "heat"), "SIMULATED_COMPLETION")

    def test_unrelated_shade_change_keeps_heat_completion(self):
        old = self.complete(analyze_context(make_scenario()), "heat")
        new = analyze_context(make_scenario(context={"shade": "present"}), previous=old)
        self.assertEqual(self.status(new, "heat"), "SIMULATED_COMPLETION")

    def test_known_soil_missing_provenance_is_the_first_question(self):
        result = analyze_context(make_scenario(context={"soil": "dry"}))
        self.assertEqual(result["questions"][0]["factor"], "soil_provenance")
        self.assertIn("soil_time", result["questions"][0]["missing_fields"])
        self.assertFalse(result["questions"][0]["optimality_claim"])

    def test_synthetic_date_cannot_silently_disagree_with_weather(self):
        with self.assertRaises(ValueError):
            AnalyzeRequest.parse({"weather_mode": "synthetic", "date": "2025-08-01"})
        with self.assertRaises(ValueError):
            AnalyzeRequest.parse({"weather_mode": "synthetic", "date": "2025-02-30"})

    def test_malformed_record_container_has_a_typed_integrity_error(self):
        with tempfile.TemporaryDirectory(dir=TEMP, prefix="release_") as directory:
            path = Path(directory) / "records.sqlite3"
            store = RecordStore(path)
            record = store.save(analyze_context(make_scenario()))
            with closing(sqlite3.connect(path)) as connection, connection:
                connection.execute("UPDATE records SET payload=?", (json.dumps([]),))
            with self.assertRaises(AppError) as caught:
                store.get(record["version_id"])
            self.assertEqual(caught.exception.code, "RECORD_INTEGRITY")


if __name__ == "__main__":
    unittest.main(verbosity=2)
