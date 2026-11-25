#!/usr/bin/env python3
"""Deterministic, standard-library source-span atlas validation and simple SVG rendering."""
from __future__ import annotations

import csv
import hashlib
import json
import math
import os
from pathlib import Path
import re
import unicodedata
import xml.etree.ElementTree as ET
from xml.sax.saxutils import escape, quoteattr

SCHEMA_VERSION = "source-span-atlas/1.0"
ALLOWED_CATEGORIES = {"entity", "connection", "step", "stage", "data", "note"}
ALLOWED_EVIDENCE = {"explicit", "inferred", "unsupported"}
ID_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_.-]*$")


class AtlasError(Exception):
    """An input or artifact validation error."""


def canonical_json(value):
    return json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def sha256_bytes(data):
    return hashlib.sha256(data).hexdigest()


def read_utf8(path):
    data = Path(path).read_bytes()
    if data.startswith(b"\xef\xbb\xbf"):
        data = data[3:]
    if b"\x00" in data:
        raise AtlasError("NUL byte in UTF-8 text: %s" % path)
    try:
        return data.decode("utf-8"), data
    except UnicodeDecodeError as exc:
        raise AtlasError("Not UTF-8: %s: %s" % (path, exc)) from exc


def normalize_with_map(text):
    """NFKC + quote/dash canonicalization + whitespace folding, retaining source offsets.

    This is deliberately not fuzzy matching, stemming, OCR correction, or dehyphenation.
    Every returned normalized character maps to a half-open span in the original text.
    """
    chars, starts, ends = [], [], []
    pending_space = None
    translations = {
        "\u2018": "'", "\u2019": "'", "\u201a": "'", "\u201b": "'",
        "\u201c": '"', "\u201d": '"', "\u201e": '"', "\u201f": '"',
        "\u2010": "-", "\u2011": "-", "\u2012": "-", "\u2013": "-",
        "\u2014": "-", "\u2015": "-", "\u2212": "-",
    }

    def emit(piece, start, end):
        nonlocal pending_space
        if piece.isspace():
            if chars and pending_space is None:
                pending_space = (start, end)
            return
        piece = translations.get(piece, piece)
        if pending_space is not None:
            chars.append(" ")
            starts.append(pending_space[0])
            ends.append(pending_space[1])
            pending_space = None
        for subchar in piece:
            chars.append(subchar)
            starts.append(start)
            ends.append(end)

    for index, original in enumerate(text):
        expanded = unicodedata.normalize("NFKC", original)
        for character in expanded:
            emit(character, index, index + 1)
    return "".join(chars), starts, ends


def normalize_text(text):
    return normalize_with_map(text)[0]


def line_number(text, offset):
    return text.count("\n", 0, offset) + 1


def page_number(text, offset):
    return text.count("\f", 0, offset) + 1


class Reporter:
    def __init__(self):
        self.errors = []
        self.warnings = []

    def error(self, code, message, assertion_id=None):
        item = {"code": code, "message": message}
        if assertion_id:
            item["assertion_id"] = assertion_id
        self.errors.append(item)

    def warning(self, code, message):
        self.warnings.append({"code": code, "message": message})


def _resolve_source_path(atlas_dir, declared):
    path = Path(declared)
    return path.resolve() if path.is_absolute() else (atlas_dir / path).resolve()


def load_sources(spec, atlas_dir, reporter):
    loaded = {}
    source_records = []
    for index, source in enumerate(spec.get("sources", [])):
        if not isinstance(source, dict):
            reporter.error("SOURCE_TYPE", "sources[%d] must be an object" % index)
            continue
        source_id = source.get("source_id")
        if not isinstance(source_id, str) or not ID_RE.match(source_id):
            reporter.error("SOURCE_ID", "Invalid or missing source_id at sources[%d]" % index)
            continue
        if source_id in loaded:
            reporter.error("SOURCE_ID_DUPLICATE", "Duplicate source_id: %s" % source_id)
            continue
        declared = source.get("path")
        if not isinstance(declared, str) or not declared:
            reporter.error("SOURCE_PATH", "Missing path for source %s" % source_id)
            continue
        path = _resolve_source_path(atlas_dir, declared)
        try:
            text, raw = read_utf8(path)
        except (OSError, AtlasError) as exc:
            reporter.error("SOURCE_READ", "%s: %s" % (source_id, exc))
            continue
        digest = sha256_bytes(raw)
        expected_hash = source.get("sha256")
        if expected_hash and expected_hash != digest:
            reporter.error("SOURCE_HASH", "Source hash changed for %s" % source_id)
        kind = source.get("kind", "text")
        if kind not in {"methods", "text", "figure", "csv"}:
            reporter.error("SOURCE_KIND", "Unsupported source kind for %s: %s" % (source_id, kind))
        visual_path = None
        visual_sha256 = None
        visual_bytes = None
        if kind == "figure" and source.get("visual_path"):
            visual_path = _resolve_source_path(atlas_dir, source["visual_path"])
            try:
                visual_raw = Path(visual_path).read_bytes()
                if not visual_raw:
                    raise AtlasError("Empty original visual")
                visual_sha256 = sha256_bytes(visual_raw)
                visual_bytes = len(visual_raw)
                declared_visual_hash = source.get("visual_sha256")
                if declared_visual_hash and declared_visual_hash != visual_sha256:
                    reporter.error("VISUAL_HASH", "Original visual hash changed for %s" % source_id)
            except (OSError, AtlasError) as exc:
                reporter.error("VISUAL_READ", "%s: %s" % (source_id, exc))
        if kind == "csv":
            try:
                rows, headers = read_csv_data(path)
            except (OSError, AtlasError, csv.Error) as exc:
                reporter.error("CSV_READ", "%s: %s" % (source_id, exc))
                rows, headers = [], []
            loaded[source_id] = {"spec": source, "path": path, "text": text,
                                 "raw": raw, "sha256": digest, "rows": rows, "headers": headers}
        else:
            normalized, starts, ends = normalize_with_map(text)
            loaded[source_id] = {"spec": source, "path": path, "text": text, "raw": raw,
                                 "sha256": digest, "normalized": normalized,
                                 "starts": starts, "ends": ends}
        loaded[source_id]["visual_path"] = visual_path
        loaded[source_id]["visual_sha256"] = visual_sha256
        source_records.append({
            "source_id": source_id, "declared_path": declared, "kind": kind,
            "sha256": digest, "bytes": len(raw), "version": source.get("version", "unspecified"),
            "role": source.get("role", "source evidence"),
            "visual_declared_path": source.get("visual_path"),
            "visual_sha256": visual_sha256, "visual_bytes": visual_bytes,
            "original_pdf_page_offset": source.get("original_pdf_page_offset", 0),
        })
    if not isinstance(spec.get("sources"), list) or not spec.get("sources"):
        reporter.error("SOURCES_REQUIRED", "At least one source is required")
    return loaded, source_records


