#!/usr/bin/env python3
"""Meaningful negative, preservation, export, pixel-diff and determinism tests."""
from __future__ import annotations

import hashlib
import json
import subprocess
import sys
import tempfile
from pathlib import Path

from contract_audit import audit as audit_contract
from edit_diff import build_diff
from png_diff import read_png
from run_example import run


def load(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def snapshot(root: Path) -> dict[str, str]:
    return {str(path.relative_to(root)): hashlib.sha256(path.read_bytes()).hexdigest()
            for path in sorted(root.rglob("*")) if path.is_file()}


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def main() -> int:
    script_dir = Path(__file__).resolve().parent
    example_dir = script_dir.parent / "examples" / "synthetic"
    try:
        with tempfile.TemporaryDirectory(prefix="dual-artifact-quality-gate-test-") as temp:
            root = Path(temp)
            output = root / "synthetic-output"
            code, summary = run(example_dir, output, output / "preview.png")
            require(code == 0, f"Corrected example failed: {summary}")
            first_snapshot = snapshot(output)
            code_second, _ = run(example_dir, output, output / "preview.png")
            require(code_second == 0, "Second deterministic run failed")
            second_snapshot = snapshot(output)
            require(first_snapshot == second_snapshot, "Repeated synthetic outputs are not byte-identical")

            result = load(output / "result.json")
            qc = load(output / "qc_report.json")
            negative = load(output / "qc_report.round1.json")
            require(result["status"] == "success" and result["case_id"] == "SYNTHETIC-dual-gate-001", "Invalid final result status/case")
            case = load(output / "case.json")
            require(all(key in result for key in case["output_contract"]), "A contract key is not top-level")
            require("outputs" not in result and "artifacts" not in result, "Contract keys were nested")
            broken_result = dict(result)
            broken_result.pop("expected_matrix")
            broken_result["outputs"] = {"expected_matrix":"expected_matrix.json"}
            require(audit_contract(case, broken_result, output)["status"] == "fail", "Nested/missing contract key was accepted")
            require(audit_contract(case, result, output)["status"] == "pass", "Final actual contract failed")
            nested_case = {"case_id":"nested-contract-test","output_contract":{"fields":{"svg":{"type":"path","required":True}}}}
            nested_audit = audit_contract(nested_case, {"case_id":"nested-contract-test","status":"partial","sources":[],"uncertainties":[],"change_records":[],"svg":None}, output)
            require(nested_audit["contract_keys"] == ["svg"], "Nested output_contract.fields was not discovered")
            require(qc["status"] == "pass" and not qc["residual_errors"], "Final residual errors remain")
            require(negative["status"] == "fail", "Deliberately defective first SVG passed")
            negative_codes = {item["code"] for item in negative["residual_errors"]}
            require({"LABEL_MISMATCH", "DIRECTION_MISMATCH", "CHART_VALUE_MISMATCH"}.issubset(negative_codes),
                    f"Independent negative checks did not catch all defects: {sorted(negative_codes)}")

            before = load(output / "rendered_observations.before.json")
            after = load(output / "rendered_observations.json")
            require(before["svg"]["entities"]["reactor"]["label"] == "VESSEL", "Before label observation missing")
            require(after["svg"]["entities"]["reactor"]["label"] == "REACTOR", "After label observation wrong")
            require(before["svg"]["edges"]["feed_to_pump"]["from"] == "pump", "Before reversed direction unobserved")
            require(after["svg"]["edges"]["feed_to_pump"]["from"] == "feed", "After direction still wrong")
            require(before["svg"]["chart_values"]["Measurement|Run B"]["value"] == 3.0, "Before chart mismatch unobserved")
            require(after["svg"]["chart_values"]["Measurement|Run B"]["value"] == 4.0, "After chart value wrong")
            require(after["csv"]["measurements.csv"]["values"]["Measurement|Run B"]["value"] == 4.0, "Independent CSV value wrong")

            edit = load(output / "source_edit_diff.json")
            require(edit["status"] == "pass", "Authorized source edit failed preservation")
            require(set(edit["changed_id_set"]) == {"reactor-label", "flow-1", "bar-run-b", "bar-b-value"},
                    f"Unexpected changed source IDs: {edit['changed_id_set']}")
            require(set(edit["unchanged_required_ids"]) == set(load(output / "edit_intent.json")["required_preserve_ids"]),
                    "A protected source ID changed")
            visual = load(output / "visual_diff.json")
            require(visual["difference_detected"] and visual["differing_pixels"] > 100, "Real before/after pixel diff is empty")
            require(visual["changed_bounding_box"] is not None, "Diff bounding box missing")
            width, height, _, _ = read_png(output / "figure.png")
            require((width, height) == (1000, 620), "Actual PNG preview dimensions wrong")
            require((output / "preview.png").read_bytes() == (output / "figure.png").read_bytes(), "--preview-png copy differs")

            # Execute the actual CLI against the independently observed defective
            # artifact. Nonzero is mandatory; this is not merely a report assertion.
            negative_cli = output / "negative_cli_report.json"
            command = [sys.executable, str(script_dir / "semantic_gate.py"),
                       "--checklist", str(output / "semantic_checklist.json"),
                       "--truth", str(output / "truth_table.json"),
                       "--matrix", str(output / "expected_matrix.json"),
                       "--observations", str(output / "rendered_observations.before.json"),
                       "--visual-review", str(output / "visual_review.before.json"),
                       "--visual-diff", str(output / "visual_diff.json"),
                       "--export-report", str(output / "export_audit.before.json"),
                       "--contract-report", str(output / "contract_audit.json"),
                       "--edit-diff", str(output / "source_edit_diff.json"),
                       "--report", str(negative_cli)]
            completed = subprocess.run(command, capture_output=True, text=True, check=False)
            require(completed.returncode != 0, "Negative semantic_gate CLI returned zero")
            negative_cli_data = load(negative_cli)
            cli_codes = {item["code"] for item in negative_cli_data["residual_errors"]}
            require({"LABEL_MISMATCH", "DIRECTION_MISMATCH", "CHART_VALUE_MISMATCH"}.issubset(cli_codes),
                    "CLI observer/gate negative mismatch codes incomplete")

            # An unaddressed source edit must independently fail preservation.
            unauthorized_svg = output / "unauthorized.svg"
            unauthorized_svg.write_text((output / "figure.svg").read_text(encoding="utf-8").replace(
                "PRESERVE THIS UNADDRESSED NOTE", "TAMPERED NOTE"), encoding="utf-8")
            unauthorized = build_diff(output / "before.svg", unauthorized_svg, load(output / "edit_intent.json"))
            require(unauthorized["status"] == "fail" and unauthorized["unauthorized_changes"],
                    "Unaddressed source text edit was not rejected")

            report = {
                "synthetic": True,
                "deterministic_files_compared": len(first_snapshot),
                "negative_cli_returncode": completed.returncode,
                "negative_codes": sorted(cli_codes),
                "final_status": qc["status"],
                "result_status": result["status"],
                "nested_contract_rejected": True,
                "visual_differing_pixels": visual["differing_pixels"],
                "authorized_changed_ids": edit["changed_id_set"],
                "unauthorized_edit_rejected": True,
                "scientific_correctness": "not evaluated; invented synthetic fixture only"
            }
            print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
            return 0
    except (AssertionError, OSError, ValueError, KeyError) as exc:
        print(json.dumps({"synthetic":True,"status":"failed","error":str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
