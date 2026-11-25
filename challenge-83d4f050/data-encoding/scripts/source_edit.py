#!/usr/bin/env python3
"""Independent source-preserving SVG editor for data-encoding cases."""
from __future__ import annotations

import re
from pathlib import Path
from xml.etree import ElementTree as ET

from data_core import DataError


def load_svg(path):
    try:
        raw = path.read_bytes()
        root = ET.fromstring(raw)
    except (OSError, ET.ParseError) as exc:
        raise DataError(f"cannot parse source SVG {path}: {exc}") from exc
    if root.tag.split("}")[-1] != "svg":
        raise DataError("source figure root is not SVG")
    ids = [element.get("id") for element in root.iter() if element.get("id")]
    if len(ids) != len(set(ids)):
        raise DataError("source SVG IDs must be unique for source-preserving edits")
    return raw, root


def svg_from_pdf(path, page_number, work_dir):
    try:
        import pymupdf
        with pymupdf.open(str(path)) as document:
            if page_number < 0 or page_number >= document.page_count:
                raise DataError("source PDF page is out of range")
            svg = document[page_number].get_svg_image(text_as_path=False).encode("utf-8")
    except DataError:
        raise
    except Exception as exc:
        raise DataError(f"cannot extract source PDF SVG: {exc}") from exc
    derived = work_dir / f"source-page-{page_number + 1}.svg"
    derived.write_bytes(svg)
    raw, root = load_svg(derived)
    return raw, root, derived


def edit_svg(original_root, edited_root, operations):
    original_all = list(original_root.iter())
    edited_all = list(edited_root.iter())
    if len(original_all) != len(edited_all):
        raise DataError("source edits may not add/remove SVG elements")
    changes, targets = [], []
    for index, operation in enumerate(operations):
        op = operation.get("op")
        if op not in {"update_svg_text", "update_svg_attr"}:
            continue
        target_id = operation.get("id")
        matches = [element for element in edited_root.iter() if element.get("id") == target_id]
        if len(matches) != 1:
            raise DataError(f"{op} target {target_id!r} is not a unique source SVG ID")
        target = matches[0]
        if op == "update_svg_text":
            if target.tag.split("}")[-1] not in {"text", "tspan", "title", "desc"} or not isinstance(operation.get("text"), str):
                raise DataError("update_svg_text needs a text/tspan/title/desc target and string text")
            before, after = target.text or "", operation["text"]
            target.text = after
            attribute = "text"
        else:
            name, value = operation.get("name"), operation.get("value")
            if not isinstance(name, str) or not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_.:-]*", name):
                raise DataError("unsafe update_svg_attr.name")
            if name.split(":")[-1].lower().startswith("on") or name.split(":")[-1].lower() in {"href", "src", "script"}:
                raise DataError("active/external SVG attributes are forbidden")
            if not isinstance(value, (str, int, float)):
                raise DataError("update_svg_attr.value must be string or number")
            before, after, attribute = target.get(name), str(value), name
            target.set(name, after)
        targets.append(target_id)
        changes.append({"operation_index": index, "op": op, "target_id": target_id, "attribute": attribute, "before": before, "after": after, "changed": before != after, "unchanged": "All non-target SVG subtrees"})
    if not targets:
        return ET.tostring(original_root, encoding="utf-8", xml_declaration=True), changes, {"target_ids": [], "preservation_verified": True}
    ancestors = set()
    for target_id in targets:
        target = next(element for element in edited_root.iter() if element.get("id") == target_id)
        def visit(node, path):
            if node is target:
                ancestors.update(path)
                return True
            return any(visit(child, path + [node]) for child in list(node))
        visit(edited_root, [])
    unchanged_count = 0
    for original, edited in zip(original_all, edited_all):
        if original.tag != edited.tag or original.get("id") != edited.get("id"):
            raise DataError("source edit changed SVG element identity/order")
        if edited not in ancestors and edited.get("id") not in targets:
            if ET.tostring(original) != ET.tostring(edited):
                raise DataError(f"undeclared SVG change near {edited.get('id')!r}")
            unchanged_count += 1
    return ET.tostring(edited_root, encoding="utf-8", xml_declaration=True), changes, {"target_ids": sorted(targets), "unchanged_element_count": unchanged_count, "preservation_verified": True}
