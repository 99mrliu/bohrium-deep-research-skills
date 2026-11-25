#!/usr/bin/env python3
"""Independently validate final JSON field/evidence shape and optional SVG text."""
from __future__ import annotations

import argparse
import json
import xml.etree.ElementTree as ET
from pathlib import Path

from forge_common import load_json, target_field_ids, validate_result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--result", required=True)
    parser.add_argument("--target-fields", required=True)
    parser.add_argument("--svg", help="optional generated SVG text preview to parse as XML")
    args = parser.parse_args(argv)
    payload = load_json(args.result)
    field_ids = target_field_ids(load_json(args.target_fields))
    validate_result(payload, field_ids)
    svg_text_nodes = None
    if args.svg:
        svg_text = Path(args.svg).read_text(encoding="utf-8")
        root = ET.fromstring(svg_text)
        svg_text_nodes = sum(1 for node in root.iter() if node.tag.rsplit("}", 1)[-1] == "text")
        if svg_text_nodes == 0:
            raise ValueError("SVG preview contains no inspectable text nodes")
    print(json.dumps({
        "valid": True,
        "case_id": payload["case_id"],
        "status": payload["status"],
        "field_count": len(payload["result"]["fields"]),
        "field_ids": field_ids,
        "svg_text_nodes": svg_text_nodes,
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
