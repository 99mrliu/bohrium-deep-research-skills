#!/usr/bin/env python3
"""Dynamic task-contract extraction and result construction/finalization helpers."""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from quantity_core import VerificationError


def read_json(path: Path) -> Any:
    try:
        with path.open("r", encoding="utf-8") as handle:
            return json.load(handle)
    except (OSError, json.JSONDecodeError) as exc:
        raise VerificationError(f"cannot read JSON {path}: {exc}") from exc


def json_blocks(markdown: str) -> list[Any]:
    documents = []
    for match in re.finditer(r"```(?:json|JSON)\s*\n(.*?)```", markdown, flags=re.S):
        try:
            documents.append(json.loads(match.group(1)))
        except json.JSONDecodeError:
            continue
    return documents


def locate_contract(task_text: str, case: dict[str, Any]) -> dict[str, Any]:
    candidates = json_blocks(task_text)
    candidates.append(case)
    for candidate in candidates:
        if not isinstance(candidate, dict):
            continue
        possibilities = [candidate]
        for key in ("output_contract", "result_contract"):
            if isinstance(candidate.get(key), dict):
                possibilities.insert(0, candidate[key])
        for contract in possibilities:
            if any(key in contract for key in ("required_fields", "field_types", "status_enum", "fields", "properties")):
                return contract
    # A safe contract for interactive use; a supplied task contract always takes precedence.
    return {
        "required_fields": ["case_id", "status", "answers", "artifacts"],
        "field_types": {"case_id": "string", "status": "string", "answers": "object", "artifacts": "array"},
        "status_enum": ["complete", "partial"],
    }


def _field_entries(contract: dict[str, Any]) -> dict[str, Any]:
    entries: dict[str, Any] = {}
    for container_name in ("field_types", "fields", "properties"):
        container = contract.get(container_name, {})
        if isinstance(container, dict):
            entries.update(container)
    return entries


def normalize_contract(contract: dict[str, Any]) -> dict[str, Any]:
    entries = _field_entries(contract)
    required_raw = contract.get("required_fields", contract.get("required", []))
    required: list[str] = []
    if isinstance(required_raw, list):
        for item in required_raw:
            if isinstance(item, str):
                required.append(item)
            elif isinstance(item, dict) and isinstance(item.get("name"), str):
                required.append(item["name"])
                entries.setdefault(item["name"], item.get("type", item))
    elif isinstance(required_raw, dict):
        for name, definition in required_raw.items():
            required.append(name)
            entries.setdefault(name, definition)
    # Validate every declared contract field, not only the required subset.
    ordered = list(dict.fromkeys(required + list(entries)))
    normalized_entries = {}
    for name in ordered:
        definition = entries.get(name, "string")
        normalized_entries[name] = {"type": definition} if isinstance(definition, str) else definition
    status_enum = contract.get("status_enum")
    if status_enum is None and isinstance(normalized_entries.get("status"), dict):
        status_enum = normalized_entries["status"].get("enum")
        if status_enum is None and isinstance(normalized_entries["status"].get("values"), list):
            status_enum = normalized_entries["status"]["values"]
    if not isinstance(status_enum, list) or not all(isinstance(x, str) for x in status_enum) or not status_enum:
        status_enum = ["complete", "partial"]
    return {"fields": normalized_entries, "required_fields": required or ordered, "status_enum": status_enum, "raw": contract}


def select_status(allowed: list[str], recommendation: str) -> str:
    if recommendation == "complete":
        preferences = ["complete", "completed", "success", "done", "finished", "ok"]
    else:
        preferences = ["partial", "insufficient_evidence", "incomplete", "in_progress", "blocked", "failed"]
    for value in preferences:
        if value in allowed:
            return value
    # Do not write a status outside the dynamic enum.
    return allowed[0]


