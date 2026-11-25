#!/usr/bin/env python3
"""ID-scoped source SVG edits with machine-checked unchanged subtrees."""
from __future__ import annotations

import copy
import re
from pathlib import Path
from xml.etree import ElementTree as ET

from topology import TopologyError, sha256_bytes


def load_source_svg(path: Path):
    try:
        raw = path.read_bytes()
        root = ET.fromstring(raw)
    except (OSError, ET.ParseError) as exc:
        raise TopologyError(f"cannot parse source SVG {path}: {exc}") from exc
    if root.tag.split("}")[-1] != "svg":
        raise TopologyError("source figure is not an SVG root element")
    return raw, root


def source_from_pdf(path: Path, page_number: int, work_dir: Path):
    try:
        import pymupdf
        with pymupdf.open(str(path)) as document:
            if page_number < 0 or page_number >= document.page_count:
                raise TopologyError(f"source_pdf page {page_number} is out of range")
            svg = document[page_number].get_svg_image(text_as_path=False).encode("utf-8")
    except TopologyError:
        raise
    except Exception as exc:
        raise TopologyError(f"cannot extract source PDF page as SVG: {exc}") from exc
    derived = work_dir / f"source-page-{page_number + 1}.svg"
    derived.write_bytes(svg)
    raw, root = load_source_svg(derived)
    return raw, root, derived


def _index(root):
    result = {}
    for element in root.iter():
        element_id = element.get("id")
        if element_id:
            if element_id in result:
                raise TopologyError(f"source SVG contains duplicate id {element_id}")
            result[element_id] = element
    return result


def apply_svg_operation(root, operation, index):
    op = operation.get("op")
    target_id = operation.get("id")
    if op not in {"update_svg_text", "update_svg_attr"}:
        raise TopologyError(f"unsupported source SVG operation {op!r}")
    if not isinstance(target_id, str) or target_id not in _index(root):
        raise TopologyError(f"{op} target id {target_id!r} does not exist in source SVG")
    target = _index(root)[target_id]
    if op == "update_svg_text":
        value = operation.get("text")
        if not isinstance(value, str):
            raise TopologyError("update_svg_text.text must be a string")
        if target.tag.split("}")[-1] not in {"text", "tspan", "title", "desc"}:
            raise TopologyError(f"SVG text target {target_id} must itself be text/tspan/title/desc")
        before = target.text or ""
        target.text = value
        return {"target_id": target_id, "attribute": "text", "before": before, "after": value}
    name = operation.get("name")
    value = operation.get("value")
    if not isinstance(name, str) or not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_.:-]*", name):
        raise TopologyError("update_svg_attr.name is not a safe XML attribute")
    local = name.split(":")[-1].lower()
    if local.startswith("on") or local in {"href", "src", "script"}:
        raise TopologyError(f"refusing active/external SVG attribute {name}")
    if not isinstance(value, (str, int, float)):
        raise TopologyError("update_svg_attr.value must be a string or number")
    before = target.get(name)
    target.set(name, str(value))
    return {"target_id": target_id, "attribute": name, "before": before, "after": str(value)}


def finalize_source_svg(original_root, edited_root, target_ids):
    """Verify that subtrees neither targeted nor containing a target are unchanged."""
    before_index = _index(original_root)
    after_index = _index(edited_root)
    if set(before_index) != set(after_index):
        raise TopologyError("source edit unexpectedly changed the set of SVG IDs")
    target_ancestors = set()
    for target_id in target_ids:
        # Ancestors are expected to differ because their descendant changed.
        current = after_index[target_id]
        # ElementTree has no parent pointers; compute paths instead.
        def mark_ancestors(node, ancestors):
            if node is current:
                target_ancestors.update(ancestors)
                return True
            return any(mark_ancestors(child, ancestors + [node]) for child in list(node))
        mark_ancestors(edited_root, [])
    original_all = list(original_root.iter())
    edited_all = list(edited_root.iter())
    if len(original_all) != len(edited_all):
        raise TopologyError("source edit changed SVG element count")
    unchanged_count = 0
    for original, edited in zip(original_all, edited_all):
        if original.tag != edited.tag or original.get("id") != edited.get("id"):
            raise TopologyError("source edit changed element ordering or identity")
        if edited not in target_ancestors and edited.get("id") not in target_ids:
            if ET.tostring(original, encoding="utf-8") != ET.tostring(edited, encoding="utf-8"):
                raise TopologyError(f"undeclared source SVG change near id {edited.get('id')!r}")
            unchanged_count += 1
    result = ET.tostring(edited_root, encoding="utf-8", xml_declaration=True)
    return result, {"target_ids": sorted(target_ids), "unchanged_element_count": unchanged_count, "preservation_verified": True}
