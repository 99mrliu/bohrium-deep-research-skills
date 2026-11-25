#!/usr/bin/env python3
"""Assemble result.json from extraction evidence and actual agent-authored analysis.

The extractor never supplies scientific claims.  Missing required analysis is
represented as explicit empty/insufficient evidence (or null when no honest value
of the declared scalar type exists), and every result gets a validation sidecar.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import sys
from typing import Any, Dict, Iterable, List, Optional, Tuple


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def load_object(path: Path) -> Dict[str, Any]:
    value = load_json(path)
    if not isinstance(value, dict):
        raise ValueError(f"{path}: expected a JSON object")
    return value


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def find_contract(value: Any) -> Optional[Dict[str, Any]]:
    if not isinstance(value, dict):
        return None
    candidate = value.get("output_contract")
    if isinstance(candidate, dict):
        return candidate
    if any(key in value for key in ("required_fields", "field_types", "properties")):
        return value
    for key in sorted(value):
        found = find_contract(value[key])
        if found is not None:
            return found
    return None


def contract_from_task(path: Path) -> Optional[Dict[str, Any]]:
    text = path.read_text(encoding="utf-8")
    candidates = [text]
    candidates.extend(re.findall(r"```(?:json)?\s*(\{.*?\})\s*```", text, flags=re.DOTALL | re.IGNORECASE))
    for candidate in candidates:
        try:
            value = json.loads(candidate)
        except json.JSONDecodeError:
            continue
        contract = find_contract(value)
        if contract is not None:
            return contract
    return None


def ordered_unique(values: Iterable[str]) -> List[str]:
    result: List[str] = []
    seen = set()
    for value in values:
        if value not in seen:
            result.append(value)
            seen.add(value)
    return result


def contract_details(contract: Dict[str, Any]) -> Tuple[List[str], List[str], Dict[str, Any], List[str]]:
    required_raw = contract.get("required_fields", [])
    required = [item for item in required_raw if isinstance(item, str)] if isinstance(required_raw, list) else []

    properties: Dict[str, Any] = {}
    for key in ("properties", "fields"):
        candidate = contract.get(key)
        if isinstance(candidate, dict):
            properties.update({str(name): spec for name, spec in candidate.items()})
    # A direct mapping of field specifications is also accepted, while dynamic
    # contract control keys are not mistaken for result fields.
    controls = {"required_fields", "field_types", "status_enum", "properties", "fields", "description", "additional_fields"}
    direct = {
        key: value
        for key, value in contract.items()
        if key not in controls and isinstance(value, (dict, str))
    }
    for key, value in direct.items():
        properties.setdefault(key, value)

    all_fields = ordered_unique(required + list(properties))
    field_types: Dict[str, Any] = {}
    raw_types = contract.get("field_types", {})
    if isinstance(raw_types, dict):
        field_types.update(raw_types)
        all_fields = ordered_unique(all_fields + [str(name) for name in raw_types])
    for field, spec in properties.items():
        if field not in field_types:
            if isinstance(spec, str):
                field_types[field] = spec
            elif isinstance(spec, dict) and "type" in spec:
                field_types[field] = spec["type"]
    if "case_id" in required and "case_id" not in field_types:
        field_types["case_id"] = "string"

    raw_enum = contract.get("status_enum")
    if raw_enum is None and isinstance(properties.get("status"), dict):
        raw_enum = properties["status"].get("enum")
    status_enum = [item for item in raw_enum if isinstance(item, str)] if isinstance(raw_enum, list) else []
    if status_enum:
        all_fields = ordered_unique(all_fields + ["status"])
        field_types.setdefault("status", "string")
    return required, all_fields, field_types, status_enum


def normalized_type(spec: Any) -> Any:
    if isinstance(spec, list):
        return [normalized_type(item) for item in spec]
    if not isinstance(spec, str):
        return spec
    value = spec.strip().lower()
    aliases = {
        "list": "array",
        "dict": "object",
        "str": "string",
        "int": "integer",
        "float": "number",
        "bool": "boolean",
    }
    value = aliases.get(value, value)
    if value.startswith("array"):
        return "array"
    if value.startswith("object"):
        return "object"
    return value


def matches_type(value: Any, spec: Any) -> bool:
    if spec is None or spec == "":
        return True
    if isinstance(spec, list):
        return any(matches_type(value, option) for option in spec)
    kind = normalized_type(spec)
    if kind == "array":
        return isinstance(value, list)
    if kind == "object":
        return isinstance(value, dict)
    if kind == "string":
        return isinstance(value, str)
    if kind == "number":
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    if kind == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    if kind == "boolean":
        return isinstance(value, bool)
    if kind == "null":
        return value is None
    # Unknown schema types are reported instead of being treated as validated.
    return False


def extraction_fact(catalog: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "status": catalog.get("status", "insufficient_evidence"),
        "formula_count": catalog.get("formula_count", 0),
        "source_count": catalog.get("source_count", 0),
        "catalog": "mathml/catalog.json",
        "catalog_markdown": "mathml/catalog.md",
        "scope": "MathML extraction and rendering only; not scientific analysis.",
    }


def placeholder(field: str, spec: Any, reason: str, status: str) -> Any:
    kind = normalized_type(spec)
    if isinstance(spec, list):
        # Prefer an honest empty container if one of the union types permits it.
        if "array" in spec:
            kind = "array"
        elif "object" in spec:
            kind = "object"
        elif "null" in spec:
            kind = "null"
        elif "string" in spec:
            kind = "string"
    if kind == "array":
        return []
    if kind == "object":
        return {"status": status, "reason": reason}
    if kind == "string":
        return f"{status}: {reason}"
    if kind == "boolean":
        # False can be a substantive answer, so use null and report the type issue.
        return None
    if kind == "null" or spec is None:
        return None
    return None


def choose_status(enum: List[str], preferred: str) -> str:
    if not enum:
        return preferred
    if preferred in enum:
        return preferred
    for candidate in ("insufficient_evidence", "partial", "incomplete", "failed", "success"):
        if candidate in enum:
            return candidate
    return enum[0]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--case", default="/input/case.json")
    parser.add_argument("--task", default="/input/task.md")
    parser.add_argument("--catalog", default="/app/work/mathml/catalog.json")
    parser.add_argument("--analysis", help="Actual agent-authored analysis JSON; omit only for an honest early partial")
    parser.add_argument("--output", default="/app/output/result.json")
    args = parser.parse_args()

    case_path = Path(args.case).expanduser().resolve()
    task_path = Path(args.task).expanduser().resolve()
    catalog_path = Path(args.catalog).expanduser().resolve()
    output_path = Path(args.output).expanduser().resolve()
    case = load_object(case_path)
    if "case_id" not in case or case["case_id"] is None:
        raise ValueError("case.json must contain case_id")
    case_id = case["case_id"]
    contract = find_contract(case)
    if contract is None:
        contract = contract_from_task(task_path)
    if contract is None:
        raise ValueError("No JSON output_contract found in case.json or task.md JSON/JSON fence")
    catalog = load_object(catalog_path)
    if catalog.get("case_id") != case_id:
        raise ValueError("Extraction catalog case_id does not exactly match case.json")

    required, all_fields, field_types, status_enum = contract_details(contract)
    analysis: Dict[str, Any] = {}
    analysis_supplied = False
    if args.analysis:
        analysis_path = Path(args.analysis).expanduser().resolve()
        analysis = load_object(analysis_path)
        analysis_supplied = True
    issues: List[Dict[str, str]] = []
    if isinstance(analysis.get("case_id"), (str, int)) and analysis["case_id"] != case_id:
        issues.append({"field": "case_id", "kind": "agent_case_id_ignored", "detail": "case.json is authoritative"})

    result: Dict[str, Any] = {"case_id": case_id}
    for field, value in analysis.items():
        if field != "case_id":
            result[field] = value

    missing: List[str] = []
    no_formula = catalog.get("formula_count", 0) == 0 or catalog.get("status") == "insufficient_evidence"
    scientific_keys = {"formula_analysis", "variable_analysis", "derivation_analysis", "numeric_analysis", "formulas", "variables", "derivations"}
    has_scientific_analysis = any(
        key in analysis and analysis[key] not in (None, "", [], {})
        for key in scientific_keys
    )
    if no_formula:
        default_status = choose_status(status_enum, "insufficient_evidence")
    elif not analysis_supplied or not has_scientific_analysis:
        default_status = choose_status(status_enum, "insufficient_evidence")
    else:
        default_status = choose_status(status_enum, "partial")

    # Only factual extraction metadata can be derived automatically.  Science
    # fields are never populated from latex or the catalog.
    for field in required + [name for name in all_fields if name.startswith("extraction_")]:
        if field in {"case_id", "status"} or field in result:
            continue
        if field in {"extraction_summary", "mathml_extraction", "extraction_evidence"}:
            if normalized_type(field_types.get(field, "object")) == "object":
                result[field] = extraction_fact(catalog)

    for field in all_fields:
        if field == "case_id" or field == "status" or field in result:
            continue
        if field in required or field in analysis:
            missing.append(field)
    # Optional declared properties are included with an explicit placeholder too
    # when field_types declares them, preventing ambiguous contract omissions.
    for field in all_fields:
        if field in {"case_id", "status"} or field in result:
            continue
        reason = (
            "No MathML formula was available; no formula or numeric value may be invented."
            if no_formula
            else "Required agent-authored evidence was not supplied; extraction does not answer this field."
        )
        result[field] = placeholder(field, field_types.get(field), reason, default_status)

    requested_status = result.get("status")
    if no_formula:
        status = choose_status(status_enum, "insufficient_evidence")
    elif requested_status in status_enum if status_enum else isinstance(requested_status, str):
        status = requested_status
    else:
        status = default_status
    if missing and status == "success":
        status = choose_status(status_enum, "partial")
        issues.append({"field": "status", "kind": "status_downgraded", "detail": "Required fields were missing"})
    if requested_status is not None and status_enum and requested_status not in status_enum:
        issues.append({"field": "status", "kind": "invalid_status_replaced", "detail": str(requested_status)})
    if "status" in all_fields or "status" in result or status_enum:
        result["status"] = status
    elif "status" not in result:
        result["status"] = status

    for field in required:
        if field not in result:
            # Defensive: schema-required fields are never silently omitted.
            result[field] = placeholder(field, field_types.get(field), "Field was missing after assembly", status)
            if field not in missing:
                missing.append(field)
    for field in ordered_unique(list(field_types) + required + all_fields + list(result)):
        if field not in result:
            issues.append({"field": field, "kind": "missing_required_field", "detail": "No value assembled"})
            continue
        spec = field_types.get(field)
        if spec is not None and not matches_type(result[field], spec):
            issues.append(
                {
                    "field": field,
                    "kind": "field_type_mismatch",
                    "detail": f"Expected {spec}; got {type(result[field]).__name__}. No value was fabricated to satisfy the type.",
                }
            )
    if no_formula:
        result["status"] = choose_status(status_enum, "insufficient_evidence")
    for field in missing:
        issues.append({"field": field, "kind": "honest_placeholder", "detail": "Agent-authored evidence was absent"})

    write_json(output_path, result)
    validation = {
        "case_id": case_id,
        "result": str(output_path),
        "status": result.get("status"),
        "analysis_supplied": analysis_supplied,
        "required_fields": required,
        "all_declared_fields": all_fields,
        "missing_authored_fields": sorted(set(missing)),
        "issues": issues,
        "contract_valid": not any(issue["kind"] in {"field_type_mismatch", "missing_required_field"} for issue in issues),
        "no_formula_insufficient_evidence": no_formula,
        "note": "Empty/null fields are honest partial output. Extraction never substitutes for agent-authored scientific analysis.",
    }
    validation_path = output_path.parent / "result_validation.json"
    write_json(validation_path, validation)
    print(f"result assembly: status={result.get('status')}, result={output_path}, validation={validation_path}")
    if not validation["contract_valid"]:
        print("result assembly: contract type/presence issues remain; see result_validation.json", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
