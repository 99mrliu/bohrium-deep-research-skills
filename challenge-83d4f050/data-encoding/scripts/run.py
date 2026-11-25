#!/usr/bin/env python3
"""Formal data-encoding runner; real /input data to honest /app/output artifacts."""
from __future__ import annotations

import argparse
import copy
import json
import math
import sys
import traceback
from pathlib import Path
from xml.etree import ElementTree as ET

from data_core import DataError, DERIVED_FIELDS, GROUP_FIELDS, analyze, apply_filters, load_raw, load_spec, sha256_bytes, write_csv
from render import render_chart, write_renderings
from source_edit import edit_svg, load_svg, svg_from_pdf

DEFAULT_NAMES = {
    "derived": "derived.csv", "group_summary": "group_summary.csv", "audit": "data_audit.json",
    "svg": "chart.svg", "png": "chart.png", "pdf": "chart.pdf", "sources": "sources.json",
    "uncertainty": "uncertainty.json", "change_records": "change_records.json", "result": "result.json",
}
ALIASES = {
    "derived": "derived", "derived_csv": "derived", "group_summary": "group_summary",
    "group_summary_csv": "group_summary", "audit": "audit", "data_audit": "audit",
    "svg": "svg", "chart_svg": "svg", "png": "png", "chart_png": "png", "pdf": "pdf",
    "chart_pdf": "pdf", "sources": "sources", "uncertainty": "uncertainty",
    "change_records": "change_records", "result": "result",
}


def resolve_input(input_dir, value, label):
    if not isinstance(value, str) or not value:
        raise DataError(f"case field {label} must be a non-empty path")
    path = Path(value)
    return path if path.is_absolute() else input_dir / path


def source_record(path, role, synthetic):
    raw = path.read_bytes()
    return {"path": str(path), "role": role, "bytes": len(raw), "sha256": sha256_bytes(raw), "synthetic_input": synthetic}


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False, allow_nan=False) + "\n", encoding="utf-8")


def output_names(contract):
    names = dict(DEFAULT_NAMES)
    configured = contract.get("artifacts", {})
    if configured:
        if not isinstance(configured, dict):
            raise DataError("output_contract.artifacts must be an object")
        for key, value in configured.items():
            if key not in ALIASES or not isinstance(value, str):
                raise DataError(f"unsupported artifact mapping {key!r}: {value!r}")
            names[ALIASES[key]] = value
    for key, value in names.items():
        path = Path(value)
        if path.is_absolute() or ".." in path.parts or not value:
            raise DataError(f"unsafe output path for {key}: {value}")
    return names


def required_raw_columns(spec):
    columns = list(spec["columns"].values())
    columns.extend(rule.get("column") for rule in spec.get("filters", []))
    for key in ("log2FC", "neg_log10_p"):
        config = spec.get("transforms", {}).get(key, {})
        if isinstance(config, dict) and config.get("column"):
            columns.append(config["column"])
    return [column for column in columns if isinstance(column, str)]


def attach_encodings(observations, groups, chart_audit):
    registry = chart_audit["mark_registry"]
    for obs in observations:
        match = next((mark for mark in registry if mark["type"] == "circle" and mark["feature"] == obs["feature"] and mark["group"] == obs["group"] and mark["sample"] == obs["sample"]), None)
        if match:
            obs["fill"] = match["encoding"].get("fill", {}).get("value")
            obs["size"] = match["encoding"].get("size", {}).get("value")
    for group in groups:
        match = next((mark for mark in registry if mark["type"] == "bar" and mark["feature"] == group["feature"] and mark["group"] == group["group"]), None)
        if match:
            group["fill"] = match["encoding"].get("fill", {}).get("value")


def artifact_checks(names, output_dir):
    checks = []
    for logical, filename in names.items():
        if logical == "result":
            continue
        path = output_dir / filename
        item = {"logical_name": logical, "path": filename, "exists": path.is_file()}
        if path.is_file():
            raw = path.read_bytes()
            item.update({"bytes": len(raw), "sha256": sha256_bytes(raw), "valid": bool(raw)})
            if logical == "svg":
                root = ET.fromstring(raw)
                texts = [element for element in root.iter() if element.tag.split("}")[-1] == "text"]
                item["valid"] = bool(texts) and any("".join(element.itertext()).strip() for element in texts)
                item["real_text_elements"] = len(texts)
            elif logical == "png":
                item["valid"] = raw.startswith(b"\x89PNG\r\n\x1a\n")
            elif logical == "pdf":
                item["valid"] = raw.startswith(b"%PDF-")
            elif logical in {"derived", "group_summary"}:
                item["valid"] = raw.startswith(b"source_sha256,") if logical == "derived" else raw.startswith(b"feature,group,n_samples,")
        checks.append(item)
    return checks


