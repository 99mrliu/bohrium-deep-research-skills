#!/usr/bin/env python3
"""Dynamic output-contract skeleton and structural final-result validation."""
from __future__ import annotations

import argparse
import copy
import json
import sys
from pathlib import Path
from typing import Any

VERDICTS = {
    "supported",
    "partially_supported",
    "contradicted",
    "insufficient_evidence",
}
STATUSES = {"success", "partial", "failed"}
WRAPPER_KEYS = ("fields", "output_fields", "contract_fields")
META_KEYS = {
    "$schema",
    "title",
    "description",
    "type",
    "required",
    "additionalProperties",
    "properties",
    "items",
}


def load_json(path: Path) -> Any:
    def no_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        out: dict[str, Any] = {}
        for key, value in pairs:
            if key in out:
                raise ValueError(f"duplicate JSON key: {key}")
            out[key] = value
        return out

    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle, object_pairs_hook=no_duplicates)


def field_entries(contract: Any) -> list[tuple[str, Any]]:
    """Normalize list/dict/json-schema-like output contracts without fixing field names."""
    if isinstance(contract, list):
        entries: list[tuple[str, Any]] = []
        for item in contract:
            if isinstance(item, str):
                entries.append((item, {}))
            elif isinstance(item, dict):
                name = next(
                    (item[k] for k in ("name", "key", "field", "id") if isinstance(item.get(k), str)),
                    None,
                )
                if not name:
                    raise ValueError("list contract object lacks name/key/field/id")
                entries.append((name, item))
            else:
                raise ValueError("output_contract list entries must be strings or objects")
        return entries
    if not isinstance(contract, dict):
        raise ValueError("output_contract must be a list or object")
    for wrapper in WRAPPER_KEYS:
        if wrapper in contract:
            return field_entries(contract[wrapper])
    if isinstance(contract.get("properties"), dict):
        return [(str(k), v) for k, v in contract["properties"].items()]
    if isinstance(contract.get("required"), list) and not contract.get("properties"):
        return [(str(k), {}) for k in contract["required"]]
    return [(str(k), v) for k, v in contract.items() if k not in META_KEYS]


def schema_type(spec: Any) -> str | None:
    if isinstance(spec, str):
        lowered = spec.lower()
        aliases = {
            "str": "string",
            "text": "string",
            "list": "array",
            "dict": "object",
            "int": "integer",
            "float": "number",
            "bool": "boolean",
        }
        return aliases.get(lowered, lowered if lowered in {"string", "array", "object", "number", "integer", "boolean", "null"} else None)
    if isinstance(spec, dict):
        value = spec.get("type", spec.get("value_type"))
        if isinstance(value, list):
            value = next((v for v in value if v != "null"), None)
        return schema_type(value) if value is not None else None
    return None


def empty_value(name: str, spec: Any) -> Any:
    if isinstance(spec, dict) and "default" in spec:
        return copy.deepcopy(spec["default"])
    kind = schema_type(spec)
    if kind == "array":
        return []
    if kind == "object":
        props = spec.get("properties") if isinstance(spec, dict) else None
        if isinstance(props, dict):
            return {str(k): empty_value(str(k), v) for k, v in props.items()}
        return {}
    if kind == "string":
        return ""
    if kind in {"number", "integer", "boolean", "null"}:
        return None
    lowered = name.lower()
    if lowered.endswith("s") or any(token in lowered for token in ("list", "items", "records", "sources", "verdicts")):
        return []
    if any(token in lowered for token in ("count", "score", "number", "total")):
        return None
    return ""


def build_skeleton(case: dict[str, Any]) -> dict[str, Any]:
    if "output_contract" not in case:
        raise ValueError("case.json lacks output_contract")
    case_id = case.get("case_id", case.get("id", case.get("caseId", "unknown_case")))
    result: dict[str, Any] = {"case_id": case_id}
    for name, spec in field_entries(case["output_contract"]):
        if name != "case_id":
            result[name] = empty_value(name, spec)
    result["status"] = "partial"
    result["sources"] = []
    result["uncertainty"] = ["Partial skeleton only; source reading, annotation, and final population are pending."]
    result["change_records"] = []
    return result


