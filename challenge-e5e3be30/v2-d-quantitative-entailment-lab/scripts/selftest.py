#!/usr/bin/env python3
"""Independent-value assertions and end-to-end/failure tests for SYNTHETIC data.

Expected statistics below were independently recomputed with direct formulas,
not obtained by calling the implementation under test. No network or third-party
packages are used.
"""
import copy
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
EXAMPLE = ROOT / "examples" / "minimal"
sys.path.insert(0, str(SCRIPTS))
sys.dont_write_bytecode = True
from contract import assemble, audit  # noqa: E402
from quantlib import (InputError, build_report, convert_units, read_json,  # noqa: E402
                      two_proportion_z_test)


class SyntheticQuantitativeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.observations = read_json(EXAMPLE / "observations.json")
        cls.claims = read_json(EXAMPLE / "claims-to-verify.json")
        cls.report = build_report(cls.observations, cls.claims, "SYNTHETIC-QEL-001")
        cls.derived = {item["id"]: item for item in cls.report["derived"]}
        cls.test = cls.report["statistical_tests"][0]

    def test_independent_manual_effect_values(self):
        # SYNTHETIC hand calculation: p1=7/10, p0=1/2, pp=20, relative=2/5,
        # ratio=7/5; displayed baseline 3/5 yields pp=10 and relative=1/6.
        expected = {
            "derived_C1_RAW_PP_1": 20.0,
            "derived_C1_RAW_PP_2": 0.4,
            "derived_C1_RAW_PP_3": 1.4,
            "derived_C2_DISPLAY_RELATIVE_1": 10.0,
            "derived_C2_DISPLAY_RELATIVE_2": 1.0 / 6.0,
            "derived_C4_UNIT_CONVERSION_1": 2.5,
        }
        for identifier, target in expected.items():
            self.assertAlmostEqual(self.derived[identifier]["value"], target, places=12)
            self.assertEqual(self.derived[identifier]["role"], "derived")
            self.assertTrue(self.derived[identifier]["formula"])
            self.assertTrue(self.derived[identifier]["source_ids"])
            self.assertIsNone(self.derived[identifier]["verdict"])
        self.assertTrue(self.derived["derived_C2_DISPLAY_RELATIVE_1"]["comparison"]["within_tolerance"])
        self.assertFalse(self.derived["derived_C2_DISPLAY_RELATIVE_2"]["comparison"]["within_tolerance"])
        self.assertTrue(any(item["type"] == "reported_display_conflicts_with_raw_counts"
                            for item in self.report["warnings"]))

    def test_independently_fixed_z_and_p_value(self):
        # Direct independent double calculation: pooled=13/22;
        # SE=sqrt((13/22)(9/22)(1/100+1/120)), z=.2/SE,
        # two-sided p=erfc(|z|/sqrt(2)).
        self.assertAlmostEqual(self.test["pooled_proportion"], 13.0 / 22.0, places=14)
        self.assertAlmostEqual(self.test["standard_error_null"], 0.06657190234489459, places=14)
        self.assertAlmostEqual(self.test["z"], 3.0042704647952423, places=12)
        self.assertAlmostEqual(self.test["p_two_sided_normal_approximation"],
                               0.002662185508945006, places=14)
        self.assertTrue(self.test["alternative"] == "two_sided")
        self.assertFalse(self.test["exact_test"])

    def test_independently_fixed_wilson_intervals(self):
        # Independent direct Wilson substitutions with z=1.959963984540054.
        expected = [(0.6041514536665332, 0.7810511470506724),
                    (0.41193870541108385, 0.5880612945889161)]
        for interval, (lower, upper) in zip(self.test["wilson_intervals"], expected):
            self.assertAlmostEqual(interval["lower"], lower, places=13)
            self.assertAlmostEqual(interval["upper"], upper, places=13)
            self.assertEqual(interval["confidence"], 0.95)
            self.assertEqual(interval["method"], "Wilson score interval (no continuity correction)")

    def test_source_reported_p_target_is_not_auto_refuted(self):
        record = self.derived["derived_C3_REPORTED_EXACT_P_1"]
        self.assertAlmostEqual(record["value"], 0.002662185508945006, places=14)
        self.assertEqual(record["comparison"]["entailment_comparison"],
                         "not_applicable_source_reporting_question")
        self.assertIn("cannot prove", record["comparison"]["warning"])
        self.assertIsNone(record["verdict"])

    def test_unit_dimensions(self):
        self.assertEqual(convert_units(2500, "ms", "s"), 2.5)
        self.assertEqual(convert_units(1500, "uL", "mL"), 1.5)
        with self.assertRaises(InputError):
            convert_units(1, "kg", "s")

    def test_sparse_data_warning_not_hard_verdict(self):
        first = {"id": "SYNTHETIC_sparse_1", "events": 1, "n": 3}
        second = {"id": "SYNTHETIC_sparse_0", "events": 0, "n": 4}
        result = two_proportion_z_test(first, second)
        self.assertTrue(result["sparse_expected_cells"])
        self.assertTrue(any("below 5" in item for item in result["warnings"]))
        self.assertNotIn("verdict", result)

    def test_dynamic_list_and_dict_contracts(self):
        context = {"case_id": "SYNTHETIC-contract", "status": "partial",
                   "claim_verdicts": [{"claim_id": "Q", "verdict": None}],
                   "sources": [], "uncertainty": ["SYNTHETIC pending"],
                   "change_records": [], "quantitative_report": {}, "derived": [],
                   "observations": [], "warnings": [], "summary": {"unresolved": 1},
                   "report_artifact": "quantitative-report.json", "plot_artifact": "effect-plot.svg"}
        list_contract = ["case_id", "claims", "status", "sources", "uncertainty", "change_records"]
        list_result, _ = assemble(list_contract, context)
        self.assertEqual(list_result["case_id"], "SYNTHETIC-contract")
        self.assertIsInstance(list_result["claims"], list)
        dict_contract = {"claims": "dict", "case_id": "str", "status": "str",
                         "sources": "list", "uncertainty": "list", "change_records": "list"}
        dict_result, _ = assemble(dict_contract, context)
        self.assertIsInstance(dict_result["claims"], dict)
        self.assertIn("Q", dict_result["claims"])
        self.assertEqual(dict_result["status"], "partial")
        context.update(status="success", sources=[{"id": "SYNTHETIC-paper"}],
                       change_records=[{"action": "SYNTHETIC-test"}],
                       claim_verdicts=[{"claim_id": "Q", "verdict": "supported", "verdict_origin": "agent"}])
        dict_result, field_status = assemble(dict_contract, context)
        checked = audit(dict_result, dict_contract, field_status, 1)
        self.assertEqual(checked["claims_checked"], 1)
        self.assertEqual(checked["errors"], [])
        status_object_contract = dict(dict_contract, status="dict")
        object_result, field_status = assemble(status_object_contract, context)
        object_audit = audit(object_result, status_object_contract, field_status, 1)
        self.assertEqual(object_result["status"]["state"], "success")
        self.assertEqual(object_audit["errors"], [])

    def test_all_observation_quotes_exist_in_synthetic_paper(self):
        paper = (EXAMPLE / "paper.md").read_text(encoding="utf-8")
        for obs in self.observations["observations"]:
            self.assertIn(obs["quote"], paper)
            if "reported_display" in obs:
                self.assertIn(obs["reported_display"]["quote"], paper)


