#!/usr/bin/env python3
"""Create a minimal SVG only when no original layered SVG exists."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import tempfile
import xml.etree.ElementTree as ET

SVG = "http://www.w3.org/2000/svg"


def atomic(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(dir=path.parent, delete=False) as f:
        f.write(data)
        f.flush()
        os.fsync(f.fileno())
        tmp = Path(f.name)
    os.replace(tmp, path)


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("output", type=Path)
    p.add_argument("--title", required=True)
    p.add_argument("--node", action="append", nargs=3, metavar=("ID", "LABEL", "COLOR"), required=True)
    args = p.parse_args()
    if args.output.exists():
        p.error("Refusing to overwrite an existing file")
    ids = [n[0] for n in args.node]
    if any(not x or not x.replace("-", "").replace("_", "").isalnum() for x in ids) or len(ids) != len(set(ids)):
        p.error("Node IDs must be simple, stable and unique")
    root = ET.Element(f"{{{SVG}}}svg", {"id": "svg-root", "width": "800", "height": str(100 + 100 * len(ids)), "viewBox": f"0 0 800 {100 + 100 * len(ids)}", "version": "1.1"})
    ET.SubElement(root, f"{{{SVG}}}metadata", {"id": "provenance"}).text = "SYNTHETIC; minimal new source; no biological source is implied"
    ET.SubElement(root, f"{{{SVG}}}title", {"id": "figure-title"}).text = args.title
    ET.SubElement(root, f"{{{SVG}}}rect", {"id": "background", "x": "0", "y": "0", "width": "800", "height": root.get("height"), "fill": "white"})
    for n, (ident, label, color) in enumerate(args.node):
        g = ET.SubElement(root, f"{{{SVG}}}g", {"id": "group-" + ident})
        y = 70 + n * 100
        ET.SubElement(g, f"{{{SVG}}}rect", {"id": ident, "x": "250", "y": str(y), "width": "300", "height": "55", "rx": "8", "fill": color, "stroke": "#334155"})
        ET.SubElement(g, f"{{{SVG}}}text", {"id": "label-" + ident, "x": "400", "y": str(y + 36), "text-anchor": "middle", "font-family": "sans-serif", "font-size": "20"}).text = label
    ET.register_namespace("", SVG)
    atomic(args.output, ET.tostring(root, encoding="utf-8", xml_declaration=True))
    print(json.dumps({"created": str(args.output), "mode": "minimal-new-source", "source_preserving": False}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
