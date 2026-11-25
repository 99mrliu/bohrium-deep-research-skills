#!/usr/bin/env python3
"""Execute a supplied argv without a shell and retain a fail-closed audit trail."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path

sys.dont_write_bytecode = True

from common import (
    effective_run_record,
    hash_file_record,
    read_json,
    sha256_bytes,
    utc_now,
    write_json_new,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-dir", required=True)
    parser.add_argument("--cwd", required=True)
    parser.add_argument("--command-json", required=True, help="JSON array of argv strings")
    parser.add_argument("--timeout-seconds", required=True, type=float)
    parser.add_argument(
        "--expected-output",
        action="append",
        required=True,
        help="Run-directory-relative regular file required for STABLE; repeatable.",
    )
    return parser.parse_args()


def checked_relative_output(run_dir: Path, value: str) -> Path:
    relative = Path(value)
    if relative.is_absolute() or not value or ".." in relative.parts:
        raise ValueError(f"expected output must be a safe relative path: {value!r}")
    output = (run_dir / relative).resolve()
    if output == run_dir or run_dir not in output.parents:
        raise ValueError(f"expected output escapes run directory: {value!r}")
    return output


def main() -> int:
    args = parse_args()
    run_dir = Path(args.run_dir).resolve()
    cwd = Path(args.cwd).resolve()
    if args.timeout_seconds <= 0:
        raise ValueError("timeout must be positive")
    if (run_dir / "execution.json").exists():
        raise ValueError("execution.json already exists; immutable runs cannot be rerun in place")
    initial = effective_run_record(run_dir)
    if initial.get("status") != "PARTIAL":
        raise ValueError("only a newly initialized PARTIAL run can be executed")
    config = read_json(run_dir / "run_config.json")
    budget = float(config["budgets"]["time_budget_seconds"])
    if args.timeout_seconds > budget:
        raise ValueError("command timeout exceeds the explicit run time budget")
    command_value = json.loads(args.command_json)
    if (
        not isinstance(command_value, list)
        or not command_value
        or not all(isinstance(part, str) and part for part in command_value)
    ):
        raise ValueError("--command-json must be a nonempty JSON array of nonempty strings")
    if not cwd.is_dir():
        raise ValueError(f"cwd is not a directory: {cwd}")
    expected = [checked_relative_output(run_dir, value) for value in args.expected_output]
    stdout_path = run_dir / "command.stdout.txt"
    stderr_path = run_dir / "command.stderr.txt"
    command_path = run_dir / "command_record.json"
    execution_path = run_dir / "execution.json"
    for path in [stdout_path, stderr_path, command_path, execution_path]:
        if path.exists():
            raise ValueError(f"refusing to replace immutable audit record: {path}")

    started_at = utc_now()
    monotonic_start = time.monotonic()
    returncode = 127
    stdout = ""
    stderr = ""
    timed_out = False
    launch_error = None
    try:
        completed = subprocess.run(
            command_value,
            cwd=str(cwd),
            shell=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=args.timeout_seconds,
            check=False,
        )
        returncode = completed.returncode
        stdout = completed.stdout
        stderr = completed.stderr
    except subprocess.TimeoutExpired as exc:
        timed_out = True
        returncode = 124
        stdout_value = exc.stdout or ""
        stderr_value = exc.stderr or ""
        stdout = stdout_value.decode("utf-8", "replace") if isinstance(stdout_value, bytes) else stdout_value
        stderr = stderr_value.decode("utf-8", "replace") if isinstance(stderr_value, bytes) else stderr_value
        stderr += f"\nTIMEOUT after {args.timeout_seconds} seconds\n"
    except OSError as exc:
        launch_error = str(exc)
        returncode = 127
        stderr = f"COMMAND LAUNCH FAILED: {exc}\n"
    duration = time.monotonic() - monotonic_start
    finished_at = utc_now()

    # The logs are immutable evidence; text conversion never changes return status.
    for path, text in [(stdout_path, stdout), (stderr_path, stderr)]:
        with path.open("x", encoding="utf-8") as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        path.chmod(0o444)

    failure_reasons: list[str] = []
    if timed_out:
        failure_reasons.append("TIMEOUT")
    if launch_error:
        failure_reasons.append("COMMAND_LAUNCH_FAILED")
    if returncode != 0:
        failure_reasons.append(f"NONZERO_RETURNCODE:{returncode}")
    expected_records = []
    output_bytes = 0
    for path in expected:
        relative = path.relative_to(run_dir).as_posix()
        if not path.is_file() or path.is_symlink():
            failure_reasons.append(f"MISSING_EXPECTED_OUTPUT:{relative}")
            expected_records.append({"path": relative, "present": False})
        else:
            record = hash_file_record(path)
            output_bytes += int(record["bytes"])
            expected_records.append({"path": relative, "present": True, **record})
    output_budget = int(config["budgets"]["output_budget_bytes"])
    if output_bytes > output_budget:
        failure_reasons.append(
            f"OUTPUT_BUDGET_EXCEEDED:{output_bytes}>{output_budget}"
        )
    stable = not failure_reasons
    status = "STABLE" if stable else "FAILED"
    run_config_sha256 = sha256_bytes((run_dir / "run_config.json").read_bytes())
    command_record = {
        "schema": "rerun-impact-ledger/command-v1",
        "run_id": run_dir.name,
        "run_config_sha256": run_config_sha256,
        "argv": command_value,
        "cwd": str(cwd),
        "shell": False,
        "started_at": started_at,
        "finished_at": finished_at,
        "duration_seconds": duration,
        "timeout_seconds": args.timeout_seconds,
        "timed_out": timed_out,
        "returncode": returncode,
        "exit_code": returncode,
        "stdout": {"path": stdout_path.name, **hash_file_record(stdout_path)},
        "stderr": {"path": stderr_path.name, **hash_file_record(stderr_path)},
        "expected_outputs": expected_records,
        "output_bytes_checked": output_bytes,
        "output_budget_bytes": output_budget,
        "failure_reasons": failure_reasons,
    }
    write_json_new(command_path, command_record)
    execution = {
        "schema": "rerun-impact-ledger/execution-v1",
        "run_id": run_dir.name,
        "initial_manifest_sha256": sha256_bytes((run_dir / "manifest.json").read_bytes()),
        "command_record_sha256": sha256_bytes(command_path.read_bytes()),
        "run_config_sha256": run_config_sha256,
        "status": status,
        "success": stable,
        "created_at": finished_at,
        "returncode": returncode,
        "exit_code": returncode,
        "duration_seconds": duration,
        "failure_reasons": failure_reasons,
        "scientific_correctness": "NOT_CERTIFIED",
        "stable_meaning": "Process gate only; nonzero, timeout, launch failure, missing output, and output overflow are never STABLE.",
    }
    write_json_new(execution_path, execution)
    print(json.dumps({"run_dir": str(run_dir), "status": status, "exit_code": returncode}))
    return 0 if stable else (returncode if returncode != 0 else 1)


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:
        print(f"run_command.py: ERROR: {exc}", file=sys.stderr)
        sys.exit(1)
