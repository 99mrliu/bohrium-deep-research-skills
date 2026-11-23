#!/usr/bin/env python3
"""Self-check harness for schema-cartographer. Python 3.10+ stdlib only.

Runs the bundled synthetic example twice into temporary directories, verifies
byte-identical outputs (determinism), and exercises invalid-input handling.
Exit 0 when every check passes, 1 otherwise. Nothing here is an official case
answer; the synthetic inputs are invented demonstration data.
"""
from __future__ import annotations

import filecmp
import json
import subprocess
import sys
import tempfile
from pathlib import Path

BUNDLE = Path(__file__).resolve().parents[1]
SCRIPT = BUNDLE / "scripts" / "schema_cartographer.py"
EXAMPLE_IN = BUNDLE / "examples" / "synthetic-input"

EXPECTED_ARTIFACTS = [
    "cleaned.csv", "cleaned.json", "mapping-report.json", "unresolved-schema.json",
    "review-queue.json", "change-log.jsonl", "audit.md", "result.json",
]


def run(case: Path, out: Path, work: Path, task: Path | None = None):
    cmd = [sys.executable, str(SCRIPT), "--case", str(case),
           "--work", str(work), "--out", str(out)]
    if task is not None:
        cmd += ["--task", str(task)]
    return subprocess.run(cmd, capture_output=True, text=True)


def check(name: str, ok: bool, detail: str = ""):
    print(f"[{'PASS' if ok else 'FAIL'}] {name}" + (f" — {detail}" if detail else ""))
    return ok


def main() -> int:
    all_ok = True
    with tempfile.TemporaryDirectory(prefix="schema-cartographer-") as tmp:
        tmp = Path(tmp)
        case = EXAMPLE_IN / "case.json"
        task = EXAMPLE_IN / "task.md"

        out_a, out_b = tmp / "run-a", tmp / "run-b"
        ra = run(case, out_a, tmp / "work-a", task)
        all_ok &= check("example run exits 0", ra.returncode == 0, ra.stderr.strip()[:200])
        missing = [a for a in EXPECTED_ARTIFACTS if not (out_a / a).is_file()]
        all_ok &= check("all expected artifacts written", not missing, f"missing: {missing}")

        result = json.loads((out_a / "result.json").read_text(encoding="utf-8"))
        all_ok &= check("status success", result.get("status") == "success")
        all_ok &= check("case_id propagated",
                        result.get("case_id") == "synthetic-demo-0001")
        contract = json.loads(case.read_text(encoding="utf-8"))["output_contract"]["fields"]
        all_ok &= check("every output_contract field present in result.json",
                        all(name in result for name in contract))
        unresolved = {u["field"] for u in result.get("unresolved_contract_fields", [])}
        all_ok &= check("unknown contract field nulled, not fabricated",
                        result.get("adjudication_workbook") is None
                        and "adjudication_workbook" in unresolved)
        for key in ("sources", "uncertainty", "change_records", "artifacts"):
            all_ok &= check(f"standard field '{key}' present", key in result)

        cleaned = json.loads((out_a / "cleaned.json").read_text(encoding="utf-8"))["records"]
        raw_ok = all(isinstance(r.get("raw"), dict) and r["raw"] for r in cleaned)
        all_ok &= check("raw source record preserved per row", raw_ok)
        conflict = [r for r in cleaned if "context_value_conflict" in r.get("duplicate_status", "")]
        all_ok &= check("conflicting rows flagged, none merged",
                        len(conflict) > 0 and len(cleaned) == result["summary"]["raw_rows"])
        review = json.loads((out_a / "review-queue.json").read_text(encoding="utf-8"))
        all_ok &= check("review queue has conflicts + anomalies",
                        any(x["kind"] == "duplicate_context_conflicting_values" for x in review["reviews"])
                        and len(review["anomalies"]) > 0)
        unresolved_schema = json.loads((out_a / "unresolved-schema.json").read_text(encoding="utf-8"))
        all_ok &= check("unmapped columns and unknown unit listed",
                        len(unresolved_schema["unmapped_columns"]) == 3
                        and len(unresolved_schema["unknown_units"]) == 1)

        rb = run(case, out_b, tmp / "work-b", task)
        same = rb.returncode == 0 and all(
            (out_b / a).read_bytes() == (out_a / a).read_bytes() for a in EXPECTED_ARTIFACTS)
        all_ok &= check("second run byte-identical (determinism)", same)

        bad = tmp / "bad.json"
        bad.write_text("{broken json,", encoding="utf-8")
        rc = run(bad, tmp / "out-bad", tmp / "work-bad")
        bad_result = json.loads((tmp / "out-bad" / "result.json").read_text(encoding="utf-8"))
        all_ok &= check("malformed JSON -> exit 2 + input_error",
                        rc.returncode == 2 and bad_result.get("status") == "input_error")

        empty = tmp / "empty.json"
        empty.write_text('{"case_id": "no-records", "note": "nothing here"}', encoding="utf-8")
        rd = run(empty, tmp / "out-empty", tmp / "work-empty")
        empty_result = json.loads((tmp / "out-empty" / "result.json").read_text(encoding="utf-8"))
        all_ok &= check("record-less case -> exit 2 + input_error",
                        rd.returncode == 2 and empty_result.get("status") == "input_error")

        re_ = run(tmp / "does-not-exist.json", tmp / "out-missing", tmp / "work-missing")
        all_ok &= check("missing case file -> exit 2 + input_error",
                        re_.returncode == 2 and json.loads(
                            (tmp / "out-missing" / "result.json").read_text()
                        ).get("status") == "input_error")

    print("SELF-CHECK:", "PASS" if all_ok else "FAIL")
    return 0 if all_ok else 1


if __name__ == "__main__":
    sys.exit(main())