def read_csv_data(path):
    text, _ = read_utf8(path)
    reader = csv.DictReader(text.splitlines())
    headers = reader.fieldnames
    if not headers or any(not h for h in headers):
        raise AtlasError("CSV must have named columns")
    if len(headers) != len(set(headers)):
        raise AtlasError("CSV column names must be unique")
    rows = []
    for row_number, row in enumerate(reader, start=2):
        if None in row or any(value is None for value in row.values()):
            raise AtlasError("Ragged CSV row %d" % row_number)
        if not any(str(value).strip() for value in row.values()):
            continue
        row["__source_row__"] = row_number
        rows.append(row)
    if not rows:
        raise AtlasError("CSV has no data rows")
    return rows, list(headers)


def match_evidence(evidence, source, reporter, assertion_id):
    quote = evidence.get("quote")
    if not isinstance(quote, str) or not quote.strip():
        reporter.error("QUOTE_REQUIRED", "Evidence needs a non-empty quote", assertion_id)
        return None
    normalized_quote = normalize_with_map(quote)[0]
    if not normalized_quote:
        reporter.error("QUOTE_EMPTY_AFTER_NORMALIZATION", "Quote is only whitespace", assertion_id)
        return None
    haystack = source["normalized"]
    first = haystack.find(normalized_quote)
    if first < 0:
        reporter.error("NORMALIZED_QUOTE_NOT_FOUND", "Exact normalized quote was not found in %s" % source["spec"]["source_id"], assertion_id)
        return None
    second = haystack.find(normalized_quote, first + 1)
    if second >= 0:
        reporter.error("QUOTE_AMBIGUOUS", "Quote is not unique; add surrounding source context", assertion_id)
        return None
    nstart, nend = first, first + len(normalized_quote)
    start = source["starts"][nstart]
    end = source["ends"][nend - 1]
    original = source["text"][start:end]
    computed_page = page_number(source["text"], start)
    computed_lines = [line_number(source["text"], start), line_number(source["text"], max(start, end - 1))]
    locator = evidence.get("locator")
    if not isinstance(locator, dict):
        reporter.error("LOCATOR_REQUIRED", "Evidence locator object required", assertion_id)
        locator = {}
    if locator.get("page") != computed_page:
        reporter.error("PAGE_MISMATCH", "Locator page %r does not match form-feed-derived page %d" % (locator.get("page"), computed_page), assertion_id)
    if not any(isinstance(locator.get(key), str) and locator.get(key).strip() for key in ("section", "figure")):
        reporter.error("SECTION_OR_FIGURE_REQUIRED", "Locator needs a non-empty section or figure", assertion_id)
    if "line_start" in locator and locator.get("line_start") != computed_lines[0]:
        reporter.error("LINE_MISMATCH", "line_start does not match source span", assertion_id)
    if "line_end" in locator and locator.get("line_end") != computed_lines[1]:
        reporter.error("LINE_MISMATCH", "line_end does not match source span", assertion_id)
    return {
        "source_id": source["spec"]["source_id"], "quote": quote,
        "normalized_quote": normalized_quote,
        "original_source_excerpt": original,
        "source_span_code_points": [start, end],
        "normalized_span": [nstart, nend],
        "page": computed_page, "line_start": computed_lines[0], "line_end": computed_lines[1],
        "locator": locator, "source_sha256": source["sha256"],
        "match_rule": "unique substring after NFKC, canonical quotes/dashes, folded whitespace; no fuzzy match",
    }