class SyntheticCommandTests(unittest.TestCase):
    def run_command(self, arguments, expected):
        process = subprocess.run([sys.executable] + arguments, cwd=ROOT, text=True,
                                 capture_output=True, timeout=30)
        self.assertEqual(process.returncode, expected,
                         "stdout=%s stderr=%s" % (process.stdout, process.stderr))
        return process

    def base_arguments(self, stem):
        return [str(SCRIPTS / stem), "--observations", str(EXAMPLE / "observations.json"),
                "--claims", str(EXAMPLE / "claims-to-verify.json"),
                "--case-id", "SYNTHETIC-failure"]

    def test_end_to_end_result_and_svg_values(self):
        with tempfile.TemporaryDirectory(prefix="qel-synthetic-e2e-") as directory:
            out = Path(directory) / "output"
            work = Path(directory) / "work"
            self.run_command([str(SCRIPTS / "run.py"), "--case", str(EXAMPLE / "case.json"),
                              "--claims", str(EXAMPLE / "claims-to-verify.json"),
                              "--input-dir", str(EXAMPLE), "--observations", str(EXAMPLE / "observations.json"),
                              "--verdicts", str(EXAMPLE / "agent-verdicts.json"),
                              "--out", str(out), "--work", str(work)], 0)
            result = json.loads((out / "result.json").read_text(encoding="utf-8"))
            self.assertEqual(result["status"], "success")
            self.assertEqual(result["case_id"], "SYNTHETIC-QEL-001")
            self.assertEqual(len(result["claim_verdicts"]), 4)
            self.assertIn("early_partial_written", {item["action"] for item in result["change_records"]})
            verdicts = {item["claim_id"]: item["verdict"] for item in result["claim_verdicts"]}
            self.assertEqual(verdicts["C1_RAW_PP"], "supported")
            self.assertEqual(verdicts["C2_DISPLAY_RELATIVE"], "partially_supported")
            self.assertEqual(verdicts["C3_REPORTED_EXACT_P"], "insufficient_evidence")
            self.assertEqual(verdicts["C4_UNIT_CONVERSION"], "supported")
            verification = json.loads((out / "verification.json").read_text(encoding="utf-8"))
            self.assertEqual(verification["contract_check"], "pass")
            svg = (out / "effect-plot.svg").read_text(encoding="utf-8")
            self.assertIn("SYNTHETIC", svg)
            self.assertIn("70.0% [60.4, 78.1]", svg)
            self.assertIn("50.0% [41.2, 58.8]", svg)

    def test_invalid_n_exits_1(self):
        bad = copy.deepcopy(self.observations if hasattr(self, "observations") else read_json(EXAMPLE / "observations.json"))
        bad["observations"][0]["n"] = 0
        with tempfile.TemporaryDirectory(prefix="qel-synthetic-bad-n-") as directory:
            bad_path = Path(directory) / "bad-n.json"
            bad_path.write_text(json.dumps(bad), encoding="utf-8")
            arguments = self.base_arguments("build_report.py")
            arguments[2] = str(bad_path)
            arguments += ["--out", str(Path(directory) / "report.json")]
            process = self.run_command(arguments, 1)
            self.assertIn("positive integer", process.stderr)

    def test_invalid_interval_exits_1(self):
        with tempfile.TemporaryDirectory(prefix="qel-synthetic-bad-ci-") as directory:
            arguments = self.base_arguments("build_report.py")
            arguments += ["--confidence", "1.0", "--out", str(Path(directory) / "report.json")]
            process = self.run_command(arguments, 1)
            self.assertIn("strictly between 0 and 1", process.stderr)

    def test_missing_paper_downgrades_agent_result_to_partial(self):
        with tempfile.TemporaryDirectory(prefix="qel-synthetic-no-paper-") as directory:
            out = Path(directory) / "output"
            self.run_command([str(SCRIPTS / "run.py"), "--case", str(EXAMPLE / "case.json"),
                              "--claims", str(EXAMPLE / "claims-to-verify.json"),
                              "--input-dir", str(Path(directory) / "empty-input"),
                              "--observations", str(EXAMPLE / "observations.json"),
                              "--verdicts", str(EXAMPLE / "agent-verdicts.json"),
                              "--out", str(out), "--work", str(Path(directory) / "work")], 0)
            result = json.loads((out / "result.json").read_text(encoding="utf-8"))
            self.assertEqual(result["status"], "partial")
            self.assertTrue(any("No paper" in note for note in result["uncertainty"]))

    def test_missing_observations_leaves_early_partial(self):
        with tempfile.TemporaryDirectory(prefix="qel-synthetic-partial-") as directory:
            out = Path(directory) / "output"
            process = self.run_command([str(SCRIPTS / "run.py"), "--case", str(EXAMPLE / "case.json"),
                                        "--claims", str(EXAMPLE / "claims-to-verify.json"),
                                        "--input-dir", str(EXAMPLE),
                                        "--observations", str(Path(directory) / "definitely-missing.json"),
                                        "--out", str(out), "--work", str(Path(directory) / "empty-work")], 1)
            self.assertIn("not found", process.stderr)
            result = json.loads((out / "result.json").read_text(encoding="utf-8"))
            self.assertEqual(result["status"], "partial")
            self.assertTrue(all(item["verdict"] is None for item in result["claim_verdicts"]))
            self.assertTrue(result["sources"])
            self.assertTrue(result["change_records"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
