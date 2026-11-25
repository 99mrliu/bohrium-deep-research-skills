#!/usr/bin/env python3
"""Conservative observation-identity graph and duplicate adjudication.

Python 3 standard library only. No network, randomness, or wall-clock access.
"""
from __future__ import annotations

import argparse
import csv
import decimal
import hashlib
import json
import os
from pathlib import Path
import re
import sys
from collections import defaultdict

SCHEMA_VERSION = "observation-identity-graph/1.0"
SYNONYM_MODES = {"exact", "token-aware"}
WRAPPERS = {"rows", "data", "records", "observations", "materials", "items", "results"}
COLLECTIONS = {"documents", "extractions", "observations", "rows", "records", "items", "materials", "results", "data"}
ALIASES = {
    "observation_id": ("observation_id", "row_id", "record_id", "id"),
    "duplicate_group": ("duplicate_group", "duplicate_id", "dup_group", "same_as"),
    "document_id": ("document_id", "doc_id", "source_document_id", "source_id", "doi"),
    "extraction_id": ("extraction_id", "extraction_run_id", "parse_id", "extract_id"),
    "experiment_id": ("experiment_id", "experiment", "run_id", "experiment_run_id"),
    "sample_id": ("sample_id", "sample", "specimen_id", "material_sample_id"),
    "material": ("material", "material_name", "compound", "substance", "chemical"),
    "metric": ("metric", "property", "property_name", "measurement", "parameter"),
    "value": ("value", "property_value", "measurement_value", "result", "val"),
    "unit": ("unit", "units", "value_unit", "property_unit"),
}
CONDITION_NAMES = {
    "temperature", "temp", "pressure", "solvent", "atmosphere", "ph", "time",
    "duration", "concentration", "wavelength", "humidity", "medium", "catalyst",
    "additive", "heating_rate", "scan_rate", "current_density", "voltage",
}
CONTEXT_FIELDS = ("document_id", "sample_id", "experiment_id", "material", "metric", "unit")
CORE_FIELDS = ("document_id", "sample_id", "material", "metric", "value", "unit")
SEMANTIC_FIELDS = ("document_id", "sample_id", "experiment_id", "material", "metric", "value", "unit")


def canonical_json(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def digest(value):
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()[:20]


def text(value):
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (dict, list)):
        return canonical_json(value)
    return re.sub(r"\s+", " ", str(value)).strip()


def minimal_value(value):
    """Whitespace and non-unit numeric spelling only; never a chemical conversion."""
    if isinstance(value, (dict, list)):
        if isinstance(value, dict):
            return {str(k): minimal_value(v) for k, v in sorted(value.items(), key=lambda kv: str(kv[0]))}
        return [minimal_value(v) for v in value]
    s = text(value)
    if re.fullmatch(r"[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?", s):
        try:
            d = decimal.Decimal(s)
            if d.is_finite():
                if d == 0:
                    return "0"
                out = format(d.normalize(), "f")
                if "." in out:
                    out = out.rstrip("0").rstrip(".")
                return out
        except decimal.InvalidOperation:
            pass
    return s


def comparable(value):
    return minimal_value(value).casefold() if isinstance(minimal_value(value), str) else minimal_value(value)


def condition_comparable(value):
    return comparable(value)


def safe_float_string(value):
    # Kept for output sanitation: non-finite numeric values become strings, never JSON constants.
    if isinstance(value, float) and (value != value or value in (float("inf"), float("-inf"))):
        return str(value)
    if isinstance(value, dict):
        return {str(k): safe_float_string(v) for k, v in value.items()}
    if isinstance(value, list):
        return [safe_float_string(v) for v in value]
    return value


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(safe_float_string(value), ensure_ascii=False, indent=2, sort_keys=True, allow_nan=False) + "\n", encoding="utf-8")


def write_jsonl(path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        for row in rows:
            handle.write(canonical_json(safe_float_string(row)) + "\n")


def write_csv(path, rows, fieldnames=None):
    path.parent.mkdir(parents=True, exist_ok=True)
    if fieldnames is None:
        fieldnames = []
        for row in rows:
            for key in row:
                if key not in fieldnames:
                    fieldnames.append(key)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="ignore", lineterminator="\n")
        writer.writeheader()
        for row in rows:
            writer.writerow({k: text(row.get(k, "")) if isinstance(row.get(k), (dict, list)) else row.get(k, "") for k in fieldnames})


def unwrap_meta(obj):
    while isinstance(obj, dict) and len(obj) == 1:
        key = next(iter(obj))
        if key in {"case", "task", "metadata", "config"} and isinstance(obj[key], dict):
            obj = obj[key]
        else:
            break
    return obj


def load_json(path):
    def reject_constant(value):
        raise ValueError("Non-finite JSON number is invalid: " + value)
    return json.loads(path.read_text(encoding="utf-8-sig"), parse_constant=reject_constant)


def resolve_optional(base, supplied, candidates):
    if supplied:
        p = Path(supplied)
        if not p.is_absolute():
            p = base / p
        return p if p.is_file() else None
    for name in candidates:
        p = base / name
        if p.is_file():
            return p
    return None


def load_metadata(path):
    """Read JSON metadata or preserve Markdown task text without inventing rules."""
    if path.suffix.casefold() == ".json":
        return unwrap_meta(load_json(path))
    if path.suffix.casefold() == ".jsonl":
        merged = {}
        with path.open("r", encoding="utf-8-sig") as handle:
            for line in handle:
                if line.strip():
                    item = json.loads(line)
                    if isinstance(item, dict):
                        merged = merge_meta(merged, unwrap_meta(item))
        return merged
    return {"task_text": path.read_text(encoding="utf-8-sig")}


def source_path(path, input_dir):
    try:
        return path.relative_to(input_dir).as_posix()
    except ValueError:
        # Absolute metadata paths outside --input are legal; do not leak host paths.
        return path.name


