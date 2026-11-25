#!/usr/bin/env python3
"""Run the labelled SYNTHETIC before/defect -> after/corrected QC example."""
from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path
from typing import Any

from artifact_observer import build_observations, dump_json
from contract_audit import audit as audit_contract
from edit_diff import build_diff as build_edit_diff
from export_audit import build_report as build_export_report
from fixture_svg import fixture_svg, render_svg_png
from png_diff import build_diff as build_visual_diff
from semantic_gate import build_report as build_qc_report

REQUIRED_NEGATIVE_CODES = {"LABEL_MISMATCH", "DIRECTION_MISMATCH", "CHART_VALUE_MISMATCH"}
LAYERS = ["background", "annotations", "entities", "flows", "chart", "legend"]


def load(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def copy(source: Path, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source, destination)


def change_records() -> list[dict[str, Any]]:
    return [
        {"target":"reactor-label","before":"VESSEL","after":"REACTOR","truth_ids":["entity.reactor.label"],"reason":"Source-backed synthetic label correction"},
        {"target":"flow-1","before":{"d":"M290 205 L235 205","data-from":"pump","data-to":"feed"},"after":{"d":"M230 205 L285 205","data-from":"feed","data-to":"pump"},"truth_ids":["edge.feed_pump.from","edge.feed_pump.to"],"reason":"Source-backed synthetic direction correction; arrowhead remains at the destination"},
        {"target":"bar-run-b","before":{"data-value":3.0,"height":135,"y":265},"after":{"data-value":4.0,"height":180,"y":220},"truth_ids":["chart.run_b.value"],"reason":"Actual synthetic CSV row 3 correction at 45 pixels per unit"},
        {"target":"bar-b-value","before":{"text":"3.0","y":253},"after":{"text":"4.0","y":208},"truth_ids":["chart.run_b.value"],"reason":"Keep visible synthetic value annotation synchronized with corrected bar"}
    ]


def result_skeleton(case: dict[str, Any]) -> dict[str, Any]:
    contract = case["output_contract"]
    result: dict[str, Any] = {"case_id":case["case_id"], "synthetic":True}
    for key in contract:
        result[key] = None
    result.update({
        "status":"partial",
        "sources":[
            {"path":"sources/method.md","locator":"lines 3-7","used_for":"Synthetic labels, flow direction, order, legend and preservation"},
            {"path":"sources/measurements.csv","locator":"rows 2-3","used_for":"Actual invented chart values and SYN-U units"}
        ],
        "uncertainties":[{"code":"EARLY_CHECKPOINT","status":"partial","impact":"QC and correction are not yet complete."}],
        "change_records":[]
    })
    return result


def assign_contract(result: dict[str, Any]) -> None:
    result.update({
        "editable_svg":"figure.svg",
        "preview_png":"figure.png",
        "truth_table":"truth_table.json",
        "semantic_checklist":"semantic_checklist.json",
        "expected_matrix":"expected_matrix.json",
        "rendered_observations":"rendered_observations.json",
        "visual_review":"visual_review.json",
        "visual_diff":"visual_diff.json",
        "source_edit_diff":"source_edit_diff.json",
        "export_audit":"export_audit.json",
        "contract_audit":"contract_audit.json",
        "qc_report":"qc_report.json"
    })


def run(example_dir: Path, output_dir: Path, preview_png: Path | None = None) -> tuple[int, dict[str, Any]]:
    if not example_dir.is_dir():
        raise FileNotFoundError(f"Example directory not found: {example_dir}")
    case = load(example_dir / "case.json")
    if case.get("synthetic") is not True:
        raise ValueError("run_example.py accepts only an explicitly synthetic example")
    output_dir.mkdir(parents=True, exist_ok=True)
    for name in ("task.md", "case.json", "truth_table.json", "semantic_checklist.json",
                 "expected_matrix.json", "edit_intent.json"):
        copy(example_dir / name, output_dir / name)
    for name in ("method.md", "measurements.csv"):
        copy(example_dir / "sources" / name, output_dir / "sources" / name)

    # A fresh deterministic partial checkpoint is always written before drawing.
    result = result_skeleton(case)
    result_path = output_dir / "result.json"
    dump_json(result_path, result)
    checklist = load(example_dir / "semantic_checklist.json")
    truth = load(example_dir / "truth_table.json")
    matrix = load(example_dir / "expected_matrix.json")
    intent = load(example_dir / "edit_intent.json")
    review_before = load(example_dir / "visual_review.before.json")
    review_after = load(example_dir / "visual_review.after.json")
    dump_json(output_dir / "visual_review.before.json", review_before)
    dump_json(output_dir / "visual_review.json", review_after)

    before_svg = output_dir / "before.svg"
    after_svg = output_dir / "figure.svg"
    before_svg.write_text(fixture_svg(False), encoding="utf-8")
    after_svg.write_text(fixture_svg(True), encoding="utf-8")
    render_svg_png(before_svg, output_dir / "before.png")
    render_svg_png(after_svg, output_dir / "figure.png")
    if preview_png:
        preview_png.parent.mkdir(parents=True, exist_ok=True)
        if preview_png.resolve() != (output_dir / "figure.png").resolve():
            copy(output_dir / "figure.png", preview_png)

    csv_path = output_dir / "sources" / "measurements.csv"
    observations_before = build_observations(before_svg, [csv_path])
    observations_after = build_observations(after_svg, [csv_path])
    dump_json(output_dir / "rendered_observations.before.json", observations_before)
    dump_json(output_dir / "rendered_observations.json", observations_after)
    export_before = build_export_report(before_svg, output_dir / "before.png", None, LAYERS)
    export_after = build_export_report(after_svg, output_dir / "figure.png", None, LAYERS)
    dump_json(output_dir / "export_audit.before.json", export_before)
    dump_json(output_dir / "export_audit.json", export_after)
    edit_diff = build_edit_diff(before_svg, after_svg, intent)
    dump_json(output_dir / "source_edit_diff.json", edit_diff)
    visual_diff = build_visual_diff(output_dir / "before.png", output_dir / "figure.png",
                                    output_dir / "visual_diff.png",
                                    output_dir / "visual_review.before.json", output_dir / "visual_review.json")
    dump_json(output_dir / "visual_diff.json", visual_diff)

    assign_contract(result)
    result["change_records"] = change_records()
    dump_json(result_path, result)
    contract_report = audit_contract(case, result, output_dir)
    dump_json(output_dir / "contract_audit.json", contract_report)

    # Preserve the failed initial evaluation; do not relabel pixel change as improvement.
    qc_before = build_qc_report(checklist, truth, matrix, observations_before, review_before,
                                visual_diff, export_before, contract_report, edit_diff)
    dump_json(output_dir / "qc_report.round1.json", qc_before)
    qc_after = build_qc_report(checklist, truth, matrix, observations_after, review_after,
                               visual_diff, export_after, contract_report, edit_diff)
    dump_json(output_dir / "qc_report.json", qc_after)

    initial_codes = {item.get("code") for item in qc_before.get("residual_errors", [])}
    negative_detected = REQUIRED_NEGATIVE_CODES.issubset(initial_codes)
    result["status"] = "success" if qc_after.get("status") == "pass" and negative_detected else "partial"
    result["uncertainties"] = [] if result["status"] == "success" else qc_after.get("residual_errors", [])
    if not negative_detected:
        result["uncertainties"].append({"code":"NEGATIVE_FIXTURE_NOT_DETECTED","status":"residual_error","impact":"The deliberate negative test did not expose all required mismatches."})
    dump_json(result_path, result)
    contract_report = audit_contract(case, result, output_dir)
    dump_json(output_dir / "contract_audit.json", contract_report)
    # Contract contents changed, so reconcile the final gate again with the final audit.
    qc_after = build_qc_report(checklist, truth, matrix, observations_after, review_after,
                               visual_diff, export_after, contract_report, edit_diff)
    dump_json(output_dir / "qc_report.json", qc_after)
    if qc_after.get("status") != "pass" and result["status"] == "success":
        result["status"] = "partial"
        result["uncertainties"] = qc_after.get("residual_errors", [])
        dump_json(result_path, result)
        contract_report = audit_contract(case, result, output_dir)
        dump_json(output_dir / "contract_audit.json", contract_report)
        qc_after = build_qc_report(checklist, truth, matrix, observations_after, review_after,
                                   visual_diff, export_after, contract_report, edit_diff)
        dump_json(output_dir / "qc_report.json", qc_after)

    summary = {
        "schema":"dual-artifact-quality-gate/synthetic-run-v1",
        "synthetic":True,
        "case_id":case["case_id"],
        "initial_status":qc_before.get("status"),
        "initial_defect_codes":sorted(code for code in initial_codes if code in REQUIRED_NEGATIVE_CODES),
        "final_status":qc_after.get("status"),
        "result_status":result["status"],
        "final_residual_errors":qc_after.get("residual_errors", []),
        "changed_source_ids":edit_diff.get("changed_id_set", []),
        "unchanged_required_ids":edit_diff.get("unchanged_required_ids", []),
        "visual_differing_pixels":visual_diff.get("differing_pixels"),
        "claim_boundary":"Actual synthetic source/visual comparison plus structural consistency; not proof of scientific correctness."
    }
    dump_json(output_dir / "example_summary.json", summary)
    return (0 if result["status"] == "success" and qc_after.get("status") == "pass" else 2), summary


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--example-dir", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--preview-png", type=Path)
    args = parser.parse_args(argv)
    try:
        code, summary = run(args.example_dir, args.output_dir, args.preview_png)
    except (OSError, ValueError, KeyError, TypeError) as exc:
        args.output_dir.mkdir(parents=True, exist_ok=True)
        failure = {"synthetic":True,"status":"failed","error":str(exc),"final_residual_errors":[{"code":"EXAMPLE_RUN_FAILED","message":str(exc),"status":"residual_error"}]}
        dump_json(args.output_dir / "example_summary.json", failure)
        # A best-effort failed result is useful even when inputs were malformed.
        if (args.example_dir / "case.json").is_file():
            try:
                case = load(args.example_dir / "case.json")
                result = result_skeleton(case)
                assign_contract(result)
                result["status"] = "failed"
                result["uncertainties"] = failure["final_residual_errors"]
                dump_json(args.output_dir / "result.json", result)
            except (OSError, ValueError, KeyError):
                pass
        print(json.dumps(failure, ensure_ascii=False, sort_keys=True))
        return 2
    print(json.dumps(summary, ensure_ascii=False, sort_keys=True))
    return code


if __name__ == "__main__":
    sys.exit(main())
