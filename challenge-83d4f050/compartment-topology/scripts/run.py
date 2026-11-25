#!/usr/bin/env python3
"""Formal runner: /input + /app/work -> /app/output, with honest partial results."""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import os
import re
import sys
import traceback
from pathlib import Path
from xml.etree import ElementTree as ET

from topology import TopologyError, compute_layout, load_topology, render_svg, sha256_bytes, write_renderings
from svg_source import apply_svg_operation, finalize_source_svg, load_source_svg, source_from_pdf

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

DEFAULT_FILES = [
    "layout.json", "figure.svg", "figure.png", "figure.pdf", "topology_audit.json",
    "sources.json", "uncertainty.json", "change_records.json", "result.json",
]
ALIASES = {
    "layout": "layout", "layout_json": "layout", "svg": "svg", "figure_svg": "svg",
    "png": "png", "figure_png": "png", "pdf": "pdf", "figure_pdf": "pdf",
    "audit": "audit", "topology_audit": "audit", "sources": "sources",
    "uncertainty": "uncertainty", "change_records": "change_records", "result": "result",
}
DEFAULT_NAMES = {
    "layout": "layout.json", "svg": "figure.svg", "png": "figure.png", "pdf": "figure.pdf",
    "audit": "topology_audit.json", "sources": "sources.json", "uncertainty": "uncertainty.json",
    "change_records": "change_records.json", "result": "result.json",
}


def read_json(path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise TopologyError(f"required JSON input {path} cannot be read: {exc}") from exc


def resolve_input(input_dir, value, label):
    if not isinstance(value, str) or not value:
        raise TopologyError(f"case.json field {label} must be a non-empty path")
    path = Path(value)
    return path if path.is_absolute() else input_dir / path


def source_record(path, role, synthetic):
    content = path.read_bytes()
    return {"path": str(path), "role": role, "bytes": len(content), "sha256": sha256_bytes(content), "synthetic_input": synthetic}


def output_names(contract):
    names = dict(DEFAULT_NAMES)
    configured = contract.get("artifacts", {})
    if configured:
        if not isinstance(configured, dict):
            raise TopologyError("output_contract.artifacts must be an object of logical-name/path pairs")
        for logical, filename in configured.items():
            if logical not in ALIASES or not isinstance(filename, str):
                raise TopologyError(f"unsupported artifact mapping {logical!r}: {filename!r}")
            names[ALIASES[logical]] = filename
    for logical, filename in names.items():
        candidate = Path(filename)
        if candidate.is_absolute() or ".." in candidate.parts or not filename:
            raise TopologyError(f"unsafe output path for {logical}: {filename}")
    return names


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False, allow_nan=False) + "\n", encoding="utf-8")


def set_nested(data, path, value):
    parts = path.split(".")
    if not parts or parts[0] != "constraints" or any(not part for part in parts):
        raise TopologyError("set_constraint.path must start with 'constraints.'")
    target = data
    for part in parts[:-1]:
        if part not in target or not isinstance(target[part], dict):
            raise TopologyError(f"constraint parent path does not exist: {part}")
        target = target[part]
    if parts[-1] not in target:
        raise TopologyError(f"set_constraint requires an existing constraint: {path}")
    target[parts[-1]] = value


