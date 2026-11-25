#!/usr/bin/env python3
"""Run evidence-limited quantity verification and produce JSON/Markdown/sweep artifacts."""
from __future__ import annotations

import argparse
import csv
import json
import sys
from copy import deepcopy
from pathlib import Path
from typing import Any

from quantity_core import VerificationError, convert, evaluate_analysis, scenario_quantity
from runtime_contract import base_result, locate_contract, normalize_contract, read_json


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(value, handle, indent=2, ensure_ascii=False, allow_nan=False)
        handle.write("\n")


def fmt(value: Any) -> str:
    if isinstance(value, float):
        return f"{value:.17g}"
    return str(value)


def sweep_artifacts(properties: list[dict[str, Any]], work_dir: Path, analysis: dict[str, Any]) -> list[str]:
    artifacts = []
    for prop in properties:
        if prop.get("kind") != "monotonic_direction_over_sweep" or prop.get("verdict") == "insufficient_evidence":
            continue
        property_id = "".join(c if c.isalnum() or c in "-_" else "_" for c in str(prop.get("property_id")))
        points = prop.get("points", [])
        csv_path = work_dir / f"{property_id}_sweep.csv"
        with csv_path.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.writer(handle)
            writer.writerow(["index", "input_value", "input_scale", "input_unit", "output", "output_unit", "canonical_output"])
            for point in points:
                raw = point["input"]
                writer.writerow([point["index"], raw.get("value"), raw.get("scale", 1.0), raw.get("unit"), point["output"], prop.get("output_unit"), point["canonical_output"]])
        artifacts.append(str(csv_path))
        if not prop.get("plot_requested"):
            continue
        png_path = work_dir / f"{property_id}_sweep.png"
        try:
            import matplotlib
            matplotlib.use("Agg")
            import matplotlib.pyplot as plt
            x = []
            first_unit = points[0]["input"].get("unit", "") if points else ""
            for point in points:
                raw = point["input"]
                x.append(convert(scenario_quantity(raw, "sweep input"), first_unit))
            y = [point["output"] for point in points]
            fig, ax = plt.subplots(figsize=(8, 4.5), dpi=140)
            ax.plot(x, y, "o-", color="#2457A6", linewidth=1.8)
            ax.set_xlabel(f"{prop.get('kind')} input [{first_unit}]")
            ax.set_ylabel(f"recomputed output [{prop.get('output_unit', '')}]")
            ax.set_title(f"Synthetic/runtime authored sweep: {property_id}")
            ax.grid(True, alpha=0.25)
            fig.tight_layout()
            fig.savefig(png_path)
            plt.close(fig)
            artifacts.append(str(png_path))
            analysis.setdefault("plot_verdicts", []).append({"property_id": property_id, "status": "written", "path": str(png_path)})
        except (ImportError, RuntimeError, OSError, ValueError) as exc:
            analysis["warnings"].append(f"Optional PNG plotting unavailable for {property_id}: {exc}; CSV/JSON/Markdown remain authoritative.")
            analysis.setdefault("plot_verdicts", []).append({"property_id": property_id, "status": "unavailable", "reason": str(exc)})
    return artifacts


