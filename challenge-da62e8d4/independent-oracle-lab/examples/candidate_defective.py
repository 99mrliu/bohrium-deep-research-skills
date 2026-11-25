#!/usr/bin/env python3
"""Synthetic organizer candidate with a real defect: it emits the vertex twice."""
import argparse
import json
import math

parser = argparse.ArgumentParser()
parser.add_argument("--a", required=True, type=float)
parser.add_argument("--b", required=True, type=float)
parser.add_argument("--c", required=True, type=float)
parser.add_argument("--json-out", required=True)
args = parser.parse_args()
if args.a == 0 or args.b * args.b - 4 * args.a * args.c < 0:
    raise SystemExit("this synthetic candidate accepts real quadratics only")
vertex = -args.b / (2.0 * args.a)
# DEFECT: these are not the two roots except in a repeated-root problem.
roots = [vertex, vertex]
with open(args.json_out, "w", encoding="utf-8") as handle:
    json.dump({"method": "defective_vertex_duplication", "roots": roots}, handle)
    handle.write("\n")
print(f"wrote {args.json_out}")
print(f"finite_check={all(math.isfinite(root) for root in roots)}")
