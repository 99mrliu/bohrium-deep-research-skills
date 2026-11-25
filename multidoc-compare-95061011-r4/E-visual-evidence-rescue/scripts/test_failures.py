#!/usr/bin/env python3
"""Executable negative tests plus parser and list/dict contract checks."""

import copy
import importlib.util
import json
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TOOL = ROOT / "scripts" / "visual_evidence.py"
INPUT = ROOT / "example" / "input"
WORK = ROOT / "example" / "work"
SPEC = importlib.util.spec_from_file_location("visual_evidence", TOOL)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class RescueTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.case = json.loads((INPUT / "case.json").read_text(encoding="utf-8"))
        cls.workorder = json.loads((INPUT / "comparison-workorder.json").read_text(encoding="utf-8"))
        cls.manifest_path = WORK / "ingest-manifest.json"
        if not cls.manifest_path.is_file():
            raise RuntimeError("Run example/run_example.sh before scripts/test_failures.py")

    def expect_invalid(self, mutated, expected_text):
        with tempfile.TemporaryDirectory(prefix="negative-", dir=WORK) as temp:
            path = Path(temp) / "workorder.json"
            path.write_text(json.dumps(mutated, ensure_ascii=False), encoding="utf-8")
            completed = subprocess.run(
                ["python3", str(TOOL), "validate", "--case", str(INPUT / "case.json"),
                 "--workorder", str(path), "--manifest", str(self.manifest_path)],
                text=True, capture_output=True, check=False,
            )
            self.assertNotEqual(completed.returncode, 0, completed.stdout + completed.stderr)
            self.assertIn(expected_text, completed.stderr, completed.stdout + completed.stderr)

    def test_caption_only_numeric_claim_fails(self):
        changed = copy.deepcopy(self.workorder)
        record = next(r for r in changed["documents"][2]["extractions"] if r["record_id"] == "G-RETENTION-EST")
        record.update({"region_id": "DOC_GAMMA:caption-001", "status": "reported", "value": "48%", "estimate": None, "range": None})
        self.expect_invalid(changed, "caption-only numeric claim")

    def test_missing_region_fails(self):
        changed = copy.deepcopy(self.workorder)
        changed["documents"][0]["extractions"][0]["region_id"] = "DOC_A:absent-region"
        self.expect_invalid(changed, "missing region")

    def test_unlike_dyes_cannot_be_pooled(self):
        changed = copy.deepcopy(self.workorder)
        source = changed["documents"][0]["extractions"][0]
        derived = copy.deepcopy(source)
        derived.update({"record_id": "A-INVALID-POOL", "status": "derived", "value": 80.5,
                        "derivation": "(82 + 79) / 2", "derived_from": ["A-REMOVAL-MO", "A-REMOVAL-CV"]})
        changed["documents"][0]["extractions"].append(derived)
        self.expect_invalid(changed, "incompatible derived quantitative inputs")

    def test_quantitative_budget_must_be_known(self):
        changed = copy.deepcopy(self.workorder)
        source = changed["documents"][0]["extractions"][0]
        record = copy.deepcopy(source)
        record.update({"record_id": "A-MISSING-BUDGET", "budget": ""})
        changed["documents"][0]["extractions"].append(record)
        self.expect_invalid(changed, "missing qualifiers ['budget']")

    def test_output_contract_list_and_dict(self):
        listed = ["matrix", {"name": "sources"}, {"uncertainty": {"type": "array"}}]
        as_dict = {"matrix": {"type": "file"}, "sources": {"type": "array"}, "uncertainty": {"type": "array"}}
        self.assertEqual([key for key, _ in MODULE.contract_keys(listed)], ["matrix", "sources", "uncertainty"])
        self.assertEqual([key for key, _ in MODULE.contract_keys(as_dict)], ["matrix", "sources", "uncertainty"])

    def test_terminal_form_feed_newline_is_not_a_phantom_page(self):
        self.assertEqual(len(MODULE.page_texts("page one\f\n")), 1)
        self.assertEqual(len(MODULE.page_texts("page one\fpage two\f")), 2)

    def test_layout_parser_carries_multirow_material(self):
        text = (INPUT / "documents" / "alpha.txt").read_text(encoding="utf-8")
        regions = MODULE.parse_layout_text(text, "DOC_A", "DOC_A:caption-001")
        self.assertEqual(len(regions), 2)
        self.assertEqual(regions[1]["cells"][0]["value"], "Alpha-7")
        self.assertEqual(regions[1]["multirow_context"], {"Material": "Alpha-7"})
        self.assertEqual(regions[0]["page"], 1)
        self.assertEqual(regions[0]["table"]["units"]["Removal (%) {test}"], "%")

    def test_result_has_exact_case_and_all_contract_fields(self):
        result = json.loads((ROOT / "example" / "output" / "result.json").read_text(encoding="utf-8"))
        self.assertEqual(result["case_id"], self.case["case_id"])
        for key in self.case["output_contract"]:
            self.assertIn(key, result)
        self.assertFalse(result["validation"]["pooling_performed"])
        status_counts = result["quality_summary"]["extraction_status_counts"]
        self.assertEqual(status_counts["read_off_figure"], 1)
        self.assertGreaterEqual(status_counts["not_reported"], 1)
        self.assertEqual(status_counts["noncomparable"], 1)


if __name__ == "__main__":
    unittest.main(verbosity=2)
