#!/usr/bin/env python3
"""Apply explicit reviewed cell bindings; never auto-promote coordinate matches."""
from __future__ import annotations

import copy

from forge_common import (FIELD_KEYS, blank_field, overall_status, utc_now,
                          validate_result)

REPORTED_REQUIRED = (
    "field_id", "source_id", "cell_id", "scalar", "units", "statistic",
    "experimental_condition", "comparator", "row_header_cell_ids",
    "column_header_cell_ids", "expected_row_header_text",
    "expected_column_header_text", "condition_cell_ids",
    "expected_condition_text", "notes",
)


def table_indexes(table_document):
    cells = {}
    segments = {}
    for table in table_document.get("tables", []):
        for segment in table.get("segments", []):
            segments[segment["segment_id"]] = (table, segment)
            for row in segment["rows"]:
                for cell in row["cells"]:
                    if cell["cell_id"] in cells:
                        raise ValueError("Duplicate reconstructed cell ID: " + cell["cell_id"])
                    cells[cell["cell_id"]] = (table, segment, row, cell)
    return cells, segments


def _binding_error(field_id, message):
    raise ValueError("Binding for %s: %s" % (field_id, message))


def _cell_for_binding(binding, cells):
    field_id = binding.get("field_id", "<missing>")
    for key in REPORTED_REQUIRED:
        if key not in binding:
            _binding_error(field_id, "missing explicit key " + key)
    cell_id = binding["cell_id"]
    if cell_id not in cells:
        _binding_error(field_id, "cell_id does not exist: " + str(cell_id))
    table, segment, row, cell = cells[cell_id]
    if cell["source_id"] != binding["source_id"]:
        _binding_error(field_id, "source_id differs from reconstructed cell")
    if not cell["text"]:
        _binding_error(field_id, "blank or spanning-placeholder cell cannot be a scalar")
    if not isinstance(binding["scalar"], str) or not binding["scalar"]:
        _binding_error(field_id, "scalar must be a non-empty verbatim string")
    if binding["scalar"] not in cell["text"]:
        _binding_error(field_id, "scalar is not a verbatim substring of the value cell")
    if not isinstance(binding["notes"], str) or not binding["notes"].strip():
        _binding_error(field_id, "review notes are required")
    for key in ("units", "statistic", "experimental_condition", "comparator"):
        if binding[key] is not None and not isinstance(binding[key], str):
            _binding_error(field_id, key + " must be a string or null")
    return table, segment, row, cell


def _verify_headers(binding, table, segment, row, value_cell, cells):
    field_id = binding["field_id"]
    list_keys = ("row_header_cell_ids", "column_header_cell_ids",
                 "expected_row_header_text", "expected_column_header_text")
    if any(not isinstance(binding[key], list) for key in list_keys):
        _binding_error(field_id, "header ID and expected header text values must be arrays")
    if len(binding["row_header_cell_ids"]) != len(binding["expected_row_header_text"]):
        _binding_error(field_id, "row header ID/text counts differ")
    if len(binding["column_header_cell_ids"]) != len(binding["expected_column_header_text"]):
        _binding_error(field_id, "column header ID/text counts differ")
    if not binding["column_header_cell_ids"]:
        _binding_error(field_id, "at least one explicitly reviewed column header is required")

    def checked_cell(cell_id):
        if cell_id not in cells:
            _binding_error(field_id, "header cell does not exist: " + str(cell_id))
        other_table, other_segment, other_row, cell = cells[cell_id]
        if cell["source_id"] != binding["source_id"] or not cell["text"]:
            _binding_error(field_id, "header source differs or header text is blank")
        return other_segment, other_row, cell

    for cell_id, expected in zip(binding["row_header_cell_ids"], binding["expected_row_header_text"]):
        _, header_row, cell = checked_cell(cell_id)
        if header_row["row_id"] != row["row_id"] or cell["cell_id"] == value_cell["cell_id"]:
            _binding_error(field_id, "row header must be a different cell in the value row")
        if cell["text"] != expected:
            _binding_error(field_id, "row header text differs: %s != %s" % (cell["text"], expected))
    for cell_id, expected in zip(binding["column_header_cell_ids"], binding["expected_column_header_text"]):
        header_segment, _, cell = checked_cell(cell_id)
        allowed = set()
        for table_id, candidate in segments_for_source(cells, binding["source_id"]):
            if table_id == table["table_id"] and candidate["segment_id"] == header_segment["segment_id"]:
                for ids in candidate["header_cell_ids_by_column"].values():
                    allowed.update(ids)
        if cell_id not in allowed:
            _binding_error(field_id, "column header is not in a reconstructed header path")
        if not (cell["column_start"] <= value_cell["column_end"] and
                value_cell["column_start"] <= cell["column_end"]):
            _binding_error(field_id, "column header and value do not occupy the same column")
        if cell["text"] != expected:
            _binding_error(field_id, "column header text differs: %s != %s" % (cell["text"], expected))


