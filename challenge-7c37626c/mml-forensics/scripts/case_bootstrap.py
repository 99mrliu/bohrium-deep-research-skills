#!/usr/bin/env python3
"""Bootstrap a case run: snapshot inputs, create work/output, write an early
honest-partial result.json containing the case_id and every output_contract
field the case declares. Stdlib only (Python 3.9+).
"""
import argparse
import json
import os
import shutil
import sys
from pathlib import Path

SKEL = {
    "status": "partial",
    "answers": {},
    "evidence": [],
    "uncertainty": {},
    "artifacts": {},
}


def load_case(input_root):
    p = Path(input_root) / "case.json"
    if not p.exists():
        return None, "case.json not found at %s" % p
    try:
        return json.loads(p.read_text(encoding="utf-8")), None
    except Exception as exc:  # malformed case.json is itself a finding
        return None, "case.json unreadable: %s" % exc


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", default="/input")
    ap.add_argument("--work", default="/app/work")
    ap.add_argument("--out", default="/app/output")
    args = ap.parse_args()

    inp, err = load_case(args.input)
    work, out = Path(args.work), Path(args.out)
    work.mkdir(parents=True, exist_ok=True)
    out.mkdir(parents=True, exist_ok=True)

    contract = {}
    if inp:
        contract = inp.get("output_contract") or {}
    result = dict(SKEL)
    result["case_id"] = inp.get("case_id") if inp else None
    for field in contract.get("required_fields", []):
        if field not in result:
            result[field] = None  # present, null, with reasons below
    result["artifacts"] = {
        "work_dir": str(work),
        "input_files": sorted(os.listdir(args.input)),
    }
    result["uncertainty"] = {
        "stage": "bootstrap",
        "notes": [err] if err else [
            "early partial result written before analysis; updated incrementally"],
    }
    (out / "result.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print("bootstrap: case_id=%s result=%s" % (result["case_id"], out / "result.json"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
