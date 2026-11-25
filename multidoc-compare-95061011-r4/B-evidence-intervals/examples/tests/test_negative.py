#!/usr/bin/env python3
"""Offline positive and adversarial checks for evidence interval enforcement."""
import copy
import json
import sys
import tempfile
import unittest
from pathlib import Path

EXAMPLE = Path(__file__).resolve().parents[1]
ROOT = EXAMPLE.parent
sys.path.insert(0, str(ROOT / "scripts"))

from evidence_intervals import assemble_contract, build_index, read_json, validate_and_render, validate_records  # noqa: E402


class EvidenceIntervalTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.input_dir = EXAMPLE / "input"
        cls.index = build_index(cls.input_dir)
        cls.workorder = read_json(cls.input_dir / "comparison-workorder.json")
        cls.evidence = read_json(cls.input_dir / "evidence.json")

    def validate(self, evidence):
        return validate_records(evidence, self.index, self.workorder)

    def test_complete_fixture_and_noncomparable_success(self):
        with tempfile.TemporaryDirectory(dir=EXAMPLE / "tests") as temporary:
            result = validate_and_render(self.input_dir, self.index, self.evidence, Path(temporary))
            self.assertEqual("success", result["status"])
            self.assertEqual("synthetic-evidence-intervals-001", result["case_id"])
            self.assertEqual(4, len(result["common_field_matrix"]))
            beta = result["synthesis"]["comparisons"][0]["records"]
            self.assertEqual(["beta-derived-128"], [row["evidence_id"] for row in beta])
            self.assertEqual(128.0, beta[0]["value"])
            gamma = [row for row in result["common_field_matrix"] if row["source_document_id"] == "fictional-gamma"]
            self.assertEqual("not_reported", gamma[0]["value"])
            self.assertEqual("not_reported", gamma[0]["paragraph_id"])
            conflicted = [row for row in result["common_field_matrix"] if row["source_document_id"] == "fictional-alpha"]
            self.assertEqual({128.0, 132.0}, {row["value"] for row in conflicted})

    def test_list_and_dict_output_contracts_are_complete(self):
        listed = assemble_contract({"case_id": "list-case", "output_contract": ["common_field_matrix", "synthesis"]}, [], {"comparisons": []}, {}, [], [], [], [], "success")
        self.assertEqual("list-case", listed["case_id"])
        self.assertIn("common_field_matrix", listed)
        self.assertIn("synthesis", listed)
        direct = assemble_contract({"case_id": "dict-case", "output_contract": {"extra_review": {"type": "list"}}}, [], {}, {}, [], [], [], [], "success")
        self.assertEqual([], direct["extra_review"])
        self.assertEqual("partial", direct["status"])
        self.assertIn("extra_review", direct["uncertainty"][0])

    def test_task_and_workorder_scope_fail_before_synthesis(self):
        changed = copy.deepcopy(self.evidence)
        changed["records"][2]["task"] = "another-task"
        changed["records"][2]["unit"] = "g/g"
        changed["records"][2]["pollutant"] = "methylene blue"
        accepted, excluded, _ = self.validate(changed)
        errors = " ".join(next(r["validation_errors"] for r in excluded if r["evidence_id"] == "beta-derived-128"))
        self.assertIn("task does not match", errors)
        self.assertIn("unit 'g/g' is outside workorder scope", errors)
        self.assertNotIn("beta-derived-128", {r["evidence_id"] for r in accepted})

    def test_normalized_quote_equivalence_preserves_source(self):
        changed = copy.deepcopy(self.evidence)
        changed["records"][0]["source_spans"][0]["quote"] = "For\u00a0Experiment A,  the adsorption_capacity result was 128 mg/g."
        accepted, excluded, _ = self.validate(changed)
        self.assertFalse(excluded)
        self.assertIn("alpha-main-128", {r["evidence_id"] for r in accepted})

    def test_no_usable_evidence_is_failed_with_contract(self):
        with tempfile.TemporaryDirectory(dir=EXAMPLE / "tests") as temporary:
            result = validate_and_render(self.input_dir, self.index, {"schema_version": "1.0", "records": []}, Path(temporary))
            self.assertEqual("failed", result["status"])
            self.assertEqual("synthetic-evidence-intervals-001", result["case_id"])
            for name in ("common_field_matrix", "synthesis", "comparison_scope", "limitations", "sources", "uncertainty", "change_records"):
                self.assertIn(name, result)

    def test_wrong_document_fails(self):
        changed = copy.deepcopy(self.evidence)
        changed["records"][0]["source_document_id"] = "fictional-beta"
        accepted, excluded, _ = self.validate(changed)
        errors = " ".join(excluded[0]["validation_errors"])
        self.assertIn("wrong source_document_id", errors)
        self.assertNotIn("alpha-main-128", {r["evidence_id"] for r in accepted})

    def test_wrong_context_qualifier_fails(self):
        changed = copy.deepcopy(self.evidence)
        changed["records"][0]["material"] = "Membrane B"
        accepted, excluded, _ = self.validate(changed)
        errors = " ".join(next(r["validation_errors"] for r in excluded if r["evidence_id"] == "alpha-main-128"))
        self.assertIn("span alpha-main-context does not contain exact qualifier", errors)
        self.assertNotIn("alpha-main-128", {r["evidence_id"] for r in accepted})

    def test_fake_quote_and_direct_value_fail(self):
        changed = copy.deepcopy(self.evidence)
        changed["records"][0]["source_spans"][0]["quote"] = "For Experiment A, the adsorption_capacity result was 999 mg/g."
        changed["records"][0]["value"] = 999.0
        changed["records"][0]["value_literal"] = "999"
        accepted, excluded, _ = self.validate(changed)
        errors = " ".join(next(r["validation_errors"] for r in excluded if r["evidence_id"] == "alpha-main-128"))
        self.assertIn("quote does not match original paragraph slice", errors)
        self.assertIn("direct value literal not found", errors)
        self.assertNotIn("alpha-main-128", {r["evidence_id"] for r in accepted})

    def test_absence_rejects_fake_paragraph(self):
        changed = copy.deepcopy(self.evidence)
        absent = changed["records"][3]
        absent["paragraph_id"] = "fictional-gamma-p0003"
        absent["page"] = 1
        accepted, excluded, _ = self.validate(changed)
        errors = " ".join(next(r["validation_errors"] for r in excluded if r["evidence_id"] == "gamma-capacity-absent"))
        self.assertIn("null locator/page and no fake spans", errors)
        self.assertEqual(3, len(accepted))

    def test_incomplete_absence_search_fails(self):
        changed = copy.deepcopy(self.evidence)
        changed["records"][3]["search_scope"]["paragraph_ids"] = ["fictional-gamma-p0003"]
        _, excluded, _ = self.validate(changed)
        errors = " ".join(next(r["validation_errors"] for r in excluded if r["evidence_id"] == "gamma-capacity-absent"))
        self.assertIn("cover every indexed document paragraph", errors)

    def test_derivation_operand_tampering_fails(self):
        changed = copy.deepcopy(self.evidence)
        changed["records"][2]["derivation"]["operands"][0]["value"] = 500.0
        _, excluded, _ = self.validate(changed)
        errors = " ".join(next(r["validation_errors"] for r in excluded if r["evidence_id"] == "beta-derived-128"))
        self.assertIn("does not equal record value", errors)

    def test_unlabelled_conflict_fails(self):
        changed = copy.deepcopy(self.evidence)
        changed["records"][0]["conflict_group"] = None
        _, excluded, _ = self.validate(changed)
        conflict = next(r for r in excluded if r["evidence_id"] == "alpha-main-128")
        self.assertIn("conflicting values", " ".join(conflict["validation_errors"]))

    def test_rendered_failure_branch_is_auditable(self):
        changed = copy.deepcopy(self.evidence)
        changed["records"][2]["source_spans"][0]["start"] = 1  # valid range, invalid quote
        with tempfile.TemporaryDirectory(dir=EXAMPLE / "tests") as temporary:
            result = validate_and_render(self.input_dir, self.index, changed, Path(temporary))
            self.assertEqual("partial", result["status"])
            self.assertTrue(any("beta-derived-128" in item for item in result["uncertainty"]))
            ledger = (Path(temporary) / "evidence-ledger.md").read_text(encoding="utf-8")
            self.assertIn("Excluded records (1)", ledger)
            persisted = json.loads((Path(temporary) / "result.json").read_text(encoding="utf-8"))
            self.assertEqual("partial", persisted["status"])
            beta_rows = [r for r in persisted["common_field_matrix"] if r["source_document_id"] == "fictional-beta"]
            self.assertEqual("missing_evidence_record", beta_rows[0]["evidence_status"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
