#!/usr/bin/env python3
"""Bootstrap an audit run: create /app/work and /app/output, write the early
honest-partial result.json (case_id + every output_contract field), and an
empty claims scaffold so the ledger is never lost. Stdlib only.
"""
import argparse
import json
import os
import sys
from pathlib import Path


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", default="/input")
    ap.add_argument("--work", default="/app/work")
    ap.add_argument("--out", default="/app/output")
    args = ap.parse_args()
    work, out = Path(args.work), Path(args.out)
    work.mkdir(parents=True, exist_ok=True)
    out.mkdir(parents=True, exist_ok=True)

    case_path = Path(args.input) / "case.json"
    case, note = {}, "case.json missing; contract fields unknown"
    if case_path.exists():
        try:
            case = json.loads(case_path.read_text(encoding="utf-8"))
            note = "early partial; claims ledger not yet built"
        except Exception as exc:
            note = "case.json unreadable: %s" % exc

    result = {
        "case_id": case.get("case_id"),
        "status": "partial",
        "answers": {},
        "evidence": [],
        "uncertainty": {"stage": "bootstrap", "notes": [note]},
        "artifacts": {"work_dir": str(work), "input_files": sorted(os.listdir(args.input))},
    }
    for field in (case.get("output_contract") or {}).get("required_fields", []):
        result.setdefault(field, None)
    (out / "result.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    scaffold = {"claims": [], "note": "fill from the actual paper; every value "
                                      "needs value+unit+source location"}
    (work / "claims.json").write_text(
        json.dumps(scaffold, ensure_ascii=False, indent=2), encoding="utf-8")
    print("bootstrap: case_id=%s; claims scaffold at %s"
          % (result["case_id"], work / "claims.json"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
