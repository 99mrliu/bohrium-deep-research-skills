#!/usr/bin/env python3
"""Index physical-layout text and recover auditable quote locations.

Python 3.9+; standard library only. This tool indexes TXT/MD or an explicit
JSON block layout. It does not parse PDF, perform OCR, or test semantic
entailment. Offsets are zero-based Unicode-code-point [start, end) offsets in
its normalized-LF reading stream and in each original supplied line.
"""

import argparse
import hashlib
import json
import os
import re
import sys
from pathlib import Path

SCHEMA = "layout-evidence-index/v1"
REPORT_SCHEMA = "layout-evidence-locations/v1"
PAGE_MARKER = re.compile(r"<!--\s*page\s*:\s*(\d+)\s*-->", re.IGNORECASE)
MAX_MATCHES_PER_QUERY = 1000


class InputError(ValueError):
    """A malformed input that prevents faithful indexing."""


def read_utf8(path):
    raw = Path(path).read_bytes()
    if raw.startswith(b"\xef\xbb\xbf"):
        raise InputError("UTF-8 BOM is not accepted; save input as plain UTF-8")
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise InputError("input is not valid UTF-8: %s" % exc) from exc
    return text, hashlib.sha256(raw).hexdigest()


def dump_json(path, payload):
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_name(target.name + ".tmp")
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    os.replace(str(temporary), str(target))


def issue(code, message, page=None, block_id=None, severity="review"):
    item = {"code": code, "severity": severity, "message": message}
    if page is not None:
        item["page"] = page
    if block_id is not None:
        item["block_id"] = block_id
    return item


def split_physical_lines(text):
    if text == "":
        return []
    lines = text.split("\n")
    if lines and lines[-1] == "":
        lines.pop()
    return lines


def paginate_plain_text(text, markdown=False):
    """Split on form feeds or standalone Markdown page markers.

    Newlines are normalized to LF before offsets are assigned. A page: 1
    marker at the start labels page one; later markers create page breaks.
    """
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    pages = [[]]
    problems = []
    declared = None

    def new_page():
        pages.append([])

    for physical in text.splitlines(keepends=True):
        marker = PAGE_MARKER.fullmatch(physical.strip()) if markdown else None
        if marker:
            number = int(marker.group(1))
            if number == 1 and not pages[-1] and len(pages) == 1:
                declared = number
                continue
            new_page()
            expected = len(pages)
            if number != expected:
                problems.append(issue(
                    "PAGE_NUMBER_MISMATCH",
                    "declared page %d but sequential input page is %d" % (number, expected),
                    page=expected,
                ))
            declared = number
            continue
        pieces = physical.split("\f")
        for index, piece in enumerate(pieces):
            if index:
                new_page()
            if piece:
                pages[-1].append(piece)
    return [split_physical_lines("".join(parts)) for parts in pages], problems, declared


def base_result(document_id, synthetic, source, include_figure_text):
    return {
        "schema_version": SCHEMA,
        "tool": "layout_evidence.py",
        "tool_version": "1.0.0",
        "document_id": document_id,
        "synthetic": bool(synthetic),
        "formal_result": False if synthetic else None,
        "source": source,
        "included_roles": ["body", "figure_text"] if include_figure_text else ["body"],
        "pages": [],
        "text": "",
        "issues": [],
        "sources": [source],
        "uncertainty": [],
        "change_records": [{
            "operation": "index",
            "source_modified": False,
            "details": "Normalized indexing only; no source text was overwritten.",
        }],
        "semantic_entailment": "not_evaluated",
    }