def segments_for_source(cells, source_id):
    seen = set()
    for table, segment, _, _ in cells.values():
        key = (table["table_id"], segment["segment_id"])
        if segment["source_id"] == source_id and key not in seen:
            seen.add(key)
            yield table["table_id"], segment


def reported_field(binding, cells):
    table, segment, row, cell = _cell_for_binding(binding, cells)
    _verify_headers(binding, table, segment, row, cell, cells)
    units = binding["units"]
    if units is not None:
        header_ids = binding["column_header_cell_ids"] + binding["row_header_cell_ids"]
        exact_context = [cell["text"]] + [cells[item][3]["text"] for item in header_ids if item in cells]
        if not any(units in text for text in exact_context):
            _binding_error(binding["field_id"],
                           "units are not a verbatim substring of the value or reviewed header cells")
    if not isinstance(binding["condition_cell_ids"], list) or not isinstance(binding["expected_condition_text"], list):
        _binding_error(binding["field_id"], "condition cell IDs and expected text must be arrays")
    if len(binding["condition_cell_ids"]) != len(binding["expected_condition_text"]):
        _binding_error(binding["field_id"], "condition cell ID/text counts differ")
    condition_evidence = []
    for condition_id, expected in zip(binding["condition_cell_ids"], binding["expected_condition_text"]):
        if condition_id not in cells:
            _binding_error(binding["field_id"], "condition cell does not exist: " + condition_id)
        condition_table, condition_segment, condition_row, condition_cell = cells[condition_id]
        if condition_table["table_id"] != table["table_id"] or condition_cell["source_id"] != cell["source_id"]:
            _binding_error(binding["field_id"], "condition cell must belong to the same table and source")
        if condition_cell["text"] != expected or not expected:
            _binding_error(binding["field_id"], "condition cell text differs from explicit expected text")
        condition_evidence.append({
            "source_id": condition_cell["source_id"], "page": condition_cell["page"],
            "paragraph_id": condition_cell["paragraph_id"], "quote": condition_cell["text"],
            "location": {"table_id": condition_table["table_id"],
                         "segment_id": condition_segment["segment_id"],
                         "row_id": condition_row["row_id"],
                         "column_start": condition_cell["column_start"],
                         "column_end": condition_cell["column_end"]},
        })
    evidence = {
        "source_id": cell["source_id"],
        "page": cell["page"],
        "paragraph_id": cell["paragraph_id"],
        "quote": cell["text"],
        "location": {
            "table_id": table["table_id"], "segment_id": segment["segment_id"],
            "row_id": row["row_id"], "column_start": cell["column_start"],
            "column_end": cell["column_end"],
            "row_header_cell_ids": list(binding["row_header_cell_ids"]),
            "column_header_cell_ids": list(binding["column_header_cell_ids"]),
        },
        "condition_evidence": condition_evidence,
    }
    notes = binding["notes"] + " [geometry=%s/%s/%s]" % (
        table["table_id"], segment["segment_id"], row["row_id"])
    return {
        "field_id": binding["field_id"], "status": "reported",
        "scalar": binding["scalar"], "units": units,
        "statistic": binding["statistic"],
        "experimental_condition": binding["experimental_condition"],
        "condition": binding["experimental_condition"],
        "comparator": binding["comparator"],
        "paragraph_id": cell["paragraph_id"], "quote": cell["text"],
        "evidence": [evidence], "notes": notes,
    }


