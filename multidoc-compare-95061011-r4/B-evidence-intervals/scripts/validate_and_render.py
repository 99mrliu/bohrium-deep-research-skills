#!/usr/bin/env python3
"""Validate evidence intervals and render matrix, ledger, and dynamic result."""
import argparse
import sys
from pathlib import Path

from evidence_intervals import BundleError, read_json, validate_and_render


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--index", type=Path, required=True)
    parser.add_argument("--evidence", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        result = validate_and_render(args.input, read_json(args.index), read_json(args.evidence), args.output)
    except (BundleError, OSError, TypeError, ValueError) as exc:
        print(f"VALIDATION/RENDER FAILED: {exc}", file=sys.stderr)
        return 1
    print(f"{result['status']}: {result['case_id']}; output={args.output}")
    return 0 if result["status"] == "success" else 2


if __name__ == "__main__":
    raise SystemExit(main())
