"""Behavior contracts reproduced before the engineering revision."""

import importlib
import json
import shutil
import sqlite3
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from pathlib import Path

from teaguard.nature import analyze_context, make_scenario
from teaguard.nature_service import NatureService

ROOT = Path(__file__).resolve().parents[1]
TEMP = ROOT / "artifacts/engineering"
TEMP.mkdir(parents=True, exist_ok=True)


class RequestContractTests(unittest.TestCase):
    def test_unknown_request_field_is_not_silently_ignored(self):
        with self.assertRaises(ValueError):
            NatureService().analyze({"weather_mod": "synthetic"})

    def test_missing_previous_version_is_not_silently_reset(self):
        with self.assertRaises(ValueError):
            NatureService().analyze({"previous_version_id": "f" * 24})

    def test_wrong_soil_time_type_has_a_contract_error(self):
        with self.assertRaises((ValueError, TypeError)):
            NatureService().analyze({"context": {"soil_time": 123}})

    def test_explanation_rejection_changes_domain_identity(self):
        payload = make_scenario()
        clean = analyze_context(payload)
        rejected = analyze_context(payload, candidate_explanation={"temperature_c": 99})
        self.assertNotEqual(clean["flags"], rejected["flags"])
        self.assertNotEqual(clean["version_id"], rejected["version_id"])

    def test_feedback_completion_requires_real_boolean(self):
        first = analyze_context(make_scenario())
        from teaguard.nature import complete_task

        with self.assertRaises((ValueError, TypeError)):
            complete_task(first, first["tasks"][0]["task_id"], completed="false")


class RecordStoreTests(unittest.TestCase):
    def setUp(self):
        try:
            self.module = importlib.import_module("teaguard.record_store")
        except ModuleNotFoundError:
            self.module = None
        self.assertIsNotNone(self.module, "Transactional local record store is missing")
        self.directory = tempfile.TemporaryDirectory(dir=TEMP, prefix="records_")
        self.addCleanup(self.directory.cleanup)
        self.path = Path(self.directory.name) / "records.sqlite3"
        self.store = self.module.RecordStore(self.path)

    def sample(self):
        return analyze_context(make_scenario(context={"soil": "dry"}))

    def test_replay_is_idempotent_across_store_instances(self):
        record = self.store.save(self.sample())
        second = self.module.RecordStore(self.path)
        self.assertEqual(record, second.save(self.sample()))
        self.assertEqual(len(second.list_recent()), 1)

    def test_caller_mutation_does_not_change_persisted_record(self):
        record = self.store.save(self.sample())
        identifier = record["version_id"]
        record["tasks"][0]["title"] = "changed by caller"
        self.assertNotEqual(
            self.store.get(identifier)["tasks"][0]["title"], "changed by caller"
        )

    def test_content_change_produces_a_distinct_identity(self):
        first = self.store.save(self.sample())
        changed = self.sample()
        changed["flags"].append("EXPLANATION_REJECTED")
        second = self.store.save(changed)
        self.assertNotEqual(first["version_id"], second["version_id"])

    def test_concurrent_writers_preserve_one_identical_record(self):
        sample = self.sample()
        with ThreadPoolExecutor(max_workers=8) as pool:
            records = list(pool.map(lambda _: self.store.save(sample), range(16)))
        self.assertEqual(len({r["version_id"] for r in records}), 1)
        self.assertEqual(len(self.store.list_recent()), 1)

    def test_tampered_payload_fails_closed(self):
        record = self.store.save(self.sample())
        with closing(sqlite3.connect(self.path)) as connection, connection:
            connection.execute(
                "UPDATE records SET payload=?", ('{"version_id":"changed"}',)
            )
        with self.assertRaises(ValueError):
            self.store.get(record["version_id"])

    def test_missing_parent_cannot_create_an_orphan(self):
        record = self.sample()
        record["lineage"] = ["a" * 24]
        with self.assertRaises(ValueError):
            self.store.save(record)
        self.assertEqual(self.store.list_recent(), [])

    def test_unknown_record_is_a_typed_failure(self):
        with self.assertRaises(ValueError):
            self.store.get("f" * 24)

    def test_history_is_available_without_browser_local_storage(self):
        first = self.store.save(self.sample())
        service = NatureService(store=self.store)
        summaries = service.list_records()
        self.assertEqual(summaries[0]["id"], first["version_id"])
        self.assertEqual(service.get_record(first["version_id"]), first)


class WeatherRepositoryTests(unittest.TestCase):
    def test_tampered_frozen_prediction_is_rejected(self):
        try:
            module = importlib.import_module("teaguard.weather_repository")
        except ModuleNotFoundError:
            module = None
        self.assertIsNotNone(module, "Frozen weather repository is missing")
        with tempfile.TemporaryDirectory(dir=TEMP, prefix="weather_") as folder:
            root = Path(folder)
            for name in (
                "data/weather_daily.csv",
                "data/PROVENANCE.json",
                "artifacts/test_predictions.json",
                "artifacts/evaluation.json",
                "PARENT_V2_BINDING.json",
            ):
                target = root / name
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(ROOT / name, target)
            file = root / "artifacts/test_predictions.json"
            rows = json.loads(file.read_text(encoding="utf-8"))
            rows[0]["heat_3d_selected"] = 99
            file.write_text(json.dumps(rows), encoding="utf-8")
            with self.assertRaises(ValueError):
                module.WeatherRepository(root)


if __name__ == "__main__":
    unittest.main(verbosity=2)
