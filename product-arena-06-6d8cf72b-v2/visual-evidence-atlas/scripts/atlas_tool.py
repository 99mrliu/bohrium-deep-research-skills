#!/usr/bin/env python3
"""Deterministic, standard-library visual evidence atlas validator/renderer."""

import argparse
import copy
import html
import json
import math
import os
import posixpath
from pathlib import Path
import sys


REGION_KINDS = {
    "figure", "panel", "caption", "body_paragraph", "table",
    "table_row", "table_column", "table_cell",
}
EVIDENCE_STATES = {"available", "missing", "unreadable", "not_reported", "conflict"}
CORROBORATION_STATES = {"corroborated", "not_reported", "conflict", "missing", "unreadable"}
INSPECTION_STATES = {"agent_attested_inspected", "not_inspected", "missing", "unreadable"}
SCHEMA_KEYS = {"type", "properties", "required", "additionalProperties", "items", "enum", "const", "minItems"}


class AtlasProblem(Exception):
    pass


def read_json(path):
    try:
        with open(path, "r", encoding="utf-8") as handle:
            value = json.load(handle)
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise AtlasProblem(f"cannot read JSON {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise AtlasProblem(f"JSON root must be an object: {path}")
    return value


def read_text(path):
    try:
        with open(path, "r", encoding="utf-8") as handle:
            return handle.read()
    except (OSError, UnicodeError) as exc:
        raise AtlasProblem(f"cannot read UTF-8 text {path}: {exc}") from exc


def write_text(path, content):
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    with open(target, "w", encoding="utf-8", newline="\n") as handle:
        handle.write(content)


def write_json(path, value):
    write_text(path, json.dumps(value, ensure_ascii=False, indent=2) + "\n")


def require_dict(value, label, errors):
    if not isinstance(value, dict):
        errors.append(f"{label} must be an object")
        return {}
    return value


def require_list(value, label, errors):
    if not isinstance(value, list):
        errors.append(f"{label} must be an array")
        return []
    return value


def duplicate_values(values):
    seen = set()
    duplicates = set()
    for value in values:
        if value in seen:
            duplicates.add(value)
        seen.add(value)
    return sorted(duplicates)


def valid_anchor(anchor, source_text, label, errors):
    if not isinstance(anchor, dict):
        errors.append(f"{label} must be an object")
        return
    if set(anchor) != {"start", "end", "quote"}:
        errors.append(f"{label} must contain exactly start, end, quote")
        return
    start, end, quote = anchor["start"], anchor["end"], anchor["quote"]
    if isinstance(start, bool) or not isinstance(start, int) or start < 0:
        errors.append(f"{label}.start must be a nonnegative integer")
        return
    if isinstance(end, bool) or not isinstance(end, int) or end < 0:
        errors.append(f"{label}.end must be a nonnegative integer")
        return
    if not isinstance(quote, str) or not quote:
        errors.append(f"{label}.quote must be a nonempty string")
        return
    if end != start + len(quote):
        errors.append(f"{label}.end must equal start plus quote length")
    if end > len(source_text) or source_text[start:end] != quote:
        errors.append(f"{label} quote/offset does not match supplied text source")


def check_corroboration(value, source_text, label, errors):
    if not isinstance(value, dict) or set(value) != {"state", "source_anchor"}:
        errors.append(f"{label} must contain exactly state and source_anchor")
        return
    state = value.get("state")
    if state not in CORROBORATION_STATES:
        errors.append(f"{label}.state is invalid: {state!r}")
    anchor = value.get("source_anchor")
    if state in {"corroborated", "conflict"}:
        if anchor is None:
            errors.append(f"{label} requires a source_anchor for {state}")
        else:
            valid_anchor(anchor, source_text, f"{label}.source_anchor", errors)
    elif state == "not_reported" and anchor is not None:
        errors.append(f"{label} not_reported requires a null source_anchor")
    elif anchor is not None:
        valid_anchor(anchor, source_text, f"{label}.source_anchor", errors)


def normalize_source_file(source_file):
    """Normalize a local source identity without touching the filesystem."""
    return posixpath.normpath(source_file.strip().replace("\\", "/"))


def subject_region_issue(claim, region_by_id):
    for state in ("conflict", "missing", "unreadable", "not_reported"):
        region_ids = [
            region_id for region_id in claim["subject_region_ids"]
            if region_by_id[region_id].get("evidence_state", "available") == state
        ]
        if region_ids:
            return state, region_ids
    return None, []


def verified_table_cell_identity(region, region_by_id):
    row_label = region.get("row_label")
    column_label = region.get("column_label")
    if not isinstance(row_label, str) or not row_label.strip():
        return False
    if not isinstance(column_label, str) or not column_label.strip():
        return False
    parent = region_by_id.get(region.get("parent_id"))
    if parent is None:
        return True
    if parent.get("kind") == "table_row" and parent.get("row_label") != row_label:
        return False
    if parent.get("kind") == "table_column" and parent.get("column_label") != column_label:
        return False
    return True


def is_direct_inspected_table_cell(claim, region_by_id):
    if claim["inspection"]["status"] != "agent_attested_inspected":
        return False
    cell_ids = [
        region_id for region_id in claim["subject_region_ids"]
        if region_by_id[region_id].get("kind") == "table_cell"
    ]
    return bool(cell_ids) and all(
        region_by_id[region_id].get("evidence_state", "available") == "available"
        and verified_table_cell_identity(region_by_id[region_id], region_by_id)
        for region_id in cell_ids
    )


def resolve_claim(claim, region_by_id):
    region_state, region_ids = subject_region_issue(claim, region_by_id)
    if region_state:
        return (
            f"unresolved_{region_state}",
            f"subject region evidence_state is {region_state}: {', '.join(region_ids)}",
        )

    caption = claim["caption_corroboration"]["state"]
    body = claim["body_corroboration"]["state"]
    inspection = claim["inspection"]["status"]
    subject_kinds = {region_by_id[rid]["kind"] for rid in claim["subject_region_ids"]}
    direct_cell = is_direct_inspected_table_cell(claim, region_by_id)

    for state in ("conflict", "missing", "unreadable"):
        if caption == state or body == state:
            locations = []
            if caption == state:
                locations.append("caption")
            if body == state:
                locations.append("body")
            return f"unresolved_{state}", f"{'/'.join(locations)} corroboration is {state}"
    if (
        "table_cell" in subject_kinds
        and not direct_cell
        and caption == "corroborated"
        and body == "not_reported"
    ):
        if inspection != "agent_attested_inspected":
            reason = "individual table cell was not agent-attested inspected; caption is not direct visual cell evidence"
        else:
            reason = "individual table-cell row/column identity is unclear; caption is not direct visual cell evidence"
        return "unresolved_caption_only_cell", reason
    if inspection != "agent_attested_inspected":
        state = inspection.replace("agent_attested_", "")
        return f"unresolved_{state}", f"inspection status is {inspection}"
    if direct_cell:
        return (
            "reviewed_corroborated",
            "agent-attested direct inspection of an available original table cell with verified row/column identity; "
            "caption/body corroboration remains separately recorded and is not machine visual truth",
        )
    if caption == "not_reported" or body == "not_reported":
        return "unresolved_not_reported", "caption or body does not report the claim"
    if caption == "corroborated" and body == "corroborated":
        return "reviewed_corroborated", "agent attestation plus caption and body anchors; not machine visual truth"
    return "unresolved_incomplete", "corroboration is incomplete"


def unresolved_state(resolution):
    state = resolution.removeprefix("unresolved_")
    if state == "caption_only_cell":
        return "not_reported"
    if state == "incomplete":
        return "not_inspected"
    return state


def validate_atlas(atlas, source_text, image_root):
    errors, warnings, unresolved = [], [], []
    required = {
        "schema_version", "case_id", "synthetic", "coordinate_convention",
        "pages", "crops", "regions", "visual_claims", "change_records"
    }
    missing = sorted(required - set(atlas))
    if missing:
        errors.append(f"atlas missing required keys: {', '.join(missing)}")
        return finish_audit(atlas, errors, warnings, unresolved)
    if atlas.get("schema_version") != "1.0":
        errors.append("schema_version must be '1.0'")
    if not isinstance(atlas.get("case_id"), str) or not atlas.get("case_id"):
        errors.append("case_id must be a nonempty string")
    if not isinstance(atlas.get("synthetic"), bool):
        errors.append("synthetic must be boolean")
    convention = atlas.get("coordinate_convention")
    expected_convention = {
        "name": "original-render-top-left-px",
        "origin": "top-left",
        "units": "px",
        "bbox": "[x0,y0,x1,y1]",
        "x1_y1": "exclusive",
        "source_anchor_offsets": "unicode-codepoint-zero-based-end-exclusive",
    }
    if convention != expected_convention:
        errors.append("coordinate_convention must exactly match the documented original-render convention")

    pages = require_list(atlas.get("pages"), "pages", errors)
    crops = require_list(atlas.get("crops"), "crops", errors)
    regions = require_list(atlas.get("regions"), "regions", errors)
    claims = require_list(atlas.get("visual_claims"), "visual_claims", errors)
    changes = require_list(atlas.get("change_records"), "change_records", errors)
    if not pages:
        errors.append("pages must not be empty")

    page_by_id = {}
    source_page_keys = []
    for index, raw_page in enumerate(pages):
        label = f"pages[{index}]"
        page = require_dict(raw_page, label, errors)
        if not page:
            continue
        page_id = page.get("page_id")
        if not isinstance(page_id, str) or not page_id:
            errors.append(f"{label}.page_id must be a nonempty string")
            continue
        if page_id in page_by_id:
            errors.append(f"duplicate page_id: {page_id}")
            continue
        page_by_id[page_id] = page
        pdf_index = page.get("pdf_page_index")
        valid_pdf_index = not isinstance(pdf_index, bool) and isinstance(pdf_index, int) and pdf_index >= 0
        if not valid_pdf_index:
            errors.append(f"{label}.pdf_page_index must be a nonnegative integer")
        if page.get("printed_page") is not None and not isinstance(page.get("printed_page"), str):
            errors.append(f"{label}.printed_page must be a string or null")
        source_file = page.get("source_file")
        if not isinstance(source_file, str) or not source_file.strip():
            errors.append(f"{label}.source_file must be a nonempty source identity")
        elif valid_pdf_index:
            source_page_keys.append((normalize_source_file(source_file), pdf_index))
        image = require_dict(page.get("image"), f"{label}.image", errors)
        width, height = image.get("width"), image.get("height")
        for dimension_name, dimension in (("width", width), ("height", height)):
            if isinstance(dimension, bool) or not isinstance(dimension, int) or dimension <= 0:
                errors.append(f"{label}.image.{dimension_name} must be a positive integer")
        image_path = image.get("path")
        if not isinstance(image_path, str) or not image_path:
            errors.append(f"{label}.image.path must be a nonempty string")
        elif image_root is not None:
            resolved = resolve_image(image_path, image_root)
            if not resolved.is_file():
                errors.append(f"{label}.image.path does not identify an existing original image: {image_path}")
        if not isinstance(image.get("role"), str) or not image.get("role"):
            errors.append(f"{label}.image.role must identify the original render/fixture role")
        layout = require_dict(page.get("layout"), f"{label}.layout", errors)
        columns = layout.get("columns")
        if isinstance(columns, bool) or not isinstance(columns, int) or columns < 1:
            errors.append(f"{label}.layout.columns must be a positive integer")
        order = layout.get("reading_order")
        if order not in {"certain", "uncertain"}:
            errors.append(f"{label}.layout.reading_order must be certain or uncertain")
        if isinstance(columns, int) and not isinstance(columns, bool) and columns > 1:
            if not isinstance(layout.get("note"), str) or not layout.get("note"):
                errors.append(f"{label}.layout.note is required for a multi-column page")
            if order == "uncertain":
                warnings.append({
                    "code": "READING_ORDER_UNCERTAIN",
                    "state": "uncertain",
                    "message": f"{page_id}: double/multi-column reading order is uncertain",
                    "claim_ids": [],
                })
    for source_file, pdf_index in duplicate_values(source_page_keys):
        errors.append(
            f"duplicate pdf_page_index {pdf_index} for normalized source_file: {source_file}"
        )

    region_by_id = {}
    for index, raw_region in enumerate(regions):
        label = f"regions[{index}]"
        region = require_dict(raw_region, label, errors)
        if not region:
            continue
        region_id = region.get("region_id")
        if not isinstance(region_id, str) or not region_id:
            errors.append(f"{label}.region_id must be a nonempty string")
            continue
        if region_id in region_by_id:
            errors.append(f"duplicate region_id: {region_id}")
            continue
        region_by_id[region_id] = region
        if region.get("page_id") not in page_by_id:
            errors.append(f"{label}.page_id does not reference a supplied page: {region.get('page_id')!r}")
            continue
        page = page_by_id[region["page_id"]]
        if region.get("kind") not in REGION_KINDS:
            errors.append(f"{label}.kind is invalid: {region.get('kind')!r}")
        bbox = region.get("bbox")
        if not isinstance(bbox, list) or len(bbox) != 4:
            errors.append(f"{label}.bbox must be [x0,y0,x1,y1]")
        else:
            numeric = all(isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v) for v in bbox)
            if not numeric:
                errors.append(f"{label}.bbox values must be finite numbers")
            else:
                x0, y0, x1, y1 = bbox
                width, height = page["image"].get("width"), page["image"].get("height")
                if not (0 <= x0 < x1 and 0 <= y0 < y1):
                    errors.append(f"{label}.bbox has impossible/reversed/negative coordinates: {bbox}")
                elif isinstance(width, int) and isinstance(height, int) and (x1 > width or y1 > height):
                    errors.append(f"{label}.bbox exceeds original image bounds: {bbox}")
        state = region.get("evidence_state", "available")
        if state not in EVIDENCE_STATES:
            errors.append(f"{label}.evidence_state is invalid: {state!r}")
        text_evidence = region.get("text_evidence")
        if region.get("kind") in {"caption", "body_paragraph", "table_cell"}:
            if not isinstance(text_evidence, dict):
                errors.append(f"{label}.text_evidence is required for {region.get('kind')}")
            else:
                if not isinstance(text_evidence.get("role"), str) or not text_evidence.get("role"):
                    errors.append(f"{label}.text_evidence.role is required")
                valid_anchor(text_evidence.get("source_anchor"), source_text, f"{label}.text_evidence.source_anchor", errors)
        elif text_evidence is not None:
            if not isinstance(text_evidence, dict):
                errors.append(f"{label}.text_evidence must be an object")
            elif text_evidence.get("source_anchor") is not None:
                valid_anchor(text_evidence["source_anchor"], source_text, f"{label}.text_evidence.source_anchor", errors)

    for region_id, region in region_by_id.items():
        parent_id = region.get("parent_id")
        if parent_id is not None:
            parent = region_by_id.get(parent_id)
            if parent is None:
                errors.append(f"region {region_id} has missing parent_id {parent_id}")
            elif parent.get("page_id") != region.get("page_id"):
                errors.append(f"region {region_id} and parent {parent_id} must share page_id")
        if region.get("kind") == "panel" and not isinstance(region.get("panel_label"), str):
            errors.append(f"panel {region_id} requires a literal panel_label, empty only when uncertainty is recorded")
        if region.get("kind") == "table_cell":
            if not isinstance(region.get("row_label"), str) or not isinstance(region.get("column_label"), str):
                errors.append(f"table_cell {region_id} requires row_label and column_label strings")

    crop_ids = []
    for index, raw_crop in enumerate(crops):
        label = f"crops[{index}]"
        crop = require_dict(raw_crop, label, errors)
        if not crop:
            continue
        crop_id = crop.get("crop_id")
        if not isinstance(crop_id, str) or not crop_id:
            errors.append(f"{label}.crop_id must be a nonempty string")
            continue
        crop_ids.append(crop_id)
        page = page_by_id.get(crop.get("page_id"))
        if page is None:
            errors.append(f"{label}.page_id does not reference a supplied page")
            continue
        parent_id = crop.get("parent_region_id")
        parent = region_by_id.get(parent_id)
        if parent is None:
            errors.append(f"{label}.parent_region_id does not reference a supplied region")
        elif parent.get("page_id") != crop.get("page_id"):
            errors.append(f"{label} crop and parent region must share page_id")
        image = require_dict(crop.get("image"), f"{label}.image", errors)
        for dimension_name in ("width", "height"):
            dimension = image.get(dimension_name)
            if isinstance(dimension, bool) or not isinstance(dimension, int) or dimension <= 0:
                errors.append(f"{label}.image.{dimension_name} must be a positive integer")
        if not isinstance(image.get("role"), str) or not image.get("role"):
            errors.append(f"{label}.image.role must identify the original crop role")
        image_path = image.get("path")
        if not isinstance(image_path, str) or not image_path:
            errors.append(f"{label}.image.path must be a nonempty string")
        elif image_root is not None and not resolve_image(image_path, image_root).is_file():
            errors.append(f"{label}.image.path does not identify an existing original crop: {image_path}")
        bbox = crop.get("source_bbox")
        if not isinstance(bbox, list) or len(bbox) != 4:
            errors.append(f"{label}.source_bbox must be [x0,y0,x1,y1] in original page coordinates")
        else:
            numeric = all(isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v) for v in bbox)
            if not numeric:
                errors.append(f"{label}.source_bbox values must be finite numbers")
            else:
                x0, y0, x1, y1 = bbox
                width, height = page["image"].get("width"), page["image"].get("height")
                if not (0 <= x0 < x1 and 0 <= y0 < y1):
                    errors.append(f"{label}.source_bbox has impossible/reversed/negative coordinates: {bbox}")
                elif isinstance(width, int) and isinstance(height, int) and (x1 > width or y1 > height):
                    errors.append(f"{label}.source_bbox exceeds original image bounds: {bbox}")
    for duplicate in duplicate_values(crop_ids):
        errors.append(f"duplicate crop_id: {duplicate}")

    change_by_id = {}
    for index, raw_change in enumerate(changes):
        label = f"change_records[{index}]"
        change = require_dict(raw_change, label, errors)
        if not change:
            continue
        required_change = {"change_record_id", "actor", "action", "subject_ids", "note"}
        if set(change) != required_change:
            errors.append(f"{label} must contain exactly {sorted(required_change)}")
        change_id = change.get("change_record_id")
        if not isinstance(change_id, str) or not change_id:
            errors.append(f"{label}.change_record_id must be nonempty")
        elif change_id in change_by_id:
            errors.append(f"duplicate change_record_id: {change_id}")
        else:
            change_by_id[change_id] = change
        if not isinstance(change.get("subject_ids"), list) or not all(isinstance(v, str) for v in change.get("subject_ids", [])):
            errors.append(f"{label}.subject_ids must be an array of strings")

    claim_ids = []
    for index, raw_claim in enumerate(claims):
        label = f"visual_claims[{index}]"
        claim = require_dict(raw_claim, label, errors)
        if not claim:
            continue
        claim_id = claim.get("claim_id")
        if not isinstance(claim_id, str) or not claim_id:
            errors.append(f"{label}.claim_id must be nonempty")
            continue
        claim_ids.append(claim_id)
        if not isinstance(claim.get("claim_text"), str) or not claim.get("claim_text"):
            errors.append(f"{label}.claim_text must be nonempty")
        if not isinstance(claim.get("decisive"), bool):
            errors.append(f"{label}.decisive must be boolean")
        subject_ids = claim.get("subject_region_ids")
        if not isinstance(subject_ids, list) or not subject_ids or not all(isinstance(v, str) for v in subject_ids):
            errors.append(f"{label}.subject_region_ids must be a nonempty string array")
        else:
            for duplicate in duplicate_values(subject_ids):
                errors.append(f"{label} repeats subject region {duplicate}")
            for region_id in subject_ids:
                if region_id not in region_by_id:
                    errors.append(f"{label} has missing subject region {region_id}")
        inspection = claim.get("inspection")
        if not isinstance(inspection, dict) or set(inspection) != {"status", "change_record_id"}:
            errors.append(f"{label}.inspection must contain exactly status and change_record_id")
        else:
            status = inspection.get("status")
            change_id = inspection.get("change_record_id")
            if status not in INSPECTION_STATES:
                errors.append(f"{label}.inspection.status invalid: {status!r}")
            if status == "agent_attested_inspected":
                record = change_by_id.get(change_id)
                if record is None:
                    errors.append(f"{label} agent attestation has missing change_record {change_id!r}")
                else:
                    if record.get("action") != "visual_inspection_attestation":
                        errors.append(f"{label} attestation change_record must use visual_inspection_attestation")
                    if claim_id not in record.get("subject_ids", []):
                        errors.append(f"{label} attestation change_record must name the claim in subject_ids")
            elif change_id is not None:
                errors.append(f"{label} non-attested inspection requires null change_record_id")
        check_corroboration(claim.get("caption_corroboration"), source_text, f"{label}.caption_corroboration", errors)
        check_corroboration(claim.get("body_corroboration"), source_text, f"{label}.body_corroboration", errors)
    for duplicate in duplicate_values(claim_ids):
        errors.append(f"duplicate claim_id: {duplicate}")

    all_record_ids = list(page_by_id) + list(region_by_id) + crop_ids + claim_ids + list(change_by_id)
    for duplicate in duplicate_values(all_record_ids):
        errors.append(f"record ID is not globally unique across pages/crops/regions/claims/changes: {duplicate}")

    if not errors:
        for claim in claims:
            resolution, reason = resolve_claim(claim, region_by_id)
            if (
                claim["decisive"]
                and resolution == "reviewed_corroborated"
                and is_direct_inspected_table_cell(claim, region_by_id)
                and claim["body_corroboration"]["state"] == "not_reported"
            ):
                warnings.append({
                    "code": "BODY_CORROBORATION_NOT_REPORTED",
                    "state": "not_reported",
                    "message": (
                        f"{claim['claim_id']}: direct original-cell evidence remains reviewed; "
                        "independent body corroboration is absent"
                    ),
                    "claim_ids": [claim["claim_id"]],
                })
            if claim["decisive"] and resolution != "reviewed_corroborated":
                item = {
                    "code": resolution.upper(),
                    "state": unresolved_state(resolution),
                    "message": f"{claim['claim_id']}: {reason}",
                    "claim_ids": [claim["claim_id"]],
                }
                unresolved.append(item)
                warnings.append(item)
    return finish_audit(atlas, errors, warnings, unresolved)


