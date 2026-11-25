#!/usr/bin/env python3
"""Apply a source-preserving, exact-once XML patch to an existing SVG.

No layout is regenerated. Before/after XML and unmodified element signatures
are checked. Only the explicitly targeted element may change.
"""
import argparse
import hashlib
import json
from pathlib import Path
import xml.etree.ElementTree as ET


def canonical_elements(svg_bytes):
    root = ET.fromstring(svg_bytes)
    result = {}
    for element in root.iter():
        eid = element.attrib.get("id")
        if eid:
            if eid in result:
                raise ValueError(f"Duplicate XML id: {eid}")
            result[eid] = ET.tostring(element, encoding="utf-8")
    return root, result


def digest(value):
    return hashlib.sha256(value).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--svg", required=True, type=Path)
    parser.add_argument("--instruction", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--audit", required=True, type=Path)
    args = parser.parse_args()
    instruction = json.loads(args.instruction.read_text(encoding="utf-8"))
    target_id = instruction["target_id"]
    old = instruction["expected_old"]
    new = instruction["replacement"]
    if old == new or not old:
        raise ValueError("expected_old and replacement must be nonempty and different.")
    original = args.svg.read_bytes()
    text = original.decode("utf-8")
    count = text.count(old)
    if count != 1:
        raise ValueError(f"Exact source fragment must occur once; found {count}. No file was written.")
    root, before = canonical_elements(original)
    if target_id not in before:
        raise ValueError(f"target_id {target_id!r} is absent. No file was written.")
    changed = text.replace(old, new, 1).encode("utf-8")
    changed_root, after = canonical_elements(changed)
    if set(before) != set(after):
        raise ValueError("Patch would add/remove IDs; split explicit structural edits into an audited instruction set.")
    if before[target_id] == after[target_id]:
        raise ValueError("The exact replacement is outside the target subtree; patch rejected.")
    original_elements = {e.attrib.get("id"): e for e in root.iter() if e.attrib.get("id")}
    changed_elements = {e.attrib.get("id"): e for e in changed_root.iter() if e.attrib.get("id")}
    parents = {child: parent for parent in root.iter() for child in parent}
    allowed_ancestors = set()
    current = original_elements[target_id]
    while current in parents:
        current = parents[current]
        if current.attrib.get("id"):
            allowed_ancestors.add(current.attrib["id"])
    for eid in before:
        if eid == target_id:
            continue
        # Ancestors serialize differently when a descendant changes, but their
        # own IDs and every attribute (including style/class) must remain exact.
        if original_elements[eid].attrib != changed_elements[eid].attrib:
            raise ValueError(f"Unmodified attributes/styles on {eid!r} changed; patch rejected.")
        if before[eid] != after[eid] and eid not in allowed_ancestors:
            raise ValueError(f"Unmodified element {eid!r} changed; patch rejected.")
    target = changed_elements[target_id]
    if instruction.get("expected_style_unchanged"):
        old_target = original_elements[target_id]
        if old_target.attrib.get("style") != target.attrib.get("style"):
            raise ValueError("Target style changed despite expected_style_unchanged.")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(changed)
    audit = {
        "status": "success", "method": "exact-once targeted XML patch; no SVG rebuild",
        "source": str(args.svg.resolve()), "output": str(args.output.resolve()),
        "target_id": target_id, "source_sha256": digest(original), "output_sha256": digest(changed),
        "unmodified_id_count": len(before) - 1,
        "target_ancestor_ids_allowed_subtree_serialization_only": sorted(allowed_ancestors),
        "all_unmodified_ids_styles_preserved": True,
    }
    args.audit.parent.mkdir(parents=True, exist_ok=True)
    args.audit.write_text(json.dumps(audit, indent=2, sort_keys=True) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