def build_index_from_pages(document_id, synthetic, source, page_inputs,
                           include_figure_text=False, pre_issues=None):
    result = base_result(document_id, synthetic, source, include_figure_text)
    result["issues"].extend(pre_issues or [])
    stream = ""
    seen_block_ids = set()

    for page_position, page_input in enumerate(page_inputs, 1):
        page_number = page_input.get("page", page_position)
        if page_number != page_position:
            result["issues"].append(issue(
                "PAGE_NUMBER_MISMATCH",
                "page value %r does not match one-based position %d" % (page_number, page_position),
                page=page_position,
            ))
            page_number = page_position
        status = page_input.get("extraction_status", "text")
        raw_blocks = page_input.get("blocks", [])
        if not isinstance(raw_blocks, list):
            raise InputError("page %d blocks must be a list" % page_number)
        by_id = {}
        for block in raw_blocks:
            block_id = block.get("block_id")
            if not isinstance(block_id, str) or not block_id:
                raise InputError("every block needs a nonempty string block_id")
            if block_id in seen_block_ids:
                raise InputError("duplicate block_id across document: %s" % block_id)
            seen_block_ids.add(block_id)
            by_id[block_id] = block

        declared_order = page_input.get("block_order")
        if declared_order is None:
            declared_order = [block.get("block_id") for block in raw_blocks]
            body_count = sum(block.get("role", "body") == "body" for block in raw_blocks)
            if body_count > 1:
                result["issues"].append(issue(
                    "ORDER_NOT_DECLARED",
                    "multiple body blocks use input order, not a verified physical reading order",
                    page=page_number,
                ))
        elif set(declared_order) != set(by_id) or len(declared_order) != len(by_id):
            raise InputError("page %d block_order must contain every block exactly once" % page_number)

        page_record = {
            "page": page_number,
            "width": page_input.get("width"),
            "height": page_input.get("height"),
            "extraction_status": status,
            "block_order": declared_order,
            "page_char_start": len(stream),
            "page_char_end": None,
            "blocks": [],
        }
        if status == "no_text_layer":
            result["issues"].append(issue(
                "NO_TEXT_LAYER",
                "no OCR or text recovery was performed; this page has no searchable text",
                page=page_number,
                severity="blocking",
            ))
        elif status == "ocr" and not page_input.get("ocr_verified", False):
            result["issues"].append(issue(
                "OCR_UNVERIFIED",
                "OCR text is present but no character-level verification is recorded",
                page=page_number,
            ))
        if status == "no_text_layer" and raw_blocks:
            result["issues"].append(issue(
                "STATUS_TEXT_CONFLICT",
                "page declares no text layer but also supplies blocks; review provenance",
                page=page_number,
                severity="blocking",
            ))
        for supplied in page_input.get("unresolved", []):
            item = dict(supplied)
            item.setdefault("page", page_number)
            item.setdefault("severity", "review")
            result["issues"].append(item)

        reading_index = 0
        for input_index, block_id in enumerate(declared_order):
            block = by_id[block_id]
            role = block.get("role", "body")
            included = role == "body" or (role == "figure_text" and include_figure_text)
            lines = block.get("lines")
            if lines is None:
                lines = split_physical_lines(str(block.get("text", "")).replace("\r\n", "\n").replace("\r", "\n"))
            if not isinstance(lines, list) or any(not isinstance(line, str) for line in lines):
                raise InputError("block %s lines must be a list of strings" % block_id)
            if any("\n" in line or "\r" in line or "\f" in line for line in lines):
                raise InputError("block %s line strings cannot contain line or page breaks" % block_id)
            bbox = block.get("bbox")
            if bbox is not None:
                if (not isinstance(bbox, list) or len(bbox) != 4 or
                        any(not isinstance(value, (int, float)) for value in bbox) or
                        bbox[0] > bbox[2] or bbox[1] > bbox[3]):
                    raise InputError("block %s bbox must be numeric [x0,y0,x1,y1]" % block_id)
            elif role == "body" and len(raw_blocks) > 1:
                result["issues"].append(issue(
                    "BBOX_MISSING",
                    "body block has no physical bounding box",
                    page=page_number,
                    block_id=block_id,
                ))

            if included and reading_index:
                stream += "\n"
            block_start = len(stream) if included else None
            record = {
                "block_id": block_id,
                "role": role,
                "column": block.get("column"),
                "bbox": bbox,
                "input_index": input_index,
                "reading_index": reading_index if included else None,
                "included": included,
                "block_char_start": block_start,
                "block_char_end": None,
                "text": "\n".join(lines),
                "lines": [],
            }
            for line_index, line_text in enumerate(lines):
                if included and line_index:
                    stream += "\n"
                start = len(stream) if included else None
                if included:
                    stream += line_text
                end = len(stream) if included else None
                record["lines"].append({
                    "line": line_index + 1,
                    "text": line_text,
                    "line_char_start": 0,
                    "line_char_end": len(line_text),
                    "document_char_start": start,
                    "document_char_end": end,
                    "page_char_start": start - page_record["page_char_start"] if included else None,
                    "page_char_end": end - page_record["page_char_start"] if included else None,
                })
            record["block_char_end"] = len(stream) if included else None
            if included:
                reading_index += 1
            page_record["blocks"].append(record)
        page_record["page_char_end"] = len(stream)
        result["pages"].append(page_record)
        if page_position != len(page_inputs):
            stream += "\n\f\n"

    result["text"] = stream
    result["page_count"] = len(result["pages"])
    result["status"] = "needs_review" if result["issues"] else "ok"
    result["uncertainty"] = [dict(item) for item in result["issues"]]
    return result


