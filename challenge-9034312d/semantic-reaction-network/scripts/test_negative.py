#!/usr/bin/env python3
"""Meaningful semantic negative tests: regulation retyping and unsupported endpoints."""
import argparse
import copy
import json
from pathlib import Path
import sys
import tempfile

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from srn import build, dump_json, load_json, validate_graph  # noqa: E402


def codes(issues):
    return {item["code"] for item in issues if item["level"] == "error"}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--example-dir", type=Path, default=HERE.parent / "examples" / "synthetic")
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()
    graph_path = (args.example_dir / "input" / "semantic_graph.json").resolve()
    original = load_json(graph_path)

    wrong = copy.deepcopy(original)
    edge = next(e for e in wrong["edges"] if e["kind"] == "inhibition")
    edge["kind"] = "material_flow"
    edge["visual"]["marker"] = "arrow"
    wrong_issues, _ = validate_graph(wrong, graph_path.parent)
    inhibition_rejected = "PORT_CARRIER_INCOMPATIBLE" in codes(wrong_issues)

    unsupported = copy.deepcopy(original)
    bad_endpoint = copy.deepcopy(next(e for e in unsupported["edges"] if e["kind"] == "catalysis"))
    bad_endpoint["id"] = "e-negative-unsupported-endpoint"
    bad_endpoint["from"] = {"node": "assay", "port": "series"}
    bad_endpoint["to"] = {"node": "chart", "port": "data_in"}
    unsupported["edges"].append(bad_endpoint)
    unsupported_issues, _ = validate_graph(unsupported, graph_path.parent)
    endpoint_rejected = "ENDPOINT_TYPE_INCOMPATIBLE" in codes(unsupported_issues)

    temp_parent = args.report.resolve().parent if args.report else HERE
    temp_parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="srn-negative-", dir=str(temp_parent)) as tmp:
        root = Path(tmp)
        wrong_path = root / "inhibition-as-material.json"
        dump_json(wrong_path, wrong)
        wrong_output = root / "wrong-output"
        wrong_output.mkdir(parents=True)
        (wrong_output / "figure.svg").write_text("<svg xmlns=\"http://www.w3.org/2000/svg\"><!-- stale prior artifact --></svg>\n", encoding="utf-8")
        wrong_returncode = build(wrong_path, wrong_output, None)
        wrong_result = load_json(wrong_output / "result.json")
        stale_svg_not_claimed = (wrong_result["editable_svg"] is None and
                                 not wrong_result["export_checks"]["svg_well_formed"])
        unsupported_path = root / "unsupported-endpoint.json"
        dump_json(unsupported_path, unsupported)
        endpoint_returncode = build(unsupported_path, root / "endpoint-output", None)

    report = {
        "test": "semantic negative controls",
        "positive_graph_error_count": len(codes(validate_graph(original, graph_path.parent)[0])),
        "cases": [
            {
                "name": "inhibition_encoded_as_material_flow",
                "expected": "nonzero build / semantic error",
                "detected_codes": sorted(codes(wrong_issues)),
                "build_returncode": wrong_returncode,
                "stale_svg_not_claimed_after_error": stale_svg_not_claimed,
                "passed": inhibition_rejected and stale_svg_not_claimed and wrong_returncode != 0 and wrong_issues != validate_graph(original, graph_path.parent)[0],
            },
            {
                "name": "unsupported_catalysis_endpoint",
                "expected": "nonzero build / semantic error",
                "detected_codes": sorted(codes(unsupported_issues)),
                "build_returncode": endpoint_returncode,
                "passed": endpoint_rejected and endpoint_returncode != 0,
            },
        ],
    }
    report["passed"] = report["positive_graph_error_count"] == 0 and all(c["passed"] for c in report["cases"])
    text = json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    print(text, end="")
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(text, encoding="utf-8", newline="\n")
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