def merge_meta(case, task):
    merged = {}
    for source in (case, task):
        if isinstance(source, dict):
            for key, value in source.items():
                if key in {"identity_contract", "identity", "row_identity", "duplicate_policy"} and isinstance(value, dict):
                    merged[key] = value
                elif key not in merged:
                    merged[key] = value
    return merged


def get_identity_contract(meta):
    contract = {}
    for key in ("identity_contract", "row_identity", "identity", "duplicate_policy"):
        value = meta.get(key)
        if isinstance(value, dict):
            contract.update(value)
    row_field = contract.get("row_id_field", meta.get("row_id_field", "observation_id"))
    fields = contract.get("identity_fields", contract.get("fields", meta.get("identity_fields", [row_field])))
    if isinstance(fields, str):
        fields = [fields]
    candidate_fields = contract.get("candidate_identity_fields", contract.get("blocking_identity_fields", fields))
    if isinstance(candidate_fields, str):
        candidate_fields = [candidate_fields]
    transport_fields = contract.get("transport_fields", contract.get("exact_duplicate_fields", fields))
    if isinstance(transport_fields, str):
        transport_fields = [transport_fields]
    allow = contract.get("allow_exact_transport_duplicates", contract.get("auto_deduplicate", False)) is True
    explicit = bool(contract) and bool(fields)
    return {
        "row_id_field": str(row_field),
        "identity_fields": [str(v) for v in fields],
        "candidate_identity_fields": [str(v) for v in candidate_fields],
        "transport_fields": [str(v) for v in transport_fields],
        "allow_exact_transport_duplicates": allow,
        "declared": explicit,
    }


def get_condition_fields(meta, records):
    fields = set()
    for container in (meta.get("identity_contract"), meta.get("extraction_contract"), meta):
        if isinstance(container, dict):
            declared = container.get("condition_fields", container.get("conditions"))
            if isinstance(declared, str):
                fields.add(declared)
            elif isinstance(declared, list):
                fields.update(str(v) for v in declared)
    for record in records:
        for key in record["raw"]:
            low = key.casefold()
            if low in CONDITION_NAMES or low.startswith("condition_") or low.startswith("condition."):
                fields.add(key)
    return sorted(fields)


def synonym_config(meta):
    raw = meta.get("synonyms", meta.get("synonym_map", {}))
    output = {}
    if not isinstance(raw, dict):
        return output
    for field, mapping in raw.items():
        if not isinstance(mapping, dict):
            continue
        exact = {}
        token = {}
        for canonical, aliases in mapping.items():
            values = aliases if isinstance(aliases, list) else [aliases]
            for alias in values + [canonical]:
                normalized = text(alias).casefold()
                exact[normalized] = str(canonical)
                tokens = tuple(sorted(re.findall(r"[\w]+", normalized, flags=re.UNICODE)))
                if tokens:
                    token[tokens] = str(canonical)
        output[str(field)] = {"exact": exact, "token": token}
    return output


def canonical_synonym(field, value, config):
    s = text(value)
    if field not in config or not s:
        return s
    folded = s.casefold()
    if folded in config[field]["exact"]:
        return config[field]["exact"][folded]
    tokens = tuple(sorted(re.findall(r"[\w]+", folded, flags=re.UNICODE)))
    return config[field]["token"].get(tokens, s)


def raw_value(raw, field):
    if field in raw:
        return raw[field]
    folded = field.casefold()
    for key in raw:
        if key.casefold() == folded:
            return raw[key]
    aliases = ALIASES.get(field, ())
    for alias in aliases:
        if alias in raw:
            return raw[alias]
    for key in raw:
        if key.casefold() in aliases:
            return raw[key]
    return ""


def flatten_json_records(obj, inherited=None, output=None):
    """Flatten common document -> extraction -> observation wrappers with inheritance."""
    if output is None:
        output = []
    if inherited is None:
        inherited = {}
    if isinstance(obj, list):
        for item in obj:
            flatten_json_records(item, inherited, output)
        return output
    if not isinstance(obj, dict):
        return output
    if len(obj) == 1 and next(iter(obj)) in WRAPPERS:
        return flatten_json_records(next(iter(obj.values())), inherited, output)
    local = dict(inherited)
    for key, value in obj.items():
        if key not in COLLECTIONS and not isinstance(value, (list, dict)):
            local[key] = value
    found_collection = False
    for key in COLLECTIONS:
        if key in obj and isinstance(obj[key], (list, dict)):
            found_collection = True
            flatten_json_records(obj[key], local, output)
    if not found_collection:
        # A JSON object with scalar attributes is a row; nested condition objects are retained.
        row = dict(local)
        for key, value in obj.items():
            if key not in COLLECTIONS:
                row[key] = value
        if row:
            output.append(row)
    return output


def read_material(path):
    suffix = path.suffix.casefold()
    if suffix == ".json":
        return flatten_json_records(load_json(path))
    if suffix == ".jsonl":
        records = []
        with path.open("r", encoding="utf-8-sig") as handle:
            for line_number, line in enumerate(handle, 1):
                if not line.strip():
                    continue
                try:
                    obj = json.loads(line, parse_constant=lambda v: (_ for _ in ()).throw(ValueError(v)))
                except (json.JSONDecodeError, ValueError) as exc:
                    raise ValueError(f"{path.name}:{line_number}: invalid JSONL: {exc}") from exc
                flatten_json_records(obj, output=records)
        return records
    if suffix in {".csv", ".tsv"}:
        with path.open("r", encoding="utf-8-sig", newline="") as handle:
            if suffix == ".tsv":
                dialect = csv.excel_tab
            else:
                sample = handle.read(8192)
                handle.seek(0)
                try:
                    dialect = csv.Sniffer().sniff(sample, delimiters=",\t")
                except csv.Error:
                    dialect = csv.excel
            reader = csv.DictReader(handle, dialect=dialect)
            if not reader.fieldnames:
                return []
            return [{str(k): (v if v is not None else "") for k, v in row.items() if k is not None} for row in reader]
    raise ValueError("Unsupported material format: " + path.name)


