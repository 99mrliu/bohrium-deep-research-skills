#!/usr/bin/env python3
"""Write a contract-complete safe PARTIAL before item authoring or execution."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.dont_write_bytecode = True

from common import make_contract_payload, read_json, write_json_atomic


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--case", default="/input/case.json")
    parser.add_argument("--output", default="/app/output/result.json")
    args = parser.parse_args()
    case = read_json(Path(args.case).resolve())
    if not isinstance(case, dict) or not isinstance(case.get("case_id"), str) or not case["case_id"]:
        raise ValueError("case.json must contain a nonempty string case_id")
    result = make_contract_payload(case)
    for field in result:
        if field == "summary":
            result[field] = {
                "process_status": "PARTIAL",
                "message": "Initialization only; items have not been authored and no command has run.",
                "expected_item_count": 4,
            }
        elif field == "uncertainty":
            result[field] = ["Scientific source reading, four-item authoring, execution, and lineage checks are incomplete."]
        elif field == "limitations":
            result[field] = ["This early PARTIAL is a recovery artifact, not a completed answer."]
        elif field == "change_records":
            result[field] = [{"stage": "early_initialization", "status": "PARTIAL", "change": "Created every contract field before scientific authoring; no result is claimed."}]
    write_json_atomic(Path(args.output).resolve(), result)
    print(f"PARTIAL result={Path(args.output).resolve()}")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:
        print(f"early_partial.py: ERROR: {exc}", file=sys.stderr)
        sys.exit(1)