def validate_figure_reviews(spec, sources, reporter):
    reviews = {}
    records = []
    for item in spec.get("figure_reviews", []) or []:
        review_id = item.get("figure_review_id") if isinstance(item, dict) else None
        source_id = item.get("source_id") if isinstance(item, dict) else None
        if not isinstance(review_id, str) or not review_id:
            reporter.error("FIGURE_REVIEW_ID", "Figure review needs figure_review_id")
            continue
        if review_id in reviews:
            reporter.error("FIGURE_REVIEW_DUPLICATE", "Duplicate figure review %s" % review_id)
            continue
        reviews[review_id] = item
        if source_id not in sources or sources[source_id]["spec"].get("kind") != "figure":
            reporter.error("FIGURE_REVIEW_SOURCE", "Figure review %s does not name a figure source" % review_id)
            continue
        if item.get("inspection_mode") != "direct_visual":
            reporter.error("FIGURE_NOT_VISUALLY_INSPECTED", "Figure review %s must use inspection_mode=direct_visual" % review_id)
        if not item.get("inspected_panels"):
            reporter.error("FIGURE_PANELS_REQUIRED", "Figure review %s needs inspected_panels" % review_id)
        if not isinstance(item.get("comparison"), str) or not item.get("comparison").strip():
            reporter.error("FIGURE_COMPARISON_REQUIRED", "Figure review %s needs a semantic comparison" % review_id)
        actual_hash = sources[source_id].get("visual_sha256") or sources[source_id]["sha256"]
        if item.get("reviewed_sha256") != actual_hash:
            reporter.error("FIGURE_REVIEW_HASH", "Figure review %s does not cover the actual source bytes" % review_id)
        records.append(dict(item, actual_sha256=actual_hash))
    return reviews, records


def validate_assertions(spec, sources, figure_reviews, reporter):
    assertions = spec.get("assertions")
    if not isinstance(assertions, list) or not assertions:
        reporter.error("ASSERTIONS_REQUIRED", "At least one assertion is required")
        return [], {}
    records, by_id, visual_ids = [], {}, {}
    for index, assertion in enumerate(assertions):
        if not isinstance(assertion, dict):
            reporter.error("ASSERTION_TYPE", "assertions[%d] must be an object" % index)
            continue
        assertion_id = assertion.get("id")
        if not isinstance(assertion_id, str) or not ID_RE.match(assertion_id):
            reporter.error("ASSERTION_ID", "Invalid assertion id at index %d" % index)
            continue
        if assertion_id in by_id:
            reporter.error("ASSERTION_DUPLICATE", "Duplicate assertion id %s" % assertion_id)
            continue
        by_id[assertion_id] = assertion
        category = assertion.get("category")
        if category not in ALLOWED_CATEGORIES:
            reporter.error("CATEGORY", "Invalid category %r" % category, assertion_id)
        label = assertion.get("label")
        if not isinstance(label, str) or not label.strip():
            reporter.error("LABEL_REQUIRED", "A visible label is required", assertion_id)
        evidence_status = assertion.get("evidence_status")
        if evidence_status not in ALLOWED_EVIDENCE:
            reporter.error("EVIDENCE_STATUS", "Use explicit, inferred, or unsupported", assertion_id)
        if evidence_status == "unsupported":
            reporter.error("UNSUPPORTED_ASSERTION", "Unsupported assertions fail the gate and must not be rendered", assertion_id)
        if evidence_status == "inferred":
            if category == "connection":
                reporter.error("INFERRED_CONNECTION_FORBIDDEN", "Never draw a guessed/inferred connection; use explicit source evidence or omit it", assertion_id)
            if not isinstance(assertion.get("inference_rationale"), str) or not assertion.get("inference_rationale").strip():
                reporter.error("INFERENCE_RATIONALE", "Inferred assertions need an explicit rationale and dashed visual treatment", assertion_id)
        visual = assertion.get("visual")
        visual_id = visual.get("id") if isinstance(visual, dict) else None
        if not isinstance(visual_id, str) or not ID_RE.match(visual_id):
            reporter.error("VISUAL_ID", "A valid visual.id is required", assertion_id)
            visual_id = None
        elif visual_id in visual_ids:
            reporter.error("VISUAL_ID_DUPLICATE", "Visual id %s is used by %s and %s" % (visual_id, visual_ids[visual_id], assertion_id), assertion_id)
        else:
            visual_ids[visual_id] = assertion_id
        evidence_records = []
        evidence = assertion.get("evidence")
        if evidence_status != "unsupported" and (not isinstance(evidence, list) or not evidence):
            reporter.error("EVIDENCE_REQUIRED", "Explicit and inferred assertions require evidence", assertion_id)
            evidence = []
        if not isinstance(evidence, list):
            evidence = []
        evidence_source_ids = []
        for item in evidence:
            if not isinstance(item, dict):
                reporter.error("EVIDENCE_TYPE", "Evidence entries must be objects", assertion_id)
                continue
            source_id = item.get("source_id")
            if source_id not in sources:
                reporter.error("EVIDENCE_SOURCE", "Unknown source %r" % source_id, assertion_id)
                continue
            if sources[source_id]["spec"].get("kind") == "csv":
                reporter.error("CSV_QUOTE_NOT_ALLOWED", "Use charts for CSV mappings; textual quote evidence must name a text/methods/figure source", assertion_id)
                continue
            match = match_evidence(item, sources[source_id], reporter, assertion_id)
            if match:
                evidence_records.append(match)
                evidence_source_ids.append(source_id)
        semantic = assertion.get("semantic_review")
        semantic_record = None
        if evidence_status != "unsupported":
            if not isinstance(semantic, dict):
                reporter.error("SEMANTIC_REVIEW_REQUIRED", "Quote matching is not semantic validation; add an independent semantic_review", assertion_id)
            else:
                semantic_record = dict(semantic)
                if semantic.get("result") != "match":
                    reporter.error("SEMANTIC_MISMATCH_OR_UNREVIEWED", "Scientific meaning must be explicitly compared and match; quote presence is insufficient", assertion_id)
                if not isinstance(semantic.get("comparison"), str) or not semantic.get("comparison").strip():
                    reporter.error("SEMANTIC_COMPARISON_REQUIRED", "Explain source meaning versus visual meaning", assertion_id)
                if not isinstance(semantic.get("reviewer"), str) or not semantic.get("reviewer").strip():
                    reporter.error("SEMANTIC_REVIEWER", "Identify the agent/native reviewer", assertion_id)
                reviewed = semantic.get("reviewed_sources")
                if not isinstance(reviewed, list) or not set(evidence_source_ids).issubset(set(reviewed)):
                    reporter.error("SEMANTIC_SOURCE_COVERAGE", "semantic_review.reviewed_sources must include every evidence source", assertion_id)
                for unknown in set(reviewed or []) - set(sources):
                    reporter.error("SEMANTIC_UNKNOWN_SOURCE", "Unknown reviewed source %s" % unknown, assertion_id)
                for source_id in evidence_source_ids:
                    if sources[source_id]["spec"].get("kind") == "figure":
                        review_id = semantic.get("figure_review_id")
                        if review_id not in figure_reviews or figure_reviews[review_id].get("source_id") != source_id:
                            reporter.error("FIGURE_REVIEW_LINK", "Figure-backed assertion needs a matching direct visual figure_review_id", assertion_id)
        if category in {"connection"}:
            for endpoint in ("from", "to"):
                if not isinstance(assertion.get(endpoint), str) or not assertion.get(endpoint):
                    reporter.error("CONNECTION_ENDPOINT", "Connections require %s visual id" % endpoint, assertion_id)
            if assertion.get("from") == assertion.get("to"):
                reporter.error("SELF_CONNECTION", "Self-connections are not supported by the minimal renderer", assertion_id)
        if category == "step":
            if not isinstance(assertion.get("order"), int) or isinstance(assertion.get("order"), bool) or assertion.get("order", 0) < 1:
                reporter.error("STEP_ORDER", "Steps need a positive integer order", assertion_id)
        records.append({
            "id": assertion_id, "category": category, "label": label,
            "evidence_status": evidence_status, "visual_id": visual_id,
            "from": assertion.get("from"), "to": assertion.get("to"), "order": assertion.get("order"),
            "inference_rationale": assertion.get("inference_rationale"),
            "evidence": evidence_records, "semantic_review": semantic_record,
            "gate_meaning": "Source spans and review attestations were checked; this is not automated scientific truth verification.",
        })
    for assertion in by_id.values():
        if assertion.get("category") == "connection":
            assertion_id = assertion.get("id")
            for endpoint in ("from", "to"):
                target = assertion.get(endpoint)
                if target in visual_ids:
                    target_assertion = by_id.get(visual_ids[target])
                    if target_assertion and target_assertion.get("category") == "connection":
                        reporter.error("EDGE_TO_EDGE", "Connections must end at node visuals, not other connections", assertion_id)
                elif isinstance(target, str):
                    reporter.error("MISSING_ENDPOINT", "%s visual %s is not declared by a node assertion" % (endpoint, target), assertion_id)
    orders = [a.get("order") for a in assertions if isinstance(a, dict) and a.get("category") == "step" and isinstance(a.get("order"), int)]
    duplicates = sorted({value for value in orders if orders.count(value) > 1})
    if duplicates:
        reporter.error("STEP_ORDER_DUPLICATE", "Duplicate step order values: %s" % duplicates)
    return records, by_id