def make_record(raw, source_name, source_row, synonyms):
    canonical = {}
    for field, aliases in ALIASES.items():
        value = raw_value(raw, field)
        if field in {"material", "metric"}:
            value = canonical_synonym(field, value, synonyms)
        else:
            value = minimal_value(value)
        canonical[field] = value
    declared_duplicate = raw_value(raw, "duplicate_group")
    canonical["duplicate_group"] = minimal_value(declared_duplicate)
    normalized_raw = {str(k): minimal_value(v) for k, v in sorted(raw.items(), key=lambda kv: str(kv[0]))}
    source_key = source_name + "#" + str(source_row)
    return {
        "raw": raw,
        "normalized_raw": normalized_raw,
        "canonical": canonical,
        "source_name": source_name,
        "source_row": source_row,
        "node_id": "obs_" + digest({"source": source_name, "row": source_row, "raw": normalized_raw}),
        "source_key": source_key,
    }


def condition_map(record, fields):
    output = {}
    raw = record["raw"]
    for field in fields:
        value = raw_value(raw, field)
        if text(value):
            output[field] = condition_comparable(value)
    nested = raw_value(raw, "conditions")
    if isinstance(nested, dict):
        for key, value in nested.items():
            output["conditions." + str(key)] = condition_comparable(value)
    elif text(nested):
        try:
            parsed = json.loads(str(nested))
            if isinstance(parsed, dict):
                for key, value in parsed.items():
                    output["conditions." + str(key)] = condition_comparable(value)
            else:
                output["conditions"] = condition_comparable(nested)
        except (json.JSONDecodeError, TypeError):
            output["conditions"] = condition_comparable(nested)
    # Unknown condition-prefixed keys are always included, preventing silent context loss.
    for key, value in raw.items():
        low = str(key).casefold()
        if (low.startswith("condition_") or low.startswith("condition.")) and key not in output:
            if text(value):
                output[key] = condition_comparable(value)
    return {key: output[key] for key in sorted(output)}


def field_equal(record, other, field):
    if field in {"conditions", "condition_fingerprint"}:
        return record["conditions"] == other["conditions"]
    if field in record["canonical"]:
        return comparable(record["canonical"][field]) == comparable(other["canonical"][field])
    return comparable(raw_value(record["raw"], field)) == comparable(raw_value(other["raw"], field))


def mismatch_fields(a, b):
    mismatches = []
    for field in ("observation_id", "duplicate_group", "extraction_id") + SEMANTIC_FIELDS:
        if not field_equal(a, b, field):
            mismatches.append(field)
    keys = sorted(set(a["conditions"]) | set(b["conditions"]))
    for key in keys:
        if key not in a["conditions"]:
            mismatches.append(key + " (missing_left)")
        elif key not in b["conditions"]:
            mismatches.append(key + " (missing_right)")
        elif a["conditions"][key] != b["conditions"][key]:
            mismatches.append(key)
    # Differences in any undeclared raw field forbid an exact transport certificate.
    for key in sorted(set(a["normalized_raw"]) | set(b["normalized_raw"])):
        if key in ALIASES or key in ALIASES.get("observation_id", ()):
            continue
        if key not in a["normalized_raw"]:
            mismatches.append(str(key) + " (missing_left)")
        elif key not in b["normalized_raw"]:
            mismatches.append(str(key) + " (missing_right)")
        elif comparable(a["normalized_raw"][key]) != comparable(b["normalized_raw"][key]):
            mismatches.append(str(key))
    return sorted(set(mismatches))


def semantic_equal(a, b, include_experiment=True):
    fields = SEMANTIC_FIELDS if include_experiment else CORE_FIELDS
    return all(field_equal(a, b, field) for field in fields) and a["conditions"] == b["conditions"]


def core_equal(a, b):
    return all(field_equal(a, b, field) for field in ("document_id", "sample_id", "material", "metric"))


def same_value(a, b):
    return field_equal(a, b, "value") and field_equal(a, b, "unit")


def identity_values(record, fields):
    return tuple(comparable(raw_value(record["raw"], field)) for field in fields)


def candidate_pairs(records, contract):
    blocks = defaultdict(set)
    for i, record in enumerate(records):
        c = record["canonical"]
        for field in contract["candidate_identity_fields"]:
            value = comparable(raw_value(record["raw"], field))
            if value != "":
                # Block each declared key independently: a shared duplicate_group must
                # still create a candidate when observation_id values differ.
                blocks[("identity", field, value)].add(i)
        if c["document_id"] and c["sample_id"] and c["material"] and c["metric"]:
            blocks[("source_core", c["document_id"], c["sample_id"], c["material"], c["metric"])].add(i)
        if c["sample_id"] and c["material"] and c["metric"]:
            blocks[("condition_core", c["sample_id"], c["material"], c["metric"], record["condition_fingerprint"])].add(i)
            blocks[("sample_metric", c["sample_id"], c["material"], c["metric"])].add(i)
        if c["experiment_id"] and c["material"] and c["metric"]:
            blocks[("experiment", c["experiment_id"], c["material"], c["metric"])].add(i)
    pairs = set()
    for members in blocks.values():
        ordered = sorted(members)
        for offset, left in enumerate(ordered):
            for right in ordered[offset + 1:]:
                pairs.add((left, right))
    return sorted(pairs)


def certificate(kind, rule, matched, mismatched, left, right, explanation):
    return {
        "certificate_type": kind,
        "rule": rule,
        "matched_fields": sorted(set(matched)),
        "mismatching_fields": sorted(set(mismatched)),
        "left_observation_node_id": left["node_id"],
        "right_observation_node_id": right["node_id"],
        "explanation": explanation,
    }


