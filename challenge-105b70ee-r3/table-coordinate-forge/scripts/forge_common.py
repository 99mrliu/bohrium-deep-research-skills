#!/usr/bin/env python3
"""Shared stdlib-only I/O and output-contract helpers.

This module deliberately has no scientific-value inference routines.  Numeric
text is treated as text until a reviewer binds it to a reconstructed cell.
"""
from __future__ import annotations

import copy
import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path

FIELD_KEYS = (
    "field_id", "status", "scalar", "units", "statistic",
    "experimental_condition", "condition", "comparator", "paragraph_id",
    "quote", "evidence", "notes",
)
FIELD_STATUSES = {"reported", "not_reported", "source_conflict", "extraction_failed"}
OVERALL_STATUSES = {"answered", "partial", "insufficient_evidence", "input_error"}
TOP_LEVEL_KEYS = ("case_id", "status", "result", "claims", "uncertainties")


def utc_now():
    return datetime.now(timezone.utc).isoformat()


def load_json(path):
    with Path(path).open("r", encoding="utf-8") as handle:
        return json.load(handle)


def atomic_write_text(path, text):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary_name = tempfile.mkstemp(prefix=path.name + ".", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(text)
        os.replace(temporary_name, path)
    except Exception:
        try:
            os.unlink(temporary_name)
        except OSError:
            pass
        raise


def write_json(path, payload):
    atomic_write_text(path, json.dumps(payload, ensure_ascii=False, indent=2) + "\n")


def blank_field(field_id, reason):
    return {
        "field_id": field_id,
        "status": "extraction_failed",
        "scalar": None,
        "units": None,
        "statistic": None,
        "experimental_condition": None,
        "condition": None,
        "comparator": None,
        "paragraph_id": None,
        "quote": None,
        "evidence": [],
        "notes": reason,
    }


def target_field_ids(target_document):
    """Read the concrete target list without using any expected answer values."""
    if isinstance(target_document, list):
        entries = target_document
    elif isinstance(target_document, dict):
        entries = None
        for key in ("fields", "target_fields", "targets"):
            if key in target_document:
                entries = target_document[key]
                break
        if entries is None:
            raise ValueError("target-fields.json needs fields, target_fields, or targets")
    else:
        raise ValueError("target-fields.json must be an object or an array")
    if not isinstance(entries, list) or not entries:
        raise ValueError("target field list must be a non-empty array")
    ids = []
    for entry in entries:
        if not isinstance(entry, dict):
            raise ValueError("every target field must be an object")
        field_id = entry.get("field_id", entry.get("id"))
        if not isinstance(field_id, str) or not field_id.strip():
            raise ValueError("every target field needs a non-empty field_id")
        if field_id in ids:
            raise ValueError("duplicate target field_id: " + field_id)
        ids.append(field_id)
    return ids


def base_result(case_id, field_ids, contract=None, label=None):
    """Make a complete, honest partial payload suitable for an early write."""
    result = {
        "case_id": case_id,
        "status": "partial",
        "result": {
            "fields": [blank_field(item, "Awaiting PDF geometry and reviewed cell binding.")
                       for item in field_ids],
            "layout": {"usable": False, "table_count": 0, "segment_count": 0},
        },
        "claims": [],
        "uncertainties": [{
            "kind": "workflow_incomplete",
            "message": "Preliminary scaffold: no field has been accepted as reported.",
        }],
        "sources": [],
        "change_records": [{
            "event": "early_partial_written",
            "at": utc_now(),
            "detail": "Result initialized before PDF parsing to preserve a valid partial deliverable.",
        }],
    }
    if label:
        result["result"]["example_label"] = label
    if isinstance(contract, dict):
        # Preserve additional case-specific contract keys, but never confuse their
        # schema descriptions with observed answers.
        for key in contract:
            if key not in result and key not in {"case_id", "status", "result", "claims", "uncertainties"}:
                result[key] = None
    return result


def unfinished_field_ids(payload):
    return [row["field_id"] for row in payload.get("result", {}).get("fields", [])
            if row.get("status") == "extraction_failed"]


def overall_status(fields):
    if not fields:
        return "input_error"
    failed = sum(row["status"] == "extraction_failed" for row in fields)
    reported = sum(row["status"] == "reported" for row in fields)
    resolved = len(fields) - failed
    if failed == 0:
        return "answered"
    if reported == 0 and resolved == 0:
        return "insufficient_evidence"
    return "partial"


def _is_null_or_string(value):
    return value is None or isinstance(value, str)


def validate_result(payload, expected_field_ids=None):
    """Validate before replacing a good deliverable; raise on contract drift."""
    errors = []
    if not isinstance(payload, dict):
        raise ValueError("result.json must be a JSON object")
    for key in TOP_LEVEL_KEYS:
        if key not in payload:
            errors.append("missing top-level key: " + key)
    if payload.get("status") not in OVERALL_STATUSES:
        errors.append("invalid overall status")
    fields = payload.get("result", {}).get("fields")
    if not isinstance(fields, list):
        errors.append("result.fields must be an array")
        fields = []
    seen = set()
    for index, row in enumerate(fields):
        prefix = "fields[%d]" % index
        if not isinstance(row, dict):
            errors.append(prefix + " must be an object")
            continue
        missing = [key for key in FIELD_KEYS if key not in row]
        if missing:
            errors.append(prefix + " missing keys: " + ", ".join(missing))
            continue
        field_id = row["field_id"]
        if not isinstance(field_id, str) or not field_id:
            errors.append(prefix + " invalid field_id")
        elif field_id in seen:
            errors.append("duplicate field_id: " + field_id)
        seen.add(field_id)
        status = row["status"]
        if status not in FIELD_STATUSES:
            errors.append(prefix + " invalid field status")
        for key in ("scalar", "units", "statistic", "experimental_condition",
                    "condition", "comparator", "paragraph_id", "quote", "notes"):
            if not _is_null_or_string(row[key]):
                errors.append(prefix + "." + key + " must be a string or null")
        if row["experimental_condition"] != row["condition"]:
            errors.append(prefix + " condition alias differs from experimental_condition")
        if not isinstance(row["evidence"], list):
            errors.append(prefix + ".evidence must be an array")
        else:
            for evidence_index, evidence in enumerate(row["evidence"]):
                if not isinstance(evidence, dict):
                    errors.append(prefix + " evidence item must be an object")
                    continue
                for key in ("source_id", "page", "paragraph_id", "quote"):
                    if key not in evidence:
                        errors.append(prefix + " evidence missing " + key)
                if not isinstance(evidence.get("source_id"), str):
                    errors.append(prefix + " evidence source_id must be a string")
                if not isinstance(evidence.get("page"), int) or evidence.get("page") < 1:
                    errors.append(prefix + " evidence page must be a positive integer")
                if not isinstance(evidence.get("paragraph_id"), str):
                    errors.append(prefix + " evidence paragraph_id must be a string")
                if not isinstance(evidence.get("quote"), str):
                    errors.append(prefix + " evidence quote must be a string")
        if status == "reported":
            if not isinstance(row["scalar"], str) or row["scalar"] == "":
                errors.append(prefix + " reported scalar must be a non-empty verbatim string")
            if len(row["evidence"]) != 1:
                errors.append(prefix + " reported field needs exactly one primary cell evidence item")
            if not row["quote"] or not row["paragraph_id"]:
                errors.append(prefix + " reported field needs quote and paragraph_id")
            if row["evidence"] and isinstance(row["evidence"][0], dict):
                if row["evidence"][0].get("quote") != row["quote"]:
                    errors.append(prefix + " primary quote differs from evidence quote")
                if row["evidence"][0].get("paragraph_id") != row["paragraph_id"]:
                    errors.append(prefix + " paragraph_id differs from evidence")
        elif status in {"not_reported", "source_conflict", "extraction_failed"}:
            if row["scalar"] is not None:
                errors.append(prefix + " " + status + " scalar must be null")
        if status == "source_conflict" and len(row["evidence"]) < 2:
            errors.append(prefix + " source_conflict needs at least two conflicting evidence items")
        if status in {"not_reported", "extraction_failed"} and row["evidence"]:
            errors.append(prefix + " " + status + " must not attach value evidence")
    if expected_field_ids is not None:
        expected = list(expected_field_ids)
        if len(fields) != len(expected) or seen != set(expected):
            errors.append("field IDs do not exactly match target-fields.json")
        actual_order = [row.get("field_id") for row in fields if isinstance(row, dict)]
        if actual_order != expected:
            errors.append("result.fields must preserve target field order")
    statuses = [row.get("status") for row in fields if isinstance(row, dict)]
    if fields and not errors:
        computed = overall_status(fields)
        if payload.get("status") != computed:
            # An early, fully unfinished scaffold may honestly remain partial;
            # apply_bindings upgrades an exhausted all-failed result to
            # insufficient_evidence before its final validated write.
            if not (payload.get("status") == "partial" and computed == "insufficient_evidence"):
                errors.append("overall status should be %s" % computed)
    if errors:
        raise ValueError("Invalid result contract:\n- " + "\n- ".join(errors))
    return copy.deepcopy(payload)
