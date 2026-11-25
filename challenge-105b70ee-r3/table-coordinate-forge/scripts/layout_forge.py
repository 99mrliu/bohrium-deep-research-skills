#!/usr/bin/env python3
"""Reconstruct candidate table geometry from pdftotext bbox-layout XHTML.

Only standard-library XML parsing and coordinates are used.  Text is never
normalized, unit-converted, spell-corrected, or selected as a requested answer.
"""
from __future__ import annotations

import argparse
import bisect
import difflib
import html
import json
import math
import re
import statistics
import xml.etree.ElementTree as ET
from pathlib import Path

from forge_common import atomic_write_text, utc_now, write_json

CONTINUATION_RE = re.compile(
    r"(?:\(|\[)?\s*(?:continued(?:\s+from\s+(?:the\s+)?previous\s+page)?|cont\.?|续表)\s*(?:\)|\])?",
    re.IGNORECASE,
)
DEFAULT_LABEL = "PDF coordinate reconstruction — candidate geometry, not extracted answers"


def local_name(tag):
    return tag.rsplit("}", 1)[-1]


def number(element, name):
    return float(element.attrib[name])


def bbox_union(boxes):
    if not boxes:
        return None
    return {
        "xMin": min(box["xMin"] for box in boxes),
        "yMin": min(box["yMin"] for box in boxes),
        "xMax": max(box["xMax"] for box in boxes),
        "yMax": max(box["yMax"] for box in boxes),
    }


def text_of(words):
    # The only inserted characters are separators between coordinate-word tokens.
    return " ".join(word["text"] for word in words)


def parse_bbox_xhtml(path, source_id, source_index):
    """Parse words and merge same-baseline PDF lines into physical rows."""
    path = Path(path)
    try:
        root = ET.parse(str(path)).getroot()
    except (ET.ParseError, OSError) as exc:
        raise ValueError("Cannot parse bbox XHTML %s: %s" % (path, exc))
    pages = [node for node in root.iter() if local_name(node.tag) == "page"]
    if not pages:
        raise ValueError("No <page> elements in bbox XHTML: " + str(path))
    output_pages = []
    for page_index, page in enumerate(pages, 1):
        try:
            width = number(page, "width")
            height = number(page, "height")
        except (KeyError, ValueError):
            raise ValueError("Each bbox page needs numeric width and height")
        original_lines = []
        for block_index, block in enumerate(
                [node for node in page.iter() if local_name(node.tag) == "block"], 1):
            lines = [node for node in list(block) if local_name(node.tag) == "line"]
            for line_index, line in enumerate(lines, 1):
                words = []
                for word_index, word in enumerate(
                        [node for node in line.iter() if local_name(node.tag) == "word"], 1):
                    try:
                        box = {key: number(word, key) for key in ("xMin", "yMin", "xMax", "yMax")}
                    except (KeyError, ValueError):
                        raise ValueError("Every bbox word needs four numeric coordinates")
                    if box["xMax"] < box["xMin"] or box["yMax"] < box["yMin"]:
                        raise ValueError("Inverted word bounding box in " + str(path))
                    value = word.text if word.text is not None else ""
                    if value == "":
                        continue
                    words.append({
                        "text": value,
                        "bbox": box,
                        "word_id": "s%03d-p%03d-b%03d-l%03d-w%03d" % (
                            source_index, page_index, block_index, line_index, word_index),
                    })
                if words:
                    words.sort(key=lambda item: (item["bbox"]["xMin"], item["bbox"]["yMin"]))
                    original_lines.append({
                        "words": words,
                        "bbox": bbox_union([word["bbox"] for word in words]),
                        "line_id": "s%03d-p%03d-b%03d-l%03d" % (
                            source_index, page_index, block_index, line_index),
                    })
        original_lines.sort(key=lambda row: (
            (row["bbox"]["yMin"] + row["bbox"]["yMax"]) / 2.0, row["bbox"]["xMin"]))
        physical_rows = []
        for line in original_lines:
            box = line["bbox"]
            center = (box["yMin"] + box["yMax"]) / 2.0
            target = None
            for candidate in reversed(physical_rows):
                other = candidate["bbox"]
                other_center = (other["yMin"] + other["yMax"]) / 2.0
                overlap = max(0.0, min(box["yMax"], other["yMax"]) - max(box["yMin"], other["yMin"]))
                minimum_height = max(0.001, min(box["yMax"] - box["yMin"], other["yMax"] - other["yMin"]))
                if abs(center - other_center) <= 0.5 * max(box["yMax"] - box["yMin"], other["yMax"] - other["yMin"]) \
                        and overlap / minimum_height >= 0.5:
                    target = candidate
                    break
                if other["yMax"] < box["yMin"]:
                    break
            if target is None:
                physical_rows.append({
                    "words": list(line["words"]),
                    "bbox": dict(box),
                    "source_line_ids": [line["line_id"]],
                })
            else:
                target["words"].extend(line["words"])
                target["words"].sort(key=lambda item: (item["bbox"]["xMin"], item["bbox"]["yMin"]))
                target["bbox"] = bbox_union([word["bbox"] for word in target["words"]])
                target["source_line_ids"].append(line["line_id"])
        for row_index, row in enumerate(physical_rows, 1):
            row["physical_row_id"] = "s%03d-p%03d-pr%03d" % (source_index, page_index, row_index)
            row["groups"] = split_coordinate_groups(row["words"], row["bbox"])
        output_pages.append({
            "page": page.attrib.get("number", str(page_index)),
            "page_index": page_index,
            "width": width,
            "height": height,
            "physical_rows": physical_rows,
            "source_id": source_id,
        })
    return output_pages