def index_text(path, markdown, synthetic):
    text, digest = read_utf8(path)
    pages, problems, declared = paginate_plain_text(text, markdown=markdown)
    source = {
        "source_id": Path(path).stem,
        "path": str(path),
        "sha256": digest,
        "media_type": "text/markdown" if markdown else "text/plain",
        "extraction": "direct UTF-8 text; LF normalization; form-feed pagination" + (
            " plus standalone Markdown page markers" if markdown else ""
        ),
    }
    page_inputs = [{
        "page": number,
        "extraction_status": "text",
        "block_order": ["p%d-b1" % number],
        "blocks": [{
            "block_id": "p%d-b1" % number,
            "role": "body",
            "column": 1,
            "lines": lines,
        }],
    } for number, lines in enumerate(pages, 1)]
    result = build_index_from_pages(
        Path(path).stem, synthetic, source, page_inputs, pre_issues=problems
    )
    result["pagination"] = {
        "kind": "markdown-page-markers-and-form-feeds" if markdown else "form-feeds",
        "last_declared_page": declared,
    }
    return result


def index_layout(path, synthetic_override=False, include_figure_text=False):
    text, digest = read_utf8(path)
    try:
        payload = json.loads(text)
    except json.JSONDecodeError as exc:
        raise InputError("invalid JSON input: %s" % exc) from exc
    if not isinstance(payload, dict) or not isinstance(payload.get("pages"), list):
        raise InputError("layout JSON must be an object with a pages list")
    supplied_source = payload.get("source", {})
    source = {
        "source_id": supplied_source.get("source_id", Path(path).stem),
        "path": str(path),
        "sha256": digest,
        "media_type": "application/json",
        "extraction": supplied_source.get("extraction", "external physical-layout extraction"),
        "origin": supplied_source.get("origin", "unspecified"),
    }
    synthetic = bool(payload.get("synthetic", False) or synthetic_override)
    return build_index_from_pages(
        payload.get("document_id", Path(path).stem), synthetic, source,
        payload["pages"], include_figure_text=include_figure_text,
    )


def fidelity_normalize(text, keep_end_hyphen=False):
    """Fold whitespace and map an end-line hyphen with or without retention."""
    chars = []
    positions = []
    i = 0
    while i < len(text):
        if text[i] == "-" and i + 1 < len(text) and text[i + 1] == "\n":
            if keep_end_hyphen:
                chars.append("-")
                positions.append(i)
            i += 2
            while i < len(text) and text[i] in " \t":
                i += 1
            continue
        if text[i].isspace():
            start = i
            i += 1
            while i < len(text) and text[i].isspace():
                i += 1
            if chars and chars[-1] != " ":
                chars.append(" ")
                positions.append(start)
            continue
        chars.append(text[i])
        positions.append(i)
        i += 1
    while chars and chars[-1] == " ":
        chars.pop()
        positions.pop()
    leading = 0
    while leading < len(chars) and chars[leading] == " ":
        leading += 1
    return "".join(chars[leading:]), positions[leading:]


def all_substring_offsets(haystack, needle):
    if not needle:
        return []
    found = []
    start = 0
    while True:
        position = haystack.find(needle, start)
        if position < 0:
            return found
        found.append(position)
        if len(found) >= MAX_MATCHES_PER_QUERY:
            return found
        start = position + 1


def iter_indexed_lines(index):
    for page in index["pages"]:
        for block in page["blocks"]:
            if not block["included"]:
                continue
            for line in block["lines"]:
                yield page, block, line


