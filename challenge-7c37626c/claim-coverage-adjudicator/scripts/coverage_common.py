#!/usr/bin/env python3
"""Shared, bundle-local primitives for claim coverage adjudication.

Python 3.9+ standard library only.  No file outside this bundle is imported.
"""
from __future__ import annotations

import json
import math
import os
import re
import tempfile
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

SCHEMA_VERSION = "claim-coverage-adjudication/v1"
SYSTEM_FIELDS = {"case_id", "status", "evidence", "uncertainty", "artifacts"}
CLAIM_TYPES = {"formula", "variable", "derivation", "numeric", "statement"}
COMPLETION_STATUSES = {
    "completed", "partial", "not_started", "insufficient_evidence", "refuted"
}
RELATIONS = {"supports", "refutes", "context"}
ORIGINS = {"reported", "inference"}

# Deliberately conservative.  A hit never proves that an answer is wrong; it
# prevents a non-answer from satisfying a completion gate.
PLACEHOLDER_EXACT = {
    "", "-", "--", "---", "...", "…", "?", "??", "n/a", "na", "none",
    "null", "nil", "tbd", "tba", "todo", "pending", "pending_analysis",
    "not analyzed", "not analysed", "not yet analyzed", "not yet analysed",
    "unknown", "not known", "not reported", "unreported", "missing",
    "not provided", "not available", "unavailable", "insufficient evidence",
    "insufficient_evidence", "placeholder", "lorem ipsum", "no answer",
    "not started", "not_started", "failed", "error",
}
PLACEHOLDER_PREFIXES = (
    "tbd:", "todo:", "pending:", "unknown:", "missing:",
    "not reported:", "not provided:", "placeholder:",
)
PLACEHOLDER_PATTERNS = (
    re.compile(r"^<+\s*(?:insert|todo|tbd|placeholder)\b", re.I),
    re.compile(r"^\[+\s*(?:insert|todo|tbd|placeholder)\b", re.I),
    re.compile(r"^\{+\s*(?:insert|todo|tbd|placeholder)\b", re.I),
    re.compile(r"^(?:answer|value|content)\s+(?:goes\s+)?here$", re.I),
)