def split_coordinate_groups(words, row_box):
    """Split only at substantial horizontal whitespace, never within a word."""
    if not words:
        return []
    typical_height = statistics.median(
        word["bbox"]["yMax"] - word["bbox"]["yMin"] for word in words)
    gap_threshold = max(8.0, 0.65 * typical_height)
    groups = []
    current = [words[0]]
    for word in words[1:]:
        gap = word["bbox"]["xMin"] - current[-1]["bbox"]["xMax"]
        if gap >= gap_threshold:
            groups.append(current)
            current = [word]
        else:
            current.append(word)
    groups.append(current)
    return [{
        "text": text_of(group),
        "bbox": bbox_union([word["bbox"] for word in group]),
        "words": group,
        "gap_threshold": gap_threshold,
    } for group in groups]


def candidate_runs(rows):
    runs = []
    current = []
    for row in rows:
        if len(row["groups"]) >= 2:
            current.append(row)
        else:
            if len(current) >= 2:
                runs.append(current)
            current = []
    if len(current) >= 2:
        runs.append(current)
    return runs


def cluster_repeated_gaps(rows):
    """Find vertical gutters present in at least two physical rows."""
    entries = []
    heights = []
    for row_index, row in enumerate(rows):
        heights.append(row["bbox"]["yMax"] - row["bbox"]["yMin"])
        for left, right in zip(row["groups"], row["groups"][1:]):
            low = left["bbox"]["xMax"]
            high = right["bbox"]["xMin"]
            if high > low:
                entries.append({"low": low, "high": high,
                                "center": (low + high) / 2.0, "row": row_index})
    tolerance = max(3.0, 0.5 * statistics.median(heights))
    clusters = []
    for entry in sorted(entries, key=lambda item: item["center"]):
        selected = None
        for cluster in reversed(clusters):
            previous = cluster["entries"][-1]
            if previous["row"] == entry["row"]:
                continue
            overlap = max(0.0, min(previous["high"], entry["high"]) -
                          max(previous["low"], entry["low"]))
            if overlap > 0 or abs(previous["center"] - entry["center"]) <= tolerance:
                selected = cluster
                break
            if entry["center"] - previous["center"] > 2 * tolerance:
                break
        if selected is None:
            clusters.append({"entries": [entry]})
        else:
            selected["entries"].append(entry)
    needed_rows = min(2, len(rows))
    cuts = []
    support = []
    for cluster in clusters:
        rows_seen = {entry["row"] for entry in cluster["entries"]}
        if len(rows_seen) >= needed_rows:
            centers = [entry["center"] for entry in cluster["entries"]]
            cuts.append(statistics.median(centers))
            support.append(len(rows_seen))
    # One gap per column transition; avoid unstable near-duplicate gutters.
    deduplicated = []
    deduplicated_support = []
    for cut, count in sorted(zip(cuts, support)):
        if deduplicated and abs(cut - deduplicated[-1]) <= tolerance:
            if count > deduplicated_support[-1]:
                deduplicated[-1] = cut
                deduplicated_support[-1] = count
        else:
            deduplicated.append(cut)
            deduplicated_support.append(count)
    return deduplicated, deduplicated_support