def validate_conflicts(spec, by_id, sources, reporter):
    records = []
    conflicts = spec.get("conflicts", []) or []
    if not isinstance(conflicts, list):
        reporter.error("CONFLICTS_TYPE", "conflicts must be a list")
        return records
    seen = set()
    for conflict in conflicts:
        if not isinstance(conflict, dict):
            reporter.error("CONFLICT_TYPE", "Conflict entries must be objects")
            continue
        conflict_id = conflict.get("id", "unnamed")
        if conflict_id in seen:
            reporter.error("CONFLICT_DUPLICATE", "Duplicate conflict %s" % conflict_id)
        seen.add(conflict_id)
        status = conflict.get("status")
        if status == "unresolved":
            reporter.error("UNRESOLVED_CONFLICT", "%s: %s" % (conflict_id, conflict.get("description", "conflict unresolved")))
        elif status != "resolved":
            reporter.error("CONFLICT_STATUS", "Conflict %s needs status resolved or unresolved" % conflict_id)
        elif not str(conflict.get("resolution", "")).strip() or not str(conflict.get("visual_treatment", "")).strip():
            reporter.error("CONFLICT_RESOLUTION", "Resolved conflict %s needs resolution and visual_treatment" % conflict_id)
        assertion_ids = conflict.get("assertion_ids", [])
        for assertion_id in assertion_ids:
            if assertion_id not in by_id:
                reporter.error("CONFLICT_ASSERTION", "Unknown assertion %s in conflict %s" % (assertion_id, conflict_id))
        for source_id in conflict.get("source_ids", []):
            if source_id not in sources:
                reporter.error("CONFLICT_SOURCE", "Unknown source %s in conflict %s" % (source_id, conflict_id))
        records.append(conflict)
    return records


