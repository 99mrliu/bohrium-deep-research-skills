#!/usr/bin/env python3
"""Auditable source-preserving SVG/XML diff with an explicit edit allowlist."""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def identifier(element: ET.Element) -> str | None:
    return element.attrib.get("id") or element.attrib.get("data-qc-id")


def normalized_text(element: ET.Element) -> str:
    text = element.text or ""
    return " ".join(text.split()) if text.strip() else ""


def child_names(element: ET.Element) -> list[str]:
    counts: dict[str, int] = {}
    names = []
    for child in list(element):
        qid = identifier(child)
        if qid:
            names.append(f"id:{qid}")
        else:
            tag = child.tag
            counts[tag] = counts.get(tag, 0) + 1
            names.append(f"anonymous:{tag}#{counts[tag]}")
    return names


def local_changes(before: ET.Element, after: ET.Element) -> dict[str, Any]:
    changes: dict[str, Any] = {}
    if before.tag != after.tag:
        changes["tag"] = {"before": before.tag, "after": after.tag}
    for name in sorted(set(before.attrib) | set(after.attrib)):
        if before.attrib.get(name) != after.attrib.get(name):
            changes[f"attribute:{name}"] = {
                "before": before.attrib.get(name), "after": after.attrib.get(name)
            }
    if normalized_text(before) != normalized_text(after):
        changes["text"] = {"before": normalized_text(before), "after": normalized_text(after)}
    if child_names(before) != child_names(after):
        changes["children"] = {"before": child_names(before), "after": child_names(after)}
    return changes


