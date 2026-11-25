#!/usr/bin/env python3
"""Conservative candidate generation and independent metamorphic verification.

Python 3 standard library only. No network, wall clock, or randomness is used.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import re
import sys
import unicodedata
from collections import Counter, defaultdict
from copy import deepcopy
from decimal import Decimal, InvalidOperation
from pathlib import Path

LABEL = "SYNTHETIC_EXAMPLE_NOT_OFFICIAL_CASE"
REQUIRED_ARTIFACTS = (
    "cleaned.csv", "cleaned.json", "verification.json", "counterexamples.jsonl",
    "changes.jsonl", "review_queue.csv", "audit.md", "result.json",
)
MISSING_TOKENS = {"", "na", "n/a", "n.a.", "null", "none", "nan", "-", "--"}
SEVERITY_RANK = {"BLOCKER": 0, "HIGH": 1, "MEDIUM": 2, "LOW": 3}
TEST_ORDER = (
    "row_conservation_disposition_partition",
    "raw_value_immutability",
    "no_fabricated_missing",
    "unit_conversion_recomputation",
    "dedup_context_non_interference",
    "deterministic_rerun",
    "column_order_row_order_metamorphic_invariance",
    "whitespace_noise_metamorphism",
    "json_finite_value_completeness",
    "review_coverage",
    "source_locator_validity",
)
TEST_DESCRIPTIONS = {
    "row_conservation_disposition_partition": "Every raw row is exactly one of kept, duplicate, or rejected.",
    "raw_value_immutability": "Only outer-whitespace trimming and declared derivations may alter raw values.",
    "no_fabricated_missing": "A missing raw value cannot become substantive without a declared derivation.",
    "unit_conversion_recomputation": "Declared unit conversions are independently recomputed with decimal arithmetic.",
    "dedup_context_non_interference": "Only full-row duplicates inside the same configured context may be removed.",
    "deterministic_rerun": "Fresh normalization runs emit identical semantic records and changes.",
    "column_order_row_order_metamorphic_invariance": "Input row/column permutations preserve semantic content and group counts.",
    "whitespace_noise_metamorphism": "Padding and irrelevant columns do not change normalized original fields.",
    "json_finite_value_completeness": "JSON is strict, finite, complete, and agrees with CSV.",
    "review_coverage": "Every counterexample and reviewable exclusion/derivation has a queue entry.",
    "source_locator_validity": "Each kept row resolves to exactly one existing raw source row.",
}


class InvalidInput(Exception):
    pass


class StrictJSON:
    @staticmethod
    def pairs(pairs):
        out = {}
        for key, value in pairs:
            if key in out:
                raise InvalidInput("duplicate JSON key: " + str(key))
            out[key] = value
        return out

    @classmethod
    def loads(cls, text):
        def bad_constant(value):
            raise InvalidInput("non-finite JSON constant: " + value)
        try:
            return json.loads(text, object_pairs_hook=cls.pairs, parse_constant=bad_constant)
        except (json.JSONDecodeError, InvalidInput) as exc:
            raise InvalidInput(str(exc)) from exc


def clean_text(value):
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)
    return unicodedata.normalize("NFC", str(value)).strip()


def is_missing(value):
    return clean_text(value).casefold() in MISSING_TOKENS


def raw_text(value):
    """Stringify without trimming; raw evidence and candidate cells stay observable."""
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)
    return unicodedata.normalize("NFC", str(value))


def scalar_text(value):
    if value is None:
        return ""
    return clean_text(value)


def finite_tree(value, path="$"):
    if isinstance(value, float) and not math.isfinite(value):
        raise InvalidInput("non-finite number at " + path)
    if isinstance(value, dict):
        for key, child in value.items():
            finite_tree(child, path + "." + str(key))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            finite_tree(child, path + "[" + str(index) + "]")


def canonical(value):
    finite_tree(value)
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def sha256(path):
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_text(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8", newline="\n")


def write_json(path, value):
    finite_tree(value)
    write_text(path, json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False) + "\n")


def write_jsonl(path, rows):
    write_text(path, "".join(json.dumps(row, ensure_ascii=False, sort_keys=True, allow_nan=False) + "\n" for row in rows))


def write_csv(path, fieldnames, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="ignore", lineterminator="\n")
        writer.writeheader()
        for row in rows:
            writer.writerow({key: scalar_text(row.get(key, "")) for key in fieldnames})


def read_json(path):
    try:
        value = StrictJSON.loads(path.read_text(encoding="utf-8-sig"))
        finite_tree(value)
        return value
    except (OSError, UnicodeError) as exc:
        raise InvalidInput("cannot read JSON " + path.name + ": " + str(exc)) from exc


def deep_unwrap_json(value):
    """Only unwrap explicit transport wrappers; never discard sibling payload keys."""
    if isinstance(value, str) and value.lstrip().startswith(("{", "[")):
        try:
            return StrictJSON.loads(value)
        except InvalidInput:
            return value
    return value


def unwrap_case(value):
    value = deep_unwrap_json(value)
    if not isinstance(value, dict):
        raise InvalidInput("case/task must be a JSON object")
    for key in ("case", "task", "config", "payload"):
        child = value.get(key)
        if isinstance(child, str):
            child = deep_unwrap_json(child)
        if isinstance(child, dict):
            merged = {k: v for k, v in value.items() if k != key}
            merged.update(child)
            return merged
    return value


def parse_text_case(path):
    text = path.read_text(encoding="utf-8-sig")
    try:
        return unwrap_case(StrictJSON.loads(text))
    except InvalidInput:
        pass
    result = {"task_text": text}
    for key in ("case_id", "task_id", "id"):
        match = re.search(r"(?im)^\s*" + key + r"\s*:\s*['\"]?([^\s'\"]+)", text)
        if match:
            result["case_id"] = match.group(1)
            break
    match = re.search(r"(?is)```(?:json)?\s*(\{.*?\})\s*```", text)
    if match:
        try:
            embedded = unwrap_case(StrictJSON.loads(match.group(1)))
            result.update(embedded)
        except InvalidInput:
            result["unparsed_embedded_contract"] = True
    return result


def discover_case(input_root, case_arg, task_arg):
    paths = []
    for supplied in (case_arg, task_arg):
        if supplied:
            path = Path(supplied)
            if not path.is_absolute():
                candidate = Path(supplied)
                if not candidate.exists():
                    candidate = input_root / supplied
                path = candidate
            if not path.is_file():
                raise InvalidInput("case/task file not found: " + str(supplied))
            paths.append(path)
    if not paths:
        for name in ("case.json", "task.json", "case_info.json", "input.json", "case.md", "task.md", "case.txt", "task.txt"):
            path = input_root / name
            if path.is_file():
                paths.append(path)
    if not paths:
        raise InvalidInput("no case/task file found")
    merged = {}
    used = []
    for path in paths:
        if path.suffix.lower() == ".json":
            part = unwrap_case(read_json(path))
        else:
            part = parse_text_case(path)
        if path.name == "input.json" and not any(k in part for k in ("case_id", "task_id", "output_contract", "materials", "unit_conversions")):
            continue
        merged.update(part)
        used.append(path)
    if not used:
        raise InvalidInput("no recognizable case/task object found")
    merged["_case_files"] = used
    return merged


def get_case_id(case):
    for key in ("case_id", "task_id", "id", "challenge_id"):
        value = case.get(key)
        if isinstance(value, (str, int)) and str(value).strip():
            return str(value).strip()
    return "unknown_case"


def contract_keys(contract):
    keys = []
    def visit(value):
        value = deep_unwrap_json(value)
        if isinstance(value, str):
            if value.strip():
                keys.append(value.strip())
        elif isinstance(value, list):
            for child in value:
                visit(child)
        elif isinstance(value, dict):
            if "name" in value and len(set(value) & {"type", "required", "description", "path"}) > 0:
                keys.append(str(value["name"]))
                return
            wrapper_keys = [k for k in ("fields", "properties", "outputs", "artifacts", "files", "required") if k in value]
            wrapper_controls = {"fields", "properties", "outputs", "artifacts", "files", "required", "type", "description", "title", "additionalProperties"}
            if wrapper_keys and set(value).issubset(wrapper_controls):
                for key in wrapper_keys:
                    visit(value[key])
            else:
                for key, descriptor in value.items():
                    if key in {"type", "description", "title", "additionalProperties"}:
                        continue
                    keys.append(str(key))
    visit(contract)
    return list(dict.fromkeys(keys))


KNOWN_CONTRACT = {
    "cleanedcsv": "cleaned.csv", "cleanedjson": "cleaned.json",
    "verification": "verification.json", "verificationjson": "verification.json",
    "counterexamples": "counterexamples.jsonl", "counterexamplesjsonl": "counterexamples.jsonl",
    "changes": "changes.jsonl", "changesjsonl": "changes.jsonl", "changerecords": "changes.jsonl",
    "reviewqueue": "review_queue.csv", "reviewqueuecsv": "review_queue.csv",
    "audit": "audit.md", "auditmd": "audit.md", "result": "result.json", "resultjson": "result.json",
}


def contract_value(key):
    normalized = re.sub(r"[^a-z0-9]", "", key.casefold())
    return KNOWN_CONTRACT.get(normalized)


def base_result(case_id, case):
    result = {
        "case_id": case_id,
        "status": "partial",
        "verification_status": "not_run",
        "sources": [],
        "uncertainty": ["Early checkpoint: processing and independent verification are incomplete."],
        "change_records": [],
        "review_queue": [],
        "artifacts": {},
        "unresolved_output_contract_fields": [],
    }
    if case.get("example_label") == LABEL:
        result["example_label"] = LABEL
    for key in contract_keys(case.get("output_contract")):
        if key not in result:
            result[key] = contract_value(key)
            if result[key] is None:
                result["unresolved_output_contract_fields"].append(key)
    return result


def source_descriptor(path, root, kind, rows=None):
    try:
        name = path.resolve().relative_to(root.resolve()).as_posix()
    except (ValueError, OSError):
        name = path.name
    item = {"path": name, "kind": kind, "sha256": sha256(path)}
    if rows is not None:
        item["rows"] = rows
    return item


def records_from_json(value):
    value = deep_unwrap_json(value)
    if isinstance(value, list):
        return value
    if isinstance(value, dict):
        for key in ("materials", "records", "rows", "items", "documents", "papers", "entries", "results", "data", "payload", "content", "body"):
            if key in value:
                child = deep_unwrap_json(value[key])
                if isinstance(child, list):
                    return child
                if isinstance(child, dict):
                    nested = records_from_json(child)
                    if nested != [child]:
                        return nested
        return [value]
    return [{"value": value}]


def load_materials(input_root, case_paths, case=None):
    data = []
    sources = []
    columns = []
    excluded = {p.resolve() for p in case_paths}
    paths = sorted((p for p in input_root.rglob("*") if p.is_file() and p.suffix.lower() in {".csv", ".tsv", ".json", ".jsonl"}), key=lambda p: p.as_posix())
    found = False

    def append_rows(rows, rel):
        for source_row, item in enumerate(rows, 1):
            if not isinstance(item, dict):
                item = {"value": item}
            finite_tree(item)
            values = {str(key): raw_text(value) for key, value in item.items()}
            for key in values:
                if key not in columns:
                    columns.append(key)
            ordinal = len(data) + 1
            data.append({
                "values": values, "source_file": rel, "source_row": source_row,
                "source_id": rel + "::row=" + str(source_row), "ordinal": ordinal,
            })

    # Embedded extraction records are raw evidence too; only explicit record
    # containers are accepted so case configuration never becomes a fake row.
    if isinstance(case, dict):
        case_name = next((p.name for p in case_paths if p.suffix.lower() == ".json"), "case.json")
        for key in ("records", "rows", "items", "extractions", "observations", "data"):
            if key not in case:
                continue
            rows = records_from_json(case[key])
            append_rows(rows, case_name + "#/" + key)
            found = True

    for path in paths:
        if path.resolve() in excluded:
            continue
        rel = path.relative_to(input_root).as_posix()
        if path.name in REQUIRED_ARTIFACTS or path.name in {"case.json", "task.json", "case_info.json", "input.json"}:
            continue
        found = True
        rows = []
        if path.suffix.lower() in {".csv", ".tsv"}:
            try:
                with path.open("r", encoding="utf-8-sig", newline="") as handle:
                    reader = csv.DictReader(handle, delimiter="\t" if path.suffix.lower() == ".tsv" else ",")
                    if not reader.fieldnames:
                        raise InvalidInput("missing CSV/TSV header: " + rel)
                    if len(reader.fieldnames) != len(set(reader.fieldnames)) or None in reader.fieldnames:
                        raise InvalidInput("duplicate/invalid CSV/TSV header: " + rel)
                    for row in reader:
                        if None in row:
                            raise InvalidInput("too many delimited fields in " + rel)
                        rows.append(row)
            except (OSError, UnicodeError, csv.Error) as exc:
                raise InvalidInput("cannot parse " + rel + ": " + str(exc)) from exc
        elif path.suffix.lower() == ".jsonl":
            try:
                for line_number, line in enumerate(path.read_text(encoding="utf-8-sig").splitlines(), 1):
                    if line.strip():
                        rows.extend(records_from_json(StrictJSON.loads(line)))
            except (OSError, UnicodeError) as exc:
                raise InvalidInput("cannot read " + rel + ": " + str(exc)) from exc
        else:
            rows = records_from_json(read_json(path))
        append_rows(rows, rel)
        sources.append(source_descriptor(path, input_root, "material", len(rows)))
    if not found:
        raise InvalidInput("no external or embedded CSV/TSV/JSON/JSONL materials found")
    if not data:
        raise InvalidInput("materials contain zero data rows")
    return data, columns, sources


def conversion_specs(case):
    raw = case.get("unit_conversions", case.get("units", []))
    if isinstance(raw, dict):
        raw = raw.get("conversions", raw.get("fields", [raw] if "source_field" in raw else []))
    specs = []
    if not isinstance(raw, list):
        return specs
    for index, item in enumerate(raw, 1):
        if not isinstance(item, dict):
            continue
        source = item.get("source_field", item.get("from_field"))
        target = item.get("target_field", item.get("to_field"))
        if not source or not target:
            continue
        try:
            factor = Decimal(str(item.get("factor", "1")))
            offset = Decimal(str(item.get("offset", "0")))
        except InvalidOperation as exc:
            raise InvalidInput("invalid unit conversion factor/offset") from exc
        if not factor.is_finite() or not offset.is_finite():
            raise InvalidInput("non-finite unit conversion")
        specs.append({
            "id": str(item.get("id", "UNIT" + str(index))),
            "source_field": str(source), "target_field": str(target),
            "from_unit": str(item.get("from_unit", "")), "to_unit": str(item.get("to_unit", "")),
            "factor": factor, "offset": offset,
        })
    return specs


def dedup_spec(case):
    raw = case.get("dedup", case.get("deduplication", {}))
    if not isinstance(raw, dict) or not raw.get("enabled", bool(raw.get("keys"))):
        return {"enabled": False, "keys": [], "context_keys": []}
    keys = raw.get("keys", raw.get("key_fields", []))
    context = raw.get("context_keys", raw.get("context", []))
    if isinstance(keys, str):
        keys = [keys]
    if isinstance(context, str):
        context = [context]
    if not isinstance(keys, list) or not isinstance(context, list) or not keys:
        raise InvalidInput("dedup keys must be a nonempty list")
    return {"enabled": True, "keys": [str(k) for k in keys], "context_keys": [str(k) for k in context]}


def decimal_text(value):
    normalized = format(value, "f")
    if "." in normalized:
        normalized = normalized.rstrip("0").rstrip(".")
    return normalized or "0"


def parse_decimal(value):
    try:
        number = Decimal(clean_text(value))
    except (InvalidOperation, ValueError):
        return None
    return number if number.is_finite() else None


def normalize(raw_records, columns, conversions, dedup):
    normalized_records = []
    changes = []
    change_counter = 0
    def next_change_id():
        nonlocal change_counter
        change_counter += 1
        return "CHG" + str(change_counter).zfill(6)
    seen = {}
    for raw in raw_records:
        values = {column: clean_text(raw["values"].get(column, "")) for column in columns}
        for column in columns:
            original = raw_text(raw["values"].get(column, ""))
            if original != values[column]:
                changes.append({
                    "change_id": next_change_id(), "type": "outer_whitespace_trim",
                    "source_id": raw["source_id"], "source_locator": raw["source_id"],
                    "field": column, "old": original, "new": values[column],
                    "disposition": "kept", "review_required": False,
                    "rationale": "Removed leading/trailing Unicode whitespace only.",
                })
        derived_fields = {}
        for spec in conversions:
            source = spec["source_field"]
            target = spec["target_field"]
            if source not in values or target not in values:
                continue
            number = parse_decimal(values[source])
            if number is not None and is_missing(values[target]):
                result = decimal_text(number * spec["factor"] + spec["offset"])
                values[target] = result
                derived_fields[target] = spec["id"]
                changes.append({
                    "change_id": next_change_id(), "type": "declared_unit_derivation",
                    "source_id": raw["source_id"], "source_locator": raw["source_id"],
                    "field": target, "old": raw_text(raw["values"].get(target, "")), "new": result,
                    "conversion_id": spec["id"], "disposition": "kept", "review_required": True,
                    "rationale": "Recomputable declared conversion; not observational imputation.",
                })
        duplicate_of = None
        if dedup["enabled"]:
            key = tuple(values.get(k, "") for k in dedup["keys"])
            context = tuple(values.get(k, "") for k in dedup["context_keys"])
            full = tuple(values.get(k, "") for k in columns)
            signature = (key, context, full)
            if signature in seen:
                duplicate_of = seen[signature]
            else:
                seen[signature] = raw["source_id"]
        record = dict(values)
        record.update({
            "_source_id": raw["source_id"], "_source_file": raw["source_file"],
            "_source_row": str(raw["source_row"]),
            "_disposition": "duplicate" if duplicate_of else "kept",
            "_ordinal": raw["ordinal"],
            "_derived_fields": derived_fields,
        })
        normalized_records.append(record)
        if duplicate_of:
            changes.append({
                "change_id": next_change_id(), "type": "exact_context_duplicate",
                "source_id": raw["source_id"], "source_locator": raw["source_id"],
                "duplicate_of": duplicate_of, "disposition": "duplicate", "review_required": True,
                "rationale": "Full normalized row and configured key/context are identical.",
            })
    kept = [record for record in normalized_records if record["_disposition"] == "kept"]
    return kept, normalized_records, changes


def public_record(record, columns):
    return {key: record.get(key, "") for key in (
        list(columns) + ["_source_id", "_source_file", "_source_row", "_disposition"]
    )}


def projection(records, columns):
    return sorted(canonical({key: record.get(key, "") for key in columns}) for record in records)


def disposition_projection(records, columns):
    counts = Counter()
    for record in records:
        signature = canonical({key: record.get(key, "") for key in columns})
        counts[(signature, record["_disposition"])] += 1
    return sorted((key[0], key[1], count) for key, count in counts.items())


def generate_candidate(output, raw_records, columns, conversions, dedup):
    kept, _, changes = normalize(raw_records, columns, conversions, dedup)
    rows = [public_record(record, columns) for record in kept]
    fields = list(columns) + ["_source_id", "_source_file", "_source_row", "_disposition"]
    write_csv(output / "cleaned.csv", fields, rows)
    write_json(output / "cleaned.json", {"cleaned": rows, "row_count": len(rows)})
    write_jsonl(output / "changes.jsonl", changes)
    return rows, changes


def read_csv_artifact(path):
    if not path.is_file():
        raise InvalidInput("missing candidate cleaned.csv")
    try:
        with path.open("r", encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle)
            if not reader.fieldnames or len(reader.fieldnames) != len(set(reader.fieldnames)):
                raise InvalidInput("invalid or duplicate cleaned.csv header")
            rows = []
            for row in reader:
                if None in row:
                    raise InvalidInput("too many CSV fields in cleaned.csv")
                rows.append({str(k): raw_text(v) for k, v in row.items()})
            return list(reader.fieldnames), rows
    except (OSError, UnicodeError, csv.Error) as exc:
        raise InvalidInput("cannot reload cleaned.csv: " + str(exc)) from exc


def read_changes(path):
    if not path.is_file():
        raise InvalidInput("missing changes.jsonl")
    rows = []
    try:
        for line_number, line in enumerate(path.read_text(encoding="utf-8-sig").splitlines(), 1):
            if not line.strip():
                continue
            value = StrictJSON.loads(line)
            finite_tree(value, "$.line[" + str(line_number) + "]")
            if not isinstance(value, dict):
                raise InvalidInput("changes.jsonl line is not an object")
            if value.get("type") == "synthetic_example_notice":
                continue
            rows.append(value)
    except (OSError, UnicodeError) as exc:
        raise InvalidInput("cannot reload changes.jsonl: " + str(exc)) from exc
    return rows


class Verification:
    def __init__(self):
        self.failures = []
        self.checks = []
    def fail(self, check, severity, message, expected=None, observed=None, source_locator="", raw=None, candidate=None):
        self.failures.append({
            "counterexample_id": "CE" + str(len(self.failures) + 1).zfill(6),
            "check": check, "severity": severity, "blocking_impact": severity in {"BLOCKER", "HIGH"},
            "message": message, "expected": expected, "observed": observed,
            "source_locator": source_locator, "raw": raw, "candidate": candidate,
        })
    def finish(self):
        for check in TEST_ORDER:
            failures = [item for item in self.failures if item["check"] == check]
            self.checks.append({
                "test_id": check, "description": TEST_DESCRIPTIONS[check],
                "status": "fail" if failures else "pass", "failure_count": len(failures),
            })


def candidate_json_rows(value):
    if isinstance(value, list):
        rows = value
    elif isinstance(value, dict):
        rows = None
        for key in ("cleaned", "records", "rows", "data", "items"):
            if key in value and isinstance(value[key], list):
                rows = value[key]
                break
        if rows is None:
            raise InvalidInput("cleaned.json lacks a cleaned/records/rows/data/items list")
    else:
        raise InvalidInput("cleaned.json must be a list or common wrapper object")
    if not all(isinstance(row, dict) for row in rows):
        raise InvalidInput("every cleaned JSON row must be an object")
    return rows


def compare_number(actual, expected):
    left = parse_decimal(actual)
    right = parse_decimal(expected)
    if left is None or right is None:
        return clean_text(actual) == clean_text(expected)
    tolerance = max(Decimal("0.000000001"), abs(right) * Decimal("0.000000001"))
    return abs(left - right) <= tolerance


def verify_candidate(raw_records, columns, conversions, dedup, output):
    v = Verification()
    by_id = {raw["source_id"]: raw for raw in raw_records}
    rows = []
    json_rows = None
    changes = []
    csv_fields = []
    try:
        csv_fields, rows = read_csv_artifact(output / "cleaned.csv")
    except InvalidInput as exc:
        v.fail("row_conservation_disposition_partition", "BLOCKER", str(exc), "reloadable CSV", "unavailable")
    try:
        value = read_json(output / "cleaned.json")
        json_rows = candidate_json_rows(value)
    except InvalidInput as exc:
        v.fail("json_finite_value_completeness", "BLOCKER", str(exc), "strict complete JSON", "invalid/unavailable")
    try:
        changes = read_changes(output / "changes.jsonl")
    except InvalidInput as exc:
        v.fail("row_conservation_disposition_partition", "BLOCKER", str(exc), "reloadable changes JSONL", "invalid/unavailable")

    mapped = {}
    used_candidates = set()
    pending = []
    buckets = defaultdict(list)
    for raw in raw_records:
        expected = normalize([raw], columns, conversions, {"enabled": False, "keys": [], "context_keys": []})[0]
        if expected:
            signature = canonical({key: expected[0].get(key, "") for key in columns})
            buckets[signature].append(raw["source_id"])
    for index, row in enumerate(rows):
        source_id = row.get("_source_id", "")
        if source_id:
            if source_id not in by_id:
                v.fail("source_locator_validity", "BLOCKER", "Candidate source ID does not resolve.", "known raw source ID", source_id, source_id, candidate=row)
                continue
            if source_id in mapped:
                v.fail("row_conservation_disposition_partition", "BLOCKER", "Raw row kept more than once.", "one disposition", "duplicate kept row", source_id, candidate=row)
                continue
            mapped[source_id] = index
            used_candidates.add(index)
        else:
            signature = canonical({key: clean_text(row.get(key, "")) for key in columns})
            choices = [sid for sid in buckets.get(signature, []) if sid not in mapped]
            if len(choices) == 1:
                mapped[choices[0]] = index
                used_candidates.add(index)
            elif len(choices) > 1:
                choice = sorted(choices)[0]
                mapped[choice] = index
                used_candidates.add(index)
                pending.append((choice, index))
            else:
                v.fail("source_locator_validity", "BLOCKER", "Unlabelled candidate row cannot be matched to a raw row.", "normalized raw row match", "no unique match", candidate=row)
    for source_id, index in pending:
        v.fail("source_locator_validity", "HIGH", "Unlabelled candidate mapping is ambiguous among identical raw rows.", "explicit _source_id", "ambiguous deterministic fallback", source_id, candidate=rows[index])

    accounted = defaultdict(list)
    for source_id, index in mapped.items():
        if rows[index].get("_disposition", "kept") != "kept":
            v.fail("row_conservation_disposition_partition", "BLOCKER", "A row in cleaned output is not marked kept.", "kept", rows[index].get("_disposition"), source_id)
        accounted[source_id].append("kept")
    for change in changes:
        disposition = change.get("disposition")
        if disposition not in {"duplicate", "rejected"}:
            continue
        source_id = str(change.get("source_id", ""))
        if source_id not in by_id:
            v.fail("row_conservation_disposition_partition", "BLOCKER", "Disposition refers to an unknown raw row.", "known source ID", source_id, source_id, candidate=change)
            continue
        accounted[source_id].append(disposition)
        if disposition == "rejected":
            v.fail("row_conservation_disposition_partition", "BLOCKER", "Rejected disposition would bypass scalar verification; the conservative auditor has no rejection rule.", "kept row or valid exact-context duplicate", "unsupported rejected disposition", source_id, raw=by_id[source_id]["values"], candidate=change)
    for raw in raw_records:
        dispositions = accounted.get(raw["source_id"], [])
        if len(dispositions) != 1:
            v.fail("row_conservation_disposition_partition", "BLOCKER", "Raw row lacks an exclusive disposition.", "exactly one disposition", dispositions, raw["source_id"], raw=raw["values"])
    for raw in raw_records:
        source_id = raw["source_id"]
        if source_id not in mapped:
            continue
        candidate = rows[mapped[source_id]]
        expected_record, _, _ = normalize([raw], columns, conversions, {"enabled": False, "keys": [], "context_keys": []})
        expected = expected_record[0] if expected_record else {"values": {}}
        expected_values = expected.get("values", expected)
        for column in columns:
            if column not in candidate:
                v.fail("raw_value_immutability", "BLOCKER", "Candidate dropped a raw column.", column, "absent", source_id, raw=raw["values"].get(column), candidate=candidate)
                continue
            actual = candidate.get(column, "")
            raw_value = raw_text(raw["values"].get(column, ""))
            expected_value = expected_values.get(column, clean_text(raw_value))
            allowed_value = actual == expected_value
            if column in expected.get("_derived_fields", {}) and compare_number(actual, expected_value):
                allowed_value = True
            if not allowed_value:
                v.fail("raw_value_immutability", "BLOCKER", "Candidate altered a value beyond allowed normalization.", expected_value, actual, source_id, raw=raw_value, candidate=actual)
            if is_missing(raw_value) and not is_missing(actual) and not allowed_value:
                v.fail("no_fabricated_missing", "BLOCKER", "Missing raw value became substantive without an allowed derivation.", "missing or declared derivation", actual, source_id, raw=raw_value, candidate=actual)
        if "_source_file" in candidate or "_source_row" in candidate:
            if candidate.get("_source_file") != raw["source_file"] or candidate.get("_source_row") != str(raw["source_row"]):
                v.fail("source_locator_validity", "BLOCKER", "Source file/row metadata disagrees with source ID.", [raw["source_file"], str(raw["source_row"])], [candidate.get("_source_file"), candidate.get("_source_row")], source_id, candidate=candidate)
        for spec in conversions:
            source_field, target_field = spec["source_field"], spec["target_field"]
            number = parse_decimal(raw["values"].get(source_field, ""))
            if number is None or target_field not in candidate:
                continue
            target = candidate.get(target_field, "")
            if is_missing(target):
                continue
            recomputed = decimal_text(number * spec["factor"] + spec["offset"])
            if not compare_number(target, recomputed):
                v.fail("unit_conversion_recomputation", "HIGH", "Declared conversion does not recompute.", recomputed, target, source_id, raw=raw["values"].get(source_field), candidate=target)

    for change in changes:
        if change.get("disposition") != "duplicate":
            continue
        source_id = str(change.get("source_id", ""))
        duplicate_of = str(change.get("duplicate_of", ""))
        raw = by_id.get(source_id)
        parent = by_id.get(duplicate_of)
        if not raw:
            continue
        if not parent:
            v.fail("dedup_context_non_interference", "HIGH", "Duplicate exclusion lacks a known raw duplicate parent.", "known kept duplicate_of source ID", duplicate_of, source_id, candidate=change)
            continue
        if not dedup["enabled"]:
            v.fail("dedup_context_non_interference", "HIGH", "Duplicate removal occurred although dedup is not configured.", "all rows kept", "duplicate", source_id, candidate=change)
            continue
        left = {key: clean_text(raw["values"].get(key, "")) for key in columns}
        right = {key: clean_text(parent["values"].get(key, "")) for key in columns}
        same_context = all(left.get(key, "") == right.get(key, "") for key in dedup["context_keys"])
        same_key = all(left.get(key, "") == right.get(key, "") for key in dedup["keys"])
        if left != right or not same_context or not same_key:
            v.fail("dedup_context_non_interference", "HIGH", "Duplicate context interferes: rows are not exact full-row/key/context duplicates.", "same full row, key, and context", {"duplicate_of": duplicate_of, "same_context": same_context, "same_key": same_key}, source_id, raw=left, candidate=right)
        if duplicate_of not in mapped:
            v.fail("dedup_context_non_interference", "HIGH", "Duplicate parent is not a kept row.", "kept duplicate parent", duplicate_of, source_id, candidate=change)

    if json_rows is not None:
        if len(json_rows) != len(rows):
            v.fail("json_finite_value_completeness", "BLOCKER", "CSV and JSON row counts differ.", len(rows), len(json_rows))
        for index, json_row in enumerate(json_rows):
            if index >= len(rows):
                break
            csv_row = rows[index]
            if set(json_row) != set(csv_row):
                v.fail("json_finite_value_completeness", "BLOCKER", "CSV and JSON field sets differ.", sorted(csv_row), sorted(json_row), csv_row.get("_source_id", ""), candidate=json_row)
                continue
            for field in csv_row:
                if raw_text(json_row[field]) != csv_row[field]:
                    v.fail("json_finite_value_completeness", "BLOCKER", "CSV and JSON cell values differ.", csv_row[field], raw_text(json_row[field]), csv_row.get("_source_id", ""), candidate=json_row)

    # Metamorphic tests rerun the pure normalizer, not any in-memory candidate state.
    kept_a, all_a, changes_a = normalize(raw_records, columns, conversions, dedup)
    kept_b, all_b, changes_b = normalize(deepcopy(raw_records), list(columns), deepcopy(conversions), deepcopy(dedup))
    if projection(kept_a, columns) != projection(kept_b, columns) or canonical(changes_a) != canonical(changes_b):
        v.fail("deterministic_rerun", "HIGH", "Fresh normalizer reruns differ.", "identical semantic output and changes", "difference")
    reordered = list(reversed(deepcopy(raw_records)))
    kept_r, all_r, _ = normalize(reordered, list(reversed(columns)), conversions, dedup)
    if projection(kept_a, columns) != projection(kept_r, columns) or disposition_projection(all_a, columns) != disposition_projection(all_r, columns):
        v.fail("column_order_row_order_metamorphic_invariance", "HIGH", "Row/column reordering changed semantic output or dispositions.", "invariant", {"original_kept": len(kept_a), "reordered_kept": len(kept_r)})
    noisy = []
    for raw in deepcopy(raw_records):
        raw["values"] = {key: ("  " + value + "\t" if not is_missing(value) else value) for key, value in raw["values"].items()}
        raw["values"]["_metamorphic_irrelevant_noise"] = "noise-" + str(raw["ordinal"])
        noisy.append(raw)
    kept_n, _, _ = normalize(noisy, columns, conversions, dedup)
    if projection(kept_a, columns) != projection(kept_n, columns):
        v.fail("whitespace_noise_metamorphism", "HIGH", "Outer whitespace or irrelevant noise changed original-field output.", "invariant original fields", "difference")
    v.finish()
    return v, changes


def build_review(failures, changes, raw_records=None):
    entries = []
    for failure in failures:
        entries.append({
            "severity": failure["severity"], "blocking_impact": "yes" if failure["blocking_impact"] else "no",
            "source_locator": failure["source_locator"], "check": failure["check"],
            "counterexample_id": failure["counterexample_id"], "change_id": "",
            "reason": failure["message"],
            "recommended_action": "Inspect raw source and candidate trace; correct data or code, then rerun independent verification.",
        })
    for change in changes:
        if not change.get("review_required"):
            continue
        check = "dedup_context_non_interference" if change.get("disposition") == "duplicate" else "unit_conversion_recomputation"
        entries.append({
            "severity": "HIGH" if change.get("disposition") in {"duplicate", "rejected"} else "MEDIUM",
            "blocking_impact": "yes" if change.get("disposition") in {"duplicate", "rejected"} else "no",
            "source_locator": str(change.get("source_locator", change.get("source_id", ""))),
            "check": check, "counterexample_id": "", "change_id": str(change.get("change_id", "")),
            "reason": change.get("rationale", "Reviewable transformation"),
            "recommended_action": "Human source-context review; automated invariants do not settle scientific identity or conflict.",
        })
    if raw_records and not entries:
        entries.append({
            "severity": "LOW", "blocking_impact": "no",
            "source_locator": raw_records[0]["source_id"], "check": "human_spot_check",
            "counterexample_id": "", "change_id": "",
            "reason": "No exception or reviewable transformation; one deterministic raw-row spot-check is the minimal non-vacuous audit sample.",
            "recommended_action": "Read this raw row and candidate in source context; this is not statistical acceptance or scientific validation.",
        })
    entries.sort(key=lambda row: (
        0 if row["blocking_impact"] == "yes" else 1,
        SEVERITY_RANK.get(row["severity"], 9), row["check"], row["source_locator"],
        row["counterexample_id"], row["change_id"],
    ))
    categories = set()
    for entry in entries:
        sample = entry["blocking_impact"] == "yes" or entry["check"] not in categories
        entry["minimal_audit_sample"] = "yes" if sample else "no"
        categories.add(entry["check"])
    for index, entry in enumerate(entries, 1):
        entry["review_id"] = "RQ" + str(index).zfill(6)
        entry["priority"] = index
    return entries


REVIEW_FIELDS = (
    "review_id", "priority", "severity", "blocking_impact", "minimal_audit_sample",
    "check", "source_locator", "counterexample_id", "change_id", "reason", "recommended_action",
)


def read_review_queue(path):
    if not path.is_file():
        return []
    try:
        with path.open("r", encoding="utf-8-sig", newline="") as handle:
            return list(csv.DictReader(handle))
    except (OSError, UnicodeError, csv.Error):
        return []


def review_gaps(failures, changes, queue):
    counterexamples = {row.get("counterexample_id", "") for row in queue}
    change_ids = {row.get("change_id", "") for row in queue}
    gaps = []
    for failure in failures:
        if failure["check"] != "review_coverage" and failure["counterexample_id"] not in counterexamples:
            gaps.append(("counterexample", failure["counterexample_id"], failure["source_locator"]))
    for change in changes:
        if change.get("review_required") and change.get("change_id", "") not in change_ids:
            gaps.append(("change", str(change.get("change_id", "")), str(change.get("source_id", ""))))
    return gaps


def write_audit(path, case_id, status, verification_status, checks, queue, unresolved, verify_existing):
    samples = [row for row in queue if row.get("minimal_audit_sample") == "yes"]
    lines = [
        "# Independent metamorphic audit", "",
        "- Case ID: `" + case_id.replace("`", "'") + "`",
        "- Delivery status: **" + status + "**; verification: **" + verification_status + "**.",
        "- Mode: " + ("verify-existing; all raw and candidate artifacts were reloaded from disk." if verify_existing else "raw inputs and candidate artifacts were independently reloaded from disk."),
        "- Scientific scope: automated invariants detect process failures; they do **not** resolve scientific conflicts, source credibility, identity, or domain correctness.", "",
        "## Checks", "", "| Check | Result | Failures |", "|---|---|---:|",
    ]
    for check in checks:
        lines.append("| " + check["test_id"] + " | " + check["status"] + " | " + str(check["failure_count"]) + " |")
    lines.extend(["", "## Minimal human audit sample", "",
                  "All blocking items are mandatory. Otherwise one deterministic representative per check is selected; this minimizes routine review without hiding risk.", ""])
    if samples:
        lines.extend(["| Review | Severity | Check | Source locator |", "|---|---|---|---|"])
        for row in samples:
            lines.append("| " + row["review_id"] + " | " + row["severity"] + " | " + row["check"] + " | " + row["source_locator"].replace("|", "\\|") + " |")
    else:
        lines.append("No transformations or failures required review. If raw rows exist, human scientific review remains outside this process audit.")
    lines.extend(["", "## Unresolved and limitations", ""])
    if unresolved:
        for key in unresolved:
            lines.append("- Output-contract key `" + str(key).replace("`", "'") + "` is null in result.json because no safe mapping is defined.")
    else:
        lines.append("- No unknown output-contract keys were encountered.")
    lines.extend([
        "- Whitespace, row/column permutation, determinism, and exact-context dedup tests are process invariants, not proofs of bibliographic truth.",
        "- Unit checks apply only to declarations in case/task; unknown units and conflicting sources require human/domain review.",
        "- Missing-value tests prohibit unjustified fabrication but do not infer whether a source omission is scientifically meaningful.",
        "- Counterexamples are executable debugging evidence, not a substitute for reviewing accepted rows.", "",
    ])
    write_text(path, "\n".join(lines))


def artifact_record(output):
    artifacts = {}
    for name in REQUIRED_ARTIFACTS:
        if name == "result.json":
            artifacts[name] = {"path": name}
            continue
        path = output / name
        if path.is_file():
            artifacts[name] = {"path": name, "bytes": path.stat().st_size, "sha256": sha256(path)}
        else:
            artifacts[name] = {"path": name, "missing": True}
    return artifacts


def ensure_empty_artifacts(output):
    if not (output / "cleaned.csv").exists():
        write_csv(output / "cleaned.csv", ["_source_id"], [])
    if not (output / "cleaned.json").exists():
        write_json(output / "cleaned.json", {"cleaned": [], "row_count": 0})
    for name in ("changes.jsonl", "counterexamples.jsonl"):
        if not (output / name).exists():
            write_jsonl(output / name, [])
    if not (output / "review_queue.csv").exists():
        write_csv(output / "review_queue.csv", REVIEW_FIELDS, [])
    if not (output / "verification.json").exists():
        write_json(output / "verification.json", {"verification_status": "fail", "checks": []})
    if not (output / "audit.md").exists():
        write_text(output / "audit.md", "# Independent metamorphic audit\n\nInput error; processing did not complete.\n")


def finalize(output, result, verification, failures, changes, queue, case_id, verify_existing, unresolved):
    ensure_empty_artifacts(output)
    verification_status = "pass" if not failures else "fail"
    has_blocking_review = any(row.get("blocking_impact") == "yes" for row in queue)
    status = "success" if verification_status == "pass" and not has_blocking_review else "partial"
    report = {
        "case_id": case_id, "verification_status": verification_status,
        "independent_reload": True, "verify_existing": verify_existing,
        "checks": verification.checks, "counterexample_count": len(failures),
        "counterexample_file": "counterexamples.jsonl",
        "scientific_conflicts_resolved": False,
        "scope_limit": "Process quality control only; no automated claim of scientific conflict resolution.",
    }
    if result.get("example_label") == LABEL:
        report["example_label"] = LABEL
    write_json(output / "verification.json", report)
    write_jsonl(output / "counterexamples.jsonl", failures)
    write_csv(output / "review_queue.csv", REVIEW_FIELDS, queue)
    result.update({
        "status": status, "verification_status": verification_status,
        "uncertainty": [
            "Metamorphic and invariant checks establish process properties only; scientific conflicts require human/domain review.",
            "Only declared unit conversions are recomputed; undeclared unit semantics remain uncertain.",
        ],
        "change_records": changes,
        "review_queue": queue,
        "artifacts": artifact_record(output),
        "unresolved_output_contract_fields": unresolved,
    })
    result.pop("processing_error", None)

    # Fill semantic output-contract requests with actual reloaded payloads, not
    # merely filenames. Only fields with no declared producer remain unresolved.
    cleaned_rows = candidate_json_rows(read_json(output / "cleaned.json"))
    remaining = []
    for key in unresolved:
        normalized = re.sub(r"[^a-z0-9]", "", key.casefold())
        if normalized in {"cleaned", "cleaneddata", "cleanedrecords", "records", "rows", "data"}:
            result[key] = cleaned_rows
        elif normalized in {"changes", "changelog"}:
            result[key] = changes
        elif normalized in {"rowcount", "cleanedrowcount"}:
            result[key] = len(cleaned_rows)
        elif normalized == "reviewcount":
            result[key] = len(queue)
        elif normalized == "changecount":
            result[key] = len(changes)
        elif normalized in {"statistics", "stats", "summary"}:
            result[key] = {"rows": len(cleaned_rows), "changes": len(changes), "review_items": len(queue)}
        else:
            remaining.append(key)
    unresolved = remaining
    result["unresolved_output_contract_fields"] = unresolved
    if unresolved:
        status = "partial"
        result["status"] = "partial"
        result["uncertainty"].append("Unknown output-contract fields are null and listed in unresolved_output_contract_fields.")
    if failures:
        result["uncertainty"].append(str(len(failures)) + " counterexamples require correction/review; verification failed.")
    elif has_blocking_review:
        result["uncertainty"].append("Verification passed, but blocking human review (for example exact-context duplicate exclusion) keeps delivery status partial.")
    write_audit(output / "audit.md", case_id, result["status"], verification_status, verification.checks, queue, unresolved, verify_existing)
    # Bind hashes only after the final audit bytes exist; otherwise a rerun sees
    # the previous audit hash and violates deterministic delivery.
    result["artifacts"] = artifact_record(output)
    write_json(output / "result.json", result)
    return 0 if verification_status == "pass" else 1


def input_error(output, result, message):
    ensure_empty_artifacts(output)
    failure = {
        "counterexample_id": "CE000001", "check": "row_conservation_disposition_partition",
        "severity": "BLOCKER", "blocking_impact": True, "message": message,
        "expected": "valid case/task and reloadable materials/candidates", "observed": "input_error",
        "source_locator": "", "raw": None, "candidate": None,
    }
    verification = Verification()
    verification.failures = [failure]
    verification.finish()
    for check in verification.checks:
        if check["status"] == "pass":
            check["status"] = "not_run"
    report = {
        "case_id": result.get("case_id", "unknown_case"), "verification_status": "fail",
        "independent_reload": True, "checks": verification.checks,
        "counterexample_count": 1, "scientific_conflicts_resolved": False,
    }
    if result.get("example_label") == LABEL:
        report["example_label"] = LABEL
    write_json(output / "verification.json", report)
    write_jsonl(output / "counterexamples.jsonl", [failure])
    queue = build_review([failure], [])
    write_csv(output / "review_queue.csv", REVIEW_FIELDS, queue)
    write_audit(output / "audit.md", result.get("case_id", "unknown_case"), "input_error", "fail", verification.checks, queue, result.get("unresolved_output_contract_fields", []), False)
    result.update({
        "status": "input_error", "verification_status": "fail", "processing_error": message,
        "uncertainty": ["Input/processing failed; no scientific or delivery validity is claimed.", message],
        "change_records": [], "review_queue": queue, "artifacts": artifact_record(output),
    })
    write_json(output / "result.json", result)
    return 2


def run(args):
    input_root = Path(args.input)
    work = Path(args.work)
    output = Path(args.output)
    output.mkdir(parents=True, exist_ok=True)
    work.mkdir(parents=True, exist_ok=True)
    result = base_result("unknown_case", {})
    write_json(output / "result.json", result)
    case = {}
    try:
        if not input_root.is_dir():
            raise InvalidInput("input directory not found: " + args.input)
        case = discover_case(input_root, args.case, args.task)
        case_id = get_case_id(case)
        result = base_result(case_id, case)
        write_json(output / "result.json", result)
        raw_records, columns, sources = load_materials(input_root, case.get("_case_files", []), case)
        conversions = conversion_specs(case)
        dedup = dedup_spec(case)
        for path in case.get("_case_files", []):
            sources.insert(0, source_descriptor(path, input_root, "case/task"))
        result["sources"] = sources
        result["raw_row_count"] = len(raw_records)
        write_json(output / "result.json", result)
        generated = False
        if not args.verify_existing and not (output / "cleaned.csv").is_file() and not (output / "cleaned.json").is_file():
            generate_candidate(output, raw_records, columns, conversions, dedup)
            generated = True
        verification, changes = verify_candidate(raw_records, columns, conversions, dedup, output)
        queue = build_review(verification.failures, changes, raw_records)
        write_csv(output / "review_queue.csv", REVIEW_FIELDS, queue)
        gaps = review_gaps(verification.failures, changes, read_review_queue(output / "review_queue.csv"))
        for kind, identifier, locator in gaps:
            verification.fail("review_coverage", "BLOCKER", "Review queue omitted a required item after reload.", kind + " queued", identifier, locator)
        if gaps:
            verification.checks = []
            verification.finish()
            queue = build_review(verification.failures, changes, raw_records)
        result["generated_candidate"] = generated
        if case.get("example_label") == LABEL:
            result["example_label"] = LABEL
        return finalize(output, result, verification, verification.failures, changes, queue, case_id, args.verify_existing, result.get("unresolved_output_contract_fields", []))
    except (InvalidInput, OSError, UnicodeError, csv.Error, ValueError, TypeError) as exc:
        return input_error(output, result, str(exc))


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description="Generate conservative candidates and independently verify process invariants.")
    parser.add_argument("--input", default="/input", help="Case/task and raw material directory")
    parser.add_argument("--work", default="/app/work", help="Scratch directory (not used as evidence)")
    parser.add_argument("--output", default="/app/output", help="Candidate and audit artifact directory")
    parser.add_argument("--case", help="Optional case JSON/text path, absolute or relative to --input")
    parser.add_argument("--task", help="Optional task JSON/text path, absolute or relative to --input")
    parser.add_argument("--verify-existing", action="store_true", help="Never generate candidates; independently validate existing output artifacts")
    return parser.parse_args(argv)


def main(argv=None):
    args = parse_args(argv)
    return run(args)


if __name__ == "__main__":
    sys.exit(main())
