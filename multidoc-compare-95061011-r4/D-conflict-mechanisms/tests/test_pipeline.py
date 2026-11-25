#!/usr/bin/env python3
"""Standard-library regression tests for scope, contracts, dyes and attribution."""
import copy
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from compare_lib import (
    assemble_result, attribution_problems, derive_verdict, index_by, load_json,
    make_clusters, quantitative_compatibility, validate_workorder,
)
from source_io import prepare_documents


class AtlasTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.input_dir = ROOT / "examples" / "input"
        cls.case = load_json(cls.input_dir / "case.json")
        cls.workorder = load_json(cls.input_dir / "comparison-workorder.json")
        cls.registry, cls.paragraphs = prepare_documents(cls.workorder, cls.input_dir, ROOT / "tests" / "work")
        cls.evidence = index_by(cls.workorder["evidence_records"], "evidence_id")
        cls.propositions = index_by(cls.workorder["propositions"], "proposition_id")

    def test_valid_and_citation_complete(self):
        report = validate_workorder(self.workorder, self.case, self.registry)
        self.assertEqual(report["errors"], [])
        self.assertTrue(report["valid"])
        documents = {d["source_document_id"] for d in self.registry["documents"]}
        for row in self.workorder["common_matrix"]["rows"]:
            self.assertEqual({c["source_document_id"] for c in row["cells"]}, documents)
            for cell in row["cells"]:
                self.assertIn(cell["paragraph_id"], self.paragraphs[cell["source_document_id"]])

    def test_scope_complement_and_genuine_conflict(self):
        verdict, _ = derive_verdict(self.propositions["P-A-AMBIENT"], self.propositions["P-B-ACIDIC"], self.evidence)
        self.assertEqual(verdict, "complements")
        verdict, _ = derive_verdict(self.propositions["P-A-AMBIENT"], self.propositions["P-B-AMBIENT"], self.evidence)
        self.assertEqual(verdict, "genuine_conflict")

    def test_no_quantitative_pooling_across_dyes_or_datasets(self):
        left = copy.deepcopy(self.propositions["P-A-AMBIENT"])
        right = copy.deepcopy(self.propositions["P-B-AMBIENT"])
        gate = quantitative_compatibility(left, right, self.workorder, self.evidence)
        self.assertFalse(gate["allowed"])
        self.assertFalse(gate["checks"]["same_dataset"])
        right["pollutants"] = ["rhodamine B"]
        gate = quantitative_compatibility(left, right, self.workorder, self.evidence)
        self.assertFalse(gate["allowed"])
        self.assertFalse(gate["checks"]["pollutant"])
        self.assertFalse(gate["checks"]["same_dye"])
        self.assertTrue(any("different dyes" in reason for reason in gate["reasons"]))

    def test_exact_keys_reject_unknown_not_fuzzy(self):
        changed = copy.deepcopy(self.workorder)
        changed["propositions"][0]["proposition_key"] = "mb-capacity-composite-vs-control-ambient-near-match"
        with self.assertRaises(ValueError):
            make_clusters(changed)

    def test_speculation_cannot_be_supported(self):
        changed = copy.deepcopy(self.workorder)
        mechanism = next(m for m in changed["mechanism_attributions"] if m["mechanism_id"] == "M-PORE-SPECULATION")
        mechanism["status"] = "supported_by_direct_comparison"
        problems = attribution_problems(changed)
        self.assertTrue(any("speculation A-E2" in problem for problem in problems))
        self.assertTrue(any("no direct comparison" in problem for problem in problems))

    def test_dynamic_list_contract(self):
        out = ROOT / "tests" / "contract-list-output"
        out.mkdir(parents=True, exist_ok=True)
        workorder = copy.deepcopy(self.workorder)
        workorder["output_contract"] = ["case_id", "status", "summary", "artifacts", "sources", "uncertainty", "change_records", "additional_unreported"]
        validation = validate_workorder(self.workorder, self.case, self.registry)
        result = assemble_result(self.case, workorder, out, validation, make_clusters(self.workorder))
        self.assertEqual(result["case_id"], self.case["case_id"])
        self.assertEqual(result["output_contract"], workorder["output_contract"])
        self.assertIn("additional_unreported", result)
        self.assertEqual(result["additional_unreported"], "unreported")
        self.assertEqual(result["status"], "partial")
        self.assertIsInstance(result["artifacts"], list)

    def test_dynamic_dict_nested_contract_and_default(self):
        out = ROOT / "tests" / "contract-dict-output"
        out.mkdir(parents=True, exist_ok=True)
        (out / "comparison-matrix.md").write_text("test matrix\n", encoding="utf-8")
        (out / "conflict-atlas.md").write_text("test atlas\n", encoding="utf-8")
        workorder = copy.deepcopy(self.workorder)
        contract = {
            "artifacts": ["comparison-matrix.md", "conflict-atlas.md"],
            "result": {"properties": {"case_id": {}, "status": {}, "custom_field": {"default": "kept"}}},
        }
        workorder["output_contract"] = contract
        validation = validate_workorder(self.workorder, self.case, self.registry)
        result = assemble_result(self.case, workorder, out, validation, make_clusters(self.workorder))
        self.assertEqual(result["custom_field"], "kept")
        self.assertEqual(result["case_id"], self.case["case_id"])
        self.assertEqual(result["output_contract"], contract)
        self.assertEqual(result["status"], "success")


if __name__ == "__main__":
    unittest.main()