def finish_audit(atlas, errors, warnings, unresolved):
    status = "failed" if errors else ("partial" if warnings else "complete")
    return {
        "case_id": atlas.get("case_id", "unknown"),
        "synthetic": atlas.get("synthetic", False),
        "status": status,
        "machine_visual_truth_verified": False,
        "machine_visual_truth_note": "The validator checks records and attestations only; it cannot verify actual agent sight or pixel truth.",
        "errors": errors,
        "warnings": warnings,
        "unresolved_claims": unresolved,
    }


def resolve_image(image_path, image_root):
    path = Path(image_path)
    return path if path.is_absolute() else Path(image_root) / path


def file_href(image_path, image_root, output_dir):
    source = resolve_image(image_path, image_root).resolve()
    target = Path(output_dir).resolve()
    return Path(os.path.relpath(str(source), str(target))).as_posix()


def quote_text(anchor):
    if not anchor:
        return "—"
    return f"{anchor['quote']} [{anchor['start']}:{anchor['end']}]"


def build_result(atlas, audit, case_contract):
    claims = []
    region_by_id = {region["region_id"]: region for region in atlas["regions"]}
    for claim in atlas["visual_claims"]:
        resolution, _ = resolve_claim(claim, region_by_id)
        claims.append({
            "claim_id": claim["claim_id"],
            "decisive": claim["decisive"],
            "inspection_status": claim["inspection"]["status"],
            "caption_state": claim["caption_corroboration"]["state"],
            "body_state": claim["body_corroboration"]["state"],
            "resolution": resolution,
            "change_record_id": claim["inspection"]["change_record_id"],
        })
    sources = [{
        "region_id": region["region_id"],
        "page_id": region["page_id"],
        "kind": region["kind"],
        "bbox": region["bbox"],
        "evidence_state": region.get("evidence_state", "available"),
    } for region in atlas["regions"]]
    artifacts = [
        {"path": "atlas.html", "kind": "atlas_html", "original": False},
        {"path": "atlas.md", "kind": "atlas_markdown", "original": False},
        {"path": "audit_report.json", "kind": "audit_report", "original": False},
    ]
    for page in atlas["pages"]:
        artifacts.append({"path": page["image"]["path"], "kind": "original_page_evidence", "original": True})
    for crop in atlas["crops"]:
        artifacts.append({"path": crop["image"]["path"], "kind": "original_crop_evidence", "original": True})
    result = {
        "case_id": atlas["case_id"],
        "synthetic": atlas["synthetic"],
        "status": "failed" if audit["errors"] else ("partial" if audit["warnings"] else "complete"),
        "task_answer": atlas.get("task_answer", "No direct task answer was supplied."),
        "sources": sources,
        "visual_claims": claims,
        "artifacts": artifacts,
        "uncertainty": audit["warnings"],
        "change_records": copy.deepcopy(atlas["change_records"]),
        "failures": list(audit["errors"]),
    }
    if case_contract.get("case_id") != atlas["case_id"]:
        raise AtlasProblem("case_id differs between case and atlas")
    schema = case_contract.get("output_contract")
    if not isinstance(schema, dict):
        raise AtlasProblem("case output_contract must be an object")
    schema_errors = []
    validate_closed_schema(result, schema, "result", schema_errors)
    if schema_errors:
        raise AtlasProblem("output contract validation failed: " + "; ".join(schema_errors))
    return result


