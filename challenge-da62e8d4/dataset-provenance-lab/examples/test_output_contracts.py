#!/usr/bin/env python3
"""Regression tests for output_contract shapes; writes evidence under a given directory."""

import copy
import importlib
import json
import subprocess
import sys
import unittest
from pathlib import Path


sys.dont_write_bytecode = True
if len(sys.argv) != 2:
    raise SystemExit(f"Usage: {sys.argv[0]} /absolute/writable/verification-output")
OUTPUT_ROOT = Path(sys.argv.pop()).expanduser().resolve()
EXAMPLE_DIR = Path(__file__).resolve().parent
BUNDLE_DIR = EXAMPLE_DIR.parent
SCRIPTS_DIR = BUNDLE_DIR / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))
audit_dataset = importlib.import_module("audit_dataset")
check_result = importlib.import_module("check_result")

BASE_CASE = json.loads((EXAMPLE_DIR / "case.json").read_text(encoding="utf-8"))
MANIFEST = EXAMPLE_DIR / "manifest.json"
TASK = EXAMPLE_DIR / "task.md"
STANDARD_FIELDS = ["case_id", "status", "sources", "uncertainty", "change_records"]


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def run_command(command, expected_status):
    completed = subprocess.run(command, text=True, capture_output=True, check=False)
    if completed.returncode != expected_status:
        raise AssertionError(
            f"Command returned {completed.returncode}, expected {expected_status}: {command}\n"
            f"stdout:\n{completed.stdout}\nstderr:\n{completed.stderr}"
        )
    return completed.stdout + completed.stderr


def validate_case(case):
    return {
        "audit": audit_dataset.case_output_contract(case),
        "checker": check_result.output_contract_fields(case),
        "required": audit_dataset.case_required_fields(case),
    }


