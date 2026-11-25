#!/usr/bin/env python3
"""Index all whitelisted PDF/text inputs into auditable paragraph locators."""
import argparse
import json
import sys
from pathlib import Path

from evidence_intervals import BundleError, build_index, write_json


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        index = build_index(args.input)
        write_json(args.output, index)
    except (BundleError, OSError) as exc:
        print(f"INDEX FAILED: {exc}", file=sys.stderr)
        return 1
    print(json.dumps({"documents": len(index["documents"]), "errors": len(index["errors"]), "index": str(args.output)}, ensure_ascii=False))
    return 2 if not index["documents"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