def unreported_field(binding):
    if not isinstance(binding.get("reviewed_scope"), str) or not binding["reviewed_scope"].strip():
        _binding_error(binding.get("field_id", "<missing>"),
                       "not_reported requires a non-empty reviewed_scope")
    if not isinstance(binding.get("notes"), str) or not binding["notes"].strip():
        _binding_error(binding["field_id"], "not_reported notes are required")
    field = blank_field(binding["field_id"], binding["notes"] +
                        " Reviewed scope: " + binding["reviewed_scope"])
    field["status"] = "not_reported"
    for key in ("experimental_condition", "statistic", "comparator"):
        value = binding.get(key)
        if value is not None and not isinstance(value, str):
            _binding_error(binding["field_id"], key + " must be a string or null when supplied")
        field[key] = value
    field["condition"] = field["experimental_condition"]
    return field


def failed_field(binding):
    if not isinstance(binding.get("notes"), str) or not binding["notes"].strip():
        _binding_error(binding.get("field_id", "<missing>"),
                       "extraction_failed requires actionable notes")
    return blank_field(binding["field_id"], binding["notes"])


def conflict_field(binding, cells):
    candidates = binding.get("candidates")
    if not isinstance(candidates, list) or len(candidates) < 2:
        _binding_error(binding.get("field_id", "<missing>"),
                       "source_conflict needs at least two explicit candidates")
    if not isinstance(binding.get("notes"), str) or not binding["notes"].strip():
        _binding_error(binding["field_id"], "source_conflict notes are required")
    resolved = []
    for candidate in candidates:
        candidate = copy.deepcopy(candidate)
        candidate["field_id"] = binding["field_id"]
        resolved.append(reported_field(candidate, cells))
    distinct = {(row["scalar"], row["units"], row["statistic"],
                 row["experimental_condition"], row["comparator"]) for row in resolved}
    if len(distinct) < 2:
        _binding_error(binding["field_id"], "conflicting candidates are not actually distinct")
    first = resolved[0]
    common = {}
    for key in ("units", "statistic", "experimental_condition", "comparator"):
        common[key] = first[key] if all(row[key] == first[key] for row in resolved) else None
    field = blank_field(binding["field_id"], binding["notes"] +
                        " Conflicting verbatim values: " + "; ".join(
                            (row["scalar"] or "") + " at " + row["paragraph_id"] for row in resolved))
    field.update({
        "status": "source_conflict", "units": common["units"],
        "statistic": common["statistic"],
        "experimental_condition": common["experimental_condition"],
        "condition": common["experimental_condition"],
        "comparator": common["comparator"],
        "paragraph_id": None, "quote": None,
        "evidence": [row["evidence"][0] for row in resolved],
    })
    return field


def binding_template(payload, label=None):
    return {
        "schema_version": "table-coordinate-forge/reviewed-bindings-v1",
        "label": label or "Reviewed cell-binding template — candidate matches are not answers",
        "instructions": [
            "Inspect table-preview.md/svg and tables.json; replace extraction_failed only after semantic review.",
            "For reported, copy REPORTED_REQUIRED keys from a candidate template and check exact cell/header IDs.",
            "For not_reported, provide reviewed_scope; for unresolved layout, retain extraction_failed with actionable notes.",
        ],
        "bindings": [{"field_id": row["field_id"], "status": "extraction_failed",
                      "notes": "No reviewed cell binding yet; inspect reconstructed geometry.",
                      "reported_candidate_template": {
                          "field_id": row["field_id"], "status": "reported",
                          "source_id": "replace", "cell_id": "replace",
                          "scalar": "verbatim substring of cell", "units": None,
                          "statistic": None, "experimental_condition": None,
                          "comparator": None, "row_header_cell_ids": [],
                          "column_header_cell_ids": ["replace"],
                          "expected_row_header_text": [],
                          "expected_column_header_text": ["exact header text"],
                          "condition_cell_ids": [],
                          "expected_condition_text": [],
                          "notes": "replace with semantic review decision"
                      }} for row in payload["result"]["fields"]],
    }


