#!/usr/bin/env python3
"""Standard-library regressions for semantic_coverage_auditor.py."""

import copy
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest


BUNDLE = Path(__file__).resolve().parents[1]
EXAMPLE = BUNDLE / "examples" / "synthetic"
AUDITOR = BUNDLE / "scripts" / "semantic_coverage_auditor.py"
TEST_DIR = Path(__file__).resolve().parent


def read_json(path):
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


class AuditorRegressionTests(unittest.TestCase):
    def setUp(self):
        self._temporary = tempfile.TemporaryDirectory(prefix=".auditor-test-", dir=str(TEST_DIR))
        self.work = Path(self._temporary.name)
        for name in ("case.json", "plan.json", "task.md", "source.json"):
            shutil.copyfile(str(EXAMPLE / name), str(self.work / name))
        shutil.copyfile(str(EXAMPLE / "authored_result.json"), str(self.work / "result.json"))
        self.case_path = self.work / "case.json"
        self.plan_path = self.work / "plan.json"
        self.result_path = self.work / "result.json"
        self.task_path = self.work / "task.md"
        self.source_path = self.work / "source.json"
        self.report_path = self.work / "audit_report.json"

    def tearDown(self):
        self._temporary.cleanup()

    def run_audit(self, with_task=True):
        command = [
            sys.executable,
            str(AUDITOR),
            "--plan",
            str(self.plan_path),
            "--result",
            str(self.result_path),
            "--case",
            str(self.case_path),
            "--source",
            str(self.source_path),
            "--report",
            str(self.report_path),
        ]
        if with_task:
            command.extend(("--task", str(self.task_path)))
        environment = dict(os.environ)
        environment["PYTHONDONTWRITEBYTECODE"] = "1"
        completed = subprocess.run(
            command,
            cwd=str(BUNDLE),
            env=environment,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
        self.assertTrue(
            self.report_path.exists(),
            "auditor did not write a report: stdout=%s stderr=%s"
            % (completed.stdout, completed.stderr),
        )
        return completed, read_json(self.report_path)

    def assert_codes(self, report, expected):
        actual = {finding["code"] for finding in report.get("findings", [])}
        self.assertTrue(expected.issubset(actual), "expected %r in %r" % (expected, actual))

    def write_direct_only_fixture(self):
        """Create a closed result with status, evidence, and scope only in matrix rows."""
        schema = {
            "type": "object",
            "additionalProperties": False,
            "required": ["case_id", "Q1"],
            "properties": {
                "case_id": {"type": "string", "const": "sidecar-only-001"},
                "Q1": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": ["item_id", "answer"],
                    "properties": {
                        "item_id": {"type": "string", "const": "Q1"},
                        "answer": {"type": "string", "minLength": 1},
                    },
                },
            },
        }
        row = {
            "item_id": "Q1",
            "question": "What mean was author-reported at 12 weeks?",
            "answer_path": "/Q1/answer",
            "status_path": None,
            "evidence_path": None,
            "checked_scope_path": None,
            "answer_status": "answered",
            "evidence": [
                {
                    "evidence_id": "Q1-E1",
                    "source_id": "SYNTH-LUMENFEN-2026",
                    "anchor": "S1",
                    "quote": "In the 12-week Lumenfen study, the author-reported mean orientation score was 82.4 points (SEM 1.2), based on 36 participants.",
                    "evidence_role": "author_reported",
                }
            ],
            "checked_scope": "Checked S1 in full for the 12-week author-reported mean and units.",
            "evidence_role": "author_reported",
            "checked_source_scope": [
                {"source_id": "SYNTH-LUMENFEN-2026", "anchors": ["S1"]}
            ],
            "required_answer_terms": ["82.4 points", "author-reported", "12-week"],
            "forbidden_generalizations": [],
            "derivation": None,
            "uncertainty": "The direct-only result intentionally has no status/evidence/scope keys.",
        }
        plan = {
            "case_id": "sidecar-only-001",
            "synthetic": True,
            "task_type": "qa",
            "output_schema": copy.deepcopy(schema),
            "answer_matrix": {"version": "1.0", "items": [row]},
            "item_id_contracts": [
                {"path": "/Q1", "id_property": "item_id", "ids": ["Q1"], "exact": True}
            ],
        }
        case = {
            "case_id": "sidecar-only-001",
            "synthetic": True,
            "output_contract": copy.deepcopy(schema),
        }
        result = {
            "case_id": "sidecar-only-001",
            "Q1": {
                "item_id": "Q1",
                "answer": "The 12-week mean was 82.4 points and was author-reported.",
            },
        }
        write_json(self.plan_path, plan)
        write_json(self.case_path, case)
        write_json(self.result_path, result)
        return plan, case, result

    def test_current_synthetic_contract_passes(self):
        completed, report = self.run_audit()
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertEqual(report["summary"], {"matrix_items": 3, "structural_findings": 0, "semantic_findings": 0})
        self.assertEqual(report["contract_authority"], "case#/output_contract")
        self.assertEqual(read_json(self.result_path)["Q3"]["evidence"], [])

    def test_changed_actual_case_contract_fails(self):
        case = read_json(self.case_path)
        case["output_contract"]["properties"]["Q1"]["properties"]["answer"]["maxLength"] = 90
        write_json(self.case_path, case)
        completed, report = self.run_audit()
        self.assertEqual(completed.returncode, 1, completed.stdout + completed.stderr)
        self.assert_codes(report, {"CONTRACT_DRIFT"})
        self.assertEqual(report["contract_authority"], "case#/output_contract")

    def test_case_and_fenced_task_contract_mismatch_fails(self):
        task = self.task_path.read_text(encoding="utf-8")
        changed = task.replace('"answer": {"type": "string", "minLength": 1, "maxLength": 900}', '"answer": {"type": "string", "minLength": 1, "maxLength": 899}', 1)
        self.assertNotEqual(changed, task)
        self.task_path.write_text(changed, encoding="utf-8")
        completed, report = self.run_audit()
        self.assertEqual(completed.returncode, 1, completed.stdout + completed.stderr)
        self.assert_codes(report, {"CONTRACT_DRIFT"})

    def test_recursive_unknown_keyword_and_composition_are_exit_2(self):
        original_case = read_json(self.case_path)
        for keyword, value in (
            ("patternProperties", {}),
            ("anyOf", [{"type": "string"}, {"type": "null"}]),
            ("oneOf", [{"type": "string"}, {"type": "null"}]),
        ):
            with self.subTest(keyword=keyword):
                case = copy.deepcopy(original_case)
                case["output_contract"]["properties"]["Q1"]["properties"]["answer"][keyword] = value
                write_json(self.case_path, case)
                completed, report = self.run_audit()
                self.assertEqual(completed.returncode, 2, completed.stdout + completed.stderr)
                self.assertEqual(report["overall_status"], "MALFORMED_INPUT")
                self.assertIn(keyword, report["error"])

    def test_non_object_case_contract_cannot_trigger_task_fallback(self):
        case = read_json(self.case_path)
        case["output_contract"] = None
        write_json(self.case_path, case)
        completed, report = self.run_audit()
        self.assertEqual(completed.returncode, 2)
        self.assertIn("must be a JSON object", report["error"])

    def test_out_of_scope_evidence_is_a_semantic_finding(self):
        result = read_json(self.result_path)
        source = read_json(self.source_path)
        table_text = next(section["text"] for section in source["sections"] if section["anchor"] == "T1")
        result["Q1"]["evidence"][0].update(
            {"anchor": "T1", "quote": table_text, "evidence_role": "author_reported"}
        )
        write_json(self.result_path, result)
        completed, report = self.run_audit()
        self.assertEqual(completed.returncode, 0, completed.stdout + completed.stderr)
        self.assertEqual(report["structural_status"], "PASS")
        self.assert_codes(report, {"EVIDENCE_OUTSIDE_CHECKED_SCOPE"})

    def test_sidecar_only_closed_direct_answer_contract_can_audit(self):
        self.write_direct_only_fixture()
        completed, report = self.run_audit(with_task=False)
        self.assertEqual(completed.returncode, 0, completed.stdout + completed.stderr)
        self.assertEqual(report["summary"], {"matrix_items": 1, "structural_findings": 0, "semantic_findings": 0})
        self.assertEqual(report["contract_authority"], "case#/output_contract")

    def test_sidecar_evidence_also_enforces_checked_scope(self):
        plan, _, _ = self.write_direct_only_fixture()
        source = read_json(self.source_path)
        table_text = next(section["text"] for section in source["sections"] if section["anchor"] == "T1")
        evidence = plan["answer_matrix"]["items"][0]["evidence"][0]
        evidence.update({"anchor": "T1", "quote": table_text})
        write_json(self.plan_path, plan)
        completed, report = self.run_audit(with_task=False)
        self.assertEqual(completed.returncode, 0, completed.stdout + completed.stderr)
        self.assert_codes(report, {"EVIDENCE_OUTSIDE_CHECKED_SCOPE"})
        finding = next(item for item in report["findings"] if item["code"] == "EVIDENCE_OUTSIDE_CHECKED_SCOPE")
        self.assertEqual(finding["path"], "/answer_matrix/items/0/evidence/0")

    def test_every_declared_property_is_required(self):
        plan, case, _ = self.write_direct_only_fixture()
        for document in (plan, case):
            schema = document["output_schema"] if "output_schema" in document else document["output_contract"]
            schema["properties"]["Q1"]["properties"]["optional_note"] = {"type": "string"}
        write_json(self.plan_path, plan)
        write_json(self.case_path, case)
        completed, report = self.run_audit(with_task=False)
        self.assertEqual(completed.returncode, 1, completed.stdout + completed.stderr)
        self.assert_codes(report, {"DECLARED_PROPERTY_MISSING"})

    def test_missing_source_scope_requires_inventory_gap(self):
        plan, _, _ = self.write_direct_only_fixture()
        row = plan["answer_matrix"]["items"][0]
        row.update(
            {
                "answer_status": "missing",
                "evidence": [],
                "checked_source_scope": [],
                "required_answer_terms": [],
                "inventory_gap": "The supplied case contained no source file for Q1; this was confirmed by the material inventory.",
                "checked_scope": "No source was available to read; checked the supplied material inventory rather than claiming non-reporting.",
                "evidence_role": "no_evidence_expected",
            }
        )
        write_json(self.plan_path, plan)
        completed, report = self.run_audit(with_task=False)
        self.assertEqual(completed.returncode, 0, completed.stdout + completed.stderr)
        self.assertEqual(report["summary"]["semantic_findings"], 0)

        row.pop("inventory_gap")
        write_json(self.plan_path, plan)
        completed, report = self.run_audit(with_task=False)
        self.assertEqual(completed.returncode, 0, completed.stdout + completed.stderr)
        self.assert_codes(report, {"INVENTORY_GAP_REQUIRED"})

    def test_empty_scope_never_passes_for_other_statuses(self):
        plan, _, _ = self.write_direct_only_fixture()
        row = plan["answer_matrix"]["items"][0]
        row.update(
            {
                "evidence": [],
                "checked_source_scope": [],
                "required_answer_terms": [],
                "inventory_gap": "An explanation alone does not make a non-missing status valid.",
                "evidence_role": "no_evidence_expected",
            }
        )
        for status in ("answered", "not_reported", "unreadable"):
            with self.subTest(status=status):
                row["answer_status"] = status
                write_json(self.plan_path, plan)
                completed, report = self.run_audit(with_task=False)
                self.assertEqual(completed.returncode, 0, completed.stdout + completed.stderr)
                self.assert_codes(report, {"CHECKED_SOURCE_SCOPE_REQUIRED"})

    def test_task_only_fallback_applies_when_case_contract_is_absent(self):
        case = read_json(self.case_path)
        del case["output_contract"]
        write_json(self.case_path, case)
        completed, report = self.run_audit()
        self.assertEqual(completed.returncode, 0, completed.stdout + completed.stderr)
        self.assertEqual(report["contract_authority"], "task#")

    def test_existing_additional_property_failure_still_works(self):
        result = read_json(self.result_path)
        result["Q1"]["helper_note"] = "not allowed by the closed nested object"
        write_json(self.result_path, result)
        completed, report = self.run_audit()
        self.assertEqual(completed.returncode, 1, completed.stdout + completed.stderr)
        self.assert_codes(report, {"ADDITIONAL_PROPERTY"})

    def test_example_runner_and_item_specific_reviews(self):
        output_root = self.work / "example-output"
        environment = dict(os.environ)
        environment["PYTHONDONTWRITEBYTECODE"] = "1"
        completed = subprocess.run(
            ["bash", str(BUNDLE / "scripts" / "run_example.sh"), str(output_root)],
            cwd=str(BUNDLE),
            env=environment,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
        self.assertEqual(completed.returncode, 0, completed.stdout + completed.stderr)
        review = read_json(output_root / "semantic_review.json")
        notes = {
            item["item_id"]: set(item["adversarial_review"].values())
            for item in review["items"]
            if item["item_id"] != "Q2"
        }
        self.assertEqual(set(notes), {"Q1", "Q3"})
        self.assertTrue(notes["Q1"].isdisjoint(notes["Q3"]))
        self.assertIn(
            "No CI formula was applied and no interval is represented as author-reported; the task prohibits deriving one from SEM here.",
            notes["Q3"],
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
