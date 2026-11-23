#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
audit_svg_parse.py — re-parse the produced SVG into a machine-checkable
figure graph (figure_graph.json): entities (id/label/type/compartment/
fill), edges (endpoints, kind, evidence, badge), legend items (item,
meaning, swatch color) and every visible <text> string.

Extraction trusts data-* attributes first (the conventions), falling back
to marker/stroke heuristics; heuristic-derived values are flagged
(*_inferred: true) so downstream auditors can warn instead of silently
trusting them.

Usage: audit_svg_parse.py --svg figure.svg --out figure_graph.json
Exit: 0 ok (possibly with warnings in the graph), 2 SVG unparseable.
"""

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import svg_conventions as C  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--svg", required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    try:
        tree = C.parse_svg(args.svg)
    except Exception as exc:  # malformed XML -> fatal for this auditor
        print("ERROR: cannot parse %s: %s" % (args.svg, exc), file=sys.stderr)
        return 2
    root = tree.getroot()

    w, h = C.svg_canvas_size(root)
    graph = {
        "file": os.path.abspath(args.svg),
        "canvas": {"width": w, "height": h},
        "entities": C.entity_records(root),
        "edges": C.edge_records(root),
        "legend": C.legend_records(root),
        "compartments": C.compartment_records(root),
        "texts": C.all_texts(root),
        "layers_present": [lid for lid in C.LAYER_IDS
                           if C.find_by_id(root, lid) is not None],
        "has_legend_group": C.find_by_id(root, C.LEGEND_ID) is not None,
    }
    with open(args.out, "w", encoding="utf-8") as fh:
        json.dump(graph, fh, indent=2, ensure_ascii=False)
    print("parsed %s: %d entities, %d edges, %d legend items, %d texts" % (
        args.svg, len(graph["entities"]), len(graph["edges"]),
        len(graph["legend"]), len(graph["texts"])))
    return 0


if __name__ == "__main__":
    sys.exit(main())