def validate_closed_schema(value, schema, label, errors):
    if not isinstance(schema, dict):
        errors.append(f"{label} schema must be an object")
        return
    unknown = set(schema) - SCHEMA_KEYS
    if unknown:
        errors.append(f"{label} schema uses unsupported keywords: {sorted(unknown)}")
        return
    if "const" in schema and value != schema["const"]:
        errors.append(f"{label} must equal const {schema['const']!r}")
    if "enum" in schema:
        if not isinstance(schema["enum"], list) or value not in schema["enum"]:
            errors.append(f"{label} is not in enum")
    expected = schema.get("type")
    type_checks = {
        "object": lambda v: isinstance(v, dict),
        "array": lambda v: isinstance(v, list),
        "string": lambda v: isinstance(v, str),
        "integer": lambda v: isinstance(v, int) and not isinstance(v, bool),
        "number": lambda v: isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v),
        "boolean": lambda v: isinstance(v, bool),
        "null": lambda v: v is None,
    }
    expected_list = expected if isinstance(expected, list) else [expected]
    if not expected_list or any(item not in type_checks for item in expected_list):
        errors.append(f"{label} schema has missing/unsupported type {expected!r}")
        return
    matched = [item for item in expected_list if type_checks[item](value)]
    if not matched:
        errors.append(f"{label} must have type {expected}")
        return
    effective_type = matched[0]
    if effective_type == "object":
        properties = schema.get("properties")
        required = schema.get("required")
        if not isinstance(properties, dict) or not isinstance(required, list):
            errors.append(f"{label} object schema needs properties and required")
            return
        if schema.get("additionalProperties") is not False:
            errors.append(f"{label} object schema must set additionalProperties false")
        for key in required:
            if not isinstance(key, str) or key not in properties:
                errors.append(f"{label} schema has invalid required key {key!r}")
            elif key not in value:
                errors.append(f"{label} missing required field {key}")
        if schema.get("additionalProperties") is False:
            for key in value:
                if key not in properties:
                    errors.append(f"{label} has additional field {key}")
        for key, child in value.items():
            if key in properties:
                validate_closed_schema(child, properties[key], f"{label}.{key}", errors)
    elif effective_type == "array":
        if "minItems" in schema and (not isinstance(schema["minItems"], int) or len(value) < schema["minItems"]):
            errors.append(f"{label} violates minItems")
        items = schema.get("items")
        if not isinstance(items, dict):
            errors.append(f"{label} array schema needs items")
        else:
            for index, child in enumerate(value):
                validate_closed_schema(child, items, f"{label}[{index}]", errors)


