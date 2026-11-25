#!/usr/bin/env python3
"""Run and compare the clearly labelled SYNTHETIC minimal example."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import subprocess
import sys

SCRIPT_DIR = Path(__file__).resolve().parent


def script_path(value):
    path = Path(value)
    return path.resolve() if path.is_absolute() else (SCRIPT_DIR / path).resolve()


def portable(value, output_dir):
    if isinstance(value, dict):
        return {key: portable(item, output_dir) for key, item in value.items()}
    if isinstance(value, list):
        return [portable(item, output_dir) for item in value]
    if isinstance(value, str):
        return value.replace(str(output_dir), "<OUTPUT_DIR>")
    return value


def load_json(path):
    return json.loads(path.read_text(encoding="utf-8"))


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--example-dir", required=True, help="examples/minimal directory; explicit and required")
    parser.add_argument("--output-dir", required=True, help="A separate writable run directory")
    parser.add_argument("--preview-png", help="Optional PNG path using already installed export tools")
    parser.add_argument("--preview-pdf", help="Optional structurally checked PDF path using already installed export tools")
    args = parser.parse_args(argv)
    example_dir = script_path(args.example_dir)
    output_dir = script_path(args.output_dir)
    atlas_input = example_dir / "input" / "atlas.json"
    expected_dir = example_dir / "expected"
    if not atlas_input.is_file() or not expected_dir.is_dir():
        print("Invalid --example-dir: input/atlas.json and expected/ are required", file=sys.stderr)
        return 2
    output_dir.mkdir(parents=True, exist_ok=True)
    if output_dir == example_dir.resolve() or example_dir.resolve() in output_dir.parents:
        print("Refusing to write generated outputs inside the example fixture", file=sys.stderr)
        return 2
    command = [sys.executable, str(SCRIPT_DIR / "source_span_atlas.py"),
               "--atlas", str(atlas_input), "--output-dir", str(output_dir)]
    if args.preview_png:
        command.extend(["--preview-png", str(script_path(args.preview_png))])
    if args.preview_pdf:
        command.extend(["--preview-pdf", str(script_path(args.preview_pdf))])
    env = dict(__import__("os").environ, PYTHONDONTWRITEBYTECODE="1")
    completed = subprocess.run(command, env=env)
    if completed.returncode != 0:
        return completed.returncode
    checks = {}
    for name in ("figure.svg", "atlas.json", "report.md", "result.json"):
        actual_path = output_dir / name
        expected_path = expected_dir / name
        if not expected_path.is_file():
            checks[name] = {"passed": False, "reason": "Missing expected file"}
            continue
        if name.endswith(".json"):
            actual = portable(load_json(actual_path), output_dir)
            expected = load_json(expected_path)
            if name == "result.json" and (args.preview_png or args.preview_pdf):
                # Export additions are checked separately; expected fixtures cover the stdlib core.
                export_failed = any(item.get("success") is not True for item in actual.get("exports", []))
                actual.pop("exports", None)
                for artifact_key in ("preview_png", "export_report", "preview_pdf", "pdf_export_report"):
                    actual.get("artifacts", {}).pop(artifact_key, None)
                actual["uncertainties"] = [item for item in actual.get("uncertainties", [])
                                           if not (isinstance(item, str) and
                                                   (item.startswith("PNG export unavailable or failed;") or
                                                    item.startswith("PDF export unavailable or failed;")))]
                if (export_failed and actual.get("status") == "partial" and
                        actual.get("verdict") == expected.get("verdict")):
                    actual["status"] = expected.get("status")
            checks[name] = {"passed": actual == expected,
                            "actual": str(actual_path.resolve()), "expected": str(expected_path.resolve())}
        else:
            actual = portable(actual_path.read_text(encoding="utf-8"), output_dir)
            expected = expected_path.read_text(encoding="utf-8")
            checks[name] = {"passed": actual == expected,
                            "actual": str(actual_path.resolve()), "expected": str(expected_path.resolve())}
    result = load_json(output_dir / "result.json")
    spec = load_json(atlas_input)
    contract_ok = result.get("case_id") == spec.get("case_id") and all(key in result for key in spec.get("output_contract", {}))
    checks["top_level_output_contract"] = {"passed": contract_ok, "required_keys": sorted(spec.get("output_contract", {}))}
    for export_format, requested in (("png", args.preview_png), ("pdf", args.preview_pdf)):
        if not requested:
            continue
        matching = [item for item in result.get("exports", []) if item.get(export_format)]
        passed_export = len(matching) == 1 and matching[0].get("success") is True
        checks["preview_%s_export" % export_format] = {
            "passed": passed_export,
            "requested": str(script_path(requested)),
            "success": matching[0].get("success") if matching else False,
        }
        if export_format == "pdf" and matching:
            checks["preview_pdf_export"]["structure_valid"] = matching[0].get("structure", {}).get("valid") is True
            checks["preview_pdf_export"]["passed"] = passed_export and checks["preview_pdf_export"]["structure_valid"]
    passed = all(item["passed"] for item in checks.values())
    run_report = {"synthetic": True, "not_an_official_case": True, "passed": passed,
                  "command": command, "checks": checks}
    (output_dir / "example_run_report.json").write_text(json.dumps(run_report, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print("Synthetic example comparison: %s" % ("PASS" if passed else "FAIL"))
    if not passed:
        print(json.dumps(checks, ensure_ascii=False, indent=2), file=sys.stderr)
        return 3
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