def build_diff(before_path: Path, after_path: Path, intent: dict[str, Any]) -> dict[str, Any]:
    errors: list[dict[str, Any]] = []
    unauthorized: list[dict[str, Any]] = []
    try:
        before_root = ET.parse(before_path).getroot()
        after_root = ET.parse(after_path).getroot()
    except (OSError, ET.ParseError) as exc:
        return {
            "schema": "dual-artifact-quality-gate/source-edit-diff-v1",
            "status": "fail", "errors": [{"code": "EDIT_XML_PARSE_ERROR", "message": str(exc)}],
            "unauthorized_changes": [], "changed_ids": [], "required_preserve_ids": []
        }
    before_keys = [identifier(e) for e in before_root.iter() if identifier(e)]
    after_keys = [identifier(e) for e in after_root.iter() if identifier(e)]
    for label, keys in (("before", before_keys), ("after", after_keys)):
        for qid in sorted(set(keys)):
            if keys.count(qid) > 1:
                errors.append({"code": "DUPLICATE_XML_ID", "artifact": label, "id": qid})
    before_ids = {identifier(e): e for e in before_root.iter() if identifier(e)}
    after_ids = {identifier(e): e for e in after_root.iter() if identifier(e)}
    allowed: dict[str, dict[str, Any]] = {}
    for entry in intent.get("allowed_changes", []):
        if not isinstance(entry, dict) or not isinstance(entry.get("id"), str) or not entry.get("id"):
            errors.append({"code": "EDIT_ALLOWLIST_ENTRY_INVALID", "entry": entry})
            continue
        if entry["id"] in allowed:
            errors.append({"code": "EDIT_ALLOWLIST_ID_DUPLICATE", "id": entry["id"]})
        allowed[entry["id"]] = entry
    required = set(intent.get("required_preserve_ids", []))
    changed_ids: list[dict[str, Any]] = []
    for qid in sorted(set(before_ids) | set(after_ids)):
        old = before_ids.get(qid)
        new = after_ids.get(qid)
        rule = allowed.get(qid, {})
        if old is None or new is None:
            change = {"id": qid, "change": "added" if old is None else "removed"}
            changed_ids.append(change)
            permitted = (old is None and rule.get("add") is True) or (new is None and rule.get("remove") is True)
            if not permitted:
                unauthorized.append({**change, "code": "UNDECLARED_ID_ADD" if old is None else "UNDECLARED_ID_REMOVE"})
            if qid in required:
                unauthorized.append({**change, "code": "REQUIRED_ID_CHANGED"})
            continue
        changes = local_changes(old, new)
        if not changes:
            continue
        changed_ids.append({"id": qid, "changes": changes})
        allowed_fields = set(rule.get("attributes", []))
        # `attributes` uses XML names, with pseudo-fields text/children/tag.
        permitted_names = allowed_fields | {f"attribute:{name}" for name in allowed_fields}
        for field, detail in changes.items():
            normalized_field = "attribute:text" if field == "attribute:text" else field
            if normalized_field not in permitted_names and field not in allowed_fields:
                unauthorized.append({"id": qid, "field": field, "detail": detail,
                                     "code": "UNDECLARED_ATTRIBUTE_CHANGE"})
        if qid in required:
            unauthorized.append({"id": qid, "code": "REQUIRED_ID_CHANGED", "changes": changes})
    for qid in sorted(required):
        if qid not in before_ids or qid not in after_ids:
            errors.append({"code": "REQUIRED_PRESERVE_ID_MISSING", "id": qid})
    for qid, rule in sorted(allowed.items()):
        if rule.get("add") and qid in before_ids:
            errors.append({"code": "ALLOWED_ADD_ALREADY_EXISTS", "id": qid})
        elif rule.get("remove") and qid not in before_ids:
            errors.append({"code": "ALLOWED_REMOVE_NOT_IN_SOURCE", "id": qid})
        elif not rule.get("add") and qid not in before_ids:
            errors.append({"code": "ALLOWED_TARGET_NOT_IN_SOURCE", "id": qid})
        if not rule.get("remove") and qid not in after_ids:
            errors.append({"code": "ALLOWED_TARGET_NOT_IN_OUTPUT", "id": qid})
        if rule.get("remove") and qid in after_ids:
            errors.append({"code": "ALLOWED_REMOVE_STILL_PRESENT", "id": qid})

    # Elements without IDs are compared by stable document position. Local changes
    # are unauthorized unless an identified ancestor explicitly allows children.
    before_parents = {child: parent for parent in before_root.iter() for child in list(parent)}
    after_parents = {child: parent for parent in after_root.iter() for child in list(parent)}

    def ancestor_allows(element: ET.Element, parents: dict[ET.Element, ET.Element]) -> bool:
        current = parents.get(element)
        while current is not None:
            qid = identifier(current)
            if qid and "children" in allowed.get(qid, {}).get("attributes", []):
                return True
            current = parents.get(current)
        return False

    def anonymous_map(root: ET.Element) -> dict[str, ET.Element]:
        result: dict[str, ET.Element] = {}
        counts: dict[str, int] = {}

        def visit(element: ET.Element, prefix: str) -> None:
            tag = element.tag
            counts_key = f"{prefix}/{tag}"
            counts[counts_key] = counts.get(counts_key, 0) + 1
            path = f"{counts_key}[{counts[counts_key]}]"
            if not identifier(element):
                result[path] = element
            for child in list(element):
                visit(child, path)
        visit(root, "")
        return result

    before_anonymous = anonymous_map(before_root)
    after_anonymous = anonymous_map(after_root)
    for path in sorted(set(before_anonymous) | set(after_anonymous)):
        old = before_anonymous.get(path)
        new = after_anonymous.get(path)
        if old is None or new is None:
            present = new if old is None else old
            if not ancestor_allows(present, after_parents if old is None else before_parents):
                unauthorized.append({"anonymous_path": path, "code": "UNDECLARED_ANONYMOUS_ADD" if old is None else "UNDECLARED_ANONYMOUS_REMOVE"})
            continue
        changes = local_changes(old, new)
        for field, detail in changes.items():
            if not ancestor_allows(old, before_parents) and not ancestor_allows(new, after_parents):
                unauthorized.append({"anonymous_path": path, "field": field, "detail": detail,
                                     "code": "UNDECLARED_ANONYMOUS_CHANGE"})
    if unauthorized:
        errors.extend(unauthorized)
    return {
        "schema": "dual-artifact-quality-gate/source-edit-diff-v1",
        "mode": intent.get("mode", "edit"),
        "before": {"path": before_path.name, "sha256": digest(before_path)},
        "after": {"path": after_path.name, "sha256": digest(after_path)},
        "status": "pass" if not errors else "fail",
        "changed_ids": changed_ids,
        "changed_id_set": sorted({entry["id"] for entry in changed_ids}),
        "required_preserve_ids": sorted(required),
        "unchanged_required_ids": sorted(qid for qid in required if qid in before_ids and qid in after_ids and not local_changes(before_ids[qid], after_ids[qid])),
        "unauthorized_changes": unauthorized,
        "errors": errors,
        "scientific_improvement": "not established by structural diff; inspect source-backed visual reviews",
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--before", type=Path, required=True)
    parser.add_argument("--after", type=Path, required=True)
    parser.add_argument("--intent", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        intent = json.loads(args.intent.read_text(encoding="utf-8"))
        report = build_diff(args.before, args.after, intent)
    except (OSError, ValueError) as exc:
        report = {"schema": "dual-artifact-quality-gate/source-edit-diff-v1", "status": "fail",
                  "errors": [{"code": "EDIT_INTENT_INVALID", "message": str(exc)}],
                  "unauthorized_changes": [], "changed_ids": []}
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return 2 if report.get("errors") else 0


if __name__ == "__main__":
    sys.exit(main())
