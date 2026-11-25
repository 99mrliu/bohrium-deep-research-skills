#!/usr/bin/env python3
"""Deterministic evidence adjudication for extracted tabular/JSON records.

Python 3 standard library only. No network, wall clock, randomness, or answer data.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import unicodedata

STATE_ORDER = ("corroborated", "source_conflict", "extractor_only", "unverifiable")
CSV_META = ("_record_id", "_evidence_state", "_review_fields", "_source_fields", "_unsupported_fields")
CONTROL_KEYS = {
    "fields", "properties", "required", "type", "description", "items", "additionalProperties",
    "required_fields", "result_fields", "top_level_fields", "$schema", "title", "definitions",
}
RECORD_KEYS = ("extracted_records", "extractions", "records", "rows", "items", "data")
IDENTIFIER_NAMES = {
    "id", "record id", "sample id", "material id", "compound id", "doi", "name", "title",
    "identifier", "entry id", "citation id", "structure id",
}
MISSING_TOKENS = {"", "na", "n/a", "none", "null", "not reported", "not available", "unknown", "missing", "unclear"}


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def dump_json(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8")


def dump_jsonl(path, rows):
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        for row in rows:
            handle.write(canonical(row) + "\n")


def read_text(path):
    return path.read_text(encoding="utf-8")


def scalar(value):
    return value is None or isinstance(value, (str, int, float, bool))


def value_text(value):
    if value is None:
        return ""
    if value is True:
        return "true"
    if value is False:
        return "false"
    if isinstance(value, (dict, list)):
        return canonical(value)
    return str(value)


def value_type(value):
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, int):
        return "integer"
    if isinstance(value, float):
        return "number"
    if isinstance(value, str):
        return "string"
    if isinstance(value, list):
        return "array"
    return "object"


def field_name(value):
    value = str(value).replace("_", " ").replace("-", " ")
    value = re.sub(r"([a-z])([A-Z])", r"\1 \2", value)
    return re.sub(r"\s+", " ", value).strip().casefold()


def pointer_escape(value):
    return str(value).replace("~", "~0").replace("/", "~1")


def normalization_rules(case):
    raw = case.get("normalization", case.get("normalization_rules", {})) if isinstance(case, dict) else {}
    if isinstance(raw, list):
        raw = {str(item): True for item in raw}
    if not isinstance(raw, dict):
        raw = {}
    allowed = ("trim_whitespace", "collapse_whitespace", "unicode_nfkc", "casefold")
    rules = {name: raw.get(name) is True for name in allowed}
    rules["apply"] = raw.get("apply", raw.get("apply_to_output", False)) is True
    return rules


def normalize(value, rules):
    text = value_text(value)
    if rules.get("unicode_nfkc"):
        text = unicodedata.normalize("NFKC", text)
    if rules.get("casefold"):
        text = text.casefold()
    if rules.get("collapse_whitespace"):
        text = re.sub(r"\s+", " ", text)
    if rules.get("trim_whitespace"):
        text = text.strip()
    return text


def same_value(left, right, rules):
    if type(left) is type(right) and left == right:
        return True
    # Numeric XML/JSON representations may compare exactly without unit conversion.
    if isinstance(left, (int, float)) and not isinstance(left, bool) and isinstance(right, (int, float)) and not isinstance(right, bool):
        return left == right
    return normalize(left, rules) == normalize(right, rules)


def token_boundaries(text, start, end, needle):
    if start and text[start - 1].isalnum() and needle[0].isalnum():
        return False
    if end < len(text) and text[end].isalnum() and needle[-1].isalnum():
        return False
    # Do not treat 12 as an exact observation of 12.5 or 512.3.
    if re.fullmatch(r"[+-]?\d+(?:\.\d+)?", needle):
        if start >= 2 and text[start - 1] == "." and text[start - 2].isdigit():
            return False
        if end + 1 < len(text) and text[end] == "." and text[end + 1].isdigit():
            return False
    return True


def line_column(text, offset):
    line = text.count("\n", 0, offset) + 1
    previous = text.rfind("\n", 0, offset)
    return line, offset - previous


def substring_anchor(path, text, start, end, page=None):
    line, column = line_column(text, start)
    anchor = {
        "kind": "pdf_page_substring" if page is not None else "text_substring",
        "source": path,
        "start": start,
        "end": end,
        "line": line,
        "column": column,
        "exact_substring": text[start:end],
    }
    if page is not None:
        anchor["page"] = page
    return anchor


def find_substrings(document, value, rules):
    needle = value_text(value)
    if len(needle) < 2 or value is None or isinstance(value, (dict, list)):
        return []
    text = document["text"]
    found = []
    start = 0
    while True:
        index = text.find(needle, start)
        if index < 0:
            break
        end = index + len(needle)
        if token_boundaries(text, index, end, needle):
            found.append(substring_anchor(document["path"], text, index, end, document.get("page")))
        start = index + max(1, len(needle))
    # Configured equivalence may find a differently-spaced/cased source spelling.
    if not found and any(rules.get(key) for key in ("trim_whitespace", "collapse_whitespace", "unicode_nfkc", "casefold")):
        target = normalize(needle, rules)
        for line_match in re.finditer(r"[^\n]+", text):
            line = line_match.group(0)
            if target and target in normalize(line, rules):
                found.append(substring_anchor(document["path"], text, line_match.start(), line_match.end(), document.get("page")))
    return found


def sha256(path):
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(65536), b""):
            digest.update(block)
    return digest.hexdigest()


def flatten_scalars(value, prefix=""):
    result = []
    if isinstance(value, dict):
        for key in sorted(value):
            result.extend(flatten_scalars(value[key], prefix + "/" + pointer_escape(key)))
    elif isinstance(value, list):
        for index, item in enumerate(value):
            result.extend(flatten_scalars(item, prefix + "/" + str(index)))
    else:
        result.append((prefix, value))
    return result


def identifiers(record):
    result = {}
    if not isinstance(record, dict):
        return result
    for key, value in record.items():
        norm = field_name(key)
        if scalar(value) and value_text(value) and (norm in IDENTIFIER_NAMES or norm.endswith(" id")):
            result[norm] = value
    return result


def records_in_json(value):
    """Return (JSON-pointer, record) pairs without inferring official answers."""
    found = []
    if isinstance(value, list) and all(isinstance(item, dict) for item in value):
        return [("/" + str(index), item) for index, item in enumerate(value)]
    if isinstance(value, dict):
        for key in RECORD_KEYS:
            child = value.get(key)
            if isinstance(child, list) and all(isinstance(item, dict) for item in child):
                base = "/" + pointer_escape(key)
                found.extend((base + "/" + str(index), item) for index, item in enumerate(child))
        if not found and value and all(scalar(item) for item in value.values()):
            found.append(("", value))
    return found


def csv_anchor(path, row_number, column, value):
    return {
        "kind": "csv_cell", "source": path, "row_number": row_number,
        "column": column, "exact_substring": value_text(value),
    }


def json_anchor(path, pointer, value):
    return {
        "kind": "json_pointer", "source": path, "json_pointer": pointer,
        "exact_substring": value_text(value), "serialized_value": canonical(value),
    }


def observation_rows(path, records, origin_kind):
    observations = []
    for record_path, record in records:
        ids = identifiers(record)
        for key, value in record.items():
            if not scalar(value):
                continue
            if origin_kind == "csv":
                try:
                    row_number = int(record_path)
                except ValueError:
                    row_number = None
                anchor = csv_anchor(path, row_number, key, value)
                field_path = key
            else:
                pointer = record_path + "/" + pointer_escape(key)
                anchor = json_anchor(path, pointer, value)
                field_path = pointer
            observations.append({
                "path": path, "record_path": record_path, "field_path": field_path,
                "field": field_name(key), "value": value, "anchor": anchor,
                "identifiers": ids, "missing": normalize(value, {"casefold": True, "trim_whitespace": True}) in MISSING_TOKENS,
            })
    return observations


def source_identity_match(candidate, observation, rules):
    left = identifiers(candidate)
    right = observation.get("identifiers", {})
    for key in sorted(set(left) & set(right)):
        if value_text(left[key]) and same_value(left[key], right[key], rules):
            return True
    return False


def strip_markdown(value):
    value = value.strip().strip("|").strip()
    value = re.sub(r"^[-*+]\s+", "", value)
    value = value.replace("**", "").replace("__", "").replace("`", "")
    return value.strip()


def labeled_value(text, field):
    """Conservative field:value or table-cell extraction; no unit/value conversion."""
    if not field:
        return []
    words = [re.escape(word) for word in field.split()]
    if not words:
        return []
    label_pattern = r"(?<![\w])" + r"[\s_-]+".join(words) + r"(?![\w])"
    results = []
    for line_match in re.finditer(r"[^\n]+", text):
        line = line_match.group(0)
        clean = strip_markdown(line)
        cells = [strip_markdown(cell) for cell in clean.strip("|").split("|")]
        for index, cell in enumerate(cells[:-1]):
            if re.fullmatch(label_pattern + r"(?:\s*\([^)]*\))?\s*:?", cell, flags=re.IGNORECASE):
                captured = cells[index + 1].strip()
                if captured:
                    results.append((captured, line_match.start(), line_match.end(), line))
        match = re.search(label_pattern + r"(?:\s*\([^)]*\))?\s*(?::|=|\|)\s*([^|;\n]+)", clean, flags=re.IGNORECASE)
        if match:
            captured = strip_markdown(match.group(1))
            if captured:
                results.append((captured, line_match.start(), line_match.end(), line))
    # Deduplicate overlapping Markdown/table interpretations.
    unique = []
    seen = set()
    for item in results:
        key = (item[0], item[1])
        if key not in seen:
            seen.add(key)
            unique.append(item)
    return unique


def parse_contract_fields(contract):
    """Normalize supported output_contract shapes to ordered field specifications."""
    if not contract:
        return []

    def parse_container(node):
        required_names = set()
        required_nodes = []
        if isinstance(node, dict) and isinstance(node.get("required"), list):
            for item in node["required"]:
                if isinstance(item, str):
                    required_names.add(item)
                elif isinstance(item, dict):
                    required_nodes.append(item)
        fields = None
        if isinstance(node, list):
            fields = node
        elif isinstance(node, dict):
            for key in ("fields", "properties", "required_fields", "result_fields", "top_level_fields"):
                if key in node:
                    fields = node[key]
                    break
            if fields is None and node.get("required") is not None:
                fields = []
            if fields is None:
                candidate = {key: value for key, value in node.items() if key not in CONTROL_KEYS}
                if candidate and all(isinstance(value, (dict, str, list)) for value in candidate.values()):
                    fields = candidate
        if fields is None:
            fields = []
        if isinstance(fields, dict):
            entries = []
            for key, spec in fields.items():
                entries.append({"name": key, "spec": spec})
        elif isinstance(fields, list):
            entries = []
            for item in fields:
                if isinstance(item, str):
                    entries.append({"name": item, "spec": {}})
                elif isinstance(item, dict):
                    name = item.get("name", item.get("field", item.get("key")))
                    if isinstance(name, str):
                        entries.append({"name": name, "spec": item})
        else:
            entries = []
        for name in sorted(required_names):
            if all(entry["name"] != name for entry in entries):
                entries.append({"name": name, "spec": {}})
        for item in required_nodes:
            name = item.get("name", item.get("field", item.get("key")))
            if isinstance(name, str) and all(entry["name"] != name for entry in entries):
                entries.append({"name": name, "spec": item})
        for entry in entries:
            entry["required"] = entry["name"] in required_names or entry["spec"].get("required") is True if isinstance(entry["spec"], dict) else entry["name"] in required_names
        return entries

    return parse_container(contract)


def contract_has_nested(spec):
    return isinstance(spec, dict) and any(key in spec for key in ("fields", "properties", "required", "required_fields", "result_fields"))


def count_for(name, context):
    claims = context["claims"]
    counts = {
        "total records": len(context["records"]), "total claims": len(claims),
        "change count": len(context["changes"]), "review count": len(context["review"]),
        "source count": len(context["sources"]),
    }
    for state in STATE_ORDER:
        counts[state.replace("_", " ")] = sum(claim["state"] == state for claim in claims)
        counts[state.replace("_", " ") + " count"] = counts[state.replace("_", " ")]
    return counts.get(name)


def contract_value(name, spec, path, required, context, unresolved):
    norm = field_name(name)
    nested = parse_contract_fields(spec) if contract_has_nested(spec) else []
    if nested:
        value = {}
        for entry in nested:
            child_path = path + "." + entry["name"]
            value[entry["name"]] = contract_value(
                entry["name"], entry["spec"], child_path, entry["required"], context, unresolved,
            )
        return value
    if norm in ("case id", "id") and path.count(".") == 0:
        return context["case_id"]
    if norm == "status":
        return context["status"]
    if norm in ("source", "sources", "source files", "source manifest"):
        return context["sources"]
    if norm in ("uncertainty", "uncertainties", "unresolved", "unresolved issues"):
        return context["uncertainty"]
    if norm in ("unresolved fields", "unknown fields"):
        return list(unresolved)
    if norm in ("change records", "change log", "changes"):
        return context["changes"]
    if norm in ("review", "review queue", "review items"):
        return context["review"]
    if norm in ("artifacts", "artifact references", "output files", "outputs"):
        return context["artifacts"]
    if norm in ("records", "cleaned records", "cleaned data", "data"):
        return context["records"]
    if norm in ("cleaned csv", "cleaned json", "changes jsonl", "review queue csv", "evidence jsonl", "audit md", "result json"):
        mapping = {
            "cleaned csv": "cleaned.csv", "cleaned json": "cleaned.json", "changes jsonl": "changes.jsonl",
            "review queue csv": "review_queue.csv", "evidence jsonl": "evidence.jsonl", "audit md": "audit.md",
            "result json": "result.json",
        }
        return mapping[norm]
    if norm in ("errors", "error messages"):
        return context["errors"]
    if norm in ("warnings", "warning messages"):
        return context["warnings"]
    if norm in ("example marker", "synthetic marker") and context["marker"]:
        return context["marker"]
    count = count_for(norm, context)
    if count is not None:
        return count
    unresolved_path = path
    if unresolved_path not in unresolved:
        unresolved.append(unresolved_path)
    return None


def make_result(context, contract):
    unresolved = []
    result = {
        "case_id": context["case_id"], "status": context["status"], "sources": context["sources"],
        "uncertainty": context["uncertainty"], "change_records": context["changes"],
        "change_log": context["changes"], "review_queue": context["review"],
        "artifacts": context["artifacts"],
    }
    if context["marker"]:
        result["example_marker"] = context["marker"]
    for entry in parse_contract_fields(contract):
        result[entry["name"]] = contract_value(
            entry["name"], entry["spec"], entry["name"], entry["required"], context, unresolved,
        )
    result["unresolved_fields"] = unresolved
    # Uncertainty entries are strings so arbitrary contracts remain JSON-serializable.
    for path in unresolved:
        message = "No evidence-backed value is defined for contract field: " + path
        if message not in result["uncertainty"]:
            result["uncertainty"].append(message)
    result["case_id"] = context["case_id"]
    result["status"] = context["status"]
    result["sources"] = context["sources"]
    result["change_records"] = context["changes"]
    result["change_log"] = context["changes"]
    result["review_queue"] = context["review"]
    result["artifacts"] = context["artifacts"]
    return result


def artifact_references():
    return {
        "cleaned_csv": "cleaned.csv", "cleaned_json": "cleaned.json", "changes_jsonl": "changes.jsonl",
        "review_queue_csv": "review_queue.csv", "evidence_jsonl": "evidence.jsonl",
        "audit_md": "audit.md", "result_json": "result.json",
    }


def initial_audit(case_id, status, uncertainties, marker):
    lines = ["# Evidence adjudication audit", ""]
    if marker:
        lines.extend([marker, ""])
    lines.extend(["- case_id: `" + value_text(case_id) + "`", "- status: `" + status + "`", ""])
    lines.append("## Uncertainty")
    lines.extend(["- " + item for item in uncertainties] or ["- None recorded yet."])
    lines.append("")
    return "\n".join(lines)


def write_early_outputs(output, context, contract):
    output.mkdir(parents=True, exist_ok=True)
    dump_jsonl(output / "changes.jsonl", [])
    dump_jsonl(output / "evidence.jsonl", [])
    with (output / "review_queue.csv").open("w", encoding="utf-8", newline="") as handle:
        csv.writer(handle).writerow(["record_id", "field_path", "observed_value", "state", "reason", "claim_id", "evidence_refs"])
    with (output / "cleaned.csv").open("w", encoding="utf-8", newline="") as handle:
        csv.writer(handle).writerow(list(CSV_META))
    dump_json(output / "cleaned.json", {"case_id": context["case_id"], "case_records": []})
    (output / "audit.md").write_text(initial_audit(context["case_id"], context["status"], ["Adjudication has not completed."], context["marker"]), encoding="utf-8")
    dump_json(output / "result.json", make_result(context, contract))


def discover_files(input_dir, case_path, task_path):
    files = []
    if not input_dir.is_dir():
        return files
    case_resolved = case_path.resolve()
    task_resolved = task_path.resolve()
    for path in sorted(input_dir.rglob("*"), key=lambda item: item.relative_to(input_dir).as_posix()):
        if not path.is_file() or path.is_symlink():
            continue
        resolved = path.resolve()
        if resolved in (case_resolved, task_resolved):
            continue
        files.append(path)
    return files


def pdf_documents(path, relative):
    converter = shutil.which("pdftotext")
    if not converter:
        return [], "pdftotext unavailable; PDF evidence remains unverifiable"
    try:
        completed = subprocess.run(
            [converter, "-layout", str(path), "-"], stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            check=False, timeout=60,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return [], "pdftotext failed: " + exc.__class__.__name__
    if completed.returncode != 0:
        return [], "pdftotext exited with status " + str(completed.returncode)
    try:
        text = completed.stdout.decode("utf-8")
    except UnicodeDecodeError:
        text = completed.stdout.decode("utf-8", errors="replace")
    pages = text.split("\f")
    if pages and not pages[-1].strip():
        pages.pop()
    documents = [{"path": relative, "text": page, "page": index + 1} for index, page in enumerate(pages)]
    if not documents:
        return [], "pdftotext produced no readable text"
    return documents, None


def extractor_path(relative, case, task_text):
    """Separate named evidence tables from extraction tables without assuming labels."""
    for key in ("extraction_file", "extracted_file", "records_file", "candidate_file"):
        declared = case.get(key)
        if isinstance(declared, str) and declared.replace("\\", "/").lstrip("./") == relative:
            return True
    for key in ("extraction_files", "extracted_files", "records_files", "candidate_files"):
        declared = case.get(key)
        if isinstance(declared, list) and any(isinstance(item, str) and item.replace("\\", "/").lstrip("./") == relative for item in declared):
            return True
    stem = Path(relative).stem.casefold()
    if re.search(r"(?:^|[_-])(reference|evidence|source|truth)(?:$|[_-])", stem):
        return False
    if re.search(r"(?:^|[_-])(extracted|extraction|candidate|submission|parsed|records?|data|tables?|observations?|measurements?)(?:$|[_-])", stem):
        return True
    # A task may explicitly identify an extraction path; source-like names above
    # still remain evidence unless a structured case declaration overrides them.
    if relative in task_text and bool(re.search(r"extract|adjudicat|candidate|submission", task_text, re.IGNORECASE)):
        return True
    # An otherwise unlabelled delimited table is a candidate extraction, never a
    # trusted answer. This fail-open discovery avoids returning an empty cleaned
    # table; independent evidence is still required for corroboration.
    return Path(relative).suffix.casefold() in (".csv", ".tsv")


def load_materials(input_dir, case_path, task_path, case, task_text):
    documents = []
    observations = []
    candidates = []
    sources = []
    errors = []
    warnings = []

    case_raw = read_text(case_path)
    documents.append({"path": "case.json", "text": case_raw, "page": None})
    sources.append({"path": "case.json", "kind": "case", "readable": True, "sha256": sha256(case_path), "page_locators": False})
    documents.append({"path": "task.md", "text": task_text, "page": None})
    sources.append({"path": "task.md", "kind": "task", "readable": True, "sha256": sha256(task_path), "page_locators": False})
    for pointer, value in flatten_scalars(case):
        observations.append({
            "path": "case.json", "record_path": pointer.rsplit("/", 1)[0], "field_path": pointer,
            "field": field_name(pointer.rsplit("/", 1)[-1]), "value": value,
            "anchor": json_anchor("case.json", pointer, value), "identifiers": identifiers(case),
            "missing": normalize(value, {"casefold": True, "trim_whitespace": True}) in MISSING_TOKENS,
        })
    # Explicit and common embedded record collections in case.json are extractor
    # candidates, not self-corroborating evidence. Both direct arrays and the
    # common nested wrappers understood by records_in_json are accepted.
    for key in ("extracted_records", "extraction_records", "extractions", "records", "rows", "observations", "measurements", "data"):
        child = case.get(key)
        for record_path, record in records_in_json(child):
            candidates.append({
                "path": "case.json",
                "record_path": "/" + pointer_escape(key) + record_path,
                "record": record,
                "kind": "json",
            })

    for path in discover_files(input_dir, case_path, task_path):
        relative = path.relative_to(input_dir).as_posix()
        suffix = path.suffix.casefold()
        source = {"path": relative, "kind": suffix.lstrip(".") or "text", "readable": False, "sha256": sha256(path), "page_locators": suffix == ".pdf"}
        sources.append(source)
        if suffix == ".pdf":
            pages, error = pdf_documents(path, relative)
            documents.extend(pages)
            source["readable"] = bool(pages)
            if error:
                source["error"] = error
                errors.append(relative + ": " + error)
            continue
        try:
            raw = read_text(path)
        except (OSError, UnicodeDecodeError) as exc:
            source["error"] = "Unreadable UTF-8 text: " + exc.__class__.__name__
            errors.append(relative + ": unreadable text")
            continue
        if "\x00" in raw:
            source["error"] = "NUL byte indicates unsupported binary content"
            errors.append(relative + ": unsupported binary content")
            continue
        source["readable"] = True
        documents.append({"path": relative, "text": raw, "page": None})
        if suffix in (".csv", ".tsv"):
            try:
                dialect = "excel-tab" if suffix == ".tsv" else "excel"
                reader = csv.DictReader(io.StringIO(raw), dialect=dialect)
                if reader.fieldnames is None:
                    raise ValueError("missing header")
                records = []
                for row_number, row in enumerate(reader, start=2):
                    record = {key: row.get(key) for key in reader.fieldnames}
                    records.append((str(row_number), record))
                    if extractor_path(relative, case, task_text):
                        candidates.append({"path": relative, "record_path": str(row_number), "record": record, "kind": "csv"})
                observations.extend(observation_rows(relative, records, "csv"))
            except (csv.Error, ValueError) as exc:
                source["error"] = "Delimited parsing failed: " + str(exc)
                errors.append(relative + ": delimited parsing failed")
        elif suffix == ".json":
            try:
                parsed = json.loads(raw)
                records = records_in_json(parsed)
                observations.extend(observation_rows(relative, records, "json"))
                if extractor_path(relative, case, task_text):
                    for record_path, record in records:
                        candidates.append({"path": relative, "record_path": record_path or "/", "record": record, "kind": "json"})
            except json.JSONDecodeError as exc:
                source["error"] = "JSON parsing failed at line " + str(exc.lineno)
                errors.append(relative + ": JSON parsing failed")
        # TXT/Markdown and successfully read unknown UTF-8 formats remain exact-search evidence.

    documents.sort(key=lambda doc: (doc["path"], doc.get("page") or 0))
    sources.sort(key=lambda source: source["path"])
    candidates.sort(key=lambda item: (item["path"], natural_key(item["record_path"])))
    return documents, observations, candidates, sources, errors, warnings


def natural_key(value):
    return tuple(int(part) if part.isdigit() else part for part in re.split(r"(\d+)", value))


def independent_identity(candidate, document, rules):
    ids = identifiers(candidate)
    if not ids:
        return False
    return any(value_text(value) and value_text(value) in document["text"] for value in ids.values())


def scalar_candidate_records(record):
    if not isinstance(record, dict):
        return []
    return [(key, value) for key, value in record.items() if scalar(value)]


def adjudicate(documents, observations, candidates, sources, errors, rules):
    claims = []
    changes = []
    review = []
    cleaned_records = []
    multiple_records = len(candidates) > 1
    candidate_paths = {candidate["path"] for candidate in candidates}
    source_readable = any(source["readable"] and source["path"] not in candidate_paths | {"case.json", "task.md"} for source in sources)

    for record_index, candidate in enumerate(candidates, start=1):
        record_id = "R" + str(record_index).zfill(6)
        cleaned = dict(candidate["record"])
        states = {}
        review_fields = []
        source_fields = []
        unsupported = []
        field_claims = []
        nested = flatten_scalars(candidate["record"])
        for field_path, observed in nested:
            key = field_path.rsplit("/", 1)[-1] if field_path.startswith("/") else field_path
            norm = field_name(key)
            claim_index = len(claims) + 1
            claim_id = "E" + str(claim_index).zfill(6)
            supports = []
            conflicts = []
            explicit_missing = []
            reasons = []

            for observation in observations:
                if observation["path"] == candidate["path"]:
                    continue
                if observation["field"] != norm:
                    continue
                identity = source_identity_match(candidate["record"], observation, rules)
                # Case-level scalar evidence is usable for a single record; multi-record
                # structured claims require a shared identifier to prevent cross-record leakage.
                if not identity and not (observation["path"] == "case.json" and not multiple_records):
                    continue
                if observation["missing"]:
                    explicit_missing.append(observation["anchor"])
                elif same_value(observed, observation["value"], rules):
                    supports.append(observation["anchor"])
                elif observed is not None and value_text(observed) != "":
                    conflicts.append({"value": observation["value"], "anchor": observation["anchor"]})

            # Exact labeled text offers field-level support and conflict detection.
            for document in documents:
                if document["path"] == candidate["path"]:
                    continue
                identity = independent_identity(candidate["record"], document, rules)
                if not identity and multiple_records:
                    continue
                for captured, start, end, raw_line in labeled_value(document["text"], norm):
                    anchor = substring_anchor(document["path"], document["text"], start, end, document.get("page"))
                    anchor["exact_field_value"] = captured
                    captured_normalized = normalize(captured, {"casefold": True, "trim_whitespace": True})
                    if captured_normalized in MISSING_TOKENS or "unit not reported" in captured_normalized or "unknown unit" in captured_normalized:
                        explicit_missing.append(anchor)
                    elif same_value(observed, captured, rules) or same_value(observed, strip_markdown(captured), rules):
                        supports.append(anchor)
                    elif observed is not None and value_text(observed) != "":
                        conflicts.append({"value": captured, "anchor": anchor})

            # Exact source substrings are independent evidence, but are secondary to
            # same-record field observations. No candidate can corroborate itself.
            for document in documents:
                if document["path"] == candidate["path"]:
                    continue
                if multiple_records and not independent_identity(candidate["record"], document, rules):
                    continue
                supports.extend(find_substrings(document, observed, rules))

            unique_supports = []
            seen = set()
            for anchor in supports:
                fingerprint = canonical(anchor)
                if fingerprint not in seen:
                    seen.add(fingerprint)
                    unique_supports.append(anchor)
            unique_conflicts = []
            seen = set()
            for conflict in conflicts:
                fingerprint = canonical(conflict)
                if fingerprint not in seen:
                    seen.add(fingerprint)
                    unique_conflicts.append(conflict)

            if observed is None or value_text(observed) == "":
                state = "unverifiable"
                reasons.append("The extracted value is missing or null.")
            elif unique_conflicts:
                state = "source_conflict"
                reasons.append("Independent evidence contains a different value for the identified field.")
            elif unique_supports:
                state = "corroborated"
                reasons.append("Independent evidence contains an exact or explicitly normalized match.")
            elif explicit_missing or errors or not source_readable:
                state = "unverifiable"
                if explicit_missing:
                    reasons.append("The matching source field is missing, unknown, or lacks a usable unit.")
                if errors:
                    reasons.append("One or more supplied evidence sources could not be read completely.")
                if not source_readable:
                    reasons.append("No independent readable material evidence is available.")
            else:
                state = "extractor_only"
                reasons.append("No independent evidence supports this non-empty extractor value.")

            claim = {
                "claim_id": claim_id, "record_id": record_id,
                "record_source": candidate["path"], "record_locator": candidate["record_path"],
                "field_path": field_path, "field_type": value_type(observed), "observed_value": observed,
                "state": state, "source_value": unique_supports[0]["exact_substring"] if unique_supports and state == "corroborated" else None,
                "support_anchors": unique_supports, "conflicts": unique_conflicts,
                "missing_or_unusable_anchors": explicit_missing,
                "reason": " ".join(reasons),
                "comparison": "source-anchored typed scalar comparison; no unit conversion or scientific inference",
                "normalization_rules": {key: value for key, value in rules.items() if key != "apply"},
            }
            claims.append(claim)
            field_claims.append(claim)
            states[field_path] = state
            if state == "corroborated":
                source_fields.append(field_path)
                if rules.get("apply") and isinstance(observed, str):
                    replacement = normalize(observed, rules)
                    if replacement != observed:
                        if field_path.startswith("/"):
                            set_pointer(cleaned, field_path, replacement)
                        else:
                            cleaned[field_path] = replacement
                        changes.append({
                            "change_id": "C" + str(len(changes) + 1).zfill(6), "record_id": record_id,
                            "field_path": field_path, "before": observed, "after": replacement,
                            "reason": "Applied only case-enabled normalization to a corroborated value.",
                            "evidence_claim_id": claim_id,
                        })
            else:
                review_fields.append(field_path)
                unsupported.append(field_path)
                review.append({
                    "record_id": record_id, "field_path": field_path, "observed_value": observed,
                    "state": state, "reason": claim["reason"], "claim_id": claim_id,
                    "evidence_refs": unique_supports + [item["anchor"] for item in unique_conflicts] + explicit_missing,
                })

        cleaned_records.append({
            "record_id": record_id, "record_source": candidate["path"],
            "record_locator": candidate["record_path"], "data": cleaned,
            "adjudication": {"field_states": states, "claim_ids": [claim["claim_id"] for claim in field_claims]},
        })
        # Keep scalar top-level CSV fields directly readable; nested values use canonical JSON.
        for key, value in list(cleaned.items()):
            if isinstance(value, (dict, list)):
                cleaned[key] = canonical(value)
        cleaned.update({
            "_record_id": record_id,
            "_evidence_state": "corroborated" if not review_fields else "partial",
            "_review_fields": ";".join(review_fields), "_source_fields": ";".join(source_fields),
            "_unsupported_fields": ";".join(unsupported),
        })
    return claims, changes, review, cleaned_records


def set_pointer(record, pointer, value):
    parts = [part.replace("~1", "/").replace("~0", "~") for part in pointer.split("/")[1:]]
    target = record
    for part in parts[:-1]:
        if isinstance(target, list):
            target = target[int(part)]
        else:
            target = target.get(part)
    last = parts[-1]
    if isinstance(target, list):
        target[int(last)] = value
    elif isinstance(target, dict):
        target[last] = value


def write_cleaned(output, cleaned_records, marker):
    columns = []
    for record in cleaned_records:
        for key in record["data"]:
            if key not in columns:
                columns.append(key)
    for key in CSV_META:
        if key not in columns:
            columns.append(key)
    if marker and "_example_marker" not in columns:
        columns.append("_example_marker")
    with (output / "cleaned.csv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns, extrasaction="ignore", lineterminator="\n")
        writer.writeheader()
        for record in cleaned_records:
            row = dict(record["data"])
            for key in CSV_META:
                row[key] = record["data"].get(key, "")
            if marker:
                row["_example_marker"] = marker
            writer.writerow(row)
    payload = {
        "case_records": cleaned_records,
        "note": "Values retain extractor content unless a case-enabled normalization was applied after corroboration; adjudication states and unresolved fields are explicit.",
    }
    if marker:
        payload["example_marker"] = marker
    dump_json(output / "cleaned.json", payload)


def write_review(output, review, marker):
    columns = ["record_id", "field_path", "observed_value", "state", "reason", "claim_id", "evidence_refs"]
    if marker:
        columns.append("example_marker")
    with (output / "review_queue.csv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns, lineterminator="\n")
        writer.writeheader()
        for item in review:
            row = dict(item)
            row["observed_value"] = value_text(row["observed_value"])
            row["evidence_refs"] = canonical(row["evidence_refs"])
            if marker:
                row["example_marker"] = marker
            writer.writerow(row)


def write_changes_evidence(output, changes, claims, marker):
    if marker:
        for row in changes + claims:
            row["example_marker"] = marker
    dump_jsonl(output / "changes.jsonl", changes)
    dump_jsonl(output / "evidence.jsonl", claims)


def audit_text(context, claims, rules):
    lines = ["# Evidence adjudication audit", ""]
    if context["marker"]:
        lines.extend([context["marker"], ""])
    lines.extend([
        "- case_id: `" + value_text(context["case_id"]) + "`",
        "- status: `" + context["status"] + "`",
        "- deterministic: no network, clock, random values, unit conversion, or inferred scientific answers",
        "- comparison: exact typed scalar matching plus only the case-enabled equivalences listed below",
        "", "## Decision states", "",
    ])
    for state in STATE_ORDER:
        lines.append("- `" + state + "`: " + str(sum(claim["state"] == state for claim in claims)))
    lines.extend(["", "## Source manifest", ""])
    for source in context["sources"]:
        line = "- `" + source["path"] + "`; readable=`" + str(source["readable"]).lower() + "`; sha256=`" + source["sha256"] + "`"
        if source.get("page_locators"):
            line += "; PDF anchors use 1-based pages from `pdftotext -layout` when available"
        if source.get("error"):
            line += "; " + source["error"]
        lines.append(line)
    lines.extend(["", "## Enabled normalization", "", "```json", json.dumps(rules, ensure_ascii=False, sort_keys=True, indent=2), "```", ""])
    lines.append("Output normalization is restricted to corroborated strings. Conflict and missing values are never silently replaced.")
    lines.extend(["", "## Review and limitations", ""])
    if context["review"]:
        for item in context["review"]:
            lines.append("- `" + item["claim_id"] + "` / `" + item["record_id"] + "` / `" + item["field_path"] + "`: **" + item["state"] + "** — " + item["reason"])
    else:
        lines.append("- No field-level review items.")
    for uncertainty in context["uncertainty"]:
        lines.append("- " + uncertainty)
    lines.extend([
        "", "An `extractor_only` value is retained as extractor content and is not source truth. `source_conflict` values are not adjudicated by plausibility. `unverifiable` covers nulls, unreadable/missing evidence, and explicitly unavailable or unit-deficient source values. PDFs without usable `pdftotext` text remain unresolved; page locations are never invented.",
        "",
    ])
    return "\n".join(lines)


def run(args):
    input_dir = Path(args.input)
    output = Path(args.output)
    work = Path(args.work)
    case_path = Path(args.case) if args.case else input_dir / "case.json"
    task_path = Path(args.task) if args.task else input_dir / "task.md"
    output.mkdir(parents=True, exist_ok=True)
    work.mkdir(parents=True, exist_ok=True)
    case = {}
    contract = {}
    case_id = None
    marker = None
    case_error = None
    try:
        case = json.loads(read_text(case_path))
        if not isinstance(case, dict):
            case_error = "case.json must contain a JSON object"
            case = {}
        else:
            case_id = find_case_id(case)
            contract = case.get("output_contract")
            if contract is None:
                for wrapper in ("case", "metadata", "case_metadata", "task", "input"):
                    child = case.get(wrapper)
                    if isinstance(child, dict) and "output_contract" in child:
                        contract = child["output_contract"]
                        break
            if contract is None:
                contract = {}
            candidate_marker = case.get("example_marker", case.get("synthetic_marker"))
            if isinstance(candidate_marker, str):
                marker = candidate_marker
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        case_error = "Cannot read valid case.json: " + exc.__class__.__name__
        case = {}
    context = {
        "case_id": case_id, "status": "partial" if not case_error else "input_error",
        "sources": [], "uncertainty": [], "claims": [], "changes": [], "review": [], "records": [],
        "artifacts": artifact_references(), "errors": [], "warnings": [], "marker": marker,
    }
    if case_error:
        context["errors"].append(case_error)
        context["uncertainty"].append(case_error)
    try:
        write_early_outputs(output, context, contract)
    except OSError as exc:
        print("Cannot create output artifacts: " + str(exc), file=sys.stderr)
        return 2
    if case_error:
        return 2
    try:
        task_text = read_text(task_path)
    except (OSError, UnicodeDecodeError) as exc:
        message = "Cannot read task.md: " + exc.__class__.__name__
        context["status"] = "input_error"
        context["errors"].append(message)
        context["uncertainty"].append(message)
        dump_json(output / "result.json", make_result(context, contract))
        (output / "audit.md").write_text(initial_audit(case_id, "input_error", context["uncertainty"], marker), encoding="utf-8")
        return 2

    try:
        documents, observations, candidates, sources, errors, warnings = load_materials(
            input_dir, case_path, task_path, case, task_text,
        )
        rules = normalization_rules(case)
        claims, changes, review, cleaned = adjudicate(documents, observations, candidates, sources, errors, rules)
        context.update({"sources": sources, "claims": claims, "changes": changes, "review": review, "records": cleaned, "errors": errors, "warnings": warnings})
        context["uncertainty"].extend(errors)
        if not candidates:
            context["uncertainty"].append("No extracted CSV/TSV/JSON records were found.")
        for claim in claims:
            if claim["state"] != "corroborated":
                context["uncertainty"].append(claim["claim_id"] + " " + claim["field_path"] + ": " + claim["state"])
        if not errors and candidates and all(claim["state"] == "corroborated" for claim in claims):
            context["status"] = "success"
        else:
            context["status"] = "partial"
        context["review"] = review
        write_cleaned(output, cleaned, marker)
        write_review(output, review, marker)
        write_changes_evidence(output, changes, claims, marker)
        result = make_result(context, contract)
        if result["unresolved_fields"] and context["status"] == "success":
            context["status"] = "partial"
            result = make_result(context, contract)
        context["uncertainty"] = result["uncertainty"]
        (output / "audit.md").write_text(audit_text(context, claims, rules), encoding="utf-8")
        dump_json(output / "result.json", result)
        return 0
    except Exception as exc:  # Preserve honest partial artifacts on unforeseen per-case failures.
        message = "Adjudication stopped: " + exc.__class__.__name__ + ": " + str(exc)
        context["status"] = "partial"
        context["errors"].append(message)
        context["uncertainty"].append(message)
        dump_json(output / "result.json", make_result(context, contract))
        (output / "audit.md").write_text(initial_audit(case_id, "partial", context["uncertainty"], marker), encoding="utf-8")
        print(message, file=sys.stderr)
        return 1


def find_case_id(case):
    for key in ("case_id", "id"):
        if key in case and scalar(case[key]):
            return case[key]
    for wrapper in ("case", "metadata", "case_metadata", "task", "input"):
        child = case.get(wrapper)
        if isinstance(child, dict):
            if "case_id" in child and scalar(child["case_id"]):
                return child["case_id"]
            if "id" in child and scalar(child["id"]):
                return child["id"]
    return None


def main(argv=None):
    parser = argparse.ArgumentParser(description="Adjudicate extracted records against supplied source evidence.")
    parser.add_argument("--input", default="/input", help="Input directory (default: /input)")
    parser.add_argument("--work", default="/app/work", help="Work directory (default: /app/work)")
    parser.add_argument("--output", default="/app/output", help="Output directory (default: /app/output)")
    parser.add_argument("--case", help="Optional explicit case.json path")
    parser.add_argument("--task", help="Optional explicit task.md path")
    args = parser.parse_args(argv)
    return run(args)


if __name__ == "__main__":
    sys.exit(main())