def default_for(definition: Any) -> Any:
    if isinstance(definition, str):
        definition = {"type": definition}
    if not isinstance(definition, dict):
        return None
    if "default" in definition:
        return definition["default"]
    if "const" in definition:
        return definition["const"]
    kind = definition.get("type", "string")
    if isinstance(kind, list):
        if "null" in kind:
            return None
        kind = kind[0] if kind else "string"
    return {
        "object": {}, "dict": {}, "array": [], "list": [], "string": "",
        "number": None, "integer": None, "boolean": False, "bool": False, "null": None,
    }.get(kind)


def known_value(name: str, definition: Any, analysis: dict[str, Any] | None, case_id: Any, status: str) -> tuple[bool, Any]:
    if name == "case_id":
        return True, case_id
    if name in {"status", "verification_status"}:
        return True, status
    if not analysis:
        return False, None
    if name in {"source_claim_verdict", "source_verdict"}:
        value = analysis.get("source_claim_verdict")
        expected = definition.get("type") if isinstance(definition, dict) else definition
        if expected in {"object", "dict"}:
            return True, {"verdict": value, "claims": analysis.get("claims", [])}
        return True, value
    if name in {"diagnostic_fault_injection_verdict", "fault_injection_verdict"}:
        value = analysis.get("diagnostic_fault_injection_verdict", {})
        expected = definition.get("type") if isinstance(definition, dict) else definition
        if expected in {"string", "str"} and isinstance(value, dict):
            value = value.get("overall")
        return True, value
    if name in {"analysis", "verification", "verification_result", "diagnostics"}:
        return True, analysis
    if name in {"limitations", "evidence_gaps"}:
        gaps = analysis.get("evidence_gaps", []) + analysis.get("errors", [])
        expected = definition.get("type") if isinstance(definition, dict) else definition
        return True, gaps if expected in {"array", "list"} else "; ".join(gaps)
    if name in {"report", "text_report"}:
        return True, analysis.get("report_path", "")
    return False, None


def base_result(contract: dict[str, Any], case_id: Any, analysis: dict[str, Any] | None = None, early: bool = False) -> dict[str, Any]:
    recommendation = "partial" if early or not analysis else analysis.get("recommended_status", "partial")
    status = select_status(contract["status_enum"], recommendation)
    result = {}
    for name, definition in contract["fields"].items():
        present, value = known_value(name, definition, analysis, case_id, status)
        result[name] = value if present else default_for(definition)
    # case_id is mandatory even if a malformed contract omitted it.
    result["case_id"] = case_id
    return result


def schema_children(definition: dict[str, Any]) -> dict[str, Any]:
    children = {}
    for key in ("properties", "field_types", "fields"):
        if isinstance(definition.get(key), dict):
            children.update(definition[key])
    return children


def schema_required(definition: dict[str, Any]) -> list[str]:
    values = []
    for key in ("required", "required_fields"):
        raw = definition.get(key, [])
        if isinstance(raw, list):
            for item in raw:
                if isinstance(item, str):
                    values.append(item)
                elif isinstance(item, dict) and isinstance(item.get("name"), str):
                    values.append(item["name"])
    return list(dict.fromkeys(values))


def matches_type(value: Any, kind: str) -> bool:
    return {
        "object": isinstance(value, dict), "dict": isinstance(value, dict),
        "array": isinstance(value, list), "list": isinstance(value, list),
        "string": isinstance(value, str), "str": isinstance(value, str),
        "number": isinstance(value, (int, float)) and not isinstance(value, bool),
        "integer": isinstance(value, int) and not isinstance(value, bool),
        "boolean": isinstance(value, bool), "bool": isinstance(value, bool),
        "null": value is None,
    }.get(kind, True)