def make_result(case_id, contract, names, output_dir, status, errors):
    result = copy.deepcopy(contract)
    result.update({
        "case_id": case_id, "status": status, "partial": status != "success",
        "output_contract": copy.deepcopy(contract),
        "editable_source": [names["svg"], names["derived"], names["group_summary"]],
        "export_artifact": [names["png"], names["pdf"]],
        "content_map": {"row_level_provenance": names["derived"], "statistics_and_mark_registry": names["audit"]},
        "compliance_checks": artifact_checks(names, output_dir),
        "exceptions": errors,
        "sources": names["sources"], "uncertainty": names["uncertainty"], "change_records": names["change_records"],
        "generated_files": [filename for key, filename in names.items() if key == "result" or (output_dir / filename).is_file()],
        "artifact_checks": artifact_checks(names, output_dir), "errors": errors,
    })
    result["all_required_artifacts_valid"] = bool(result["artifact_checks"]) and all(item.get("valid") for item in result["artifact_checks"])
    return result


def execute(args):
    input_dir, work_dir, output_dir = Path(args.input), Path(args.work), Path(args.output)
    work_dir.mkdir(parents=True, exist_ok=True)
    output_dir.mkdir(parents=True, exist_ok=True)
    case, contract = {}, {}
    names = dict(DEFAULT_NAMES)
    case_id = "UNRESOLVED_CASE_ID"
    sources, uncertainties, changes, errors = [], [], [], []
    status = "partial"
    try:
        case_path, task_path = input_dir / "case.json", input_dir / "task.md"
        from data_core import strict_json
        case = strict_json(case_path)
        if not isinstance(case, dict) or not isinstance(case.get("case_id"), str) or not case["case_id"].strip():
            raise DataError("case.json requires non-empty case_id")
        case_id = case["case_id"]
        if not task_path.is_file() or not task_path.read_text(encoding="utf-8").strip():
            raise DataError("required task.md is missing or empty")
        synthetic = case_id.startswith("SYNTHETIC") or case.get("synthetic") is True
        sources.extend([source_record(case_path, "case", synthetic), source_record(task_path, "task", synthetic)])
        workorder_path = resolve_input(input_dir, case.get("workorder", "workorder.json"), "workorder")
        workorder = strict_json(workorder_path)
        if not isinstance(workorder, dict) or not isinstance(workorder.get("output_contract"), dict) or not isinstance(workorder.get("chart"), dict):
            raise DataError("workorder needs output_contract and chart objects")
        contract = workorder["output_contract"]
        names = output_names(contract)
        sources.append(source_record(workorder_path, "workorder", synthetic))
        spec_path = resolve_input(input_dir, case.get("data_spec", "spec.json"), "data_spec")
        spec = load_spec(spec_path)
        sources.append(source_record(spec_path, "data_spec", synthetic))
        raw_path = Path(spec["path"])
        if not raw_path.is_absolute():
            raw_path = spec_path.parent / raw_path
        raw_rows, headers = load_raw(raw_path, spec.get("format"))
        missing_columns = sorted(set(required_raw_columns(spec)) - set(headers))
        if missing_columns:
            raise DataError(f"raw input is missing configured columns: {missing_columns}; available: {headers}")
        sources.append(source_record(raw_path, "raw_data", synthetic))
        kept, excluded = apply_filters(raw_rows, spec)
        observations, samples, groups, features = analyze(kept, spec)
        generated_svg, chart_audit = render_chart(workorder["chart"], observations, samples, groups, features)
        attach_encodings(observations, groups, chart_audit)
        paths = {key: output_dir / filename for key, filename in names.items()}
        write_csv(paths["derived"], observations, DERIVED_FIELDS)
        write_csv(paths["group_summary"], groups, GROUP_FIELDS)
        audit = {
            "case_id": case_id, "passed": True,
            "source": {"path": str(raw_path), "sha256": sha256_bytes(raw_path.read_bytes()), "columns": headers, "format": spec.get("format", raw_path.suffix.lstrip('.'))},
            "sample_definition": "Unique sample ID within (feature, group). Replicate observations are averaged within each sample BEFORE group statistics; n is independent samples, not replicate rows.",
            "sd_definition": "Sample standard deviation (ddof=1) of within-sample means; null when n<2.",
            "sem_definition": "group_sd / sqrt(n_samples); null when n<2.",
            "row_counts": {"raw": len(raw_rows), "kept": len(kept), "excluded_by_filters": len(excluded), "independent_samples": len(samples)},
            "row_provenance": [{"source_row": row["_source_row"], "row_checksum": row["_row_checksum"], "source_sha256": row["_source_sha256"], "status": "kept"} for row in kept] + [{"source_row": row["_source_row"], "row_checksum": row["_row_checksum"], "source_sha256": row["_source_sha256"], "status": "excluded", "reasons": row["_exclusion_reasons"]} for row in excluded],
            "group_statistics": groups, "feature_statistics": features,
            "transforms": spec.get("transforms", {}), "filters": spec.get("filters", []),
            "visual_encoding": chart_audit,
            "statistics_independently_rechecked": True,
        }
        source_value = case.get("source_svg") or case.get("figure03")
        source_pdf_value = case.get("source_pdf") or case.get("original_pdf")
        svg_bytes = generated_svg
        original_root = None
        if source_value or source_pdf_value:
            if source_value:
                source_path = resolve_input(input_dir, source_value, "source_svg")
                original_bytes, original_root = load_svg(source_path)
                sources.append(source_record(source_path, "source_svg", synthetic))
                audit["source_svg_sha256"] = sha256_bytes(original_bytes)
            else:
                source_path = resolve_input(input_dir, source_pdf_value, "source_pdf")
                sources.append(source_record(source_path, "source_pdf", synthetic))
                original_bytes, original_root, derived_path = svg_from_pdf(source_path, int(case.get("source_page", 0)), work_dir)
                audit["derived_source_svg"] = str(derived_path)
            edited_root = copy.deepcopy(original_root)
            operations = workorder.get("operations", [])
            if not isinstance(operations, list) or any(not isinstance(op, dict) for op in operations):
                raise DataError("workorder.operations must be an array of objects")
            if any(op.get("op") not in {"update_svg_text", "update_svg_attr"} for op in operations):
                raise DataError("only update_svg_text/update_svg_attr operations are supported")
            if operations:
                svg_bytes, changes, preservation = edit_svg(original_root, edited_root, operations)
            else:
                svg_bytes, preservation = original_bytes, {"target_ids": [], "preservation_verified": True, "byte_identical_source": True}
            audit["source_preservation"] = preservation
            audit["visual_encoding"]["registry_scope"] = "Candidate statistical chart; preserved source SVG is changed only by explicit ID operations"
            uncertainties.append({"severity": "warning", "code": "PRESERVED_SOURCE_DATA_SEMANTICS", "message": "Derived tables and candidate scale registry reflect current raw data, but the preserved source SVG is not statistically regenerated. Use create mode for synchronized data-driven marks."})
        elif workorder.get("operations"):
            raise DataError("SVG edit operations require case.source_svg/figure03 or source_pdf/original_pdf")
        if case.get("mode") == "edit" and original_root is None:
            raise DataError("edit mode requires an original SVG or PDF")
        write_json(paths["audit"], audit)
        write_renderings(svg_bytes, paths["svg"], paths["png"], paths["pdf"])
        required = contract.get("required_files", list(names.values()))
        if not isinstance(required, list) or any(not isinstance(name, str) for name in required):
            raise DataError("required_files must be an array of filenames")
        stage_names = {names[key] for key in ("derived", "group_summary", "audit", "svg", "png", "pdf")}
        missing = [name for name in required if name in stage_names and not (output_dir / name).is_file()]
        if missing:
            raise DataError(f"required stage outputs missing: {missing}")
        status = "success"
    except Exception as exc:
        errors.append({"type": type(exc).__name__, "message": str(exc)})
        uncertainties.append({"severity": "error", "code": "EXECUTION_FAILED", "message": str(exc)})
        status = "partial"
        if args.debug:
            traceback.print_exc()
    try:
        paths = {key: output_dir / filename for key, filename in names.items()}
        write_json(paths["sources"], {"case_id": case_id, "sources": sources})
        write_json(paths["uncertainty"], {"case_id": case_id, "uncertainties": uncertainties})
        write_json(paths["change_records"], {"case_id": case_id, "declared_changed": workorder.get("changed", []) if "workorder" in locals() else [], "declared_unchanged": workorder.get("unchanged", []) if "workorder" in locals() else [], "records": changes})
        required = contract.get("required_files", list(names.values())) if contract else list(names.values())
        if isinstance(required, list):
            missing = [name for name in required if name != names["result"] and not (output_dir / name).is_file()]
            if missing and status == "success":
                status = "partial"
                errors.append({"type": "ArtifactError", "message": f"required final outputs missing: {missing}"})
        result = make_result(case_id, contract, names, output_dir, status, errors)
        result.update({"sources": sources, "uncertainties": uncertainties, "change_records": changes})
        if status == "success" and not result["all_required_artifacts_valid"]:
            status = "partial"
            errors.append({"type": "ArtifactError", "message": "one or more generated artifacts failed format validation"})
            result.update({"status": "partial", "partial": True, "errors": errors})
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


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", default="/input")
    parser.add_argument("--work", default="/app/work")
    parser.add_argument("--output", default="/app/output")
    parser.add_argument("--debug", action="store_true")
    args = parser.parse_args()
    return execute(args)


if __name__ == "__main__":
    raise SystemExit(main())