def render_markdown(atlas, audit, image_root, output_dir):
    synthetic = " **SYNTHETIC — FICTIONAL EVIDENCE, NOT A REAL PAPER.**" if atlas["synthetic"] else ""
    region_by_id = {r["region_id"]: r for r in atlas["regions"]}
    lines = [
        "# Visual Evidence Atlas" + (" — SYNTHETIC" if atlas["synthetic"] else ""),
        "", synthetic, "",
        f"- Case: `{atlas['case_id']}`",
        f"- Validation: **{audit['status']}**",
        "- Machine visual truth verified: **false** (records cannot prove actual sight).",
        "- Coordinates: original-render top-left pixels, `[x0,y0,x1,y1]`, end-exclusive.",
        "", "## Original pages", "",
    ]
    for page in atlas["pages"]:
        href = file_href(page["image"]["path"], image_root, output_dir)
        lines.extend([
            f"### {page['page_id']} — PDF index {page['pdf_page_index']}; printed page {page.get('printed_page')}",
            "", f"Source file identity: `{page['source_file']}`",
            f"Reading order: **{page['layout']['reading_order']}**; columns: {page['layout']['columns']}. {page['layout'].get('note', '')}", "",
            f"[Open original evidence]({href})", "", f"![Original evidence {page['page_id']}]({href})", "",
        ])
    lines.extend(["", "## Original crops", ""])
    if atlas["crops"]:
        for crop in atlas["crops"]:
            href = file_href(crop["image"]["path"], image_root, output_dir)
            lines.extend([
                f"### {crop['crop_id']}", "",
                f"Parent region: `{crop['parent_region_id']}`; page: `{crop['page_id']}`; original-page source bbox: `{crop['source_bbox']}`. Crop pixel dimensions: {crop['image']['width']}×{crop['image']['height']}.", "",
                f"[Open original crop]({href})", "", f"![Original crop {crop['crop_id']}]({href})", "",
            ])
    else:
        lines.append("- No task-relevant original crops were supplied.")
    lines.extend(["", "## Regions", "", "| ID | Page | Kind | Identity | BBox | Evidence | Source quote |", "|---|---|---|---|---|---|---|"])
    for region in atlas["regions"]:
        identity = "; ".join(f"{key}={region[key]}" for key in ("panel_label", "row_label", "column_label") if key in region) or "—"
        evidence = region.get("text_evidence") or {}
        quote = quote_text(evidence.get("source_anchor")).replace("|", "\\|")
        lines.append(f"| {region['region_id']} | {region['page_id']} | {region['kind']} | {identity} | {region['bbox']} | {region.get('evidence_state', 'available')} | {quote} |")
    lines.extend(["", "## Decisive claims and corroboration", ""])
    for claim in atlas["visual_claims"]:
        resolution, reason = resolve_claim(claim, region_by_id)
        lines.extend([
            f"### {claim['claim_id']} — {resolution}", "", claim["claim_text"], "",
            f"- Decisive: {claim['decisive']}; subjects: {', '.join(claim['subject_region_ids'])}",
            f"- Inspection: **{claim['inspection']['status']}**; change_record: {claim['inspection']['change_record_id']}",
            f"- Caption: **{claim['caption_corroboration']['state']}** — {quote_text(claim['caption_corroboration']['source_anchor'])}",
            f"- Body: **{claim['body_corroboration']['state']}** — {quote_text(claim['body_corroboration']['source_anchor'])}",
            f"- Resolution basis: {reason}", "",
        ])
    lines.extend(["## Unresolved items and warnings", ""])
    if audit["warnings"]:
        for warning in audit["warnings"]:
            lines.append(f"- **{warning['code']} / {warning['state']}**: {warning['message']}")
    else:
        lines.append("- None; actual sight still is not machine-verified.")
    return "\n".join(lines) + "\n"


