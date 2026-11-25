#!/usr/bin/env python3
"""Executable unit/integration checks; all writes stay under --work."""
import argparse
import copy
import importlib.util
import json
import math
from pathlib import Path
import subprocess
import sys

sys.dont_write_bytecode = True


def load(path):
    return json.loads(path.read_text(encoding="utf-8"))


def dump(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--example", required=True, type=Path)
    p.add_argument("--work", required=True, type=Path)
    args = p.parse_args()
    example = args.example.resolve()
    root = args.work.resolve()
    root.mkdir(parents=True, exist_ok=True)
    engine = (example / "../../scripts/paper_figure_twin.py").resolve()
    spec_base = load(example / "spec.json")
    case_base = load(example / "case.json")
    # Inline checks cover logarithmic calibration, the overlap guard, and every
    # supported output_contract family, including standard names in a contract.
    spec = importlib.util.spec_from_file_location("paper_figure_twin", engine)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    fit = module.fit_axis({"pixel_scale": "log", "anchors": [{"pixel": 0, "value": 1}, {"pixel": 100, "value": 100}]}, "x")
    assert math.isclose(module.pixel_to_value(50, fit), 10, rel_tol=1e-12)
    paper = [{"x": 0.0, "y": 1.0, "pixel_x": 0, "pixel_y": 0}, {"x": 1.0, "y": 1.1, "pixel_x": 1, "pixel_y": 1}]
    candidate = {"id": "disjoint", "points": [{"x": 10.0, "y": 0}, {"x": 11.0, "y": 0}]}
    try:
        module.compare_series(paper, candidate)
        raise AssertionError("zero-width overlap was not rejected")
    except module.PartialError:
        pass
    assert module.extract_contract_fields(["summary", {"name": "custom"}]) == ["summary", "custom"]
    assert module.extract_contract_fields({"case_id": {"type": "string"}, "summary": {}, "optional": {"required": False}}) == ["case_id", "summary"]
    assert module.extract_contract_fields({"fields": [{"key": "summary"}], "required_fields": ["custom"]}) == ["summary", "custom"]
    assert module.extract_contract_fields({"required_fields": ["status", "sources"]}) == ["status", "sources"]
    assert module.extract_contract_fields({
        "type": "object",
        "properties": {"summary": {"type": "string"}, "custom": {"type": "object"}, "optional": {"type": "string"}},
        "required": ["summary", "custom"],
    }) == ["summary", "custom"]

    custom_value = {
        "value": "top-level-required-by-case-schema",
        "evidence_path": "../case.json",
        "evidence": "case.json output_contract.required explicitly declares custom_delivery; this delivery fixture is not a scientific metric.",
    }

    def schema_contract():
        required = ["case_id", "status", "sources", "uncertainty", "change_records", "summary",
                    "comparison", "mapping", "report", "reproduction_verdict", "custom_delivery"]
        return {"type": "object",
                "properties": {name: {"type": ["object", "string", "array", "null"]} for name in required},
                "required": required}

    def prepared(kind):
        case = copy.deepcopy(case_base)
        spec_copy = copy.deepcopy(spec_base)
        case["case_id"] = "test-" + kind
        case["task"] = str(example / "task.md")
        for candidate_spec in case["candidates"]:
            candidate_spec["command"][0] = sys.executable
            candidate_spec["command"][1] = str(engine)
            candidate_spec["cwd"] = str(example)
        spec_copy["figure"]["source_file"] = str(example / "paper_figure.svg")
        spec_copy["series"][0]["points_file"] = str(example / "paper_points.json")
        test_work = root / kind / "work"
        test_output = root / kind / "output"
        test_work.mkdir(parents=True, exist_ok=True)
        spec_path = root / kind / "spec.json"
        case["spec"] = str(spec_path)
        case_path = root / kind / "case.json"
        dump(spec_path, spec_copy)
        dump(case_path, case)
        return case, spec_copy, case_path, spec_path, test_work, test_output

    def assert_flattened(case, result):
        for field in module.BASE_FIELDS:
            assert field in result, (case["case_id"], field)
        for field in module.extract_contract_fields(case.get("output_contract")):
            assert field in result, (case["case_id"], field)
        assert result["status"] in {"success", "partial", "unable", "refused"}
        assert "output_contract" not in result

    records = []
    for kind in ("missing_anchor", "no_x_overlap"):
        case, spec_copy, case_path, spec_path, test_work, test_output = prepared(kind)
        case["candidates"] = [copy.deepcopy(case_base["candidates"][0])]
        case["candidates"][0]["command"][0] = sys.executable
        case["candidates"][0]["command"][1] = str(engine)
        case["candidates"][0]["cwd"] = str(example)
        spec_copy["series"][0]["candidate_series"] = [spec_copy["series"][0]["candidate_series"][0]]
        if kind == "missing_anchor":
            spec_copy["axes"]["x"]["anchors"] = []
        else:
            case["output_contract"] = schema_contract()
            spec_copy["contract_values"] = {"custom_delivery": custom_value}
            shifted = {"series": [{"id": "a_s1", "unit": "mV", "x_definition": "time_since_start_s",
                                   "source": {"method": "negative disjoint-x fixture"},
                                   "points": [{"x": 100, "y": 1}, {"x": 101, "y": 1}]}]}
            fixture = test_work / "shifted_fixture.json"
            dump(fixture, shifted)
            case["candidates"][0]["command"] = [sys.executable, "-c",
                "import shutil,sys; shutil.copyfile(sys.argv[1],sys.argv[2])", str(fixture), "{work}/candidate_a.json"]
            case["candidates"][0]["output"] = "{work}/candidate_a.json"
        dump(spec_path, spec_copy)
        dump(case_path, case)
        proc = subprocess.run([sys.executable, str(engine), "compare", "--case", str(case_path),
                               "--work", str(test_work), "--output", str(test_output)],
                              text=True, capture_output=True, check=False)
        result = load(test_output / "result.json")
        assert proc.returncode == 1, (kind, proc.returncode, proc.stdout, proc.stderr)
        assert result["status"] == "partial" and result["case_id"] == "test-" + kind
        assert result["reproduction_verdict"] == "not_comparable"
        assert "PARTIAL:" in proc.stderr
        assert_flattened(case, result)
        if kind == "no_x_overlap":
            assert result["custom_delivery"] == custom_value
            assert not Path(custom_value["evidence_path"]).is_absolute()
            assert (test_output / custom_value["evidence_path"]).resolve().is_file()
            assert result["summary"]
        assert not (test_output / "comparison.json").exists(), kind + " fabricated comparison"
        records.append({"test": kind, "exit_code": proc.returncode, "status": result["status"],
                        "reproduction_verdict": result["reproduction_verdict"],
                        "contract_fields_flattened": module.extract_contract_fields(case["output_contract"]),
                        "stderr": proc.stderr.strip(), "comparison_created": False})

    # A complete JSON Schema run proves custom fields are data-driven rather than
    # hardcoded, while a numeric reproduction failure remains task success/exit 2.
    case, _, schema_case_path, schema_spec_path, schema_work, schema_output = prepared("json_schema_contract")
    case["output_contract"] = schema_contract()
    schema_spec = load(schema_spec_path)
    schema_spec["contract_values"] = {"custom_delivery": custom_value}
    dump(schema_spec_path, schema_spec)
    dump(schema_case_path, case)
    proc = subprocess.run([sys.executable, str(engine), "compare", "--case", str(schema_case_path),
                           "--work", str(schema_work),
                           "--output", str(schema_output)], text=True, capture_output=True, check=False)
    result = load(schema_output / "result.json")
    assert proc.returncode == 2, (proc.returncode, proc.stdout, proc.stderr)
    assert result["status"] == "success" and result["reproduction_verdict"] == "fail"
    assert result["custom_delivery"] == custom_value
    assert (schema_output / custom_value["evidence_path"]).resolve().is_file()
    assert result["errors"] == []
    assert_flattened(case, result)
    records.append({"test": "json_schema_contract", "exit_code": proc.returncode,
                    "status": result["status"], "reproduction_verdict": result["reproduction_verdict"],
                    "custom_field": "custom_delivery", "custom_field_preserved": True})

    # Complete computation with an unknown required value is incomplete delivery:
    # keep the honest scientific verdict but use partial/exit 1 and never invent it.
    case, _, unknown_case_path, _, unknown_work, unknown_output = prepared("unknown_contract_field")
    case["output_contract"] = ["summary", "custom_without_evidence"]
    dump(unknown_case_path, case)
    proc = subprocess.run([sys.executable, str(engine), "compare", "--case", str(unknown_case_path),
                           "--work", str(unknown_work),
                           "--output", str(unknown_output)], text=True, capture_output=True, check=False)
    result = load(unknown_output / "result.json")
    assert proc.returncode == 1, (proc.returncode, proc.stdout, proc.stderr)
    assert result["status"] == "partial" and result["reproduction_verdict"] == "fail"
    unavailable = result["custom_without_evidence"]
    assert isinstance(unavailable, dict) and unavailable["status"] == "unavailable"
    assert unavailable["evidence_required"] is True
    assert (unknown_output / "comparison.json").is_file(), "real numeric work must not be erased"
    assert_flattened(case, result)
    records.append({"test": "unknown_contract_field", "exit_code": proc.returncode,
                    "status": result["status"], "reproduction_verdict": result["reproduction_verdict"],
                    "unknown_value": "structured_unavailable", "comparison_created": True})

    # Without a readable case there is no reliable case_id or contract to flatten.
    unable_dir = root / "unreadable_case"
    unable_output = unable_dir / "output"
    unable_dir.mkdir(parents=True, exist_ok=True)
    bad_case = unable_dir / "case.json"
    bad_case.write_text("{not-json\n", encoding="utf-8")
    proc = subprocess.run([sys.executable, str(engine), "compare", "--case", str(bad_case),
                           "--work", str(unable_dir / "work"), "--output", str(unable_output)],
                          text=True, capture_output=True, check=False)
    result = load(unable_output / "result.json")
    assert proc.returncode == 1 and result["status"] == "unable"
    assert result["case_id"] == "unknown" and result["reproduction_verdict"] == "not_comparable"
    assert all(field in result for field in module.BASE_FIELDS)
    records.append({"test": "unreadable_case", "exit_code": proc.returncode,
                    "status": result["status"], "reproduction_verdict": result["reproduction_verdict"]})

    dump(root / "negative_results.json", {
        "log_axis_check": "pass", "primitive_overlap_check": "pass",
        "contract_parser_checks": ["list", "mapping", "fields", "required_fields", "json_schema"],
        "integration": records,
    })
    print(json.dumps({"status": "pass", "checks": records}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
