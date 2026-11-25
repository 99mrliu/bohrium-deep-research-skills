#!/usr/bin/env python3
"""Reject mechanism support based on speculation or missing direct comparison."""
import argparse
import sys
from pathlib import Path

from compare_lib import attribution_problems, load_json


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workorder", type=Path, required=True)
    args = parser.parse_args()
    problems = attribution_problems(load_json(args.workorder))
    if problems:
        for problem in problems:
            print(f"ERROR: {problem}", file=sys.stderr)
        return 1
    print("Mechanism attribution checks passed; speculation has not been promoted to support.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