def read_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def write_json(path: Path, value: Any) -> None:
    """Atomically replace a UTF-8 JSON file, retaining its parent directory."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix="." + path.name + ".", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(value, handle, ensure_ascii=False, indent=2, allow_nan=False)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def contract_fields(case: Dict[str, Any]) -> List[str]:
    """Accept required_fields (preferred), legacy fields, and common variants."""
    contract = case.get("output_contract") or {}
    raw = contract.get("required_fields", contract.get("fields", []))
    fields: List[str] = []
    if isinstance(raw, dict):
        raw = list(raw.keys())
    if isinstance(raw, list):
        for item in raw:
            name = item.get("name") if isinstance(item, dict) else item
            if isinstance(name, str) and name and name not in fields:
                fields.append(name)
    if "case_id" not in fields:
        fields.insert(0, "case_id")
    return fields


def field_types(case: Dict[str, Any]) -> Dict[str, str]:
    contract = case.get("output_contract") or {}
    result = dict(contract.get("field_types") or {})
    # Also understand a legacy object-valued fields declaration without making
    # it a substitute for required_fields.
    raw = contract.get("fields")
    if isinstance(raw, dict):
        for name, declaration in raw.items():
            if name not in result and isinstance(declaration, dict):
                if isinstance(declaration.get("type"), str):
                    result[name] = declaration["type"]
            elif name not in result and isinstance(declaration, str):
                result[name] = declaration
    return result


def status_enum(case: Dict[str, Any]) -> List[str]:
    values = (case.get("output_contract") or {}).get("status_enum") or [
        "success", "partial", "insufficient_evidence", "failed"
    ]
    return [value for value in values if isinstance(value, str)]


def empty_for_type(type_name: Optional[str]) -> Any:
    return {
        "object": {}, "array": [], "string": "", "boolean": False,
        "number": None, "integer": None, "null": None,
    }.get(type_name or "", None)


def matches_type(value: Any, type_name: str) -> bool:
    if type_name == "object":
        return isinstance(value, dict)
    if type_name == "array":
        return isinstance(value, list)
    if type_name == "string":
        return isinstance(value, str)
    if type_name == "boolean":
        return isinstance(value, bool)
    if type_name == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    if type_name == "number":
        return (isinstance(value, (int, float)) and not isinstance(value, bool)
                and math.isfinite(float(value)))
    if type_name == "null":
        return value is None
    # Unknown declared types fail closed rather than being ignored.
    return False


def is_placeholder(value: Any) -> bool:
    if value is None:
        return True
    if not isinstance(value, str):
        return False
    normalized = re.sub(r"\s+", " ", value.strip()).casefold()
    if normalized in PLACEHOLDER_EXACT:
        return True
    if normalized.startswith(PLACEHOLDER_PREFIXES):
        return True
    return any(pattern.search(normalized) for pattern in PLACEHOLDER_PATTERNS)


def placeholder_paths(value: Any, path: str = "$") -> List[str]:
    """Find scalar non-answers recursively; zero and False are real values."""
    if is_placeholder(value):
        return [path]
    if isinstance(value, dict):
        found: List[str] = []
        for key, child in value.items():
            found.extend(placeholder_paths(child, "%s.%s" % (path, key)))
        return found
    if isinstance(value, list):
        found = []
        for index, child in enumerate(value):
            found.extend(placeholder_paths(child, "%s[%d]" % (path, index)))
        return found
    return []


def validate_contract_shape(result: Dict[str, Any], case: Dict[str, Any]) -> List[Dict[str, str]]:
    issues: List[Dict[str, str]] = []
    types = field_types(case)
    for field in contract_fields(case):
        if field not in result:
            issues.append({"code": "missing_output_field", "field": field,
                           "message": "required output field is absent"})
            continue
        if field in types and not matches_type(result[field], types[field]):
            issues.append({"code": "output_field_type", "field": field,
                           "message": "expected %s" % types[field]})
    expected = case.get("case_id")
    if result.get("case_id") != expected:
        issues.append({"code": "case_id_mismatch", "field": "case_id",
                       "message": "result case_id must exactly equal input case_id"})
    status = result.get("status")
    allowed = status_enum(case)
    if status not in allowed:
        issues.append({"code": "status_not_in_enum", "field": "status",
                       "message": "status %r is not in %r" % (status, allowed)})
    return issues


def initial_result(case: Dict[str, Any], work: Path) -> Dict[str, Any]:
    types = field_types(case)
    result: Dict[str, Any] = {}
    for field in contract_fields(case):
        result[field] = empty_for_type(types.get(field))
    result["case_id"] = case.get("case_id")
    allowed = status_enum(case)
    result["status"] = "partial" if "partial" in allowed else (
        "insufficient_evidence" if "insufficient_evidence" in allowed else allowed[0]
    )
    for name, default in (("answers", {}), ("evidence", []),
                          ("uncertainty", {}), ("artifacts", {})):
        if name in result and name not in types:
            result[name] = default
    if isinstance(result.get("uncertainty"), dict):
        result["uncertainty"].update({
            "stage": "scaffold",
            "limits": ["analysis and claim adjudication have not completed"],
            "empty_or_null_fields": [
                field for field in result
                if field not in {"case_id", "status", "uncertainty"}
                and (result[field] is None or result[field] == "" or result[field] == []
                     or result[field] == {})
            ],
        })
    if isinstance(result.get("artifacts"), dict):
        result["artifacts"].update({
            "work_dir": str(work),
            "note": "early honest partial; no scientific answer asserted",
        })
    return result


def normalize_answer(value: Any) -> str:
    if isinstance(value, str):
        return re.sub(r"\s+", " ", value.strip()).casefold()
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def evidence_key(record: Dict[str, Any]) -> Tuple[str, str, str, str]:
    return (
        str(record.get("excerpt_id", "")),
        str(record.get("source_file", "")),
        str(record.get("locator", "")),
        str(record.get("quote", "")),
    )


def issue(code: str, message: str, **context: Any) -> Dict[str, Any]:
    value = {"code": code, "message": message}
    value.update(context)
    return value
