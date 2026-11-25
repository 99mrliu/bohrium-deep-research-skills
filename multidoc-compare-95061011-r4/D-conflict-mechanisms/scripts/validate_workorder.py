#!/usr/bin/env python3
"""Prepare local sources and validate evidence, scope, matrix and relations."""
import argparse
import sys
from pathlib import Path

from compare_lib import dump_json, load_json, validate_workorder
from source_io import prepare_documents


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-dir", type=Path, required=True)
    parser.add_argument("--work-dir", type=Path, required=True)
    args = parser.parse_args()
    case_path = args.input_dir / "case.json"
    workorder_path = args.input_dir / "comparison-workorder.json"
    task_path = args.input_dir / "task.md"
    try:
        if not task_path.is_file():
            raise ValueError(f"missing required task file: {task_path}")
        case = load_json(case_path)
        workorder = load_json(workorder_path)
        if not isinstance(case.get("case_id"), str) or not case["case_id"]:
            raise ValueError("case.json requires nonempty string case_id")
        registry, _ = prepare_documents(workorder, args.input_dir, args.work_dir)
        report = validate_workorder(workorder, case, registry)
        args.work_dir.mkdir(parents=True, exist_ok=True)
        dump_json(args.work_dir / "source-registry.json", registry)
        dump_json(args.work_dir / "validation.json", report)
    except (OSError, ValueError, RuntimeError, KeyError, TypeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    for warning in report["warnings"]:
        print(f"WARNING: {warning}")
    for error in report["errors"]:
        print(f"ERROR: {error}", file=sys.stderr)
    if report["errors"]:
        return 1
    print("Evidence, exact citations, scopes, common matrix and relations validated.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
