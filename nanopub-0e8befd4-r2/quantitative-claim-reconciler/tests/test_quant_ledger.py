#!/usr/bin/env python3
"""Real subprocess regression tests for the synthetic quantitative ledger."""

import copy
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "quant_ledger.py"
REPORT_ROOT = ROOT / "tests" / "reports"


def read_json(path):
    with open(path, "r", encoding="utf-8") as handle:
        return json.load(handle)


def write_json(path, payload):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2, sort_keys=True)
        handle.write("\n")


class QuantLedgerTests(unittest.TestCase):
    maxDiff = None

    def run_process(self, case, task, resources, work, output):
        command = [
            sys.executable, str(SCRIPT), "--case", str(case), "--task", str(task),
            "--resources", str(resources), "--work-root", str(work),
            "--output-root", str(output),
        ]
        return subprocess.run(command, cwd=str(ROOT), text=True, capture_output=True, timeout=30)

    def fixture_process(self, name, base):
        fixture = ROOT / "examples" / name
        work = base / "work"
        output = base / "output"
        process = self.run_process(
            fixture / "input" / "case.json", fixture / "input" / "task.md",
            fixture / "environment" / "resources.yaml", work, output,
        )
        return process, work, output

    def assert_matches_expected(self, name, output):
        expected = ROOT / "examples" / name / "expected"
        self.assertEqual(read_json(output / "calculations.json"), read_json(expected / "calculations.json"))
        self.assertEqual(read_json(output / "result.json"), read_json(expected / "result.json"))

    def report_negative(self, name, process, result, expected_match):
        report = {
            "dataset_status": "SYNTHETIC negative execution; not an official result",
            "fixture": "examples/" + name,
            "command": "python3 scripts/quant_ledger.py --case examples/{0}/input/case.json --task examples/{0}/input/task.md --resources examples/{0}/environment/resources.yaml --work-root <temporary>/work --output-root <temporary>/output".format(name),
            "expected_exit_code": 2,
            "actual_exit_code": process.returncode,
            "case_id": result["case_id"],
            "result_status": result["status"],
            "pending_value": result["assertion_results"][-1]["value"],
            "unresolved_reason": result["assertion_results"][-1].get("error"),
            "expected_artifacts_match": expected_match,
        }
        short_name = "unbalanced" if name == "negative_unbalanced" else "division_by_zero"
        write_json(REPORT_ROOT / (short_name + "_report.json"), report)

    def test_positive_expected_and_quantitative_values(self):
        with tempfile.TemporaryDirectory(prefix="qcr-positive-") as temporary:
            process, work, output = self.fixture_process("synthetic", Path(temporary))
            self.assertEqual(process.returncode, 0, process.stderr)
            self.assertTrue((work / "work_ledger.json").is_file())
            self.assert_matches_expected("synthetic", output)
            calculations = read_json(output / "calculations.json")
            result = read_json(output / "result.json")
            self.assertEqual(result["case_id"], "SYNTHETIC-QC-001")
            self.assertEqual(result["status"], "complete")
            self.assertEqual(len(result["assertion_results"]), 25)
            self.assertEqual(len(calculations["calculations"]), 6)
            self.assertEqual(len(calculations["direct_assertions"]), 14)
            self.assertEqual(len(calculations["qualitative_assertions"]), 5)
            values = {item["assertion_id"]: item["rounded_value"] for item in calculations["calculations"]}
            self.assertEqual(values, {
                "C01": "30.0", "C02": "29.4", "C03": "25.0",
                "C04": "-25.0", "C05": "0", "C06": "-1",
            })
            exact = {item["assertion_id"]: item["exact_result"]["fraction"] for item in calculations["calculations"]}
            self.assertEqual(exact["C02"], "500/17")
            evidence_ids = {item["evidence_id"] for item in read_json(ROOT / "examples" / "synthetic" / "input" / "case.json")["evidence"]}
            for calculation in calculations["calculations"]:
                self.assertEqual(calculation["direct_vs_calculated"], "calculated")
                self.assertEqual(calculation["rounding"]["applied_at"], "presentation_only")
                self.assertEqual(calculation["evidence_validation"]["status"], "valid")
                self.assertTrue(set(calculation["evidence_validation"]["evidence_ids"]).issubset(evidence_ids))
            self.assertEqual(len(calculations["direct_assertions"]), 14)
            self.assertTrue(all(item["direct_vs_calculated"] == "direct" for item in calculations["direct_assertions"]))
            self.assertIn("sources", result)
            self.assertIn("uncertainty", result)
            self.assertIn("change_records", result)
            self.assertEqual(result["run_metadata"]["external_requests_used"], 0)

    def test_unbalanced_real_nonzero_and_report(self):
        with tempfile.TemporaryDirectory(prefix="qcr-unbalanced-") as temporary:
            process, work, output = self.fixture_process("negative_unbalanced", Path(temporary))
            self.assertEqual(process.returncode, 2, process.stdout + process.stderr)
            self.assertTrue((work / "work_ledger.json").is_file())
            self.assert_matches_expected("negative_unbalanced", output)
            result = read_json(output / "result.json")
            self.assertEqual(result["status"], "failed")
            self.assertEqual(result["assertion_results"][-1]["status"], "pending")
            self.assertIsNone(result["assertion_results"][-1]["value"])
            self.assertIn("residual=1/1 events", result["assertion_results"][-1]["error"])
            self.report_negative("negative_unbalanced", process, result, True)

    def test_division_zero_real_nonzero_and_report(self):
        with tempfile.TemporaryDirectory(prefix="qcr-zero-") as temporary:
            process, work, output = self.fixture_process("negative_division_zero", Path(temporary))
            self.assertEqual(process.returncode, 2, process.stdout + process.stderr)
            self.assertTrue((work / "work_ledger.json").is_file())
            self.assert_matches_expected("negative_division_zero", output)
            result = read_json(output / "result.json")
            self.assertEqual(result["status"], "failed")
            self.assertEqual(result["assertion_results"][-1]["status"], "pending")
            self.assertIsNone(result["assertion_results"][-1]["value"])
            self.assertIn("division by zero", result["assertion_results"][-1]["error"])
            self.report_negative("negative_division_zero", process, result, True)

    def run_mutated_positive(self, base, mutator):
        source = read_json(ROOT / "examples" / "synthetic" / "input" / "case.json")
        mutated = copy.deepcopy(source)
        mutator(mutated)
        case = base / "mutated_case.json"
        write_json(case, mutated)
        work, output = base / "work", base / "output"
        process = self.run_process(
            case, ROOT / "examples" / "synthetic" / "input" / "task.md",
            ROOT / "examples" / "synthetic" / "environment" / "resources.yaml", work, output,
        )
        return process, work, output

    def test_missing_operand_preserves_fourteen_completed_direct_items(self):
        with tempfile.TemporaryDirectory(prefix="qcr-missing-") as temporary:
            def mutate(case):
                del next(item for item in case["assertions"] if item["assertion_id"] == "C01")["operands"]["denominator"]
            process, work, output = self.run_mutated_positive(Path(temporary), mutate)
            self.assertEqual(process.returncode, 2)
            result = read_json(output / "result.json")
            self.assertEqual(result["summary"]["completed_assertions"], 14)
            self.assertEqual(result["assertion_results"][-1]["assertion_id"], "C01")
            self.assertIsNone(result["assertion_results"][-1]["value"])
            self.assertTrue((work / "work_ledger.json").is_file())

    def test_missing_evidence_id_is_rejected(self):
        with tempfile.TemporaryDirectory(prefix="qcr-evidence-") as temporary:
            def mutate(case):
                assertion = next(item for item in case["assertions"] if item["assertion_id"] == "C01")
                assertion["operand_evidence_ids"]["denominator"] = ["E-NOT-PRESENT"]
                assertion["evidence_ids"] = ["E-A-M", "E-NOT-PRESENT"]
            process, _, output = self.run_mutated_positive(Path(temporary), mutate)
            self.assertEqual(process.returncode, 2)
            result = read_json(output / "result.json")
            self.assertIn("missing evidence ID", result["assertion_results"][-1]["error"])
            self.assertIsNone(result["assertion_results"][-1]["value"])

    def test_mentions_people_denominator_confusion_is_rejected(self):
        with tempfile.TemporaryDirectory(prefix="qcr-scope-") as temporary:
            def mutate(case):
                assertion = next(item for item in case["assertions"] if item["assertion_id"] == "C01")
                assertion["operands"]["denominator"] = "300"
                assertion["operand_units"]["denominator"] = "people"
                assertion["operand_kinds"]["denominator"] = "people"
                assertion["operand_evidence_ids"]["denominator"] = ["E-ALL-P"]
                assertion["scope"]["denominator"] = "All systems represented people in 2024"
                assertion["evidence_ids"] = ["E-A-M", "E-ALL-P"]
            process, _, output = self.run_mutated_positive(Path(temporary), mutate)
            self.assertEqual(process.returncode, 2)
            result = read_json(output / "result.json")
            self.assertIn("denominators are confused", result["assertion_results"][-1]["error"])
            self.assertIsNone(result["assertion_results"][-1]["value"])


def main():
    report_root = Path(REPORT_ROOT)
    report_root.mkdir(parents=True, exist_ok=True)
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(QuantLedgerTests)
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    summary = {
        "suite": "quantitative-claim-reconciler real subprocess tests",
        "python": sys.version.split()[0],
        "tests_run": result.testsRun,
        "failures": len(result.failures),
        "errors": len(result.errors),
        "skipped": len(result.skipped),
        "status": "passed" if result.wasSuccessful() else "failed",
    }
    write_json(report_root / "test_summary.json", summary)
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    sys.exit(main())
