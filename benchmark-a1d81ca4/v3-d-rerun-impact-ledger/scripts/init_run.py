#!/usr/bin/env python3
"""Initialize one real run from case.json, task.md, and materials."""

from __future__ import annotations

import argparse
import os
import platform
import sys
import tempfile
from pathlib import Path

sys.dont_write_bytecode = True

from common import (
    canonical_bytes,
    contract_type_errors,
    hash_file_record,
    hash_tree,
    make_contract_payload,
    output_field_specs,
    read_json,
    sha256_bytes,
    utc_now,
    validate_contract_payload,
    write_json_atomic,
    write_json_new,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-dir", default="/input")
    parser.add_argument("--work-root", default="/app/work")
    parser.add_argument("--output-result", default="/app/output/result.json")
    parser.add_argument("--item-bank", required=True)
    parser.add_argument("--time-budget-seconds", required=True, type=float)
    parser.add_argument("--output-budget-bytes", required=True, type=int)
    parser.add_argument(
        "--model",
        default=os.environ.get("DECLARED_MODEL", "unknown"),
        help="Explicit declaration only; never infer a model.",
    )
    parser.add_argument(
        "--harness",
        default=os.environ.get("DECLARED_HARNESS", "unknown"),
        help="Explicit declaration only; never infer a harness.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.time_budget_seconds <= 0 or args.output_budget_bytes <= 0:
        raise ValueError("both budgets must be positive")
    input_dir = Path(args.input_dir).resolve()
    case_path = input_dir / "case.json"
    task_path = input_dir / "task.md"
    materials_path = input_dir / "materials"
    case_value = read_json(case_path)
    bank_value = read_json(Path(args.item_bank).resolve())
    if not isinstance(case_value, dict) or not isinstance(case_value.get("case_id"), str):
        raise ValueError("case.json must contain a string case_id")
    if not isinstance(bank_value, dict) or not isinstance(bank_value.get("items"), list):
        raise ValueError("item bank must contain an items list")
    items = bank_value["items"]
    if len(items) != 4:
        raise ValueError(f"exactly four items are required, found {len(items)}")
    item_ids = [item.get("item_id") for item in items if isinstance(item, dict)]
    if len(item_ids) != 4 or len(set(item_ids)) != 4 or not all(
        isinstance(item_id, str) and item_id for item_id in item_ids
    ):
        raise ValueError("the item bank must have four unique, nonempty item_id values")

    work_root = Path(args.work_root).resolve()
    work_root.mkdir(parents=True, exist_ok=True)
    run_dir = Path(tempfile.mkdtemp(prefix="run-", dir=str(work_root)))
    run_id = run_dir.name
    bank_path = Path(args.item_bank).resolve()
    bank_sha256 = hash_file_record(bank_path)["sha256"]
    tool_versions = {
        "python": platform.python_version(),
        "python_implementation": platform.python_implementation(),
        "platform": platform.platform(),
    }
    config = {
        "schema": "rerun-impact-ledger/run-config-v1",
        "synthetic_or_real": "source-conditioned benchmark-DRAFT",
        "run_id": run_id,
        "created_at": utc_now(),
        "input_dir": str(input_dir),
        "case_path": str(case_path),
        "task_path": str(task_path),
        "materials_dir": str(materials_path),
        "item_bank_path": str(bank_path),
        "item_bank_sha256": bank_sha256,
        "item_bank_version": bank_value.get("bank_version", "unknown"),
        "declared_model": args.model if args.model else "unknown",
        "declared_harness": args.harness if args.harness else "unknown",
        "declaration_policy": "CLI or DECLARED_MODEL/DECLARED_HARNESS only; otherwise unknown",
        "budgets": {
            "time_budget_seconds": args.time_budget_seconds,
            "output_budget_bytes": args.output_budget_bytes,
            "source": "explicit required CLI arguments",
        },
        "tool_versions": tool_versions,
    }
    config_path = run_dir / "run_config.json"
    write_json_new(config_path, config)
    config_sha256 = sha256_bytes(config_path.read_bytes())
    material_records = hash_tree(materials_path)
    case_record = hash_file_record(case_path)
    task_record = hash_file_record(task_path)
    manifest = {
        "schema": "rerun-impact-ledger/manifest-v1",
        "run_id": run_id,
        "case_id": case_value["case_id"],
        "status": "PARTIAL",
        "success": False,
        "created_at": utc_now(),
        "run_config_sha256": config_sha256,
        "immutable_record_policy": "manifest, config, execution, and command records are create-once",
        "inputs": {
            "case.json": case_record,
            "task.md": task_record,
            "materials": material_records,
            "item_bank": {
                "path": str(bank_path),
                "version": bank_value.get("bank_version", "unknown"),
                **hash_file_record(bank_path),
            },
        },
        "declared_model": config["declared_model"],
        "declared_harness": config["declared_harness"],
        "tool_versions": tool_versions,
        "budgets": config["budgets"],
        "result_path": str(Path(args.output_result).resolve()),
        "scientific_correctness": "NOT_CERTIFIED",
    }
    manifest_path = run_dir / "manifest.json"
    write_json_new(manifest_path, manifest)

    result = make_contract_payload(case_value)
    for field in result:
        if field == "summary":
            result[field] = {
                "process_status": "PARTIAL",
                "message": "Run initialized; command has not completed.",
                "expected_item_count": 4,
            }
        elif field == "sources":
            result[field] = [
                {"name": "case.json", **case_record},
                {"name": "task.md", **task_record},
                {"name": "item_bank", "version": bank_value.get("bank_version", "unknown"), "sha256": bank_sha256},
            ] + [{"name": f"materials/{r['path']}", "sha256": r["sha256"]} for r in material_records]
        elif field == "uncertainty":
            result[field] = ["No command result exists yet; content correctness is not evaluated."]
        elif field == "limitations":
            result[field] = ["PARTIAL is not success and cannot be treated as STABLE."]
        elif field == "change_records":
            result[field] = []
        elif field == "run_manifest":
            result[field] = {
                "run_id": run_id,
                "path": str(manifest_path),
                "sha256": sha256_bytes(manifest_path.read_bytes()),
                "status": "PARTIAL",
                "success": False,
                "manifest": manifest,
            }
    defaults = make_contract_payload(case_value)
    errors = contract_type_errors(case_value, result)
    for spec in output_field_specs(case_value):
        field = str(spec["name"])
        if any(error.startswith(f"field {field!r} ") for error in errors):
            # Initialization remains PARTIAL; an incompatible populated alias
            # falls back to that descriptor's typed empty value.
            result[field] = defaults[field]
    validate_contract_payload(case_value, result)
    write_json_atomic(Path(args.output_result).resolve(), result)
    print(str(run_dir))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:
        print(f"init_run.py: ERROR: {exc}", file=sys.stderr)
        sys.exit(1)