def make_match(index, query_mode, normalized_start, normalized_end, position_map):
    if query_mode == "exact":
        start, end = normalized_start, normalized_end
    else:
        start = position_map[normalized_start]
        end = position_map[normalized_end - 1] + 1
    segments = []
    for page, block, line in iter_indexed_lines(index):
        line_start = line["document_char_start"]
        line_end = line["document_char_end"]
        if line_start is None or line_end <= start or line_start >= end:
            continue
        left = max(start, line_start)
        right = min(end, line_end)
        if right < left:
            continue
        segments.append({
            "page": page["page"],
            "block_id": block["block_id"],
            "reading_index": block["reading_index"],
            "line": line["line"],
            "line_offset_start": left - line_start,
            "line_offset_end": right - line_start,
            "document_char_start": left,
            "document_char_end": right,
            "page_char_start": left - page["page_char_start"],
            "page_char_end": right - page["page_char_start"],
            "text": line["text"][left - line_start:right - line_start],
        })
    if not segments:
        raise RuntimeError("internal mapping failure: match has no source-line segment")
    first = segments[0]
    pages = sorted(set(segment["page"] for segment in segments))
    blocks = []
    for segment in segments:
        if segment["block_id"] not in blocks:
            blocks.append(segment["block_id"])
    match = {
        "page": first["page"],
        "block_id": first["block_id"],
        "line": first["line"],
        "line_offset_start": first["line_offset_start"],
        "line_offset_end": first["line_offset_end"],
        "offset": {
            "start": first["line_offset_start"],
            "end": first["line_offset_end"],
            "unit": "unicode_codepoint",
            "base": 0,
            "interval": "half_open",
            "scope": "original_supplied_line",
        },
        "document_char_start": start,
        "document_char_end": end,
        "page_char_start": start - index["pages"][first["page"] - 1]["page_char_start"] if len(pages) == 1 else None,
        "page_char_end": end - index["pages"][first["page"] - 1]["page_char_start"] if len(pages) == 1 else None,
        "source_excerpt": index["text"][start:end],
        "segments": segments,
        "spans_pages": pages,
        "spans_blocks": blocks,
    }
    return match