def validate_charts(spec, sources, by_id, reporter):
    records = []
    charts = spec.get("charts", []) or []
    if not isinstance(charts, list):
        reporter.error("CHARTS_TYPE", "charts must be a list")
        return records
    seen = set()
    for chart in charts:
        if not isinstance(chart, dict):
            reporter.error("CHART_TYPE", "Chart entries must be objects")
            continue
        chart_id = chart.get("id")
        if chart_id in seen:
            reporter.error("CHART_DUPLICATE", "Duplicate chart %s" % chart_id)
            continue
        seen.add(chart_id)
        source_id = chart.get("source_id")
        assertion_id = chart.get("assertion_id")
        if source_id not in sources or sources[source_id]["spec"].get("kind") != "csv":
            reporter.error("CHART_SOURCE", "Chart %s needs a CSV source" % chart_id)
            continue
        if assertion_id not in by_id:
            reporter.error("CHART_ASSERTION", "Chart %s needs an existing assertion_id" % chart_id, assertion_id)
        elif by_id[assertion_id].get("visual", {}).get("id") != chart_id:
            reporter.error("CHART_VISUAL_BINDING", "Chart id must equal its assertion visual.id", chart_id)
        x_column, y_column = chart.get("x_column"), chart.get("y_column")
        headers = sources[source_id]["headers"]
        for column in (x_column, y_column):
            if column not in headers:
                reporter.error("CSV_COLUMN_NOT_FOUND", "CSV column %r not found; actual headers: %s" % (column, headers), chart_id)
        mappings = []
        if x_column in headers and y_column in headers:
            for row in sources[source_id]["rows"]:
                raw_x, raw_y = row[x_column], row[y_column]
                try:
                    x, y = float(raw_x), float(raw_y)
                    if not math.isfinite(x) or not math.isfinite(y):
                        raise ValueError("non-finite")
                except (ValueError, TypeError):
                    reporter.error("CSV_NUMERIC_REQUIRED", "Row %s has nonnumeric chart value" % row["__source_row__"], chart_id)
                    continue
                mappings.append({
                    "source_row": row["__source_row__"], "x_column": x_column, "y_column": y_column,
                    "x_raw": raw_x, "y_raw": raw_y, "x_value": x, "y_value": y,
                    "source_sha256": sources[source_id]["sha256"], "visual_element_id": chart_id,
                })
        records.append({
            "id": chart_id, "assertion_id": assertion_id, "source_id": source_id,
            "x_column": x_column, "y_column": y_column,
            "title": chart.get("title", "CSV data"), "x_label": chart.get("x_label", x_column),
            "y_label": chart.get("y_label", y_column), "row_mappings": mappings,
            "binding_rule": "Exact case-sensitive CSV headers and source row numbers; no invented or imputed values",
        })
    return records


def validate_spec(spec, atlas_path):
    reporter = Reporter()
    atlas_path = Path(atlas_path).resolve()
    atlas_dir = atlas_path.parent
    if not isinstance(spec, dict):
        reporter.error("ATLAS_TYPE", "Atlas root must be an object")
        return {"schema_version": SCHEMA_VERSION, "verdict": "failed", "errors": reporter.errors,
                "warnings": [], "sources": [], "assertions": [], "conflicts": [], "charts": [],
                "figure_reviews": [], "case_id": "unknown"}, {}, {}, []
    case_id = spec.get("case_id")
    if not isinstance(case_id, str) or not case_id.strip():
        reporter.error("CASE_ID", "case_id is required")
    if spec.get("schema_version") != SCHEMA_VERSION:
        reporter.error("SCHEMA_VERSION", "Expected %s" % SCHEMA_VERSION)
    if not isinstance(spec.get("output_contract"), dict):
        reporter.error("OUTPUT_CONTRACT", "output_contract object is required; its keys are copied to result.json top level")
    sources, source_records = load_sources(spec, atlas_dir, reporter)
    figure_reviews, figure_records = validate_figure_reviews(spec, sources, reporter)
    assertions, by_id = validate_assertions(spec, sources, figure_reviews, reporter)
    conflicts = validate_conflicts(spec, by_id, sources, reporter)
    charts = validate_charts(spec, sources, by_id, reporter)
    return {
        "schema_version": SCHEMA_VERSION, "case_id": case_id or "unknown",
        "synthetic": bool(spec.get("synthetic", False)),
        "verdict": "failed" if reporter.errors else "passed",
        "gate_scope": "Exact normalized source spans + locators + separate semantic/direct-figure review attestations + real CSV bindings + conflict policy. A passing gate is not proof of scientific correctness.",
        "normalization": {
            "operations_in_order": ["per-original-character Unicode NFKC", "canonical curly quotes and Unicode dashes", "Unicode whitespace folded to one ASCII space", "leading/trailing whitespace omitted"],
            "excluded": ["fuzzy similarity", "stemming", "synonyms", "automatic PDF line dehyphenation", "OCR correction"],
            "offset_unit": "Python Unicode code point offsets in decoded original source; half-open [start,end)",
        },
        "sources": source_records, "assertions": assertions, "conflicts": conflicts,
        "charts": charts, "figure_reviews": figure_records,
        "errors": reporter.errors, "warnings": reporter.warnings,
    }, sources, by_id, charts


def _attrs(items):
    return " ".join("%s=%s" % (key, quoteattr(str(value))) for key, value in items.items())


def _text(x, y, value, css_class="label", extra=None):
    attrs = {"x": round(x, 3), "y": round(y, 3), "class": css_class}
    attrs.update(extra or {})
    return "<text %s>%s</text>" % (_attrs(attrs), escape(str(value)))


