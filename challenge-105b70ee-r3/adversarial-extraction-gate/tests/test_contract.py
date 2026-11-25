"""Stdlib integration tests for mutation isolation, scaffold, and finalizer."""
from __future__ import annotations

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
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))

from mutation_audit import run_audit  # noqa: E402
from scaffold import dumps  # noqa: E402
import synthetic_fixture  # noqa: E402


class ContractTests(unittest.TestCase):
    def test_every_named_mutation_is_rejected_and_base_is_untouched(self) -> None:
        base = synthetic_fixture.valid_result()
        before = json.dumps(base, sort_keys=True).encode("utf-8")
        report = run_audit()
        after = json.dumps(base, sort_keys=True).encode("utf-8")
        self.assertEqual(before, after, "audit mutated the valid base")
        self.assertTrue(report["overall_actual_pass"], report)
        self.assertGreaterEqual(report["observed_totals"]["mutations_run"], 12)
        for record in report["mutation_results"]:
            self.assertTrue(record["actual_validator_rejected"], record["mutation"])
            self.assertTrue(record["expected_code_observed"], record["mutation"])
            self.assertTrue(record["base_unchanged"], record["mutation"])

    def test_scaffold_and_finalizer_failure_never_clobber_valid_output(self) -> None:
        with tempfile.TemporaryDirectory(prefix="adversarial-gate-test-") as temporary:
            root = Path(temporary)
            inputs, work, output = root / "input", root / "work", root / "output"
            inputs.mkdir()
            (inputs / "case.json").write_text(dumps({"case_id": synthetic_fixture.CASE_ID}), encoding="utf-8")
            (inputs / "target-fields.json").write_text(dumps(synthetic_fixture.targets()), encoding="utf-8")
            (inputs / "task.md").write_text("SYNTHETIC integration test\n", encoding="utf-8")
            environment = dict(os.environ, PYTHONDONTWRITEBYTECODE="1")
            scaffold_command = [
                sys.executable, str(SCRIPTS / "scaffold.py"),
                "--case", str(inputs / "case.json"), "--targets", str(inputs / "target-fields.json"),
                "--task", str(inputs / "task.md"), "--work", str(work), "--output", str(output),
            ]
            scaffolded = subprocess.run(scaffold_command, capture_output=True, text=True, env=environment, check=False)
            self.assertEqual(scaffolded.returncode, 0, scaffolded.stdout + scaffolded.stderr)
            early = json.loads((output / "result.json").read_text(encoding="utf-8"))
            self.assertEqual(early["status"], "partial")
            self.assertEqual(len(early["result"]["fields"]), 2)
            self.assertTrue(all(field["status"] == "extraction_failed" and field["scalar"] is None for field in early["result"]["fields"]))

            (work / "source-corpus.json").write_text(dumps(synthetic_fixture.corpus()), encoding="utf-8")
            valid = synthetic_fixture.valid_result()
            (work / "draft-result.json").write_text(dumps(valid), encoding="utf-8")
            (work / "decoy-review.json").write_text(dumps(synthetic_fixture.decoy_review()), encoding="utf-8")
            finalize_command = [
                sys.executable, str(SCRIPTS / "finalize.py"),
                "--case", str(inputs / "case.json"), "--targets", str(inputs / "target-fields.json"),
                "--corpus", str(work / "source-corpus.json"), "--draft", str(work / "draft-result.json"),
                "--review", str(work / "decoy-review.json"), "--output", str(output),
            ]
            accepted = subprocess.run(finalize_command, capture_output=True, text=True, env=environment, check=False)
            self.assertEqual(accepted.returncode, 0, accepted.stdout + accepted.stderr)
            delivered_hash = hashlib.sha256((output / "result.json").read_bytes()).hexdigest()

            corrupted = copy.deepcopy(valid)
            corrupted["result"]["fields"][0]["units"] = "mg/mL"
            corrupted["result"]["field_results"] = copy.deepcopy(corrupted["result"]["fields"])
            (work / "draft-result.json").write_text(dumps(corrupted), encoding="utf-8")
            rejected = subprocess.run(finalize_command, capture_output=True, text=True, env=environment, check=False)
            self.assertEqual(rejected.returncode, 1, rejected.stdout + rejected.stderr)
            self.assertEqual(delivered_hash, hashlib.sha256((output / "result.json").read_bytes()).hexdigest())
            rejection = json.loads(rejected.stdout)
            self.assertFalse(rejection["final_result_written"])
            self.assertTrue(rejection["existing_output_unchanged_on_rejection"])
            self.assertIn("UNIT_NOT_IN_QUOTE", {item["code"] for item in rejection["contract_errors"]})


if __name__ == "__main__":
    unittest.main(verbosity=2)
