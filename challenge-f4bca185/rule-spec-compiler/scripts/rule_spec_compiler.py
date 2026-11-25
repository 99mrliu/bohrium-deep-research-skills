#!/usr/bin/env python3
"""Deterministic, standard-library declarative rule-spec compiler and executor."""
from __future__ import annotations

import argparse
import csv
import copy
import decimal
import hashlib
import json
import math
import os
from pathlib import Path
import re
import sys
from typing import Any, Iterable

VERSION = "1.0.0"
MARKER_KEY = "artifact_marker"
FORMATS = ("records", "rows", "data", "items", "results", "samples", "examples",
           "extractions", "extraction_records", "observations", "measurements")
MISSING_DEFAULT: tuple[str, ...] = ()
REVIEW_COLUMNS = [
    "review_id", "code", "severity", "status", "row_key", "field",
    "rule_ids", "message", "source", "pointer",
]
BUILTIN_KINDS = {
    "trim_whitespace", "normalize_missing", "parse_number", "normalize_range",
    "convert_unit", "literal_map", "regex_replace", "validate_identity",
}
KIND_ALIASES = {
    "trim": "trim_whitespace", "strip": "trim_whitespace",
    "whitespace": "trim_whitespace", "missing": "normalize_missing",
    "missing_tokens": "normalize_missing", "numeric": "parse_number",
    "number": "parse_number", "range": "normalize_range",
    "unit": "convert_unit", "field_mapping": "rename_field",
    "rename": "rename_field", "map": "literal_map",
    "identity": "validate_identity",
}
UNIT_SCALE = {
    "mg": ("g", decimal.Decimal("0.001")),
    "g": ("g", decimal.Decimal("1")),
    "kg": ("g", decimal.Decimal("1000")),
    "ug": ("g", decimal.Decimal("0.000001")),
    "µg": ("g", decimal.Decimal("0.000001")),
    "μg": ("g", decimal.Decimal("0.000001")),
    "ng": ("g", decimal.Decimal("0.000000001")),
    "mm": ("m", decimal.Decimal("0.001")),
    "cm": ("m", decimal.Decimal("0.01")),
    "m": ("m", decimal.Decimal("1")),
    "km": ("m", decimal.Decimal("1000")),
    "um": ("m", decimal.Decimal("0.000001")),
    "µm": ("m", decimal.Decimal("0.000001")),
    "μm": ("m", decimal.Decimal("0.000001")),
    "nm": ("m", decimal.Decimal("0.000000001")),
    "nl": ("l", decimal.Decimal("0.000000001")),
    "ul": ("l", decimal.Decimal("0.000001")),
    "µl": ("l", decimal.Decimal("0.000001")),
    "μl": ("l", decimal.Decimal("0.000001")),
    "ml": ("l", decimal.Decimal("0.001")),
    "l": ("l", decimal.Decimal("1")),
    "cl": ("l", decimal.Decimal("0.01")),
    "dl": ("l", decimal.Decimal("0.1")),
    "mmol": ("mol", decimal.Decimal("0.001")),
    "umol": ("mol", decimal.Decimal("0.000001")),
    "µmol": ("mol", decimal.Decimal("0.000001")),
    "μmol": ("mol", decimal.Decimal("0.000001")),
    "mol": ("mol", decimal.Decimal("1")),
}
UNIT_ALIASES = {
    "liter": "l", "litre": "l", "liters": "l", "litres": "l",
    "gram": "g", "grams": "g", "meter": "m", "metre": "m",
}


def canonical(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def digest(value: Any) -> str:
    return hashlib.sha256(canonical(value).encode("utf-8")).hexdigest()


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def clean_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, str):
        if value.strip().lower() in {"nan", "+nan", "-nan", "infinity", "+infinity", "-infinity", "inf", "+inf", "-inf"}:
            raise ValueError("non-finite numeric tokens are not accepted")
        return value
    if isinstance(value, decimal.Decimal):
        if not value.is_finite():
            raise ValueError("non-finite decimal")
        return decimal_text(value)
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError("non-finite float")
        return decimal_text(decimal.Decimal(str(value)))
    if isinstance(value, (list, dict)):
        return canonical(value)
    return str(value)


def decimal_text(value: decimal.Decimal) -> str:
    if value == 0:
        return "0"
    text = format(value.normalize(), "f")
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return text


