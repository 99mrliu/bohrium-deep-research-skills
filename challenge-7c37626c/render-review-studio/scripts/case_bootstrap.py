#!/usr/bin/env python3
"""Bootstrap a render-studio run: create work/output, write early
honest-partial result.json (case_id + all output_contract fields) and empty
formulas/variables scaffolds. Stdlib only.
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
            note = "early partial; no previews rendered yet"
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
    (work / "formulas.json").write_text(json.dumps(
        {"formulas": [], "note": "fill with {id, latex, source} from the actual reading"},
        ensure_ascii=False, indent=2), encoding="utf-8")
    (work / "variables.json").write_text(json.dumps(
        {"rows": [], "note": "fill with {symbol, definition, unit, source}"},
        ensure_ascii=False, indent=2), encoding="utf-8")
    print("bootstrap: case_id=%s" % result["case_id"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
