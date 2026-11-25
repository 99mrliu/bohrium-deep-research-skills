#!/usr/bin/env python3
"""End-to-end quantity cleaning, ledger and honest output-contract adapter."""
from __future__ import annotations

import argparse
import copy
import csv
import hashlib
import json
import sys
from collections import Counter, OrderedDict
from dataclasses import dataclass, field
from decimal import Decimal, DecimalException
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from quantity_core import (
    NumberConvention, QuantityError, RoundingPolicy, convert_quantity, format_decimal,
    parse_quantity,
)

ARTIFACT_NAMES = (
    "cleaned.csv", "cleaned.json", "quantity_ledger.jsonl", "changes.jsonl",
    "review_queue.csv", "audit.md", "result.json",
)
BASE_RESULT_FIELDS = ("case_id", "status", "sources", "uncertainty", "change_records",
                      "review_queue", "artifacts")
KNOWN_CONTRACT_FIELDS = set(BASE_RESULT_FIELDS) | {
    "cleaned_data", "cleaned_records", "records", "data", "rows", "changes", "change_log",
    "summary", "errors", "row_count", "review_count", "change_count", "contract_unresolved",
}
RECORD_KEYS = {"records", "rows", "items", "measurements", "extractions", "observations",
               "data", "materials", "table", "entries"}
CONVERSION_KEYS = {"unit_conversions", "conversions", "quantity_fields", "unit_targets",
                   "target_units", "standardize", "column_units", "fields_to_convert"}
MISSING = {"", "na", "n/a", "null", "none", "missing", "not reported", "not_reported"}


class InputError(RuntimeError):
    pass


def reject_json_constant(value: str) -> None:
    raise InputError("Non-finite JSON number is forbidden: " + value)


def json_safe(value: Any) -> Any:
    if isinstance(value, Decimal):
        if not value.is_finite():
            raise InputError("Refusing non-finite Decimal output.")
        return format_decimal(value)
    if isinstance(value, float):
        if value != value or value in (float("inf"), float("-inf")):
            raise InputError("Refusing NaN/Infinity output.")
        return value
    if isinstance(value, dict):
        return {str(k): json_safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [json_safe(v) for v in value]
    return value


def dump_json(path: Path, value: Any) -> None:
    path.write_text(json.dumps(json_safe(value), ensure_ascii=False, indent=2,
                               sort_keys=True, allow_nan=False) + "\n", encoding="utf-8")


def write_jsonl(path: Path, records: Iterable[Dict[str, Any]]) -> None:
    text = "".join(json.dumps(json_safe(row), ensure_ascii=False, sort_keys=True,
                              allow_nan=False) + "\n" for row in records)
    path.write_text(text, encoding="utf-8")


def display_path(path: Path, root: Path) -> str:
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except (ValueError, OSError):
        return path.name


def load_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8-sig"), parse_float=Decimal,
                          parse_constant=reject_json_constant)
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise InputError("Cannot parse JSON %s: %s" % (path.name, exc)) from exc


def first_recursive(obj: Any, keys: Sequence[str]) -> Any:
    """Breadth-first lookup gives outer, case-level policy precedence."""
    wanted = set(keys)
    queue = [obj]
    while queue:
        current = queue.pop(0)
        if isinstance(current, dict):
            for key in keys:
                if key in current:
                    return current[key]
            queue.extend(v for k, v in current.items() if k not in RECORD_KEYS and
                         isinstance(v, (dict, list)))
        elif isinstance(current, list):
            queue.extend(v for v in current if isinstance(v, (dict, list)))
    return None


def case_identifier(case: Any) -> Optional[str]:
    if isinstance(case, dict):
        value = case.get("case_id", case.get("caseId"))
        if value is not None:
            return str(value)
        nested = case.get("case")
        if isinstance(nested, dict):
            value = nested.get("case_id", nested.get("id"))
            if value is not None:
                return str(value)
        if case.get("id") is not None:
            return str(case["id"])
    return None


