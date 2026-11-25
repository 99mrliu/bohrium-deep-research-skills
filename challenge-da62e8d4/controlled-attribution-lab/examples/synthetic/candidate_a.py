#!/usr/bin/env python3
"""Candidate A: deliberately buggy default quadrature for the lab example."""

import argparse
import json
import math
from pathlib import Path
import random
import re


def material_targets(path):
    text = Path(path).read_text(encoding="utf-8")
    target = float(re.search(r"TARGET=([0-9.]+)", text).group(1))
    tolerance = float(re.search(r"TOLERANCE=([0-9.]+)", text).group(1))
    return target, tolerance


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--material", required=True)
    # BUG: 4 is organization-defined, not a paper fact. The pre-registration
    # tests whether changing only this parameter explains the excess error.
    parser.add_argument("--steps", type=int, default=4)
    parser.add_argument("--seed", type=int, required=True)
    parser.add_argument("--noise-scale", type=float, default=0.002)
    args = parser.parse_args()
    if args.steps < 1:
        parser.error("--steps must be positive")
    target, tolerance = material_targets(args.material)
    width = 1.0 / args.steps
    estimate = width * sum(math.exp(-(i * width)) for i in range(args.steps))
    estimate += random.Random(args.seed).uniform(-args.noise_scale, args.noise_scale)
    error = abs(estimate - target)
    print(f"candidate=A method=left_rectangle steps={args.steps} seed={args.seed}")
    print(json.dumps({
        "candidate": "A",
        "estimate": estimate,
        "error": error,
        "target": target,
        "tolerance": tolerance,
        "within_preregistered_tolerance": error <= tolerance,
        "steps": args.steps,
        "seed": args.seed
    }, sort_keys=True))


if __name__ == "__main__":
    main()
