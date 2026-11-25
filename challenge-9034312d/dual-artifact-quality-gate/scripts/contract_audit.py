#!/usr/bin/env python3
"""Initialize or audit the actual case's top-level result/output contract."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

STATUSES = {"success", "partial", "failed"}
PATH_SUFFIXES = {".svg", ".png", ".pdf", ".json", ".csv", ".txt", ".md", ".pptx", ".xlsx", ".cif"}


def load(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def dump(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def fields(case: dict[str, Any]) -> dict[str, dict[str, Any]]:
    contract = case.get("output_contract", {})
    result: dict[str, dict[str, Any]] = {}
    if isinstance(contract, dict) and isinstance(contract.get("fields"), (dict, list)):
        contract = contract["fields"]
    if isinstance(contract, dict):
        for key, spec in contract.items():
            if isinstance(spec, dict):
                result[key] = spec
            else:
                result[key] = {"description": str(spec), "type": "path"}
    if isinstance(contract, list):
        for item in contract:
            if isinstance(item, str):
                result[item] = {"type": "path"}
            elif isinstance(item, dict):
                key = item.get("name") or item.get("key") or item.get("field")
                if isinstance(key, str):
                    result[key] = item
    return result


def looks_like_path(value: str, spec: dict[str, Any]) -> bool:
    declared = str(spec.get("type", spec.get("kind", "path"))).lower()
    if declared in {"string", "text", "number", "integer", "boolean", "object", "array"}:
        return False
    if declared in {"path", "file", "artifact", "output"}:
        return True
    return "/" in value or Path(value).suffix.lower() in PATH_SUFFIXES


def audit(case: dict[str, Any], result: Any, output_root: Path) -> dict[str, Any]:
    errors: list[dict[str, str]] = []
    warnings: list[str] = []
    contract = fields(case)
    if not contract:
        errors.append({"code": "OUTPUT_CONTRACT_MISSING", "message": "case.json has no discoverable output_contract fields."})
    if not isinstance(result, dict):
        return {"schema": "dual-artifact-quality-gate/contract-audit-v1",
                "status": "fail", "contract_keys": sorted(contract),
                "errors": [{"code": "RESULT_NOT_OBJECT", "message": "result.json must be an object."}],
                "warnings": []}
    case_id = case.get("case_id", case.get("id"))
    if "case_id" not in result:
        errors.append({"code": "CASE_ID_MISSING", "message": "Top-level case_id is required."})
    elif case_id is not None and result["case_id"] != case_id:
        errors.append({"code": "CASE_ID_MISMATCH", "message": f"Expected {case_id!r}, got {result['case_id']!r}."})
    status = result.get("status")
    if status not in STATUSES:
        errors.append({"code": "STATUS_INVALID", "message": "Use success, partial, or failed."})
    for key in ("sources", "uncertainties", "change_records"):
        if key not in result:
            errors.append({"code": "TOP_LEVEL_KEY_MISSING", "message": key})
        elif not isinstance(result[key], list):
            errors.append({"code": "FIELD_TYPE_INVALID", "message": f"{key} must be a list."})
    for key, spec in contract.items():
        if key not in result:
            errors.append({"code": "CONTRACT_KEY_NOT_TOP_LEVEL", "message": key})
            continue
        value = result[key]
        if value is None or value == "" or value == []:
            message = f"Contract key {key} is empty."
            if status == "success" and spec.get("required", True):
                errors.append({"code": "CONTRACT_VALUE_MISSING", "message": message})
            else:
                warnings.append(message)
            continue
        values = value if isinstance(value, list) else [value]
        for item in values:
            if not isinstance(item, str) or not looks_like_path(item, spec):
                continue
            candidate = Path(item)
            resolved = candidate if candidate.is_absolute() else output_root / candidate
            try:
                inside = resolved.resolve().is_relative_to(output_root.resolve())
            except OSError:
                inside = False
            if not inside:
                errors.append({"code": "CONTRACT_PATH_OUTSIDE_OUTPUT", "message": f"{key}: {item}"})
            elif not resolved.is_file():
                message = f"{key}: file does not exist: {item}"
                if status == "success":
                    errors.append({"code": "CONTRACT_FILE_MISSING", "message": message})
                else:
                    warnings.append(message)
    if status == "success":
        for item in result.get("uncertainties", []):
            if isinstance(item, dict) and item.get("status") in {"residual_error", "failed", "error"}:
                errors.append({"code": "RESIDUAL_ERROR_WITH_SUCCESS", "message": str(item.get("code", "unnamed"))})
        if not result.get("sources"):
            warnings.append("Success has an empty sources list; verify that this is genuinely source-free.")
    return {
        "schema": "dual-artifact-quality-gate/contract-audit-v1",
        "case_id": result.get("case_id"),
        "status": "pass" if not errors else "fail",
        "result_status": status,
        "contract_keys": sorted(contract),
        "top_level_contract_verified": True,
        "output_root": output_root.name,
        "errors": errors,
        "warnings": warnings,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--case", type=Path, required=True)
    parser.add_argument("--result", type=Path)
    parser.add_argument("--init-result", type=Path)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        case = load(args.case)
        if not isinstance(case, dict):
            raise ValueError("case.json must be an object")
    except (OSError, ValueError) as exc:
        report = {"schema": "dual-artifact-quality-gate/contract-audit-v1", "status": "fail",
                  "errors": [{"code": "CASE_INPUT_INVALID", "message": str(exc)}], "warnings": []}
        dump(args.report, report)
        return 2
    contract = fields(case)
    if args.init_result:
        result_path = args.init_result
        if result_path.exists():
            try:
                result = load(result_path)
                if not isinstance(result, dict):
                    result = {}
            except (ValueError, OSError):
                result = {}
        else:
            result = {}
        result["case_id"] = case.get("case_id", case.get("id", "unknown"))
        for key in contract:
            result.setdefault(key, None)
        result["status"] = "partial"
        result.setdefault("sources", [])
        checkpoint = "Early checkpoint: required evidence/artifacts are not yet complete."
        uncertainties = result.setdefault("uncertainties", [])
        if uncertainties == []:
            uncertainties.append(checkpoint)
        result.setdefault("change_records", [])
        dump(result_path, result)
    elif args.result:
        result_path = args.result
    else:
        report = {"schema": "dual-artifact-quality-gate/contract-audit-v1", "status": "fail",
                  "errors": [{"code": "RESULT_NOT_SUPPLIED", "message": "Use --result or --init-result."}],
                  "warnings": []}
        dump(args.report, report)
        return 2
    try:
        result = load(result_path)
        report = audit(case, result, args.output_root)
    except (OSError, ValueError) as exc:
        report = {"schema": "dual-artifact-quality-gate/contract-audit-v1", "status": "fail",
                  "errors": [{"code": "RESULT_INPUT_INVALID", "message": str(exc)}], "warnings": []}
    dump(args.report, report)
    return 2 if report.get("errors") else 0


if __name__ == "__main__":
    sys.exit(main())