def _entry(field_name: str, data: Any, fallback_target: Optional[str] = None) -> Optional[Dict[str, Any]]:
    if isinstance(data, str):
        return {"field": field_name, "target_unit": data}
    if not isinstance(data, dict):
        return None
    spec = dict(data)
    field_name = str(spec.get("field", spec.get("name", spec.get("value_field",
                     spec.get("column", field_name)))))
    target = spec.get("target_unit", spec.get("to", spec.get("target",
                 spec.get("canonical_unit", fallback_target))))
    explicit_target = target is not None
    if target is None and spec.get("unit") is not None:
        target = spec.get("unit")
    hint = spec.get("source_unit", spec.get("input_unit", spec.get("unit_hint")))
    if hint is None and explicit_target and spec.get("unit") is not None:
        hint = spec.get("unit")
    return {
        "field": field_name,
        "target_unit": str(target) if target is not None else None,
        "unit_hint": str(hint) if hint is not None else None,
        "unit_field": spec.get("unit_field", spec.get("unit_column")),
        "rounding": spec.get("rounding"),
        "report_missing": bool(spec.get("report_missing", spec.get("required", False))),
    }


def conversion_specs(case: Any) -> "OrderedDict[str, Dict[str, Any]]":
    """Read mapping/list/wrapper unit rules; only explicitly named fields."""
    found: "OrderedDict[str, Dict[str, Any]]" = OrderedDict()
    queue = [case]
    while queue:
        obj = queue.pop(0)
        if isinstance(obj, dict):
            for key, value in obj.items():
                if key in CONVERSION_KEYS:
                    if isinstance(value, dict):
                        direct = _entry("", value)
                        if direct and direct["field"]:
                            found[direct["field"]] = direct
                        else:
                            for field_name, item in value.items():
                                entry = _entry(str(field_name), item)
                                if entry and entry["target_unit"]:
                                    found[entry["field"]] = entry
                    elif isinstance(value, list):
                        for item in value:
                            entry = _entry("", item)
                            if entry and entry["field"] and entry["target_unit"]:
                                found[entry["field"]] = entry
                elif key not in RECORD_KEYS and key != "output_contract" and isinstance(value, (dict, list)):
                    queue.append(value)
        elif isinstance(obj, list):
            queue.extend(v for v in obj if isinstance(v, (dict, list)))
    return found


def _add_rows_from_json(obj: Any, source: str, locator: str,
                        rows: List[Dict[str, Any]], top_level: bool = False) -> None:
    if isinstance(obj, list):
        if obj and all(isinstance(v, dict) for v in obj):
            for index, row in enumerate(obj):
                rows.append({"data": copy.deepcopy(row), "source": source,
                             "locator": "%s[%d]" % (locator, index),
                             "ordinal": len(rows) + 1})
        return
    if not isinstance(obj, dict):
        return
    for key, value in obj.items():
        child = "%s.%s" % (locator, key)
        if key in RECORD_KEYS and isinstance(value, list):
            wrapped = bool(value) and all(isinstance(v, dict) for v in value) and any(
                any(nested in RECORD_KEYS and isinstance(v.get(nested), (dict, list))
                    for nested in v) for v in value)
            if all(isinstance(v, dict) for v in value) and not wrapped:
                _add_rows_from_json(value, source, child, rows)
            else:
                for index, item in enumerate(value):
                    if isinstance(item, (dict, list)):
                        _add_rows_from_json(item, source, "%s[%d]" % (child, index), rows)
        elif isinstance(value, dict) and key not in ("output_contract",):
            _add_rows_from_json(value, source, child, rows)


@dataclass
class Work:
    rows: List[Dict[str, Any]] = field(default_factory=list)
    ledger: List[Dict[str, Any]] = field(default_factory=list)
    changes: List[Dict[str, Any]] = field(default_factory=list)
    review: List[Dict[str, Any]] = field(default_factory=list)
    sources: List[Dict[str, Any]] = field(default_factory=list)
    unresolved: List[str] = field(default_factory=list)


def identity(row: Dict[str, Any]) -> str:
    data = row["data"]
    for key in ("row_id", "record_id", "extraction_id", "id"):
        if key in data and data[key] not in (None, ""):
            return str(data[key])
    return "%s#%s" % (row["source"], row["ordinal"])


def _is_missing(value: Any) -> bool:
    return value is None or isinstance(value, str) and value.strip().lower() in MISSING


