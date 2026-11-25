#!/usr/bin/env python3
"""Deterministic estimand validation, stratification, transforms, and gates.

This module deliberately performs no meta-analysis and infers no numeric heterogeneity
statistic. Agent-supplied semantic normalization is checked against exact source quotes.
"""
from __future__ import annotations

import copy
import hashlib
import json
import re
from decimal import Decimal, InvalidOperation, localcontext
from fractions import Fraction
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Sequence, Tuple

NOT_REPORTED = "not_reported"
OPERATIONS = {"DESCRIBE", "DIRECTION", "RANK", "TRANSFORM", "POOL"}
EXACT_CONVERSIONS = {
    "h_to_min": {"fields": {"time", "budget"}, "from": "h", "to": "min", "factor": Fraction(60),
                 "definition": "1 h = 60 min (exact)"},
    "min_to_h": {"fields": {"time", "budget"}, "from": "min", "to": "h", "factor": Fraction(1, 60),
                 "definition": "1 min = 1/60 h (exact)"},
}
REQUIRED_RECORD_KEYS = {
    "estimand_id", "source_document_id", "evidence", "task_id", "outcome", "metric",
    "population", "material", "pollutant", "intervention", "condition", "budget", "time", "unit",
    "scale", "estimate",
}
DIMENSIONS = (
    "task_id", "outcome", "metric", "population", "material", "pollutant", "intervention", "condition",
    "budget", "time", "unit", "scale",
)


class SchemaError(ValueError):
    """An input, source link, or normalized record is invalid."""


class OperationBlocked(ValueError):
    """Raised only in strict mode when an operation gate is blocked."""


def load_json(path: Path) -> Any:
    try:
        with path.open("r", encoding="utf-8") as handle:
            return json.load(handle)
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise SchemaError(f"Cannot read valid UTF-8 JSON from {path}: {exc}") from exc


def is_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def is_unknown(value: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, str):
        return value.strip().lower() in {"", "unknown", NOT_REPORTED, "n/a", "na"}
    return False


def unknown_paths(value: Any, prefix: str = "") -> List[str]:
    """Find unknown leaves without treating optional moderators as core dimensions."""
    if is_unknown(value):
        return [prefix]
    if isinstance(value, Mapping):
        found: List[str] = []
        for key, child in value.items():
            found.extend(unknown_paths(child, f"{prefix}.{key}" if prefix else str(key)))
        return found
    if isinstance(value, list):
        found = []
        for index, child in enumerate(value):
            found.extend(unknown_paths(child, f"{prefix}[{index}]"))
        return found
    return []


def decimal_text(value: Any) -> str:
    try:
        number = Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise SchemaError(f"Not a finite decimal: {value!r}") from exc
    if not number.is_finite():
        raise SchemaError(f"Not a finite decimal: {value!r}")
    if number == 0:
        return "0"
    normalized = number.normalize()
    text = format(normalized, "f")
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return text


def canonical_value(value: Any) -> Any:
    if isinstance(value, Mapping):
        result = {}
        for key in sorted(value):
            child = value[key]
            if key == "value" and is_number(child):
                result[key] = decimal_text(child)
            else:
                result[key] = canonical_value(child)
        return result
    if isinstance(value, list):
        return [canonical_value(child) for child in value]
    return value


def stratum_components(record: Mapping[str, Any]) -> Dict[str, Any]:
    return {dimension: canonical_value(copy.deepcopy(record[dimension])) for dimension in DIMENSIONS}


