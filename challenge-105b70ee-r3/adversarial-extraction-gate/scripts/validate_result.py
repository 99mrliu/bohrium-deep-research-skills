#!/usr/bin/env python3
"""Validate one extraction; exit 0=accepted, 1=rejected, 2=input/tool error."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from result_contract import InputDataError, load_json, parse_targets, validate_result
from mutation_audit import SEMANTIC_LIMIT


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--result", type=Path, default=Path("/app/output/result.json"))
    parser.add_argument("--targets", type=Path, default=Path("/input/target-fields.json"))
    parser.add_argument("--corpus", type=Path, default=Path("/app/work/source-corpus.json"))
    parser.add_argument("--case", type=Path, default=Path("/input/case.json"))
    args = parser.parse_args()
    try:
        case = load_json(args.case)
        if not isinstance(case, dict) or not isinstance(case.get("case_id"), str):
            raise InputDataError("case.json needs a string case_id")
        result = load_json(args.result)
        targets = parse_targets(load_json(args.targets))
        corpus = load_json(args.corpus)
        errors = validate_result(result, targets, corpus, case["case_id"])
    except (InputDataError, OSError, UnicodeError, ValueError) as exc:
        report = {"actual_pass": False, "input_error": str(exc), "exit_status": 2, "semantic_limit": SEMANTIC_LIMIT}
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 2
    report = {
        "actual_pass": not errors,
        "case_id": case["case_id"],
        "result": str(args.result),
        "errors": errors,
        "exit_status": 0 if not errors else 1,
        "semantic_limit": SEMANTIC_LIMIT,
    }
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if not errors else 1


if __name__ == "__main__":
    raise SystemExit(main())