def validate_schema(value: Any, definition: Any, path: str, errors: list[str]) -> None:
    if isinstance(definition, str):
        definition = {"type": definition}
    if not isinstance(definition, dict):
        return
    if "anyOf" in definition and isinstance(definition["anyOf"], list):
        branches = []
        for alternative in definition["anyOf"]:
            branch_errors: list[str] = []
            validate_schema(value, alternative, path, branch_errors)
            branches.append(branch_errors)
        if all(branches):
            errors.append(f"{path} does not match anyOf: {branches[0]}")
        return
    kind = definition.get("type")
    kinds = kind if isinstance(kind, list) else ([kind] if isinstance(kind, str) else [])
    if kinds and not any(matches_type(value, item) for item in kinds):
        errors.append(f"{path} must have type {kind}, got {type(value).__name__}")
        return
    if "enum" in definition and value not in definition["enum"]:
        errors.append(f"{path}={value!r} is outside enum {definition['enum']!r}")
    if "const" in definition and value != definition["const"]:
        errors.append(f"{path} must equal const {definition['const']!r}")
    if isinstance(value, str) and definition.get("minLength", 0) > len(value):
        errors.append(f"{path} is shorter than minLength")
    if isinstance(value, dict):
        for required in schema_required(definition):
            if required not in value or value[required] is None or value[required] in ("", [], {}):
                errors.append(f"{path}.{required} is required and must be non-empty")
        for key, child_definition in schema_children(definition).items():
            if key in value:
                validate_schema(value[key], child_definition, f"{path}.{key}", errors)
    if isinstance(value, list) and "items" in definition:
        for index, item in enumerate(value):
            validate_schema(item, definition["items"], f"{path}[{index}]", errors)
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        if "minimum" in definition and value < definition["minimum"]:
            errors.append(f"{path} is below minimum")
        if "maximum" in definition and value > definition["maximum"]:
            errors.append(f"{path} is above maximum")


def artifact_paths(artifacts: Any) -> list[str]:
    paths = []
    if isinstance(artifacts, list):
        for item in artifacts:
            if isinstance(item, str):
                paths.append(item)
            elif isinstance(item, dict) and isinstance(item.get("path"), str):
                paths.append(item["path"])
    elif isinstance(artifacts, dict):
        for value in artifacts.values():
            if isinstance(value, str):
                paths.append(value)
            elif isinstance(value, dict) and isinstance(value.get("path"), str):
                paths.append(value["path"])
    return paths


def finalize(contract: dict[str, Any], case_id: Any, analysis: dict[str, Any], answers: Any, artifacts: Any) -> tuple[dict[str, Any], list[str]]:
    result = base_result(contract, case_id, analysis)
    status = select_status(contract["status_enum"], analysis.get("recommended_status", "partial"))
    errors = []
    for name, definition in contract["fields"].items():
        if name == "answers":
            result[name] = answers
        elif name == "artifacts":
            result[name] = artifacts
        elif name in {"status", "verification_status"}:
            result[name] = status
        elif isinstance(answers, dict) and name in answers:
            # Also support contracts with direct agent-authored fields instead of one answers object.
            result[name] = answers[name]
    result["case_id"] = case_id
    if answers is None or answers == {} or answers == [] or answers == "":
        errors.append("agent-authored answers must be non-empty; the finalizer does not invent answers")
    if artifacts is None or artifacts == {} or artifacts == [] or artifacts == "":
        errors.append("artifacts must reference at least one retained analysis/report file")
    for name in contract["fields"]:
        if name in {"status", "verification_status"}:
            definition = dict(contract["fields"][name]) if isinstance(contract["fields"][name], dict) else {"type": contract["fields"][name]}
            definition["enum"] = contract["status_enum"]
            validate_schema(result[name], definition, name, errors)
        else:
            validate_schema(result[name], contract["fields"][name], name, errors)
    for name in contract["required_fields"]:
        if name not in result:
            errors.append(f"required contract field {name!r} is absent")
        elif result[name] is None or result[name] in ("", [], {}):
            errors.append(f"required contract field {name!r} is null or empty")
    for path in artifact_paths(artifacts):
        if not Path(path).is_file():
            errors.append(f"artifact does not exist or is not a file: {path}")
    if result.get("case_id") != case_id:
        errors.append("case_id differs from the input case")
    return result, errors
