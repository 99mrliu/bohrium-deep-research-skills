#!/usr/bin/env python3
"""Audit semantic coverage and a documented JSON Schema subset using only stdlib.

The auditor checks mechanical conditions, not scientific truth. Exact quote retrieval,
required-term presence, and a non-empty checked scope do not establish entailment.
"""

import argparse
import json
import os
import re
import sys
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple


class AuditInputError(Exception):
    """Malformed or unsupported auditor input."""


class DuplicateKeyError(ValueError):
    pass


def unique_object(pairs: Sequence[Tuple[str, Any]]) -> Dict[str, Any]:
    obj: Dict[str, Any] = {}
    for key, value in pairs:
        if key in obj:
            raise DuplicateKeyError("duplicate JSON key: %s" % key)
        obj[key] = value
    return obj


def load_json(path: Path, label: str) -> Any:
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        raise AuditInputError("cannot read %s at %s: %s" % (label, path, exc))
    try:
        return json.loads(text, object_pairs_hook=unique_object)
    except (json.JSONDecodeError, DuplicateKeyError) as exc:
        raise AuditInputError("malformed %s at %s: %s" % (label, path, exc))


def write_json(path: Path, value: Any) -> None:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
    except (OSError, UnicodeError) as exc:
        raise AuditInputError("cannot write report at %s: %s" % (path, exc))


def escape_pointer(token: str) -> str:
    return token.replace("~", "~0").replace("/", "~1")


def pointer_tokens(pointer: str) -> List[str]:
    if pointer == "":
        return []
    if not isinstance(pointer, str) or not pointer.startswith("/"):
        raise AuditInputError("invalid JSON Pointer (must be empty or start with '/'): %r" % pointer)
    tokens = []
    for raw in pointer[1:].split("/"):
        # Strict RFC 6901 escapes: '~' may only introduce '~0' or '~1'.
        index = 0
        while index < len(raw):
            if raw[index] == "~":
                if index + 1 >= len(raw) or raw[index + 1] not in ("0", "1"):
                    raise AuditInputError("invalid JSON Pointer escape in %r" % pointer)
                index += 2
            else:
                index += 1
        tokens.append(raw.replace("~1", "/").replace("~0", "~"))
    return tokens


def resolve_pointer(document: Any, pointer: str) -> Tuple[bool, Any]:
    current = document
    for token in pointer_tokens(pointer):
        if isinstance(current, dict):
            if token not in current:
                return False, None
            current = current[token]
        elif isinstance(current, list):
            if not re.match(r"^(0|[1-9][0-9]*)$", token):
                return False, None
            index = int(token)
            if index >= len(current):
                return False, None
            current = current[index]
        else:
            return False, None
    return True, current


def resolve_schema_pointer(schema: Dict[str, Any], pointer: str) -> Optional[Dict[str, Any]]:
    current: Any = schema
    for token in pointer_tokens(pointer):
        if not isinstance(current, dict):
            return None
        if "items" in current and isinstance(current.get("items"), dict):
            # Array indices do not change the item schema.
            if re.match(r"^(0|[1-9][0-9]*)$", token):
                current = current["items"]
                continue
        properties = current.get("properties", {})
        if isinstance(properties, dict) and token in properties:
            current = properties[token]
        else:
            return None
    return current if isinstance(current, dict) else None


def json_equal(left: Any, right: Any) -> bool:
    if isinstance(left, bool) or isinstance(right, bool):
        return type(left) is type(right) and left == right
    if isinstance(left, (int, float)) and isinstance(right, (int, float)):
        return left == right
    if type(left) is not type(right):
        return False
    return left == right


def matches_type(value: Any, expected: str) -> bool:
    if expected == "object":
        return isinstance(value, dict)
    if expected == "array":
        return isinstance(value, list)
    if expected == "string":
        return isinstance(value, str)
    if expected == "boolean":
        return isinstance(value, bool)
    if expected == "null":
        return value is None
    if expected == "number":
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    if expected == "integer":
        if isinstance(value, bool):
            return False
        return isinstance(value, int) or (isinstance(value, float) and value.is_integer())
    raise AuditInputError("unsupported JSON Schema type: %r" % expected)


class Audit:
    def __init__(self) -> None:
        self.findings: List[Dict[str, str]] = []

    def add(self, severity: str, code: str, path: str, message: str) -> None:
        self.findings.append(
            {"severity": severity, "code": code, "path": path, "message": message}
        )

    def structural(self, code: str, path: str, message: str) -> None:
        self.add("STRUCTURAL", code, path, message)

    def semantic(self, code: str, path: str, message: str) -> None:
        self.add("SEMANTIC", code, path, message)

    def count(self, severity: str) -> int:
        return sum(1 for item in self.findings if item["severity"] == severity)


