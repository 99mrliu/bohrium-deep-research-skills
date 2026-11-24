#!/usr/bin/env python3
"""result.py -- result.json skeleton generation and validation.

Mirrors the case's output_contract so no required field is ever hand-written.

Subcommands:
  result-skeleton --case <case.json> --out <skeleton.json>
      Build a skeleton preserving every contract key (nested keys included)
      with type-shaped placeholders, plus case_id / status / sources /
      uncertainty / notes.
  validate-result --case <case.json> --result <result.json>
      Check case_id equality, presence and declared type of every contract
      field, and the status enum. Null fields are allowed only when `notes`
      is non-empty (honest degradation, never fabricated content).
      Exit code 1 on any failure.

Python 3 standard library only. Deterministic.
"""
import argparse
import json
import sys

PLACEHOLDER = {
    "string": "", "array": [], "object": {}, "number": None,
    "boolean": False, "null": None, "any": None,
}
PY_TYPE = {
    "string": str, "array": list, "object": dict,
    "number": (int, float), "boolean": bool,
}


def _read(path):
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


def _write_json(path, obj):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)
        f.write("\n")


def _contract(case):
    c = case.get("output_contract", {})
    if isinstance(c, dict) and isinstance(c.get("fields"), dict):
        return c["fields"]
    return c if isinstance(c, dict) else {}


def _skeleton_from(contract):
    out = {}
    for k, v in contract.items():
        if isinstance(v, dict):
            out[k] = _skeleton_from(v)
        else:
            out[k] = PLACEHOLDER.get(str(v).lower())
    return out


def cmd_skeleton(args):
    case = json.loads(_read(args.case))
    contract = _contract(case)
    skel = {
        "case_id": case.get("case_id"),
        "status": "partial",
        "sources": [],
        "uncertainty": "",
        "notes": ("Skeleton from result.py result-skeleton; fill every field "
                  "honestly. Use null only for fields that cannot be mapped, "
                  "and explain them in notes."),
    }
    for k in contract:
        if k not in skel:
            skel[k] = _skeleton_from({k: contract[k]})[k]
    _write_json(args.out, skel)
    print("result-skeleton: case_id=%s fields=%s"
          % (skel["case_id"], ",".join(contract.keys())))
    return 0


def _check_type(path, declared, value, errors):
    if isinstance(declared, dict):
        if not isinstance(value, dict):
            errors.append("%s: expected object" % path)
            return
        for k, v in declared.items():
            if k not in value:
                errors.append("%s.%s: missing" % (path, k))
            elif value[k] is not None:
                _check_type("%s.%s" % (path, k), v, value[k], errors)
        return
    t = str(declared).lower()
    if t in ("any", "null"):
        return
    py = PY_TYPE.get(t)
    if py is None:
        return
    if t == "number" and isinstance(value, bool):
        errors.append("%s: expected number, got boolean" % path)
    elif not isinstance(value, py):
        errors.append("%s: expected %s, got %s"
                      % (path, t, type(value).__name__))


def cmd_validate(args):
    case = json.loads(_read(args.case))
    result = json.loads(_read(args.result))
    contract = _contract(case)
    errors, nulls = [], []

    if result.get("case_id") != case.get("case_id"):
        errors.append("case_id mismatch: result=%r case=%r"
                      % (result.get("case_id"), case.get("case_id")))
    if result.get("status") not in ("success", "partial", "blocked"):
        errors.append("status must be one of success|partial|blocked")

    for k, declared in contract.items():
        if k not in result:
            errors.append("missing contract field: %s" % k)
            continue
        v = result[k]
        if v is None:
            nulls.append(k)
        else:
            _check_type(k, declared, v, errors)
    if nulls and not str(result.get("notes", "")).strip():
        errors.append("null contract fields %s require a non-empty notes "
                      "explanation" % nulls)

    for e in errors:
        print("FAIL %s" % e)
    if errors:
        print("validate-result: %d error(s)" % len(errors))
        return 1
    print("validate-result: PASS (case_id=%s, %d contract fields, nulls=%s)"
          % (result.get("case_id"), len(contract), nulls or "none"))
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(
        description="result.json skeleton generation and validation.")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("result-skeleton", help="build a contract-shaped skeleton")
    p.add_argument("--case", required=True)
    p.add_argument("--out", required=True)
    p.set_defaults(func=cmd_skeleton)

    p = sub.add_parser("validate-result", help="validate result.json against the case")
    p.add_argument("--case", required=True)
    p.add_argument("--result", required=True)
    p.set_defaults(func=cmd_validate)

    args = ap.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