def make_segment(rows, source_id, source_index, page, segment_id, cuts, cut_support):
    column_count = len(cuts) + 1
    segment_rows = []
    for row_index, row in enumerate(rows, 1):
        row_id = "%s-r%02d" % (segment_id, row_index)
        placed = []
        for group in row["groups"]:
            box = group["bbox"]
            left = bisect.bisect_right(cuts, box["xMin"])
            right = bisect.bisect_left(cuts, box["xMax"])
            right = max(left, min(column_count - 1, right))
            placed.append({"column_start": left, "column_end": right, "groups": [group]})
        merged = []
        for item in placed:
            if merged and item["column_start"] == merged[-1]["column_start"] \
                    and item["column_end"] == merged[-1]["column_end"]:
                merged[-1]["groups"].extend(item["groups"])
            else:
                merged.append(item)
        cells = []
        occupied = set()
        for item in merged:
            start = item["column_start"]
            end = item["column_end"]
            occupied.update(range(start, end + 1))
            words = [word for group in item["groups"] for word in group["words"]]
            words.sort(key=lambda word: word["bbox"]["xMin"])
            box = bbox_union([word["bbox"] for word in words])
            cells.append({
                "cell_id": "%s-c%02d%s" % (row_id, start + 1,
                                           "-c%02d" % (end + 1) if end > start else ""),
                "row_id": row_id,
                "column_start": start + 1,
                "column_end": end + 1,
                "text": text_of(words),
                "bbox": box,
                "source_id": source_id,
                "page": page["page_index"],
                "word_ids": [word["word_id"] for word in words],
                "spanning_geometry": end > start,
            })
        for column in range(column_count):
            if column not in occupied:
                cells.append({
                    "cell_id": "%s-c%02d" % (row_id, column + 1),
                    "row_id": row_id,
                    "column_start": column + 1,
                    "column_end": column + 1,
                    "text": None,
                    "bbox": None,
                    "source_id": source_id,
                    "page": page["page_index"],
                    "word_ids": [],
                    "spanning_geometry": False,
                })
        cells.sort(key=lambda cell: (cell["column_start"], cell["column_end"], cell["cell_id"]))
        for cell in cells:
            cell["paragraph_id"] = cell["cell_id"]
        segment_rows.append({
            "row_id": row_id,
            "physical_row_id": row["physical_row_id"],
            "bbox": row["bbox"],
            "source_line_ids": row["source_line_ids"],
            "cells": cells,
        })
    all_boxes = [row["bbox"] for row in segment_rows]
    header_cells = [cell["cell_id"] for cell in segment_rows[0]["cells"] if cell["text"]]
    return {
        "segment_id": segment_id,
        "source_id": source_id,
        "page": page["page_index"],
        "pdf_page_label": page["page"],
        "bbox": bbox_union(all_boxes),
        "column_count": column_count,
        "column_cuts": cuts,
        "relative_column_cuts": [cut / page["width"] for cut in cuts],
        "cut_row_support": cut_support,
        "header_row_ids": [segment_rows[0]["row_id"]],
        "data_row_ids": [row["row_id"] for row in segment_rows[1:]],
        "header_status": "geometric_candidate_requires_agent_review",
        "own_header_cell_ids": header_cells,
        "rows": segment_rows,
        "continued_from": None,
        "continuation_reason": None,
        "header_cell_ids_by_column": {},
    }


def header_text(segment, column):
    row_id = segment["header_row_ids"][0]
    row = next(row for row in segment["rows"] if row["row_id"] == row_id)
    return " ".join(cell["text"] or "" for cell in row["cells"]
                    if cell["column_start"] <= column <= cell["column_end"])


def continuation_comparison(previous, current):
    if previous["source_id"] != current["source_id"]:
        return False, "different source", 0.0, 0.0
    if current["page"] != previous["page"] + 1:
        return False, "not adjacent pages", 0.0, 0.0
    if previous["column_count"] != current["column_count"]:
        return False, "column count changed", 0.0, 0.0
    old_text = " | ".join(header_text(previous, col) for col in range(1, previous["column_count"] + 1))
    new_text = " | ".join(header_text(current, col) for col in range(1, current["column_count"] + 1))
    old_normalized = CONTINUATION_RE.sub("", old_text).strip().lower()
    new_normalized = CONTINUATION_RE.sub("", new_text).strip().lower()
    similarity = difflib.SequenceMatcher(None, old_normalized, new_normalized).ratio()
    if previous["relative_column_cuts"] and current["relative_column_cuts"]:
        geometry_delta = max(abs(a - b) for a, b in zip(
            previous["relative_column_cuts"], current["relative_column_cuts"]))
    else:
        geometry_delta = 0.0
    explicit = bool(CONTINUATION_RE.search(new_text))
    if explicit and geometry_delta <= 0.10:
        return True, "explicit continued header plus compatible columns", similarity, geometry_delta
    if similarity >= 0.65 and geometry_delta <= 0.04:
        return True, "repeated header and column cuts match across adjacent pages", similarity, geometry_delta
    return False, "insufficient continuation evidence", similarity, geometry_delta