def _multiline(x, y, text, width=23, css_class="label"):
    words = str(text).split()
    lines, current = [], ""
    for word in words:
        candidate = (current + " " + word).strip()
        if current and len(candidate) > width:
            lines.append(current)
            current = word
        else:
            current = candidate
    if current or not lines:
        lines.append(current)
    spans = []
    for index, line in enumerate(lines[:3]):
        spans.append('<tspan x="%s" dy="%s">%s</tspan>' % (round(x, 3), 0 if index == 0 else 18, escape(line)))
    if len(lines) > 3:
        spans[-1] = spans[-1].replace("</tspan>", "…</tspan>")
    return '<text x="%s" y="%s" class="%s">%s</text>' % (round(x, 3), round(y, 3), css_class, "".join(spans))


def render_svg(spec, atlas, charts):
    nodes = [a for a in spec["assertions"] if a.get("category") in {"entity", "step", "stage"}]
    notes = [a for a in spec["assertions"] if a.get("category") == "note"]
    edges = [a for a in spec["assertions"] if a.get("category") == "connection"]
    width = 1200
    height = 760 if charts else (610 if notes else 540)
    positions, dimensions = {}, {}
    entities = [a for a in nodes if a.get("category") == "entity"]
    steps = [a for a in nodes if a.get("category") in {"step", "stage"}]
    for row, items, y, w, h in ((0, entities, 135, 230, 86), (1, steps, 300, 230, 78)):
        for index, assertion in enumerate(items):
            x = 60 + index * 275
            visual_id = assertion["visual"]["id"]
            positions[visual_id] = (x, y)
            dimensions[visual_id] = (w, h)
    note_positions = {}
    for index, assertion in enumerate(notes):
        note_positions[assertion["visual"]["id"]] = (60 + index * 550, 455)
    out = [
        '<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink" width="%d" height="%d" viewBox="0 0 %d %d" role="img" aria-labelledby="figure-title figure-desc">' % (width, height, width, height),
        '<title id="figure-title">%s</title>' % escape(spec.get("title", "Source-span atlas figure")),
        '<desc id="figure-desc">Editable source-bound figure. Each scientific group has data-assertion-id and data-source-ids. Exact source spans are in atlas.json. Semantic review remains a separate human/native-model responsibility.</desc>',
        '<defs><marker id="arrow-explicit" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse"><path d="M 0 0 L 10 5 L 0 10 z" fill="#24527a"/></marker><style><![CDATA[',
        'text{font-family:Arial,Helvetica,"Noto Sans CJK SC","Microsoft YaHei",sans-serif;fill:#17232d}.title{font-size:24px;font-weight:700}.subtitle{font-size:14px;fill:#4a5a67}.label{font-size:15px}.small{font-size:12px;fill:#435564}.node{fill:#eaf3f8;stroke:#24527a;stroke-width:1.7}.step{fill:#f3f0e7;stroke:#715d32;stroke-width:1.7}.note{fill:#fff8e8;stroke:#8a6327;stroke-width:1.4;stroke-dasharray:5 4}.edge{fill:none;stroke:#24527a;stroke-width:2}.inferred{stroke-dasharray:7 5}.axis{stroke:#536575;stroke-width:1.4}.grid{stroke:#d8e0e5;stroke-width:1}.point{fill:#a33f34;stroke:#fff;stroke-width:1}.series{fill:none;stroke:#a33f34;stroke-width:2}.chart-bg{fill:#fbfcfd;stroke:#9aabb8}]]></style></defs>',
        '<g id="layer-background" inkscape:groupmode="layer" inkscape:label="Background" xmlns:inkscape="http://www.inkscape.org/namespaces/inkscape"><rect x="0" y="0" width="1200" height="%d" fill="#ffffff"/></g>' % height,
        '<g id="layer-titles" inkscape:groupmode="layer" inkscape:label="Titles" xmlns:inkscape="http://www.inkscape.org/namespaces/inkscape">',
        _text(50, 45, spec.get("title", "Source-span atlas figure"), "title"),
        _text(50, 72, "SYNTHETIC fixture — not a real experiment" if spec.get("synthetic") else "Source-bound editable figure; see atlas.json for evidence and uncertainties", "subtitle"),
        '</g>', '<g id="layer-edges" inkscape:groupmode="layer" inkscape:label="Evidence-backed relations" xmlns:inkscape="http://www.inkscape.org/namespaces/inkscape">',
    ]
    for assertion in edges:
        from_id, to_id = assertion.get("from"), assertion.get("to")
        if from_id not in positions or to_id not in positions:
            continue
        x1, y1 = positions[from_id]
        x2, y2 = positions[to_id]
        w1, h1 = dimensions[from_id]
        w2, h2 = dimensions[to_id]
        if y1 == y2 and x2 >= x1:
            start = (x1 + w1, y1 + h1 / 2)
            end = (x2 - 7, y2 + h2 / 2)
        elif y1 == y2:
            start = (x1, y1 + h1 / 2)
            end = (x2 + w2 + 7, y2 + h2 / 2)
        else:
            start = (x1 + w1 / 2, y1 + h1)
            end = (x2 + w2 / 2, y2 - 7)
        source_ids = sorted({e.get("source_id") for e in assertion.get("evidence", [])})
        desc = "; ".join(e.get("quote", "") for e in assertion.get("evidence", []))
        out.append('<g %s><title>%s</title><desc>%s</desc>' % (_attrs({"id": assertion["visual"]["id"], "data-scientific": "true", "data-assertion-id": assertion["id"], "data-evidence-status": assertion["evidence_status"], "data-source-ids": ",".join(source_ids)}), escape(assertion.get("label", "")), escape(desc)))
        out.append('<line x1="%s" y1="%s" x2="%s" y2="%s" class="edge" marker-end="url(#arrow-explicit)"/>' % (round(start[0], 2), round(start[1], 2), round(end[0], 2), round(end[1], 2)))
        out.append('</g>')
    out.append('</g>')
    out.append('<g id="layer-nodes" inkscape:groupmode="layer" inkscape:label="Entities and ordered steps" xmlns:inkscape="http://www.inkscape.org/namespaces/inkscape">')
    for assertion in nodes:
        visual_id = assertion["visual"]["id"]
        x, y = positions[visual_id]
        w, h = dimensions[visual_id]
        source_ids = sorted({e.get("source_id") for e in assertion.get("evidence", [])})
        evidence_text = "; ".join(e.get("quote", "") for e in assertion.get("evidence", []))
        css = "node" if assertion.get("category") == "entity" else "step"
        if assertion.get("evidence_status") == "inferred":
            css += " inferred"
        out.append('<g %s>' % _attrs({"id": visual_id, "data-scientific": "true", "data-assertion-id": assertion["id"], "data-evidence-status": assertion["evidence_status"], "data-source-ids": ",".join(source_ids)}))
        out.append('<title>%s</title><desc>%s</desc>' % (escape(assertion["label"]), escape(evidence_text)))
        if assertion.get("category") == "stage":
            out.append('<path d="M %s %s H %s L %s %s L %s %s H %s Z" class="%s"/>' % (x, y, x + w - 18, x + w, y + h / 2, x + w - 18, y + h, x, css))
        else:
            out.append('<rect x="%s" y="%s" width="%s" height="%s" rx="10" class="%s"/>' % (x, y, w, h, css))
        if assertion.get("category") == "step":
            out.append('<circle cx="%s" cy="%s" r="16" fill="#715d32"/><text x="%s" y="%s" text-anchor="middle" font-size="14" fill="#fff">%s</text>' % (x + 22, y + 22, x + 22, y + 27, assertion.get("order")))
            out.append(_multiline(x + 47, y + 31, assertion["label"], 19))
        else:
            out.append(_multiline(x + 16, y + 32, assertion["label"], 24))
        out.append(_text(x + 16, y + h - 10, assertion["evidence_status"], "small"))
        out.append('</g>')
    out.append('</g>')
    out.append('<g id="layer-notes" inkscape:groupmode="layer" inkscape:label="Evidence-backed notes" xmlns:inkscape="http://www.inkscape.org/namespaces/inkscape">')
    for assertion in notes:
        visual_id = assertion["visual"]["id"]
        x, y = note_positions[visual_id]
        source_ids = sorted({e.get("source_id") for e in assertion.get("evidence", [])})
        out.append('<g %s>' % _attrs({"id": visual_id, "data-scientific": "true", "data-assertion-id": assertion["id"], "data-evidence-status": assertion["evidence_status"], "data-source-ids": ",".join(source_ids)}))
        out.append('<rect x="%s" y="%s" width="500" height="74" rx="8" class="note"/>' % (x, y))
        out.append(_multiline(x + 15, y + 24, assertion["label"], 58, "small"))
        out.append('</g>')
    out.append('</g>')
    out.append('<g id="layer-charts" inkscape:groupmode="layer" inkscape:label="CSV-linked charts" xmlns:inkscape="http://www.inkscape.org/namespaces/inkscape">')
    for chart_index, chart in enumerate(charts):
        rows = chart["row_mappings"]
        if not rows:
            continue
        x0, y0, w, h = 640 + chart_index * 510, 285, 480, 340
        assertion = next(a for a in spec["assertions"] if a["id"] == chart["assertion_id"])
        source_ids = sorted({e.get("source_id") for e in assertion.get("evidence", [])} | {chart["source_id"]})
        out.append('<g %s>' % _attrs({"id": chart["id"], "data-scientific": "true", "data-assertion-id": chart["assertion_id"], "data-evidence-status": assertion["evidence_status"], "data-source-ids": ",".join(source_ids)}))
        out.append('<rect x="%s" y="%s" width="%s" height="%s" class="chart-bg"/>' % (x0, y0, w, h))
        out.append(_text(x0 + 18, y0 + 27, chart["title"], "label"))
        px0, py0, pw, ph = x0 + 65, y0 + 60, w - 105, 210
        xs, ys = [r["x_value"] for r in rows], [r["y_value"] for r in rows]
        xmin, xmax, ymin, ymax = min(xs), max(xs), min(ys), max(ys)
        xspan = xmax - xmin or 1.0
        yspan = ymax - ymin or 1.0
        points = []
        for tick in range(5):
            gy = py0 + tick * ph / 4
            out.append('<line x1="%s" y1="%s" x2="%s" y2="%s" class="grid"/>' % (px0, gy, px0 + pw, gy))
        out.append('<line x1="%s" y1="%s" x2="%s" y2="%s" class="axis"/>' % (px0, py0 + ph, px0 + pw, py0 + ph))
        out.append('<line x1="%s" y1="%s" x2="%s" y2="%s" class="axis"/>' % (px0, py0, px0, py0 + ph))
        out.append(_text(px0 + pw / 2, py0 + ph + 48, chart["x_label"], "small", {"text-anchor": "middle"}))
        out.append(_text(x0 + 15, py0 + ph / 2, chart["y_label"], "small", {"transform": "rotate(-90 %s %s)" % (x0 + 15, py0 + ph / 2), "text-anchor": "middle"}))
        for row in rows:
            px = px0 + (row["x_value"] - xmin) / xspan * pw
            py = py0 + ph - (row["y_value"] - ymin) / yspan * ph
            points.append((px, py, row))
        out.append('<polyline points="%s" class="series"/>' % " ".join("%s,%s" % (round(px, 3), round(py, 3)) for px, py, _ in points))
        for index, (px, py, row) in enumerate(points):
            out.append('<circle cx="%s" cy="%s" r="5" class="point" data-row="%s" data-x-column=%s data-y-column=%s data-x=%s data-y=%s><title>CSV row %s: %s=%s; %s=%s</title></circle>' % (round(px, 3), round(py, 3), row["source_row"], quoteattr(row["x_column"]), quoteattr(row["y_column"]), quoteattr(row["x_raw"]), quoteattr(row["y_raw"]), row["source_row"], escape(row["x_column"]), escape(row["x_raw"]), escape(row["y_column"]), escape(row["y_raw"])))
            out.append(_text(px, py - 10, "%s, %s" % (row["x_raw"], row["y_raw"]), "small", {"text-anchor": "middle"}))
        out.append(_text(px0, py0 + ph + 25, "%s=%s; %s=%s" % (chart["x_column"], xmin, chart["y_column"], ymin), "small"))
        out.append(_text(px0 + pw, py0 + ph + 25, "%s=%s; %s=%s" % (chart["x_column"], xmax, chart["y_column"], ymax), "small", {"text-anchor": "end"}))
        out.append('</g>')
    out.append('</g>')
    out.append('<g id="layer-legend" inkscape:groupmode="layer" inkscape:label="Evidence legend" xmlns:inkscape="http://www.inkscape.org/namespaces/inkscape">')
    legend_y = height - 42
    out.append(_text(55, legend_y, "Evidence: explicit = solid; inferred = dashed and uncertainty retained; unsupported = blocked. Quotes alone never establish scientific meaning.", "small"))
    out.append('</g></svg>')
    return "\n".join(out) + "\n"


