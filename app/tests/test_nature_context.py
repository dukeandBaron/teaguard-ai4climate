"""Frozen behavior contract for the10 nature-context scenarios and web integration."""

import importlib
import json
import unittest
from copy import deepcopy
from pathlib import Path


def api(test):
    try:
        module = importlib.import_module("teaguard.nature")
    except ModuleNotFoundError:
        module = None
    test.assertIsNotNone(module, "Nature-context runtime is missing")
    return module


class NatureContextTests(unittest.TestCase):
    def run_context(self, context=None, **kwargs):
        module = api(self)
        payload = module.make_scenario(context=context or {})
        return module.analyze_context(payload, **kwargs)

    def codes(self, result):
        return {task["focus"] for task in result["tasks"]}

    def test_unified_state_passes_runtime_contract(self):
        result = self.run_context()
        self.assertEqual(api(self).validate_state(result["nature_state"]), [])
        self.assertFalse(result["operational_admission"])
        self.assertEqual(len(result["applicability"]), 5)

    def test_runtime_json_schema_checks_real_generated_instances(self):
        import jsonschema

        schema = json.loads(
            (
                Path(__file__).resolve().parents[1] / "data/nature_state_schema.json"
            ).read_text(encoding="utf-8")
        )
        validator = jsonschema.Draft202012Validator(
            schema, format_checker=jsonschema.FormatChecker()
        )
        for ctx in [
            {},
            {"soil": "moist"},
            {"soil": "dry", "shade": "absent"},
            {"requested_claim": "hydrogel_treatment"},
        ]:
            with self.subTest(context=ctx):
                validator.validate(self.run_context(ctx)["nature_state"])

    def test_n01_moist_soil_preserves_heat_without_watering_dose(self):
        result = self.run_context({"soil": "moist"})
        self.assertIn("heat", self.codes(result))
        self.assertIn("reconcile_soil", self.codes(result))
        self.assertFalse(any("dose_mm" in t for t in result["tasks"]))

    def test_n02_dry_soil_requests_observation_details(self):
        result = self.run_context({"soil": "dry"})
        self.assertIn("verify_soil_method", self.codes(result))
        self.assertIn("joint_context_review", self.codes(result))

    def test_n03_unknown_soil_remains_unknown(self):
        result = self.run_context({"soil": None})
        self.assertIn("request_soil", self.codes(result))
        factor = next(
            f
            for f in result["nature_state"]["context_factors"]
            if f["factor"] == "SOIL_MOISTURE_DESCRIPTION"
        )
        self.assertIsNone(factor["state"])
        self.assertEqual(factor["status"], "UNKNOWN")

    def test_n04_shade_changes_tasks_not_weather(self):
        first = self.run_context({"shade": "present"})
        second = self.run_context({"shade": "absent"})
        self.assertEqual(first["weather_hash"], second["weather_hash"])
        self.assertIn("shade_coverage", self.codes(first))
        self.assertIn("exposed_position", self.codes(second))

    def test_n05_stage_and_cultivar_do_not_create_sensitivity_coefficient(self):
        cases = [
            self.run_context({"growth_stage": value})
            for value in ["young_growth", "mature", "unknown"]
        ]
        self.assertEqual(len({r["weather_hash"] for r in cases}), 1)
        self.assertIn("verify_growth_stage", self.codes(cases[0]))
        self.assertIn("request_stage", self.codes(cases[2]))
        self.assertTrue(all("damage_probability" not in r for r in cases))

    def test_n06_cross_species_treatment_is_withheld(self):
        result = self.run_context({"requested_claim": "hydrogel_treatment"})
        card = next(c for c in result["applicability"] if c["card_id"] == "E03")
        self.assertEqual(card["applicability"], "MISMATCH")
        self.assertEqual(result["claim_review"]["status"], "WITHHELD")
        self.assertEqual(card["conditions"]["crop"], "Brassica napus")

    def test_n07_gene_expression_not_field_combined_damage(self):
        result = self.run_context({"requested_claim": "field_combined_damage"})
        card = next(c for c in result["applicability"] if c["card_id"] == "E02")
        self.assertEqual(card["applicability"], "MISMATCH")
        self.assertEqual(result["claim_review"]["status"], "WITHHELD")
        self.assertIn("endpoint", card["dimension_checks"])

    def test_n08_conflicting_scales_keep_both_observations(self):
        result = self.run_context(
            {"soil": "moist", "soil_time": None, "soil_depth_cm": None}
        )
        observations = result["nature_state"]["observations"]
        self.assertTrue(
            any(o["kind"] == "REFERENCE_ET0_MINUS_PRECIP" for o in observations)
        )
        self.assertTrue(any(o["kind"] == "SOIL_DESCRIPTION" for o in observations))
        self.assertIn("RECONCILE_CONFLICT", [t["task_type"] for t in result["tasks"]])
        self.assertTrue(
            any(e["relation"] == "CONFLICTS_WITH" for e in result["graph"]["edges"])
        )

    def test_n09_bad_generated_numbers_and_citations_are_rejected(self):
        result = self.run_context(
            candidate_explanation={
                "temperature_c": 99,
                "card_ids": ["E-NONEXISTENT-INJECTED"],
            }
        )
        self.assertIn("EXPLANATION_REJECTED", result["flags"])
        self.assertEqual(result["weather"]["heat_point_c"], 34.5)
        self.assertNotIn("99", result["explanation"])
        self.assertNotIn("E-NONEXISTENT-INJECTED", result["used_card_ids"])

    def test_n10_feedback_appends_simulated_version_without_duplicates(self):
        first = self.run_context({"soil": "dry"})
        before = deepcopy(first)
        completed = api(self).complete_task(first, first["tasks"][0]["task_id"])
        self.assertEqual(first, before)
        self.assertIn(first["version_id"], completed["lineage"])
        self.assertEqual(completed["tasks"][0]["status"], "SIMULATED_COMPLETION")
        repeated = api(self).analyze_context(
            api(self).make_scenario(context={"soil": "dry"}), previous=completed
        )
        keys = [t["deduplication_key"] for t in repeated["tasks"]]
        self.assertEqual(len(keys), len(set(keys)))
        self.assertIn(completed["version_id"], repeated["lineage"])

    def test_species_cultivar_setting_treatment_endpoint_are_processed(self):
        result = self.run_context(
            {
                "species": "Camellia sinensis",
                "cultivar": "Tieguanyin",
                "setting": "artificial_chamber",
                "treatment": "heat_or_PEG",
                "endpoint": "gene_expression",
            }
        )
        card = next(c for c in result["applicability"] if c["card_id"] == "E02")
        self.assertEqual(card["applicability"], "MATCH")
        self.assertTrue(
            all(
                card["dimension_checks"][k] == "MATCH"
                for k in ["species", "cultivar", "setting", "treatment", "endpoint"]
            )
        )

    def test_graph_references_resolve_and_no_causal_weight_is_invented(self):
        graph = self.run_context()["graph"]
        nodes = {n["id"] for n in graph["nodes"]}
        self.assertTrue(
            all(e["source"] in nodes and e["target"] in nodes for e in graph["edges"])
        )
        self.assertTrue(
            all(e["causal_effect_measured"] is False for e in graph["edges"])
        )

    def test_unknown_condition_branch_audit_does_not_call_it_information_gain(self):
        result = self.run_context()
        self.assertTrue(result["questions"])
        self.assertTrue(all("branch_task_changes" in q for q in result["questions"]))
        self.assertTrue(
            all(q["optimality_claim"] is False for q in result["questions"])
        )

    def test_invalid_synthetic_provenance_is_rejected(self):
        payload = api(self).make_scenario()
        payload["nature_state"]["observations"][-1]["use_scope"] = (
            "OPERATIONAL_INPUT_CANDIDATE"
        )
        with self.assertRaises(ValueError):
            api(self).analyze_context(payload)

    def test_invalid_context_types_are_not_silently_defaulted(self):
        for value in ([], False, "bad"):
            with self.subTest(value=value), self.assertRaises((ValueError, TypeError)):
                api(self).make_scenario(context=value)

    def test_ai_factor_cannot_be_relabelled_as_measured(self):
        payload = api(self).make_scenario()
        payload["nature_state"]["context_factors"][0]["status"] = (
            "MEASURED_WITH_PROVENANCE"
        )
        with self.assertRaises(ValueError):
            api(self).analyze_context(payload)

    def test_species_mismatch_reason_identifies_species(self):
        result = self.run_context({"species": "Brassica napus"})
        match = next(c for c in result["applicability"] if c["card_id"] == "E02")
        self.assertIn("物种", match["reason"])

    def test_layered_comparators_share_identical_numeric_payload(self):
        module = api(self)
        payload = module.make_scenario(context={"soil": "moist"})
        outputs = [
            module.analyze_context(payload, policy=p)
            for p in ["weather_rules", "weather_evidence", "full"]
        ]
        self.assertEqual(len({r["weather_hash"] for r in outputs}), 1)
        self.assertEqual(len(outputs[0]["applicability"]), 0)
        self.assertEqual(len(outputs[-1]["applicability"]), 5)
        self.assertIn("reconcile_soil", self.codes(outputs[-1]))


if __name__ == "__main__":
    unittest.main(verbosity=2)
