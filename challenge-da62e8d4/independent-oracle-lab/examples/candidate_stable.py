#!/usr/bin/env python3
"""Synthetic organizer candidate using a stable floating-point analytic formula."""
import argparse
import json
import math

parser = argparse.ArgumentParser()
parser.add_argument("--a", required=True, type=float)
parser.add_argument("--b", required=True, type=float)
parser.add_argument("--c", required=True, type=float)
args = parser.parse_args()
discriminant = args.b * args.b - 4.0 * args.a * args.c
if args.a == 0 or discriminant < 0:
    raise SystemExit("this synthetic candidate accepts real quadratics only")
sqrt_discriminant = math.sqrt(discriminant)
if sqrt_discriminant == 0:
    roots = [-args.b / (2.0 * args.a)] * 2
else:
    q = -0.5 * (args.b + math.copysign(sqrt_discriminant, args.b))
    roots = sorted([q / args.a, args.c / q])
print("diagnostic: candidate uses q-form; this line is not the JSON result")
print(json.dumps({"method": "float_stable_q_form", "roots": roots}))
