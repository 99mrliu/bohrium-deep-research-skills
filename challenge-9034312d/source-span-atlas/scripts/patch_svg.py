#!/usr/bin/env python3
"""Patch existing SVG text/attributes through XML-located byte ranges, without tree rebuilds."""
from __future__ import annotations

import argparse
import copy
from html import unescape
import json
from pathlib import Path
import re
import sys
from xml.parsers import expat
from xml.sax.saxutils import escape, quoteattr
import xml.etree.ElementTree as ET
from hashlib import sha256

SCRIPT_DIR = Path(__file__).resolve().parent


def script_path(value):
    path = Path(value)
    return path.resolve() if path.is_absolute() else (SCRIPT_DIR / path).resolve()


def start_tag_end(data, start):
    quote = None
    index = start
    while index < len(data):
        byte = data[index]
        if quote:
            if byte == quote:
                quote = None
        elif byte in (34, 39):
            quote = byte
        elif byte == 62:
            return index + 1
        index += 1
    raise ValueError("Unterminated XML start tag")


def locate(data, wanted_ids):
    parser = expat.ParserCreate()
    locations = {}
    stack = []

    def start(name, attrs):
        element_id = attrs.get("id")
        begin = parser.CurrentByteIndex
        stack.append(element_id)
        if element_id in wanted_ids:
            if element_id in locations:
                raise ValueError("Duplicate id in SVG: %s" % element_id)
            locations[element_id] = {"start": begin, "start_end": start_tag_end(data, begin), "name": name}

    def end(name):
        element_id = stack.pop()
        if element_id in locations and "end" not in locations[element_id]:
            locations[element_id]["end"] = parser.CurrentByteIndex

    parser.StartElementHandler = start
    parser.EndElementHandler = end
    parser.Parse(data, True)
    return locations


