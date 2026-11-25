#!/usr/bin/env python3
"""Deterministic structural checks for scientific scope meshes.

This module does not assess semantic support, scientific truth, or search completeness.
Python standard library only.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

DIMENSIONS = (
    "subject_population_material",
    "intervention_method",
    "comparator",
    "dataset_sample",
    "experimental_conditions",
    "metric_unit",
    "direction_effect",
    "limitations",
)
CLASSIFICATIONS = {"demonstrated", "inferred", "not_reported", "conflicting"}
UNIVERSAL_RE = re.compile(
    r"(?i)(?:\balways\b|(?<![A-Za-z0-9_])all(?![A-Za-z0-9_])|\bevery\b|"
    r"\buniversally\b|\bstate\s+of\s+the\s+art\b|\bbest\b|"
    r"\bno\s+exceptions?\b|总是|始终|所有|全部|普遍|万能|无一例外|最先进|最佳)"
)
SECTIONS = ("methods", "results", "tables", "discussion")
ANCHOR_RE = re.compile(r"(?m)^\[([A-Za-z0-9_.:#-]+)\][ \t]*$")


class InputError(Exception):
    """Malformed or unreadable CLI input."""


def load_json(path: str) -> Any:
    p = Path(path)
    try:
        text = p.read_text(encoding="utf-8")
    except FileNotFoundError as exc:
        raise InputError(f"missing JSON input: {p}") from exc
    except (OSError, UnicodeError) as exc:
        raise InputError(f"unreadable JSON input {p}: {exc}") from exc
    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        raise InputError(f"malformed JSON {p}: line {exc.lineno}, column {exc.colno}: {exc.msg}") from exc


def write_json(path: str, value: Any) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _err(path: str, code: str, message: str) -> Dict[str, str]:
    return {"path": path, "code": code, "message": message}


def _nonempty(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _dimension_errors(value: Any, path: str) -> List[Dict[str, str]]:
    if _nonempty(value):
        return []
    if not isinstance(value, dict):
        return [_err(path, "DIMENSION_REQUIRED", "use a nonempty string or an NR/NA object with a reason")]
    if set(value) != {"status", "reason"} or value.get("status") not in {"NR", "NA"} or not _nonempty(value.get("reason")):
        return [_err(path, "INVALID_NR_NA", "object must contain exactly status (NR or NA) and a nonempty reason")]
    return []


def _anchored_region(text: str, anchor: str) -> Optional[str]:
    matches = list(ANCHOR_RE.finditer(text))
    for index, match in enumerate(matches):
        if match.group(1) == anchor:
            end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
            return text[match.end():end]
    return None


def verify_evidence(
    evidence: Any,
    path: str,
    source_root: Optional[str],
    source_cache: Dict[str, Any],
    source_texts: Optional[Dict[str, str]] = None,
) -> List[Dict[str, str]]:
    """Verify exact quote containment within an explicitly anchored source region."""
    errors: List[Dict[str, str]] = []
    if not isinstance(evidence, dict):
        return [_err(path, "EVIDENCE_OBJECT_REQUIRED", "evidence must be an object")]
    for key in ("source", "anchor", "quote"):
        if not _nonempty(evidence.get(key)):
            errors.append(_err(f"{path}.{key}", "EVIDENCE_FIELD_REQUIRED", f"{key} must be a nonempty string"))
    if errors:
        return errors
    source = evidence["source"]
    anchor = evidence["anchor"]
    quote = evidence["quote"]
    if Path(source).is_absolute() or ".." in Path(source).parts:
        return [_err(f"{path}.source", "UNSAFE_SOURCE_PATH", "source must stay relative to source-root")]
    try:
        if source_texts is not None:
            if source not in source_texts:
                raise FileNotFoundError(source)
            text = source_texts[source]
        else:
            if source_root is None:
                raise InputError("source-root is required when no preloaded sources are supplied")
            if source not in source_cache:
                root = Path(source_root).resolve()
                candidate = (root / source).resolve()
                if root != candidate and root not in candidate.parents:
                    raise InputError(f"source escapes source-root: {source}")
                try:
                    source_cache[source] = candidate.read_text(encoding="utf-8")
                except FileNotFoundError:
                    source_cache[source] = _err(f"{path}.source", "SOURCE_MISSING", f"source file not found: {source}")
                except (OSError, UnicodeError) as exc:
                    source_cache[source] = _err(f"{path}.source", "SOURCE_UNREADABLE", f"source cannot be read: {exc}")
            text = source_cache[source]
    except FileNotFoundError:
        return [_err(f"{path}.source", "SOURCE_MISSING", f"source file not found: {source}")]
    if isinstance(text, dict):
        cached = dict(text)
        cached["path"] = f"{path}.source"
        return [cached]
    region = _anchored_region(text, anchor)
    if region is None:
        errors.append(_err(f"{path}.anchor", "ANCHOR_MISSING", f"explicit anchor [{anchor}] not found in {source}"))
    elif quote not in region:
        errors.append(_err(f"{path}.quote", "QUOTE_MISMATCH", "quote is not a verbatim contiguous substring of the anchored region"))
    return errors


def validate_scope_payload(
    payload: Any,
    source_root: Optional[str] = None,
    source_texts: Optional[Dict[str, str]] = None,
) -> Dict[str, Any]:
    errors: List[Dict[str, str]] = []
    cache: Dict[str, Any] = {}
    if not isinstance(payload, dict) or not isinstance(payload.get("records"), list):
        return {
            "valid": False,
            "record_count": 0,
            "errors": [_err("records", "RECORDS_ARRAY_REQUIRED", "top level must be an object with a records array")],
            "error_count": 1,
            "semantic_validation": False,
        }
    records = payload["records"]
    seen: Dict[str, int] = {}
    evidence_count = 0
    for i, record in enumerate(records):
        path = f"records[{i}]"
        if not isinstance(record, dict):
            errors.append(_err(path, "RECORD_OBJECT_REQUIRED", "record must be an object"))
            continue
        for field in ("record_id", "claim_id"):
            if not _nonempty(record.get(field)):
                errors.append(_err(f"{path}.{field}", "ID_REQUIRED", f"{field} must be a nonempty string"))
        rid = record.get("record_id")
        if _nonempty(rid):
            if rid in seen:
                errors.append(_err(f"{path}.record_id", "DUPLICATE_RECORD_ID", f"also used by records[{seen[rid]}]"))
            else:
                seen[rid] = i
        classification = record.get("classification")
        if classification not in CLASSIFICATIONS:
            errors.append(_err(f"{path}.classification", "INVALID_CLASSIFICATION", "expected demonstrated, inferred, not_reported, or conflicting"))
        for field in DIMENSIONS:
            errors.extend(_dimension_errors(record.get(field), f"{path}.{field}"))
        evidence = record.get("evidence")
        if not isinstance(evidence, list):
            errors.append(_err(f"{path}.evidence", "EVIDENCE_ARRAY_REQUIRED", "evidence must be an array"))
            evidence = []
        minimum = 2 if classification == "conflicting" else (1 if classification in {"demonstrated", "inferred"} else 0)
        if len(evidence) < minimum:
            errors.append(_err(f"{path}.evidence", "INSUFFICIENT_EVIDENCE", f"{classification} requires at least {minimum} evidence item(s)"))
        if classification == "inferred" and not _nonempty(record.get("inference_reasoning")):
            errors.append(_err(f"{path}.inference_reasoning", "INFERENCE_REASON_REQUIRED", "inferred records must separate reasoning from direct findings"))
        if classification == "not_reported" and not _nonempty(record.get("not_reported_basis")):
            errors.append(_err(f"{path}.not_reported_basis", "NR_BASIS_REQUIRED", "not_reported records must document targeted searches"))
        if classification == "conflicting" and not _nonempty(record.get("conflict_note")):
            errors.append(_err(f"{path}.conflict_note", "CONFLICT_NOTE_REQUIRED", "conflicting records must retain both sides and the disagreement"))
        for j, item in enumerate(evidence):
            evidence_count += 1
            errors.extend(verify_evidence(item, f"{path}.evidence[{j}]", source_root, cache, source_texts))
    return {
        "valid": not errors,
        "synthetic": payload.get("synthetic") is True,
        "record_count": len(records),
        "evidence_count": evidence_count,
        "error_count": len(errors),
        "errors": errors,
        "semantic_validation": False,
        "note": "Structural and quote-containment checks only; no semantic or scientific validation.",
    }


def _records_by_id(payload: Any) -> Tuple[Dict[str, Dict[str, Any]], List[Dict[str, str]]]:
    errors: List[Dict[str, str]] = []
    result: Dict[str, Dict[str, Any]] = {}
    if not isinstance(payload, dict) or not isinstance(payload.get("records"), list):
        return result, [_err("records", "RECORDS_ARRAY_REQUIRED", "records input must contain a records array")]
    for i, record in enumerate(payload["records"]):
        if not isinstance(record, dict) or not _nonempty(record.get("record_id")):
            errors.append(_err(f"records[{i}].record_id", "ID_REQUIRED", "each record needs a nonempty record_id"))
            continue
        rid = record["record_id"]
        if rid in result:
            errors.append(_err(f"records[{i}].record_id", "DUPLICATE_RECORD_ID", rid))
        result[rid] = record
    return result, errors


def audit_claims_payload(
    claims_payload: Any,
    records_payload: Any,
    source_root: Optional[str] = None,
    source_texts: Optional[Dict[str, str]] = None,
) -> Dict[str, Any]:
    records, errors = _records_by_id(records_payload)
    cache: Dict[str, Any] = {}
    if not isinstance(claims_payload, dict) or not isinstance(claims_payload.get("claims"), list):
        return {
            "valid": False,
            "errors": [_err("claims", "CLAIMS_ARRAY_REQUIRED", "top level must be an object with a claims array")],
            "claims": [],
            "semantic_validation": False,
        }
    audits: List[Dict[str, Any]] = []
    for i, claim in enumerate(claims_payload["claims"]):
        path = f"claims[{i}]"
        if not isinstance(claim, dict):
            errors.append(_err(path, "CLAIM_OBJECT_REQUIRED", "claim must be an object"))
            continue
        if _nonempty(claim.get("claim_id")):
            cid = claim["claim_id"]
        else:
            cid = path
            errors.append(_err(f"{path}.claim_id", "ID_REQUIRED", "claim_id must be a nonempty string"))
        statement = claim.get("statement")
        if not _nonempty(statement):
            errors.append(_err(f"{path}.statement", "STATEMENT_REQUIRED", "statement must be a nonempty string"))
            statement = ""
        declared = claim.get("universal") is True
        flags: List[str] = []
        if UNIVERSAL_RE.search(statement) and not declared:
            flags.append("POSSIBLE_UNIVERSAL_NOT_DECLARED")
        linked = claim.get("scope_record_ids")
        if not isinstance(linked, list) or not all(_nonempty(x) for x in linked):
            errors.append(_err(f"{path}.scope_record_ids", "RECORD_LINKS_REQUIRED", "scope_record_ids must be an array of record IDs"))
            linked = []
        raw_exceptions = claim.get("scope_record_link_exceptions", {})
        if not isinstance(raw_exceptions, dict):
            errors.append(_err(f"{path}.scope_record_link_exceptions", "INVALID_LINK_EXCEPTIONS", "exceptions must be an object keyed by linked record ID"))
            raw_exceptions = {}
        composition_exceptions = set()
        for rid, exception in raw_exceptions.items():
            epath = f"{path}.scope_record_link_exceptions.{rid}"
            if rid not in linked:
                errors.append(_err(epath, "LINK_EXCEPTION_NOT_LINKED", "exception record ID must also occur in scope_record_ids"))
            if (
                not isinstance(exception, dict)
                or set(exception) != {"kind", "reason"}
                or exception.get("kind") != "composition"
                or not _nonempty(exception.get("reason"))
            ):
                errors.append(_err(epath, "INVALID_COMPOSITION_EXCEPTION", "use exactly kind='composition' and a nonempty reason; universal aggregate links need no exception"))
            else:
                composition_exceptions.add(rid)
        for rid in linked:
            if rid not in records:
                errors.append(_err(f"{path}.scope_record_ids", "UNKNOWN_RECORD", f"no scope record named {rid}"))
            elif not declared and records[rid].get("claim_id") != cid and rid not in composition_exceptions:
                errors.append(_err(
                    f"{path}.scope_record_ids",
                    "RECORD_CLAIM_MISMATCH",
                    f"record {rid} has claim_id {records[rid].get('claim_id')!r}, expected {cid!r}; "
                    "document a composition exception or correct the link",
                ))
        if declared:
            coverage = claim.get("section_coverage")
            if not isinstance(coverage, dict):
                coverage = {}
            for section in SECTIONS:
                entry = coverage.get(section)
                if not isinstance(entry, dict) or entry.get("checked") is not True:
                    flags.append(f"UNIVERSAL_MISSING_{section.upper()}")
                    continue
                ev = entry.get("evidence")
                if ev is None:
                    flags.append(f"UNIVERSAL_MISSING_{section.upper()}_EVIDENCE")
                else:
                    evidence_errors = verify_evidence(ev, f"{path}.section_coverage.{section}.evidence", source_root, cache, source_texts)
                    errors.extend(evidence_errors)
                    if evidence_errors:
                        flags.append(f"UNIVERSAL_INVALID_{section.upper()}_EVIDENCE")
            search = claim.get("exception_search")
            if not isinstance(search, dict) or search.get("performed") is not True:
                flags.append("UNIVERSAL_NO_EXCEPTION_SEARCH")
                search = {}
            terms = search.get("terms")
            locations = search.get("locations")
            if not isinstance(terms, list) or not terms or not all(_nonempty(x) for x in terms):
                flags.append("UNIVERSAL_NO_SEARCH_TERMS")
            if not isinstance(locations, list) or not locations or not all(_nonempty(x) for x in locations):
                flags.append("UNIVERSAL_NO_SEARCH_LOCATIONS")
            counterexamples = claim.get("counterexamples")
            if not isinstance(counterexamples, list):
                errors.append(_err(f"{path}.counterexamples", "COUNTEREXAMPLE_ARRAY_REQUIRED", "universal claims need a counterexamples array"))
                counterexamples = []
            unresolved = False
            for j, counterexample in enumerate(counterexamples):
                cpath = f"{path}.counterexamples[{j}]"
                if not isinstance(counterexample, dict):
                    errors.append(_err(cpath, "COUNTEREXAMPLE_OBJECT_REQUIRED", "counterexample must be an object"))
                    unresolved = True
                    continue
                rid = counterexample.get("record_id")
                if rid not in records:
                    errors.append(_err(f"{cpath}.record_id", "UNKNOWN_COUNTEREXAMPLE_RECORD", f"no scope record named {rid}"))
                    unresolved = True
                disposition = counterexample.get("disposition")
                if disposition not in {"bounded_restatement", "conflicting_evidence", "explained_out_of_scope"}:
                    errors.append(_err(f"{cpath}.disposition", "INVALID_DISPOSITION", "use bounded_restatement, conflicting_evidence, or explained_out_of_scope"))
                    unresolved = True
                if disposition == "conflicting_evidence":
                    unresolved = True
                if not _nonempty(counterexample.get("reason")):
                    errors.append(_err(f"{cpath}.reason", "COUNTEREXAMPLE_REASON_REQUIRED", "counterexample disposition needs a reason"))
            if counterexamples:
                flags.append("UNIVERSAL_COUNTEREXAMPLE_FOUND")
                flags.append("UNSUPPORTED_GENERALIZATION")
            else:
                flags.append("NO_COUNTEREXAMPLE_FOUND_NOT_EXHAUSTIVE")
            if unresolved:
                flags.append("UNIVERSAL_UNRESOLVED_COUNTEREXAMPLE")
            if not _nonempty(claim.get("bounded_restatement")):
                flags.append("UNIVERSAL_NO_BOUNDED_RESTATEMENT")
            assessment = "unsupported_generalization" if counterexamples else "requires_adjudication"
        else:
            assessment = "bounded_or_non_universal"
        audits.append({
            "claim_id": cid,
            "universal_declared": declared,
            "assessment": assessment,
            "flags": sorted(set(flags)),
            "scope_record_ids": linked,
            "bounded_restatement": claim.get("bounded_restatement"),
        })
    return {
        "valid": not errors,
        "synthetic": claims_payload.get("synthetic") is True,
        "claim_count": len(audits),
        "claims": audits,
        "errors": errors,
        "error_count": len(errors),
        "semantic_validation": False,
        "note": "Flags are adjudication prompts. No flag-free universal is proven true or exhaustive.",
    }


def _type_ok(value: Any, expected: str) -> bool:
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
    if expected == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    if expected == "number":
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    raise InputError(f"unsupported schema type: {expected}")


SCHEMA_TYPES = {"object", "array", "string", "boolean", "null", "integer", "number"}
SCHEMA_KEYWORDS = {
    # Assertions supported by _schema_check.
    "type", "const", "enum", "required", "properties", "additionalProperties",
    "minProperties", "maxProperties", "items", "minItems", "maxItems",
    "uniqueItems", "minLength", "maxLength", "pattern", "minimum", "maximum",
    "anyOf", "oneOf", "allOf",
    # Annotations carry no validation constraint.
    "$schema", "$comment", "title", "description", "default", "examples",
}


def _schema_audit(schema: Any, path: str, errors: List[Dict[str, str]]) -> None:
    """Recursively reject schema constructs this checker cannot enforce."""
    if isinstance(schema, bool):
        return
    if not isinstance(schema, dict):
        errors.append(_err(path, "INVALID_SCHEMA", "schema must be an object or boolean"))
        return
    for keyword in schema:
        if keyword not in SCHEMA_KEYWORDS:
            errors.append(_err(
                f"{path}.{keyword}",
                "UNSUPPORTED_SCHEMA_KEYWORD",
                f"unsupported schema keyword {keyword!r}; it cannot be silently ignored",
            ))
    if "type" in schema:
        expected = schema["type"]
        types = expected if isinstance(expected, list) else [expected]
        if (
            not types
            or not all(isinstance(item, str) and item in SCHEMA_TYPES for item in types)
            or len(set(types)) != len(types)
        ):
            errors.append(_err(f"{path}.type", "INVALID_SCHEMA", "type must be a supported type or a nonempty unique array of supported types"))
    if "required" in schema:
        required = schema["required"]
        if (
            not isinstance(required, list)
            or not all(_nonempty(item) for item in required)
            or len(set(required)) != len(required)
        ):
            errors.append(_err(f"{path}.required", "INVALID_SCHEMA", "required must be a unique array of nonempty property names"))
    if "enum" in schema and (not isinstance(schema["enum"], list) or not schema["enum"]):
        errors.append(_err(f"{path}.enum", "INVALID_SCHEMA", "enum must be a nonempty array"))
    if "properties" in schema:
        properties = schema["properties"]
        if not isinstance(properties, dict):
            errors.append(_err(f"{path}.properties", "INVALID_SCHEMA", "properties must be an object"))
        else:
            for name, subschema in properties.items():
                _schema_audit(subschema, f"{path}.properties.{name}", errors)
    if "additionalProperties" in schema:
        additional = schema["additionalProperties"]
        if not isinstance(additional, (dict, bool)):
            errors.append(_err(f"{path}.additionalProperties", "INVALID_SCHEMA", "additionalProperties must be a schema object or boolean"))
        elif isinstance(additional, dict):
            _schema_audit(additional, f"{path}.additionalProperties", errors)
    if "items" in schema:
        items = schema["items"]
        if not isinstance(items, (dict, bool)):
            errors.append(_err(f"{path}.items", "INVALID_SCHEMA", "items must be one schema object or boolean applied to every array item"))
        else:
            _schema_audit(items, f"{path}.items", errors)
    for keyword in ("anyOf", "oneOf", "allOf"):
        if keyword not in schema:
            continue
        alternatives = schema[keyword]
        if not isinstance(alternatives, list) or not alternatives:
            errors.append(_err(f"{path}.{keyword}", "INVALID_SCHEMA", f"{keyword} must be a nonempty array of schemas"))
            continue
        for index, subschema in enumerate(alternatives):
            _schema_audit(subschema, f"{path}.{keyword}[{index}]", errors)
    for keyword in ("minProperties", "maxProperties", "minItems", "maxItems", "minLength", "maxLength"):
        if keyword in schema:
            constraint = schema[keyword]
            if not isinstance(constraint, int) or isinstance(constraint, bool) or constraint < 0:
                errors.append(_err(f"{path}.{keyword}", "INVALID_SCHEMA", f"{keyword} must be a nonnegative integer"))
    if "uniqueItems" in schema and not isinstance(schema["uniqueItems"], bool):
        errors.append(_err(f"{path}.uniqueItems", "INVALID_SCHEMA", "uniqueItems must be boolean"))
    if "pattern" in schema:
        pattern = schema["pattern"]
        if not isinstance(pattern, str):
            errors.append(_err(f"{path}.pattern", "INVALID_SCHEMA", "pattern must be a string"))
        else:
            try:
                re.compile(pattern)
            except re.error as exc:
                errors.append(_err(f"{path}.pattern", "INVALID_SCHEMA", f"invalid regular expression: {exc}"))
    for keyword in ("minimum", "maximum"):
        if keyword in schema:
            constraint = schema[keyword]
            if not isinstance(constraint, (int, float)) or isinstance(constraint, bool):
                errors.append(_err(f"{path}.{keyword}", "INVALID_SCHEMA", f"{keyword} must be numeric"))


def _alternative_matches(value: Any, alternatives: List[Any], path: str) -> int:
    matches = 0
    for alternative in alternatives:
        branch_errors: List[Dict[str, str]] = []
        _schema_check(value, alternative, path, branch_errors)
        if not branch_errors:
            matches += 1
    return matches


def _schema_check(value: Any, schema: Any, path: str, errors: List[Dict[str, str]]) -> None:
    if isinstance(schema, bool):
        if not schema:
            errors.append(_err(path, "SCHEMA_FALSE", "value disallowed by false schema"))
        return
    if not isinstance(schema, dict):
        raise InputError(f"schema at {path} must be an object or boolean")
    expected = schema.get("type")
    if expected is not None:
        types = expected if isinstance(expected, list) else [expected]
        if not any(_type_ok(value, item) for item in types):
            errors.append(_err(path, "TYPE_MISMATCH", f"expected {' or '.join(types)}"))
            return
    if "const" in schema and value != schema["const"]:
        errors.append(_err(path, "CONST_MISMATCH", "value differs from required const"))
    if "enum" in schema and value not in schema["enum"]:
        errors.append(_err(path, "ENUM_MISMATCH", "value is not in enum"))
    if "anyOf" in schema and _alternative_matches(value, schema["anyOf"], path) == 0:
        errors.append(_err(path, "ANY_OF_MISMATCH", "value does not satisfy any anyOf branch"))
    if "oneOf" in schema:
        matches = _alternative_matches(value, schema["oneOf"], path)
        if matches == 0:
            errors.append(_err(path, "ONE_OF_MISMATCH", "value does not satisfy any oneOf branch"))
        elif matches != 1:
            errors.append(_err(path, "ONE_OF_MULTIPLE_MATCHES", f"value satisfies {matches} oneOf branches; exactly one is required"))
    if "allOf" in schema:
        for alternative in schema["allOf"]:
            _schema_check(value, alternative, path, errors)
    if isinstance(value, dict):
        for key in schema.get("required", []):
            if key not in value:
                errors.append(_err(f"{path}.{key}", "REQUIRED_MISSING", "required field is absent"))
        props = schema.get("properties", {})
        additional = schema.get("additionalProperties", True)
        for key, item in value.items():
            if key in props:
                _schema_check(item, props[key], f"{path}.{key}", errors)
            elif additional is False:
                errors.append(_err(f"{path}.{key}", "ADDITIONAL_PROPERTY", "additionalProperties is false"))
            elif additional is not True:
                _schema_check(item, additional, f"{path}.{key}", errors)
        if "minProperties" in schema and len(value) < schema["minProperties"]:
            errors.append(_err(path, "MIN_PROPERTIES", "too few object properties"))
        if "maxProperties" in schema and len(value) > schema["maxProperties"]:
            errors.append(_err(path, "MAX_PROPERTIES", "too many object properties"))
    if isinstance(value, list):
        if "minItems" in schema and len(value) < schema["minItems"]:
            errors.append(_err(path, "MIN_ITEMS", f"expected at least {schema['minItems']} items"))
        if "maxItems" in schema and len(value) > schema["maxItems"]:
            errors.append(_err(path, "MAX_ITEMS", f"expected at most {schema['maxItems']} items"))
        if schema.get("uniqueItems") is True:
            encoded = [json.dumps(item, sort_keys=True, ensure_ascii=False) for item in value]
            if len(encoded) != len(set(encoded)):
                errors.append(_err(path, "UNIQUE_ITEMS", "array items must be unique"))
        if "items" in schema:
            for index, item in enumerate(value):
                _schema_check(item, schema["items"], f"{path}[{index}]", errors)
    if isinstance(value, str):
        if "minLength" in schema and len(value) < schema["minLength"]:
            errors.append(_err(path, "MIN_LENGTH", "string is too short"))
        if "maxLength" in schema and len(value) > schema["maxLength"]:
            errors.append(_err(path, "MAX_LENGTH", "string is too long"))
        if "pattern" in schema and re.search(schema["pattern"], value) is None:
            errors.append(_err(path, "PATTERN_MISMATCH", "string does not match pattern"))
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        if "minimum" in schema and value < schema["minimum"]:
            errors.append(_err(path, "MINIMUM", "number is below minimum"))
        if "maximum" in schema and value > schema["maximum"]:
            errors.append(_err(path, "MAXIMUM", "number is above maximum"))


def validate_contract_payload(result: Any, contract_input: Any, case_id: Optional[str] = None) -> Dict[str, Any]:
    is_case = isinstance(contract_input, dict) and "output_contract" in contract_input
    schema = contract_input["output_contract"] if is_case else contract_input
    if not isinstance(schema, (dict, bool)):
        raise InputError("contract must be a schema object or a case containing output_contract")
    errors: List[Dict[str, str]] = []
    schema_path = "case.output_contract" if is_case else "contract"
    _schema_audit(schema, schema_path, errors)
    schema_error_count = len(errors)
    if not errors:
        _schema_check(result, schema, "result", errors)
    # A runtime case requests every declared top-level result property, even if
    # its schema's standard JSON `required` list accidentally omits one.
    if not schema_error_count and is_case and isinstance(schema, dict) and isinstance(result, dict):
        required = set(schema.get("required", []))
        for key in schema.get("properties", {}):
            if key not in result and key not in required:
                errors.append(_err(
                    f"result.{key}",
                    "DECLARED_PROPERTY_MISSING",
                    "every top-level property declared by case.output_contract must be present",
                ))
    case_case_id = contract_input.get("case_id") if is_case else None
    if case_case_id is not None:
        if case_id is not None and case_id != case_case_id:
            errors.append(_err("contract.case_id", "CASE_ID_ARGUMENT_MISMATCH", f"case case_id {case_case_id!r} is authoritative, not --case-id {case_id!r}"))
        case_id = case_case_id
    if case_id is not None and (not isinstance(result, dict) or result.get("case_id") != case_id):
        errors.append(_err("result.case_id", "CASE_ID_MISMATCH", f"expected {case_id!r}"))
    return {
        "valid": not errors,
        "case_id": case_id,
        "schema_valid": schema_error_count == 0,
        "schema_error_count": schema_error_count,
        "error_count": len(errors),
        "errors": errors,
        "semantic_validation": False,
        "note": "Supported contract shape and coverage only; this does not validate scientific meaning or status honesty.",
    }


def _command(args: argparse.Namespace) -> int:
    if args.command == "validate-scope":
        payload = load_json(args.records)
        report = validate_scope_payload(payload, source_root=args.source_root)
    elif args.command == "check-claims":
        claims = load_json(args.claims)
        records = load_json(args.records)
        report = audit_claims_payload(claims, records, source_root=args.source_root)
    elif args.command == "check-contract":
        result = load_json(args.result)
        contract = load_json(args.contract)
        report = validate_contract_payload(result, contract, case_id=args.case_id)
    else:
        raise InputError("unknown command")
    write_json(args.output, report)
    print(json.dumps({"command": args.command, "valid": report["valid"], "output": args.output}, ensure_ascii=False))
    return 0 if report["valid"] else 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    scope = sub.add_parser("validate-scope", help="validate scope dimensions and anchored evidence")
    scope.add_argument("--records", required=True)
    scope.add_argument("--source-root", required=True)
    scope.add_argument("--output", required=True)
    claims = sub.add_parser("check-claims", help="audit universal coverage and counterexamples")
    claims.add_argument("--claims", required=True)
    claims.add_argument("--records", required=True)
    claims.add_argument("--source-root", required=True)
    claims.add_argument("--output", required=True)
    contract = sub.add_parser("check-contract", help="validate result against the original output contract")
    contract.add_argument("--result", required=True)
    contract.add_argument("--contract", required=True)
    contract.add_argument("--case-id")
    contract.add_argument("--output", required=True)
    return parser


def main(argv: Optional[List[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return _command(args)
    except InputError as exc:
        print(f"scope-mesh input error: {exc}", file=sys.stderr)
        return 2
    except OSError as exc:
        print(f"scope-mesh output error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
