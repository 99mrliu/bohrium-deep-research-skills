#!/usr/bin/env python3
"""Validate a result JSON against the explicit case output contract.

Inputs: --case CASE.json and --result RESULT.json. No files are modified.
Exit 0: structural checks passed. Exit 2: input or contract validation failed.
"""

import argparse
import json
import sys
from pathlib import Path

from output_contract import parse_output_contract


ALLOWED_STATUSES = {"success", "partial", "unable", "refused"}
BASE_ARRAYS = ("sources", "uncertainty", "change_records")


def load_object(path_string, label):
    path = Path(path_string).expanduser().resolve()
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"Cannot read {label} {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise ValueError(f"{label} must be a JSON object")
    return value


def output_contract_fields(case):
    return parse_output_contract(case)


def required_fields(case):
    return output_contract_fields(case)["required_fields"]


def validate(case, result):
    errors = []
    fields = required_fields(case)
    if result.get("case_id") != case.get("case_id"):
        errors.append(
            f"case_id mismatch: expected {case.get('case_id')!r}, got {result.get('case_id')!r}"
        )
    if result.get("status") not in ALLOWED_STATUSES:
        errors.append(f"status must be one of {sorted(ALLOWED_STATUSES)}")
    if "output_contract" in result:
        errors.append("top-level output_contract is forbidden; contract answer fields must be flattened")
    for field in BASE_ARRAYS:
        if not isinstance(result.get(field), list):
            errors.append(f"{field} must be a top-level array")
    for field in fields:
        if field not in result:
            errors.append(f"missing top-level contract field: {field}")
        elif result.get("status") == "success" and result[field] is None:
            errors.append(f"success result has null contract field: {field}")

    if result.get("status") == "success" and "method_comparison" in result:
        method = result.get("method_comparison")
        if not isinstance(method, dict):
            errors.append("success method_comparison must be an object")
        else:
            if method.get("status") != "completed":
                errors.append("success method_comparison.status must be 'completed'")
            runs = method.get("candidate_runs")
            if not isinstance(runs, list) or len(runs) < 2:
                errors.append("success method_comparison needs at least two candidate_runs")
            for key in ("predeclared_tolerance", "comparison", "attribution"):
                if key not in method or method[key] is None:
                    errors.append(f"success method_comparison missing {key}")
    return errors


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--case", required=True, help="Input case JSON")
    parser.add_argument("--result", required=True, help="Result JSON to validate without modifying it")
    args = parser.parse_args(argv)
    try:
        case = load_object(args.case, "case")
        result = load_object(args.result, "result")
        errors = validate(case, result)
    except ValueError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    if errors:
        for error in errors:
            print(f"ERROR: {error}", file=sys.stderr)
        print(f"FAILED: {len(errors)} contract error(s)", file=sys.stderr)
        return 2
    print(
        f"OK: case_id={result['case_id']} status={result['status']} "
        f"required_fields={len(required_fields(case))}; structural checks only"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
