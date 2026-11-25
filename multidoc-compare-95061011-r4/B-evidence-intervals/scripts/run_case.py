#!/usr/bin/env python3
"""Run the local index-validate-render pipeline without writes outside work/output."""
import argparse
import sys
from pathlib import Path

from evidence_intervals import BundleError, build_index, failure_result, read_json, validate_and_render, write_json


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--work", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--evidence", type=Path, help="Defaults to WORK/evidence.json")
    args = parser.parse_args()
    evidence_path = args.evidence or args.work / "evidence.json"
    try:
        index = build_index(args.input)
        write_json(args.work / "source-index.json", index)
        evidence = read_json(evidence_path)
        result = validate_and_render(args.input, index, evidence, args.output)
    except (BundleError, OSError, TypeError, ValueError) as exc:
        try:
            result = failure_result(args.input, args.output, str(exc))
        except Exception as write_exc:  # Last-resort CLI diagnostic; no silent success.
            print(f"FAILED TO WRITE RESULT: {write_exc}; original error: {exc}", file=sys.stderr)
            return 1
        print(f"failed: {exc}", file=sys.stderr)
    print(f"{result['status']}: {result['case_id']}; output={args.output}")
    return 0 if result["status"] == "success" else 2


if __name__ == "__main__":
    raise SystemExit(main())