def stratum_key(record: Mapping[str, Any]) -> str:
    """Canonical JSON key; numeric 90 and 90.0 therefore share a representation."""
    return json.dumps(stratum_components(record), ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def fingerprint(key: str) -> str:
    return hashlib.sha256(key.encode("utf-8")).hexdigest()


def parse_corpus_document(path: Path, input_root: Path) -> Dict[str, Any]:
    """Read the simple auditable corpus format defined in references/runtime-and-schemas.md."""
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        raise SchemaError(f"Cannot read corpus document {path}: {exc}") from exc
    lines = text.splitlines()
    nonempty = [line for line in lines if line.strip()]
    if not nonempty or not nonempty[0].startswith("SOURCE_DOCUMENT_ID: "):
        raise SchemaError(f"{path} must begin with 'SOURCE_DOCUMENT_ID: <id>'")
    source_id = nonempty[0].split(": ", 1)[1].strip()
    if not source_id or any(char.isspace() for char in source_id):
        raise SchemaError(f"Invalid source_document_id in {path}")
    paragraphs: Dict[str, str] = {}
    for line in lines:
        if not line.strip() or line == nonempty[0]:
            continue
        match = re.fullmatch(r"\[([A-Za-z0-9_.:-]+)\]\s*(.*)", line)
        if not match:
            raise SchemaError(f"Unmarked corpus paragraph in {path}: {line!r}")
        paragraph_id, paragraph = match.groups()
        if paragraph_id in paragraphs:
            raise SchemaError(f"Duplicate paragraph_id {paragraph_id} in {path}")
        if not paragraph:
            raise SchemaError(f"Empty paragraph {paragraph_id} in {path}")
        paragraphs[paragraph_id] = paragraph
    if not paragraphs:
        raise SchemaError(f"No paragraphs in {path}")
    try:
        relative_path = path.resolve().relative_to(input_root.resolve()).as_posix()
    except ValueError as exc:
        raise SchemaError(f"Corpus path escapes input root: {path}") from exc
    return {
        "source_document_id": source_id,
        "path": relative_path,
        "paragraphs": paragraphs,
        "text_sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
        "text": text,
    }


def load_all_corpus_documents(input_root: Path, declarations: Any) -> Dict[str, Dict[str, Any]]:
    """Read every declared file and reject unlisted files under input/corpus."""
    if not isinstance(declarations, list) or not declarations:
        raise SchemaError("case.json corpus_documents must be a nonempty list")
    declared_paths: List[Path] = []
    expected_ids: Dict[Path, str] = {}
    for item in declarations:
        if (not isinstance(item, Mapping)
                or not {"source_document_id", "path"}.issubset(set(item))):
            raise SchemaError("Each corpus declaration needs source_document_id and path")
        relative = item["path"]
        if not isinstance(relative, str) or not relative or Path(relative).is_absolute():
            raise SchemaError("Corpus path must be a nonempty relative path")
        path = (input_root / relative).resolve()
        try:
            path.relative_to(input_root.resolve())
        except ValueError as exc:
            raise SchemaError(f"Corpus path escapes input root: {relative}") from exc
        if path in expected_ids:
            raise SchemaError(f"Duplicate corpus path: {relative}")
        declared_paths.append(path)
        expected_ids[path] = item["source_document_id"]
    corpus_dir = input_root / "corpus"
    discovered = {path.resolve() for path in corpus_dir.rglob("*") if path.is_file()} if corpus_dir.exists() else set()
    listed = set(declared_paths)
    if discovered != listed:
        missing = sorted(str(path) for path in discovered - listed)
        absent = sorted(str(path) for path in listed - discovered)
        raise SchemaError(f"Corpus declaration mismatch; unlisted={missing}, nonexistent={absent}")
    documents: Dict[str, Dict[str, Any]] = {}
    for path in declared_paths:
        document = parse_corpus_document(path, input_root)
        source_id = document["source_document_id"]
        if source_id != expected_ids[path]:
            raise SchemaError(f"Declared/document source_document_id mismatch at {path}")
        if source_id in documents:
            raise SchemaError(f"Duplicate source_document_id: {source_id}")
        documents[source_id] = document
    return documents


def _require_mapping(value: Any, label: str, keys: Iterable[str]) -> None:
    if not isinstance(value, Mapping):
        raise SchemaError(f"{label} must be an object")
    for key in keys:
        if key not in value:
            raise SchemaError(f"{label} lacks {key}")


def _validate_measurement(value: Any, label: str) -> None:
    _require_mapping(value, label, ("value", "unit"))
    measurement_value, unit = value["value"], value["unit"]
    if is_unknown(measurement_value) or is_unknown(unit):
        if not (is_unknown(measurement_value) and is_unknown(unit)):
            raise SchemaError(f"{label} value and unit must both be reported or both be not_reported")
    elif not is_number(measurement_value):
        raise SchemaError(f"{label}.value must be numeric or not_reported")
    elif Decimal(str(measurement_value)) < 0:
        raise SchemaError(f"{label}.value cannot be negative")


def validate_records(records: Any, documents: Mapping[str, Any], case_id: str, task_id: str,
                     task_text: str) -> Dict[str, Dict[str, Any]]:
    if not isinstance(case_id, str) or not case_id:
        raise SchemaError("case_id must be a nonempty string")
    if not isinstance(task_id, str) or not task_id or task_id not in task_text:
        raise SchemaError("workorder task_id must be a nonempty string appearing verbatim in task.md")
    if not isinstance(records, list) or not records:
        raise SchemaError("estimands.json records must be a nonempty list")
    indexed: Dict[str, Dict[str, Any]] = {}
    for index, record in enumerate(records):
        label = f"records[{index}]"
        _require_mapping(record, label, REQUIRED_RECORD_KEYS)
        estimand_id = record["estimand_id"]
        if not isinstance(estimand_id, str) or not estimand_id or estimand_id in indexed:
            raise SchemaError(f"Missing or duplicate estimand_id at {label}")
        if record["task_id"] != task_id:
            raise SchemaError(f"{estimand_id}: task_id does not match workorder/task.md")
        source_id = record["source_document_id"]
        if source_id not in documents:
            raise SchemaError(f"{estimand_id}: unknown source_document_id {source_id!r}")
        _require_mapping(record["metric"], f"{estimand_id}.metric", ("name", "definition"))
        if unknown_paths(record["metric"], "metric"):
            raise SchemaError(f"{estimand_id}: metric name and definition must be explicitly normalized")
        for field in ("outcome", "population", "material", "pollutant", "intervention", "unit", "scale"):
            if not isinstance(record[field], str):
                raise SchemaError(f"{estimand_id}.{field} must be a string (use not_reported when absent)")
        _validate_measurement(record["budget"], f"{estimand_id}.budget")
        _validate_measurement(record["time"], f"{estimand_id}.time")
        _require_mapping(record["estimate"], f"{estimand_id}.estimate", ("value", "unit", "direction"))
        estimate = record["estimate"]
        if not (is_number(estimate["value"]) or is_unknown(estimate["value"])):
            raise SchemaError(f"{estimand_id}.estimate.value must be numeric or not_reported")
        if not isinstance(estimate["unit"], str) or not isinstance(estimate["direction"], str):
            raise SchemaError(f"{estimand_id}.estimate unit/direction must be strings")
        if is_number(estimate["value"]) and estimate["unit"] != record["unit"]:
            raise SchemaError(f"{estimand_id}: estimate.unit must equal declared estimand unit")
        evidence = record["evidence"]
        if not isinstance(evidence, list) or not evidence:
            raise SchemaError(f"{estimand_id}: evidence must be a nonempty list")
        seen_evidence = set()
        for item in evidence:
            _require_mapping(item, f"{estimand_id}.evidence", ("source_document_id", "paragraph_id", "quote"))
            exact_source = item["source_document_id"]
            paragraph_id, quote = item["paragraph_id"], item["quote"]
            if exact_source != source_id:
                raise SchemaError(f"{estimand_id}: evidence source_document_id differs from record")
            if paragraph_id not in documents[source_id]["paragraphs"]:
                raise SchemaError(f"{estimand_id}: unknown source paragraph {source_id}/{paragraph_id}")
            if not isinstance(quote, str) or not quote or quote not in documents[source_id]["paragraphs"][paragraph_id]:
                raise SchemaError(f"{estimand_id}: quote is not an exact substring of {source_id}/{paragraph_id}")
            pair = (exact_source, paragraph_id, quote)
            if pair in seen_evidence:
                raise SchemaError(f"{estimand_id}: duplicate evidence item")
            seen_evidence.add(pair)
        indexed[estimand_id] = copy.deepcopy(record)
    return indexed


def validate_operation_requests(requests: Any, indexed: Mapping[str, Any]) -> List[Dict[str, Any]]:
    if not isinstance(requests, list) or not requests:
        raise SchemaError("comparison-workorder.json operation_requests must be a nonempty list")
    seen = set()
    validated = []
    for request in requests:
        _require_mapping(request, "operation_request", ("operation_id", "operation", "estimand_ids"))
        operation_id, operation = request["operation_id"], request["operation"]
        if not isinstance(operation_id, str) or not operation_id or operation_id in seen:
            raise SchemaError("Missing or duplicate operation_id")
        if operation not in OPERATIONS:
            raise SchemaError(f"{operation_id}: unsupported operation {operation!r}")
        ids = request["estimand_ids"]
        if not isinstance(ids, list) or not ids or len(ids) != len(set(ids)):
            raise SchemaError(f"{operation_id}: estimand_ids must be nonempty and unique")
        unknown = [item for item in ids if item not in indexed]
        if unknown:
            raise SchemaError(f"{operation_id}: unknown estimand_ids {unknown}")
        if operation != "DESCRIBE" and len(ids) < 2:
            raise SchemaError(f"{operation_id}: {operation} needs at least two estimands")
        seen.add(operation_id)
        validated.append(copy.deepcopy(request))
    return validated


def _measurement_after_conversion(measurement: Mapping[str, Any], conversion_name: str) -> Dict[str, Any]:
    conversion = EXACT_CONVERSIONS[conversion_name]
    converted = copy.deepcopy(measurement)
    if is_unknown(measurement["value"]):
        return converted
    factor = conversion["factor"]
    exact = Fraction(str(measurement["value"])) * factor
    denominator = exact.denominator
    for prime in (2, 5):
        while denominator % prime == 0:
            denominator //= prime
    if denominator != 1:
        raise SchemaError(
            f"Exact converted value {exact} has no finite JSON decimal representation; refusing approximation"
        )
    # The remaining denominator has only 2/5 factors, so decimal division terminates exactly.
    with localcontext() as context:
        context.prec = max(50, len(str(abs(exact.numerator))) + len(str(exact.denominator)) + 10)
        value = Decimal(exact.numerator) / Decimal(exact.denominator)
    converted["value"] = float(value) if value != value.to_integral() else int(value)
    converted["unit"] = conversion["to"]
    return converted


def apply_transforms(indexed: Mapping[str, Any], ids: Sequence[str], transforms: Any) -> Tuple[Dict[str, Dict[str, Any]], List[Dict[str, Any]]]:
    """Apply only whitelisted exact conversions to an in-memory copy."""
    if transforms is None:
        transforms = []
    if not isinstance(transforms, list):
        raise SchemaError("transforms must be a list")
    transformed = {item: copy.deepcopy(indexed[item]) for item in ids}
    audit: List[Dict[str, Any]] = []
    used = set()
    for item in transforms:
        _require_mapping(item, "transform", ("estimand_id", "field", "conversion", "reason"))
        estimand_id, field, conversion_name = item["estimand_id"], item["field"], item["conversion"]
        if estimand_id not in transformed:
            raise SchemaError("Transform targets an estimand outside the operation")
        if conversion_name not in EXACT_CONVERSIONS:
            raise SchemaError(f"Unapproved/non-exact conversion {conversion_name!r}")
        conversion = EXACT_CONVERSIONS[conversion_name]
        if field not in conversion["fields"]:
            raise SchemaError(f"{conversion_name} is not approved for {field}")
        if not isinstance(item["reason"], str) or not item["reason"].strip():
            raise SchemaError("Every transform requires a documented reason")
        token = (estimand_id, field)
        if token in used:
            raise SchemaError(f"Duplicate transform for {estimand_id}/{field}")
        used.add(token)
        measurement = transformed[estimand_id][field]
        if is_unknown(measurement["value"]):
            raise SchemaError(f"Cannot transform unknown {estimand_id}/{field}")
        if measurement["unit"] != conversion["from"]:
            raise SchemaError(f"{estimand_id}/{field} has unit {measurement['unit']!r}, expected {conversion['from']!r}")
        before = copy.deepcopy(measurement)
        transformed[estimand_id][field] = _measurement_after_conversion(measurement, conversion_name)
        audit.append({
            "estimand_id": estimand_id, "field": field, "conversion": conversion_name,
            "definition": conversion["definition"], "reason": item["reason"],
            "before": before, "after": copy.deepcopy(transformed[estimand_id][field]),
        })
    return transformed, audit


def _quantitative_unknowns(record: Mapping[str, Any]) -> List[str]:
    unknown = []
    for dimension in DIMENSIONS:
        unknown.extend(unknown_paths(record[dimension], dimension))
    unknown.extend(unknown_paths(record["estimate"]["value"], "estimate.value"))
    unknown.extend(unknown_paths(record["estimate"]["unit"], "estimate.unit"))
    return unknown


def _mismatches(records: Mapping[str, Mapping[str, Any]], ids: Sequence[str]) -> List[str]:
    baseline = stratum_components(records[ids[0]])
    mismatched = set()
    for estimand_id in ids[1:]:
        current = stratum_components(records[estimand_id])
        for dimension in DIMENSIONS:
            if current[dimension] != baseline[dimension]:
                mismatched.add(dimension)
    return sorted(mismatched)


def _single_fingerprints(records: Mapping[str, Mapping[str, Any]], ids: Sequence[str]) -> List[str]:
    return [fingerprint(stratum_key(records[item])) for item in ids]


def evaluate_operation(request: Mapping[str, Any], indexed: Mapping[str, Any]) -> Dict[str, Any]:
    """Return an allowed/blocked decision, never a pooled numeric estimate."""
    operation = request["operation"]
    operation_id = request["operation_id"]
    ids = list(request["estimand_ids"])
    blocking: List[str] = []
    caveats: List[str] = []
    audit: List[Dict[str, Any]] = []
    working = {item: copy.deepcopy(indexed[item]) for item in ids}

    if operation in {"RANK", "TRANSFORM", "POOL"}:
        for estimand_id in ids:
            for path in _quantitative_unknowns(working[estimand_id]):
                blocking.append(f"UNKNOWN:{estimand_id}:{path}")
        try:
            working, audit = apply_transforms(indexed, ids, request.get("transforms", []))
        except SchemaError as exc:
            blocking.append(f"TRANSFORM_INVALID:{exc}")

    mismatches = _mismatches(working, ids) if not any(item.startswith("TRANSFORM_INVALID") for item in blocking) else []
    raw_mismatches = _mismatches(indexed, ids)
    raw_unknowns = sorted({f"{item}:{path}" for item in ids for path in _quantitative_unknowns(indexed[item])})

    if operation == "DESCRIBE":
        if raw_mismatches:
            caveats.append("Side-by-side description retains unlike dimensions: " + ", ".join(raw_mismatches))
        if raw_unknowns:
            caveats.append("Not-reported cells remain explicit: " + ", ".join(raw_unknowns))
        rationale = "DESCRIBE permits unlike measures and unknown cells; no numeric synthesis is implied."
    elif operation == "DIRECTION":
        for estimand_id in ids:
            direction = indexed[estimand_id]["estimate"]["direction"]
            if is_unknown(direction):
                blocking.append(f"UNKNOWN:{estimand_id}:estimate.direction")
        supplied_caveats = request.get("caveats")
        if not isinstance(supplied_caveats, list) or not supplied_caveats or not all(
                isinstance(item, str) and item.strip() for item in supplied_caveats):
            blocking.append("DIRECTION_REQUIRES_EXPLICIT_CAVEATS")
        else:
            caveats.extend(supplied_caveats)
        if raw_mismatches:
            caveats.append("Directions are qualitative only across dimensions: " + ", ".join(raw_mismatches))
        if raw_unknowns:
            caveats.append("Qualitative direction does not repair missing values: " + ", ".join(raw_unknowns))
        rationale = "DIRECTION is gateable with explicit caveats and reported directions; effect sizes are not ranked."
    else:
        if operation == "TRANSFORM" and not request.get("transforms"):
            blocking.append("TRANSFORM_REQUIRES_AT_LEAST_ONE_EXACT_CONVERSION")
        if mismatches:
            blocking.append("ESTIMAND_MISMATCH:" + ",".join(mismatches))
        if operation == "RANK":
            rationale = "RANK requires one known estimand and compatible estimate scale after any requested exact transforms."
        elif operation == "TRANSFORM":
            rationale = "TRANSFORM permits only documented exact conversions and requires post-conversion stratum identity."
        else:
            rationale = "POOL is only a gate; no pooled estimate or heterogeneity statistic is calculated."
            exchangeability = request.get("exchangeability")
            required_true = ("design_compatibility", "independence_or_overlap", "methodological_exchangeability")
            if not isinstance(exchangeability, Mapping):
                blocking.append("POOL_EXCHANGEABILITY_NOT_JUSTIFIED")
            else:
                for key in required_true:
                    if exchangeability.get(key) is not True:
                        blocking.append(f"POOL_EXCHANGEABILITY_UNPROVEN:{key}")
                if not isinstance(exchangeability.get("justification"), str) or not exchangeability["justification"].strip():
                    blocking.append("POOL_EXCHANGEABILITY_JUSTIFICATION_MISSING")
        if not blocking:
            estimate_units = {working[item]["estimate"]["unit"] for item in ids}
            estimate_scales = {working[item]["scale"] for item in ids}
            if len(estimate_units) != 1 or len(estimate_scales) != 1:
                blocking.append("ESTIMATE_SCALE_MISMATCH")
        if operation == "POOL" and len({record["source_document_id"] for record in working.values()}) < 5:
            caveats.append("Tiny paper set: exchangeability is not inferred from numerical similarity; pooling is normally inappropriate.")

    # A mismatch in descriptive mode is information, not a prohibition.
    result = {
        "operation_id": operation_id,
        "operation": operation,
        "estimand_ids": ids,
        "allowed": not blocking,
        "comparability": "noncomparable" if raw_mismatches else ("unknown" if raw_unknowns else "same_estimand"),
        "blocking_reasons": sorted(set(blocking)),
        "caveats": list(dict.fromkeys(caveats)),
        "raw_stratum_fingerprints": _single_fingerprints(indexed, ids),
        "gated_stratum_fingerprints": _single_fingerprints(working, ids),
        "mismatches_after_requested_transforms": mismatches,
        "transform_audit": audit,
        "rationale": rationale,
    }
    if operation == "DIRECTION":
        result["directions"] = [
            {"estimand_id": estimand_id, "direction": indexed[estimand_id]["estimate"]["direction"]}
            for estimand_id in ids
        ]
    if operation == "POOL":
        result["numeric_synthesis"] = "not_performed"
    return result


def evaluate_all(requests: Sequence[Mapping[str, Any]], indexed: Mapping[str, Any]) -> List[Dict[str, Any]]:
    return [evaluate_operation(request, indexed) for request in requests]


def ensure_operations_allowed(results: Sequence[Mapping[str, Any]]) -> None:
    blocked = [result["operation_id"] for result in results if not result["allowed"]]
    if blocked:
        raise OperationBlocked("Blocked quantitative/qualitative operation requests in strict mode: " + ", ".join(blocked))


def preflight_rows(indexed: Mapping[str, Any], task_id: str) -> List[Dict[str, str]]:
    """Explicit task/metric/unit/material/pollutant/budget checks before any synthesis."""
    rows = []
    for estimand_id, record in indexed.items():
        cells = {"task": "ok" if record["task_id"] == task_id else "mismatch"}
        for field in ("metric", "unit", "material", "pollutant", "budget"):
            cells[field] = NOT_REPORTED if unknown_paths(record[field], field) else "ok"
        rows.append({"estimand_id": estimand_id, **cells})
    return rows