def attribute_patch(start_tag, attribute, new_value):
    # XML is prevalidated. Replace only the existing attribute's quoted value.
    pattern = re.compile(r"(?P<prefix>\s" + re.escape(attribute) + r"\s*=\s*)(?P<q>[\"'])(?P<value>.*?)(?P=q)", re.DOTALL)
    match = pattern.search(start_tag)
    if not match:
        raise ValueError("Attribute %s is absent; refusing to imply that adding it is an in-place edit" % attribute)
    before = unescape(match.group("value"))
    quote = match.group("q")
    escaped = escape(str(new_value), {'"': "&quot;", "'": "&apos;"})
    replacement = match.group("prefix") + quote + escaped + quote
    return start_tag[:match.start()] + replacement + start_tag[match.end():], before, str(new_value)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-svg", required=True)
    parser.add_argument("--patch", required=True, help='JSON {"patches":[{"element_id":"...","new_text":"...","attributes":{"x":"12"},"reason":"...","assertion_id":"..."}]}')
    parser.add_argument("--gate-report", required=True, help="Passed atlas.json covering the edited semantics")
    parser.add_argument("--output-svg", required=True)
    parser.add_argument("--records", required=True)
    args = parser.parse_args(argv)
    input_svg = script_path(args.input_svg)
    patch_path = script_path(args.patch)
    gate_path = script_path(args.gate_report)
    output_svg = script_path(args.output_svg)
    records_path = script_path(args.records)
    try:
        if input_svg.resolve() == output_svg.resolve():
            raise ValueError("Refusing in-place overwrite; retain original and write a separate edited SVG")
        original = input_svg.read_bytes()
        text = original.decode("utf-8")
        ET.fromstring(original)
        patch_doc = json.loads(patch_path.read_text(encoding="utf-8"))
        gate = json.loads(gate_path.read_text(encoding="utf-8"))
        if gate.get("verdict") != "passed":
            raise ValueError("Gate report verdict is not passed; fix evidence/semantics before editing")
        patches = patch_doc.get("patches")
        if not isinstance(patches, list) or not patches:
            raise ValueError("patches must be a non-empty list")
        ids = [item.get("element_id") for item in patches]
        if any(not isinstance(item, str) or not item for item in ids) or len(ids) != len(set(ids)):
            raise ValueError("Every target needs a unique element_id")
        locations = locate(original, set(ids))
        operations, change_records = [], []
        for item in patches:
            element_id = item["element_id"]
            if element_id not in locations:
                raise ValueError("Target id not found: %s" % element_id)
            location = locations[element_id]
            if "end" not in location:
                raise ValueError("Target must be a non-self-closing XML element: %s" % element_id)
            original_start = original[location["start"]:location["start_end"]].decode("utf-8")
            original_content = original[location["start_end"]:location["end"]].decode("utf-8")
            after_start = original_start
            attribute_changes = []
            attributes = item.get("attributes", {})
            if not isinstance(attributes, dict):
                raise ValueError("attributes must be an object")
            for name, value in attributes.items():
                after_start, before_value, after_value = attribute_patch(after_start, name, value)
                attribute_changes.append({"name": name, "before": before_value, "after": after_value})
            if after_start != original_start:
                operations.append((location["start"], location["start_end"], after_start.encode("utf-8")))
            if "new_text" in item:
                if "<" in original_content or ">" in original_content:
                    raise ValueError("Text patch supports a single text run only; nested tspans must be targeted individually")
                if not isinstance(item["new_text"], str):
                    raise ValueError("new_text must be a string")
                before_text = unescape(original_content)
                after_text = escape(item["new_text"])
                operations.append((location["start_end"], location["end"], after_text.encode("utf-8")))
            else:
                before_text, after_text = None, None
            if not operations or (after_start == original_start and "new_text" not in item):
                raise ValueError("No edit specified for %s" % element_id)
            change_records.append({
                "element_id": element_id, "assertion_id": item.get("assertion_id"), "action": "modified",
                "reason": item.get("reason", ""), "gate_verdict": "passed",
                "before": {"text": before_text, "attributes": [{"name": entry["name"], "value": entry["before"]} for entry in attribute_changes]},
                "after": {"text": after_text, "attributes": [{"name": entry["name"], "value": entry["after"]} for entry in attribute_changes]},
                "edit_method": "XML-located byte-range replacement", "tree_reserialized": False,
            })
        for first, second in zip(sorted(operations), sorted(operations)[1:]):
            if first[1] > second[0]:
                raise ValueError("Overlapping patch ranges are forbidden")
        edited = bytearray(original)
        for start, end, replacement in sorted(operations, reverse=True):
            edited[start:end] = replacement
        edited_bytes = bytes(edited)
        ET.fromstring(edited_bytes)
        output_svg.parent.mkdir(parents=True, exist_ok=True)
        records_path.parent.mkdir(parents=True, exist_ok=True)
        output_svg.write_bytes(edited_bytes)
        # Verify that bytes outside authorized ranges are exactly retained after reconstruction.
        rebuilt = bytearray()
        cursor = 0
        for start, end, replacement in sorted(operations):
            rebuilt.extend(original[cursor:start])
            rebuilt.extend(replacement)
            cursor = end
        rebuilt.extend(original[cursor:])
        if bytes(rebuilt) != edited_bytes:
            raise ValueError("Byte-preservation verification failed")
        record_doc = {
            "input_svg": str(input_svg), "output_svg": str(output_svg),
            "input_sha256": sha256(original).hexdigest(), "output_sha256": sha256(edited_bytes).hexdigest(),
            "unchanged_bytes_outside_target_ranges": True,
            "change_records": change_records,
            "limits": "Existing text runs and existing attributes only. No insertion/deletion, tree serialization, or silent layout reconstruction. Required unsupported edits must remain partial.",
        }
        records_path.write_text(json.dumps(record_doc, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        print(str(output_svg))
        return 0
    except (OSError, UnicodeError, ValueError, ET.ParseError, expat.ExpatError, json.JSONDecodeError) as exc:
        print("SVG patch failed: %s" % exc, file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