def refresh_claims_and_uncertainties(payload):
    payload["claims"] = []
    payload["uncertainties"] = []
    for row in payload["result"]["fields"]:
        if row["status"] == "reported":
            evidence = row["evidence"][0]
            payload["claims"].append({
                "kind": "field_extraction", "field_id": row["field_id"],
                "source_id": evidence["source_id"], "evidence": [evidence],
                "location": evidence["location"],
                "statement": "%s = %s%s under %s" % (
                    row["field_id"], row["scalar"],
                    (" " + row["units"]) if row["units"] else "",
                    row["experimental_condition"] or "no additional condition recorded"),
            })
        elif row["status"] == "source_conflict":
            payload["claims"].append({
                "kind": "source_conflict", "field_id": row["field_id"],
                "source_id": row["evidence"][0]["source_id"],
                "evidence": row["evidence"],
                "location": [item["location"] for item in row["evidence"]],
            })
            payload["uncertainties"].append({
                "kind": "source_conflict", "field_id": row["field_id"],
                "message": row["notes"],
            })
        else:
            payload["uncertainties"].append({
                "kind": row["status"], "field_id": row["field_id"],
                "message": row["notes"],
            })
    if not payload["uncertainties"]:
        payload["uncertainties"].append({
            "kind": "geometry_review", "field_id": None,
            "message": "No unresolved field binding remains; original PDF visual review is still recommended for merged cells.",
        })


def apply_bindings(payload, table_document, binding_document, expected_field_ids):
    """Return a staged result; caller validates and atomically writes it."""
    if not isinstance(binding_document, dict) or not isinstance(binding_document.get("bindings"), list):
        raise ValueError("Reviewed binding document needs a bindings array")
    cells, _ = table_indexes(table_document)
    binding_by_id = {}
    for binding in binding_document["bindings"]:
        if not isinstance(binding, dict) or not isinstance(binding.get("field_id"), str):
            raise ValueError("Every binding needs a field_id")
        field_id = binding["field_id"]
        if field_id not in expected_field_ids:
            raise ValueError("Binding field_id is not requested: " + field_id)
        if field_id in binding_by_id:
            raise ValueError("Duplicate binding for field_id: " + field_id)
        binding_by_id[field_id] = binding
    fields = []
    for field_id in expected_field_ids:
        binding = binding_by_id.get(field_id)
        if binding is None:
            fields.append(blank_field(field_id, "No reviewed cell binding was supplied; inspect candidate geometry."))
            continue
        status = binding.get("status")
        if status == "reported":
            fields.append(reported_field(binding, cells))
        elif status == "not_reported":
            fields.append(unreported_field(binding))
        elif status == "source_conflict":
            fields.append(conflict_field(binding, cells))
        elif status == "extraction_failed":
            fields.append(failed_field(binding))
        else:
            _binding_error(field_id, "invalid binding status: " + str(status))
    staged = copy.deepcopy(payload)
    staged["result"]["fields"] = fields
    staged["result"]["layout"] = {
        "usable": bool(table_document.get("tables")),
        "table_count": len(table_document.get("tables", [])),
        "segment_count": sum(len(table["segments"]) for table in table_document.get("tables", [])),
        "preview_markdown": "table-preview.md", "preview_svg": "table-preview.svg",
        "binding_policy": "Only explicit reviewed bindings were applied; geometry candidates are not auto-promoted.",
    }
    staged["status"] = overall_status(fields)
    refresh_claims_and_uncertainties(staged)
    staged.setdefault("change_records", []).append({
        "event": "reviewed_bindings_applied", "at": utc_now(),
        "detail": "Applied %d explicit bindings; %d fields remain extraction_failed." % (
            len(binding_by_id), sum(row["status"] == "extraction_failed" for row in fields)),
    })
    return validate_result(staged, expected_field_ids)
