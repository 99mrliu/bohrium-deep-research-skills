#!/usr/bin/env python3
"""Audit explicitly described CSV train/test data without modifying inputs.

Inputs: --manifest JSON, --case JSON, --task Markdown, --output-dir directory.
Outputs: audit.json, result.json (partial draft), report.md, summary.txt.
Only the Python standard library is required.
"""

import argparse
import csv
import hashlib
import json
import math
import re
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

from output_contract import parse_output_contract


DETAIL_LIMIT = 100
HASH_RE = re.compile(r"^[0-9a-f]{64}$")
INTEGER_RE = re.compile(r"^[+-]?\d+$")


class AuditError(Exception):
    """A user-facing input or audit configuration error."""


def load_json(path_string, label):
    path = Path(path_string).expanduser().resolve()
    try:
        text = path.read_text(encoding="utf-8")
        value = json.loads(text)
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise AuditError(f"Cannot read {label} {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise AuditError(f"{label} must contain a JSON object: {path}")
    return value, path


def sha256_file(path):
    digest = hashlib.sha256()
    try:
        with path.open("rb") as handle:
            for block in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(block)
    except OSError as exc:
        raise AuditError(f"Cannot hash {path}: {exc}") from exc
    return digest.hexdigest()


def require_nonempty_string(value, location):
    if not isinstance(value, str) or not value.strip():
        raise AuditError(f"{location} must be a non-empty string")


def require_integer(value, location, minimum=0):
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        raise AuditError(f"{location} must be an integer >= {minimum}")


def validate_file_id_list(value, location, known_ids):
    if not isinstance(value, list) or not value:
        raise AuditError(f"{location} must be a non-empty array")
    if len(set(value)) != len(value):
        raise AuditError(f"{location} contains duplicate file IDs")
    for file_id in value:
        require_nonempty_string(file_id, f"{location} item")
        if file_id not in known_ids:
            raise AuditError(f"{location} references unknown file ID {file_id!r}")


def validate_manifest(manifest):
    required = {"schema_version", "dataset", "files", "target", "features", "split"}
    missing = sorted(required - set(manifest))
    if missing:
        raise AuditError(f"Manifest missing required keys: {', '.join(missing)}")
    if manifest["schema_version"] != "1.0":
        raise AuditError("Manifest schema_version must be '1.0'")
    dataset = manifest["dataset"]
    if not isinstance(dataset, dict):
        raise AuditError("Manifest dataset must be an object")
    for key in ("name", "version"):
        require_nonempty_string(dataset.get(key), f"dataset.{key}")
    source = dataset.get("source")
    if not isinstance(source, dict) or source.get("kind") not in {
        "synthetic", "author_repository", "publisher", "organization_fixture", "other", "unknown"
    }:
        raise AuditError("dataset.source.kind must be a supported declared source kind")

    files = manifest["files"]
    if not isinstance(files, list) or len(files) < 2:
        raise AuditError("Manifest files must contain at least two entries")
    by_id = {}
    for index, spec in enumerate(files):
        location = f"files[{index}]"
        if not isinstance(spec, dict):
            raise AuditError(f"{location} must be an object")
        for key in ("id", "path", "role", "sha256", "format"):
            if key not in spec:
                raise AuditError(f"{location} missing {key}")
        file_id = spec["id"]
        require_nonempty_string(file_id, f"{location}.id")
        if file_id in by_id:
            raise AuditError(f"Duplicate file ID {file_id!r}")
        require_nonempty_string(spec["path"], f"{location}.path")
        if spec["role"] not in {"train", "test", "validation", "unlabeled", "other"}:
            raise AuditError(f"{location}.role is not supported")
        if spec["format"] != "csv":
            raise AuditError(f"{location}.format must be 'csv'")
        if not isinstance(spec["sha256"], str) or not HASH_RE.fullmatch(spec["sha256"]):
            raise AuditError(f"{location}.sha256 must be 64 lowercase hexadecimal characters")
        if len(spec.get("delimiter", ",")) != 1:
            raise AuditError(f"{location}.delimiter must be one character")
        missing_values = spec.get("missing_values", [""])
        if not isinstance(missing_values, list) or not all(isinstance(v, str) for v in missing_values):
            raise AuditError(f"{location}.missing_values must be an array of strings")
        if len(set(missing_values)) != len(missing_values):
            raise AuditError(f"{location}.missing_values contains duplicates")
        by_id[file_id] = spec

    target = manifest["target"]
    if not isinstance(target, dict):
        raise AuditError("target must be an object")
    target_name = target.get("name")
    require_nonempty_string(target_name, "target.name")
    features = manifest["features"]
    if not isinstance(features, dict):
        raise AuditError("features must be an object")
    feature_names = features.get("names")
    if not isinstance(feature_names, list) or not feature_names:
        raise AuditError("features.names must be a non-empty array")
    if len(set(feature_names)) != len(feature_names):
        raise AuditError("features.names contains duplicates")
    for name in feature_names:
        require_nonempty_string(name, "features.names item")
    if target_name in feature_names:
        raise AuditError("target.name must not appear in features.names")

    split = manifest["split"]
    if not isinstance(split, dict):
        raise AuditError("split must be an object")
    validate_file_id_list(split.get("train_file_ids"), "split.train_file_ids", by_id)
    validate_file_id_list(split.get("test_file_ids"), "split.test_file_ids", by_id)
    if set(split["train_file_ids"]) & set(split["test_file_ids"]):
        raise AuditError("The same file ID cannot be both train and test")

    claims = manifest.get("paper_claims", [])
    if not isinstance(claims, list):
        raise AuditError("paper_claims must be an array")
    claim_ids = set()
    for index, claim in enumerate(claims):
        location = f"paper_claims[{index}]"
        if not isinstance(claim, dict):
            raise AuditError(f"{location} must be an object")
        for key in ("claim_id", "kind", "expected"):
            if key not in claim:
                raise AuditError(f"{location} missing {key}")
        require_nonempty_string(claim["claim_id"], f"{location}.claim_id")
        if claim["claim_id"] in claim_ids:
            raise AuditError(f"Duplicate claim ID {claim['claim_id']!r}")
        claim_ids.add(claim["claim_id"])
        if claim["kind"] not in {"n_rows", "n_features", "split"}:
            raise AuditError(f"{location}.kind is not supported")
    return by_id


def observed_type(value):
    lowered = value.lower()
    if lowered in {"true", "false"}:
        return "boolean"
    if INTEGER_RE.fullmatch(value):
        return "integer"
    try:
        number = float(value)
        if math.isfinite(number):
            return "number"
    except ValueError:
        pass
    return "string"


def infer_column_type(values):
    types = {observed_type(value) for value in values}
    if not types:
        return "empty"
    if types == {"integer"}:
        return "integer"
    if types <= {"integer", "number"}:
        return "number"
    if len(types) == 1:
        return next(iter(types))
    return "mixed"


def target_distribution(rows, target_name, missing_values):
    counts = Counter()
    for row in rows:
        value = row[target_name]
        key = ("missing", None) if value in missing_values else ("value", value)
        counts[key] += 1
    output = []
    for (kind, value), count in sorted(counts.items(), key=lambda item: (item[0][0], str(item[0][1]))):
        output.append({"kind": kind, "value": value, "count": count})
    return output


def within_file_duplicates(rows, columns, file_id, row_numbers):
    groups = defaultdict(list)
    for row, row_number in zip(rows, row_numbers):
        key = tuple(row[column] for column in columns)
        groups[key].append(row_number)
    repeated = [(key, numbers) for key, numbers in groups.items() if len(numbers) > 1]
    repeated.sort(key=lambda item: (str(item[0]), item[1]))
    details = [
        {
            "file_id": file_id,
            "row_numbers": numbers,
            "count": len(numbers),
            "row": dict(zip(columns, key)),
        }
        for key, numbers in repeated[:DETAIL_LIMIT]
    ]
    return {
        "duplicate_group_count": len(repeated),
        "duplicate_excess_rows": sum(len(numbers) - 1 for _, numbers in repeated),
        "details_truncated": len(repeated) > DETAIL_LIMIT,
        "details": details,
    }


def read_table(spec, manifest_dir, target_name, feature_names):
    file_id = spec["id"]
    supplied_path = Path(spec["path"]).expanduser()
    path = supplied_path if supplied_path.is_absolute() else manifest_dir / supplied_path
    path = path.resolve()
    if not path.is_file():
        raise AuditError(f"Data file for {file_id!r} is not a regular file: {path}")
    actual_hash = sha256_file(path)
    encoding = spec.get("encoding", "utf-8")
    delimiter = spec.get("delimiter", ",")
    missing_values = set(spec.get("missing_values", [""]))
    rows = []
    row_numbers = []
    try:
        with path.open("r", encoding=encoding, newline="") as handle:
            reader = csv.reader(handle, delimiter=delimiter)
            try:
                columns = next(reader)
            except StopIteration as exc:
                raise AuditError(f"Data file is empty: {path}") from exc
            if not columns or any(column == "" for column in columns):
                raise AuditError(f"Data file has an empty column name: {path}")
            if len(set(columns)) != len(columns):
                raise AuditError(f"Data file has duplicate column names: {path}")
            required_columns = set(feature_names) | {target_name}
            absent = sorted(required_columns - set(columns))
            if absent:
                raise AuditError(f"Data file {path} lacks required columns: {', '.join(absent)}")
            for values in reader:
                if values == []:
                    continue
                if len(values) != len(columns):
                    raise AuditError(
                        f"Ragged CSV row in {path} at physical line {reader.line_num}: "
                        f"expected {len(columns)} cells, got {len(values)}"
                    )
                rows.append(dict(zip(columns, values)))
                row_numbers.append(reader.line_num)
    except (OSError, UnicodeError, csv.Error) as exc:
        raise AuditError(f"Cannot parse CSV {path}: {exc}") from exc

    missing_by_column = {}
    types = {}
    total_missing = 0
    for column in columns:
        values = [row[column] for row in rows]
        missing_count = sum(value in missing_values for value in values)
        total_missing += missing_count
        missing_by_column[column] = {
            "count": missing_count,
            "fraction": (missing_count / len(rows)) if rows else 0.0,
        }
        types[column] = infer_column_type([value for value in values if value not in missing_values])

    hash_match = actual_hash == spec["sha256"]
    audit = {
        "id": file_id,
        "role": spec["role"],
        "path": str(path),
        "declared_sha256": spec["sha256"],
        "actual_sha256": actual_hash,
        "sha256_match": hash_match,
        "encoding": encoding,
        "delimiter": delimiter,
        "missing_values": sorted(missing_values),
        "n_rows": len(rows),
        "n_columns": len(columns),
        "column_names": columns,
        "observed_types": types,
        "missing_by_column": missing_by_column,
        "total_missing_cells": total_missing,
        "within_file_full_row_duplicates": within_file_duplicates(
            rows, columns, file_id, row_numbers
        ),
        "target_distribution": target_distribution(rows, target_name, missing_values),
    }
    internal = {
        "id": file_id,
        "path": path,
        "columns": columns,
        "rows": rows,
        "row_numbers": row_numbers,
        "missing_values": missing_values,
    }
    return audit, internal


def make_occurrence_map(internals, key_function, target_name):
    output = defaultdict(list)
    for internal in internals:
        for row, row_number in zip(internal["rows"], internal["row_numbers"]):
            output[key_function(row)].append({
                "file_id": internal["id"],
                "row_number": row_number,
                "target": row[target_name],
                "row": row,
            })
    return output


def public_occurrences(occurrences):
    return [
        {"file_id": item["file_id"], "row_number": item["row_number"], "target": item["target"]}
        for item in occurrences[:DETAIL_LIMIT]
    ]


def audit_split(internals_by_id, split, feature_names, target_name):
    train_ids = split["train_file_ids"]
    test_ids = split["test_file_ids"]
    train = [internals_by_id[file_id] for file_id in train_ids]
    test = [internals_by_id[file_id] for file_id in test_ids]
    train_rows = sum(len(item["rows"]) for item in train)
    test_rows = sum(len(item["rows"]) for item in test)

    train_column_sets = {file_id: set(internals_by_id[file_id]["columns"]) for file_id in train_ids}
    test_column_sets = {file_id: set(internals_by_id[file_id]["columns"]) for file_id in test_ids}
    all_sets = list(train_column_sets.values()) + list(test_column_sets.values())
    full_comparable = all(column_set == all_sets[0] for column_set in all_sets[1:])
    full_group_count = None
    full_details = []
    if full_comparable:
        columns = sorted(all_sets[0])
        full_key = lambda row: tuple((column, row[column]) for column in columns)
        train_full = make_occurrence_map(train, full_key, target_name)
        test_full = make_occurrence_map(test, full_key, target_name)
        common_full = sorted(set(train_full) & set(test_full), key=str)
        full_group_count = len(common_full)
        for key in common_full[:DETAIL_LIMIT]:
            full_details.append({
                "row": dict(key),
                "train_occurrences": public_occurrences(train_full[key]),
                "test_occurrences": public_occurrences(test_full[key]),
            })
        full_status = "comparable"
    else:
        full_status = "not_comparable_different_column_sets"

    feature_key = lambda row: tuple(row[column] for column in feature_names)
    train_features = make_occurrence_map(train, feature_key, target_name)
    test_features = make_occurrence_map(test, feature_key, target_name)
    common_features = sorted(set(train_features) & set(test_features), key=str)
    conflicting_count = 0
    feature_details = []
    for key in common_features:
        train_occurrences = train_features[key]
        test_occurrences = test_features[key]
        targets = {item["target"] for item in train_occurrences + test_occurrences}
        conflicting = len(targets) > 1
        if conflicting:
            conflicting_count += 1
        if len(feature_details) < DETAIL_LIMIT:
            full_match = False
            if full_comparable:
                columns = sorted(all_sets[0])
                for left in train_occurrences:
                    for right in test_occurrences:
                        if all(left["row"][column] == right["row"][column] for column in columns):
                            full_match = True
                            break
                    if full_match:
                        break
            feature_details.append({
                "features": dict(zip(feature_names, key)),
                "train_occurrences": public_occurrences(train_occurrences),
                "test_occurrences": public_occurrences(test_occurrences),
                "distinct_targets": sorted(targets),
                "target_conflict": conflicting,
                "has_full_row_match": full_match,
            })

    return {
        "train_file_ids": train_ids,
        "test_file_ids": test_ids,
        "train_rows": train_rows,
        "test_rows": test_rows,
        "feature_names": feature_names,
        "comparison_rule": "Exact CSV cell strings; no normalization or imputation.",
        "full_row_cross_split": {
            "status": full_status,
            "overlap_group_count": full_group_count,
            "details_truncated": full_group_count is not None and full_group_count > DETAIL_LIMIT,
            "details": full_details,
        },
        "feature_only_cross_split": {
            "status": "comparable",
            "overlap_group_count": len(common_features),
            "target_conflicting_group_count": conflicting_count,
            "details_truncated": len(common_features) > DETAIL_LIMIT,
            "details": feature_details,
        },
        "interpretation_guardrail": (
            "Exact or feature-only overlap and target conflicts are observations, not automatic proof "
            "of synthetic data, split leakage, or label leakage."
        ),
    }


def claim_evidence_missing(claim):
    missing = []
    if "page" not in claim or claim["page"] is None or claim["page"] == "":
        missing.append("page")
    if not isinstance(claim.get("quote"), str) or not claim.get("quote", "").strip():
        missing.append("quote")
    if not isinstance(claim.get("locator"), dict) or not claim.get("locator"):
        missing.append("locator")
    return missing


def check_claim(claim, internals_by_id, split, feature_names):
    output = {
        "claim_id": claim["claim_id"],
        "kind": claim["kind"],
        "expected": claim["expected"],
        "page": claim.get("page"),
        "quote": claim.get("quote"),
        "locator": claim.get("locator"),
        "document_sha256": claim.get("document_sha256"),
        "evidence_note": claim.get("evidence_note"),
        "pdf_quote_independently_verified": False,
    }
    missing_evidence = claim_evidence_missing(claim)
    if missing_evidence:
        output.update({
            "status": "unverifiable",
            "observed": None,
            "match": None,
            "missing_evidence": missing_evidence,
        })
        return output

    locator = claim["locator"]
    kind = claim["kind"]
    if kind == "n_rows":
        file_ids = locator.get("file_ids")
        validate_file_id_list(file_ids, f"claim {claim['claim_id']} locator.file_ids", internals_by_id)
        observed = sum(len(internals_by_id[file_id]["rows"]) for file_id in file_ids)
        require_integer(claim["expected"], f"claim {claim['claim_id']} expected")
    elif kind == "n_features":
        file_id = locator.get("file_id")
        require_nonempty_string(file_id, f"claim {claim['claim_id']} locator.file_id")
        if file_id not in internals_by_id:
            raise AuditError(f"claim {claim['claim_id']} references unknown file ID {file_id!r}")
        names = locator.get("feature_names", feature_names)
        if not isinstance(names, list) or len(set(names)) != len(names):
            raise AuditError(f"claim {claim['claim_id']} feature_names must be a unique array")
        for name in names:
            require_nonempty_string(name, f"claim {claim['claim_id']} feature_names item")
            if name not in internals_by_id[file_id]["columns"]:
                raise AuditError(f"claim {claim['claim_id']} feature {name!r} is absent from {file_id}")
        observed = len(names)
        require_integer(claim["expected"], f"claim {claim['claim_id']} expected")
    else:
        expected = claim["expected"]
        if not isinstance(expected, dict) or set(expected) != {"train", "test"}:
            raise AuditError(f"claim {claim['claim_id']} split expected must have train and test")
        require_integer(expected["train"], f"claim {claim['claim_id']} expected.train")
        require_integer(expected["test"], f"claim {claim['claim_id']} expected.test")
        train_ids = locator.get("train_file_ids", split["train_file_ids"])
        test_ids = locator.get("test_file_ids", split["test_file_ids"])
        validate_file_id_list(train_ids, f"claim {claim['claim_id']} locator.train_file_ids", internals_by_id)
        validate_file_id_list(test_ids, f"claim {claim['claim_id']} locator.test_file_ids", internals_by_id)
        observed = {
            "train": sum(len(internals_by_id[file_id]["rows"]) for file_id in train_ids),
            "test": sum(len(internals_by_id[file_id]["rows"]) for file_id in test_ids),
        }

    matches = observed == claim["expected"]
    output.update({
        "status": "verified" if matches else "mismatch",
        "observed": observed,
        "match": matches,
        "missing_evidence": [],
        "scope": "Numerical consistency only; quote fidelity and data provenance are not proved.",
    })
    return output


def case_output_contract(case):
    try:
        return parse_output_contract(case)
    except ValueError as exc:
        raise AuditError(str(exc)) from exc


def case_required_fields(case):
    """Return only the required subset; build_result receives all declared fields."""
    return case_output_contract(case)["required_fields"]


def build_result(case_id, contract_fields, audit, sources, manifest_path):
    known = {
        "data_identity": {
            "dataset": audit["dataset"],
            "manifest_path": str(manifest_path),
            "manifest_sha256": audit["manifest_sha256"],
            "files": [
                {
                    "id": item["id"],
                    "path": item["path"],
                    "role": item["role"],
                    "declared_sha256": item["declared_sha256"],
                    "actual_sha256": item["actual_sha256"],
                    "sha256_match": item["sha256_match"],
                }
                for item in audit["files"]
            ],
            "source_inference": "Not attempted; source is only the manifest declaration.",
        },
        "data_quality": audit["files"],
        "split_audit": audit["split_audit"],
        "paper_claim_checks": audit["paper_claim_checks"],
        "method_comparison": {
            "status": "not_run",
            "candidate_runs": [],
            "reason": "The audit tool does not execute either candidate numerical method.",
        },
        "limitations": list(audit["limitations"]) + [
            "Both candidate methods, environment capture, predeclared tolerances, comparison, and attribution remain required for a formal task."
        ],
    }
    result = {
        "case_id": case_id,
        "status": "partial",
        "sources": sources,
        "uncertainty": [
            "This result is an audit-only partial draft; no candidate numerical method was run.",
            "Statistical overlap or distribution findings do not establish synthetic origin or label leakage.",
            "Claim checks do not independently verify quotes against a PDF or establish dataset provenance.",
        ],
        "change_records": [],
    }
    for field in contract_fields:
        # Standard result keys may themselves be declared by the contract. Keep
        # the values initialized above instead of treating them as collisions or
        # overwriting them with an unavailable placeholder.
        if field in result:
            continue
        if field in known:
            result[field] = known[field]
        else:
            result[field] = {
                "status": "unavailable",
                "reason": "The dataset audit does not produce this task-specific contract field.",
                "completion_required": True,
            }
            result["uncertainty"].append(
                f"Contract field {field!r} is unavailable in this audit-only partial draft; "
                "task-specific evidence is required."
            )
    if audit["dataset"]["source"]["kind"] == "synthetic":
        result["uncertainty"].append(
            "The manifest declares synthetic data; this fixture is not author code, a physical experiment, or full PMLB."
        )
    return result


def compact_json(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def make_report(audit, result):
    lines = [
        "# Dataset provenance audit",
        "",
        f"- case_id: `{audit['case_id']}`",
        f"- audit status: **{audit['status']}**",
        f"- result status: **{result['status']}** (candidate methods were not run)",
        f"- declared dataset: **{audit['dataset']['name']}**, version `{audit['dataset']['version']}`",
        f"- declared source kind: `{audit['dataset']['source']['kind']}` (not independently inferred)",
        "",
        "## File identity and quality",
        "",
        "| id | role | rows | columns | SHA256 match | missing cells | internal duplicate groups |",
        "|---|---|---:|---:|---|---:|---:|",
    ]
    for item in audit["files"]:
        lines.append(
            f"| {item['id']} | {item['role']} | {item['n_rows']} | {item['n_columns']} | "
            f"{item['sha256_match']} | {item['total_missing_cells']} | "
            f"{item['within_file_full_row_duplicates']['duplicate_group_count']} |"
        )
    lines.extend(["", "Actual SHA256 values:"])
    for item in audit["files"]:
        lines.append(f"- `{item['id']}`: `{item['actual_sha256']}`")
        lines.append(f"  - observed types: `{compact_json(item['observed_types'])}`")
        lines.append(f"  - target distribution: `{compact_json(item['target_distribution'])}`")

    split = audit["split_audit"]
    full = split["full_row_cross_split"]
    feature = split["feature_only_cross_split"]
    lines.extend([
        "",
        "## Train/test comparability",
        "",
        f"- train rows: **{split['train_rows']}**; test rows: **{split['test_rows']}**",
        f"- full-row cross-split groups: **{full['overlap_group_count']}** ({full['status']})",
        f"- feature-only cross-split groups: **{feature['overlap_group_count']}**",
        f"- feature-only groups with conflicting targets: **{feature['target_conflicting_group_count']}**",
        "- features: " + ", ".join(f"`{name}`" for name in split["feature_names"]),
        "",
        "These are exact-cell observations. They do not by themselves prove synthetic origin, split leakage, or label leakage.",
        "",
        "Feature-only overlap details (up to 100):",
        "",
    ])
    if not feature["details"]:
        lines.append("None.")
    for detail in feature["details"]:
        lines.append(
            f"- `{compact_json(detail['features'])}`: targets={compact_json(detail['distinct_targets'])}, "
            f"target_conflict={detail['target_conflict']}, full_row_match={detail['has_full_row_match']}"
        )

    lines.extend([
        "",
        "## Recorded paper-claim consistency checks",
        "",
        "`verified` means only that the supplied expected value matches the computed data value. The script does not verify PDF quote fidelity or provenance.",
        "",
        "| claim | kind | status | page | expected | observed | quote |",
        "|---|---|---|---|---|---|---|",
    ])
    for claim in audit["paper_claim_checks"]:
        quote = (claim.get("quote") or "").replace("|", "\\|")
        lines.append(
            f"| {claim['claim_id']} | {claim['kind']} | {claim['status']} | {claim.get('page')} | "
            f"`{compact_json(claim['expected'])}` | `{compact_json(claim.get('observed'))}` | {quote} |"
        )
    lines.extend([
        "",
        "## Limitations and required continuation",
        "",
    ])
    # limitations is optional unless the actual contract declares it. Fall back
    # to the audit's own limitations, and preserve structured unavailable values
    # as JSON instead of assuming a list or indexing a missing key.
    limitations = result.get("limitations")
    if limitations is None:
        limitations = audit["limitations"]
    elif not isinstance(limitations, list):
        limitations = [limitations]
    lines.extend(f"- {item if isinstance(item, str) else compact_json(item)}" for item in limitations)
    lines.extend([
        "",
        "A formal case still requires actually running both candidates, recording environments and parameters, declaring tolerances before comparison, comparing outputs, and attributing differences. Missing original data or repositories must remain an explicit scope limitation.",
        "",
    ])
    return "\n".join(lines)


def make_summary(audit, result):
    split = audit["split_audit"]
    claims = audit["claim_summary"]
    full_count = split["full_row_cross_split"]["overlap_group_count"]
    lines = [
        f"case_id={audit['case_id']}",
        f"status={result['status']}",
        f"train_rows={split['train_rows']}",
        f"test_rows={split['test_rows']}",
        f"full_row_overlap_groups={full_count}",
        f"feature_only_overlap_groups={split['feature_only_cross_split']['overlap_group_count']}",
        "feature_only_conflicting_target_groups="
        f"{split['feature_only_cross_split']['target_conflicting_group_count']}",
        f"claims_verified={claims['verified']}",
        f"claims_mismatch={claims['mismatch']}",
        f"claims_unverifiable={claims['unverifiable']}",
    ]
    return "\n".join(lines) + "\n"


def write_json(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def run(args):
    case, case_path = load_json(args.case, "case")
    case_id = case.get("case_id")
    require_nonempty_string(case_id, "case.case_id")
    contract = case_output_contract(case)
    manifest, manifest_path = load_json(args.manifest, "manifest")
    by_id = validate_manifest(manifest)
    task_path = Path(args.task).expanduser().resolve()
    try:
        task_path.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        raise AuditError(f"Cannot read task {task_path}: {exc}") from exc

    file_audits = []
    internals_by_id = {}
    for spec in by_id.values():
        file_audit, internal = read_table(
            spec, manifest_path.parent, manifest["target"]["name"], manifest["features"]["names"]
        )
        file_audits.append(file_audit)
        internals_by_id[spec["id"]] = internal

    split_audit = audit_split(
        internals_by_id, manifest["split"], manifest["features"]["names"], manifest["target"]["name"]
    )
    claim_checks = [
        check_claim(claim, internals_by_id, manifest["split"], manifest["features"]["names"])
        for claim in manifest.get("paper_claims", [])
    ]
    claim_summary = {
        status: sum(claim["status"] == status for claim in claim_checks)
        for status in ("verified", "mismatch", "unverifiable")
    }
    missing_original_note = (
        "If original data or repositories are absent, conclusions are limited to the supplied files; "
        "absence must remain explicit in the formal result."
    )
    audit = {
        "audit_schema_version": "1.0",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "case_id": case_id,
        "status": "completed",
        "manifest_path": str(manifest_path),
        "manifest_sha256": sha256_file(manifest_path),
        "case_path": str(case_path),
        "task_path": str(task_path),
        "dataset": manifest["dataset"],
        "files": file_audits,
        "split_audit": split_audit,
        "paper_claim_checks": claim_checks,
        "claim_summary": claim_summary,
        "provenance_inference": {
            "attempted": False,
            "reason": "File statistics and hashes do not independently establish dataset origin.",
        },
        "limitations": [
            "Audit covers only the explicitly listed files and exact-cell definitions in the manifest.",
            "PDF quote fidelity requires direct reading of the real PDF; this script does not perform that reading.",
            "Statistical anomalies cannot automatically prove synthetic data, split leakage, or label leakage.",
            missing_original_note,
        ],
    }
    hash_mismatches = [item["id"] for item in file_audits if not item["sha256_match"]]
    if hash_mismatches:
        audit["status"] = "failed_hash_verification"
        audit["limitations"].append("SHA256 mismatch for file IDs: " + ", ".join(hash_mismatches))

    sources = [
        {"type": "case", "path": str(case_path), "sha256": sha256_file(case_path)},
        {"type": "task", "path": str(task_path), "sha256": sha256_file(task_path)},
        {"type": "manifest", "path": str(manifest_path), "sha256": audit["manifest_sha256"]},
    ]
    sources.extend(
        {"type": "dataset_file", "id": item["id"], "path": item["path"], "sha256": item["actual_sha256"]}
        for item in file_audits
    )
    result = build_result(case_id, contract["fields"], audit, sources, manifest_path)
    report = make_report(audit, result)
    summary = make_summary(audit, result)

    output_dir = Path(args.output_dir).expanduser().resolve()
    try:
        output_dir.mkdir(parents=True, exist_ok=True)
        write_json(output_dir / "audit.json", audit)
        write_json(output_dir / "result.json", result)
        (output_dir / "report.md").write_text(report, encoding="utf-8")
        (output_dir / "summary.txt").write_text(summary, encoding="utf-8")
    except OSError as exc:
        raise AuditError(f"Cannot write outputs to {output_dir}: {exc}") from exc

    print(f"Wrote audit outputs to {output_dir}")
    print(f"Audit status: {audit['status']}; result status: {result['status']}")
    if hash_mismatches:
        print("SHA256 mismatch: " + ", ".join(hash_mismatches), file=sys.stderr)
        return 4
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", required=True, help="Input dataset manifest JSON")
    parser.add_argument("--case", required=True, help="Input case JSON with case_id and output_contract")
    parser.add_argument("--task", required=True, help="Input task Markdown/text")
    parser.add_argument("--output-dir", required=True, help="Directory for audit/result/report/summary outputs")
    args = parser.parse_args(argv)
    try:
        return run(args)
    except AuditError as exc:
        print(f"audit_dataset.py: error: {exc}", file=sys.stderr)
        return 2
    except Exception as exc:  # Ensure unexpected failures are nonzero and visible.
        print(f"audit_dataset.py: unexpected {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