class ContractShapeTests(unittest.TestCase):
    maxDiff = None

    def assert_parse(self, contract, fields, required):
        case = {"case_id": "shape-test", "output_contract": contract}
        parsed = validate_case(case)
        expected = {"fields": fields, "required_fields": required}
        self.assertEqual(parsed["audit"], expected)
        self.assertEqual(parsed["checker"], expected)
        self.assertEqual(parsed["required"], required)
        self.assertEqual(check_result.required_fields(case), required)

    def test_list_mapping_fields_and_required_fields_shapes(self):
        shapes = [
            (["alpha", {"name": "beta"}], ["alpha", "beta"], ["alpha", "beta"]),
            ({"alpha": {"type": "string"}, "status": {"type": "string"}},
             ["alpha", "status"], ["alpha", "status"]),
            ({"fields": [{"name": "alpha"}, "beta"]}, ["alpha", "beta"], ["alpha", "beta"]),
            ({"fields": {"alpha": {}, "beta": {}}, "required_fields": ["alpha"]},
             ["alpha", "beta"], ["alpha"]),
            ({"required_fields": {"alpha": {}, "status": {}}},
             ["alpha", "status"], ["alpha", "status"]),
        ]
        for contract, fields, required in shapes:
            with self.subTest(contract=contract):
                self.assert_parse(contract, fields, required)

    def test_json_schema_direct_and_nested_shapes(self):
        schema = {
            "type": "object",
            "properties": {"alpha": {"type": "string"}, "optional_note": {"type": "object"}},
            "required": ["alpha"],
        }
        for contract in (schema, {"schema": schema}, {"json_schema": schema}):
            with self.subTest(contract=contract):
                self.assert_parse(contract, ["alpha", "optional_note"], ["alpha"])
        self.assert_parse(
            {"properties": {"optional_note": {"type": "object"}}},
            ["optional_note"],
            [],
        )

    def test_malformed_contracts_are_rejected_independently(self):
        malformed = [
            [],
            ["alpha", "alpha"],
            [{"type": "string"}],
            {"fields": []},
            {"properties": {}},
            {"properties": {"alpha": {}}, "required": ["not_declared"]},
            {"properties": {"alpha": {}}, "required": "alpha"},
            ["output_contract"],
        ]
        for contract in malformed:
            case = {"case_id": "bad-contract", "output_contract": contract}
            with self.subTest(contract=contract):
                with self.assertRaises(audit_dataset.AuditError):
                    audit_dataset.case_output_contract(case)
                with self.assertRaises(ValueError):
                    check_result.output_contract_fields(case)

    def test_only_the_four_result_statuses_are_allowed(self):
        case = {"case_id": "status-test", "output_contract": ["data_quality"]}
        base = {
            "case_id": "status-test",
            "sources": [],
            "uncertainty": [],
            "change_records": [],
            "data_quality": [],
        }
        for status in ("success", "partial", "unable", "refused"):
            with self.subTest(status=status):
                self.assertEqual(check_result.validate(case, dict(base, status=status)), [])
        errors = check_result.validate(case, dict(base, status="completed"))
        self.assertTrue(any("status must be one of" in error for error in errors))

    def run_shape(self, name, contract, all_fields, required_fields):
        output_dir = OUTPUT_ROOT / name
        case = copy.deepcopy(BASE_CASE)
        case["case_id"] = f"synthetic-contract-{name}"
        case["output_contract"] = contract
        case_path = output_dir / "case.json"
        result_path = output_dir / "result.json"
        write_json(case_path, case)
        self.assertEqual(audit_dataset.case_output_contract(case)["fields"], all_fields)
        self.assertEqual(check_result.required_fields(case), required_fields)

        audit_log = run_command([
            sys.executable, str(SCRIPTS_DIR / "audit_dataset.py"),
            "--manifest", str(MANIFEST), "--case", str(case_path),
            "--task", str(TASK), "--output-dir", str(output_dir),
        ], 0)
        (output_dir / "audit_run.log").write_text(audit_log, encoding="utf-8")
        positive_log = run_command([
            sys.executable, str(SCRIPTS_DIR / "check_result.py"),
            "--case", str(case_path), "--result", str(result_path),
        ], 0)
        (output_dir / "positive_validation.log").write_text(positive_log, encoding="utf-8")

        result = json.loads(result_path.read_text(encoding="utf-8"))
        self.assertEqual(result["status"], "partial")
        self.assertEqual(result["case_id"], case["case_id"])
        self.assertNotIn("output_contract", result)
        for field in all_fields:
            self.assertIn(field, result)
        for field in STANDARD_FIELDS:
            if field in all_fields:
                self.assertNotEqual(result[field], {"status": "unavailable"})
        self.assertIsInstance(result["sources"], list)
        self.assertIsInstance(result["uncertainty"], list)
        self.assertIsInstance(result["change_records"], list)
        return output_dir, case_path, result

    def reject_missing_required(self, output_dir, case_path, result, required_field):
        negative = copy.deepcopy(result)
        negative.pop(required_field)
        negative_path = output_dir / "negative_result.json"
        write_json(negative_path, negative)
        log = run_command([
            sys.executable, str(SCRIPTS_DIR / "check_result.py"),
            "--case", str(case_path), "--result", str(negative_path),
        ], 2)
        (output_dir / "negative_validation.log").write_text(log, encoding="utf-8")
        self.assertIn(f"missing top-level contract field: {required_field}", log)

    def test_list_contract_positive_negative_and_standard_fields(self):
        fields = STANDARD_FIELDS + ["data_quality", "task_specific_finding"]
        output_dir, case_path, result = self.run_shape("list", fields, fields, fields)
        self.assertNotIn("limitations", result)
        self.assertEqual(result["task_specific_finding"]["status"], "unavailable")
        self.assertIs(result["task_specific_finding"]["completion_required"], True)
        self.assertTrue(any("task_specific_finding" in item for item in result["uncertainty"]))
        report = (output_dir / "report.md").read_text(encoding="utf-8")
        self.assertIn("Audit covers only the explicitly listed files", report)
        self.reject_missing_required(output_dir, case_path, result, "data_quality")

    def test_json_schema_positive_negative_and_optional_property(self):
        properties = {
            "case_id": {"type": "string"},
            "status": {"type": "string", "enum": ["success", "partial", "unable", "refused"]},
            "sources": {"type": "array"},
            "uncertainty": {"type": "array"},
            "change_records": {"type": "array"},
            "data_quality": {"type": "array"},
            "optional_note": {"type": "object"},
        }
        required = STANDARD_FIELDS + ["data_quality"]
        contract = {"type": "object", "properties": properties, "required": required}
        all_fields = list(properties)
        output_dir, case_path, result = self.run_shape(
            "json_schema", contract, all_fields, required
        )
        self.assertNotIn("limitations", result)
        self.assertEqual(result["optional_note"]["status"], "unavailable")
        report = (output_dir / "report.md").read_text(encoding="utf-8")
        self.assertIn("Audit covers only the explicitly listed files", report)

        without_optional = copy.deepcopy(result)
        without_optional.pop("optional_note")
        optional_path = output_dir / "without_optional_result.json"
        write_json(optional_path, without_optional)
        optional_log = run_command([
            sys.executable, str(SCRIPTS_DIR / "check_result.py"),
            "--case", str(case_path), "--result", str(optional_path),
        ], 0)
        (output_dir / "optional_omitted_validation.log").write_text(optional_log, encoding="utf-8")
        self.reject_missing_required(output_dir, case_path, result, "data_quality")

        invalid_case = copy.deepcopy(BASE_CASE)
        invalid_case["case_id"] = "synthetic-contract-invalid-json-schema"
        invalid_case["output_contract"] = {
            "properties": {"data_quality": {"type": "array"}},
            "required": ["not_declared"],
        }
        invalid_dir = OUTPUT_ROOT / "invalid_json_schema"
        invalid_path = invalid_dir / "case.json"
        write_json(invalid_path, invalid_case)
        invalid_log = run_command([
            sys.executable, str(SCRIPTS_DIR / "audit_dataset.py"),
            "--manifest", str(MANIFEST), "--case", str(invalid_path),
            "--task", str(TASK), "--output-dir", str(invalid_dir),
        ], 2)
        (invalid_dir / "invalid_contract.log").write_text(invalid_log, encoding="utf-8")
        self.assertIn("absent from declared fields/properties", invalid_log)


if __name__ == "__main__":
    unittest.main(verbosity=2)
