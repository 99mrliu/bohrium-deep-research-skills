#!/usr/bin/env python3
"""Regression tests for task statuses and output-contract extraction."""
from __future__ import annotations

import copy
import importlib.util
from pathlib import Path
import sys
import unittest


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "oracle_lab.py"
MODULE_SPEC = importlib.util.spec_from_file_location("independent_oracle_lab", SCRIPT)
assert MODULE_SPEC is not None and MODULE_SPEC.loader is not None
oracle_lab = importlib.util.module_from_spec(MODULE_SPEC)
sys.modules[MODULE_SPEC.name] = oracle_lab
MODULE_SPEC.loader.exec_module(oracle_lab)


class ContractExtractionTests(unittest.TestCase):
    def test_supported_contract_shapes(self) -> None:
        scenarios = [
            (
                "list",
                ["case_id", "alpha", {"name": "beta"}, {"key": "status"}, "alpha"],
                ["case_id", "alpha", "beta", "status"],
            ),
            (
                "plain_mapping",
                {"alpha": "description", "status": {"type": "string"}},
                ["alpha", "status"],
            ),
            (
                "fields_and_required_fields",
                {
                    "fields": ["alpha", {"name": "beta"}],
                    "required_fields": ["case_id", "status", "sources", "uncertainty", "change_records"],
                },
                ["alpha", "beta", "case_id", "status", "sources", "uncertainty", "change_records"],
            ),
            (
                "fields_mapping",
                {
                    "fields": {"alpha": {"type": "object"}, "beta": {"type": "array"}},
                    "required_fields": {"sources": True, "status": True},
                },
                ["alpha", "beta", "sources", "status"],
            ),
            (
                "json_schema",
                {
                    "$schema": "https://json-schema.org/draft/2020-12/schema",
                    "type": "object",
                    "properties": {"case_id": {"type": "string"}, "alpha": {"type": "object"}},
                    "required": ["case_id", "status", "sources", "uncertainty", "change_records"],
                },
                ["case_id", "alpha", "status", "sources", "uncertainty", "change_records"],
            ),
        ]
        for label, contract, expected in scenarios:
            with self.subTest(label=label):
                actual = oracle_lab.extract_contract_fields({"output_contract": contract})
                self.assertEqual(expected, actual)
                self.assertNotIn("fields", actual)
                self.assertNotIn("required_fields", actual)
                self.assertNotIn("properties", actual)
                self.assertNotIn("required", actual)