def build_layout(inputs, label=DEFAULT_LABEL):
    """Build layout and table documents for [(source_id, bbox_path), ...]."""
    all_layout_pages = []
    tables = []
    segment_counter = 0
    for source_index, (source_id, path) in enumerate(inputs, 1):
        pages = parse_bbox_xhtml(path, source_id, source_index)
        all_layout_pages.extend(pages)
        previous_segment = None
        previous_table = None
        for page in pages:
            runs = candidate_runs(page["physical_rows"])
            for run in runs:
                cuts, support = cluster_repeated_gaps(run)
                if not cuts or len(cuts) > 30:
                    continue
                segment_counter += 1
                segment_id = "s%03d-seg%03d" % (source_index, segment_counter)
                segment = make_segment(run, source_id, source_index, page, segment_id, cuts, support)
                is_continuation = False
                if previous_segment is not None:
                    is_continuation, reason, similarity, delta = continuation_comparison(previous_segment, segment)
                    if is_continuation:
                        table = previous_table
                        segment["table_id"] = table["table_id"]
                        segment["continued_from"] = previous_segment["segment_id"]
                        segment["continuation_reason"] = reason
                        segment["continuation_header_similarity"] = round(similarity, 4)
                        segment["continuation_cut_delta"] = round(delta, 4)
                        for column in range(1, segment["column_count"] + 1):
                            inherited = previous_segment["header_cell_ids_by_column"].get(str(column), [])
                            own = [cell["cell_id"] for cell in segment["rows"][0]["cells"]
                                   if cell["text"] and cell["column_start"] <= column <= cell["column_end"]]
                            segment["header_cell_ids_by_column"][str(column)] = inherited + own
                        table["segments"].append(segment)
                if not is_continuation:
                    table = {"table_id": "s%03d-table%03d" % (source_index, len(tables) + 1),
                             "source_id": source_id, "segments": []}
                    segment["table_id"] = table["table_id"]
                    for column in range(1, segment["column_count"] + 1):
                        segment["header_cell_ids_by_column"][str(column)] = [
                            cell["cell_id"] for cell in segment["rows"][0]["cells"]
                            if cell["text"] and cell["column_start"] <= column <= cell["column_end"]]
                    table["segments"].append(segment)
                    tables.append(table)
                previous_segment = segment
                previous_table = table
            # Only a trailing segment can continue as the first segment on the next page.
            if runs:
                last_run = runs[-1]
                if previous_segment is None or previous_segment["rows"][-1]["physical_row_id"] != last_run[-1]["physical_row_id"]:
                    previous_segment = None
                    previous_table = None
            else:
                previous_segment = None
                previous_table = None
    layout = {"schema_version": "table-coordinate-forge/layout-v1",
              "label": label, "created_at": utc_now(), "pages": all_layout_pages,
              "coordinate_convention": "PDF points as supplied by pdftotext; origin at upper-left"}
    table_document = {"schema_version": "table-coordinate-forge/tables-v1",
                      "label": label, "created_at": utc_now(), "tables": tables,
                      "promotion_policy": "Candidates only; a reviewed binding is mandatory for every field."}
    return layout, table_document


