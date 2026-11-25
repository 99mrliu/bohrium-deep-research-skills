#!/usr/bin/env python3
"""Independently observe visible semantics in SVG and source CSV files.

This module intentionally has no dependency on any renderer, IR, truth table, or
expected matrix. It reports structural observations only.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import sys
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any

SCHEMA = "dual-artifact-quality-gate/observations-v1"
QC_KIND = "data-qc-kind"
QC_ID = "data-qc-id"
INKSCAPE = "{http://www.inkscape.org/namespaces/inkscape}"
SVG = "{http://www.w3.org/2000/svg}"
GRAPHICAL = {"rect", "circle", "ellipse", "line", "polyline", "polygon", "path", "use"}
NUMBER = re.compile(r"^[+-]?(?:0|[1-9][0-9]*)(?:\.[0-9]+)?(?:[eE][+-]?[0-9]+)?$")


def local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def dump_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def numeric(value: str) -> Any:
    value = value.strip()
    if not NUMBER.match(value):
        return value
    try:
        if "." not in value and "e" not in value.lower():
            return int(value)
        result = float(value)
        return result if result == result and abs(result) != float("inf") else value
    except ValueError:
        return value


def style_record(element: ET.Element) -> dict[str, Any]:
    """Observe inline presentation, falling back to the first visible graphic child."""
    target = element
    if local(element.tag) not in GRAPHICAL:
        for child in list(element):
            if local(child.tag) in GRAPHICAL and not hidden(child, False):
                target = child
                break
    record: dict[str, Any] = {}
    for name in ("fill", "stroke", "stroke-width", "stroke-dasharray", "opacity", "marker-end"):
        if name in element.attrib:
            record[name] = element.attrib[name]
        elif name in target.attrib:
            record[name] = target.attrib[name]
    declarations = element.attrib.get("style", "") + ";" + target.attrib.get("style", "")
    for item in declarations.split(";"):
        if ":" in item:
            key, value = item.split(":", 1)
            if key.strip() in {"fill", "stroke", "stroke-width", "stroke-dasharray", "opacity", "marker-end"}:
                record[key.strip()] = value.strip()
    return record


def hidden(element: ET.Element, inherited: bool) -> bool:
    style = element.attrib.get("style", "").replace(" ", "")
    return inherited or element.attrib.get("display") == "none" or \
        element.attrib.get("visibility") in {"hidden", "collapse"} or \
        "display:none" in style or "visibility:hidden" in style


def label_of(element: ET.Element) -> str:
    pieces: list[str] = []
    for text_element in element.iter():
        if local(text_element.tag) == "text":
            pieces.append("".join(text_element.itertext()))
    if not pieces and local(element.tag) in {"text", "tspan", "textPath"}:
        pieces.append("".join(element.itertext()))
    return " ".join(" ".join(pieces).split())


def geometry(element: ET.Element) -> dict[str, Any]:
    names = ("x", "y", "x1", "y1", "x2", "y2", "width", "height", "cx", "cy", "r", "d", "points", "transform")
    result: dict[str, Any] = {}
    for name in names:
        if name in element.attrib:
            value: Any = element.attrib[name]
            if name not in {"d", "points", "transform"}:
                plain = value.strip().removesuffix("px")
                value = numeric(plain)
            result[name] = value
    if local(element.tag) not in GRAPHICAL:
        for child in element.iter():
            if local(child.tag) in GRAPHICAL:
                child_geometry = geometry(child)
                for key, value in child_geometry.items():
                    result.setdefault(key, value)
    return result


def marker_id(value: str | None) -> Any:
    if value is None:
        return None
    match = re.fullmatch(r"url\(\s*#([^\)\s]+)\s*\)", value.strip())
    return match.group(1) if match else value


def parse_view_box(value: str | None) -> list[float] | None:
    if not value:
        return None
    try:
        return [float(item) for item in re.split(r"[\s,]+", value.strip())]
    except ValueError:
        return None


def observe_svg(path: Path) -> tuple[dict[str, Any], list[str], list[str]]:
    limitations: list[str] = []
    errors: list[str] = []
    result: dict[str, Any] = {
        "path": path.name,
        "sha256": sha256(path),
        "entities": {},
        "edges": {},
        "legend_items": {},
        "chart_values": {},
        "layers": [],
        "layer_set": [],
        "texts": [],
        "text_count": 0,
        "element_count": 0,
        "ids": [],
    }
    try:
        root = ET.parse(path).getroot()
    except (ET.ParseError, OSError) as exc:
        errors.append(f"SVG_PARSE_ERROR: {exc}")
        return result, limitations, errors
    if local(root.tag) != "svg":
        errors.append(f"SVG_ROOT_INVALID: expected svg, got {local(root.tag)}")
    result["view_box"] = parse_view_box(root.attrib.get("viewBox"))
    result["width"] = root.attrib.get("width")
    result["height"] = root.attrib.get("height")
    result["element_count"] = sum(1 for _ in root.iter())

    seen: dict[str, set[str]] = {"entity": set(), "edge": set(), "legend-item": set(), "chart-value": set()}
    layer_names: list[str] = []

    def add_observed(kind: str, identifier: str, record: dict[str, Any], target: dict[str, Any]) -> None:
        if identifier in seen[kind]:
            errors.append(f"DUPLICATE_QC_ID: {kind}:{identifier}")
            return
        seen[kind].add(identifier)
        target[identifier] = record

    def walk(element: ET.Element, inherited_hidden: bool = False, layer: str | None = None) -> None:
        is_hidden = hidden(element, inherited_hidden)
        current_layer = layer
        if local(element.tag) == "g":
            layer_value = element.attrib.get("data-qc-layer")
            if element.attrib.get(INKSCAPE + "groupmode") == "layer":
                layer_value = element.attrib.get(INKSCAPE + "label") or element.attrib.get("id") or layer_value
            if layer_value:
                current_layer = layer_value
                if not is_hidden:
                    layer_names.append(layer_value)
        if not is_hidden:
            identifier = element.attrib.get("id") or element.attrib.get(QC_ID)
            if identifier:
                result["ids"].append(identifier)
            if local(element.tag) == "text":
                text = " ".join("".join(element.itertext()).split())
                if text:
                    result["texts"].append({"id": element.attrib.get("id"), "text": text, "layer": current_layer})
            kind = element.attrib.get(QC_KIND)
            qid = element.attrib.get(QC_ID)
            if kind and kind not in seen:
                errors.append(f"UNKNOWN_QC_KIND: {kind}")
            if kind in seen and not qid:
                errors.append(f"MISSING_QC_ID: {kind}")
            if kind in seen and qid:
                base: dict[str, Any] = {
                    "label": label_of(element),
                    "layer": current_layer,
                    "style": style_record(element),
                    "geometry": geometry(element),
                }
                if kind == "entity":
                    add_observed(kind, qid, base, result["entities"])
                elif kind == "edge":
                    base.update({
                        "from": element.attrib.get("data-from"),
                        "to": element.attrib.get("data-to"),
                        "order": numeric(element.attrib["data-order"]) if "data-order" in element.attrib else None,
                        "marker_start": marker_id(element.attrib.get("marker-start")),
                        "marker_mid": marker_id(element.attrib.get("marker-mid")),
                        "marker_end": marker_id(element.attrib.get("marker-end")),
                    })
                    add_observed(kind, qid, base, result["edges"])
                elif kind == "legend-item":
                    base["target"] = element.attrib.get("data-target")
                    add_observed(kind, qid, base, result["legend_items"])
                elif kind == "chart-value":
                    base.update({
                        "series": element.attrib.get("data-series"),
                        "key": element.attrib.get("data-key"),
                        "value": numeric(element.attrib.get("data-value", "")),
                        "unit": element.attrib.get("data-unit"),
                    })
                    add_observed(kind, qid, base, result["chart_values"])
        for child in list(element):
            walk(child, is_hidden, current_layer)

    walk(root)
    result["layers"] = sorted(set(layer_names))
    result["layer_set"] = sorted(set(layer_names))
    result["text_count"] = len(result["texts"])
    result["ids"] = sorted(set(result["ids"]))
    if result["text_count"] == 0:
        limitations.append("No visible SVG text elements observed; text may be outlines or hidden.")
    if not any(result[key] for key in ("entities", "edges", "legend_items", "chart_values")):
        limitations.append("No data-qc-kind semantic elements observed; only raw SVG structure/text is available.")
    return result, limitations, errors


def observe_csv(path: Path) -> tuple[dict[str, Any], list[str], list[str]]:
    limitations: list[str] = []
    errors: list[str] = []
    result: dict[str, Any] = {"path": path.name, "sha256": sha256(path)}
    try:
        with path.open("r", encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle)
            columns = list(reader.fieldnames or [])
            rows = [dict(row) for row in reader]
    except (OSError, UnicodeError, csv.Error) as exc:
        errors.append(f"CSV_PARSE_ERROR: {path.name}: {exc}")
        return result, limitations, errors
    result["columns"] = columns
    result["rows"] = rows
    values: dict[str, Any] = {}
    category_column = "category" if "category" in columns else "key" if "key" in columns else None
    if "value" in columns and category_column:
        for index, row in enumerate(rows, start=2):
            series = row.get("series", "") or ""
            category = row.get(category_column, "") or ""
            key = f"{series}|{category}"
            if key in values:
                limitations.append(f"Duplicate CSV key {key!r} in {path.name}; first value retained.")
                continue
            values[key] = {
                "value": numeric(row.get("value", "") or ""),
                "unit": row.get("unit"),
                "row": index,
                "series": series,
                "category": category,
            }
    else:
        limitations.append(f"CSV {path.name} has no series/category/value projection; raw rows remain available.")
    result["values"] = values
    return result, limitations, errors


def build_observations(svg_path: Path, csv_paths: list[Path]) -> dict[str, Any]:
    svg, svg_limitations, svg_errors = observe_svg(svg_path)
    limitations = list(svg_limitations)
    errors = list(svg_errors)
    csv_records: dict[str, Any] = {}
    for csv_path in csv_paths:
        record, csv_limitations, csv_errors = observe_csv(csv_path)
        if csv_path.name in csv_records:
            errors.append(f"CSV_BASENAME_COLLISION: {csv_path.name}")
            continue
        csv_records[csv_path.name] = record
        limitations.extend(csv_limitations)
        errors.extend(csv_errors)
    return {
        "schema": SCHEMA,
        "observer": "artifact_observer.py",
        "independence": "SVG/CSV only; no IR, truth table, expected matrix, or renderer import",
        "scientific_correctness": "not evaluated",
        "svg": svg,
        "csv": csv_records,
        "parser_limitations": sorted(set(limitations)),
        "errors": sorted(set(errors)),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--svg", type=Path, required=True)
    parser.add_argument("--csv", type=Path, action="append", default=[])
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        record = build_observations(args.svg, args.csv)
    except OSError as exc:
        record = {
            "schema": SCHEMA,
            "observer": "artifact_observer.py",
            "independence": "SVG/CSV only; no IR, truth table, expected matrix, or renderer import",
            "scientific_correctness": "not evaluated",
            "svg": {"path": args.svg.name}, "csv": {}, "parser_limitations": [],
            "errors": [f"INPUT_ERROR: {exc}"],
        }
    dump_json(args.output, record)
    return 2 if record["errors"] else 0


if __name__ == "__main__":
    sys.exit(main())
