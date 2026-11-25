#!/usr/bin/env python3
"""Region-backed PDF/text evidence recovery; Python standard library only."""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import math
import re
import shutil
import subprocess
import sys
from collections import Counter
from pathlib import Path

REGION_TYPES = {"prose", "table_row", "figure_panel", "caption"}
STATUSES = {"reported", "read_off_figure", "derived", "not_reported", "noncomparable"}
QUALIFIERS = ("task", "metric", "units", "material", "pollutant", "budget", "dataset_id", "dye_id")
BASE_QUALIFIERS = QUALIFIERS[:6]


class EvidenceError(Exception):
    """A user-actionable evidence or runtime error."""


def load_json(path: Path):
    try:
        with path.open("r", encoding="utf-8") as handle:
            return json.load(handle)
    except FileNotFoundError as exc:
        raise EvidenceError(f"JSON file not found: {path}") from exc
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise EvidenceError(f"Cannot read UTF-8 JSON {path}: {exc}") from exc


def write_json(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8").replace("\r\n", "\n").replace("\r", "\n")
    except FileNotFoundError as exc:
        raise EvidenceError(f"Input document not found: {path}") from exc
    except UnicodeError as exc:
        raise EvidenceError(f"Input document is not valid UTF-8: {path}: {exc}") from exc


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8", newline="\n")


def safe_name(source_document_id: str) -> str:
    stem = re.sub(r"[^A-Za-z0-9_.-]+", "_", source_document_id).strip("._") or "document"
    digest = hashlib.sha256(source_document_id.encode("utf-8")).hexdigest()[:10]
    return f"{stem}-{digest}"


def page_texts(text: str) -> list[str]:
    pages = text.split("\f")
    # Poppler/text exports may put a newline after the terminal page delimiter.
    if len(pages) > 1 and not pages[-1].strip():
        pages.pop()
    return pages or [""]


def documents_of(workorder: dict) -> list[dict]:
    docs = workorder.get("documents")
    if not isinstance(docs, list) or not docs:
        raise EvidenceError("Workorder documents must be a non-empty list.")
    seen = set()
    for doc in docs:
        if not isinstance(doc, dict) or not isinstance(doc.get("source_document_id"), str):
            raise EvidenceError("Every document needs a string source_document_id.")
        docid = doc["source_document_id"]
        if not docid or docid in seen:
            raise EvidenceError(f"Missing or duplicate source_document_id: {docid!r}")
        seen.add(docid)
    return docs


def run_pdftotext(pdf: Path, destination: Path, layout: bool) -> None:
    executable = shutil.which("pdftotext")
    if not executable:
        raise EvidenceError(
            "PDF ingestion requires pdftotext on PATH (Poppler). "
            "No fallback claims PDF fidelity; supply UTF-8 layout text or install Poppler outside this run."
        )
    command = [executable]
    if layout:
        command.append("-layout")
    command.extend(["-enc", "UTF-8", str(pdf), str(destination)])
    destination.parent.mkdir(parents=True, exist_ok=True)
    completed = subprocess.run(command, text=True, capture_output=True, check=False)
    if completed.returncode:
        raise EvidenceError(
            f"pdftotext failed for {pdf} ({'layout' if layout else 'normal'}): "
            f"{completed.stderr.strip() or 'exit ' + str(completed.returncode)}"
        )
    # Deliberately no -nopgbrk: form feeds are the physical-page boundary evidence.


def cmd_ingest(args) -> dict:
    workorder = load_json(Path(args.workorder))
    input_root = Path(args.input_root)
    work = Path(args.work)
    manifest = {"documents": [], "warnings": []}
    for doc in documents_of(workorder):
        docid = doc["source_document_id"]
        relative = doc.get("path")
        if not isinstance(relative, str) or not relative:
            raise EvidenceError(f"Document {docid} needs a source path.")
        source = Path(relative)
        if not source.is_absolute():
            source = input_root / source
        source = source.resolve()
        suffix = source.suffix.lower()
        normal_path = work / "normal" / f"{safe_name(docid)}.txt"
        layout_path = work / "layout" / f"{safe_name(docid)}.txt"
        if suffix in {".txt", ".text", ".md"}:
            text = read_text(source)
            write_text(normal_path, text)
            write_text(layout_path, text)
            method = "utf8_text_dual_stream_copy"
        elif suffix == ".pdf":
            run_pdftotext(source, normal_path, layout=False)
            run_pdftotext(source, layout_path, layout=True)
            method = "pdftotext_normal_and_layout"
        else:
            raise EvidenceError(f"Unsupported document type for {docid}: {source.suffix}; use PDF or UTF-8 text.")
        normal = read_text(normal_path)
        layout = read_text(layout_path)
        normal_pages = page_texts(normal)
        layout_pages = page_texts(layout)
        if len(normal_pages) != len(layout_pages):
            raise EvidenceError(f"Normal/layout page count differs for {docid}; inspect form-feed preservation.")
        manifest["documents"].append({
            "source_document_id": docid,
            "source_path": str(source),
            "source_sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
            "method": method,
            "normal_text": str(normal_path),
            "layout_text": str(layout_path),
            "page_count": len(layout_pages),
            "form_feeds": layout.count("\f"),
        })
    manifest_path = work / "ingest-manifest.json"
    write_json(manifest_path, manifest)
    print(f"Ingested {len(manifest['documents'])} documents; manifest: {manifest_path}")
    return manifest


def header_columns(line: str) -> list[tuple[int, int, str]]:
    """Split a simple whitespace-aligned line at runs of two or more spaces."""
    stripped = line.rstrip("\n")
    matches = list(re.finditer(r"\S(?:.*?\S)?(?=\s{2,}|$)", stripped))
    return [(m.start(), m.end(), m.group(0).strip()) for m in matches]


def cells_at_columns(line: str, columns: list[tuple[int, int, str]]) -> list[str]:
    values = []
    for index, (start, end, _header) in enumerate(columns):
        next_start = columns[index + 1][0] if index + 1 < len(columns) else len(line)
        values.append(line[start:max(end, next_start)].strip())
    return values


def annotation(header: str) -> tuple[list[str], str | None, str | None]:
    sample = None
    sample_match = re.search(r"\{([^{}]+)\}\s*$", header)
    if sample_match:
        sample = sample_match.group(1).strip()
    unit = None
    unit_match = re.search(r"(?:\(([^()]+)\)|\[([^\[\]]+)\])\s*(?:\{[^{}]+\})?\s*$", header)
    if unit_match:
        unit = (unit_match.group(1) or unit_match.group(2)).strip()
    parts = [part.strip() for part in header.split(">") if part.strip()]
    return parts or [header], unit, sample


def parse_layout_text(text: str, docid: str, paragraph_id: str) -> list[dict]:
    """Conservative drafts for simple aligned tables; an agent must verify every draft."""
    regions = []
    table_number = 0
    for page_number, page in enumerate(page_texts(text), start=1):
        lines = page.splitlines()
        index = 0
        while index < len(lines) - 1:
            columns = header_columns(lines[index])
            # ASCII axes/rules are figure geometry, not simple table headers.
            if len(columns) < 2 or not lines[index + 1].strip() or any(mark in lines[index] for mark in ("|", "___", "---")):
                index += 1
                continue
            first_values = cells_at_columns(lines[index + 1], columns)
            if sum(bool(value) for value in first_values) < 2:
                index += 1
                continue
            header_line = lines[index]
            headers = [column[2] for column in columns]
            unit_map, split_map, paths = {}, {}, []
            for header in headers:
                path, unit, sample = annotation(header)
                paths.append(path)
                if unit:
                    unit_map[header] = unit
                if sample:
                    split_map[header] = sample
            table_number += 1
            row_number = 0
            cursor = index + 1
            previous = [""] * len(headers)
            while cursor < len(lines) and lines[cursor].strip():
                raw = lines[cursor]
                values = cells_at_columns(raw, columns)
                if sum(bool(value) for value in values) < 1:
                    break
                carried = {}
                cells = []
                for col_index, (header, value) in enumerate(zip(headers, values)):
                    original = value
                    if not value and previous[col_index]:
                        value = previous[col_index]
                        carried[header] = previous[col_index]
                    path, unit, sample = annotation(header)
                    cells.append({
                        "header": header,
                        "header_path": path,
                        "value": value,
                        "source_value": original,
                        "units": unit,
                        "sample_split": sample,
                        "carried_from_previous_row": header in carried,
                    })
                    if value:
                        previous[col_index] = value
                row_number += 1
                regions.append({
                    "source_document_id": docid,
                    "page": page_number,
                    "region_type": "table_row",
                    "region_id": f"{docid}:table-{table_number:03d}-row-{row_number:03d}",
                    "paragraph_id": paragraph_id,
                    "text": raw.strip(),
                    "table": {
                        "headers": headers,
                        "header_paths": paths,
                        "units": unit_map,
                        "sample_splits": split_map,
                        "header_text": header_line.strip(),
                    },
                    "cells": cells,
                    "multirow_context": carried,
                })
                cursor += 1
            index = max(cursor, index + 1)
    return regions


def cmd_parse_layout(args) -> dict:
    source = Path(args.input)
    text = read_text(source)
    regions = parse_layout_text(text, args.source_document_id, args.paragraph_id)
    payload = {
        "source_document_id": args.source_document_id,
        "paragraph_id": args.paragraph_id,
        "regions": regions,
        "warning": "Draft geometry only: verify headers, multirow context, page and IDs before use.",
    }
    destination = Path(args.output)
    write_json(destination, payload)
    print(f"Drafted {len(regions)} table-row regions: {destination}")
    return payload


def parse_pages(spec: str) -> list[int]:
    pages = set()
    for part in spec.split(","):
        part = part.strip()
        match = re.fullmatch(r"(\d+)(?:-(\d+))?", part)
        if not match:
            raise EvidenceError(f"Invalid page specification {part!r}; use 1,3,5-7.")
        start = int(match.group(1))
        end = int(match.group(2) or start)
        if start < 1 or end < start:
            raise EvidenceError(f"Invalid physical page range: {part}")
        pages.update(range(start, end + 1))
    return sorted(pages)


def cmd_render_pages(args) -> list[str]:
    executable = shutil.which("pdftoppm")
    if not executable:
        raise EvidenceError("PDF page rendering requires pdftoppm on PATH (Poppler); no page image was created.")
    pdf = Path(args.pdf)
    if not pdf.is_file():
        raise EvidenceError(f"PDF not found: {pdf}")
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    created = []
    for page in parse_pages(args.pages):
        prefix = output_dir / f"page-{page:04d}"
        command = [executable, "-f", str(page), "-l", str(page), "-singlefile", "-r", str(args.dpi), "-png", str(pdf), str(prefix)]
        completed = subprocess.run(command, text=True, capture_output=True, check=False)
        if completed.returncode:
            raise EvidenceError(f"pdftoppm failed for {pdf} page {page}: {completed.stderr.strip()}")
        image = prefix.with_suffix(".png")
        if not image.is_file():
            raise EvidenceError(f"pdftoppm reported success but did not create {image}")
        created.append(str(image))
        print(image)
    print("Inspect these images visually/OCR as needed; record paths and uncertainty in the workorder.")
    return created


def is_number(value) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def has_number(value) -> bool:
    # Catch plain numbers and suffixed/prefixed numeric claims such as "48%", "~48" or "2-fold".
    return is_number(value) or (isinstance(value, str) and bool(re.search(r"(?:\d+(?:\.\d*)?|\.\d+)(?:[Ee][+-]?\d+)?", value.strip())))


def _qualifier(record: dict, key: str):
    value = record.get(key)
    if isinstance(value, str):
        return value.strip()
    return value


def _missing_qualifier(value) -> bool:
    return value is None or (isinstance(value, str) and (not value.strip() or value.strip().lower() in {"not_reported", "unknown", "n/a"}))


def validate_workorder(case: dict, workorder: dict, manifest: dict | None = None) -> dict:
    if not isinstance(workorder, dict):
        raise EvidenceError("Workorder must be a JSON object.")
    docs = documents_of(workorder)
    if case.get("case_id") is None:
        raise EvidenceError("case.json needs case_id.")
    if "output_contract" not in case:
        raise EvidenceError("case.json needs output_contract.")
    contract_keys(workorder_contract=case["output_contract"])  # shape check only

    page_counts = {}
    if manifest:
        for item in manifest.get("documents", []):
            page_counts[item.get("source_document_id")] = item.get("page_count")

    regions = {}
    prose_regions = {}
    all_regions = []
    for doc in docs:
        docid = doc["source_document_id"]
        doc_regions = doc.get("regions")
        if not isinstance(doc_regions, list) or not doc_regions:
            raise EvidenceError(f"{docid}: regions must be a non-empty list.")
        for region in doc_regions:
            label = f"{docid} region"
            if not isinstance(region, dict) or region.get("source_document_id") != docid:
                raise EvidenceError(f"{label}: exact source_document_id is required.")
            page = region.get("page")
            if not isinstance(page, int) or isinstance(page, bool) or page < 1:
                raise EvidenceError(f"{label}: page must be a positive physical-page integer.")
            if docid in page_counts and page > page_counts[docid]:
                raise EvidenceError(f"{label}: page {page} exceeds ingested page count {page_counts[docid]}.")
            kind = region.get("region_type")
            if kind not in REGION_TYPES:
                raise EvidenceError(f"{label}: region_type must be one of {sorted(REGION_TYPES)}.")
            paragraph_id = region.get("paragraph_id")
            if not isinstance(paragraph_id, str) or not paragraph_id:
                raise EvidenceError(f"{label}: stable paragraph_id linking prose/caption/context is required.")
            region_id = region.get("region_id")
            if kind == "prose":
                if region_id not in (None, ""):
                    raise EvidenceError(f"{label}: prose uses paragraph_id, not region_id.")
                prose_regions.setdefault((docid, paragraph_id), []).append(region)
            else:
                if not isinstance(region_id, str) or not region_id:
                    raise EvidenceError(f"{label}: nonprose evidence needs a stable region_id.")
                key = (docid, region_id)
                if key in regions:
                    raise EvidenceError(f"Duplicate region ID: {docid} / {region_id}")
                regions[key] = region
            if not isinstance(region.get("text"), str) or not region.get("text").strip():
                raise EvidenceError(f"{label}: exact region text is required.")
            if kind == "table_row":
                table = region.get("table")
                cells = region.get("cells")
                if not isinstance(table, dict) or not isinstance(table.get("headers"), list) or not table["headers"]:
                    raise EvidenceError(f"{label} {region_id}: table.headers is required.")
                for name in ("header_paths", "units", "sample_splits"):
                    if name not in table:
                        raise EvidenceError(f"{label} {region_id}: table.{name} must be recorded (empty if absent).")
                if not isinstance(cells, list) or len(cells) != len(table["headers"]):
                    raise EvidenceError(f"{label} {region_id}: cells must align with all table headers.")
                for cell in cells:
                    if not isinstance(cell, dict) or not cell.get("header_path") or "value" not in cell or "units" not in cell or "sample_split" not in cell:
                        raise EvidenceError(f"{label} {region_id}: every cell needs header_path, value, units and sample_split.")
                    if cell.get("carried_from_previous_row") and cell["value"] not in region.get("multirow_context", {}).values():
                        raise EvidenceError(f"{label} {region_id}: carried multirow value lacks multirow_context.")
            if kind == "figure_panel" and (not isinstance(region.get("panel_labels"), list) or not region["panel_labels"]):
                raise EvidenceError(f"{label} {region_id}: figure panel_labels are required.")
            all_regions.append(region)

    records = {}
    doc_records = {doc["source_document_id"]: [] for doc in docs}
    readoff_visuals = []
    for doc in docs:
        docid = doc["source_document_id"]
        extractions = doc.get("extractions")
        if not isinstance(extractions, list):
            raise EvidenceError(f"{docid}: extractions must be a list (empty allowed only without matrix requirements).")
        for record in extractions:
            if not isinstance(record, dict) or record.get("source_document_id") != docid:
                raise EvidenceError(f"{docid} extraction: exact source_document_id is required.")
            record_id = record.get("record_id")
            if not isinstance(record_id, str) or not record_id or record_id in records:
                raise EvidenceError(f"{docid}: each extraction needs a globally unique record_id.")
            if not isinstance(record.get("field_id"), str) or not record["field_id"]:
                raise EvidenceError(f"{docid}/{record_id}: field_id is required.")
            paragraph_id = record.get("paragraph_id")
            if not isinstance(paragraph_id, str) or not paragraph_id:
                raise EvidenceError(f"{docid}/{record_id}: exact paragraph_id is required.")
            region_id = record.get("region_id")
            if region_id:
                region = regions.get((docid, region_id))
                if not region:
                    raise EvidenceError(f"{docid}/{record_id}: missing region {region_id!r}.")
                if region["paragraph_id"] != paragraph_id:
                    raise EvidenceError(f"{docid}/{record_id}: paragraph_id does not match its region caption/context.")
            else:
                candidates = prose_regions.get((docid, paragraph_id), [])
                if len(candidates) != 1:
                    raise EvidenceError(f"{docid}/{record_id}: prose extraction must resolve to exactly one paragraph region.")
                region = candidates[0]
            status = record.get("status")
            if status not in STATUSES:
                raise EvidenceError(f"{docid}/{record_id}: status must be one of {sorted(STATUSES)}.")
            for key in BASE_QUALIFIERS:
                if key not in record:
                    raise EvidenceError(f"{docid}/{record_id}: qualifier {key} must be explicit, even if not_reported.")
            numeric = any(has_number(record.get(key)) for key in ("value", "estimate"))
            numeric = numeric or (isinstance(record.get("range"), list) and any(has_number(v) for v in record["range"]))
            if numeric:
                missing = [key for key in BASE_QUALIFIERS if _missing_qualifier(_qualifier(record, key))]
                if missing:
                    raise EvidenceError(f"{docid}/{record_id}: quantitative synthesis blocked; missing qualifiers {missing}.")
            if region["region_type"] == "caption" and numeric:
                raise EvidenceError(f"{docid}/{record_id}: caption-only numeric claim is forbidden; captions provide context, not curve values.")
            if status == "read_off_figure":
                if region["region_type"] != "figure_panel":
                    raise EvidenceError(f"{docid}/{record_id}: read_off_figure must point to a figure_panel region.")
                if record.get("value") is not None:
                    raise EvidenceError(f"{docid}/{record_id}: figure read-off cannot be stored as exact value; use estimate/range.")
                estimate_ok = has_number(record.get("estimate"))
                value_range = record.get("range")
                range_ok = isinstance(value_range, list) and len(value_range) == 2 and all(has_number(v) for v in value_range)
                if not (estimate_ok or range_ok):
                    raise EvidenceError(f"{docid}/{record_id}: figure read-off needs estimate and/or two-ended range.")
                if not range_ok and not isinstance(record.get("uncertainty"), dict):
                    raise EvidenceError(f"{docid}/{record_id}: estimate-only read-off needs an uncertainty object.")
                if not isinstance(record.get("uncertainty"), dict) or not record["uncertainty"].get("note"):
                    raise EvidenceError(f"{docid}/{record_id}: figure read-off needs explicit uncertainty.note.")
                visual = record.get("visual_inspection")
                if not isinstance(visual, dict) or not isinstance(visual.get("paths"), list) or not visual["paths"]:
                    raise EvidenceError(f"{docid}/{record_id}: visual_inspection.paths must identify inspected page image or synthetic layout text.")
                if not visual.get("method") or not visual.get("notes"):
                    raise EvidenceError(f"{docid}/{record_id}: visual_inspection method and notes are required.")
                readoff_visuals.append((record, region))
            elif region["region_type"] == "figure_panel" and (numeric or status == "reported"):
                raise EvidenceError(f"{docid}/{record_id}: figure-panel numbers must be read_off_figure estimates/ranges, never exact reported values.")
            if status in {"not_reported", "noncomparable"}:
                if any(record.get(key) is not None for key in ("value", "estimate", "range")):
                    raise EvidenceError(f"{docid}/{record_id}: {status} must preserve null value/estimate/range.")
                if not record.get("reason"):
                    raise EvidenceError(f"{docid}/{record_id}: {status} needs an honest reason.")
            if status == "derived":
                if not is_number(record.get("value")) or not record.get("derivation"):
                    raise EvidenceError(f"{docid}/{record_id}: derived record needs numeric value and derivation expression.")
                if not isinstance(record.get("derived_from"), list) or not record["derived_from"]:
                    raise EvidenceError(f"{docid}/{record_id}: derived record needs derived_from record IDs.")
            records[record_id] = record
            doc_records[docid].append(record)

    for record in list(records.values()):
        if record["status"] != "derived":
            continue
        for key in BASE_QUALIFIERS:
            if _missing_qualifier(_qualifier(record, key)):
                raise EvidenceError(f"{record['record_id']}: derived quantitative record lacks {key}.")
        sources = []
        for source_id in record["derived_from"]:
            source = records.get(source_id)
            if not source:
                raise EvidenceError(f"{record['record_id']}: derived_from missing record {source_id}.")
            if source["status"] not in {"reported", "derived"} or not is_number(source.get("value")):
                raise EvidenceError(f"{record['record_id']}: cannot derive from nonnumeric/non-reported {source_id}.")
            sources.append(source)
        mismatches = [key for key in QUALIFIERS if any(_qualifier(src, key) != _qualifier(record, key) for src in sources)]
        if mismatches:
            raise EvidenceError(f"{record['record_id']}: incompatible derived quantitative inputs: {mismatches}; no unit conversion or pooling applied.")
        if len(sources) > 1:
            for key in ("dataset_id", "dye_id"):
                if _missing_qualifier(_qualifier(record, key)):
                    raise EvidenceError(f"{record['record_id']}: multi-input derivation requires known {key}; unlike datasets/dyes cannot be pooled.")

    matrix_fields = field_list(workorder)
    for doc in docs:
        docid = doc["source_document_id"]
        present = {record["field_id"] for record in doc_records[docid]}
        missing = [field for field in matrix_fields if field not in present]
        if missing:
            raise EvidenceError(f"{docid}: matrix fields missing explicit records (use not_reported/noncomparable): {missing}.")
    return {"documents": docs, "regions": all_regions, "records": records, "readoff_visuals": readoff_visuals}


def contract_keys(workorder_contract) -> list[tuple[str, object]]:
    """Accept output_contract as a dict, string list, or descriptor list."""
    pairs = []
    if isinstance(workorder_contract, dict):
        pairs = list(workorder_contract.items())
    elif isinstance(workorder_contract, list):
        for item in workorder_contract:
            if isinstance(item, str) and item:
                pairs.append((item, None))
            elif isinstance(item, dict):
                identifier = next((item.get(key) for key in ("name", "field", "field_id", "key", "id") if isinstance(item.get(key), str) and item.get(key)), None)
                if identifier:
                    pairs.append((identifier, item))
                else:
                    for key, value in item.items():
                        if isinstance(key, str):
                            pairs.append((key, value))
            else:
                raise EvidenceError("output_contract list entries must be strings or objects.")
    else:
        raise EvidenceError("output_contract must be a list or object.")
    keys = [key for key, _ in pairs]
    if not keys or len(set(keys)) != len(keys) or any(not isinstance(key, str) or not key for key in keys):
        raise EvidenceError("output_contract must yield nonempty unique string field names.")
    return pairs


def field_list(workorder: dict) -> list[str]:
    raw = workorder.get("matrix_fields")
    if raw is None:
        raw = sorted({record["field_id"] for doc in workorder["documents"] for record in doc.get("extractions", [])})
    pairs = contract_keys(raw)
    return [key for key, _ in pairs]


def markdown(value) -> str:
    if value is None or value == "":
        return "—"
    if isinstance(value, (dict, list)):
        value = json.dumps(value, ensure_ascii=False, separators=(",", ":"))
    return str(value).replace("|", "\\|").replace("\n", "<br>").replace("\f", "<form-feed>")


def markdown_table(headers: list[str], rows: list[list[object]]) -> str:
    lines = ["| " + " | ".join(headers) + " |", "| " + " | ".join("---" for _ in headers) + " |"]
    lines.extend("| " + " | ".join(markdown(cell) for cell in row) + " |" for row in rows)
    return "\n".join(lines) + "\n"


def render_matrix(workorder: dict, fields: list[str]) -> str:
    lines = [
        "# Comparison matrix\n",
        "One row per source region/extraction record. No pooling, unit conversion, or unlike dataset/dye merging is performed. "
        "`not_reported` and `noncomparable` are preserved.\n",
    ]
    headers = ["field_id", "source_document_id", "paragraph_id", "region_id", "page", "region_type", "record_id", "task", "metric", "units", "material", "pollutant", "budget", "dataset_id", "dye_id", "status", "value_or_estimate", "reason_or_uncertainty"]
    rows = []
    for field in fields:
        for doc in workorder["documents"]:
            docid = doc["source_document_id"]
            matching = [r for r in doc["extractions"] if r["field_id"] == field]
            region_lookup = {r.get("region_id"): r for r in doc["regions"] if r.get("region_id")}
            prose_lookup = {r["paragraph_id"]: r for r in doc["regions"] if r["region_type"] == "prose"}
            for record in matching:
                region = region_lookup.get(record.get("region_id")) if record.get("region_id") else prose_lookup[record["paragraph_id"]]
                status = record["status"]
                if status == "read_off_figure":
                    value = {"estimate": record.get("estimate"), "range": record.get("range"), "units": record.get("units")}
                else:
                    value = record.get("value") if record.get("value") is not None else status
                caveat = record.get("reason") or record.get("uncertainty") or record.get("derivation") or ""
                rows.append([field, docid, record["paragraph_id"], record.get("region_id"), region["page"], region["region_type"], record["record_id"], record.get("task"), record.get("metric"), record.get("units"), record.get("material"), record.get("pollutant"), record.get("budget"), record.get("dataset_id"), record.get("dye_id"), status, value, caveat])
    lines.append(markdown_table(headers, rows))
    return "\n".join(lines)


def render_regions(workorder: dict) -> str:
    lines = [
        "# Source-region evidence ledger\n",
        "Physical pages are one-indexed. Prose is keyed by `paragraph_id`; nonprose uses `region_id` plus `paragraph_id` for caption/context linkage. "
        "Table drafts and figure read-offs require scientific verification; captions are context only.\n",
    ]
    headers = ["source_document_id", "page", "region_type", "region_id", "paragraph_id", "header_path_units_sample_split", "multirow_cell_context", "panel_labels", "region_text"]
    rows = []
    for doc in workorder["documents"]:
        for region in doc["regions"]:
            table_context = None
            if region["region_type"] == "table_row":
                table_context = {
                    "headers": region["table"]["headers"],
                    "header_paths": region["table"]["header_paths"],
                    "units": region["table"]["units"],
                    "sample_splits": region["table"]["sample_splits"],
                    "cells": region["cells"],
                }
            rows.append([region["source_document_id"], region["page"], region["region_type"], region.get("region_id"), region["paragraph_id"], table_context, region.get("multirow_context"), region.get("panel_labels"), region["text"]])
    lines.append(markdown_table(headers, rows))
    return "\n".join(lines)


def default_result_value(key: str, workorder: dict, counts: Counter):
    if key in {"comparison_matrix", "comparison-matrix", "matrix"}:
        return "comparison-matrix.md"
    if key in {"source_region_ledger", "source_regions", "region_ledger", "source-regions"}:
        return "source-regions.md"
    if key == "status":
        return workorder.get("status", "partial")
    if key == "sources":
        return copy.deepcopy(workorder.get("sources", []))
    if key == "uncertainty":
        return copy.deepcopy(workorder.get("uncertainty", []))
    if key == "change_records":
        return copy.deepcopy(workorder.get("change_records", []))
    if key == "quality_summary":
        return {"document_count": len(workorder["documents"]), "extraction_status_counts": dict(sorted(counts.items()))}
    return None


def cmd_validate(args) -> dict:
    case = load_json(Path(args.case))
    workorder = load_json(Path(args.workorder))
    manifest = load_json(Path(args.manifest)) if args.manifest else None
    checked = validate_workorder(case, workorder, manifest)
    print(f"VALID: {len(checked['documents'])} documents, {len(checked['regions'])} regions, {len(checked['records'])} extraction records.")
    return checked


def cmd_render(args) -> dict:
    case = load_json(Path(args.case))
    workorder = load_json(Path(args.workorder))
    manifest = load_json(Path(args.manifest)) if args.manifest else None
    checked = validate_workorder(case, workorder, manifest)
    output = Path(args.output)
    output.mkdir(parents=True, exist_ok=True)
    matrix_path = output / "comparison-matrix.md"
    regions_path = output / "source-regions.md"
    matrix_path.write_text(render_matrix(workorder, field_list(workorder)), encoding="utf-8")
    regions_path.write_text(render_regions(workorder), encoding="utf-8")

    counts = Counter(record["status"] for record in checked["records"].values())
    explicit = workorder.get("result_fields", {})
    if not isinstance(explicit, dict):
        raise EvidenceError("result_fields must be an object when present.")
    result = {"case_id": case["case_id"]}
    contract_pairs = contract_keys(case["output_contract"])
    for key, _spec in contract_pairs:
        result[key] = copy.deepcopy(explicit[key]) if key in explicit else default_result_value(key, workorder, counts)
    # Provenance fields are mandatory even when a minimal output_contract omitted them.
    for key in ("status", "sources", "uncertainty", "change_records"):
        if key not in result:
            result[key] = default_result_value(key, workorder, counts)

    # Ensure visual inspection traces reach result.json even if omitted from optional contract fields.
    visual_entries = []
    for record, region in checked["readoff_visuals"]:
        visual_entries.append({
            "source_document_id": record["source_document_id"],
            "paragraph_id": record["paragraph_id"],
            "region_id": region["region_id"],
            "record_id": record["record_id"],
            "visual_inspection": copy.deepcopy(record["visual_inspection"]),
        })
        source_trace = json.dumps(result["sources"], ensure_ascii=False)
        change_trace = json.dumps(result["change_records"], ensure_ascii=False)
        for path in record["visual_inspection"]["paths"]:
            if path not in source_trace and isinstance(result["sources"], list):
                result["sources"].append({"source_document_id": record["source_document_id"], "region_id": region["region_id"], "path": path, "type": "visual_inspection"})
            if path not in change_trace and isinstance(result["change_records"], list):
                result["change_records"].append({"action": "visual_inspection", "region_id": region["region_id"], "record_id": record["record_id"], "paths": [path]})
        if record["record_id"] not in json.dumps(result["uncertainty"], ensure_ascii=False) and isinstance(result["uncertainty"], list):
            result["uncertainty"].append({"record_id": record["record_id"], "estimate": record.get("estimate"), "range": record.get("range"), "uncertainty": copy.deepcopy(record["uncertainty"])})
    result["artifacts"] = {"comparison_matrix": matrix_path.name, "source_region_ledger": regions_path.name}
    result["visual_inspection_index"] = visual_entries
    result["validation"] = {"status": "passed", "region_count": len(checked["regions"]), "extraction_count": len(checked["records"]), "pooling_performed": False}
    result_path = output / "result.json"
    write_json(result_path, result)
    unpopulated = [key for key, _ in contract_pairs if key not in explicit and default_result_value(key, workorder, counts) is None]
    if unpopulated:
        print(f"WARNING: contract fields have no workorder result_fields value and remain null: {', '.join(unpopulated)}", file=sys.stderr)
    print(f"Rendered {matrix_path}, {regions_path}, and {result_path}")
    return result


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    ingest = sub.add_parser("ingest", help="Create normal/layout UTF-8 text streams with form feeds preserved.")
    ingest.add_argument("--workorder", default="/input/comparison-workorder.json")
    ingest.add_argument("--input-root", default="/input")
    ingest.add_argument("--work", default="/app/work")
    ingest.set_defaults(func=cmd_ingest)

    parse = sub.add_parser("parse-layout", help="Draft simple aligned table rows with header and multirow context.")
    parse.add_argument("--input", required=True)
    parse.add_argument("--source-document-id", required=True)
    parse.add_argument("--paragraph-id", required=True)
    parse.add_argument("--output", required=True)
    parse.set_defaults(func=cmd_parse_layout)

    pages = sub.add_parser("render-pages", help="Render selected physical PDF pages to PNG with pdftoppm.")
    pages.add_argument("--pdf", required=True)
    pages.add_argument("--pages", required=True, help="One-indexed physical pages, e.g. 1,3,5-7")
    pages.add_argument("--output-dir", default="/app/work/page-images")
    pages.add_argument("--dpi", default="180", type=int)
    pages.set_defaults(func=cmd_render_pages)

    for name, function in (("validate", cmd_validate), ("render", cmd_render)):
        command = sub.add_parser(name, help=f"{name.capitalize()} region-backed extraction records and outputs.")
        command.add_argument("--case", default="/input/case.json")
        command.add_argument("--workorder", default="/input/comparison-workorder.json")
        command.add_argument("--manifest", default=None)
        command.set_defaults(func=function)
        if name == "render":
            command.add_argument("--output", default="/app/output")
    return parser


def main(argv=None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        args.func(args)
        return 0
    except EvidenceError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