def _looks_numeric(value: Any) -> bool:
    if not isinstance(value, str):
        return False
    text = value.strip()
    while text[:1] in ("~", "≈", "≃", "∼"):
        text = text[1:].lstrip()
    while text[:1] in ("+", "-", "−"):
        text = text[1:]
    return bool(text) and text[0] in "0123456789.,"


def canonical_unit(dimension: Dict[str, int]) -> Optional[str]:
    if dimension == {"temperature": 1}: return "K"
    if dimension == {"time": 1}: return "s"
    if dimension == {"mass": 1, "length": -1, "time": -2}: return "Pa"
    if dimension == {"mass": 1, "length": 2, "time": -2}: return "J"
    if dimension == {"length": 1}: return "m"
    if dimension == {"length": 3}: return "m^3"
    if dimension == {"amount": 1}: return "mol"
    if dimension == {"amount": 1, "length": -3}: return "mol/m^3"
    if dimension == {"amount": 1, "length": -3, "time": -1}: return "mol/m^3/s"
    return None


def contract_fields(contract: Any) -> List[str]:
    """Support direct maps, lists, JSON-schema properties, and common wrappers."""
    if contract is None:
        return []
    if isinstance(contract, list):
        result = []
        for item in contract:
            if isinstance(item, str):
                result.append(item)
            elif isinstance(item, dict):
                name = item.get("name", item.get("field", item.get("key")))
                if isinstance(name, str):
                    result.append(name)
        return list(dict.fromkeys(result))
    if not isinstance(contract, dict):
        return []
    for key in ("properties", "fields", "output_fields", "outputs"):
        if key in contract:
            return contract_fields(contract[key])
    for key in ("schema", "result", "contract"):
        if key in contract and isinstance(contract[key], (dict, list)):
            return contract_fields(contract[key])
    if "required" in contract and isinstance(contract["required"], list):
        return [str(v) for v in contract["required"] if isinstance(v, str)]
    metadata = {"type", "description", "title", "additionalProperties", "required", "$schema"}
    keys = [str(k) for k in contract if k not in metadata]
    # A single descriptive mapping is a wrapper, not an output field map.
    if not keys and isinstance(contract.get("result"), dict):
        return contract_fields(contract["result"])
    return keys


