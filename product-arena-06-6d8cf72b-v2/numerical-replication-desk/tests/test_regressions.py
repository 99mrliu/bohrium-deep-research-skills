#!/usr/bin/env python3
"""Standard-library subprocess regressions for numerical-replication-desk."""

import copy
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
import xml.etree.ElementTree as ET
from decimal import Decimal

BUNDLE = Path(__file__).resolve().parents[1]
NRD = BUNDLE / "scripts" / "nrd.py"
EXAMPLE = BUNDLE / "examples" / "synthetic"


def save_json(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def load_json(path):
    return json.loads(path.read_text(encoding="utf-8"))


def object_schema(properties):
    return {
        "type": "object",
        "properties": properties,
        "required": list(properties),
        "additionalProperties": False,
    }


class CliRegressions(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix=".tmp-regression-", dir=BUNDLE / "tests")
        self.work = Path(self.temporary.name)
        (self.work / "materials").mkdir()
        (self.work / "task.md").write_text("Recompute the values and make a chart.\n", encoding="utf-8")
        self.counter = 0

    def tearDown(self):
        self.temporary.cleanup()

    def env(self):
        environment = os.environ.copy()
        environment["PYTHONDONTWRITEBYTECODE"] = "1"
        return environment

    def ledger(self, numbers=("1", "2"), units=None, visual=False):
        if units is None:
            units = ["ms"] * len(numbers)
        source_lines = ["%s=%s %s" % (name, number, unit) for name, number, unit in zip(("a", "b", "c"), numbers, units)]
        source_text = "\n".join(source_lines) + "\n"
        (self.work / "materials" / "source.md").write_text(source_text, encoding="utf-8")
        names = ("a", "b", "c")[:len(numbers)]
        values = []
        for name, number, unit, line in zip(names, numbers, units, source_lines):
            start = source_text.index(line)
            values.append({
                "value_id": name,
                "number": number,
                "unit": unit,
                "provenance": "author_reported",
                "anchor": {
                    "source_id": "source",
                    "locator": "synthetic test line %s" % name,
                    "row": name,
                    "column": "measurement",
                    "condition": "test",
                    "unit": unit,
                    "quote": line,
                    "char_start": start,
                    "char_end": start + len(line),
                },
            })
        expected = sum((Decimal(number) for number in numbers), Decimal(0))
        ledger = {
            "schema_version": "1.0",
            "ledger_id": "regression-ledger",
            "synthetic": True,
            "numbers_matter": bool(visual),
            "sources": [{"source_id": "source", "path": "materials/source.md"}],
            "values": values,
            "calculations": [{
                "calculation_id": "sum_check",
                "operation": "sum",
                "provenance": "independently_calculated",
                "direction": "signed",
                "operands": {name: name for name in names},
                "expected": format(expected, "f"),
                "expected_basis": "test fixture sum",
                "tolerance": {"type": "absolute", "value": "0"},
                "rounding": {"places": 2, "mode": "ROUND_HALF_UP"},
            }],
            "visual_comparison": {
                "enabled": bool(visual),
                "derived_output": "comparison.svg",
                "original_render": None,
                "original_crop": None,
                "original_review": {"status": "missing", "checked_values": [], "note": "No original supplied."},
                "series": [
                    {"label": name, "bars": [{"label": name, "value_id": name}]}
                    for name in names
                ],
            },
        }
        return ledger

    def case(self, ledger=None):
        if ledger is None:
            ledger = self.ledger()
        save_json(self.work / "ledger.json", ledger)
        contract = object_schema({
            "case_id": {"type": "string"},
            "status": {"type": "string", "enum": ["complete", "partial", "failed"]},
            "answer": {"type": "string"},
            "numerical_findings": {
                "type": "array",
                "items": object_schema({
                    "calculation_id": {"type": "string"},
                    "actual": {"type": "string"},
                    "calculation_match": {"type": "boolean"},
                    "output_unit": {"type": "string"},
                }),
            },
        })
        return {
            "case_id": "regression-case",
            "synthetic": True,
            "numeric_ledger_path": "ledger.json",
            "output_contract": contract,
            "response": {"answer": "checked"},
        }

    def run_case(self, case, expected=0, output_name=None):
        self.counter += 1
        output = self.work / (output_name or ("output-%d" % self.counter))
        case_path = self.work / ("case-%d.json" % self.counter)
        save_json(case_path, case)
        process = subprocess.run(
            [os.sys.executable, str(NRD), "run", "--case", str(case_path), "--task", str(self.work / "task.md"),
             "--materials", str(self.work / "materials"), "--output-dir", str(output)],
            cwd=str(BUNDLE), env=self.env(), text=True, capture_output=True, check=False,
        )
        self.assertEqual(expected, process.returncode, process.stdout + process.stderr)
        return process, output

    def run_verify(self, ledger, expected=0, fail_on_mismatch=True):
        self.counter += 1
        output = self.work / ("verify-%d" % self.counter)
        path = self.work / ("verify-ledger-%d.json" % self.counter)
        save_json(path, ledger)
        command = [os.sys.executable, str(NRD), "verify", "--ledger", str(path), "--output-dir", str(output)]
        if fail_on_mismatch:
            command.append("--fail-on-mismatch")
        process = subprocess.run(command, cwd=str(BUNDLE), env=self.env(), text=True, capture_output=True, check=False)
        self.assertEqual(expected, process.returncode, process.stdout + process.stderr)
        return process, output

    def test_const_is_seeded_and_uses_json_aware_equality(self):
        case = self.case()
        const_value = {"enabled": True, "level": 1, "nested": [False, 2]}
        properties = {
            "enabled": {"type": "boolean"},
            "level": {"type": "integer"},
            "nested": {"type": "array", "items": {"type": ["boolean", "integer"]}},
        }
        case["output_contract"]["properties"]["settings"] = {
            "type": "object", "properties": properties, "required": list(properties),
            "additionalProperties": False, "const": const_value,
        }
        case["output_contract"]["required"].append("settings")
        _process, output = self.run_case(case)
        self.assertEqual(const_value, load_json(output / "result.json")["settings"])
        self.assertIs(load_json(output / "result.json")["settings"]["enabled"], True)

        bad = copy.deepcopy(case)
        bad["response"]["settings"] = {"enabled": 1, "level": 1, "nested": [False, 2]}
        process, output = self.run_case(bad, expected=2)
        self.assertIn("const", process.stderr)
        self.assertFalse((output / "result.json").exists())

    def test_unknown_nested_schema_keyword_fails_before_execution(self):
        case = self.case()
        case["output_contract"]["properties"]["answer"]["format"] = "email"
        process, output = self.run_case(case, expected=2)
        self.assertIn("unsupported schema keywords", process.stderr)
        self.assertFalse(output.exists(), "contract preflight must precede ledger execution/output creation")

    def test_status_honors_success_partial_failed_vocabulary(self):
        case = self.case()
        case["output_contract"]["properties"]["status"]["enum"] = ["success", "partial", "failed"]
        _process, output = self.run_case(case)
        self.assertEqual("success", load_json(output / "result.json")["status"])

        partial_only = self.case()
        partial_only["output_contract"]["properties"]["status"]["enum"] = ["partial", "failed"]
        _process, output = self.run_case(partial_only)
        self.assertEqual("partial", load_json(output / "result.json")["status"])

        const_success = self.case()
        const_success["output_contract"]["properties"]["status"] = {"type": "string", "const": "success"}
        _process, output = self.run_case(const_success)
        self.assertEqual("success", load_json(output / "result.json")["status"])

        dishonest = self.case()
        dishonest["output_contract"]["properties"]["status"] = {"type": "string", "const": "success"}
        del dishonest["response"]
        process, output = self.run_case(dishonest, expected=2)
        self.assertIn("honest partial status", process.stderr)
        self.assertFalse((output / "result.json").exists())

    def test_refs_alternatives_pattern_unique_and_exclusive_bounds(self):
        case = self.case()
        properties = case["output_contract"]["properties"]
        case["output_contract"]["$defs"] = {"code": {"type": "string", "pattern": "^[A-Z]{2}$"}}
        properties.update({
            "code": {"$ref": "#/$defs/code"},
            "tags": {"type": "array", "items": {"type": "string"}, "minItems": 2, "uniqueItems": True},
            "score": {"type": "number", "exclusiveMinimum": 0, "exclusiveMaximum": 2, "multipleOf": 0.5},
            "choice": {"anyOf": [{"type": "string", "const": "safe"}, {"type": "integer", "minimum": 1}]},
            "one": {"oneOf": [{"type": "integer", "minimum": 1}, {"type": "number", "maximum": 2}]},
        })
        case["output_contract"]["required"].extend(["code", "tags", "score", "choice", "one"])
        case["response"].update({"code": "AB", "tags": ["a", "b"], "score": 1.5, "choice": "safe", "one": 0.5})
        _process, output = self.run_case(case)
        result = load_json(output / "result.json")
        self.assertEqual("AB", result["code"])
        self.assertEqual(0.5, result["one"])

        invalid_responses = [
            ({"code": "ab"}, "pattern"),
            ({"tags": ["a", "a"]}, "not unique"),
            ({"score": 2}, "exclusiveMaximum"),
            ({"choice": 0}, "anyOf"),
            ({"one": 1}, "oneOf matched 2 branches"),
        ]
        for patch, message in invalid_responses:
            with self.subTest(message=message):
                bad = copy.deepcopy(case)
                bad["response"].update(patch)
                process, output = self.run_case(bad, expected=2)
                self.assertIn(message, process.stderr)
                self.assertFalse((output / "result.json").exists())

    def test_wrong_and_out_of_range_quote_regions_fail_closed(self):
        for region_kind in ("wrong", "out_of_range", "legacy"):
            with self.subTest(region_kind=region_kind):
                ledger = self.ledger()
                anchor = ledger["values"][1]["anchor"]
                if region_kind == "wrong":
                    anchor["char_start"] += 1
                    anchor["char_end"] += 1
                elif region_kind == "out_of_range":
                    anchor["char_end"] = 10000
                else:
                    del anchor["char_start"]
                    del anchor["char_end"]
                _process, output = self.run_verify(ledger, expected=1)
                verification = load_json(output / "verification.json")
                check = verification["source_values"][1]["quote_check"]
                expected_status = {"wrong": "region_not_matched", "out_of_range": "invalid_region", "legacy": "locator_not_checked"}[region_kind]
                self.assertEqual(expected_status, check["status"])
                self.assertEqual("failed", verification["status"])
                self.assertEqual("anchor_failed", verification["calculations"][0]["status"])
                self.assertFalse(verification["calculations"][0]["match"])

        missing_source = self.ledger()
        missing_source["values"][0]["anchor"]["source_id"] = "nonexistent-source"
        process, _output = self.run_verify(missing_source, expected=2)
        self.assertIn("unknown source", process.stderr)

    def test_bundled_example_uses_missing_for_unsupplied_original(self):
        case_path = EXAMPLE / "case.json"
        output = self.work / "example-output"
        process = subprocess.run(
            [os.sys.executable, str(NRD), "run", "--case", str(case_path), "--task", str(EXAMPLE / "task.md"),
             "--materials", str(EXAMPLE / "materials"), "--output-dir", str(output), "--fail-on-mismatch"],
            cwd=str(BUNDLE), env=self.env(), text=True, capture_output=True, check=False,
        )
        self.assertEqual(0, process.returncode, process.stdout + process.stderr)
        verification = load_json(output / "verification.json")
        figure = next(item for item in verification["source_values"] if item["value_id"] == "figure_1_a_high_control")
        self.assertEqual("missing", figure["provenance"])
        visual = verification["visual_comparison"]
        self.assertEqual("missing", visual["original_render"]["status"])
        self.assertEqual("missing", visual["original_crop"]["status"])
        self.assertEqual("missing", visual["original_review"]["status"])
        result = load_json(output / "result.json")
        self.assertIn("missing", result["notes"]["visual_comparison"])
        self.assertNotIn("Original Figure 1 is not_reported", json.dumps(verification))

    def assert_svg_geometry(self, svg_path, expected_ids):
        root = ET.parse(str(svg_path)).getroot()
        self.assertEqual("0 0 1000 620", root.attrib["viewBox"])
        bars = [node for node in root.iter("{http://www.w3.org/2000/svg}rect") if "data-value-id" in node.attrib]
        self.assertEqual(set(expected_ids), {node.attrib["data-value-id"] for node in bars})
        for bar in bars:
            x, y = float(bar.attrib["x"]), float(bar.attrib["y"])
            width, height = float(bar.attrib["width"]), float(bar.attrib["height"])
            self.assertGreaterEqual(x, 0)
            self.assertGreaterEqual(y, 130)
            self.assertLessEqual(x + width, 1000)
            self.assertLessEqual(y + height, 440)
        ticks = [node for node in root.iter("{http://www.w3.org/2000/svg}text") if "tick" in node.attrib.get("class", "")]
        self.assertEqual(6, len(ticks))
        for tick in ticks:
            self.assertGreaterEqual(float(tick.attrib["y"]), 0)
            self.assertLessEqual(float(tick.attrib["y"]), 620)
        return root, bars, ticks

    def test_negative_mixed_sign_zero_and_unit_aware_svg(self):
        ledger = self.ledger(numbers=("-10", "0", "15"), units=("ms", "ms", "ms"), visual=True)
        _process, output = self.run_verify(ledger)
        svg_path = output / "comparison.svg"
        root, bars, ticks = self.assert_svg_geometry(svg_path, {"a", "b", "c"})
        svg = svg_path.read_text(encoding="utf-8")
        self.assertIn("Value (ms)", svg)
        self.assertNotIn("Error (%)", svg)
        self.assertTrue(any((tick.text or "").startswith("-") for tick in ticks))
        zero = next(bar for bar in bars if bar.attrib["data-value-id"] == "b")
        self.assertEqual(0.0, float(zero.attrib["height"]))

        all_zero = self.ledger(numbers=("0", "0", "0"), visual=True)
        _process, output = self.run_verify(all_zero)
        _root, bars, _ticks = self.assert_svg_geometry(output / "comparison.svg", {"a", "b", "c"})
        self.assertTrue(all(float(bar.attrib["height"]) == 0 for bar in bars))

        valid_label = self.ledger(numbers=("-10", "0", "15"), units=("ms", "ms", "ms"), visual=True)
        valid_label["visual_comparison"]["axis_label"] = "Latency (ms)"
        _process, output = self.run_verify(valid_label)
        self.assertIn("Latency (ms)", (output / "comparison.svg").read_text(encoding="utf-8"))

    def test_svg_rejects_mixed_units_and_mismatched_axis_label(self):
        mixed = self.ledger(numbers=("1", "2"), units=("ms", "percent"), visual=True)
        mixed["calculations"] = [{
            "calculation_id": "division_allows_distinct_input_units",
            "operation": "division", "provenance": "independently_calculated", "direction": "signed",
            "operands": {"numerator": "a", "denominator": "b"}, "output_unit": "dimensionless",
            "expected": "0.5", "expected_basis": "test fixture division",
            "tolerance": {"type": "absolute", "value": "0"},
            "rounding": {"places": 2, "mode": "ROUND_HALF_UP"},
        }]
        process, _output = self.run_verify(mixed, expected=2)
        self.assertIn("mixed canonical units", process.stderr)

        wrong_label = self.ledger(numbers=("1", "2"), units=("ms", "ms"), visual=True)
        wrong_label["visual_comparison"]["axis_label"] = "Error (%)"
        process, _output = self.run_verify(wrong_label, expected=2)
        self.assertIn("axis_label", process.stderr)

    def test_bundled_example_preserves_thirteen_checks_and_special_result(self):
        output = self.work / "full-example"
        process = subprocess.run(
            ["sh", str(BUNDLE / "scripts" / "run_example.sh"), str(output)],
            cwd=str(BUNDLE), env=self.env(), text=True, capture_output=True, check=False,
        )
        self.assertEqual(0, process.returncode, process.stdout + process.stderr)
        verification = load_json(output / "verification.json")
        self.assertEqual("passed", verification["status"])
        self.assertEqual(13, verification["summary"]["calculations_total"])
        self.assertEqual(13, verification["summary"]["matched"])
        calculations = {item["calculation_id"]: item for item in verification["calculations"]}
        self.assertEqual("25.00", calculations["a_high_relative_reduction"]["actual_rounded"])
        self.assertEqual("10.00", calculations["a_high_pp_reduction"]["actual_rounded"])
        self.assertTrue(all(value["quote_check"]["status"] in ("matched", "not_applicable") for value in verification["source_values"]))
        self.assert_svg_geometry(output / "comparison.svg", {
            "a_high_control", "a_high_treatment", "b_high_control", "b_high_treatment",
            "a_low_control", "a_low_treatment", "b_low_control", "b_low_treatment",
        })


if __name__ == "__main__":
    unittest.main()
