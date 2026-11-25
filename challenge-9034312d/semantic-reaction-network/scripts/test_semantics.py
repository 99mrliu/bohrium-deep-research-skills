#!/usr/bin/env python3
"""Focused validator regression checks; all fixtures are SYNTHETIC mutations."""
import argparse
import copy
import json
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from srn import load_json, validate_graph  # noqa: E402


def error_codes(graph, base):
    return sorted({i["code"] for i in validate_graph(graph, base)[0] if i["level"] == "error"})


def add_cycle(graph):
    graph["nodes"] = copy.deepcopy(graph["nodes"])
    product = next(n for n in graph["nodes"] if n["id"] == "product")
    substrate = next(n for n in graph["nodes"] if n["id"] == "substrate")
    product["ports"].append({"id": "recycle_out", "direction": "out", "carrier": "material"})
    substrate["ports"].append({"id": "recycle_in", "direction": "in", "carrier": "material"})
    graph["edges"].append({
        "id": "synthetic-recycle", "kind": "material_flow",
        "from": {"node": "product", "port": "recycle_out"},
        "to": {"node": "substrate", "port": "recycle_in"},
        "source_refs": ["methods03"], "visual": {"marker": "arrow"}
    })


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--example-dir", type=Path, default=HERE.parent / "examples" / "synthetic")
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()
    graph_path = (args.example_dir / "input" / "semantic_graph.json").resolve()
    base = graph_path.parent
    original = load_json(graph_path)
    checks = []

    def check(name, graph, expected=(), absent=()):
        codes = error_codes(graph, base)
        passed = all(code in codes for code in expected) and all(code not in codes for code in absent)
        checks.append({"name": name, "expected_present": list(expected), "expected_absent": list(absent),
                       "detected_codes": codes, "passed": passed})

    cycle = copy.deepcopy(original)
    add_cycle(cycle)
    check("cycle_requires_explicit_feedback", cycle, ["UNDECLARED_FEEDBACK_CYCLE"])
    feedback = copy.deepcopy(cycle)
    next(e for e in feedback["edges"] if e["id"] == "synthetic-recycle")["feedback"] = True
    check("explicit_feedback_legalizes_only_actual_cycle", feedback, [],
          ["UNDECLARED_FEEDBACK_CYCLE", "CYCLE_WITHOUT_FEEDBACK_ON_EACH_PATH", "FEEDBACK_NOT_CYCLIC"])
    false_feedback = copy.deepcopy(original)
    next(e for e in false_feedback["edges"] if e["kind"] == "inhibition")["feedback"] = True
    check("feedback_outside_cycle_rejected", false_feedback, ["FEEDBACK_NOT_CYCLIC"])

    generic = copy.deepcopy(original)
    edge = next(e for e in generic["edges"] if e["kind"] == "inhibition")
    edge["kind"] = "activation"
    edge["visual"]["marker"] = "arrow"
    check("generic_activation_arrow_rejected", generic, ["REGULATION_MARKER"])

    disconnected = copy.deepcopy(original)
    disconnected["edges"] = [e for e in disconnected["edges"] if e["id"] != "e-readout-chart"]
    check("required_chart_disconnection_rejected", disconnected, ["DISCONNECTED_REQUIRED_NODES"])

    branch = copy.deepcopy(original)
    duplicate = copy.deepcopy(next(e for e in branch["edges"] if e["id"] == "e-substrate-conversion"))
    duplicate["id"] = "synthetic-second-substrate-route"
    branch["edges"].append(duplicate)
    ids = ["e-substrate-conversion", "synthetic-second-substrate-route"]
    check("fanout_fanin_require_declarations", branch, ["UNDECLARED_BRANCH", "UNDECLARED_JOIN"])
    resolved = copy.deepcopy(branch)
    resolved["branches"] = [{"id": "synthetic-branch", "node": "substrate", "family": "material",
                             "mode": "all", "edge_ids": ids, "source_refs": ["methods03"]}]
    resolved["joins"] = [{"id": "synthetic-join", "node": "reaction", "family": "material",
                          "mode": "all", "edge_ids": ids, "source_refs": ["methods03"]}]
    check("exact_branch_join_declarations_accepted", resolved, [],
          ["UNDECLARED_BRANCH", "UNDECLARED_JOIN", "BRANCH_JOIN_EDGE_SET"])

    phase = copy.deepcopy(original)
    phase["phase_dependencies"].append({"from_phase": "detection", "to_phase": "reaction",
                                       "type": "precedes", "source_refs": ["methods03"]})
    check("ambiguous_phase_cycle_rejected", phase, ["PHASE_CYCLE"])
    graph = copy.deepcopy(original)
    next(n for n in graph["nodes"] if n["id"] == "chart")["chart"]["x"] = "not_a_csv_header"
    check("nonexistent_chart_header_rejected", graph, ["CHART_COLUMN_MISSING"])

    report = {"fixture": "SYNTHETIC validator mutations only", "positive_codes": error_codes(original, base),
              "passed": not error_codes(original, base) and all(c["passed"] for c in checks), "checks": checks}
    text = json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    print(text, end="")
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(text, encoding="utf-8", newline="\n")
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
