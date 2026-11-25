#!/usr/bin/env python3
"""Run the clearly labelled SYNTHETIC minimal example; no external packages."""
from pathlib import Path
import argparse
import sys

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from srn import build, load_json  # noqa: E402


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--example-dir", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--preview-png", type=Path)
    parser.add_argument("--preview-pdf", type=Path)
    args = parser.parse_args()
    graph = args.example_dir / "input" / "semantic_graph.json"
    if not graph.is_file():
        graph = args.example_dir / "semantic_graph.json"
    if not graph.is_file():
        parser.error("No input/semantic_graph.json (or semantic_graph.json) in example directory.")
    data = load_json(graph)
    if data.get("synthetic") is not True or not data.get("case_id", "").startswith("SYNTHETIC-"):
        parser.error("run_example.py is reserved for explicitly labelled SYNTHETIC inputs.")
    case_path = graph.parent / "case.json"
    task_path = graph.parent / "task.md"
    if not case_path.is_file() or not task_path.is_file():
        parser.error("Synthetic examples must include actual case.json and task.md beside the graph.")
    case = load_json(case_path)
    task_text = task_path.read_text(encoding="utf-8")
    if case.get("case_id") != data.get("case_id") or case.get("output_contract") != data.get("output_contract"):
        parser.error("case.json identity/output_contract must exactly match the semantic graph.")
    if case.get("synthetic") is not True or "SYNTHETIC" not in task_text.upper():
        parser.error("case.json and task.md must be explicitly labelled SYNTHETIC.")
    return build(graph, args.output_dir, args.preview_png, args.preview_pdf)


if __name__ == "__main__":
    raise SystemExit(main())
