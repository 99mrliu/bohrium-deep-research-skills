#!/usr/bin/env python3
"""Regression tests for question coverage, IDs, modes and dynamic contracts."""
import copy
import json
from pathlib import Path
import tempfile
import unittest

import coverage_tool as tool

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "examples" / "positive"


class CoverageToolTests(unittest.TestCase):
    def setUp(self):
        self.coverage = json.loads((BASE / "input" / "coverage.json").read_text(encoding="utf-8"))
        self.manifest = json.loads((ROOT / "references" / "coverage-manifest.json").read_text(encoding="utf-8"))
        self.case = json.loads((BASE / "input" / "case.json").read_text(encoding="utf-8"))
        self.task = str(BASE / "input" / "task.md")
        self.contract = tool.load_contract(self.task, self.case, self.manifest)

    def codes(self, coverage=None, manifest=None):
        gaps, _ = tool.validate_coverage(coverage or self.coverage, manifest or self.manifest)
        return {gap["code"] for gap in gaps}

    def first_leaf(self):
        return self.coverage["questions"][0]["subquestions"][0]

    def result_errors(self, result):
        return {gap["code"] for gap in tool.validate_result(result, self.coverage, self.case, self.contract, self.manifest)}

    def valid_result(self):
        result = tool.make_skeleton(self.case, self.contract, self.manifest)
        for name, pointer in self.manifest["output_map"].items():
            result[name] = copy.deepcopy(tool.pointer_get(self.coverage, pointer))
        return result

    def test_01_positive_has_twenty_claims_and_passes(self):
        gaps, summary = tool.validate_coverage(self.coverage, self.manifest)
        self.assertEqual([], gaps)
        self.assertEqual(20, summary["claims"])
        self.assertEqual(24, summary["subquestions"])

    def test_02_missing_answer(self):
        self.first_leaf().pop("answer")
        self.assertIn("answer.missing", self.codes())

    def test_03_missing_question_id(self):
        self.first_leaf()["subquestion_id"] = ""
        self.assertIn("id.missing", self.codes())

    def test_04_duplicate_subquestion_id(self):
        self.coverage["questions"][0]["subquestions"][1]["subquestion_id"] = "Q1.1"
        self.assertIn("id.duplicate", self.codes())

    def test_05_dangling_claim(self):
        self.first_leaf()["claim_ids"] = ["C-X"]
        self.assertIn("id.dangling", self.codes())

    def test_06_dangling_evidence(self):
        self.first_leaf()["evidence_ids"] = ["E-X"]
        self.assertIn("id.dangling", self.codes())

    def test_07_dangling_claim_registry_link(self):
        self.coverage["claims"][0]["evidence_ids"] = ["E-X"]
        self.assertIn("id.dangling", self.codes())

    def test_08_unreported_scope_required(self):
        leaf = self.coverage["questions"][5]["subquestions"][0]
        leaf["unreported"]["searched_scope"] = []
        self.assertIn("unreported.searched_scope", self.codes())

    def test_09_unreported_cannot_carry_factual_links(self):
        leaf = self.coverage["questions"][5]["subquestions"][0]
        leaf["claim_ids"] = ["C01"]
        self.assertIn("unreported.factual_links", self.codes())

    def test_10_invalid_status(self):
        self.first_leaf()["status"] = "done"
        self.assertIn("status.invalid", self.codes())

    def test_11_progress_status_ceiling(self):
        self.first_leaf()["status"] = "partial"
        self.first_leaf()["progress_percent"] = 51
        self.assertIn("status.ceiling_exceeded", self.codes())

    def test_12_confidence_upper_bound(self):
        self.first_leaf()["confidence"] = 1.01
        self.assertIn("confidence.range", self.codes())

    def test_13_direct_report_needs_direct_support(self):
        self.coverage["evidence"][0]["support"] = "computed"
        self.coverage["evidence"][0]["derivation"] = "unchanged value"
        self.assertIn("answer_mode.support_mismatch", self.codes())

    def test_14_computed_needs_derivation(self):
        self.coverage["evidence"][4].pop("derivation")
        self.assertIn("derivation.missing", self.codes())

    def test_15_inferred_needs_rationale(self):
        self.coverage["evidence"][8].pop("rationale")
        self.assertIn("rationale.missing", self.codes())

    def test_16_duplicate_claim_ids(self):
        self.coverage["claims"][1]["claim_id"] = "C01"
        self.assertIn("id.duplicate", self.codes())

    def test_17_duplicate_evidence_ids(self):
        self.coverage["evidence"][1]["evidence_id"] = "E01"
        self.assertIn("id.duplicate", self.codes())

    def test_18_duplicate_source_ids(self):
        self.coverage["sources"].append(copy.deepcopy(self.coverage["sources"][0]))
        self.assertIn("id.duplicate", self.codes())

    def test_19_source_uncertainty_required(self):
        self.coverage["sources"][0].pop("uncertainty")
        self.assertIn("source.uncertainty_missing", self.codes())

    def test_20_question_claim_key_required(self):
        self.coverage["questions"][0].pop("claim_ids")
        codes = self.codes()
        self.assertIn("question.required_missing", codes)
        self.assertIn("links.type", codes)

    def test_21_requirement_matrix_required(self):
        self.first_leaf()["requirement"]["evidence_kinds"] = []
        self.assertIn("requirement.evidence_kinds", self.codes())

    def test_22_missing_contract_is_input_error(self):
        with tempfile.TemporaryDirectory() as folder:
            task = Path(folder) / "task.md"
            task.write_text("No JSON contract here", encoding="utf-8")
            with self.assertRaises(tool.InputError):
                tool.load_contract(str(task), {"case_id": "x"}, self.manifest)

    def test_23_exact_rejects_extra_result_field(self):
        result = self.valid_result()
        result["coverage_report"] = {}
        self.assertIn("result.unexpected_field", self.result_errors(result))

    def test_24_exact_rejects_missing_result_field(self):
        result = self.valid_result()
        result.pop("uncertainty")
        self.assertIn("result.field_missing", self.result_errors(result))

    def test_25_case_id_must_be_original(self):
        result = self.valid_result()
        result["case_id"] = "changed"
        self.assertIn("result.case_id_changed", self.result_errors(result))

    def test_26_task_contract_precedes_case_contract(self):
        case = copy.deepcopy(self.case)
        case["output_contract"] = ["wrong_fallback"]
        contract = tool.load_contract(self.task, case, self.manifest)
        self.assertEqual("task.md", contract["source"])
        self.assertNotIn("wrong_fallback", contract["fields"])

    def test_27_unseen_contract_generates_corresponding_skeleton(self):
        result = self.valid_result()
        self.assertEqual({"case_id", "answers", "sources", "uncertainty", "change_records"}, set(result))
        self.assertEqual(set(), self.result_errors(result))

    def test_28_stale_result_differs_from_current_coverage(self):
        result = self.valid_result()
        result["answers"] = copy.deepcopy(result["answers"])
        result["answers"][0]["answer"] = "stale"
        self.assertIn("result.stale_payload", self.result_errors(result))

    def test_29_manifest_can_rename_answer_key(self):
        manifest = copy.deepcopy(self.manifest)
        manifest["answer_key"] = "response"
        manifest["required_question_keys"] = ["response" if key == "answer" else key for key in manifest["required_question_keys"]]
        manifest["required_subquestion_keys"] = ["response" if key == "answer" else key for key in manifest["required_subquestion_keys"]]
        for question in self.coverage["questions"]:
            question["response"] = question.pop("answer")
            for child in question["subquestions"]:
                child["response"] = child.pop("answer")
        self.assertEqual(set(), self.codes(manifest=manifest))

    def test_30_json_schema_contract_and_case_fallback(self):
        case = {"case_id": "other", "output_contract": {"properties": {"alpha": {"type": "array"}}, "required": ["beta"], "additionalProperties": False}}
        with tempfile.TemporaryDirectory() as folder:
            task = Path(folder) / "task.md"
            task.write_text("contract deliberately absent", encoding="utf-8")
            contract = tool.load_contract(str(task), case, self.manifest)
        self.assertEqual("case.json", contract["source"])
        self.assertEqual(["alpha", "beta"], contract["fields"])
        self.assertTrue(contract["exact_top_level"])

    def test_31_repeated_local_link_detected(self):
        self.first_leaf()["claim_ids"] = ["C01", "C01"]
        self.assertIn("links.repeated", self.codes())

    def test_32_parent_cannot_hide_unanswered_child(self):
        self.coverage["questions"][0]["subquestions"][0]["status"] = "unanswered"
        self.coverage["questions"][0]["subquestions"][0]["progress_percent"] = 0
        self.assertIn("status.child_mismatch", self.codes())

    def test_33_change_records_must_be_array(self):
        self.coverage["change_records"] = {}
        self.assertIn("change_records.type", self.codes())

    def test_34_json_pointer_handles_escaped_tokens(self):
        document = {"a/b": {"~key": [7]}}
        self.assertEqual(7, tool.pointer_get(document, "/a~1b/~0key/0"))


if __name__ == "__main__":
    unittest.main()
