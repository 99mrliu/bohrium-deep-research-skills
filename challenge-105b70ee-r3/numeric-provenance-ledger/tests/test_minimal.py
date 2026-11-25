#!/usr/bin/env python3
"""Runnable stdlib regression tests for the explicitly synthetic example."""

import copy
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
EXAMPLE = ROOT / "examples" / "minimal"
INPUT = EXAMPLE / "input"
LEDGER_SCRIPT = ROOT / "scripts" / "numeric_ledger.py"
RESULT_SCRIPT = ROOT / "scripts" / "numeric_result.py"


class NumericProvenanceTests(unittest.TestCase):
    def setUp(self):
        self.temp_context = tempfile.TemporaryDirectory(prefix=".stdlib-test-", dir=EXAMPLE)
        self.work = Path(self.temp_context.name)
        self.ledger = self.work / "numeric_ledger.jsonl"
        self.result = self.work / "result.json"
        self.audit = self.work / "audit.md"
        self.selection = self.work / "selection.json"
        self.selection.write_text((EXAMPLE / "selection.json").read_text(encoding="utf-8"), encoding="utf-8")
        self.run_command([
            sys.executable, "-B", str(LEDGER_SCRIPT),
            "--sources", str(INPUT / "sources.json"),
            "--ledger", str(self.ledger),
        ])

    def tearDown(self):
        self.temp_context.cleanup()

    def run_command(self, command, expected=0):
        environment = dict(os.environ)
        environment["PYTHONDONTWRITEBYTECODE"] = "1"
        completed = subprocess.run(
            command, cwd=ROOT, env=environment, text=True,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False,
        )
        self.assertEqual(
            completed.returncode, expected,
            f"command returned {completed.returncode}, expected {expected}\n"
            f"stdout: {completed.stdout}\nstderr: {completed.stderr}",
        )
        return completed

    def result_args(self, command):
        return [
            sys.executable, "-B", str(RESULT_SCRIPT), command,
            "--case", str(INPUT / "case.json"),
            "--targets", str(INPUT / "target-fields.json"),
            "--sources", str(INPUT / "sources.json"),
            "--ledger", str(self.ledger),
            "--selection", str(self.selection),
            "--output", str(self.result),
            "--audit", str(self.audit),
        ]

    def build(self):
        return self.run_command(self.result_args("build"))

    def check(self, expected=0):
        return self.run_command(self.result_args("check"), expected=expected)

    def read_result(self):
        return json.loads(self.result.read_text(encoding="utf-8"))

    def write_result(self, value):
        self.result.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    def write_selection(self, value):
        self.selection.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    def test_end_to_end_real_artifacts_and_statuses(self):
        self.build()
        self.check()
        self.assertTrue(self.ledger.is_file())
        self.assertTrue(self.result.is_file())
        self.assertTrue(self.audit.is_file())
        result = self.read_result()
        fields = {field["field_id"]: field for field in result["result"]["fields"]}
        self.assertEqual(result["status"], "answered")
        self.assertEqual(len(fields), 3)
        self.assertEqual(fields["treatment_response_37c"]["scalar"], "4.8 ± 0.3")
        self.assertEqual(fields["treatment_response_37c"]["units"], "mV")
        self.assertEqual(fields["treatment_response_37c"]["condition"], "37 °C")
        self.assertEqual(fields["recovery_half_time"]["status"], "not_reported")
        self.assertEqual(fields["replicated_treatment_response_37c"]["status"], "source_conflict")
        self.assertIsNone(fields["replicated_treatment_response_37c"]["scalar"])
        self.assertEqual(len(fields["replicated_treatment_response_37c"]["conflicts"]), 2)
        audit = self.audit.read_text(encoding="utf-8")
        self.assertIn("N000005", audit)
        self.assertIn("not_reported", audit)
        self.assertIn("Conflict variant 2", audit)

    def test_all_requested_typography_is_harvested_losslessly(self):
        records = [json.loads(line) for line in self.ledger.read_text(encoding="utf-8").splitlines()]
        raw = {record["raw"]: record for record in records}
        expected = {
            "4.8 ± 0.3 mV", "2–4 ms", "p<0.01", "n=18", "Fig. 2",
            "5 × 10⁻³ mol·L⁻¹", "8%", "(95% CI 0.4–1.1)",
            "0.6 percentage points", "<0.2 °C", "Table 2",
        }
        missing = expected - set(raw)
        self.assertFalse(missing, f"missing lexical tokens: {missing}")
        for text in expected:
            token = raw[text]
            with self.subTest(text=text):
                self.assertEqual(text, token["raw"])
                for component in token["components"]:
                    self.assertEqual(component["text"], token["context"][component["start"] - token["context_start"]:component["end"] - token["context_start"]])
        self.assertEqual(raw["8%"]["units"], "%")
        self.assertEqual(raw["0.6 percentage points"]["units"], "percentage points")
        self.assertNotEqual(raw["8%"]["units"], raw["0.6 percentage points"]["units"])
        self.assertEqual(raw["p<0.01"]["statistic"], "p<0.01")
        self.assertEqual(raw["p<0.01"]["comparator"], "<")

    def test_reject_altered_scalar(self):
        self.build()
        result = self.read_result()
        result["result"]["fields"][0]["scalar"] = "4.9 ± 0.3"
        self.write_result(result)
        failure = self.check(expected=2)
        self.assertIn(".scalar", failure.stderr)
        self.assertIn("rejected", failure.stderr)

    def test_reject_altered_unit(self):
        self.build()
        result = self.read_result()
        result["result"]["fields"][0]["units"] = "µV"
        self.write_result(result)
        failure = self.check(expected=2)
        self.assertIn(".units", failure.stderr)

    def test_reject_altered_condition_text(self):
        self.build()
        result = self.read_result()
        result["result"]["fields"][0]["experimental_condition"] = "25 °C"
        result["result"]["fields"][0]["condition"] = "25 °C"
        self.write_result(result)
        failure = self.check(expected=2)
        self.assertIn("experimental_condition", failure.stderr)

    def test_reject_wrong_condition_binding_in_selection(self):
        selection = json.loads(self.selection.read_text(encoding="utf-8"))
        # N000005 is treated 37 °C; N000001 is the 25 °C control condition.
        selection["fields"]["treatment_response_37c"]["condition_token_ids"] = ["N000001"]
        self.write_selection(selection)
        failure = self.run_command(self.result_args("build"), expected=2)
        self.assertIn("wrong condition binding", failure.stderr)
        self.assertFalse(self.result.exists())

    def test_reject_decoy_value_under_other_condition(self):
        selection = json.loads(self.selection.read_text(encoding="utf-8"))
        # N000002 is 3.2 ± 0.2 mV at 25 °C, not the treated 37 °C value.
        selection["fields"]["treatment_response_37c"]["value_token_ids"] = ["N000002"]
        self.write_selection(selection)
        failure = self.run_command(self.result_args("build"), expected=2)
        self.assertIn("wrong condition binding", failure.stderr)

    def test_identifier_digits_are_not_silently_lost(self):
        source = self.work / "identifier-source.json"
        residual_ledger = self.work / "identifier-ledger.jsonl"
        source.write_text(json.dumps({"sources": [{
            "source_id": "synthetic-identifiers",
            "paragraphs": [{"paragraph_id": "p", "page": None, "text": "C6H12O6 and ID7 are retained as residuals."}],
        }]}), encoding="utf-8")
        self.run_command([
            sys.executable, "-B", str(LEDGER_SCRIPT), "--sources", str(source),
            "--ledger", str(residual_ledger),
        ])
        records = [json.loads(line) for line in residual_ledger.read_text(encoding="utf-8").splitlines()]
        self.assertEqual([record["raw"] for record in records], ["6", "12", "6", "7"])
        self.assertTrue(all(record["kind"] == "numeric_residual" for record in records))

    def test_append_only_rerun_is_byte_identical(self):
        before_path = self.ledger.read_bytes()
        before_hash = hashlib.sha256(before_path).hexdigest()
        completed = self.run_command([
            sys.executable, "-B", str(LEDGER_SCRIPT),
            "--sources", str(INPUT / "sources.json"),
            "--ledger", str(self.ledger),
        ])
        self.assertIn('"appended_tokens": 0', completed.stdout)
        self.assertEqual(hashlib.sha256(self.ledger.read_bytes()).hexdigest(), before_hash)
        self.assertEqual(self.ledger.read_bytes(), before_path)

    def test_changed_existing_source_cannot_rewrite_ledger(self):
        original = self.ledger.read_bytes()
        changed_sources = copy.deepcopy(json.loads((INPUT / "sources.json").read_text(encoding="utf-8")))
        changed_sources["sources"][0]["paragraphs"][0]["text"] = changed_sources["sources"][0]["paragraphs"][0]["text"].replace("3.2", "9.9")
        changed_path = self.work / "changed-sources.json"
        changed_path.write_text(json.dumps(changed_sources, ensure_ascii=False), encoding="utf-8")
        failure = self.run_command([
            sys.executable, "-B", str(LEDGER_SCRIPT),
            "--sources", str(changed_path), "--ledger", str(self.ledger),
        ], expected=2)
        self.assertIn("append-only collision", failure.stderr)
        self.assertEqual(self.ledger.read_bytes(), original)

    def test_early_partial_is_immediate_complete_field_envelope(self):
        early = self.work / "early-result.json"
        self.run_command([
            sys.executable, "-B", str(RESULT_SCRIPT), "init",
            "--case", str(INPUT / "case.json"),
            "--targets", str(INPUT / "target-fields.json"),
            "--output", str(early),
        ])
        result = json.loads(early.read_text(encoding="utf-8"))
        self.assertEqual(result["status"], "partial")
        self.assertEqual(len(result["result"]["fields"]), 3)
        self.assertTrue(all(field["status"] == "extraction_failed" for field in result["result"]["fields"]))
        self.assertTrue(all(field["failure_kind"] == "pending_read" for field in result["result"]["fields"]))

    def test_unreadable_is_not_relabelled_absent(self):
        selection = json.loads(self.selection.read_text(encoding="utf-8"))
        selection["fields"]["recovery_half_time"] = {
            "status": "extraction_failed",
            "failure_kind": "unreadable_source",
            "coverage": [],
            "notes": "SYNTHETIC test of an unreadable source; no absence claim or numeric value is made.",
        }
        self.write_selection(selection)
        self.build()
        field = self.read_result()["result"]["fields"][1]
        self.assertEqual(field["status"], "extraction_failed")
        self.assertEqual(field["failure_kind"], "unreadable_source")
        self.assertIsNone(field["scalar"])
        self.assertNotEqual(field["status"], "not_reported")


if __name__ == "__main__":
    unittest.main()