def markdown_report(analysis: dict[str, Any], artifacts: list[str]) -> str:
    lines = [
        "# Metamorphic quantity verification report", "",
        f"**case_id:** `{analysis.get('case_id')}`  ",
        f"**recommended_status:** `{analysis.get('recommended_status')}`  ",
        f"**outcome:** `{analysis.get('outcome')}`", "",
        "> Numerical equality within tolerance does not validate the model, its assumptions, or the source. An invariant is independent only if it was not derived from the claimed result.", "",
        "## Intermediate sourced input values", "",
        "| name | raw value | scale | unit | unit factor to SI | canonical value | source locator |",
        "|---|---:|---:|---|---:|---:|---|",
    ]
    for item in analysis.get("intermediate_input_values", []):
        raw = item.get("raw_value") if item.get("raw_value") is not None else f"MathML {item.get('mathml')}"
        lines.append(f"| {item['name']} | {fmt(raw)} | {fmt(item['scale'])} | {item['unit']} | {fmt(item['unit_factor_to_SI'])} | {fmt(item['canonical_value'])} | {item['source_locator']} |")
    if not analysis.get("intermediate_input_values"):
        lines.append("| — | — | — | — | — | — | no sourced values resolved |")
    lines.extend(["", "## Source-claim verification (no injected faults)", ""])
    for claim in analysis.get("claims", []):
        lines.append(f"### {claim.get('claim_id')}: `{claim.get('verdict')}`")
        lines.append("")
        if claim.get("error"):
            lines.append(f"- Evidence gap: {claim['error']}")
        else:
            reported = claim["reported"]
            tol = claim["tolerance"]
            lines.extend([
                f"- Formula: `{claim['formula']}`",
                f"- Reported interval: [{fmt(reported['lower'])}, {fmt(reported['upper'])}] {reported['unit']} (source: {reported['source_locator']})",
                f"- Recomputed value: **{fmt(claim['recomputed_value'])} {reported['unit']}** (canonical {fmt(claim['recomputed_canonical_value'])})",
                f"- Residual to interval: **{fmt(claim['residual_to_reported_interval'])} {reported['unit']}**; signed residual to nearest bound: {fmt(claim['signed_residual_to_nearest_bound'])}",
                f"- Tolerance = absolute {fmt(tol['absolute'])} + relative part {fmt(tol['relative_part'])} + rounding {fmt(tol['rounding_absolute'])} = **{fmt(tol['total'])} {reported['unit']}**",
                f"- Expanded comparison interval: [{fmt(claim['expanded_reported_interval'][0])}, {fmt(claim['expanded_reported_interval'][1])}] {reported['unit']}",
            ])
        lines.append("")
    lines.extend([f"**source_claim_verdict:** `{analysis.get('source_claim_verdict')}`", "", "## Independently authored metamorphic properties", ""])
    properties = analysis.get("property_results", [])
    if not properties:
        lines.append("No properties were supplied. This run is partial, not a vacuous success.")
    for prop in properties:
        lines.extend([f"### {prop.get('property_id')}: `{prop.get('verdict')}`", "", f"- Kind: `{prop.get('kind')}`"])
        if prop.get("error"):
            lines.append(f"- Evidence gap: {prop['error']}")
        for comparison in prop.get("comparisons", []):
            lines.append(f"- Scale multiplier {comparison['multiplier']}: baseline {fmt(comparison['left'])}, transformed {fmt(comparison['right'])} {comparison['unit']}; residual {fmt(comparison['absolute_residual'])}; tolerance {fmt(comparison['tolerance']['total'])}; within={comparison['within_tolerance']}")
        for step in prop.get("steps", []):
            lines.append(f"- Sweep {step['left_index']}→{step['right_index']}: delta {fmt(step['delta'])}; tolerance {fmt(step['tolerance']['total'])}; within={step['within_tolerance']}")
        if "sequence" in prop:
            for point in prop["sequence"]:
                lines.append(f"- Limit approach {point['index']}: value {fmt(point['left'])} {point['unit']}; expected {fmt(point['right'])}; residual {fmt(point['absolute_residual'])}; tolerance {fmt(point['tolerance']['total'])}")
            lines.append(f"- {prop.get('caveat')}")
        if "comparison" in prop:
            comparison = prop["comparison"]
            lines.append(f"- Transformed relation: left {fmt(comparison['left'])}, right {fmt(comparison['right'])} {comparison['unit']}; residual {fmt(comparison['absolute_residual'])}; tolerance {fmt(comparison['tolerance']['total'])}; within={comparison['within_tolerance']}")
        lines.append("")

    lines.extend(["## Deliberate diagnostic fault injection (isolated attribution)", "", f"**diagnostic_fault_injection_verdict:** `{analysis.get('diagnostic_fault_injection_verdict', {}).get('overall')}`", ""])
    faults = analysis.get("diagnostic_fault_injection_verdict", {}).get("faults", [])
    if not faults:
        lines.append("No faults injected.")
    for fault in faults:
        lines.extend([f"### {fault.get('fault_id')}: `{fault.get('verdict')}`", ""])
        if fault.get("error"):
            lines.append(f"- Diagnostic error: {fault['error']}")
        if fault.get("mutation"):
            lines.append(f"- Mutation: `{json.dumps(fault['mutation'], ensure_ascii=False)}`")
        for detection in fault.get("detections", []):
            lines.append(f"- Detection: {json.dumps(detection, ensure_ascii=False)}")
        lines.append(f"- Attribution: {fault.get('attribution', 'diagnostic only')}")
        lines.append("")
    lines.extend(["## Evidence gaps, errors, and warnings", ""])
    gaps = analysis.get("evidence_gaps", []) + analysis.get("errors", []) + analysis.get("warnings", [])
    lines.extend([f"- {item}" for item in gaps] or ["- None recorded; this still does not validate the model."])
    lines.extend(["", "## Artifacts", ""])
    lines.extend([f"- `{path}`" for path in artifacts] or ["- No artifacts listed."])
    lines.extend(["", "## Interpretation", "", analysis.get("claim_caveat", ""), ""])
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--case", default="/input/case.json")
    parser.add_argument("--task", default="/input/task.md")
    parser.add_argument("--work-dir", default="/app/work")
    parser.add_argument("--output", default="/app/output/result.json")
    args = parser.parse_args(argv)
    case_path, task_path = Path(args.case), Path(args.task)
    work_dir, output_path = Path(args.work_dir), Path(args.output)
    work_dir.mkdir(parents=True, exist_ok=True)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    case: dict[str, Any] = {}
    contract = normalize_contract(locate_contract("", {}))
    try:
        case = read_json(case_path)
        if not isinstance(case, dict):
            raise VerificationError("case.json must be an object")
        task_text = task_path.read_text(encoding="utf-8")
        contract = normalize_contract(locate_contract(task_text, case))
        # Early durable result: honest partial, correct case id, and every declared field.
        write_json(output_path, base_result(contract, case.get("case_id"), early=True))
        analysis, properties = evaluate_analysis(case, case_path.resolve().parent)
        analysis_path, report_path = work_dir / "analysis.json", work_dir / "report.md"
        artifacts = sweep_artifacts(properties, work_dir, analysis)
        analysis["artifact_paths"] = [str(analysis_path), str(report_path)] + artifacts
        analysis["report_path"] = str(report_path)
        write_json(analysis_path, analysis)
        report_path.write_text(markdown_report(analysis, analysis["artifact_paths"]), encoding="utf-8")
        # A draft remains partial until the finalizer receives agent-authored answers.
        draft_analysis = deepcopy(analysis)
        draft_analysis["recommended_status"] = "partial"
        result = base_result(contract, case.get("case_id"), draft_analysis)
        for name, definition in contract["fields"].items():
            kind = definition.get("type") if isinstance(definition, dict) else definition
            if name == "artifacts":
                if kind in {"object", "dict"}:
                    result[name] = {Path(path).name: path for path in analysis["artifact_paths"]}
                else:
                    result[name] = analysis["artifact_paths"]
        write_json(output_path, result)
        print(json.dumps({"analysis": str(analysis_path), "report": str(report_path), "draft_result": str(output_path), "recommended_status": analysis["recommended_status"], "source_claim_verdict": analysis["source_claim_verdict"], "diagnostic_fault_injection_verdict": analysis["diagnostic_fault_injection_verdict"]["overall"]}, ensure_ascii=False))
        return 0
    except (VerificationError, OSError, UnicodeError) as exc:
        failure = {"case_id": case.get("case_id"), "recommended_status": "partial", "source_claim_verdict": "insufficient_evidence", "diagnostic_fault_injection_verdict": {"overall": "not_run", "faults": []}, "errors": [str(exc)], "evidence_gaps": ["Runtime failed before complete verification; no values were imputed."], "claims": [], "property_results": [], "intermediate_input_values": []}
        analysis_path = work_dir / "analysis.json"
        report_path = work_dir / "report.md"
        write_json(analysis_path, failure)
        report_path.write_text(markdown_report(failure, [str(analysis_path), str(report_path)]), encoding="utf-8")
        write_json(output_path, base_result(contract, case.get("case_id"), failure))
        print(f"verification incomplete: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