def write_csv(path: Path, columns: Sequence[str], rows: Iterable[Dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(columns), extrasaction="ignore", lineterminator="\n")
        writer.writeheader()
        for row in rows:
            output = {}
            for key in columns:
                value = row.get(key)
                if value is None:
                    output[key] = ""
                elif isinstance(value, (dict, list)):
                    output[key] = json.dumps(json_safe(value), ensure_ascii=False, sort_keys=True,
                                             allow_nan=False)
                else:
                    output[key] = str(value)
            writer.writerow(output)


REVIEW_COLUMNS = ("case_id", "row_id", "source", "source_locator", "field", "raw_value",
                  "code", "message", "status")


def write_artifacts(output: Path, work: Work, cleaned: List[Dict[str, Any]],
                    columns: Sequence[str], result: Dict[str, Any], audit: str) -> None:
    output.mkdir(parents=True, exist_ok=True)
    write_csv(output / "cleaned.csv", columns, cleaned)
    dump_json(output / "cleaned.json", cleaned)
    write_jsonl(output / "quantity_ledger.jsonl", work.ledger)
    write_jsonl(output / "changes.jsonl", work.changes)
    write_csv(output / "review_queue.csv", REVIEW_COLUMNS, work.review)
    (output / "audit.md").write_text(audit, encoding="utf-8")
    dump_json(output / "result.json", result)


def initial_result(case_id: Optional[str], contract: Any, sources: List[Dict[str, Any]]) -> Dict[str, Any]:
    fields = contract_fields(contract)
    result = {key: None for key in fields}
    unresolved = [{"code": "unresolved_contract", "field": key,
                   "message": "Unknown output-contract key is null; no producer is declared."}
                  for key in fields if key not in KNOWN_CONTRACT_FIELDS]
    result.update({"case_id": case_id, "status": "partial", "sources": sources,
                   "uncertainty": [{"code": "processing_incomplete",
                                    "message": "Early partial output; compilation has not completed."}] + unresolved,
                   "change_records": [], "review_queue": [],
                   "artifacts": {name: name for name in ARTIFACT_NAMES}, "errors": [],
                   "contract_unresolved": [item["message"] + " Field: " + item["field"] + "."
                                           for item in unresolved]})
    return result


def process(input_path: Path, output: Path, case_path: Optional[Path], task_path: Optional[Path]) -> int:
    work = Work()
    case: Any = None
    contract: Any = None
    root = input_path if input_path.is_dir() else input_path.parent
    # Read actual case/task and every supported material document deterministically.
    if not input_path.exists():
        raise InputError("Input path does not exist: " + str(input_path))
    paths = sorted(p for p in root.rglob("*") if p.is_file() and
                   p.suffix.lower() in (".json", ".jsonl", ".csv", ".tsv", ".md"))
    if case_path:
        case_path = case_path.resolve()
        if not case_path.is_file():
            raise InputError("--case does not name a file")
        case = load_json(case_path)
        if case_path not in paths:
            paths.append(case_path)
    else:
        candidate = root / "case.json" if root.is_dir() else root
        if candidate.is_file():
            case_path = candidate
            case = load_json(candidate)
    if task_path:
        task_path = task_path.resolve()
        if not task_path.is_file():
            raise InputError("--task does not name a file")
        if task_path not in paths:
            paths.append(task_path)
    if not paths:
        raise InputError("No readable case/material .json, .jsonl, .csv, .tsv or .md files were supplied.")
    case_id = case_identifier(case)
    contract = first_recursive(case, ("output_contract", "outputContract")) if case is not None else None
    paths = sorted(set(paths))
    for path in paths:
        role = "task" if (task_path and path.resolve() == task_path.resolve()) or path.name == "task.md" else (
               "case" if case_path and path.resolve() == case_path.resolve() else "material")
        raw = path.read_bytes()
        work.sources.append({"path": display_path(path, root), "role": role,
                             "sha256": hashlib.sha256(raw).hexdigest()})

    # All required artifacts exist before cell processing, with honest partial status.
    partial = initial_result(case_id, contract, work.sources)
    initial_columns = ["__row_id", "__source", "__quantity_review"]
    initial_audit = "# Quantity expression audit\n\nStatus: partial; processing has not completed.\n"
    write_artifacts(output, work, [], initial_columns, partial, initial_audit)

    # Parse source files. The case can itself hold common nested records.
    json_docs: List[Tuple[Path, Any]] = []
    if case is not None:
        json_docs.append((case_path, case))
        _add_rows_from_json(case, display_path(case_path, root), "$", work.rows, True)
    for path in paths:
        if case_path and path.resolve() == case_path.resolve():
            continue
        if task_path and path.resolve() == task_path.resolve():
            # Task prose is read and hashed, but never interpreted as a material value.
            path.read_text(encoding="utf-8-sig")
            continue
        suffix = path.suffix.lower()
        source = display_path(path, root)
        if suffix == ".json":
            data = load_json(path)
            json_docs.append((path, data))
            _add_rows_from_json(data, source, "$", work.rows, True)
        elif suffix == ".jsonl":
            try:
                lines = path.read_text(encoding="utf-8-sig").splitlines()
            except (OSError, UnicodeError) as exc:
                raise InputError("Cannot read %s: %s" % (source, exc)) from exc
            for line_number, line in enumerate(lines, 1):
                if not line.strip():
                    continue
                try:
                    data = json.loads(line, parse_float=Decimal, parse_constant=reject_json_constant)
                except json.JSONDecodeError as exc:
                    raise InputError("Invalid JSONL %s line %d: %s" % (source, line_number, exc)) from exc
                if isinstance(data, dict) and not any(k in RECORD_KEYS for k in data):
                    work.rows.append({"data": data, "source": source,
                                      "locator": "$.line[%d]" % line_number, "ordinal": len(work.rows) + 1})
                else:
                    _add_rows_from_json(data, source, "$.line[%d]" % line_number, work.rows)
        elif suffix in (".csv", ".tsv"):
            try:
                with path.open("r", encoding="utf-8-sig", newline="") as handle:
                    reader = csv.DictReader(handle, delimiter="\t" if suffix == ".tsv" else ",")
                    if not reader.fieldnames or any(h is None or h == "" for h in reader.fieldnames):
                        raise InputError("Missing/empty header in " + source)
                    for line_number, row in enumerate(reader, 2):
                        if None in row:
                            raise InputError("Extra unlabelled CSV cells in %s line %d" % (source, line_number))
                        work.rows.append({"data": dict(row), "source": source,
                                          "locator": "$.line[%d]" % line_number,
                                          "ordinal": len(work.rows) + 1})
            except (OSError, UnicodeError, csv.Error) as exc:
                raise InputError("Cannot parse table %s: %s" % (source, exc)) from exc
        elif suffix == ".md":
            path.read_text(encoding="utf-8-sig")
    if not work.rows:
        raise InputError("No material rows were found; provide a table or common nested records.")

    # Case-level conventions override any identically located material-level rules.
    merged_spec: Dict[str, Any] = {}
    for path, data in json_docs:
        if case_path is None or path.resolve() != case_path.resolve():
            region = first_recursive(data, ("number_region", "numberRegion", "numeric_locale"))
            if region is not None:
                merged_spec["number_region"] = region
            for key in ("decimal_separator", "thousands_separator", "group_separator", "rounding"):
                value = first_recursive(data, (key,))
                if value is not None:
                    merged_spec[key] = value
    if case is not None:
        for key in ("number_region", "numberRegion", "numeric_locale", "locale",
                    "decimal_separator", "thousands_separator", "group_separator", "rounding"):
            value = first_recursive(case, (key,))
            if value is not None:
                merged_spec[key] = value
    convention = NumberConvention.from_spec(merged_spec)
    rounding = RoundingPolicy.from_spec(merged_spec)
    specs: "OrderedDict[str, Dict[str, Any]]" = OrderedDict()
    for path, data in json_docs:
        if case_path is None or path.resolve() != case_path.resolve():
            specs.update(conversion_specs(data))
    if case is not None:
        specs.update(conversion_specs(case))  # Actual case rules have final precedence.

    cleaned: List[Dict[str, Any]] = []
    columns: List[str] = []
    for row in work.rows:
        for key in row["data"]:
            if key not in columns:
                columns.append(key)
    for extra in ("__row_id", "__source", "__quantity_review"):
        if extra not in columns:
            columns.append(extra)

    for row in work.rows:
        original = row["data"]
        clean = copy.deepcopy(original)
        rid = identity(row)
        clean["__row_id"] = rid
        clean["__source"] = row["source"]
        codes_for_row: List[str] = []
        fields_to_process = list(specs) if specs else [
            key for key, value in original.items() if _looks_numeric(value)]
        for field_name in fields_to_process:
            spec = specs.get(field_name, {})
            raw = original.get(field_name)
            base = {"case_id": case_id, "row_id": rid, "source": row["source"],
                    "source_locator": row["locator"] + "." + field_name, "field": field_name}
            if field_name not in original or _is_missing(raw):
                # Sparse records often legitimately omit unrelated configured fields.
                # Present blanks stay blank and enter the ledger; review is opt-in so
                # an optional blank is not confused with an actionable extraction defect.
                if field_name not in original and not spec.get("report_missing"):
                    continue
                code = "missing_field" if field_name not in original else "missing_value"
                message = "Configured field is absent." if field_name not in original else "Missing remains empty; zero was not substituted."
                ledger = dict(base, raw_lexeme=raw, status="missing", code=code,
                              review_required=bool(spec.get("report_missing")),
                              formula_trace=None, output_value=raw)
                work.ledger.append(ledger)
                if spec.get("report_missing"):
                    work.review.append(dict(base, raw_value=raw, code=code, message=message, status="open"))
                    codes_for_row.append(code)
                continue
            unit_hint = spec.get("unit_hint")
            if spec.get("unit_field"):
                unit_hint = original.get(spec["unit_field"])
            is_auto = not specs
            try:
                quantity = parse_quantity(str(raw), convention, str(unit_hint) if unit_hint else None)
                target = spec.get("target_unit") or canonical_unit(quantity.unit.dimension)
                if target is None:
                    raise QuantityError("no_safe_canonical_unit",
                                        "No explicit target and no safe canonical spelling for this dimension.")
                local_rounding = RoundingPolicy.from_spec({"rounding": spec["rounding"]}) if spec.get("rounding") else rounding
                converted = convert_quantity(quantity, str(target), local_rounding)
                clean[field_name] = converted.expression
                parsed = {
                    "kind": quantity.kind, "approximate": quantity.approximate,
                    "value": format_decimal(quantity.value),
                    "interval_high": format_decimal(quantity.interval_high) if quantity.interval_high is not None else None,
                    "uncertainty": format_decimal(quantity.uncertainty) if quantity.uncertainty is not None else None,
                    "source_unit": quantity.unit.symbol,
                    "target_unit": converted.target.symbol,
                    "converted_values": [format_decimal(v) for v in converted.values],
                    "converted_uncertainty": format_decimal(converted.uncertainty) if converted.uncertainty is not None else None,
                }
                ledger = dict(base, raw_lexeme=str(raw), raw_unit=quantity.unit.symbol,
                              status="converted", code=None, parsed=parsed,
                              dimension=quantity.unit.dimension, output_value=converted.expression,
                              uncertainty=parsed["converted_uncertainty"], formula_trace=converted.trace,
                              rule_ids=["QEC-PARSE-001", "QEC-UNIT-002", "QEC-ROUND-003"])
                work.ledger.append(ledger)
                if str(raw) != converted.expression:
                    work.changes.append(dict(base, before=str(raw), after=converted.expression,
                                             raw_lexeme=str(raw), uncertainty=parsed["converted_uncertainty"],
                                             formula_trace=converted.trace,
                                             rule_ids=["QEC-PARSE-001", "QEC-UNIT-002", "QEC-ROUND-003"]))
            except (QuantityError, DecimalException) as exc:
                if is_auto and isinstance(exc, QuantityError) and exc.code == "missing_unit":
                    continue  # Plain numeric strings are not auto-labelled as measurements.
                code = exc.code if isinstance(exc, QuantityError) else "decimal_arithmetic_error"
                message = str(exc)
                work.ledger.append(dict(base, raw_lexeme=str(raw), status="unresolved", code=code,
                                        formula_trace=None, output_value=raw))
                work.review.append(dict(base, raw_value=str(raw), code=code, message=message, status="open"))
                codes_for_row.append(code)
        clean["__quantity_review"] = ";".join(dict.fromkeys(codes_for_row))
        cleaned.append(clean)

    unresolved_contract = []
    result = {key: None for key in contract_fields(contract)}
    known = {
        "case_id": case_id, "cleaned_data": cleaned, "cleaned_records": cleaned,
        "records": cleaned, "data": cleaned, "rows": cleaned,
        "sources": work.sources, "uncertainty": work.review,
        "changes": work.changes, "change_log": work.changes, "change_records": work.changes,
        "review_queue": work.review, "artifacts": {name: name for name in ARTIFACT_NAMES},
        "review_count": len(work.review), "change_count": len(work.changes),
        "summary": {"rows": len(cleaned), "converted_cells": len(work.changes),
                    "review_items": len(work.review)},
    }
    for key in list(result):
        if key in known:
            result[key] = known[key]
        elif key not in KNOWN_CONTRACT_FIELDS:
            unresolved_contract.append("output_contract.%s is null: no declared producer for this key." % key)
    status = "partial" if work.review or case_id is None else "success"
    if case_id is None:
        work.unresolved.append("case_id is null because no case identifier was supplied.")
    result.update({
        "case_id": case_id, "status": status, "sources": work.sources,
        "uncertainty": work.review + [{"code": "unresolved_contract", "message": v} for v in unresolved_contract] +
                     [{"code": "missing_case_id", "message": v} for v in work.unresolved],
        "change_records": work.changes, "review_queue": work.review,
        "artifacts": {name: name for name in ARTIFACT_NAMES},
        "errors": [], "contract_unresolved": unresolved_contract + work.unresolved,
        "row_count": len(cleaned),
    })
    if unresolved_contract and status == "success":
        result["status"] = "partial"
    counts = Counter(item["code"] for item in work.review)
    audit_lines = [
        "# Quantity expression audit", "",
        "Status: **%s**." % result["status"],
        "Case: %s." % (case_id if case_id is not None else "not supplied"), "",
        "## Scope", "",
        "Only typed quantity cells are changed. Identity is preserved; no deduplication, entity merging, scientific-conflict adjudication or missing-value imputation is attempted.",
        "Case unit/number-region rules take precedence over material defaults. Unknown units and ambiguous numbers remain raw and enter review.", "",
        "## Deterministic rule trace", "",
        "- `QEC-PARSE-001`: stateful tokenization; recursive-descent quantity/unit parsing; conservative number-region handling.",
        "- `QEC-UNIT-002`: exponent-vector dimensional check and explicit Decimal linear/affine conversion; interval reversal for a negative multiplier.",
        "- `QEC-ROUND-003`: %s, digits/places=%d, ROUND_HALF_EVEN." % (rounding.mode, rounding.digits), "",
        "## Counts", "",
        "- Rows: %d" % len(cleaned),
        "- Ledger entries: %d" % len(work.ledger),
        "- Changed cells: %d" % len(work.changes),
        "- Review items: %d" % len(work.review), "",
        "## Review codes", "",
    ]
    audit_lines += ["- `%s`: %d" % (key, counts[key]) for key in sorted(counts)] or ["- None."]
    audit_lines += ["", "## Sources", ""]
    audit_lines += ["- `%s` (%s), SHA-256 `%s`" % (s["path"], s["role"], s["sha256"]) for s in work.sources]
    audit_lines += ["", "## Limits", "",
        "The registry rejects unknown units. Missing data are not zero. Rounding controls presentation, not measurement confidence.",
        "No automatic inference is made from task prose or field names alone; auto mode requires an embedded, registered unit.", ""]
    write_artifacts(output, work, cleaned, columns, result, "\n".join(audit_lines))
    return 0


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Compile typed quantity expressions and emit an algebraic ledger.")
    parser.add_argument("--input", default="/input")
    parser.add_argument("--work", default="/app/work")
    parser.add_argument("--output", default="/app/output")
    parser.add_argument("--case", default=None)
    parser.add_argument("--task", default=None)
    args = parser.parse_args(argv)
    output = Path(args.output)
    case_path = Path(args.case) if args.case else None
    task_path = Path(args.task) if args.task else None
    try:
        # --work is contractual scratch space; deterministic processing needs no cache.
        return process(Path(args.input), output, case_path, task_path)
    except Exception as exc:
        if isinstance(exc, (KeyboardInterrupt, SystemExit)):
            raise
        case = None; case_id = None; contract = None
        if case_path and case_path.is_file():
            try:
                case = load_json(case_path)
            except Exception:
                case = None
        elif Path(args.input).is_dir() and (Path(args.input) / "case.json").is_file():
            try:
                case = load_json(Path(args.input) / "case.json")
            except Exception:
                case = None
        if isinstance(case, dict):
            case_id = case_identifier(case)
            contract = first_recursive(case, ("output_contract", "outputContract"))
        message = str(exc)
        work = Work(review=[{"row_id": "", "source": "", "source_locator": "", "field": "",
                             "raw_value": "", "code": "invalid_input", "message": message, "status": "open"}])
        result = initial_result(case_id, contract, [])
        unresolved = list(result.get("contract_unresolved", []))
        result.update({"status": "input_error",
                       "uncertainty": work.review + [item for item in result.get("uncertainty", [])
                                                      if item.get("code") == "unresolved_contract"],
                       "review_queue": work.review, "errors": [message],
                       "contract_unresolved": unresolved + ["Processing could not start or complete: " + message]})
        audit = "# Quantity expression audit\n\nStatus: **input_error**.\n\nInvalid input; no values were inferred.\n\n%s\n" % message
        try:
            write_artifacts(output, work, [], ["__row_id", "__source", "__quantity_review"], result, audit)
        except Exception as output_exc:
            print("quantity-expression-lab: %s; output failure: %s" % (exc, output_exc), file=sys.stderr)
            return 2
        print("quantity-expression-lab: " + message, file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
