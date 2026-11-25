#!/usr/bin/env python3
"""Stdlib regression tests; every fixture and assertion is SYNTHETIC."""
from __future__ import annotations

import copy
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.dont_write_bytecode = True
SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))
import field_contract as fc  # noqa: E402

ROOT = SCRIPT_DIR.parent
MINIMAL = ROOT / "examples" / "minimal"


def load(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


class FieldContractTests(unittest.TestCase):
    def setUp(self):
        # Temporary runtimes stay inside this skill bundle and are removed after each test.
        self.temporary = tempfile.TemporaryDirectory(prefix=".synthetic-test-", dir=str(MINIMAL))
        self.base = Path(self.temporary.name)
        self.input_dir = self.base / "input"
        self.work = self.base / "work"
        self.output = self.base / "output"
        import shutil
        shutil.copytree(MINIMAL / "input", self.input_dir)
        code = fc.main(["init", "--input-dir", str(self.input_dir),
                        "--work", str(self.work), "--output", str(self.output)])
        self.assertEqual(code, 0)
        self.contract = load(self.work / "acceptance-contract.json")
        self.decisions = load(MINIMAL / "agent" / "decisions.json")

    def tearDown(self):
        self.temporary.cleanup()

    def finalize(self, decisions=None):
        path = self.base / "decisions.json"
        fc.write_json(path, self.decisions if decisions is None else decisions)
        return fc.main(["finalize", "--work", str(self.work), "--output", str(self.output),
                        "--source-register", str(MINIMAL / "agent" / "source-register.json"),
                        "--decisions", str(path)])

    def test_skeleton_and_tests_precede_candidates(self):
        result = load(self.output / "result.json")
        self.assertEqual(result["status"], "insufficient_evidence")
        self.assertEqual(len(result["result"]["fields"]), 5)
        self.assertTrue(all(row["status"] == "extraction_failed" for row in result["result"]["fields"]))
        events = load(self.work / "runtime-events.json")["events"]
        self.assertEqual([event["candidate_values_read"] for event in events], [False, False])
        for field in self.contract["fields"]:
            self.assertEqual(len(field["acceptance_tests"]), 10)
            self.assertTrue(all(test["state_before_candidates"] == "pending" for test in field["acceptance_tests"]))
        self.assertEqual(load(MINIMAL / "agent" / "decisions.json")["contract_sha256"],
                         self.contract["contract_sha256"])

    def test_synthetic_end_to_end_statuses_and_decoy_rejection(self):
        self.assertEqual(self.finalize(), 0)
        result = load(self.output / "result.json")
        self.assertEqual(result["status"], "partial")
        self.assertTrue(result["synthetic"])
        fields = {row["field_id"]: row for row in result["result"]["fields"]}
        self.assertEqual(fields["F_YIELD_120C"]["status"], "reported")
        self.assertEqual(fields["F_YIELD_120C"]["scalar"], 72)
        self.assertEqual(fields["F_YIELD_120C"]["paragraph_id"], "p-yield-120C")
        self.assertEqual(fields["F_YIELD_120C"]["experimental_condition"],
                         fields["F_YIELD_120C"]["condition"])
        rejected = fields["F_YIELD_120C"]["rejected_candidates"][0]
        self.assertEqual(rejected["evidence"]["paragraph_id"], "p-decoy-80C")
        self.assertEqual(rejected["failed_test_id"], "F_YIELD_120C::required_condition")
        self.assertEqual(fields["F_YIELD_SD_120C"]["status"], "not_reported")
        self.assertIsNone(fields["F_YIELD_SD_120C"]["scalar"])
        self.assertEqual(fields["F_SELECTIVITY_120C"]["status"], "source_conflict")
        self.assertIsNone(fields["F_SELECTIVITY_120C"]["scalar"])
        self.assertEqual([row["scalar"] for row in fields["F_SELECTIVITY_120C"]["conflict_candidates"]], [90, 88])
        self.assertEqual(fields["F_CONVERSION_120C"]["status"], "extraction_failed")
        self.assertEqual(fields["F_AUTHOR_OUTLOOK"]["modality"], "author_speculation")
        self.assertEqual(result["result"]["fields"], result["result"]["field_results"])
        self.assertTrue((self.output / "contract-audit.md").read_text(encoding="utf-8").startswith("# SYNTHETIC"))

    def test_negative_same_number_wrong_condition_is_not_reported(self):
        bad = copy.deepcopy(self.decisions)
        row = bad["decisions"][0]
        row["experimental_condition"] = "temperature=80 °C AND solvent=toluene"
        row["paragraph_id"] = "p-decoy-80C"
        row["quote"] = "At 80 °C in toluene, Catalyst X gave a yield of 72%."
        row["evidence"][0] = {"source_id": "S_SYNTHETIC", "page": 1,
                              "paragraph_id": "p-decoy-80C", "quote": row["quote"]}
        for check in row["acceptance_checks"]:
            if check["test_id"] == "F_YIELD_120C::required_condition":
                check["passed"] = False
                check["rationale"] = "SYNTHETIC negative control: 80 °C violates the precompiled 120 °C requirement."
        self.assertEqual(self.finalize(bad), 2)
        # Finalization is all-or-nothing: the valid conservative skeleton remains untouched.
        self.assertEqual(load(self.output / "result.json")["result"]["fields"][0]["failure_reason"],
                         "Awaiting agent-authored adjudication.")

    def test_negative_literal_from_another_paragraph_fails_exact_binding(self):
        bad = copy.deepcopy(self.decisions)
        bad["decisions"][0]["evidence"][0]["quote"] = "At 80 °C in toluene, Catalyst X gave a yield of 72%."
        self.assertEqual(self.finalize(bad), 2)

    def test_unresolved_schema_axis_blocks_until_question_schema_amendment(self):
        target = load(self.input_dir / "target-fields.json")
        del target["fields"][0]["metric_identity"]
        fc.write_json(self.input_dir / "target-fields.json", target)
        self.assertEqual(fc.main(["init", "--input-dir", str(self.input_dir),
                                  "--work", str(self.work), "--output", str(self.output)]), 0)
        contract = load(self.work / "acceptance-contract.json")
        self.assertIn("metric_identity is not explicit in target schema", contract["fields"][0]["blocking_issues"])
        self.decisions["contract_sha256"] = contract["contract_sha256"]
        self.assertEqual(self.finalize(), 2)  # unresolved metric_identity, not merely a hash mismatch
        amendments = {"amendments": [{
            "field_id": "F_YIELD_120C",
            "set": {"metric_identity": "product yield"},
            "rationale": "SYNTHETIC: resolved from the question 'What yield'; no candidate value consulted."
        }]}
        fc.write_json(self.base / "amendments.json", amendments)
        self.assertEqual(fc.main(["amend-contract", "--work", str(self.work),
                                  "--amendments", str(self.base / "amendments.json")]), 0)
        amended = load(self.work / "acceptance-contract.json")
        self.assertEqual(amended["fields"][0]["blocking_issues"], [])
        self.assertNotEqual(amended["contract_sha256"], self.contract["contract_sha256"])
        # Old decisions remain hash-bound to the old contract and cannot silently carry over.
        self.assertEqual(self.finalize(), 2)


if __name__ == "__main__":
    unittest.main(verbosity=2)