def adjudicate(records, contract):
    decisions = []
    allowed_pairs = set()
    for index, (left, right) in enumerate(candidate_pairs(records, contract), 1):
        a, b = records[left], records[right]
        mismatches = mismatch_fields(a, b)
        identity_fields_matched = [
            field for field in contract["candidate_identity_fields"]
            if comparable(raw_value(a["raw"], field)) != ""
            and comparable(raw_value(a["raw"], field)) == comparable(raw_value(b["raw"], field))
        ]
        identity_match = bool(identity_fields_matched)
        transport_match = (
            identity_match
            and all(field_equal(a, b, field) for field in contract["transport_fields"])
            and any(comparable(raw_value(a["raw"], field)) != "" for field in contract["transport_fields"])
        )
        raw_same = a["normalized_raw"] == b["normalized_raw"]
        category = "unresolved"
        action = "reject"
        rule = "insufficient_evidence"
        explanation = "Candidate remains separate because the identity contract does not prove an exact transport duplicate."
        matched = []
        if identity_match:
            matched.extend(identity_fields_matched)
        if raw_same and transport_match and contract["declared"] and contract["allow_exact_transport_duplicates"]:
            category, action, rule = "exact_transport_duplicate", "merge", "declared_exact_transport_identity"
            explanation = "All normalized raw fields and every declared transport identity field match; the case explicitly permits automatic transport deduplication."
            matched.extend(contract["transport_fields"] + ["normalized_raw"])
            allowed_pairs.add((left, right))
        elif identity_match and not raw_same:
            category, rule = "conflicting_identity", "explicit_identity_context_conflict"
            explanation = "An explicit declared identity matches, but one or more source, sample, material, metric, value, or condition fields conflict."
        elif raw_same and not (contract["declared"] and contract["allow_exact_transport_duplicates"]):
            category, rule = "unresolved", "exact_values_without_identity_authorization"
            explanation = "Identical values cannot be merged because the case has no enabling exact-transport identity contract."
            matched.append("normalized_raw")
        elif semantic_equal(a, b, include_experiment=True):
            category, rule = "repeated_extraction", "same_experiment_observation_distinct_extraction"
            explanation = "The semantic observation repeats within the same declared experiment; this is evidence duplication, not a certified transport duplicate."
            matched.extend(list(SEMANTIC_FIELDS) + ["conditions"])
        elif (not field_equal(a, b, "experiment_id") and a["canonical"]["experiment_id"] and b["canonical"]["experiment_id"]
              and all(field_equal(a, b, field) for field in ("sample_id", "material", "metric"))
              and a["conditions"] == b["conditions"]):
            category, rule = "repeated_experiment", "distinct_experiment_same_condition"
            explanation = "The same sample/material/metric/condition occurs under different experiment identities and is retained as a repeated experiment, including when reported by different documents."
            matched.extend(["sample_id", "material", "metric", "conditions"])
            if same_value(a, b):
                matched.extend(["value", "unit"])
        elif core_equal(a, b) and a["conditions"] != b["conditions"]:
            category, rule = "same_core_different_context", "full_condition_fingerprint_mismatch"
            explanation = "The observation core is similar but the full condition fingerprint differs; equal values never override this context mismatch."
            matched.extend(["document_id", "sample_id", "material", "metric"])
        elif semantic_equal(a, b, include_experiment=False):
            category, rule = "unresolved", "same_semantics_without_experiment_or_identity_proof"
            explanation = "Matching values and conditions are insufficient to distinguish repeated extraction from independent observation without experiment/identity evidence."
            matched.extend(list(CORE_FIELDS) + ["conditions"])
        if action == "reject":
            cert = certificate("deny", rule, matched, mismatches, a, b, explanation)
        else:
            cert = certificate("allow", rule, matched, mismatches, a, b, explanation)
            if cert["mismatching_fields"]:
                raise AssertionError("Allow certificate cannot contain mismatches")
        decisions.append({
            "decision_id": "dec_" + digest({"left": a["node_id"], "right": b["node_id"], "category": category}),
            "left_observation_node_id": a["node_id"],
            "right_observation_node_id": b["node_id"],
            "left_observation_id": a["canonical"]["observation_id"] or None,
            "right_observation_id": b["canonical"]["observation_id"] or None,
            "action": action,
            "category": category,
            "cluster_relationship": "certified_transport_duplicate" if action == "merge" else "retained_separately",
            "certificate": cert,
        })
    return decisions, allowed_pairs


