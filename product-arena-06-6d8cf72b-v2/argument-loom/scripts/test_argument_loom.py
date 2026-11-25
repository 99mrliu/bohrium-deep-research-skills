#!/usr/bin/env python3
"""Black-box positive and deliberate negative self-tests; uses temporary dirs only."""

import copy
import json
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "scripts" / "argument_loom.py"
EXAMPLE = ROOT / "examples" / "synthetic"


def run(arguments):
    return subprocess.run([sys.executable, str(SCRIPT)] + arguments,
                          text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)


def load(path):
    return json.loads(path.read_text(encoding="utf-8"))


def dump(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def assert_true(condition, message):
    if not condition:
        raise AssertionError(message)


def assemble_fixture(root, name, case, source, graph, response=None):
    fixture = root / name
    case_path, source_path, graph_path = fixture / "case.json", fixture / "source.json", fixture / "graph.json"
    dump(case_path, case)
    dump(source_path, source)
    dump(graph_path, graph)
    arguments = ["assemble", "--case", str(case_path), "--source", str(source_path),
                 "--graph", str(graph_path), "--output-dir", str(fixture / "output")]
    if response is not None:
        response_path = fixture / "response.json"
        dump(response_path, response)
        arguments.extend(["--response", str(response_path)])
    return run(arguments), fixture / "output"


def main():
    case_path = EXAMPLE / "case.json"
    source_path = EXAMPLE / "sources" / "paper.json"
    graph_path = EXAMPLE / "graph.input.json"
    case, source, graph = load(case_path), load(source_path), load(graph_path)
    with tempfile.TemporaryDirectory(prefix="argument-loom-selftest-") as temporary:
        root = Path(temporary)
        positive = root / "positive"
        completed = run(["assemble", "--case", str(case_path), "--source", str(source_path),
                         "--graph", str(graph_path), "--output-dir", str(positive)])
        assert_true(completed.returncode == 0, "positive assembly failed: " + completed.stdout + completed.stderr)
        result = load(positive / "result.json")
        notes = (positive / "notes.md").read_text(encoding="utf-8")
        graph_md = (positive / "graph.md").read_text(encoding="utf-8")
        assert_true(load(positive / "audit.json")["status"] == "PASS", "positive audit did not PASS")
        assert_true("合成示例" in result["summary"] and "non-official" in notes and "SYNTHETIC" in graph_md,
                    "synthetic/non-official labels missing")
        print("PASS positive: synthetic example remains labelled")

        real_case, real_source, real_graph = copy.deepcopy(case), copy.deepcopy(source), copy.deepcopy(graph)
        real_case.pop("synthetic", None)
        real_case["case_id"] = "real-five-sections"
        real_case["output_contract"]["properties"]["case_id"]["const"] = "real-five-sections"
        real_case["output_contract"]["properties"]["status"]["enum"] = ["success", "partial", "failed"]
        real_source.pop("label", None)
        real_source["sections"] = real_source["sections"][:5]
        real_graph.pop("example_label", None)
        real_graph["sections"] = real_graph["sections"][:5]
        real_graph["nodes"] = [node for node in real_graph["nodes"]
                               if node["section_id"] != "conclusion" and node["id"] != "W2"]
        retained_ids = {node["id"] for node in real_graph["nodes"]}
        real_graph["edges"] = [edge for edge in real_graph["edges"]
                               if edge["from"] in retained_ids and edge["to"] in retained_ids]
        real_graph["uncertainties"] = ["Interpretation remains bounded to the supplied source."]
        real_graph["change_records"] = []
        real_completed, real_output = assemble_fixture(root, "real-five", real_case, real_source, real_graph)
        assert_true(real_completed.returncode == 0, "five-section real assembly failed: " + real_completed.stdout + real_completed.stderr)
        real_result = load(real_output / "result.json")
        real_notes = (real_output / "notes.md").read_text(encoding="utf-8")
        real_graph_md = (real_output / "graph.md").read_text(encoding="utf-8")
        generated_text = real_result["summary"] + real_notes + real_graph_md
        assert_true("SYNTHETIC" not in generated_text and "合成示例" not in generated_text and
                    "non-official" not in generated_text, "real artifacts falsely received synthetic banners")
        assert_true("six" not in real_notes.lower() and "6. Conclusion" not in real_notes and
                    "six" not in real_result["source_status"][0]["detail"].lower(), "hardcoded six-section text remains")
        assert_true("5 registered sections" in real_result["source_status"][0]["detail"] and
                    real_result["status"] == "success", "dynamic section count or success enum adaptation failed")
        print("PASS real/status: five sections, no synthetic/six-section text, success enum")

        for semantic_status in ("unreviewed", "disputed"):
            open_graph = copy.deepcopy(graph)
            next(node for node in open_graph["nodes"] if node["id"] == "C1")["semantic_status"] = semantic_status
            open_completed, open_output = assemble_fixture(root, "open-" + semantic_status, case, source, open_graph,
                                                           response={"status": "complete"})
            assert_true(open_completed.returncode == 0, semantic_status + " graph was not structurally accepted")
            open_result = load(open_output / "result.json")
            assert_true(open_result["status"] == "partial" and any("C1" in item for item in open_result["uncertainties"]),
                        semantic_status + " core claim did not force partial or could be upgraded by response: " + repr(open_result))
        partial_source = copy.deepcopy(source)
        partial_source["status"] = "partial"
        gap_completed, gap_output = assemble_fixture(root, "source-gap", case, partial_source, graph)
        assert_true(gap_completed.returncode == 0 and load(gap_output / "result.json")["status"] == "partial",
                    "source gap did not force partial")
        print("PASS semantic/source gaps: unreviewed, disputed, and partial sources downgrade")

        incompatible_case = copy.deepcopy(case)
        incompatible_case["output_contract"]["properties"]["status"]["enum"] = ["complete"]
        open_graph = copy.deepcopy(graph)
        next(node for node in open_graph["nodes"] if node["id"] == "C1")["semantic_status"] = "unreviewed"
        incompatible, incompatible_output = assemble_fixture(root, "incompatible-status", incompatible_case, source, open_graph)
        assert_true(incompatible.returncode != 0 and "STATUS_ENUM" in
                    {issue["code"] for issue in load(incompatible_output / "audit.json")["issues"]} and
                    not (incompatible_output / "result.json").exists(),
                    "incompatible status enum was not rejected honestly")
        print("PASS incompatible status: cannot falsely upgrade required partial to complete")

        response_case = copy.deepcopy(case)
        response_case["output_contract"]["properties"]["answer"] = {"type": "string", "minLength": 1}
        response_case["output_contract"]["properties"]["analysis"] = {
            "type": "object", "additionalProperties": False, "required": ["direct"],
            "properties": {"direct": {"type": "string", "minLength": 1}}
        }
        missing_response, missing_output = assemble_fixture(root, "missing-response", response_case, source, graph)
        assert_true(missing_response.returncode != 0 and not (missing_output / "result.json").exists() and
                    {"answer", "analysis"} == {issue["path"].split(".")[-1] for issue in
                     load(missing_output / "audit.json")["issues"] if issue["code"] == "RESPONSE_FIELD"},
                    "declared optional direct-answer fields were silently omitted")
        response = {"answer": "The direct answer.", "analysis": {"direct": "Preserved contract-native detail."}}
        response_completed, response_output = assemble_fixture(root, "response", response_case, source, graph, response)
        assert_true(response_completed.returncode == 0, "response overlay assembly failed: " + response_completed.stderr)
        response_result = load(response_output / "result.json")
        assert_true(response_result["answer"] == response["answer"] and response_result["analysis"] == response["analysis"] and
                    response_result["outputs"]["argument_graph"] == "argument_graph.json" and
                    response_result["uncertainties"] and response_result["change_records"],
                    "response overlay dropped direct answers or generated graph metadata")
        print("PASS response overlay: declared direct answers and graph metadata coexist")

        broken_graph = copy.deepcopy(graph)
        next(node for node in broken_graph["nodes"] if node["id"] == "C1")["anchor"]["quote"] = "a quote that does not occur in the source"
        next(node for node in broken_graph["nodes"] if node["id"] == "C1")["limit_status"] = "not_reported"
        broken_graph["edges"] = [edge for edge in broken_graph["edges"]
                                 if not (edge["to"] == "C1" and edge["type"] == "supports")]
        broken, broken_output = assemble_fixture(root, "broken-graph", case, source, broken_graph)
        assert_true(broken.returncode != 0, "broken graph falsely returned success")
        broken_audit = load(broken_output / "audit.json")
        codes = {issue["code"] for issue in broken_audit["issues"]}
        assert_true(broken_audit["status"] == "FAIL" and
                    {"ANCHOR_QUOTE", "MISSING_EVIDENCE", "LIMIT_EDGE_UNEXPECTED"} <= codes,
                    "broken graph failures were not specific: " + repr(codes))
        assert_true(load(broken_output / "result.json")["status"] == "failed" and
                    "unavailable" in (broken_output / "notes.md").read_text(encoding="utf-8").lower() and
                    load(broken_output / "argument_graph.json") == broken_graph,
                    "broken graph lacked contract-valid honest failure artifacts or input preservation")
        broken_case_path = root / "broken-graph" / "case.json"
        checked = run(["check-result", "--case", str(broken_case_path), "--result", str(broken_output / "result.json"),
                       "--output", str(broken_output / "contract-audit.json")])
        assert_true(checked.returncode == 0 and load(broken_output / "contract-audit.json")["status"] == "PASS",
                    "early failed result is not contract-valid")

        malformed_dir = root / "malformed-graph"
        malformed_dir.mkdir()
        malformed_graph_path = malformed_dir / "graph.json"
        malformed_graph_path.write_text("{not valid JSON", encoding="utf-8")
        malformed_output = malformed_dir / "output"
        malformed = run(["assemble", "--case", str(case_path), "--source", str(source_path),
                         "--graph", str(malformed_graph_path), "--output-dir", str(malformed_output)])
        assert_true(malformed.returncode != 0 and load(malformed_output / "result.json")["status"] == "failed" and
                    "GRAPH_INPUT" in {issue["code"] for issue in load(malformed_output / "audit.json")["issues"]} and
                    "nodes" not in load(malformed_output / "argument_graph.json"),
                    "unreadable graph did not produce an honest contract-valid failure result")
        print("PASS honest failure: invalid and unreadable graphs emit failed results without fabricated graph content")

        broken_result = copy.deepcopy(result)
        broken_result["uncontracted"] = "must be rejected"
        broken_result["outputs"]["extra"] = "nested-extra.txt"
        broken_result["case_id"] = "wrong-case"
        broken_result_path = root / "broken-result.json"
        dump(broken_result_path, broken_result)
        contract_audit_path = root / "broken-contract-audit.json"
        contract = run(["check-result", "--case", str(case_path), "--result", str(broken_result_path),
                        "--output", str(contract_audit_path)])
        assert_true(contract.returncode != 0, "broken result falsely returned success")
        contract_audit = load(contract_audit_path)
        contract_codes = [issue["code"] for issue in contract_audit["issues"]]
        assert_true(contract_audit["status"] == "FAIL" and contract_codes.count("ADDITIONAL_PROPERTY") == 2 and
                    "CASE_ID" in contract_codes, "contract failures were not specific: " + repr(contract_codes))
        print("PASS negative contract: nested/top-level additions and wrong case rejected")

        malformed_invocation = run([])
        assert_true(malformed_invocation.returncode != 0, "malformed invocation falsely returned success")
        print("PASS malformed invocation: nonzero from explicit CLI parser")
    print("SELF-TEST PASS: synthetic/real, response, semantic, enum, failure, and contract regressions passed")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (AssertionError, OSError, json.JSONDecodeError) as exc:
        print("SELF-TEST FAIL: " + str(exc), file=sys.stderr)
        sys.exit(1)
