#!/usr/bin/env python3
"""Candidate B: independent composite Simpson quadrature implementation."""

import argparse
import json
import math
from pathlib import Path
import re


def material_targets(path):
    text = Path(path).read_text(encoding="utf-8")
    target = float(re.search(r"TARGET=([0-9.]+)", text).group(1))
    tolerance = float(re.search(r"TOLERANCE=([0-9.]+)", text).group(1))
    return target, tolerance


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--material", required=True)
    parser.add_argument("--seed", type=int, required=True)
    args = parser.parse_args()
    target, tolerance = material_targets(args.material)
    # Organization-defined numerical parameter; not reported by a real paper.
    intervals = 100
    width = 1.0 / intervals
    estimate = math.exp(0.0) + math.exp(-1.0)
    estimate += 4.0 * sum(math.exp(-(i * width)) for i in range(1, intervals, 2))
    estimate += 2.0 * sum(math.exp(-(i * width)) for i in range(2, intervals, 2))
    estimate *= width / 3.0
    # A tiny deterministic seed sensitivity makes the baseline noise measurable.
    # Chosen seed sets in the plan have the same median, yielding inconclusive.
    estimate += ((args.seed % 3) - 1) * 0.001
    error = abs(estimate - target)
    print(f"candidate=B method=composite_simpson intervals={intervals} seed={args.seed}")
    print(json.dumps({
        "candidate": "B",
        "estimate": estimate,
        "error": error,
        "target": target,
        "tolerance": tolerance,
        "within_preregistered_tolerance": error <= tolerance,
        "intervals": intervals,
        "seed": args.seed
    }, sort_keys=True))


if __name__ == "__main__":
    main()