def apply_topology_operation(topology, operation):
    op = operation.get("op")
    target_id = operation.get("id")
    entities = {e["id"]: e for e in topology["entities"]}
    edges = {e["id"]: e for e in topology["edges"]}
    if op in {"set_entity_compartment", "update_label", "set_entity_kind"}:
        if target_id not in entities:
            raise TopologyError(f"{op}: unknown entity id {target_id!r}")
        entity = entities[target_id]
        field = {"set_entity_compartment": "compartment", "update_label": "label", "set_entity_kind": "kind"}[op]
        value = operation.get(field)
        if not isinstance(value, str) or not value:
            raise TopologyError(f"{op}.{field} must be a non-empty string")
        before = entity.get(field)
        entity[field] = value
        return {"target_id": target_id, "field": field, "before": before, "after": value}
    if op == "set_edge_kind":
        if target_id not in edges:
            raise TopologyError(f"set_edge_kind: unknown edge id {target_id!r}")
        value = operation.get("kind")
        if not isinstance(value, str) or not value:
            raise TopologyError("set_edge_kind.kind must be a non-empty string")
        before = edges[target_id].get("kind")
        edges[target_id]["kind"] = value
        return {"target_id": target_id, "field": "kind", "before": before, "after": value}
    if op == "set_feedback":
        if target_id not in edges or not isinstance(operation.get("feedback"), bool):
            raise TopologyError("set_feedback needs a known edge id and boolean feedback")
        current = list(topology["constraints"].get("feedback_edges", []))
        before = target_id in current
        current = sorted((set(current) | {target_id}) if operation["feedback"] else (set(current) - {target_id}))
        topology["constraints"]["feedback_edges"] = current
        return {"target_id": target_id, "field": "feedback", "before": before, "after": operation["feedback"]}
    if op == "set_constraint":
        path = operation.get("path")
        if not isinstance(path, str) or "value" not in operation:
            raise TopologyError("set_constraint needs path and value")
        # NaN/Infinity are not legal JSON and are therefore not accepted here.
        before = copy.deepcopy(topology)
        set_nested(topology, path, operation["value"])
        after = copy.deepcopy(topology)
        if before == after:
            raise TopologyError(f"set_constraint {path} made no change")
        return {"target_id": target_id, "field": path, "before": "see workorder/source checksum", "after": operation["value"]}
    raise TopologyError(f"unsupported topology operation {op!r}")


def verify_regular_outputs(paths):
    checks = []
    for logical, path in paths.items():
        if logical == "result":
            continue
        item = {"logical_name": logical, "path": path.name, "exists": path.is_file()}
        if item["exists"]:
            raw = path.read_bytes()
            item.update({"bytes": len(raw), "sha256": sha256_bytes(raw), "valid": len(raw) > 0})
            if logical == "svg":
                root = ET.fromstring(raw)
                texts = [e for e in root.iter() if e.tag.split("}")[-1] == "text"]
                item["valid"] = len(texts) > 0 and any("".join(e.itertext()).strip() for e in texts)
                item["real_text_elements"] = len(texts)
            elif logical == "png":
                item["valid"] = raw.startswith(b"\x89PNG\r\n\x1a\n")
            elif logical == "pdf":
                item["valid"] = raw.startswith(b"%PDF-")
        checks.append(item)
    return checks


def build_result(case_id, contract, names, output_dir, status, errors):
    # Every caller-defined output_contract field is retained at top level and in full below.
    result = copy.deepcopy(contract)
    result.update({
        "case_id": case_id, "status": status, "partial": status != "success",
        "output_contract": copy.deepcopy(contract),
        "editable_source": [names["layout"], names["svg"]],
        "export_artifact": [names["png"], names["pdf"]],
        "content_map": {"topology_model": names["layout"], "element_topology_audit": names["audit"]},
        "compliance_checks": verify_regular_outputs({key: output_dir / filename for key, filename in names.items()}),
        "exceptions": errors,
        "sources": names["sources"], "uncertainty": names["uncertainty"], "change_records": names["change_records"],
        "generated_files": [filename for key, filename in names.items() if key == "result" or (output_dir / filename).is_file()],
        "artifact_checks": verify_regular_outputs({key: output_dir / filename for key, filename in names.items()}),
        "errors": errors,
    })
    result["all_required_artifacts_valid"] = bool(result["artifact_checks"]) and all(item.get("valid") for item in result["artifact_checks"])
    return result