def locate_queries(index, queries_payload, query_source):
    query_items = queries_payload.get("queries")
    if not isinstance(query_items, list):
        raise InputError("query JSON must contain a queries list")
    locations = []
    counts = {"matched": 0, "ambiguous": 0, "not_found": 0, "invalid": 0}
    for number, item in enumerate(query_items, 1):
        query_id = item.get("query_id", "q%d" % number)
        query = item.get("query")
        mode = item.get("mode", "fidelity")
        record = {
            "query_id": query_id,
            "query": query,
            "mode": mode,
            "semantic_entailment": "not_evaluated",
        }
        if not isinstance(query, str) or not query or mode not in ("exact", "fidelity"):
            record.update({
                "status": "invalid",
                "match_count": 0,
                "matches": [],
                "error": "query must be a nonempty string and mode exact or fidelity",
            })
            counts["invalid"] += 1
            locations.append(record)
            continue
        variants = [("exact", False)] if mode == "exact" else [
            ("hyphen_removed", False),
            ("hyphen_retained", True),
        ]
        matches_by_raw_range = {}
        normalized_queries = {}
        for variant, keep_end_hyphen in variants:
            if mode == "exact":
                haystack, needle, positions = index["text"], query, None
            else:
                haystack, positions = fidelity_normalize(index["text"], keep_end_hyphen)
                needle, unused_query_map = fidelity_normalize(query, keep_end_hyphen)
            normalized_queries[variant] = needle
            if not needle:
                continue
            for start in all_substring_offsets(haystack, needle):
                match = make_match(index, mode, start, start + len(needle), positions)
                if mode == "fidelity":
                    match["fidelity_variant"] = variant
                raw_range = (match["document_char_start"], match["document_char_end"])
                matches_by_raw_range.setdefault(raw_range, match)
        if not any(normalized_queries.values()):
            record.update({
                "status": "invalid",
                "match_count": 0,
                "matches": [],
                "error": "query folds to an empty string",
            })
            counts["invalid"] += 1
            locations.append(record)
            continue
        matches = sorted(matches_by_raw_range.values(), key=lambda match: (
            match["document_char_start"], match["document_char_end"]
        ))[:MAX_MATCHES_PER_QUERY]
        status = "matched" if len(matches) == 1 else ("ambiguous" if matches else "not_found")
        record.update({
            "status": status,
            "match_count": len(matches),
            "normalized_query": normalized_queries[variants[0][0]],
            "normalized_queries": normalized_queries,
            "matches": matches,
        })
        if len(matches) >= MAX_MATCHES_PER_QUERY:
            record["match_limit_reached"] = True
        counts[status] += 1
        locations.append(record)

    unresolved = [dict(item) for item in index.get("issues", [])]
    for record in locations:
        if record["status"] == "ambiguous":
            unresolved.append({
                "code": "AMBIGUOUS_QUOTE",
                "severity": "review",
                "query_id": record["query_id"],
                "message": "multiple physical matches; a unique evidence span is not asserted",
            })
        elif record["status"] == "not_found":
            unresolved.append({
                "code": "QUOTE_NOT_FOUND",
                "severity": "review",
                "query_id": record["query_id"],
                "message": "no match under the requested fidelity mode; not a claim about PDF meaning",
            })
        elif record["status"] == "invalid":
            unresolved.append({
                "code": "INVALID_QUERY",
                "severity": "error",
                "query_id": record["query_id"],
                "message": record["error"],
            })
    report = {
        "schema_version": REPORT_SCHEMA,
        "case_id": queries_payload.get("case_id"),
        "document_id": index["document_id"],
        "synthetic": bool(index.get("synthetic") or queries_payload.get("synthetic")),
        "formal_result": False if (index.get("synthetic") or queries_payload.get("synthetic")) else None,
        "expected_failure": bool(queries_payload.get("expected_failure", False)),
        "status": "ok" if not unresolved else "unresolved",
        "summary": dict(counts, total=len(locations)),
        "locations": locations,
        "unresolved_distortions": unresolved,
        "sources": index.get("sources", []) + [{
            "source_id": "queries",
            "path": query_source,
            "media_type": "application/json",
        }],
        "uncertainty": [dict(item) for item in unresolved],
        "change_records": [{
            "operation": "locate",
            "source_modified": False,
            "query_count": len(locations),
            "details": "Offsets computed against the supplied index; no semantic inference performed.",
        }],
        "semantic_entailment": "not_evaluated",
    }
    return report


def values_match(expected, actual, path=""):
    errors = []
    if isinstance(expected, dict):
        if not isinstance(actual, dict):
            return ["%s: expected object" % path]
        for key, value in expected.items():
            if key not in actual:
                errors.append("%s.%s: missing" % (path, key))
            else:
                errors.extend(values_match(value, actual[key], path + "." + key))
    elif isinstance(expected, list):
        if not isinstance(actual, list) or len(expected) != len(actual):
            errors.append("%s: list length differs" % path)
        else:
            for index, (left, right) in enumerate(zip(expected, actual)):
                errors.extend(values_match(left, right, "%s[%d]" % (path, index)))
    elif expected != actual:
        errors.append("%s: expected %r, got %r" % (path, expected, actual))
    return errors