def render_html(atlas, audit, image_root, output_dir):
    region_by_id = {r["region_id"]: r for r in atlas["regions"]}
    page_sections = []
    for page in atlas["pages"]:
        href = html.escape(file_href(page["image"]["path"], image_root, output_dir), quote=True)
        width, height = page["image"]["width"], page["image"]["height"]
        boxes = []
        for region in atlas["regions"]:
            if region["page_id"] != page["page_id"]:
                continue
            x0, y0, x1, y1 = region["bbox"]
            style = f"left:{x0 / width * 100:.5f}%;top:{y0 / height * 100:.5f}%;width:{(x1-x0) / width * 100:.5f}%;height:{(y1-y0) / height * 100:.5f}%"
            boxes.append(f'<span class="box" style="{style}" title="{html.escape(region["region_id"], quote=True)}"><b>{html.escape(region["region_id"])}</b></span>')
        page_sections.append(f'''<section><h2>{html.escape(page["page_id"])}</h2>
<p>PDF index {page["pdf_page_index"]}; printed page {html.escape(str(page.get("printed_page")))}; source identity <code>{html.escape(page["source_file"])}</code>.</p>
<p class="warning">Columns: {page["layout"]["columns"]}; reading order: {html.escape(page["layout"]["reading_order"])}. {html.escape(page["layout"].get("note", ""))}</p>
<p><a href="{href}">Open original evidence ({html.escape(page["image"]["path"])})</a></p>
<div class="page"><a href="{href}"><img src="{href}" alt="Original evidence {html.escape(page["page_id"], quote=True)}"></a>{''.join(boxes)}</div></section>''')
    crop_sections = []
    for crop in atlas["crops"]:
        href = html.escape(file_href(crop["image"]["path"], image_root, output_dir), quote=True)
        crop_sections.append(f'''<section><h2>Original crop {html.escape(crop["crop_id"])}</h2>
<p>Page <code>{html.escape(crop["page_id"])}</code>; parent region <code>{html.escape(crop["parent_region_id"])}</code>; original-page source bbox <code>{html.escape(str(crop["source_bbox"]))}</code>. Crop dimensions: {crop["image"]["width"]}×{crop["image"]["height"]} pixels.</p>
<p><a href="{href}">Open original crop</a></p><a href="{href}"><img class="crop" src="{href}" alt="Original crop {html.escape(crop["crop_id"], quote=True)}"></a></section>''')
    region_rows = []
    for region in atlas["regions"]:
        evidence = region.get("text_evidence") or {}
        identity = "; ".join(f"{key}={region[key]}" for key in ("panel_label", "row_label", "column_label") if key in region) or "—"
        region_rows.append("<tr>" + "".join(f"<td>{html.escape(str(value))}</td>" for value in (
            region["region_id"], region["page_id"], region["kind"], identity, region["bbox"],
            region.get("evidence_state", "available"), quote_text(evidence.get("source_anchor")),
        )) + "</tr>")
    claim_sections = []
    for claim in atlas["visual_claims"]:
        resolution, reason = resolve_claim(claim, region_by_id)
        claim_sections.append(f'''<section class="claim"><h3>{html.escape(claim["claim_id"])} — {html.escape(resolution)}</h3>
<p>{html.escape(claim["claim_text"])}</p><ul>
<li>Decisive: {claim["decisive"]}; subjects: {html.escape(", ".join(claim["subject_region_ids"]))}</li>
<li>Inspection: <strong>{html.escape(claim["inspection"]["status"])}</strong>; change record: {html.escape(str(claim["inspection"]["change_record_id"]))}</li>
<li>Caption: <strong>{html.escape(claim["caption_corroboration"]["state"])}</strong> — {html.escape(quote_text(claim["caption_corroboration"]["source_anchor"]))}</li>
<li>Body: <strong>{html.escape(claim["body_corroboration"]["state"])}</strong> — {html.escape(quote_text(claim["body_corroboration"]["source_anchor"]))}</li>
<li>Resolution basis: {html.escape(reason)}</li></ul></section>''')
    warning_items = "".join(f'<li><strong>{html.escape(w["code"])} / {html.escape(w["state"])}</strong>: {html.escape(w["message"])}</li>' for w in audit["warnings"]) or "<li>None; actual sight still is not machine-verified.</li>"
    banner = '<div class="synthetic">SYNTHETIC — FICTIONAL EVIDENCE, NOT A REAL PAPER</div>' if atlas["synthetic"] else ""
    return f'''<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Visual Evidence Atlas — {html.escape(atlas["case_id"])}</title>
<style>
body{{font:15px/1.45 system-ui,sans-serif;margin:2rem;color:#18222d;max-width:1200px}}h1,h2,h3{{color:#143d59}}.synthetic{{background:#fff3cd;border:3px solid #b26a00;padding:1rem;font-weight:800;font-size:1.2rem}}.warning{{background:#fff3cd;padding:.6rem}}.page{{position:relative;display:inline-block;max-width:100%;border:2px solid #555}}.page img{{display:block;width:100%;height:auto;max-width:760px}}img.crop{{display:block;max-width:100%;height:auto;border:2px solid #555}}.box{{position:absolute;border:2px solid #e22;box-sizing:border-box;pointer-events:none}}.box b{{position:absolute;background:#fff;color:#a00;font-size:10px;max-width:180px;overflow:hidden}}table{{border-collapse:collapse;width:100%}}th,td{{border:1px solid #aaa;padding:.4rem;vertical-align:top;text-align:left}}th{{background:#e8f0f4}}.claim{{border-left:4px solid #477; padding-left:1rem;margin:1rem 0}}code{{overflow-wrap:anywhere}}footer{{margin-top:2rem;border-top:1px solid #aaa;padding-top:1rem}}
</style></head><body>{banner}<h1>Visual Evidence Atlas</h1>
<p>Case <code>{html.escape(atlas["case_id"])}</code>; validation <strong>{audit["status"]}</strong>.</p>
<p><strong>Machine visual truth verified: false.</strong> {html.escape(audit["machine_visual_truth_note"])}</p>
<p>Coordinates: original-render top-left pixels, [x0,y0,x1,y1], end-exclusive. Colored boxes identify records; original evidence is never replaced.</p>
{''.join(page_sections)}{''.join(crop_sections)}<h2>Region records</h2><table><thead><tr><th>ID</th><th>Page</th><th>Kind</th><th>Identity</th><th>BBox</th><th>Evidence</th><th>Source quote</th></tr></thead><tbody>{''.join(region_rows)}</tbody></table>
<h2>Decisive claims and corroboration</h2>{''.join(claim_sections)}
<h2>Unresolved items and warnings</h2><ul>{warning_items}</ul>
<footer>All inspection statuses are agent attestations with change records, never automatic visual-truth passes. Synthetic fixture: {atlas["synthetic"]}.</footer></body></html>'''


