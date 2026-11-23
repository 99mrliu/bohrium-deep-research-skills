#!/usr/bin/env python3
"""Fail-closed contract linter for result.json.

Checks against the case's own output_contract:
  - every required field present
  - field types match field_types (string/object/array/number/boolean)
  - status value inside status_enum
  - case_id exactly matches the case file
  - null-reason rule: no required field may be null unless `uncertainty`
    names the field (a null with no named reason is a violation)

Stdlib only. Violations are printed and written to lint_report.json.
"""
import argparse
import json
import sys
from pathlib import Path

PY_TYPES = {"string": str, "object": dict, "array": list,
            "number": (int, float), "boolean": bool}


def lint(result, case):
    contract = (case.get("output_contract") or {})
    required = contract.get("required_fields", [])
    types = contract.get("field_types", {})
    enum = contract.get("status_enum")
    violations = []

    if case.get("case_id") is not None and result.get("case_id") != case.get("case_id"):
        violations.append("case_id mismatch: result %r != case %r"
                          % (result.get("case_id"), case.get("case_id")))

    for field in required:
        if field not in result:
            violations.append("required field missing: %r" % field)
            continue
        if result[field] is None:
            unc_text = json.dumps(result.get("uncertainty"), ensure_ascii=False)
            if field not in unc_text:
                violations.append("null-reason violation: field %r is null but "
                                  "not named in uncertainty" % field)
            continue
        if field in types:
            py = PY_TYPES.get(types[field])
            if py and not isinstance(result[field], py):
                violations.append("type mismatch: field %r should be %s, got %s"
                                  % (field, types[field], type(result[field]).__name__))
    if enum and result.get("status") is not None and result["status"] not in enum:
        violations.append("status %r outside contract enum %s" % (result["status"], enum))
    return violations


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--case", default="/input/case.json")
    ap.add_argument("--out", default="/app/output")
    ap.add_argument("--work", default=None)
    args = ap.parse_args()
    case_path = Path(args.case)
    out = Path(args.out)
    case = {}
    if case_path.exists():
        try:
            case = json.loads(case_path.read_text(encoding="utf-8"))
        except Exception as exc:
            print("case.json unreadable: %s" % exc)
            return 1
    rp = out / "result.json"
    if not rp.exists():
        print("result.json missing at %s" % rp)
        return 1
    try:
        result = json.loads(rp.read_text(encoding="utf-8"))
    except Exception as exc:
        print("result.json unreadable: %s" % exc)
        return 1

    violations = lint(result, case)
    work = Path(args.work) if args.work else (out.parent / "work")
    work.mkdir(parents=True, exist_ok=True)
    report = {"violations": violations, "status": result.get("status"),
              "clean": not violations}
    (work / "lint_report.json").write_text(
        json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    for v in violations:
        print("VIOLATION: %s" % v)
    print("lint: %s (%d violations)" % ("CLEAN" if not violations else "FAILED",
                                        len(violations)))
    return 0 if not violations else 2


if __name__ == "__main__":
    sys.exit(main())