def components(records, allowed_pairs):
    parent = list(range(len(records)))
    def root(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i
    for left, right in sorted(allowed_pairs):
        rl, rr = root(left), root(right)
        if rl != rr:
            parent[max(rl, rr)] = min(rl, rr)
    groups = defaultdict(list)
    for i in range(len(records)):
        groups[root(i)].append(i)
    ordered = sorted(groups.values(), key=lambda members: min(records[j]["node_id"] for j in members))
    cluster_for = {}
    representative = {}
    for members in ordered:
        cluster = "cluster_" + digest([records[j]["node_id"] for j in members])
        keeper = min(members, key=lambda j: (records[j]["source_name"], records[j]["source_row"]))
        for j in members:
            cluster_for[j] = cluster
            representative[j] = keeper
    return cluster_for, representative


def graph_records(records, decisions, cluster_for, representative):
    nodes = {}
    edges = {}
    for i, record in enumerate(records):
        c = record["canonical"]
        doc_key = c["document_id"] or "file:" + record["source_name"]
        doc_id = "doc_" + digest(doc_key)
        extraction_key = c["extraction_id"] or (doc_key + "#unidentified-extraction")
        extraction_id = "ext_" + digest(extraction_key)
        if doc_id not in nodes:
            nodes[doc_id] = {"record_type": "node", "node_type": "document", "node_id": doc_id, "identity": c["document_id"] or None, "source_file": record["source_name"]}
        if extraction_id not in nodes:
            nodes[extraction_id] = {"record_type": "node", "node_type": "extraction", "node_id": extraction_id, "identity": c["extraction_id"] or None, "document_node_id": doc_id}
        disposition = "exact_transport_duplicate" if representative[i] != i else "retained_unique"
        related_decisions = [d for d in decisions if record["node_id"] in {d["left_observation_node_id"], d["right_observation_node_id"]}]
        if representative[i] == i and any(d["action"] == "merge" for d in related_decisions):
            disposition = "retained_transport_representative"
        else:
            related = [d["category"] for d in related_decisions if d["action"] == "reject"]
            if representative[i] == i and related:
                priority = ["conflicting_identity", "repeated_extraction", "repeated_experiment", "same_core_different_context", "unresolved"]
                disposition = "retained_" + sorted(set(related), key=lambda v: priority.index(v) if v in priority else 99)[0]
        record["disposition"] = disposition
        nodes[record["node_id"]] = {
            "record_type": "node", "node_type": "observation", "node_id": record["node_id"],
            "observation_id": c["observation_id"] or None, "document_node_id": doc_id,
            "extraction_node_id": extraction_id, "sample_id": c["sample_id"] or None,
            "experiment_id": c["experiment_id"] or None, "material": c["material"] or None,
            "metric": c["metric"] or None, "value": c["value"] or None, "unit": c["unit"] or None,
            "conditions": record["conditions"], "condition_fingerprint": record["condition_fingerprint"],
            "disposition": disposition, "cluster_id": cluster_for[i],
            "statistical_include": representative[i] == i,
            "source_file": record["source_name"], "source_row": record["source_row"],
        }
        for edge_type, target in (("EXTRACTED_FROM", extraction_id), ("OBSERVED_IN", doc_id)):
            edge_id = "edge_" + digest([record["node_id"], edge_type, target])
            edges[edge_id] = {"record_type": "edge", "edge_type": edge_type, "edge_id": edge_id, "from": record["node_id"], "to": target, "evidence": "declared_or_source_locator"}
    typed = {
        "SAME_EXTRACTION": lambda r: r["canonical"]["extraction_id"],
        "SAME_SAMPLE": lambda r: r["canonical"]["sample_id"],
        "SAME_CONDITION": lambda r: r["condition_fingerprint"],
        "SAME_EXPERIMENT": lambda r: r["canonical"]["experiment_id"],
    }
    for edge_type, getter in typed.items():
        groups = defaultdict(list)
        for i, record in enumerate(records):
            value = getter(record)
            if value:
                if edge_type == "SAME_CONDITION":
                    # A condition edge is meaningful only for the same measurement core.
                    key = (record["canonical"]["sample_id"], record["canonical"]["material"], record["canonical"]["metric"], value)
                else:
                    key = value
                groups[key].append(i)
        for key, members in groups.items():
            for offset, left in enumerate(members):
                for right in members[offset + 1:]:
                    edge_id = "edge_" + digest([edge_type, records[left]["node_id"], records[right]["node_id"]])
                    edges[edge_id] = {
                        "record_type": "edge", "edge_type": edge_type, "edge_id": edge_id,
                        "from": records[left]["node_id"], "to": records[right]["node_id"],
                        "evidence": {"key": text(key), "not_a_merge_certificate": True},
                    }
    for decision in decisions:
        if decision["action"] == "merge":
            edge_id = "edge_" + digest(["CERTIFIED_TRANSPORT_DUPLICATE", decision["decision_id"]])
            edges[edge_id] = {
                "record_type": "edge", "edge_type": "CERTIFIED_TRANSPORT_DUPLICATE", "edge_id": edge_id,
                "from": decision["left_observation_node_id"], "to": decision["right_observation_node_id"],
                "decision_id": decision["decision_id"], "allow_certificate": decision["certificate"],
            }
    return list(nodes.values()) + list(edges.values())


def contract_entries(meta):
    contract = meta.get("output_contract")
    if contract is None:
        for wrapper in ("case", "metadata", "case_metadata", "task", "input"):
            child = meta.get(wrapper)
            if isinstance(child, dict) and "output_contract" in child:
                contract = child["output_contract"]
                break
    entries = []

    def add(name, spec):
        if name and all(existing != str(name) for existing, _ in entries):
            entries.append((str(name), spec))

    def visit(node):
        if isinstance(node, str):
            add(node, node)
        elif isinstance(node, list):
            for item in node:
                if isinstance(item, dict):
                    name = item.get("name", item.get("field", item.get("key")))
                    if name:
                        add(name, item)
                    else:
                        visit(item)
                else:
                    visit(item)
        elif isinstance(node, dict):
            name = node.get("name", node.get("field", node.get("key")))
            if name and len(node) > 1:
                add(name, node)
                return
            wrappers = [key for key in ("fields", "properties", "outputs", "artifacts", "files") if key in node]
            wrapper_controls = {"fields", "properties", "outputs", "artifacts", "files", "required", "type", "description", "title", "additionalProperties"}
            if wrappers and set(node).issubset(wrapper_controls):
                for key in wrappers:
                    visit(node[key])
                required = node.get("required", [])
                if isinstance(required, list):
                    for item in required:
                        if isinstance(item, str) and all(existing != item for existing, _ in entries):
                            add(item, {})
                return
            if isinstance(node.get("required"), list) and len(node) == 1:
                visit(node["required"])
                return
            for key, spec in node.items():
                if key not in {"type", "description", "title", "additionalProperties"}:
                    add(key, spec)

    visit(contract if contract is not None else {})
    return entries


KNOWN_CONTRACT = {
    "cleaned_csv": "cleaned.csv", "cleaned": "cleaned.csv", "cleaned_json": "cleaned.json",
    "observation_graph": "observation_graph.jsonl", "graph": "observation_graph.jsonl",
    "duplicate_decisions": "duplicate_decisions.jsonl", "decisions": "duplicate_decisions.jsonl",
    "changes": "changes.jsonl", "change_records": "changes.jsonl", "review_queue": "review_queue.csv",
    "audit": "audit.md", "result": "result.json",
}


def contract_result_value(name, spec, counts):
    stem = re.sub(r"(?:_file|_path|_output)$", "", name.casefold())
    filename = KNOWN_CONTRACT.get(name, KNOWN_CONTRACT.get(stem))
    if not filename:
        lowered = name.casefold()
        for key, candidate in KNOWN_CONTRACT.items():
            if key in lowered:
                filename = candidate
                break
    if not filename:
        return None, False
    descriptor = {"path": filename, "record_count": counts.get(filename, 0)}
    if isinstance(spec, dict):
        value = dict(spec)
        value.update(descriptor)
        return value, True
    if isinstance(spec, list):
        return {"contract": spec, **descriptor}, True
    return descriptor, True


def run(args):
    input_dir = Path(args.input)
    work_dir = Path(args.work)
    output_dir = Path(args.output)
    work_dir.mkdir(parents=True, exist_ok=True)
    output_dir.mkdir(parents=True, exist_ok=True)
    paths = {
        "cleaned.csv": output_dir / "cleaned.csv", "cleaned.json": output_dir / "cleaned.json",
        "observation_graph.jsonl": output_dir / "observation_graph.jsonl",
        "duplicate_decisions.jsonl": output_dir / "duplicate_decisions.jsonl",
        "changes.jsonl": output_dir / "changes.jsonl", "review_queue.csv": output_dir / "review_queue.csv",
        "audit.md": output_dir / "audit.md", "result.json": output_dir / "result.json",
    }
    case_id = None
    uncertainty = []
    sources = []
    status = "partial"
    write_json(paths["result.json"], {"schema_version": SCHEMA_VERSION, "case_id": None, "status": status, "sources": [], "uncertainty": ["Processing has started; outputs are partial."], "change_records": {"path": "changes.jsonl", "record_count": 0}, "review_queue": {"path": "review_queue.csv", "record_count": 0}, "artifacts": {}})
    exit_code = 0
    try:
        if not input_dir.is_dir():
            raise ValueError("Input directory does not exist: " + str(input_dir))
        case_path = resolve_optional(input_dir, args.case, ("case.json", "case.jsonl"))
        task_path = resolve_optional(input_dir, args.task, ("task.md", "task.json", "task.jsonl"))
        if args.case and case_path is None:
            raise ValueError("Invalid case: explicitly supplied --case file was not found")
        if args.task and task_path is None:
            raise ValueError("Invalid case: explicitly supplied --task file was not found")
        case_obj = load_metadata(case_path) if case_path else {}
        task_obj = load_metadata(task_path) if task_path else {}
        meta = merge_meta(case_obj, task_obj)
        for role, path in (("case", case_path), ("task", task_path)):
            if path:
                content = path.read_bytes()
                sources.append({"path": source_path(path, input_dir), "role": role, "sha256": hashlib.sha256(content).hexdigest(), "bytes": len(content)})
        case_id = meta.get("case_id", meta.get("id"))
        if case_id is None:
            for wrapper in ("case", "metadata", "case_metadata", "task", "input"):
                child = meta.get(wrapper)
                if isinstance(child, dict) and child.get("case_id", child.get("id")) is not None:
                    case_id = child.get("case_id", child.get("id"))
                    break
        case_id = text(case_id) or None
        if not case_id:
            raise ValueError("Invalid case: missing case_id in case/task metadata")
        excluded = {p.resolve() for p in (case_path, task_path) if p}
        material_paths = [p for p in sorted(input_dir.rglob("*"), key=lambda p: p.as_posix()) if p.is_file() and p.suffix.casefold() in {".csv", ".tsv", ".json", ".jsonl"} and p.resolve() not in excluded]
        raw_records = []
        if case_path:
            embedded = {key: case_obj[key] for key in ("records", "rows", "observations", "extractions", "data", "items", "results") if key in case_obj}
            if embedded:
                case_name = source_path(case_path, input_dir)
                for row_number, row in enumerate(flatten_json_records(embedded), 1):
                    if isinstance(row, dict):
                        raw_records.append((case_name, row_number, row))
        if not material_paths and not raw_records:
            raise ValueError("Invalid case: no external or embedded CSV/TSV/JSON/JSONL observations")
        for path in material_paths:
            content = path.read_bytes()
            sources.append({"path": path.relative_to(input_dir).as_posix(), "role": "material", "sha256": hashlib.sha256(content).hexdigest(), "bytes": len(content)})
            rows = read_material(path)
            for row_number, row in enumerate(rows, 1):
                if isinstance(row, dict):
                    raw_records.append((path.relative_to(input_dir).as_posix(), row_number, row))
        if not raw_records:
            raise ValueError("Invalid case: material files contain no observation objects")
        contract = get_identity_contract(meta)
        if not (contract["declared"] and contract["allow_exact_transport_duplicates"]):
            uncertainty.append({"code": "NO_AUTO_DEDUP_AUTHORIZATION", "message": "No enabling case identity contract; identical rows remain unmerged and unresolved."})
        synonyms = synonym_config(meta)
        records = [make_record(raw, source, row, synonyms) for source, row, raw in raw_records]
        condition_fields = get_condition_fields(meta, records)
        for record in records:
            record["conditions"] = condition_map(record, condition_fields)
            record["condition_fingerprint"] = "cond_" + digest(record["conditions"])
        decisions, allowed_pairs = adjudicate(records, contract)
        cluster_for, representative = components(records, allowed_pairs)
        graph = graph_records(records, decisions, cluster_for, representative)
        example_marker = text(meta.get("example_marker", ""))
        if example_marker:
            for item in graph + decisions:
                item["example_marker"] = example_marker
        cleaned = []
        changes = []
        metadata_fields = ["_observation_node_id", "_disposition", "_cluster_id", "_statistical_include", "_condition_fingerprint", "_source_file", "_source_row"]
        original_fields = []
        for record in records:
            for key in record["raw"]:
                if key not in original_fields:
                    original_fields.append(key)
        for i, record in enumerate(records):
            row = dict(record["raw"])
            for field in ("material", "metric"):
                if field in row and text(row[field]) != text(record["canonical"][field]):
                    changes.append({"change_id": "chg_" + digest([record["node_id"], field, row[field], record["canonical"][field]]), "observation_node_id": record["node_id"], "change_type": "declared_synonym_canonicalization", "field": field, "before": row[field], "after": record["canonical"][field], "reason": "Exact or token-aware match in the case-declared synonym map; no chemical inference."})
                    row[field] = record["canonical"][field]
            row.update({
                "_observation_node_id": record["node_id"], "_disposition": record["disposition"],
                "_cluster_id": cluster_for[i], "_statistical_include": representative[i] == i,
                "_condition_fingerprint": record["condition_fingerprint"], "_source_file": record["source_name"],
                "_source_row": record["source_row"],
            })
            if representative[i] != i:
                changes.append({"change_id": "chg_" + digest([record["node_id"], "statistical_exclusion"]), "observation_node_id": record["node_id"], "change_type": "statistical_view_exclusion", "field": "_statistical_include", "before": True, "after": False, "reason": "Certified exact transport duplicate; retained in cleaned output and excluded only from statistical view.", "cluster_id": cluster_for[i]})
            cleaned.append(row)
        review = []
        for decision in decisions:
            if decision["action"] == "reject":
                cert = decision["certificate"]
                review.append({
                    "review_id": "rev_" + decision["decision_id"], "decision_id": decision["decision_id"],
                    "left_observation_node_id": decision["left_observation_node_id"], "right_observation_node_id": decision["right_observation_node_id"],
                    "category": decision["category"], "priority": "high" if decision["category"] in {"conflicting_identity", "unresolved"} else "medium",
                    "mismatching_fields": ";".join(cert["mismatching_fields"]), "rule": cert["rule"],
                    "status": "needs_review" if decision["category"] in {"conflicting_identity", "unresolved"} else "informational_retained",
                    "example_marker": example_marker,
                })
        for change in changes:
            if example_marker:
                change["example_marker"] = example_marker
        statistical_rows = [cleaned[i] for i in range(len(records)) if representative[i] == i]
        excluded_ids = [records[i]["node_id"] for i in range(len(records)) if representative[i] != i]
        cleaned_document = {
            "schema_version": SCHEMA_VERSION, "case_id": case_id, "example_marker": example_marker or None, "rows": cleaned,
            "statistical_view": {"row_count": len(statistical_rows), "excluded_observation_node_ids": excluded_ids, "exclusion_rule": "Exclude only rows with an allow-certified exact_transport_duplicate; no semantic or contextual duplicate is excluded.", "rows": statistical_rows},
        }
        write_csv(paths["cleaned.csv"], cleaned, original_fields + metadata_fields)
        write_json(paths["cleaned.json"], cleaned_document)
        write_jsonl(paths["observation_graph.jsonl"], graph)
        write_jsonl(paths["duplicate_decisions.jsonl"], decisions)
        write_jsonl(paths["changes.jsonl"], changes)
        write_csv(paths["review_queue.csv"], review, ["review_id", "decision_id", "left_observation_node_id", "right_observation_node_id", "category", "priority", "mismatching_fields", "rule", "status", "example_marker"])
        counts = {"cleaned.csv": len(cleaned), "cleaned.json": len(cleaned), "observation_graph.jsonl": len(graph), "duplicate_decisions.jsonl": len(decisions), "changes.jsonl": len(changes), "review_queue.csv": len(review), "audit.md": 1, "result.json": 1}
        category_counts = defaultdict(int)
        for decision in decisions:
            category_counts[decision["category"]] += 1
        if category_counts["conflicting_identity"]:
            uncertainty.append({"code": "CONFLICTING_IDENTITY", "count": category_counts["conflicting_identity"], "message": "Explicit identity candidates with conflicting fields remain unmerged and queued for review."})
        if category_counts["unresolved"]:
            uncertainty.append({"code": "UNRESOLVED_CANDIDATES", "count": category_counts["unresolved"], "message": "Candidates with insufficient identity evidence remain unmerged and queued for review."})
        audit = [
            "# Observation identity graph audit", "", f"- Case ID: `{case_id}`", f"- Schema: `{SCHEMA_VERSION}`",
            f"- Input observations: **{len(records)}**", f"- Cleaned rows retained: **{len(cleaned)}**",
            f"- Statistical-view rows: **{len(statistical_rows)}**", f"- Statistical exclusions (certified transport only): **{len(excluded_ids)}**",
            "", "## Case identity contract", "", "```json", canonical_json(contract), "```", "",
            "Automatic merge requires normalized raw equality, equality of every declared transport field, and explicit case authorization. Same values never override source, sample, material, metric, experiment, or full-condition mismatches.",
            "", "## Decision categories", "",
        ]
        for category in sorted(category_counts):
            audit.append(f"- `{category}`: {category_counts[category]}")
        audit += ["", "## Certificates", "", f"Every one of {len(decisions)} candidate decisions has an explicit allow or deny certificate. Deny certificates enumerate `mismatching_fields`; an empty list means evidence was insufficient rather than that contexts were proven equal. Graph `SAME_*` edges are contextual assertions, not merge authorization.", "", "## Statistical view", "", "All rows are retained in `cleaned.csv` and `cleaned.json`. Only certified transport duplicates have `_statistical_include=false`. `cleaned.json` embeds the derived statistical view.", "", "## Uncertainty and limits", ""]
        if uncertainty:
            audit.extend(f"- `{item['code']}`: {item['message']}" for item in uncertainty)
        else:
            audit.append("- Candidates not authorized as exact transport duplicates remain separate; unresolved candidates require human review.")
        audit += ["- Normalization is limited to whitespace, numeric spelling, and case-declared exact/token-aware synonyms. No units or chemical identities are inferred.", "- Source locators and all original columns are retained.", ""]
        paths["audit.md"].write_text("\n".join(audit), encoding="utf-8")
        result = {
            "schema_version": SCHEMA_VERSION, "case_id": case_id, "status": "success",
            "example_marker": example_marker or None,
            "sources": sources, "uncertainty": uncertainty,
            "change_records": {"path": "changes.jsonl", "record_count": len(changes)},
            "review_queue": {"path": "review_queue.csv", "record_count": len(review)},
            "artifacts": {name: {"path": name, "record_count": counts[name]} for name in sorted(paths)},
            "summary": {"input_rows": len(records), "cleaned_rows": len(cleaned), "statistical_rows": len(statistical_rows), "decision_counts": dict(sorted(category_counts.items())), "clusters": len(set(cluster_for.values()))},
            "identity_contract": contract, "condition_fields": condition_fields,
            "unresolved_required_fields": [],
        }
        preserved_contract_fields = {"case_id", "status", "sources", "uncertainty", "change_records", "review_queue", "artifacts", "summary", "unresolved_required_fields"}
        for name, spec in contract_entries(meta):
            if name in preserved_contract_fields:
                continue
            normalized = re.sub(r"[^a-z0-9]", "", name.casefold())
            if normalized in {"cleaned", "cleaneddata", "cleanedrecords", "records", "rows", "data"}:
                value, known = cleaned, True
            elif normalized in {"statisticalview", "statistics", "stats"}:
                value, known = cleaned_document["statistical_view"], True
            elif normalized in {"changes", "changelog"}:
                value, known = changes, True
            elif normalized in {"rowcount", "cleanedrowcount"}:
                value, known = len(cleaned), True
            elif normalized in {"reviewcount"}:
                value, known = len(review), True
            else:
                value, known = contract_result_value(name, spec, counts)
            result[name] = value
            if not known:
                result["unresolved_required_fields"].append(name)
                uncertainty.append({"code": "UNKNOWN_REQUIRED_OUTPUT_FIELD", "field": name, "message": "Required output-contract field is unknown; its result value is null and unresolved."})
        if result["unresolved_required_fields"]:
            result["status"] = "partial"
        write_json(paths["result.json"], result)
        status = "success"
    except Exception as exc:
        exit_code = 2
        status = "input_error"
        uncertainty.append({"code": "INVALID_CASE", "message": str(exc)})
        # Honest, schema-complete partial artifacts on invalid input. Overwrite every
        # managed artifact so a previous successful run cannot masquerade as this one.
        write_csv(paths["cleaned.csv"], [], ["_observation_node_id", "_disposition", "_cluster_id", "_statistical_include"])
        write_json(paths["cleaned.json"], {"schema_version": SCHEMA_VERSION, "case_id": case_id, "rows": [], "statistical_view": {"row_count": 0, "rows": [], "excluded_observation_node_ids": []}})
        for name in ("observation_graph.jsonl", "duplicate_decisions.jsonl", "changes.jsonl"):
            write_jsonl(paths[name], [])
        write_csv(paths["review_queue.csv"], [], ["review_id", "decision_id", "category", "status"])
        paths["audit.md"].write_text("# Invalid observation case\n\n" + str(exc) + "\n", encoding="utf-8")
        result = {"schema_version": SCHEMA_VERSION, "case_id": case_id, "status": status, "error": str(exc), "sources": sources, "uncertainty": uncertainty, "change_records": {"path": "changes.jsonl", "record_count": 0}, "review_queue": {"path": "review_queue.csv", "record_count": 0}, "artifacts": {name: {"path": name} for name in sorted(paths)}, "unresolved_required_fields": []}
        try:
            case_path = resolve_optional(input_dir, args.case, ("case.json",)) if input_dir.is_dir() else None
            task_path = resolve_optional(input_dir, args.task, ("task.md", "task.json", "task.jsonl")) if input_dir.is_dir() else None
            partial_meta = {}
            if case_path:
                partial_meta = merge_meta(load_metadata(case_path), {})
            if task_path:
                partial_meta = merge_meta(partial_meta, load_metadata(task_path))
            for name, spec in contract_entries(partial_meta):
                if name in {"case_id", "status", "sources", "uncertainty", "change_records", "review_queue", "artifacts", "unresolved_required_fields"}:
                    continue
                value, known = contract_result_value(name, spec, {})
                result[name] = value if known else None
                if not known:
                    result["unresolved_required_fields"].append(name)
        except Exception:
            pass
        write_json(paths["result.json"], result)
    return exit_code


def main(argv=None):
    parser = argparse.ArgumentParser(description="Build an observation identity graph and conservatively adjudicate duplicates.")
    parser.add_argument("--input", default="/input", help="Input directory containing case/task and materials")
    parser.add_argument("--work", default="/app/work", help="Work directory (created; no nondeterministic state)")
    parser.add_argument("--output", default="/app/output", help="Output directory")
    parser.add_argument("--case", default=None, help="Case JSON path, absolute or relative to --input")
    parser.add_argument("--task", default=None, help="Task JSON path, absolute or relative to --input")
    args = parser.parse_args(argv)
    return run(args)


if __name__ == "__main__":
    sys.exit(main())
