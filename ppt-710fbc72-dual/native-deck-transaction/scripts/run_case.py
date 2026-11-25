#!/usr/bin/env python3
"""Prepare or finish a native-deck-transaction case without installing dependencies."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

try:
    from native_core import TransactionError, contract_fields, finish, prepare
except ImportError as exc:
    raise SystemExit(
        "Missing declared runtime dependency. Install/enable python-pptx, PyMuPDF, and Pillow "
        "in the environment before running; this skill never auto-installs packages. " + str(exc)
    ) from exc


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Immutable-base native PPTX edit transactions")
    sub = p.add_subparsers(dest="command", required=True)
    for name in ("prepare", "finish"):
        cmd = sub.add_parser(name)
        cmd.add_argument("--input", required=True, type=Path)
        cmd.add_argument("--work", required=True, type=Path)
        cmd.add_argument("--output", required=True, type=Path)
        if name == "finish":
            cmd.add_argument("--plan", type=Path, help="Defaults to WORK/transaction_plan.json")
    return p


def emergency_result(args: argparse.Namespace, exc: Exception) -> None:
    """Preserve a contract-complete failure even when discovery cannot start."""
    case = {}
    case_path = args.input / "case.json"
    if case_path.is_file():
        try:
            case = json.loads(case_path.read_text(encoding="utf-8"))
        except Exception:
            case = {}
    result = {
        "case_id": str(case.get("case_id", case.get("id", "unknown"))),
        "status": "failed", "sources": [], "uncertainty": [f"{type(exc).__name__}: {exc}"],
        "change_log": [{"event": "failure", "detail": "Runner stopped before a normal result could be produced."}],
        "artifacts": [], "output_contract": case.get("output_contract", case.get("fields", [])),
    }
    for field in contract_fields(case):
        result.setdefault(field, None)
    args.output.mkdir(parents=True, exist_ok=True)
    (args.output / "result.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main() -> int:
    args = parser().parse_args()
    try:
        if args.command == "prepare":
            result = prepare(args.input, args.work, args.output)["result"]
        else:
            result = finish(args.input, args.work, args.output, args.plan)
    except (TransactionError, OSError, ValueError, json.JSONDecodeError) as exc:
        emergency_result(args, exc)
        print(str(exc), file=sys.stderr)
        return 2
    print(json.dumps({
        "case_id": result.get("case_id"),
        "status": result.get("status"),
        "result": str((args.output / "result.json").resolve()),
        "uncertainty": result.get("uncertainty", []),
    }, ensure_ascii=False, indent=2))
    return 0 if result.get("status") in {"success", "partial"} else 2


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except TransactionError as exc:
        # finish normally converts transaction failures to result.json; this handles
        # failures early enough that no result object could be constructed.
        print(str(exc), file=sys.stderr)
        raise SystemExit(2)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"Case input/plan failure: {exc}", file=sys.stderr)
        raise SystemExit(2)
