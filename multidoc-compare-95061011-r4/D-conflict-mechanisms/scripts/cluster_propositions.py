#!/usr/bin/env python3
"""Cluster only exact agent-specified proposition keys; never fuzzy match."""
import argparse
import sys
from pathlib import Path

from compare_lib import dump_json, load_json, make_clusters


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workorder", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        clusters = make_clusters(load_json(args.workorder))
        dump_json(args.output, clusters)
    except (ValueError, KeyError, TypeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    print(f"Exact-key clusters written to {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