def coverage_for_svg(svg_path, spec, atlas, reporter):
    try:
        tree = ET.parse(str(svg_path))
    except (OSError, ET.ParseError) as exc:
        reporter.error("SVG_PARSE", "Cannot audit SVG: %s" % exc)
        return None
    root = tree.getroot()
    all_ids = {}
    scientific = {}
    for element in root.iter():
        element_id = element.attrib.get("id")
        if element_id:
            all_ids.setdefault(element_id, []).append(element)
        if element.attrib.get("data-scientific") == "true":
            scientific[element_id] = element
    duplicates = sorted(key for key, values in all_ids.items() if len(values) > 1)
    for duplicate in duplicates:
        reporter.error("SVG_DUPLICATE_ID", "Duplicate SVG id %s" % duplicate)
    expected = {a["visual"]["id"]: a for a in spec["assertions"] if isinstance(a.get("visual"), dict) and a["visual"].get("id")}
    missing, mismatched = [], []
    for visual_id, assertion in expected.items():
        if visual_id not in all_ids:
            missing.append(visual_id)
            reporter.error("COVERAGE_MISSING_VISUAL", "No SVG element for %s / %s" % (assertion["id"], visual_id), assertion["id"])
        elif visual_id not in scientific:
            reporter.error("COVERAGE_NOT_SCIENTIFIC", "SVG visual %s lacks data-scientific=true" % visual_id, assertion["id"])
        elif scientific[visual_id].attrib.get("data-assertion-id") != assertion["id"]:
            mismatched.append(visual_id)
            reporter.error("COVERAGE_ASSERTION_MISMATCH", "SVG data-assertion-id does not match %s" % assertion["id"], assertion["id"])
    orphans = []
    for visual_id, element in scientific.items():
        assertion_id = element.attrib.get("data-assertion-id")
        if visual_id not in expected or assertion_id not in {a["id"] for a in spec["assertions"]}:
            orphans.append(visual_id)
            reporter.error("COVERAGE_ORPHAN_VISUAL", "Scientific SVG visual %s has no atlas assertion" % visual_id)
    source_to_visual = {}
    for assertion in spec["assertions"]:
        if not isinstance(assertion, dict) or not isinstance(assertion.get("visual"), dict):
            continue
        visual_id = assertion["visual"].get("id")
        for evidence in assertion.get("evidence", []) or []:
            source_id = evidence.get("source_id")
            if isinstance(source_id, str):
                source_to_visual.setdefault(source_id, set()).add(visual_id)
    for chart in atlas.get("charts", []):
        source_to_visual.setdefault(chart["source_id"], set()).add(chart["id"])
    return {
        "svg_path": str(Path(svg_path).resolve()), "coverage_rule": "Bidirectional: every assertion visual exists with matching data-assertion-id; every data-scientific SVG group maps back to an assertion.",
        "expected_visual_count": len(expected), "scientific_visual_count": len(scientific),
        "missing_visuals": sorted(missing), "mismatched_visuals": sorted(mismatched),
        "orphan_scientific_visuals": sorted(orphans), "duplicate_svg_ids": duplicates,
        "source_to_visual": {key: sorted(values) for key, values in sorted(source_to_visual.items())},
        "assertion_to_visual": {a["id"]: a["visual"].get("id") for a in spec["assertions"] if isinstance(a, dict) and isinstance(a.get("visual"), dict)},
        "passed": not (missing or mismatched or orphans or duplicates),
    }