def markdown_preview(table_document, layout):
    lines = ["# " + table_document["label"], "",
             "Candidate reconstruction only. Cell values are not requested-field answers.", ""]
    if not table_document["tables"]:
        lines += ["No candidate table satisfied the repeated-gutter rules.", ""]
    for table in table_document["tables"]:
        lines += ["## %s — %s" % (table["table_id"], table["source_id"]), ""]
        for segment in table["segments"]:
            continuation = segment["continued_from"] or "none"
            lines += ["### %s — PDF page %s" % (segment["segment_id"], segment["pdf_page_label"]), "",
                      "Continued from: `%s`; headers: **%s**." % (continuation, segment["header_status"]), ""]
            lines += ["| Row ID | " + " | ".join("Column %d" % col for col in range(1, segment["column_count"] + 1)) + " |",
                      "|---|" + "---|" * segment["column_count"]]
            for row in segment["rows"]:
                values = []
                for col in range(1, segment["column_count"] + 1):
                    matches = [cell for cell in row["cells"]
                               if cell["column_start"] <= col <= cell["column_end"]]
                    if not matches:
                        values.append("")
                    else:
                        cell = matches[0]
                        value = "∅" if cell["text"] is None else cell["text"].replace("|", "\\|")
                        values.append(value + "<br>`%s`" % cell["cell_id"])
                lines.append("| `%s` | %s |" % (row["row_id"], " | ".join(values)))
            for column, ids in sorted(segment["header_cell_ids_by_column"].items(), key=lambda item: int(item[0])):
                lines.append("")
                lines.append("Column %s effective header path: %s" % (column, ", ".join("`%s`" % item for item in ids)))
            lines.append("")
    return "\n".join(lines) + "\n"


def svg_preview(table_document):
    """Portable vector preview made only of SVG text and geometry primitives."""
    width = 1200
    y = 30.0
    parts = ["<svg xmlns=\"http://www.w3.org/2000/svg\" width=\"1200\" height=\"100\" viewBox=\"0 0 1200 100\">",
             "<rect width=\"100%\" height=\"100%\" fill=\"white\"/>",
             "<g font-family=\"monospace\" font-size=\"12\" fill=\"#17202a\">"]
    def add_text(x, baseline, value, weight="normal", size="12"):
        parts.append("<text x=\"%.2f\" y=\"%.2f\" font-weight=\"%s\" font-size=\"%s\">%s</text>" % (
            x, baseline, weight, size, html.escape(str(value))))
    add_text(20, y, table_document["label"], "bold", "18")
    y += 30
    add_text(20, y, "Candidate cells only; no requested field is promoted by this preview.")
    y += 30
    for table in table_document["tables"]:
        add_text(20, y, table["table_id"] + " — " + table["source_id"], "bold", "15")
        y += 25
        for segment in table["segments"]:
            col_width = min(280.0, 1150.0 / segment["column_count"])
            add_text(20, y, "%s | PDF page %s | continued from %s" % (
                segment["segment_id"], segment["pdf_page_label"], segment["continued_from"] or "none"), "bold")
            y += 8
            for row in segment["rows"]:
                y += 22
                add_text(10, y + 13, row["row_id"], "normal", "9")
                for col in range(1, segment["column_count"] + 1):
                    x = 150 + (col - 1) * col_width
                    matches = [cell for cell in row["cells"] if cell["column_start"] <= col <= cell["column_end"]]
                    parts.append("<rect x=\"%.2f\" y=\"%.2f\" width=\"%.2f\" height=\"22\" fill=\"none\" stroke=\"#90a4ae\"/>" % (
                        x, y, col_width - 3))
                    if matches:
                        cell = matches[0]
                        text = "∅" if cell["text"] is None else cell["text"]
                        # SVG text remains inspectable/searchable; long cells are visibly clipped by preview width.
                        add_text(x + 4, y + 12, text[:44])
                        add_text(x + 4, y + 20, cell["cell_id"], "normal", "7")
            y += 35
    parts[0] = "<svg xmlns=\"http://www.w3.org/2000/svg\" width=\"1200\" height=\"%d\" viewBox=\"0 0 1200 %d\">" % (
        int(math.ceil(y + 20)), int(math.ceil(y + 20)))
    parts.append("</g></svg>")
    return "\n".join(parts) + "\n"


def save_layout(layout, table_document, output_dir):
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    write_json(output_dir / "layout.json", layout)
    write_json(output_dir / "tables.json", table_document)
    atomic_write_text(output_dir / "table-preview.md", markdown_preview(table_document, layout))
    atomic_write_text(output_dir / "table-preview.svg", svg_preview(table_document))


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bbox", required=True, help="pdftotext -bbox-layout XHTML")
    parser.add_argument("--source-id", default="source-001")
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--label", default=DEFAULT_LABEL)
    args = parser.parse_args(argv)
    layout, tables = build_layout([(args.source_id, args.bbox)], args.label)
    save_layout(layout, tables, args.output_dir)
    print(json.dumps({"pages": len(layout["pages"]), "tables": len(tables["tables"]),
                      "output_dir": args.output_dir}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