def require_number(value: Any, keyword: str, path: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise AuditInputError("schema %s at %s must be a number" % (keyword, path or "/"))
    return value


def require_nonnegative_int(value: Any, keyword: str, path: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise AuditInputError("schema %s at %s must be a non-negative integer" % (keyword, path or "/"))
    return value


# This is deliberately a small, explicit JSON Schema subset. In particular, composition
# and references are rejected rather than ignored. The annotation keywords are inert but
# recognized so that an ordinary schema declaration or human-readable title is portable.
SUPPORTED_SCHEMA_KEYWORDS = frozenset(
    (
        "$schema",
        "$id",
        "title",
        "description",
        "type",
        "const",
        "enum",
        "properties",
        "required",
        "additionalProperties",
        "minProperties",
        "maxProperties",
        "items",
        "minItems",
        "maxItems",
        "uniqueItems",
        "minLength",
        "maxLength",
        "pattern",
        "minimum",
        "maximum",
        "exclusiveMinimum",
        "exclusiveMaximum",
    )
)


def guard_supported_schema(schema: Any, schema_path: str) -> None:
    """Recursively reject keywords this auditor cannot evaluate, even on dead branches."""
    if not isinstance(schema, dict):
        raise AuditInputError("schema at %s must be an object" % (schema_path or "/"))
    unknown = sorted(set(schema) - SUPPORTED_SCHEMA_KEYWORDS)
    if unknown:
        raise AuditInputError(
            "unsupported JSON Schema keyword(s) %s at %s; supported subset: %s"
            % (
                ", ".join(repr(keyword) for keyword in unknown),
                schema_path or "#",
                ", ".join(sorted(SUPPORTED_SCHEMA_KEYWORDS)),
            )
        )
    if "type" in schema:
        declared_type = schema["type"]
        declared_types = [declared_type] if isinstance(declared_type, str) else declared_type
        supported_types = {"object", "array", "string", "boolean", "null", "number", "integer"}
        if (
            not isinstance(declared_types, list)
            or not declared_types
            or any(not isinstance(item, str) or item not in supported_types for item in declared_types)
        ):
            raise AuditInputError(
                "schema type at %s must be a supported type name or non-empty array of them"
                % (schema_path or "#")
            )
    properties = schema.get("properties", {})
    if not isinstance(properties, dict):
        raise AuditInputError("schema properties at %s must be an object" % (schema_path or "#"))
    for key, child in properties.items():
        if not isinstance(key, str):
            raise AuditInputError("schema property names at %s must be strings" % (schema_path or "#"))
        guard_supported_schema(
            child, schema_path + "/properties/" + escape_pointer(key)
        )
    if "items" in schema:
        guard_supported_schema(schema["items"], schema_path + "/items")
    additional = schema.get("additionalProperties", True)
    if isinstance(additional, dict):
        guard_supported_schema(additional, schema_path + "/additionalProperties")
    elif not isinstance(additional, bool):
        raise AuditInputError(
            "additionalProperties at %s must be boolean or a schema object" % (schema_path or "#")
        )


def validate_schema(
    value: Any, schema: Any, path: str, schema_path: str, audit: Audit
) -> None:
    # Call the recursive guard here as well as at intake so this public helper cannot
    # silently accept an unsupported nested schema when reused by another entry point.
    guard_supported_schema(schema, schema_path)

    if "const" in schema and not json_equal(value, schema["const"]):
        audit.structural(
            "CONST_MISMATCH", path, "Expected constant %r; found %r." % (schema["const"], value)
        )
    if "enum" in schema:
        options = schema["enum"]
        if not isinstance(options, list) or not options:
            raise AuditInputError("schema enum at %s must be a non-empty array" % schema_path)
        if not any(json_equal(value, option) for option in options):
            audit.structural(
                "ENUM_MISMATCH", path, "Value %r is not one of %r." % (value, options)
            )

    if "type" in schema:
        expected = schema["type"]
        expected_types = [expected] if isinstance(expected, str) else expected
        if not isinstance(expected_types, list) or not expected_types:
            raise AuditInputError("schema type at %s must be a string or non-empty array" % schema_path)
        if not any(matches_type(value, item) for item in expected_types):
            audit.structural(
                "TYPE_MISMATCH",
                path,
                "Expected type %r; found JSON value %r." % (expected, value),
            )
            return

    if isinstance(value, dict):
        required = schema.get("required", [])
        if not isinstance(required, list) or any(not isinstance(key, str) for key in required):
            raise AuditInputError("schema required at %s must be an array of strings" % schema_path)
        for key in required:
            if key not in value:
                audit.structural(
                    "REQUIRED_MISSING", path, "Required property %r is missing." % key
                )
        properties = schema.get("properties", {})
        if not isinstance(properties, dict):
            raise AuditInputError("schema properties at %s must be an object" % schema_path)
        # This task requires an explicit value for every declared property. JSON Schema's
        # `required` list is therefore a minimum, not permission to omit other declarations.
        for key in properties:
            if key not in value:
                audit.structural(
                    "DECLARED_PROPERTY_MISSING",
                    path + "/" + escape_pointer(key),
                    "Declared property %r is missing; this task requires every declared property."
                    % key,
                )
        additional = schema.get("additionalProperties", True)
        for key, child in value.items():
            child_path = path + "/" + escape_pointer(key)
            if key in properties:
                validate_schema(
                    child,
                    properties[key],
                    child_path,
                    schema_path + "/properties/" + escape_pointer(key),
                    audit,
                )
            elif additional is False:
                audit.structural(
                    "ADDITIONAL_PROPERTY",
                    child_path,
                    "Property is forbidden by additionalProperties: false.",
                )
            elif isinstance(additional, dict):
                validate_schema(
                    child,
                    additional,
                    child_path,
                    schema_path + "/additionalProperties",
                    audit,
                )
            elif additional is not True:
                raise AuditInputError(
                    "additionalProperties at %s must be boolean or a schema object" % schema_path
                )
        for keyword in ("minProperties", "maxProperties"):
            if keyword in schema:
                limit = require_nonnegative_int(schema[keyword], keyword, schema_path)
                if keyword == "minProperties" and len(value) < limit:
                    audit.structural("MIN_PROPERTIES", path, "Expected at least %d properties." % limit)
                if keyword == "maxProperties" and len(value) > limit:
                    audit.structural("MAX_PROPERTIES", path, "Expected at most %d properties." % limit)

    if isinstance(value, list):
        if "minItems" in schema:
            limit = require_nonnegative_int(schema["minItems"], "minItems", schema_path)
            if len(value) < limit:
                audit.structural(
                    "MIN_ITEMS", path, "Expected at least %d items; found %d." % (limit, len(value))
                )
        if "maxItems" in schema:
            limit = require_nonnegative_int(schema["maxItems"], "maxItems", schema_path)
            if len(value) > limit:
                audit.structural(
                    "MAX_ITEMS", path, "Expected at most %d items; found %d." % (limit, len(value))
                )
        if schema.get("uniqueItems") is True:
            serialized = [json.dumps(item, sort_keys=True, ensure_ascii=False) for item in value]
            if len(set(serialized)) != len(serialized):
                audit.structural("UNIQUE_ITEMS", path, "Array items must be unique.")
        if "items" in schema:
            for index, child in enumerate(value):
                validate_schema(
                    child,
                    schema["items"],
                    path + "/" + str(index),
                    schema_path + "/items",
                    audit,
                )

    if isinstance(value, str):
        if "minLength" in schema:
            limit = require_nonnegative_int(schema["minLength"], "minLength", schema_path)
            if len(value) < limit:
                audit.structural(
                    "MIN_LENGTH", path, "Expected at least %d characters; found %d." % (limit, len(value))
                )
        if "maxLength" in schema:
            limit = require_nonnegative_int(schema["maxLength"], "maxLength", schema_path)
            if len(value) > limit:
                audit.structural(
                    "MAX_LENGTH", path, "Expected at most %d characters; found %d." % (limit, len(value))
                )
        if "pattern" in schema:
            try:
                matched = re.search(schema["pattern"], value)
            except (re.error, TypeError) as exc:
                raise AuditInputError("invalid schema pattern at %s: %s" % (schema_path, exc))
            if not matched:
                audit.structural("PATTERN_MISMATCH", path, "String does not match required pattern.")

    if isinstance(value, (int, float)) and not isinstance(value, bool):
        for keyword, comparator, code, wording in (
            ("minimum", lambda a, b: a >= b, "MINIMUM", "at least"),
            ("maximum", lambda a, b: a <= b, "MAXIMUM", "at most"),
        ):
            if keyword in schema:
                limit = require_number(schema[keyword], keyword, schema_path)
                if not comparator(value, limit):
                    audit.structural(
                        code, path, "Expected value %s %s; found %s." % (wording, limit, value)
                    )
        for keyword, comparator, code, wording in (
            ("exclusiveMinimum", lambda a, b: a > b, "EXCLUSIVE_MINIMUM", "greater than"),
            ("exclusiveMaximum", lambda a, b: a < b, "EXCLUSIVE_MAXIMUM", "less than"),
        ):
            if keyword in schema:
                limit = require_number(schema[keyword], keyword, schema_path)
                if not comparator(value, limit):
                    audit.structural(
                        code, path, "Expected value %s %s; found %s." % (wording, limit, value)
                    )


def extract_task_schema(text: str) -> Optional[Dict[str, Any]]:
    blocks = re.findall(r"```(?:json|JSON)\s*(\{.*?\})\s*```", text, flags=re.DOTALL)
    for block in blocks:
        try:
            candidate = json.loads(block, object_pairs_hook=unique_object)
        except (json.JSONDecodeError, DuplicateKeyError) as exc:
            raise AuditInputError("malformed JSON code block in task: %s" % exc)
        if isinstance(candidate, dict) and (
            "properties" in candidate or "required" in candidate
        ) and "type" in candidate:
            return candidate
    return None


def index_sources(raw_sources: Iterable[Tuple[Path, Any]]) -> Dict[str, Dict[str, str]]:
    indexed: Dict[str, Dict[str, str]] = {}
    for path, raw in raw_sources:
        if not isinstance(raw, dict) or not isinstance(raw.get("source_id"), str):
            raise AuditInputError("source index at %s needs a string source_id" % path)
        source_id = raw["source_id"]
        if source_id in indexed:
            raise AuditInputError("duplicate source_id across --source inputs: %s" % source_id)
        anchors: Dict[str, str] = {}
        if "text" in raw:
            if not isinstance(raw["text"], str):
                raise AuditInputError("source text at %s must be a string" % path)
            anchors["FULL"] = raw["text"]
        if "sections" in raw:
            sections = raw["sections"]
            if not isinstance(sections, list):
                raise AuditInputError("source sections at %s must be an array" % path)
            for index, section in enumerate(sections):
                if not isinstance(section, dict):
                    raise AuditInputError("source section %d at %s must be an object" % (index, path))
                anchor = section.get("anchor")
                text = section.get("text")
                if not isinstance(anchor, str) or not anchor or not isinstance(text, str):
                    raise AuditInputError(
                        "source section %d at %s needs non-empty anchor and string text" % (index, path)
                    )
                if anchor in anchors:
                    raise AuditInputError("duplicate anchor %s in source %s" % (anchor, source_id))
                anchors[anchor] = text
        if not anchors:
            raise AuditInputError("source %s at %s has neither text nor sections" % (source_id, path))
        indexed[source_id] = anchors
    return indexed


PLACEHOLDER_RE = re.compile(
    r"\b(?:TBD|TODO|FIXME|XXX|PLACEHOLDER|LOREM\s+IPSUM)\b|<answer>|\[insert[^\]]*\]|answer\s+here",
    flags=re.IGNORECASE,
)
CITATION_FIRST_RE = re.compile(r"^\s*(?:\[[^\]]+\]|【[^】]+】|source\s*:|see\s+(?:source|table|figure)\b)", re.IGNORECASE)


def require_matrix(plan: Dict[str, Any]) -> List[Dict[str, Any]]:
    matrix = plan.get("answer_matrix")
    if not isinstance(matrix, dict) or not isinstance(matrix.get("items"), list):
        raise AuditInputError("plan.answer_matrix.items must be an array")
    items = matrix["items"]
    if not items:
        raise AuditInputError("plan.answer_matrix.items must not be empty")
    required = (
        "item_id",
        "question",
        "answer_path",
        "status_path",
        "evidence_path",
        "checked_scope_path",
        "evidence_role",
        "checked_source_scope",
        "required_answer_terms",
        "forbidden_generalizations",
    )
    seen = set()
    for index, row in enumerate(items):
        if not isinstance(row, dict):
            raise AuditInputError("answer matrix row %d must be an object" % index)
        for key in required:
            if key not in row:
                raise AuditInputError("answer matrix row %d lacks %s" % (index, key))
        for key in ("item_id", "question", "answer_path", "evidence_role"):
            if not isinstance(row[key], str) or not row[key]:
                raise AuditInputError("answer matrix row %d field %s must be non-empty string" % (index, key))
        for key in ("status_path", "evidence_path", "checked_scope_path"):
            if row[key] is not None and (not isinstance(row[key], str) or not row[key]):
                raise AuditInputError(
                    "answer matrix row %d field %s must be null or a non-empty JSON Pointer"
                    % (index, key)
                )
        for key in ("answer_path", "status_path", "evidence_path", "checked_scope_path"):
            if row[key] is not None:
                pointer_tokens(row[key])
        if "inventory_gap" in row and (
            not isinstance(row["inventory_gap"], str) or not row["inventory_gap"].strip()
        ):
            raise AuditInputError(
                "answer matrix row %s inventory_gap must be a non-empty explanation"
                % row["item_id"]
            )
        if row["item_id"] in seen:
            raise AuditInputError("duplicate answer matrix item_id: %s" % row["item_id"])
        seen.add(row["item_id"])
        for key in ("required_answer_terms", "forbidden_generalizations", "checked_source_scope"):
            if not isinstance(row[key], list):
                raise AuditInputError("answer matrix row %s field %s must be an array" % (row["item_id"], key))
    return items


def validate_item_ids(plan: Dict[str, Any], result: Any, audit: Audit) -> None:
    contracts = plan.get("item_id_contracts", [])
    if not isinstance(contracts, list):
        raise AuditInputError("plan.item_id_contracts must be an array")
    for index, contract in enumerate(contracts):
        if not isinstance(contract, dict):
            raise AuditInputError("item_id_contracts[%d] must be an object" % index)
        for key in ("path", "id_property", "ids", "exact"):
            if key not in contract:
                raise AuditInputError("item_id_contracts[%d] lacks %s" % (index, key))
        path = contract["path"]
        id_property = contract["id_property"]
        expected = contract["ids"]
        if not isinstance(path, str) or not (id_property is None or isinstance(id_property, str)):
            raise AuditInputError("invalid path or id_property in item_id_contracts[%d]" % index)
        if not isinstance(expected, list) or any(not isinstance(item, str) for item in expected):
            raise AuditInputError("item_id_contracts[%d].ids must be an array of strings" % index)
        found, target = resolve_pointer(result, path)
        if not found:
            audit.structural("ITEM_ID_TARGET_MISSING", path, "Cannot check item IDs because target is missing.")
            continue
        actual: List[str] = []
        if isinstance(target, list):
            for item_index, item in enumerate(target):
                if not isinstance(item, dict) or id_property is None or not isinstance(item.get(id_property), str):
                    audit.structural(
                        "ITEM_ID_MISSING",
                        path + "/" + str(item_index),
                        "Array item lacks a string %r." % id_property,
                    )
                else:
                    actual.append(item[id_property])
        elif isinstance(target, dict):
            if id_property is None:
                actual = list(target.keys())
            elif isinstance(target.get(id_property), str):
                actual = [target[id_property]]
            else:
                audit.structural("ITEM_ID_MISSING", path, "Object lacks a string %r." % id_property)
        else:
            audit.structural("ITEM_ID_TARGET_TYPE", path, "Item ID target must be object or array.")
            continue
        duplicates = sorted({item for item in actual if actual.count(item) > 1})
        if duplicates:
            audit.structural("DUPLICATE_ITEM_ID", path, "Duplicate item IDs: %s." % duplicates)
        if contract["exact"] is True:
            if actual != expected:
                audit.structural(
                    "EXACT_ITEM_IDS",
                    path,
                    "Expected exact ordered IDs %r (count %d); found %r (count %d)."
                    % (expected, len(expected), actual, len(actual)),
                )
        else:
            missing = [item for item in expected if item not in actual]
            if missing:
                audit.structural("REQUIRED_ITEM_IDS", path, "Missing required item IDs: %r." % missing)


def audit_matrix(
    output_schema: Dict[str, Any],
    result: Dict[str, Any],
    matrix: List[Dict[str, Any]],
    sources: Dict[str, Dict[str, str]],
    audit: Audit,
) -> None:
    # Every declared answer object needs a matrix row. Result keys named only in `required`
    # are not sufficient because the task also requires every declared property to be present.
    properties = output_schema.get("properties", {})
    answer_paths = {row["answer_path"] for row in matrix}
    if isinstance(properties, dict):
        for key, child_schema in properties.items():
            if isinstance(child_schema, dict) and isinstance(child_schema.get("properties"), dict):
                if "answer" in child_schema["properties"]:
                    expected_path = "/" + escape_pointer(key) + "/answer"
                    if expected_path not in answer_paths:
                        audit.semantic(
                            "UNMATRIXED_REQUIRED_QUESTION",
                            expected_path,
                            "Declared answer field has no answer-matrix row.",
                        )

    for row_index, row in enumerate(matrix):
        item_id = row["item_id"]
        answer_path = row["answer_path"]

        def resolve_result_or_sidecar(
            pointer_key: str, sidecar_key: str
        ) -> Tuple[bool, Any, str]:
            pointer = row[pointer_key]
            if pointer is None:
                sidecar_path = "/answer_matrix/items/%d/%s" % (row_index, sidecar_key)
                if sidecar_key in row:
                    return True, row[sidecar_key], sidecar_path
                return False, None, sidecar_path
            found, value = resolve_pointer(result, pointer)
            return found, value, pointer

        found_answer, answer = resolve_pointer(result, answer_path)
        found_status, status, status_path = resolve_result_or_sidecar("status_path", "answer_status")
        found_evidence, evidence, evidence_path = resolve_result_or_sidecar("evidence_path", "evidence")
        found_scope, checked_scope, checked_scope_path = resolve_result_or_sidecar(
            "checked_scope_path", "checked_scope"
        )

        if not found_status or status not in ("answered", "not_reported", "unreadable", "missing"):
            audit.semantic(
                "STATUS_INVALID", status_path, "%s needs a valid answer status." % item_id
            )
            status = None

        if not found_answer or not isinstance(answer, str) or not answer.strip():
            audit.semantic("UNANSWERED", answer_path, "%s has no direct answer." % item_id)
            answer = ""
        else:
            if PLACEHOLDER_RE.search(answer):
                audit.semantic(
                    "PLACEHOLDER_ANSWER", answer_path, "%s contains placeholder language." % item_id
                )
            if CITATION_FIRST_RE.search(answer):
                audit.semantic(
                    "CITATION_BEFORE_ANSWER",
                    answer_path,
                    "%s appears to begin with a citation rather than a direct answer." % item_id,
                )
            if status == "answered" and answer.strip().casefold().startswith(
                ("not reported", "not_reported", "unreadable", "missing source")
            ):
                audit.semantic(
                    "STATUS_ANSWER_MISMATCH",
                    answer_path,
                    "%s is marked answered but its wording indicates absence." % item_id,
                )

        lowered = answer.casefold()
        for term in row["required_answer_terms"]:
            if not isinstance(term, str) or not term:
                raise AuditInputError("required_answer_terms for %s must contain non-empty strings" % item_id)
            if term.casefold() not in lowered:
                audit.semantic(
                    "REQUIRED_ANSWER_TERM_MISSING",
                    answer_path,
                    "%s lacks required qualifier/comparator/unit/negation snippet %r. Human review required."
                    % (item_id, term),
                )
        for phrase in row["forbidden_generalizations"]:
            if not isinstance(phrase, str) or not phrase:
                raise AuditInputError("forbidden_generalizations for %s must contain non-empty strings" % item_id)
            if phrase.casefold() in lowered:
                audit.semantic(
                    "UNSUPPORTED_GENERALIZATION_RISK",
                    answer_path,
                    "%s contains review-trigger phrase %r." % (item_id, phrase),
                )

        if not found_scope or not isinstance(checked_scope, str) or not checked_scope.strip():
            code = "CHECKED_SCOPE_REQUIRED" if status in ("not_reported", "unreadable", "missing") else "CHECKED_SCOPE_MISSING"
            audit.semantic(
                code,
                checked_scope_path,
                "%s requires a non-empty account of the actual checked scope." % item_id,
            )
            checked_scope = ""

        declared_source_scope = row["checked_source_scope"]
        if not declared_source_scope:
            if status == "missing":
                if not row.get("inventory_gap"):
                    audit.semantic(
                        "INVENTORY_GAP_REQUIRED",
                        "/answer_matrix/items/%d/inventory_gap" % row_index,
                        "%s has an empty checked source scope; missing-source status requires "
                        "an explicit inventory_gap explanation." % item_id,
                    )
            else:
                audit.semantic(
                    "CHECKED_SOURCE_SCOPE_REQUIRED",
                    "/answer_matrix/items/%d/checked_source_scope" % row_index,
                    "%s may not have an empty checked source scope unless its status is missing "
                    "and an inventory_gap is documented." % item_id,
                )

        declared_source_anchors = set()
        for scope_index, scope in enumerate(declared_source_scope):
            if not isinstance(scope, dict) or not isinstance(scope.get("source_id"), str) or not isinstance(scope.get("anchors"), list):
                raise AuditInputError("invalid checked_source_scope[%d] for %s" % (scope_index, item_id))
            source_id = scope["source_id"]
            if source_id not in sources:
                audit.semantic(
                    "CHECKED_SOURCE_UNAVAILABLE",
                    checked_scope_path,
                    "%s declares unavailable source %s in checked scope." % (item_id, source_id),
                )
                continue
            for anchor in scope["anchors"]:
                if not isinstance(anchor, str) or not anchor:
                    raise AuditInputError("invalid checked anchor for %s" % item_id)
                declared_source_anchors.add((source_id, anchor))
                if anchor not in sources[source_id]:
                    audit.semantic(
                        "CHECKED_ANCHOR_UNKNOWN",
                        checked_scope_path,
                        "%s declares unknown anchor %s/%s." % (item_id, source_id, anchor),
                    )
                if anchor.casefold() not in checked_scope.casefold():
                    audit.semantic(
                        "CHECKED_SCOPE_ANCHOR_NOT_DOCUMENTED",
                        checked_scope_path,
                        "%s checked_scope does not document declared anchor %s/%s."
                        % (item_id, source_id, anchor),
                    )

        if status == "answered":
            if not found_evidence or not isinstance(evidence, list) or not evidence:
                audit.semantic(
                    "ANSWERED_EVIDENCE_MISSING",
                    evidence_path,
                    "%s is answered but has no evidence items to review." % item_id,
                )
                evidence = []
        elif status in ("not_reported", "unreadable", "missing"):
            # Deliberately no non-empty evidence requirement for absence states.
            if not found_evidence or not isinstance(evidence, list):
                evidence = []
            if not evidence and row["evidence_path"] is not None:
                evidence_schema = resolve_schema_pointer(output_schema, row["evidence_path"])
                if isinstance(evidence_schema, dict):
                    minimum = evidence_schema.get("minItems", 0)
                    if isinstance(minimum, int) and not isinstance(minimum, bool) and minimum > 0:
                        audit.semantic(
                            "ABSENCE_EVIDENCE_CONTRACT_CONFLICT",
                            evidence_path,
                            "%s honestly has no evidence, but schema minItems=%d. Keep checked_scope and flag the conflict; never fabricate evidence."
                            % (item_id, minimum),
                        )

        if not isinstance(evidence, list):
            evidence = []
        for evidence_index, item in enumerate(evidence):
            item_path = evidence_path + "/" + str(evidence_index)
            if not isinstance(item, dict):
                audit.semantic("EVIDENCE_NOT_OBJECT", item_path, "Evidence item must be an object.")
                continue
            source_id = item.get("source_id")
            anchor = item.get("anchor")
            quote = item.get("quote")
            if not isinstance(source_id, str) or source_id not in sources:
                audit.semantic(
                    "EVIDENCE_SOURCE_UNKNOWN", item_path, "Evidence source_id is unknown: %r." % source_id
                )
                continue
            if not isinstance(anchor, str) or anchor not in sources[source_id]:
                audit.semantic(
                    "EVIDENCE_ANCHOR_UNKNOWN",
                    item_path,
                    "Evidence anchor %r is unknown at source %s." % (anchor, source_id),
                )
                continue
            if (source_id, anchor) not in declared_source_anchors:
                audit.semantic(
                    "EVIDENCE_OUTSIDE_CHECKED_SCOPE",
                    item_path,
                    "Evidence pair %s/%s is outside the declared checked_source_scope %s; "
                    "a valid quote outside that scope is not automatic support."
                    % (source_id, anchor, sorted(declared_source_anchors)),
                )
            if not isinstance(quote, str) or not quote:
                audit.semantic("EVIDENCE_QUOTE_EMPTY", item_path + "/quote", "Quote must be non-empty.")
            elif quote not in sources[source_id][anchor]:
                audit.semantic(
                    "QUOTE_NOT_AT_ANCHOR",
                    item_path + "/quote",
                    "Quote is not an exact substring of %s/%s; entailment cannot be reviewed mechanically."
                    % (source_id, anchor),
                )
            expected_role = row["evidence_role"]
            if expected_role != "no_evidence_expected" and item.get("evidence_role") != expected_role:
                audit.semantic(
                    "EVIDENCE_ROLE_DRIFT",
                    item_path + "/evidence_role",
                    "%s matrix expects evidence role %r; found %r."
                    % (item_id, expected_role, item.get("evidence_role")),
                )


def portable_path(value: str) -> str:
    """Keep machine-local absolute paths out of shareable audit artifacts."""
    try:
        return os.path.relpath(str(Path(value).resolve()), str(Path.cwd().resolve()))
    except (OSError, ValueError):
        return str(value)


def make_report(
    args: argparse.Namespace,
    audit: Audit,
    matrix_count: int,
    synthetic: bool,
) -> Dict[str, Any]:
    structural_count = audit.count("STRUCTURAL")
    semantic_count = audit.count("SEMANTIC")
    structural_status = "FAIL" if structural_count else "PASS"
    semantic_status = "NEEDS_HUMAN_REVIEW" if semantic_count else "NOT_AUTO_VERIFIED"
    return {
        "label": "SYNTHETIC audit" if synthetic else "Semantic coverage audit",
        "synthetic": synthetic,
        "structural_status": structural_status,
        "semantic_status": semantic_status,
        "overall_status": (
            "FAIL"
            if structural_count
            else "NEEDS_HUMAN_REVIEW"
            if semantic_count
            else "STRUCTURAL_PASS_SEMANTICS_NOT_AUTO_VERIFIED"
        ),
        "truth_notice": (
            "Mechanical checks do not establish scientific truth, complete source coverage, "
            "or whole-answer entailment. Exact quote retrieval and required-term presence "
            "still require human semantic review."
        ),
        "summary": {
            "matrix_items": matrix_count,
            "structural_findings": structural_count,
            "semantic_findings": semantic_count,
        },
        "findings": audit.findings,
        "paths": {
            "plan": portable_path(args.plan),
            "result": portable_path(args.result),
            "case": portable_path(args.case),
            "task": portable_path(args.task) if args.task else None,
            "sources": [portable_path(item) for item in args.source],
            "report": portable_path(args.report),
        },
    }


def parse_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Audit answer semantics and output_schema without claiming automatic truth."
    )
    parser.add_argument("--plan", required=True, help="Plan JSON containing output_schema and answer_matrix")
    parser.add_argument("--result", required=True, help="Actual contract-native result JSON")
    parser.add_argument(
        "--case",
        required=True,
        help="Actual case JSON containing case_id and, when supplied, authoritative output_contract",
    )
    parser.add_argument("--task", help="Optional actual task Markdown with fenced output_contract JSON")
    parser.add_argument(
        "--source",
        required=True,
        action="append",
        help="Actual source index JSON; repeat for multiple sources",
    )
    parser.add_argument("--report", required=True, help="Audit report JSON output path")
    return parser.parse_args(argv)


def run(args: argparse.Namespace) -> Tuple[Dict[str, Any], int]:
    plan_path = Path(args.plan)
    result_path = Path(args.result)
    case_path = Path(args.case)
    plan = load_json(plan_path, "plan")
    result = load_json(result_path, "result")
    case = load_json(case_path, "case")
    if not isinstance(plan, dict) or not isinstance(plan.get("output_schema"), dict):
        raise AuditInputError("plan must be an object with object output_schema")
    if not isinstance(result, dict):
        raise AuditInputError("result must be a JSON object")
    if not isinstance(case, dict) or not isinstance(case.get("case_id"), str):
        raise AuditInputError("case must be an object with string case_id")
    case_has_contract = "output_contract" in case
    if case_has_contract and not isinstance(case["output_contract"], dict):
        raise AuditInputError("actual case.output_contract must be a JSON object when present")

    plan_schema = plan["output_schema"]
    case_schema = case.get("output_contract")
    guard_supported_schema(plan_schema, "plan#/output_schema")
    if case_has_contract:
        guard_supported_schema(case_schema, "case#/output_contract")

    task_schema = None
    if args.task:
        task_path = Path(args.task)
        try:
            task_text = task_path.read_text(encoding="utf-8")
        except (OSError, UnicodeError) as exc:
            raise AuditInputError("cannot read task at %s: %s" % (task_path, exc))
        task_schema = extract_task_schema(task_text)
        if task_schema is not None:
            guard_supported_schema(task_schema, "task#")

    # The actual case is authoritative whenever the key exists (including malformed null,
    # which was rejected above). Only a genuinely absent case contract permits task fallback.
    if case_has_contract:
        primary_label, primary_schema = "case#/output_contract", case_schema
    elif task_schema is not None:
        primary_label, primary_schema = "task#", task_schema
    else:
        primary_label, primary_schema = "plan#/output_schema", plan_schema

    matrix = require_matrix(plan)
    raw_sources = [(Path(path), load_json(Path(path), "source")) for path in args.source]
    sources = index_sources(raw_sources)
    audit = Audit()

    if plan.get("case_id") != case["case_id"]:
        audit.structural(
            "PLAN_CASE_ID_DRIFT", "/case_id", "Plan case_id does not match actual case.json."
        )
    if result.get("case_id") != case["case_id"]:
        audit.structural(
            "RESULT_CASE_ID_DRIFT", "/case_id", "Result case_id does not match actual case.json."
        )

    if case_has_contract and plan_schema != case_schema:
        audit.structural(
            "CONTRACT_DRIFT",
            "/output_schema",
            "Plan output_schema differs from authoritative actual case.output_contract.",
        )
    if case_has_contract and task_schema is not None and task_schema != case_schema:
        audit.structural(
            "CONTRACT_DRIFT",
            "",
            "Fenced task output_contract differs from authoritative actual case.output_contract.",
        )
    if not case_has_contract and task_schema is not None and task_schema != plan_schema:
        audit.structural(
            "CONTRACT_DRIFT",
            "",
            "Task output_contract and plan.output_schema differ; both are reported and validated.",
        )
    if args.task and task_schema is None:
        audit.semantic(
            "TASK_SCHEMA_NOT_FOUND",
            "",
            "No fenced output schema found; %s was used." % primary_label,
        )

    # Validate every supplied schema (deduplicating exact copies), while reporting which one
    # is authoritative. A drift can never be hidden by validating only the easier variant.
    supplied_schemas = [("plan#/output_schema", plan_schema)]
    if case_has_contract:
        supplied_schemas.append(("case#/output_contract", case_schema))
    if task_schema is not None:
        supplied_schemas.append(("task#", task_schema))
    supplied_schemas.sort(key=lambda pair: pair[0] != primary_label)
    validated_schemas: List[Dict[str, Any]] = []
    for label, schema in supplied_schemas:
        if not any(schema == previous for previous in validated_schemas):
            validate_schema(result, schema, "", label, audit)
            validated_schemas.append(schema)

    validate_item_ids(plan, result, audit)
    audit_matrix(primary_schema, result, matrix, sources, audit)
    report = make_report(args, audit, len(matrix), bool(plan.get("synthetic", False)))
    report["contract_authority"] = primary_label
    report["validated_schema_count"] = len(validated_schemas)
    write_json(Path(args.report), report)
    return report, 1 if audit.count("STRUCTURAL") else 0


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = parse_args(argv)
    try:
        report, exit_code = run(args)
    except AuditInputError as exc:
        failure = {
            "structural_status": "FAIL",
            "semantic_status": "NEEDS_HUMAN_REVIEW",
            "overall_status": "MALFORMED_INPUT",
            "error": str(exc),
            "truth_notice": "Malformed input was not audited; no truth or completeness claim is made.",
            "paths": {
                "plan": portable_path(args.plan),
                "result": portable_path(args.result),
                "case": portable_path(args.case),
                "task": portable_path(args.task) if args.task else None,
                "sources": [portable_path(item) for item in args.source],
                "report": portable_path(args.report),
            },
        }
        try:
            write_json(Path(args.report), failure)
        except AuditInputError as write_exc:
            print(str(write_exc), file=sys.stderr)
        print("Malformed input: %s" % exc, file=sys.stderr)
        print("Report: %s" % Path(args.report).resolve(), file=sys.stderr)
        return 2
    print("Report: %s" % Path(args.report).resolve())
    print(
        "Structural: %s (%d findings); semantic: %s (%d findings)"
        % (
            report["structural_status"],
            report["summary"]["structural_findings"],
            report["semantic_status"],
            report["summary"]["semantic_findings"],
        )
    )
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