def execute(args, mode):
    atlas = read_json(args.atlas)
    source_text = read_text(args.text_source)
    audit = validate_atlas(atlas, source_text, Path(args.image_root) if args.image_root else None)
    if mode == "validate":
        write_json(args.audit, audit)
        return audit, atlas
    if audit["errors"]:
        if mode == "build":
            write_json(Path(args.output_dir) / "audit_report.json", audit)
        raise AtlasProblem("atlas validation failed: " + "; ".join(audit["errors"]))
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    write_json(output_dir / "audit_report.json", audit)
    write_text(output_dir / "atlas.md", render_markdown(atlas, audit, Path(args.image_root), output_dir))
    write_text(output_dir / "atlas.html", render_html(atlas, audit, Path(args.image_root), output_dir))
    if mode == "build":
        case_contract = read_json(args.case)
        result = build_result(atlas, audit, case_contract)
        write_json(output_dir / "result.json", result)
    return audit, atlas


def parser():
    root = argparse.ArgumentParser(description=__doc__)
    commands = root.add_subparsers(dest="command", required=True)
    validate = commands.add_parser("validate", help="validate records and write audit; nonzero on errors")
    validate.add_argument("--atlas", required=True)
    validate.add_argument("--text-source", required=True)
    validate.add_argument("--image-root")
    validate.add_argument("--audit", required=True)
    for name in ("render", "build"):
        command = commands.add_parser(name, help="validate and render atlas" + (" plus result" if name == "build" else ""))
        command.add_argument("--atlas", required=True)
        command.add_argument("--text-source", required=True)
        command.add_argument("--image-root", required=True)
        command.add_argument("--output-dir", required=True)
        if name == "build":
            command.add_argument("--case", required=True)
    return root


def main(argv=None):
    args = parser().parse_args(argv)
    try:
        audit, _ = execute(args, args.command)
    except AtlasProblem as exc:
        if args.command == "validate" and hasattr(args, "audit"):
            fallback = finish_audit({}, [str(exc)], [], [])
            try:
                write_json(args.audit, fallback)
            except OSError:
                pass
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    print(json.dumps({"status": audit["status"], "errors": len(audit["errors"]), "warnings": len(audit["warnings"]), "machine_visual_truth_verified": False}))
    return 2 if audit["errors"] else 0


if __name__ == "__main__":
    sys.exit(main())