def validate_type(value: Any, spec: Any, allow_none: bool) -> bool:
    if value is None:
        return allow_none or schema_type(spec) == "null"
    kind = schema_type(spec)
    if kind is None:
        return True
    checks = {
        "string": lambda v: isinstance(v, str),
        "array": lambda v: isinstance(v, list),
        "object": lambda v: isinstance(v, dict),
        "number": lambda v: isinstance(v, (int, float)) and not isinstance(v, bool),
        "integer": lambda v: isinstance(v, int) and not isinstance(v, bool),
        "boolean": lambda v: isinstance(v, bool),
        "null": lambda v: v is None,
    }
    return checks[kind](value)


def walk_verdicts(value: Any, trail: str = "result") -> list[str]:
    errors: list[str] = []
    if isinstance(value, dict):
        for key, child in value.items():
            if key == "verdict" and child not in VERDICTS:
                errors.append(f"{trail}.{key} has invalid verdict {child!r}")
            errors.extend(walk_verdicts(child, f"{trail}.{key}"))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            errors.extend(walk_verdicts(child, f"{trail}[{index}]"))
    return errors


def validate_result(case: dict[str, Any], result: Any) -> list[str]:
    errors: list[str] = []
    if not isinstance(result, dict):
        return ["result.json must contain a top-level object"]
    expected_case_id = case.get("case_id", case.get("id", case.get("caseId", "unknown_case")))
    if result.get("case_id") != expected_case_id:
        errors.append(f"case_id must equal {expected_case_id!r}")
    if "output_contract" not in case:
        errors.append("case.json lacks output_contract")
        entries: list[tuple[str, Any]] = []
    else:
        try:
            entries = field_entries(case["output_contract"])
        except ValueError as exc:
            return [str(exc)]
    status = result.get("status")
    for name, spec in entries:
        if name not in result:
            errors.append(f"missing output_contract field: {name}")
        elif not validate_type(result[name], spec, status != "success"):
            errors.append(f"field {name} does not match declared type {schema_type(spec)}")
    for required in ("status", "sources", "uncertainty", "change_records"):
        if required not in result:
            errors.append(f"missing required field: {required}")
    if status not in STATUSES:
        errors.append("status must be success, partial, or failed")
    if not isinstance(result.get("sources"), list):
        errors.append("sources must be a list")
    elif status in {"success", "partial"} and not result["sources"]:
        errors.append("sources cannot be empty for success/partial")
    if not isinstance(result.get("uncertainty"), (list, str)):
        errors.append("uncertainty must be a list or string")
    elif status in {"partial", "failed"} and not result["uncertainty"]:
        errors.append("partial/failed result must explain uncertainty")
    if not isinstance(result.get("change_records"), list):
        errors.append("change_records must be a list")
    elif status == "success":
        for index, record in enumerate(result["change_records"]):
            if isinstance(record, dict) and record.get("review_status") == "unresolved":
                errors.append(f"success cannot contain unresolved change_records[{index}]")
    errors.extend(walk_verdicts(result))
    return errors


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    skeleton = sub.add_parser("skeleton")
    skeleton.add_argument("--case-json", required=True, type=Path)
    skeleton.add_argument("--output", required=True, type=Path)
    final = sub.add_parser("validate-final")
    final.add_argument("--case-json", required=True, type=Path)
    final.add_argument("--result", required=True, type=Path)
    args = parser.parse_args()
    try:
        case = load_json(args.case_json)
        if not isinstance(case, dict):
            raise ValueError("case.json must contain an object")
        if args.command == "skeleton":
            write_json(args.output, build_skeleton(case))
            print(f"wrote dynamic partial skeleton: {args.output}")
            return 0
        result = load_json(args.result)
        errors = validate_result(case, result)
        if errors:
            for error in errors:
                print(f"ERROR: {error}", file=sys.stderr)
            return 1
        print("final result satisfies the dynamic structural contract")
        return 0
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