def verify_suite(suite_path):
    suite_text, suite_digest = read_utf8(suite_path)
    suite = json.loads(suite_text)
    if not isinstance(suite.get("groups"), list):
        raise InputError("verification suite requires groups")
    base = Path(suite_path).parent
    records = []
    for group in suite["groups"]:
        relative_input = group["input"]
        input_path = base / relative_input
        synthetic = bool(suite.get("synthetic") or group.get("synthetic"))
        if str(input_path).lower().endswith(".json"):
            index = index_layout(str(input_path), synthetic_override=synthetic)
        else:
            index = index_text(str(input_path), str(input_path).lower().endswith(".md"), synthetic)
        queries = {
            "case_id": suite.get("suite_id"),
            "synthetic": synthetic,
            "queries": [{
                "query_id": case["id"],
                "query": case["query"],
                "mode": case.get("mode", "fidelity"),
            } for case in group["cases"]],
        }
        report = locate_queries(index, queries, str(suite_path))
        by_id = {record["query_id"]: record for record in report["locations"]}
        for case in group["cases"]:
            actual = by_id[case["id"]]
            errors = values_match(case["expected_status"], actual["status"], "status")
            if "expected_matches" in case:
                errors.extend(values_match(case["expected_matches"], actual["match_count"], "match_count"))
            if "expected" in case:
                errors.extend(values_match(case["expected"], actual["matches"], "matches"))
            records.append({
                "id": case["id"],
                "group": group["name"],
                "input": str(input_path),
                "passed": not errors,
                "assertion_errors": errors,
                "actual": actual,
            })
    passed = sum(record["passed"] for record in records)
    output = {
        "schema_version": "layout-evidence-verification/v1",
        "suite_id": suite.get("suite_id"),
        "synthetic": True,
        "formal_result": False,
        "status": "passed" if passed == len(records) else "failed",
        "assertion_count": len(records),
        "passed_count": passed,
        "failed_count": len(records) - passed,
        "suite_sha256": suite_digest,
        "tests": records,
        "semantic_entailment": "not_evaluated",
    }
    return output


def command_index(args):
    if str(args.input).lower().endswith(".json"):
        result = index_layout(args.input, args.synthetic, args.include_figure_text)
    else:
        suffix = str(args.input).lower()
        if not suffix.endswith((".txt", ".md")):
            raise InputError("non-JSON input must have .txt or .md extension")
        result = index_text(args.input, suffix.endswith(".md"), args.synthetic)
    dump_json(args.output, result)
    print("index=%s status=%s pages=%d issues=%d output=%s" % (
        result["document_id"], result["status"], result["page_count"],
        len(result["issues"]), args.output,
    ))
    return 2 if result["issues"] else 0


def command_locate(args):
    index_text_value, unused_digest = read_utf8(args.index)
    index = json.loads(index_text_value)
    if index.get("schema_version") != SCHEMA:
        raise InputError("unsupported index schema")
    query_text, unused_query_digest = read_utf8(args.queries)
    queries = json.loads(query_text)
    report = locate_queries(index, queries, args.queries)
    dump_json(args.output, report)
    print("case_id=%s status=%s summary=%s output=%s" % (
        report["case_id"], report["status"], json.dumps(report["summary"], sort_keys=True), args.output,
    ))
    return 2 if report["status"] != "ok" else 0


def command_verify(args):
    report = verify_suite(args.suite)
    dump_json(args.output, report)
    print("suite=%s status=%s assertions=%d passed=%d failed=%d output=%s" % (
        report["suite_id"], report["status"], report["assertion_count"],
        report["passed_count"], report["failed_count"], args.output,
    ))
    return 0 if report["status"] == "passed" else 1


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    index_parser = subparsers.add_parser("index", help="index JSON layout or paginated TXT/MD")
    index_parser.add_argument("--input", required=True)
    index_parser.add_argument("--output", required=True)
    index_parser.add_argument("--synthetic", action="store_true", help="label TXT/MD input as synthetic")
    index_parser.add_argument("--include-figure-text", action="store_true", help="opt in to figure_text blocks")
    index_parser.set_defaults(function=command_index)

    locate_parser = subparsers.add_parser("locate", help="locate exact or fidelity quotes")
    locate_parser.add_argument("--index", required=True)
    locate_parser.add_argument("--queries", required=True)
    locate_parser.add_argument("--output", required=True)
    locate_parser.set_defaults(function=command_locate)

    verify_parser = subparsers.add_parser("verify", help="run synthetic assertion suite end to end")
    verify_parser.add_argument("--suite", required=True)
    verify_parser.add_argument("--output", required=True)
    verify_parser.set_defaults(function=command_verify)

    args = parser.parse_args(argv)
    try:
        return args.function(args)
    except (InputError, OSError, json.JSONDecodeError) as exc:
        failure = {
            "schema_version": "layout-evidence-error/v1",
            "status": "error",
            "error": str(exc),
            "semantic_entailment": "not_evaluated",
        }
        output = getattr(args, "output", None)
        if output:
            dump_json(output, failure)
            print("error=%s output=%s" % (exc, output), file=sys.stderr)
        else:
            print("error=%s" % exc, file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