def safe_json(value: Any) -> Any:
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, decimal.Decimal):
        if not value.is_finite():
            return None
        return decimal_text(value)
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    if isinstance(value, dict):
        return {str(k): safe_json(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [safe_json(v) for v in value]
    return clean_text(value)


def deep_merge(base: Any, overlay: Any) -> Any:
    if isinstance(base, dict) and isinstance(overlay, dict):
        result = copy.deepcopy(base)
        for key, value in overlay.items():
            result[key] = deep_merge(result[key], value) if key in result else copy.deepcopy(value)
        return result
    return copy.deepcopy(overlay)


def pointer_token(value: str) -> str:
    return value.replace("~", "~0").replace("/", "~1")


def patch_parent(document: Any, pointer: str, create: bool) -> tuple[Any, str]:
    if not pointer.startswith("/"):
        raise ValueError("JSON Patch path must start with '/'")
    parts = pointer[1:].split("/")
    parts = [p.replace("~1", "/").replace("~0", "~") for p in parts]
    node = document
    for part in parts[:-1]:
        if isinstance(node, dict):
            if part not in node:
                if not create:
                    raise ValueError("missing JSON Patch parent: " + pointer)
                node[part] = {}
            node = node[part]
        elif isinstance(node, list):
            if part == "-":
                raise ValueError("'-' is only valid as final array segment")
            node = node[int(part)]
        else:
            raise ValueError("invalid JSON Patch parent: " + pointer)
    return node, parts[-1]


def apply_json_patch(document: Any, operations: list[Any]) -> Any:
    result = copy.deepcopy(document)
    for operation in operations:
        if not isinstance(operation, dict) or operation.get("op") not in {"add", "replace", "remove"}:
            raise ValueError("only add, replace, and remove JSON Patch operations are supported")
        op, path = operation["op"], operation.get("path", "")
        if op == "add" and "value" not in operation:
            raise ValueError("add operation requires value")
        if op == "replace" and "value" not in operation:
            raise ValueError("replace operation requires value")
        if path == "":
            if op == "remove":
                result = None
            else:
                result = copy.deepcopy(operation["value"])
            continue
        parent, key = patch_parent(result, path, op == "add")
        if isinstance(parent, list):
            if key == "-" and op == "add":
                parent.append(copy.deepcopy(operation.get("value")))
                continue
            index = int(key)
            if op == "remove":
                del parent[index]
            elif op == "replace":
                parent[index] = copy.deepcopy(operation["value"])
            else:
                parent.insert(index, copy.deepcopy(operation["value"]))
        elif isinstance(parent, dict):
            if op == "remove":
                if key not in parent:
                    raise ValueError("remove path does not exist: " + path)
                del parent[key]
            else:
                if op == "replace" and key not in parent:
                    raise ValueError("replace path does not exist: " + path)
                parent[key] = copy.deepcopy(operation["value"])
        else:
            raise ValueError("invalid JSON Patch target: " + path)
    return result


def read_json(path: Path) -> Any:
    raw = path.read_bytes()
    text = raw.decode("utf-8-sig")

    def reject_constant(token: str) -> None:
        raise ValueError("non-finite JSON number: " + token)

    return json.loads(text, parse_constant=reject_constant)


def display_path(path: Path, root: Path) -> str:
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except (ValueError, OSError):
        return path.name


def atomic_bytes(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_bytes(data)
    os.replace(temporary, path)


def atomic_text(path: Path, text: str) -> None:
    atomic_bytes(path, text.encode("utf-8"))


def write_json(path: Path, value: Any) -> None:
    atomic_text(path, canonical(safe_json(value)) + "\n")


def write_csv(path: Path, columns: list[str], rows: Iterable[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    with temporary.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns, extrasaction="ignore", lineterminator="\n")
        writer.writeheader()
        for row in rows:
            writer.writerow({column: clean_text(row.get(column, "")) for column in columns})
    os.replace(temporary, path)


class RulesEngine:
    def __init__(self) -> None:
        self.review: list[dict[str, Any]] = []
        self.changes: list[dict[str, Any]] = []
        self.review_seen: set[str] = set()
        self.change_sequence = 0
        self.marker = ""
        self.identity_review_done: set[str] = set()

    def add_review(self, code: str, message: str, *, severity: str = "error",
                   row_key: str = "", field: str = "", rule_ids: Iterable[str] = (),
                   source: str = "", pointer: str = "", status: str = "open") -> None:
        material = [code, severity, row_key, field, sorted(rule_ids), message, source, pointer]
        review_id = "Q-" + digest(material)[:16]
        if review_id in self.review_seen:
            return
        self.review_seen.add(review_id)
        self.review.append({
            "review_id": review_id, "code": code, "severity": severity,
            "status": status, "row_key": row_key, "field": field,
            "rule_ids": list(rule_ids), "message": message,
            "source": source, "pointer": pointer,
        })

    def add_change(self, rule: dict[str, Any], row: dict[str, Any], row_key: str,
                   field: str, before: Any, after: Any) -> None:
        self.change_sequence += 1
        record = {
            "sequence": self.change_sequence, "rule_id": rule["rule_id"],
            "row": row.get("__row_number"), "row_key": row_key, "field": field,
            "before": clean_text(before), "after": clean_text(after),
            "source": row.get("__source", ""),
            "provenance": rule.get("provenance", []),
        }
        if self.marker:
            record[MARKER_KEY] = self.marker
        self.changes.append(record)

    def actionable(self) -> bool:
        return any(item["severity"] in {"error", "warning"} and item["status"] == "open" for item in self.review)


def spec_items(value: Any, pointer: str, source: str) -> list[tuple[dict[str, Any], str, str]]:
    if value is None:
        return []
    if isinstance(value, dict) and "rules" in value and len(value) >= 1:
        value = value["rules"]
        pointer += "/rules"
    found: list[tuple[dict[str, Any], str, str]] = []
    if isinstance(value, list):
        for index, item in enumerate(value):
            if isinstance(item, dict):
                found.append((copy.deepcopy(item), source, pointer + "/" + str(index)))
    elif isinstance(value, dict):
        # A single typed rule, or an id -> rule mapping.
        if any(key in value for key in ("type", "kind", "rule", "operator")):
            found.append((copy.deepcopy(value), source, pointer))
        else:
            for key in sorted(value):
                item = value[key]
                if isinstance(item, dict):
                    item = copy.deepcopy(item)
                    item.setdefault("id", key)
                    found.append((item, source, pointer + "/" + pointer_token(key)))
    return found


def field_list(value: Any) -> list[str]:
    if isinstance(value, str):
        return [part.strip() for part in re.split(r"[,，]", value) if part.strip()]
    if isinstance(value, list):
        return [str(part) for part in value if isinstance(part, (str, int))]
    return []


def discover_task_specs(text: str, source: str) -> list[tuple[dict[str, Any], str, str]]:
    found: list[tuple[dict[str, Any], str, str]] = []
    # Explicit fenced rule-spec JSON is the preferred task.md representation.
    pattern = re.compile(r"```(?:json[ \t]+)?(?:rule-spec|rules)[ \t]*\n(.*?)```", re.I | re.S)
    for match in pattern.finditer(text):
        line = text.count("\n", 0, match.start()) + 1
        try:
            value = json.loads(match.group(1), parse_constant=lambda x: (_ for _ in ()).throw(ValueError(x)))
            found.extend(spec_items(value, "#L" + str(line), source))
        except (ValueError, json.JSONDecodeError):
            found.append(({"type": "invalid_task_rule_spec", "enabled": False}, source, "#L" + str(line)))
    directives = {
        "missing tokens": "missing_tokens", "missing values": "missing_tokens",
        "缺失标记": "missing_tokens", "缺失值标记": "missing_tokens",
        "numeric fields": "numeric_fields", "数值字段": "numeric_fields",
        "range fields": "range_fields", "范围字段": "range_fields",
        "identity keys": "identity_keys", "row identity": "identity_keys",
        "行标识": "identity_keys", "主键": "identity_keys",
    }
    for number, line in enumerate(text.splitlines(), 1):
        match = re.match(r"^\s*(?:[-*]\s*)?([^:：]{2,40})\s*[:：]\s*(.*?)\s*$", line)
        if not match:
            continue
        label = match.group(1).strip().lower().lstrip("# ").strip()
        value = match.group(2).strip()
        if label in directives:
            key = directives[label]
            tokens = [v.strip().strip("'\"") for v in re.split(r"[,，]", value) if v.strip()]
            found.append(({key: tokens}, source, "#L" + str(number)))
        else:
            unit = re.match(r"^(?:unit target|单位目标)\s+([^=]+)\s*=\s*(\S+)$", label + ": " + value, re.I)
            # Unit target is also accepted in the conventional "unit target: field = unit" form.
            unit = re.match(r"^(?:unit target|单位目标)\s*[:：]?\s*([^=]+)\s*=\s*(\S+)$", match.group(1) + ": " + value, re.I)
            if unit:
                found.append(({"type": "convert_unit", "field": unit.group(1).strip(),
                               "target": unit.group(2).strip()}, source, "#L" + str(number)))
            mapping = re.match(r"^(?:field mapping|字段映射)\s*[:：]?\s*(\S+)\s*(?:->|=>|→)\s*(\S+)$", match.group(1) + ": " + value, re.I)
            if mapping:
                found.append(({"type": "rename_field", "source": mapping.group(1),
                               "target": mapping.group(2)}, source, "#L" + str(number)))
    return found


def case_convenience(case: dict[str, Any], source: str = "case.json") -> list[tuple[dict[str, Any], str, str]]:
    found = spec_items(case.get("rules"), "/rules", source)
    for key in ("field_mappings", "field_mapping", "mappings"):
        mappings = case.get(key)
        if isinstance(mappings, dict):
            for old, new in mappings.items():
                if isinstance(new, str):
                    found.append(({"type": "rename_field", "source": old, "target": new},
                                  source, "/" + pointer_token(key) + "/" + pointer_token(str(old))))
        elif isinstance(mappings, list):
            for index, item in enumerate(mappings):
                if isinstance(item, dict):
                    spec = dict(item)
                    spec.setdefault("type", "rename_field")
                    spec.setdefault("source", spec.get("from"))
                    spec.setdefault("target", spec.get("to"))
                    found.append((spec, source, "/" + pointer_token(key) + "/" + str(index)))
    tokens = case.get("missing_tokens", case.get("missing_values"))
    if tokens is not None:
        found.append(({"type": "normalize_missing", "field": "*", "tokens": tokens},
                      source, "/missing_tokens" if "missing_tokens" in case else "/missing_values"))
    numeric = case.get("numeric_fields")
    if numeric is not None:
        conventions = case.get("numeric_conventions", {})
        for field in field_list(numeric):
            spec = {"type": "parse_number", "field": field}
            if isinstance(conventions, dict):
                spec.update({k: v for k, v in conventions.items() if k in {"decimal", "thousands", "allow_percent"}})
            found.append((spec, source, "/numeric_fields"))
    ranges = case.get("range_fields")
    if ranges is not None:
        conventions = case.get("range_conventions", {})
        for field in field_list(ranges):
            spec = {"type": "normalize_range", "field": field}
            if isinstance(conventions, dict):
                spec.update(conventions)
            found.append((spec, source, "/range_fields"))
    targets = case.get("unit_targets", {})
    if isinstance(targets, dict):
        for field, value in targets.items():
            if isinstance(value, str):
                spec = {"type": "convert_unit", "field": field, "target": value}
            elif isinstance(value, dict):
                spec = dict(value)
                spec.update({"type": "convert_unit", "field": field})
            else:
                continue
            found.append((spec, source, "/unit_targets/" + pointer_token(str(field))))
    identity = case.get("identity_keys", case.get("row_identity_keys"))
    if identity is not None:
        found.append(({"type": "validate_identity", "keys": identity},
                      source, "/identity_keys" if "identity_keys" in case else "/row_identity_keys"))
    return found


def normalize_rule(raw: dict[str, Any], source: str, pointer: str,
                   engine: RulesEngine) -> dict[str, Any] | None:
    spec = copy.deepcopy(raw)
    original_type = spec.get("type", spec.get("kind", spec.get("rule", spec.get("operator"))))
    # Expand a one-operation convenience object from a task directive.
    if original_type is None:
        if "numeric_fields" in spec:
            expanded = []
            for field in field_list(spec["numeric_fields"]):
                expanded.append(normalize_rule({"type": "parse_number", "field": field}, source, pointer, engine))
            return expanded[0] if len(expanded) == 1 else None
        if "range_fields" in spec:
            expanded = []
            for field in field_list(spec["range_fields"]):
                expanded.append(normalize_rule({"type": "normalize_range", "field": field}, source, pointer, engine))
            return expanded[0] if len(expanded) == 1 else None
        convenience_types = [
            ("missing_tokens", "normalize_missing"), ("identity_keys", "validate_identity"),
        ]
        for key, kind in convenience_types:
            if key in spec:
                spec["type"] = kind
                if kind == "normalize_missing":
                    spec["tokens"] = spec[key]
                    spec["field"] = "*"
                else:
                    spec["keys"] = spec[key]
                original_type = kind
                break
    kind = KIND_ALIASES.get(str(original_type).lower(), str(original_type).lower()) if original_type else "invalid"
    if kind == "rename_field":
        normalized = {k: spec.get(k) for k in ("source", "target")}
    elif kind == "validate_identity":
        normalized = {"keys": field_list(spec.get("keys", spec.get("fields")))}
    elif kind == "trim_whitespace":
        normalized = {"fields": field_list(spec.get("fields", spec.get("field", "*"))) or ["*"]}
    elif kind in {"normalize_missing", "parse_number", "normalize_range", "convert_unit", "literal_map", "regex_replace"}:
        normalized = dict(spec)
        normalized["field"] = str(spec.get("field", "*"))
    else:
        engine.add_review("INVALID_RULE", "unsupported or missing rule type: " + str(original_type),
                          source=source, pointer=pointer)
        return None
    normalized["type"] = kind
    normalized["priority"] = spec.get("priority", default_priority(kind))
    if not isinstance(normalized["priority"], int) or isinstance(normalized["priority"], bool):
        engine.add_review("INVALID_RULE", "priority must be an integer", source=source, pointer=pointer)
        return None
    normalized["enabled"] = spec.get("enabled", True) is not False
    normalized["builtin"] = kind in BUILTIN_KINDS
    declared_id = spec.get("id")
    if declared_id:
        normalized["declared_id"] = str(declared_id)
    basis = {k: v for k, v in normalized.items() if k not in {"enabled", "builtin", "declared_id"}}
    rid = "R-" + re.sub(r"[^a-z0-9]+", "-", kind.lower()).strip("-") + "-" + digest(basis)[:12]
    normalized["rule_id"] = rid
    normalized["provenance"] = [{"source": source, "pointer": pointer}]
    error = validate_rule(normalized)
    if error:
        engine.add_review("INVALID_RULE", error, rule_ids=[rid], source=source, pointer=pointer)
        normalized["enabled"] = False
        normalized["compile_error"] = error
    return normalized


def default_priority(kind: str) -> int:
    return {"rename_field": 100, "normalize_missing": 200, "trim_whitespace": 300,
            "literal_map": 350, "regex_replace": 360, "parse_number": 400,
            "normalize_range": 420, "convert_unit": 440, "validate_identity": 900}.get(kind, 500)


def validate_rule(rule: dict[str, Any]) -> str:
    kind = rule["type"]
    if kind == "rename_field" and (not rule.get("source") or not rule.get("target")):
        return "rename_field requires source and target"
    if kind == "validate_identity" and not rule.get("keys"):
        return "validate_identity requires at least one key"
    if kind in {"normalize_missing", "parse_number", "normalize_range", "convert_unit", "literal_map", "regex_replace"} and not rule.get("field"):
        return "field is required"
    if kind == "normalize_missing":
        if not isinstance(rule.get("tokens", []), list) or not all(isinstance(v, (str, int, float)) for v in rule.get("tokens", [])):
            return "normalize_missing tokens must be a scalar list"
    if kind == "convert_unit":
        if not isinstance(rule.get("target"), str) or not rule.get("target"):
            return "convert_unit requires a target unit"
    if kind == "literal_map" and not isinstance(rule.get("values"), dict):
        return "literal_map requires a values object"
    if kind == "regex_replace":
        if not isinstance(rule.get("pattern"), str) or not isinstance(rule.get("replacement"), str):
            return "regex_replace requires pattern and replacement strings"
        try:
            re.compile(rule["pattern"])
        except re.error as exc:
            return "invalid regular expression: " + str(exc)
    if kind in {"parse_number", "normalize_range"}:
        if rule.get("decimal", ".") not in {".", ","}:
            return "decimal convention must be '.' or ','"
        if rule.get("thousands") not in {None, "", ",", " ", ".", "_", "'"}:
            return "unsupported thousands convention"
    return ""


def expand_directives(raw_rules: list[tuple[dict[str, Any], str, str]], engine: RulesEngine) -> list[dict[str, Any]]:
    expanded: list[tuple[dict[str, Any], str, str]] = []
    for raw, source, pointer in raw_rules:
        if raw.get("type") is None and raw.get("kind") is None:
            if "numeric_fields" in raw:
                for index, field in enumerate(field_list(raw["numeric_fields"])):
                    expanded.append(({"type": "parse_number", "field": field}, source, pointer + "/" + str(index)))
                continue
            if "range_fields" in raw:
                for index, field in enumerate(field_list(raw["range_fields"])):
                    expanded.append(({"type": "normalize_range", "field": field}, source, pointer + "/" + str(index)))
                continue
        expanded.append((raw, source, pointer))
    result: dict[str, dict[str, Any]] = {}
    explicit_disable: set[str] = set()
    for raw, source, pointer in expanded:
        rule = normalize_rule(raw, source, pointer, engine)
        if rule is None:
            continue
        rid = rule["rule_id"]
        if rid in result:
            prior = result[rid]
            prior["provenance"].extend(rule["provenance"])
            # Identical declarations with different explicit enabled states are incompatible.
            if prior["enabled"] != rule["enabled"]:
                engine.add_review("RULE_CONFLICT", "same rule is both enabled and disabled",
                                  rule_ids=[rid], source=source, pointer=pointer)
                prior["enabled"] = False
        else:
            result[rid] = rule
    ordered = sorted(result.values(), key=lambda r: (r["priority"], r["rule_id"]))
    apply_mapping_aliases(ordered)
    detect_conflicts(ordered, engine)
    return ordered


def apply_mapping_aliases(rules: list[dict[str, Any]]) -> None:
    aliases: dict[str, str] = {}
    ambiguous: set[str] = set()
    for rule in rules:
        if rule["type"] == "rename_field" and rule["enabled"]:
            source, target = rule.get("source"), rule.get("target")
            if source in aliases and aliases[source] != target:
                ambiguous.add(source)
            else:
                aliases[source] = target
    for rule in rules:
        if rule["type"] in {"rename_field", "validate_identity"}:
            continue
        field = rule.get("field")
        if field in aliases and field not in ambiguous:
            rule["field"] = aliases[field]
            rule["compiled_alias"] = field
        if "fields" in rule:
            rule["fields"] = [aliases.get(f, f) if f not in ambiguous else f for f in rule["fields"]]


def detect_conflicts(rules: list[dict[str, Any]], engine: RulesEngine) -> None:
    groups: dict[tuple[str, ...], list[dict[str, Any]]] = {}
    for rule in rules:
        if not rule["enabled"]:
            continue
        kind = rule["type"]
        if kind in {"parse_number", "normalize_range", "convert_unit", "regex_replace", "literal_map", "normalize_missing"}:
            key = (rule.get("field", ""), "cell")
        elif kind == "rename_field":
            key = ("source:" + str(rule.get("source")), "rename")
        else:
            continue
        groups.setdefault(key, []).append(rule)
    for key, members in sorted(groups.items()):
        if len(members) < 2:
            continue
        by_signature: dict[str, list[dict[str, Any]]] = {}
        for member in members:
            basis = {k: v for k, v in member.items() if k not in {"rule_id", "provenance", "priority", "declared_id"}}
            by_signature.setdefault(digest(basis), []).append(member)
        if len(by_signature) <= 1:
            continue
        ids = [m["rule_id"] for m in members]
        for member in members:
            member["enabled"] = False
            member["hold_reason"] = "incompatible rules on same target"
        engine.add_review("RULE_CONFLICT", "incompatible rules target " + key[0] + "; all are held",
                          field=key[0], rule_ids=ids, source=members[0]["provenance"][0]["source"],
                          pointer=members[0]["provenance"][0]["pointer"])
    # Different names cannot be merged into one occupied target without explicit row handling.
    target_groups: dict[str, list[dict[str, Any]]] = {}
    for rule in rules:
        if rule["type"] == "rename_field" and rule["enabled"]:
            target_groups.setdefault(str(rule["target"]), []).append(rule)
    for target, members in sorted(target_groups.items()):
        sources = {member.get("source") for member in members}
        if len(members) > 1 and len(sources) > 1:
            ids = [member["rule_id"] for member in members]
            for member in members:
                member["enabled"] = False
                member["hold_reason"] = "multiple sources map to one target"
            engine.add_review("RULE_CONFLICT", "multiple sources map to target " + target + "; mappings held",
                              field=target, rule_ids=ids)


def row_key(row: dict[str, Any], identity_keys: list[str]) -> str:
    if not identity_keys:
        return str(row.get("__source", "data")) + "#row=" + str(row.get("__row_number", ""))
    values = []
    for key in identity_keys:
        value = row.get(key)
        values.append(str(key) + "=" + (clean_text(value) if value is not None else ""))
    return "|".join(values)


def active_fields(rule: dict[str, Any], row: dict[str, Any]) -> list[str]:
    fields = rule.get("fields", [rule.get("field", "*")])
    if fields == ["*"] or rule.get("field") == "*":
        return sorted(k for k in row if not k.startswith("__"))
    return [str(field) for field in fields]


def parse_decimal(value: Any, rule: dict[str, Any]) -> decimal.Decimal:
    if isinstance(value, bool) or value is None:
        raise ValueError("not a numeric value")
    if isinstance(value, (int, float, decimal.Decimal)):
        number = decimal.Decimal(str(value))
    else:
        text = str(value).strip()
        if not text:
            raise ValueError("empty value")
        allow_percent = rule.get("allow_percent") is True
        percent = text.endswith("%")
        if percent:
            if not allow_percent:
                raise ValueError("percent sign not declared")
            text = text[:-1].strip()
        thousands = rule.get("thousands")
        if thousands:
            text = text.replace(thousands, "")
        if rule.get("decimal", ".") == ",":
            if "." in text and not thousands:
                raise ValueError("ambiguous dot under decimal-comma convention")
            text = text.replace(",", ".")
        elif "," in text and thousands != ",":
            raise ValueError("comma requires an explicit numeric convention")
        if not re.fullmatch(r"[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?", text):
            raise ValueError("not a conservative numeric representation")
        number = decimal.Decimal(text)
        if percent:
            number /= decimal.Decimal(100)
    if not number.is_finite():
        raise ValueError("non-finite number")
    return number


def normalize_unit_token(token: str) -> str:
    token = token.strip().replace(" ", "")
    molarity = re.fullmatch(r"(m|u|µ|μ|n)?M", token)
    if molarity:
        prefix = molarity.group(1) or ""
        return prefix + "mol/l"
    token = UNIT_ALIASES.get(token.lower(), token.lower())
    return token


def split_unit_value(value: Any, rule: dict[str, Any]) -> tuple[decimal.Decimal, str]:
    if rule.get("source_unit"):
        number = parse_decimal(value, rule)
        return number, normalize_unit_token(str(rule["source_unit"]))
    if not isinstance(value, str):
        raise ValueError("unit must be in the value or declared as source_unit")
    match = re.fullmatch(r"\s*(.+?)\s*([a-zA-Zµμ/]+)\s*", value)
    if not match:
        raise ValueError("missing explicit unit")
    numeric_text, unit = match.groups()
    number = parse_decimal(numeric_text, rule)
    return number, normalize_unit_token(unit)


def conversion_factor(source: str, target: str) -> decimal.Decimal:
    source, target = normalize_unit_token(source), normalize_unit_token(target)
    if source == target:
        return decimal.Decimal(1)
    # Straight known units.
    if source in UNIT_SCALE and target in UNIT_SCALE:
        sb, ss = UNIT_SCALE[source]
        tb, ts = UNIT_SCALE[target]
        if sb == tb:
            return ss / ts
    # Consistent compound prefixes for M, mol/L, and per-volume concentrations.
    match_s = re.fullmatch(r"(m|u|µ|μ|n)?mol/l", source)
    match_t = re.fullmatch(r"(m|u|µ|μ|n)?mol/l", target)
    if match_s and match_t:
        factors = {None: decimal.Decimal(1), "m": decimal.Decimal("0.001"),
                   "u": decimal.Decimal("0.000001"), "µ": decimal.Decimal("0.000001"),
                   "μ": decimal.Decimal("0.000001"), "n": decimal.Decimal("0.000000001")}
        return factors[match_s.group(1)] / factors[match_t.group(1)]
    raise ValueError("incompatible or unknown unit conversion: " + source + " -> " + target)


def normalize_range_value(value: Any, rule: dict[str, Any]) -> str:
    if not isinstance(value, str):
        raise ValueError("range must be text with declared bounds")
    text = value.strip()
    separator = None
    for candidate in ("..", "…", "–", "—", " to ", "~", "～", "-"):
        if candidate in text:
            separator = candidate
            break
    if separator is None:
        raise ValueError("range separator not recognized")
    left, right = text.split(separator, 1)
    minimum, maximum = parse_decimal(left.strip(), rule), parse_decimal(right.strip(), rule)
    if minimum > maximum:
        raise ValueError("range lower bound exceeds upper bound")
    return decimal_text(minimum) + ".." + decimal_text(maximum)


def literal_missing(value: Any, tokens: list[str]) -> bool:
    if value is None or value == "":
        return True
    try:
        text = clean_text(value)
    except ValueError:
        return False
    return text in tokens


def execute_rule(rule: dict[str, Any], rows: list[dict[str, Any]], identity_keys: list[str],
                 engine: RulesEngine, global_missing: list[str]) -> None:
    kind = rule["type"]
    if kind == "validate_identity":
        seen: dict[str, int] = {}
        for row in rows:
            key = row_key(row, identity_keys)
            values = [clean_text(row.get(field, "")) for field in identity_keys]
            if not any(values):
                engine.add_review("IDENTITY_MISSING", "all declared identity fields are empty",
                                  row_key=key, field=",".join(identity_keys), rule_ids=[rule["rule_id"]],
                                  source=row.get("__source", ""))
            if key in seen:
                engine.add_review("IDENTITY_DUPLICATE", "duplicate row identity; rows retained",
                                  row_key=key, field=",".join(identity_keys), rule_ids=[rule["rule_id"]],
                                  source=row.get("__source", ""))
            else:
                seen[key] = row.get("__row_number", 0)
        return
    for row in rows:
        key = row_key(row, identity_keys)
        if kind == "rename_field":
            source, target = rule["source"], rule["target"]
            if source not in row or source.startswith("__"):
                continue
            before = row.get(source)
            if target in row and not literal_missing(row.get(target), global_missing) and clean_text(row[target]) != clean_text(before):
                engine.add_review("FIELD_COLLISION", "rename would overwrite a different nonempty value; no change applied",
                                  row_key=key, field=target, rule_ids=[rule["rule_id"]], source=row.get("__source", ""))
                continue
            if source == target:
                continue
            row[target] = before
            del row[source]
            engine.add_change(rule, row, key, source + "->" + target, before, before)
            continue
        for field in active_fields(rule, row):
            if field.startswith("__") or field not in row:
                continue
            before = row.get(field)
            if kind != "normalize_missing" and literal_missing(before, global_missing):
                continue
            try:
                if kind == "trim_whitespace":
                    after = clean_text(before).strip()
                elif kind == "normalize_missing":
                    tokens = [clean_text(v) for v in rule.get("tokens", [])]
                    after = "" if clean_text(before).strip() in tokens or clean_text(before) in tokens else before
                elif kind == "parse_number":
                    after = decimal_text(parse_decimal(before, rule))
                elif kind == "normalize_range":
                    after = normalize_range_value(before, rule)
                elif kind == "convert_unit":
                    number, source_unit = split_unit_value(before, rule)
                    after = decimal_text(number * conversion_factor(source_unit, rule["target"]))
                elif kind == "literal_map":
                    mapping = {clean_text(k): v for k, v in rule.get("values", {}).items()}
                    case_sensitive = rule.get("case_sensitive", True) is not False
                    probe = clean_text(before)
                    if not case_sensitive:
                        mapping = {k.casefold(): v for k, v in mapping.items()}
                        probe = probe.casefold()
                    after = mapping[probe] if probe in mapping else before
                elif kind == "regex_replace":
                    after = re.sub(rule["pattern"], rule["replacement"], clean_text(before))
                else:
                    continue
                after_text = clean_text(after)
                if after_text != clean_text(before):
                    row[field] = after_text
                    engine.add_change(rule, row, key, field, before, after_text)
            except (ValueError, decimal.InvalidOperation, KeyError, IndexError, re.error) as exc:
                engine.add_review("CONVERSION_ERROR", str(exc), row_key=key, field=field,
                                  rule_ids=[rule["rule_id"]], source=row.get("__source", ""))


def discover_data_files(root: Path, case: dict[str, Any], reserved: set[Path]) -> list[Path]:
    declared = case.get("data_files", case.get("data_file"))
    paths: list[Path] = []
    if declared:
        for item in field_list(declared):
            candidate = Path(item)
            if not candidate.is_absolute():
                candidate = root / candidate
            if candidate.is_file():
                paths.append(candidate)
    else:
        if root.is_dir():
            for base, directories, files in os.walk(root):
                directories[:] = sorted(d for d in directories if not d.startswith(".") and d not in {"work", "output"})
                for name in sorted(files):
                    path = Path(base) / name
                    if path.suffix.lower() in {".csv", ".tsv", ".json", ".jsonl"} and path not in reserved:
                        if name in {"case.json", "rules.json", "config.json", "result.json", "execution_plan.json", "changes.jsonl"}:
                            continue
                        paths.append(path)
    return sorted(set(paths), key=lambda p: display_path(p, root))


def load_json_records(value: Any) -> list[dict[str, Any]]:
    if isinstance(value, list):
        if all(isinstance(item, dict) for item in value):
            return [copy.deepcopy(item) for item in value]
        raise ValueError("JSON record array must contain only objects")
    if isinstance(value, dict):
        for wrapper in FORMATS:
            if wrapper in value:
                return load_json_records(value[wrapper])
        raise ValueError("no common record wrapper found (records/rows/data/items/results/samples/examples)")
    raise ValueError("JSON data must be an object wrapper or object array")


def read_records(path: Path) -> list[dict[str, Any]]:
    if path.suffix.lower() in {".csv", ".tsv"}:
        with path.open("r", encoding="utf-8-sig", newline="") as handle:
            sample = handle.read(8192)
            handle.seek(0)
            delimiter = "\t" if path.suffix.lower() == ".tsv" else ","
            if path.suffix.lower() == ".csv":
                try:
                    delimiter = csv.Sniffer().sniff(sample, delimiters=",;\t|").delimiter
                except csv.Error:
                    pass
            reader = csv.DictReader(handle, delimiter=delimiter)
            if reader.fieldnames is None or any(not name for name in reader.fieldnames):
                raise ValueError("missing or empty CSV header")
            rows = []
            for record in reader:
                if None in record:
                    raise ValueError("CSV row has more cells than headers")
                rows.append(dict(record))
            return rows
    if path.suffix.lower() == ".json":
        return load_json_records(read_json(path))
    if path.suffix.lower() == ".jsonl":
        records = []
        for line_number, line in enumerate(path.read_text(encoding="utf-8-sig").splitlines(), 1):
            if not line.strip():
                continue
            value = json.loads(line, parse_constant=lambda x: (_ for _ in ()).throw(ValueError("non-finite JSON number " + x)))
            loaded = load_json_records(value)
            if not loaded:
                raise ValueError("empty wrapper at JSONL line " + str(line_number))
            records.extend(loaded)
        return records
    raise ValueError("unsupported data suffix")


def normalize_contract(contract: Any) -> list[dict[str, Any]]:
    required_names: list[str] = []
    optional_names: list[str] = []

    def consume(value: Any, default_required: bool = True) -> None:
        if isinstance(value, list):
            for item in value:
                if isinstance(item, str):
                    (required_names if default_required else optional_names).append(item)
                elif isinstance(item, dict):
                    name = item.get("name", item.get("field", item.get("key")))
                    if isinstance(name, str):
                        required = item.get("required", default_required) is not False
                        (required_names if required else optional_names).append(name)
        elif isinstance(value, dict):
            for name, descriptor in value.items():
                if name in {"fields", "required", "optional", "properties"}:
                    continue
                if isinstance(descriptor, dict):
                    required = descriptor.get("required", default_required) is not False
                else:
                    required = default_required
                (required_names if required else optional_names).append(name)

    if isinstance(contract, dict):
        required = contract.get("required")
        if isinstance(required, list):
            consume(required, True)
        elif isinstance(required, dict):
            consume(required, True)
        consume(contract.get("optional", []), False)
        if "fields" in contract:
            fields = contract["fields"]
            if isinstance(fields, dict):
                for name, descriptor in fields.items():
                    if isinstance(descriptor, dict):
                        is_required = descriptor.get("required", True) is not False
                    else:
                        is_required = True
                    if isinstance(required, list):
                        is_required = name in required
                    (required_names if is_required else optional_names).append(name)
            elif isinstance(fields, list):
                for item in fields:
                    if isinstance(item, str):
                        is_required = item in required if isinstance(required, list) else True
                        (required_names if is_required else optional_names).append(item)
                    elif isinstance(item, dict):
                        name = item.get("name", item.get("field", item.get("key")))
                        default_required = (name in required if isinstance(required, list) else True)
                        is_required = item.get("required", default_required) is not False
                        consume([item], is_required)
        elif "properties" in contract:
            for name, descriptor in contract["properties"].items():
                is_required = name in required if isinstance(required, list) else True
                (required_names if is_required else optional_names).append(name)
        elif required is None and "optional" not in contract:
            consume(contract, True)
    else:
        consume(contract, True)
    ordered: list[dict[str, Any]] = []
    seen: set[str] = set()
    for name in required_names + optional_names:
        if name in seen:
            continue
        seen.add(name)
        ordered.append({"name": name, "required": name in required_names})
    return ordered


def public_row(row: dict[str, Any], columns: list[str], marker: str) -> dict[str, Any]:
    result = {column: clean_text(row.get(column, "")) for column in columns}
    if marker:
        result[MARKER_KEY] = marker
    return result


def artifacts_payload() -> dict[str, str]:
    return {name: name for name in (
        "cleaned.csv", "cleaned.json", "execution_plan.json", "changes.jsonl",
        "review_queue.csv", "audit.md", "result.json", "statistics.csv",
    )}


def sources_payload(source_records: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    return [source_records[key] for key in sorted(source_records)]


def make_result(case_id: Any, status: str, source_records: dict[str, dict[str, Any]],
                engine: RulesEngine, artifact_marker: str = "", unresolved: list[str] | None = None,
                extra: dict[str, Any] | None = None) -> dict[str, Any]:
    result: dict[str, Any] = {
        "case_id": case_id, "status": status, "sources": sources_payload(source_records),
        "uncertainty": [{"code": item["code"], "message": item["message"], "review_id": item["review_id"]}
                        for item in engine.review if item["severity"] != "info"],
        "change_records": safe_json(engine.changes),
        "change_log": safe_json(engine.changes),
        "review_queue": safe_json(engine.review), "artifacts": artifacts_payload(),
        "unresolved_fields": sorted(unresolved or []),
        "change_record_count": len(engine.changes),
    }
    if artifact_marker:
        result[MARKER_KEY] = artifact_marker
    if extra:
        result.update(safe_json(extra))
    return result


def write_review_csv(path: Path, engine: RulesEngine) -> None:
    columns = ([MARKER_KEY] if engine.marker else []) + REVIEW_COLUMNS
    records = []
    if engine.marker:
        records.append({MARKER_KEY: engine.marker, "review_id": "Q-SYNTHETIC-MARKER",
                        "code": "EXAMPLE_MARKER", "severity": "info", "status": "closed",
                        "message": engine.marker})
    for item in engine.review:
        record = dict(item)
        record["rule_ids"] = ";".join(item["rule_ids"])
        if engine.marker:
            record[MARKER_KEY] = engine.marker
        records.append(record)
    write_csv(path, columns, records)


def write_changes(path: Path, engine: RulesEngine) -> None:
    text = "".join(canonical(safe_json(change)) + "\n" for change in engine.changes)
    if not text and engine.marker:
        # An empty changes file remains empty by design; its marker is in result/audit.
        text = ""
    atomic_text(path, text)


def statistics(engine: RulesEngine, rows: list[dict[str, Any]], input_count: int, held_rules: int) -> dict[str, Any]:
    conversions = sum(1 for item in engine.review if item["code"] == "CONVERSION_ERROR")
    return {
        "input_rows": input_count, "output_rows": len(rows),
        "changed_cells": len(engine.changes),
        "review_items": sum(1 for item in engine.review if item["severity"] != "info"),
        "conversion_errors": conversions, "held_rules": held_rules,
    }


def write_statistics(path: Path, stats: dict[str, Any], marker: str) -> None:
    columns = [MARKER_KEY, "metric", "value"] if marker else ["metric", "value"]
    rows = []
    for key in sorted(stats):
        row = {"metric": key, "value": stats[key]}
        if marker:
            row[MARKER_KEY] = marker
        rows.append(row)
    write_csv(path, columns, rows)


def audit_text(case_id: Any, status: str, plan: dict[str, Any], stats: dict[str, Any],
               engine: RulesEngine, unresolved: list[str], marker: str) -> str:
    lines = []
    if marker:
        lines += ["# " + marker, ""]
    case_label = "null" if case_id is None else str(case_id)
    lines += ["# Rule-spec compilation audit", "", "- case_id: `" + case_label + "`",
              "- status: `" + status + "`",
              "- plan_sha256: `" + plan.get("plan_sha256", "") + "`",
              "- input_rows: " + str(stats["input_rows"]),
              "- output_rows: " + str(stats["output_rows"]),
              "- changed_cells: " + str(stats["changed_cells"]),
              "", "## Compiled rules", ""]
    for rule in plan.get("rules", []):
        state = "held" if not rule.get("enabled") else "executed"
        lines.append("- `" + rule["rule_id"] + "` — " + rule["type"] + ", priority " +
                     str(rule["priority"]) + ", " + state + "; provenance `" + canonical(rule["provenance"]) + "`")
    lines += ["", "## Review", ""]
    if not engine.review:
        lines.append("No review items.")
    for item in engine.review:
        lines.append("- `" + item["review_id"] + "` **" + item["code"] + "**: " + item["message"])
    lines += ["", "## Contract", "", "Unresolved required fields: " + (", ".join(unresolved) if unresolved else "none"), "",
              "Missing values remain empty. No imputation, silent conflict resolution, row deduplication, random order, network access, or clock-derived value is used.", ""]
    return "\n".join(lines)


def save_all_outputs(output: Path, work: Path, result: dict[str, Any], plan: dict[str, Any],
                     engine: RulesEngine, public_rows: list[dict[str, Any]], columns: list[str],
                     stats: dict[str, Any], unresolved: list[str], marker: str) -> None:
    output.mkdir(parents=True, exist_ok=True)
    work.mkdir(parents=True, exist_ok=True)
    output_columns = columns + ([MARKER_KEY] if marker and MARKER_KEY not in columns else [])
    write_csv(output / "cleaned.csv", output_columns, public_rows)
    write_json(output / "cleaned.json", public_rows)
    write_json(output / "execution_plan.json", plan)
    write_json(work / "execution_plan.json", plan)
    write_changes(output / "changes.jsonl", engine)
    write_review_csv(output / "review_queue.csv", engine)
    atomic_text(output / "audit.md", audit_text(result.get("case_id"), str(result.get("status", "input_error")),
                                               plan, stats, engine, unresolved, marker))
    write_statistics(output / "statistics.csv", stats, marker)
    write_json(output / "result.json", result)


def empty_plan(case_id: Any, engine: RulesEngine, marker: str = "") -> dict[str, Any]:
    plan: dict[str, Any] = {"compiler_version": VERSION, "case_id": case_id, "rules": [],
                            "messages": "compilation did not complete"}
    if marker:
        plan[MARKER_KEY] = marker
    plan["plan_sha256"] = digest(plan)
    return plan


def run(args: argparse.Namespace) -> int:
    input_root = Path(args.input)
    output = Path(args.output)
    work = Path(args.work)
    output.mkdir(parents=True, exist_ok=True)
    work.mkdir(parents=True, exist_ok=True)
    engine = RulesEngine()
    sources: dict[str, dict[str, Any]] = {}
    case: dict[str, Any] = {}
    raw_rules: list[tuple[dict[str, Any], str, str]] = []
    case_id: str | None = None
    marker = ""
    contract: list[dict[str, Any]] = []
    rows: list[dict[str, Any]] = []
    public_rows: list[dict[str, Any]] = []
    columns: list[str] = []
    stats = statistics(engine, rows, 0, 0)
    plan = empty_plan(case_id, engine)
    case_valid = True
    overrides_valid = True

    def source_add(path: Path, role: str) -> None:
        name = display_path(path, input_root)
        try:
            raw = path.read_bytes()
            sources[role + ":" + name] = {"name": name, "role": role, "sha256": sha256_bytes(raw), "bytes": len(raw)}
        except OSError as exc:
            engine.add_review("READ_ERROR", str(exc), source=name)

    # An honest, contract-bearing early result is written before compilation or mutation.
    early = make_result(case_id, "partial", sources, engine)
    write_json(output / "result.json", early)
    try:
        case_path = Path(args.case) if args.case else input_root / "case.json"
        if case_path.is_file():
            source_add(case_path, "case")
            try:
                loaded_case = read_json(case_path)
                if not isinstance(loaded_case, dict):
                    raise ValueError("case.json must contain an object")
                case = loaded_case
            except (OSError, ValueError, UnicodeError, json.JSONDecodeError) as exc:
                case_valid = False
                engine.add_review("CASE_ERROR", "case could not be parsed: " + str(exc), source=display_path(case_path, input_root))
        else:
            case_valid = False
            engine.add_review("CASE_ERROR", "case.json not found", source=display_path(case_path, input_root))

        # Config dictionaries are deep merged into case; config.rules append declarations.
        # A list is RFC-6902-style add/replace/remove JSON Patch on {"case":...,"rules":[...]}.
        for config_arg in args.config or []:
            config_path = Path(config_arg)
            source_add(config_path, "config")
            try:
                config = read_json(config_path)
                if isinstance(config, list):
                    current = {"case": case, "rules": raw_rules_to_specs(raw_rules)}
                    patched = apply_json_patch(current, config)
                    if not isinstance(patched, dict) or not isinstance(patched.get("case"), dict):
                        raise ValueError("patched root/case must be an object")
                    case = patched["case"]
                    raw_rules = spec_items(patched.get("rules", []), "/rules", display_path(config_path, input_root))
                elif isinstance(config, dict):
                    rule_additions = config.pop("rules", []) if isinstance(config, dict) else []
                    raw_rules.extend(spec_items(rule_additions, "/rules", display_path(config_path, input_root)))
                    case_overlay = config.pop("case", config)
                    if not isinstance(case_overlay, dict):
                        raise ValueError("config.case must be an object")
                    case = deep_merge(case, case_overlay)
                    disable_ids = config.get("disable_rule_ids", [])
                    if disable_ids:
                        case["_disable_rule_ids"] = field_list(disable_ids)
                    if config.get("reviewed_rule_ids"):
                        case["_reviewed_rule_ids"] = field_list(config["reviewed_rule_ids"])
                    if config.get("rule_overrides"):
                        case["_rule_overrides"] = config["rule_overrides"]
                else:
                    raise ValueError("config must be an object or JSON Patch list")
            except (OSError, ValueError, UnicodeError, json.JSONDecodeError) as exc:
                overrides_valid = False
                engine.add_review("CONFIG_ERROR", "config rejected: " + str(exc), source=display_path(config_path, input_root))

        raw_case_id = case.get("case_id", case.get("id"))
        if raw_case_id is None:
            for wrapper in ("case", "metadata", "case_metadata", "task", "input"):
                child = case.get(wrapper)
                if isinstance(child, dict) and child.get("case_id", child.get("id")) is not None:
                    raw_case_id = child.get("case_id", child.get("id"))
                    break
        case_id = str(raw_case_id) if raw_case_id is not None and str(raw_case_id) else None
        marker = str(case.get(MARKER_KEY, ""))
        engine.marker = marker
        contract_spec = case.get("output_contract")
        if contract_spec is None:
            for wrapper in ("case", "metadata", "case_metadata", "task", "input"):
                child = case.get(wrapper)
                if isinstance(child, dict) and "output_contract" in child:
                    contract_spec = child["output_contract"]
                    break
        contract = normalize_contract(contract_spec if contract_spec is not None else [])
        # Refresh the early result as soon as case identity and contract are known.
        early = make_result(case_id, "partial", sources, engine, marker, [f["name"] for f in contract if f["required"]])
        for field in contract:
            early.setdefault(field["name"], None)
        write_json(output / "result.json", early)
        raw_rules = case_convenience(case) + raw_rules

        task_path = Path(args.task) if args.task else input_root / "task.md"
        if task_path.is_file():
            source_add(task_path, "task")
            try:
                task_text = task_path.read_text(encoding="utf-8-sig")
                raw_rules.extend(discover_task_specs(task_text, display_path(task_path, input_root)))
            except (OSError, UnicodeError) as exc:
                engine.add_review("TASK_ERROR", str(exc), source=display_path(task_path, input_root))
        else:
            engine.add_review("TASK_ERROR", "task.md not found", severity="warning", source=display_path(task_path, input_root))

        rule_paths: list[Path] = []
        if args.rules:
            rule_paths = [Path(p) for p in args.rules]
        else:
            default_rules = input_root / "rules.json"
            if default_rules.is_file():
                rule_paths.append(default_rules)
            for resource in field_list(case.get("rule_resources", [])):
                resource_path = Path(resource)
                if not resource_path.is_absolute():
                    resource_path = input_root / resource_path
                if resource_path.is_file():
                    rule_paths.append(resource_path)
        reserved = {case_path.resolve(), task_path.resolve()} | {Path(p).resolve() for p in args.config or []}
        reserved |= {p.resolve() for p in rule_paths}
        for rule_path in sorted(set(rule_paths), key=lambda p: display_path(p, input_root)):
            source_add(rule_path, "rules")
            try:
                resource = read_json(rule_path)
                raw_rules.extend(spec_items(resource, "", display_path(rule_path, input_root)))
            except (OSError, ValueError, UnicodeError, json.JSONDecodeError) as exc:
                engine.add_review("RULE_RESOURCE_ERROR", str(exc), source=display_path(rule_path, input_root))

        # Apply disable and normalized-rule overrides before conflict analysis.
        disabled = set(field_list(case.get("_disable_rule_ids", case.get("disable_rule_ids", []))))
        overrides = case.get("_rule_overrides", case.get("rule_overrides", {}))
        if isinstance(overrides, dict):
            index = 0
            while index < len(raw_rules):
                raw, source, pointer = raw_rules[index]
                declared_id = str(raw.get("id", ""))
                if declared_id in overrides and isinstance(overrides[declared_id], dict):
                    raw = deep_merge(raw, overrides[declared_id])
                    raw_rules[index] = (raw, source, pointer + "/override")
                index += 1
        rules = expand_directives(raw_rules, engine)
        for rule in rules:
            if rule["rule_id"] in disabled or rule.get("declared_id") in disabled:
                rule["enabled"] = False
                rule["hold_reason"] = "disabled by user configuration"
        # Only explicitly supplied rules exist: there is no silent default rule register.
        for rule in rules:
            if rule["type"] in BUILTIN_KINDS:
                rule["authorization"] = "explicit_case_declaration"
        identity_keys = []
        identity_rules = [r for r in rules if r["enabled"] and r["type"] == "validate_identity"]
        if len(identity_rules) > 1:
            ids = [r["rule_id"] for r in identity_rules]
            for rule in identity_rules:
                rule["enabled"] = False
                rule["hold_reason"] = "conflicting identity declarations"
            engine.add_review("RULE_CONFLICT", "multiple identity declarations; all held", rule_ids=ids)
        elif identity_rules:
            identity_keys = identity_rules[0]["keys"]
        # Aliases also apply to row identity keys.
        aliases = {r["source"]: r["target"] for r in rules if r["enabled"] and r["type"] == "rename_field"}
        identity_keys = [aliases.get(k, k) for k in identity_keys]
        missing_tokens = sorted({clean_text(v) for r in rules if r["enabled"] and r["type"] == "normalize_missing"
                                 for v in r.get("tokens", [])})
        plan_material = {
            "compiler": "declarative-rule-spec-compiler", "compiler_version": VERSION,
            "case_id": case_id, "rule_count": len(rules), "rules": rules,
            "execution_order": [r["rule_id"] for r in rules if r["enabled"]],
            "identity_keys": identity_keys, "missing_tokens": missing_tokens,
            "reviewed_rule_ids": sorted(field_list(case.get("_reviewed_rule_ids", case.get("reviewed_rule_ids", [])))),
            "disabled_rule_ids": sorted(disabled),
            "incompatibility_policy": "hold_all_conflicting_rules_and_review",
            "source_digests": sources_payload(sources),
        }
        plan = dict(plan_material)
        plan["compile_review_ids"] = [q["review_id"] for q in engine.review]
        if marker:
            plan[MARKER_KEY] = marker
        plan["plan_sha256"] = digest(plan)
        # Freeze plan before execution; it is never changed based on data outcomes.
        frozen_plan_text = canonical(safe_json(plan)) + "\n"
        atomic_text(work / "execution_plan.json", frozen_plan_text)
        atomic_text(output / "execution_plan.json", frozen_plan_text)

        data_paths = discover_data_files(input_root, case, reserved)
        input_count = 0

        def append_records(loaded: list[dict[str, Any]], source_name: str) -> None:
            nonlocal input_count
            for source_row_number, record in enumerate(loaded, 1):
                row = copy.deepcopy(record)
                for key, value in list(row.items()):
                    if not isinstance(key, str):
                        row[str(key)] = row.pop(key)
                    try:
                        clean_text(value)
                    except ValueError as exc:
                        engine.add_review("DATA_ERROR", str(exc), source=source_name, field=key)
                        row[key] = ""
                row["__source"] = source_name
                row["__source_row"] = source_row_number
                input_count += 1
                row["__row_number"] = input_count
                rows.append(row)

        # The official wrapper may either reference external materials or embed
        # records directly in case.json. Do not treat the whole metadata object
        # as an observation; only explicit common record containers are loaded.
        embedded_name = display_path(case_path, input_root)
        for wrapper in FORMATS:
            if wrapper not in case:
                continue
            try:
                append_records(load_json_records(case[wrapper]), embedded_name)
            except (OSError, ValueError, UnicodeError, TypeError) as exc:
                engine.add_review("DATA_ERROR", "embedded " + wrapper + ": " + str(exc), source=embedded_name)

        for path in data_paths:
            source_name = display_path(path, input_root)
            source_add(path, "data")
            try:
                loaded = read_records(path)
            except (OSError, ValueError, UnicodeError, csv.Error, json.JSONDecodeError) as exc:
                engine.add_review("DATA_ERROR", str(exc), source=source_name)
                continue
            append_records(loaded, source_name)
        if not data_paths and not rows:
            engine.add_review("DATA_ERROR", "no supported external or embedded data records discovered")

        for row in rows:
            for key in row:
                if not key.startswith("__") and key not in columns:
                    columns.append(key)
        declared_columns = field_list(case.get("output_columns", []))
        if declared_columns:
            columns = declared_columns + [column for column in columns if column not in declared_columns]

        for rule in rules:
            if rule["enabled"]:
                execute_rule(rule, rows, identity_keys, engine, missing_tokens)

        # Recalculate columns after mappings, retaining stable first-appearance order.
        for row in rows:
            for key in row:
                if not key.startswith("__") and key not in columns:
                    columns.append(key)
        columns = [c for c in columns if c == MARKER_KEY or any(c in row for row in rows) or c in declared_columns]
        public_rows = [public_row(row, columns, marker) for row in rows]
        # Guarantee marker values and JSON/CSV cell finiteness independently of input types.
        for public in public_rows:
            if marker:
                public[MARKER_KEY] = marker
        stats = statistics(engine, rows, input_count, sum(1 for r in rules if not r["enabled"]))
        unresolved = [f["name"] for f in contract if f["required"] and f["name"] not in resolvable_contract_fields()]
        known_values = contract_values(public_rows, stats, plan, engine)
        for field in contract:
            if field["name"] in known_values and known_values[field["name"]] is None and field["required"]:
                if field["name"] not in unresolved:
                    unresolved.append(field["name"])
        if case_id is None and "case_id" not in unresolved:
            unresolved.append("case_id")

        status = "success"
        exit_code = 0
        if rows and engine.actionable():
            status, exit_code = "partial", 0
        if not rows and engine.actionable():
            status, exit_code = "input_error", 2
        if not case_valid or not overrides_valid:
            status = "partial" if rows else "input_error"
            exit_code = 0 if rows else 2
        if unresolved:
            status = "partial" if rows or status != "input_error" else "input_error"
            exit_code = 0 if exit_code != 2 else 2
        result = make_result(case_id, status, sources, engine, marker, unresolved)
        for field in contract:
            name = field["name"]
            result[name] = known_values[name] if name in known_values else result.get(name)
        result["plan_sha256"] = plan["plan_sha256"]
        save_all_outputs(output, work, result, plan, engine, public_rows, columns, stats, unresolved, marker)
        # Execution cannot mutate the reviewed plan.
        if (output / "execution_plan.json").read_text(encoding="utf-8") != frozen_plan_text or (work / "execution_plan.json").read_text(encoding="utf-8") != frozen_plan_text:
            raise RuntimeError("immutable execution plan changed during execution")
        print(canonical({"status": status, "case_id": case_id, "rows": len(rows), "changes": len(engine.changes),
                         "review_items": len(engine.review), "plan_sha256": plan["plan_sha256"]}))
        return exit_code
    except Exception as exc:  # Final defensive contract-complete failure output.
        engine.add_review("INTERNAL_ERROR", str(exc))
        status = "partial" if rows else "input_error"
        exit_code = 0 if rows else 2
        if isinstance(case, dict):
            raw_case_id = case.get("case_id", case.get("id", case_id))
            case_id = str(raw_case_id) if raw_case_id is not None and str(raw_case_id) else None
        marker = str(case.get(MARKER_KEY, marker)) if isinstance(case, dict) else marker
        engine.marker = marker
        if plan.get("case_id") is None and case_id is not None:
            plan = empty_plan(case_id, engine, marker)
        unresolved = [f["name"] for f in contract if f["required"] and f["name"] not in resolvable_contract_fields()]
        if case_id is None and "case_id" not in unresolved:
            unresolved.append("case_id")
        stats = statistics(engine, rows, len(rows), 0)
        public_rows = [public_row(row, columns, marker) for row in rows]
        result = make_result(case_id, status, sources, engine, marker, unresolved)
        known_values = contract_values(public_rows, stats, plan, engine)
        for field in contract:
            name = field["name"]
            result[name] = known_values[name] if name in known_values else result.get(name)
        save_all_outputs(output, work, result, plan, engine, public_rows, columns, stats, unresolved, marker)
        print(canonical({"status": status, "case_id": case_id, "error": str(exc)}))
        return exit_code


def raw_rules_to_specs(rules: list[tuple[dict[str, Any], str, str]]) -> list[dict[str, Any]]:
    return [copy.deepcopy(item[0]) for item in rules]


def resolvable_contract_fields() -> set[str]:
    return {"case_id", "status", "sources", "uncertainty", "change_records", "change_log",
            "review_queue", "artifacts", "unresolved_fields", "change_record_count", "plan_sha256",
            "cleaned", "cleaned_data", "cleaned_rows", "records", "rows", "data",
            "statistics", "stats", "row_count", "review_count", "change_count",
            "changes", "execution_plan"}


def contract_values(public_rows: list[dict[str, Any]], stats: dict[str, Any],
                    plan: dict[str, Any], engine: RulesEngine) -> dict[str, Any]:
    records = safe_json(public_rows)
    return {
        "cleaned": records, "cleaned_data": records, "cleaned_rows": records,
        "records": records, "rows": records, "data": records,
        "statistics": stats, "stats": stats, "row_count": stats["output_rows"],
        "review_count": stats["review_items"], "change_count": stats["changed_cells"],
        "changes": safe_json(engine.changes), "execution_plan": safe_json(plan),
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", default="/input", help="directory containing case.json, task.md, and data")
    parser.add_argument("--work", default="/app/work", help="work directory for the frozen plan")
    parser.add_argument("--output", default="/app/output", help="artifact output directory")
    parser.add_argument("--case", help="override case.json path")
    parser.add_argument("--task", help="override task.md path")
    parser.add_argument("--rules", action="append", help="override automatic rule resource discovery; repeatable")
    parser.add_argument("--config", action="append", help="JSON config or JSON Patch override; repeatable")
    parser.add_argument("--version", action="version", version=VERSION)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    return run(args)


if __name__ == "__main__":
    sys.exit(main())