def execute(args):
    input_dir, work_dir, output_dir = Path(args.input), Path(args.work), Path(args.output)
    work_dir.mkdir(parents=True, exist_ok=True)
    output_dir.mkdir(parents=True, exist_ok=True)
    case = {}
    contract = {}
    names = dict(DEFAULT_NAMES)
    case_id = "UNRESOLVED_CASE_ID"
    sources = []
    uncertainties = []
    changes = []
    errors = []
    status = "partial"
    try:
        case_path = input_dir / "case.json"
        task_path = input_dir / "task.md"
        case = read_json(case_path)
        if not isinstance(case, dict) or not isinstance(case.get("case_id"), str) or not case["case_id"].strip():
            raise TopologyError("case.json must contain non-empty case_id")
        case_id = case["case_id"]
        if not task_path.is_file() or not task_path.read_text(encoding="utf-8").strip():
            raise TopologyError(f"required task input {task_path} is missing or empty")
        synthetic = case_id.startswith("SYNTHETIC") or case.get("synthetic") is True
        sources.extend([source_record(case_path, "case", synthetic), source_record(task_path, "task", synthetic)])
        workorder_path = resolve_input(input_dir, case.get("workorder", "workorder.json"), "workorder")
        workorder = read_json(workorder_path)
        if not isinstance(workorder, dict) or not isinstance(workorder.get("output_contract"), dict):
            raise TopologyError("workorder.json and its output_contract object are required")
        contract = workorder["output_contract"]
        names = output_names(contract)
        sources.append(source_record(workorder_path, "workorder", synthetic))
        topology_path = resolve_input(input_dir, case.get("topology", "topology.json"), "topology")
        raw_topology = topology_path.read_bytes()
        topology = load_topology(topology_path)
        sources.append(source_record(topology_path, "topology", synthetic))
        operations = workorder.get("operations", [])
        if not isinstance(operations, list):
            raise TopologyError("workorder.operations must be an array")
        for index, operation in enumerate(operations):
            if not isinstance(operation, dict) or not isinstance(operation.get("op"), str):
                raise TopologyError(f"operation {index} is not an object with op")
            op = operation["op"]
            record = {"operation_index": index, "op": op, "changed": False}
            if op in {"update_svg_text", "update_svg_attr"}:
                continue
            details = apply_topology_operation(topology, operation)
            record.update(details)
            record["changed"] = details["before"] != details["after"]
            record["unchanged"] = "All entities, edges and constraints not named by this operation"
            changes.append(record)
        layout, audit = compute_layout(topology)
        layout["case_id"] = case_id
        layout["topology_source_sha256"] = sha256_bytes(raw_topology)
        source_svg_value = case.get("source_svg") or case.get("figure03")
        source_pdf_value = case.get("source_pdf") or case.get("original_pdf")
        original_root = None
        edited_root = None
        source_preservation = None
        if source_svg_value or source_pdf_value:
            if source_svg_value:
                source_path = resolve_input(input_dir, source_svg_value, "source_svg")
                original_bytes, original_root = load_source_svg(source_path)
                sources.append(source_record(source_path, "source_svg", synthetic))
                audit["source_svg_sha256"] = sha256_bytes(original_bytes)
            else:
                source_path = resolve_input(input_dir, source_pdf_value, "source_pdf")
                sources.append(source_record(source_path, "source_pdf", synthetic))
                page = int(case.get("source_page", 0))
                original_bytes, original_root, derived = source_from_pdf(source_path, page, work_dir)
                audit["source_pdf_page"] = page
                audit["derived_source_svg"] = str(derived)
            edited_root = copy.deepcopy(original_root)
        if case.get("mode") == "edit" and original_root is None:
            raise TopologyError("edit mode requires case.source_svg/figure03 or case.source_pdf/original_pdf")
        svg_targets = []
        if original_root is not None:
            for index, operation in enumerate(operations):
                if operation.get("op") not in {"update_svg_text", "update_svg_attr"}:
                    continue
                details = apply_svg_operation(edited_root, operation, _index_for_operation(edited_root))
                changes.append({"operation_index": index, "op": operation["op"], **details, "changed": details["before"] != details["after"], "unchanged": "Every SVG subtree except the target and its ancestors"})
                svg_targets.append(operation["id"])
            if svg_targets:
                svg_bytes, source_preservation = finalize_source_svg(original_root, edited_root, svg_targets)
            else:
                # Preserve source bytes exactly when no SVG operation was requested.
                svg_bytes = original_bytes
                source_preservation = {"target_ids": [], "preservation_verified": True, "byte_identical_source": True}
            audit["source_preservation"] = source_preservation
            if any(c["op"] not in {"update_svg_text", "update_svg_attr"} for c in changes):
                uncertainties.append({"severity": "warning", "code": "PRESERVED_GEOMETRY", "message": "Topology/layout changes are recorded in layout.json; preserved source SVG geometry is changed only by explicit update_svg_attr operations."})
        else:
            svg_bytes = render_svg(topology, layout)
        paths = {key: output_dir / filename for key, filename in names.items()}
        write_json(paths["layout"], layout)
        write_json(paths["audit"], audit)
        write_renderings(svg_bytes, paths["svg"], paths["png"], paths["pdf"])
        required = contract.get("required_files", list(names.values()))
        if not isinstance(required, list) or any(not isinstance(name, str) for name in required):
            raise TopologyError("output_contract.required_files must be an array of filenames")
        # Provenance/result records are finalized below, after this rendering stage.
        rendered_names = {names[key] for key in ("layout", "svg", "png", "pdf", "audit")}
        missing = [name for name in required if name in rendered_names and not (output_dir / name).is_file()]
        if missing:
            raise TopologyError(f"required rendered outputs are missing: {missing}")
        status = "success"
    except Exception as exc:
        errors.append({"type": type(exc).__name__, "message": str(exc)})
        uncertainties.append({"severity": "error", "code": "EXECUTION_FAILED", "message": str(exc)})
        status = "partial"
        if args.debug:
            traceback.print_exc()
    # These records are attempted even on validation/render failure; no success claim is fabricated.
    try:
        paths = {key: output_dir / filename for key, filename in names.items()}
        source_doc = {"case_id": case_id, "sources": sources}
        uncertainty_doc = {"case_id": case_id, "uncertainties": uncertainties}
        change_doc = {
            "case_id": case_id,
            "declared_changed": workorder.get("changed", []) if "workorder" in locals() else [],
            "declared_unchanged": workorder.get("unchanged", []) if "workorder" in locals() else [],
            "records": changes,
        }
        write_json(paths["sources"], source_doc)
        write_json(paths["uncertainty"], uncertainty_doc)
        write_json(paths["change_records"], change_doc)
        required = contract.get("required_files", list(names.values())) if contract else list(names.values())
        if isinstance(required, list):
            missing = [name for name in required if name != names["result"] and not (output_dir / name).is_file()]
            if missing and status == "success":
                status = "partial"
                errors.append({"type": "ArtifactError", "message": f"required final outputs missing: {missing}"})
        result = build_result(case_id, contract, names, output_dir, status, errors)
        result.update({"sources": sources, "uncertainties": uncertainties, "change_records": changes})
        if status == "success" and not result["all_required_artifacts_valid"]:
            status = "partial"
            result["status"] = "partial"
            result["partial"] = True
            errors.append({"type": "ArtifactError", "message": "one or more generated artifacts failed format validation"})
            result["errors"] = errors
        write_json(paths["result"], result)
    except Exception as exc:
        print(f"fatal: cannot write partial result: {exc}", file=sys.stderr)
        return 1
    if status != "success":
        for error in errors:
            print(f"error[{error['type']}]: {error['message']}", file=sys.stderr)
        return 2
    print(json.dumps({"case_id": case_id, "status": status, "output": str(output_dir)}, ensure_ascii=False))
    return 0


def _index_for_operation(root):
    # Kept as a function so apply_svg_operation receives a fresh index for every operation.
    return {element.get("id"): element for element in root.iter() if element.get("id")}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", default="/input", help="formal input directory containing case.json/task.md")
    parser.add_argument("--work", default="/app/work", help="scratch directory")
    parser.add_argument("--output", default="/app/output", help="final artifact directory")
    parser.add_argument("--debug", action="store_true")
    args = parser.parse_args()
    return execute(args)


if __name__ == "__main__":
    raise SystemExit(main())