class ResultStatusTests(unittest.TestCase):
    def setUp(self) -> None:
        witness_keys = {
            "materials_environment_parameters",
            "two_candidate_materials_reviewed",
            "paper_table_figure_comparisons",
            "difference_attribution",
            "raw_data_repository_status",
        }
        self.spec = {
            "candidates": [{"id": "a"}, {"id": "b"}],
            "_witness": {key: {"audited": True} for key in witness_keys},
        }
        self.report = {
            "completion_status": "complete",
            "spec_sha256": "0" * 64,
            "sources": [{"path": "paper.pdf", "loaded": True}],
            "uncertainties": [],
            "paper_vs_oracle": {"status": "mismatched"},
            "candidates": [
                {
                    "id": identifier,
                    "status": "passed",
                    "passed": True,
                    "trials": [{"candidate_vs_paper": {"status": "mismatched"}}],
                }
                for identifier in ("a", "b")
            ],
        }
        self.case = {
            "case_id": "formal-001",
            "output_contract": {
                "type": "object",
                "properties": {
                    "case_id": {"type": "string"},
                    "status": {"type": "string"},
                    "sources": {"type": "array"},
                    "uncertainty": {"type": "array"},
                    "change_records": {"type": "array"},
                    "reproduction_summary": {"type": "object"},
                    "paper_comparison": {"type": "object"},
                },
                "required": ["case_id", "status", "sources", "uncertainty", "change_records"],
            },
        }

    def make_result(self, report=None, case=None, spec=None, case_error=None):
        return oracle_lab.make_result(
            copy.deepcopy(self.report if report is None else report),
            copy.deepcopy(self.case if case is None else case),
            Path("case.json"),
            case_error,
            copy.deepcopy(self.spec if spec is None else spec),
            Path("output"),
            Path("output/oracle_report.json"),
            Path("output/oracle_report.md"),
        )

    def test_success_allows_paper_mismatch(self) -> None:
        result = self.make_result()
        self.assertEqual("success", result["status"])
        self.assertEqual("success", result["reproduction_summary"]["status"])
        self.assertEqual("mismatched", result["paper_comparison"]["status"])
        self.assertIn(result["status"], oracle_lab.RESULT_STATUSES)
        for field in oracle_lab.REQUIRED_RESULT_FIELDS:
            self.assertIn(field, result)
        self.assertNotIn("type", result)
        self.assertNotIn("properties", result)
        self.assertNotIn("required", result)

    def test_partial_conditions(self) -> None:
        scenarios = []

        synthetic_report = copy.deepcopy(self.report)
        synthetic_spec = copy.deepcopy(self.spec)
        synthetic_spec["evaluation_mode"] = "synthetic"
        scenarios.append(("synthetic", synthetic_report, self.case, synthetic_spec, None))

        failed_report = copy.deepcopy(self.report)
        failed_report["candidates"][0]["status"] = "failed"
        scenarios.append(("candidate_failure", failed_report, self.case, self.spec, None))

        source_report = copy.deepcopy(self.report)
        source_report["sources"][0]["loaded"] = False
        scenarios.append(("missing_source", source_report, self.case, self.spec, None))

        running_report = copy.deepcopy(self.report)
        running_report["completion_status"] = "partial"
        scenarios.append(("incomplete_execution", running_report, self.case, self.spec, None))

        missing_trial_report = copy.deepcopy(self.report)
        missing_trial_report["candidates"][0]["trials"] = []
        scenarios.append(("missing_trial", missing_trial_report, self.case, self.spec, None))

        no_witness_spec = copy.deepcopy(self.spec)
        no_witness_spec["_witness"] = {}
        scenarios.append(("missing_witness", self.report, self.case, no_witness_spec, None))

        unknown_case = copy.deepcopy(self.case)
        unknown_case["output_contract"] = ["case_id", "status", "unprovided_evidence"]
        scenarios.append(("missing_contract_evidence", self.report, unknown_case, self.spec, None))

        for label, report, case, spec, case_error in scenarios:
            with self.subTest(label=label):
                result = self.make_result(report, case, spec, case_error)
                self.assertEqual("partial", result["status"])
                if label == "missing_contract_evidence":
                    self.assertEqual(["unprovided_evidence"], result["missing_required_evidence"])

    def test_scalar_reproduction_summary_does_not_break_status(self) -> None:
        spec = copy.deepcopy(self.spec)
        spec["contract_values"] = {"reproduction_summary": "evidence-backed concise summary"}
        result = self.make_result(spec=spec)
        self.assertEqual("success", result["status"])
        self.assertEqual("evidence-backed concise summary", result["reproduction_summary"])

    def test_unable_conditions(self) -> None:
        missing_id_case = copy.deepcopy(self.case)
        del missing_id_case["case_id"]
        result = self.make_result(case=missing_id_case)
        self.assertEqual("unable", result["status"])
        self.assertIsNone(result["case_id"])

        run_error_report = copy.deepcopy(self.report)
        run_error_report["run_error"] = "required execution backend unavailable"
        result = self.make_result(report=run_error_report)
        self.assertEqual("unable", result["status"])

    def test_result_status_enumeration(self) -> None:
        self.assertEqual({"success", "partial", "unable", "refused"}, set(oracle_lab.RESULT_STATUSES))
        for result in (self.make_result(), self.make_result(case={})):
            self.assertIn(result["status"], oracle_lab.RESULT_STATUSES)
            self.assertNotEqual("complete", result["status"])


if __name__ == "__main__":
    unittest.main()
