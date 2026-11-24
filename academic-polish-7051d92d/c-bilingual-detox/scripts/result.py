#!/usr/bin/env python3
"""result.py -- result.json skeleton generation and validation against the
case's output_contract (c2e-detox-polish).

Python 3 standard library only. Deterministic.

Subcommands:
  result-skeleton --case <case.json> --out <f|->
      Mirror the case's output_contract into a fill-in skeleton: every contract
      key is present, nested keys and declared types are preserved as typed
      placeholders; case_id is pre-filled from the case. Fields the Agent
      cannot map must be set to null (honest null) and explained in notes --
      never fabricated.

  validate-result --case <case.json> --result <result.json>
      Check: result case_id equals the case case_id; every contract key is
      present; non-null values match the declared type (with safe coercions,
      e.g. "92%" -> not attempted, "3" -> 3 for integer/number); status is one
      of success/partial/blocked. Nulls are accepted but reported as honest-
      null warnings (they must be explained in notes). Exit 1 on any error.

Contract type tags: string / number / integer / boolean / array / object /
any. A contract value that is itself an object of key->tag recurses.
"""
import argparse
import json
import sys

VERSION = "1.0.0"
STATUSES = ("success", "partial", "blocked")


def placeholder(tag):
    if isinstance(tag, dict):
        return {k: placeholder(v) for k, v in tag.items()}
    return {
        "string": "",
        "number": 0,
        "integer": 0,
        "boolean": False,
        "array": [],
        "object": {},
        "any": None,
    }.get(tag, None)


def build_skeleton(case):
    contract = case.get("output_contract", {})
    skeleton = {k: placeholder(v) for k, v in contract.items()}
    if "case_id" in skeleton:
        skeleton["case_id"] = case.get("case_id", "")
    return {
        "tool": "result.py",
        "version": VERSION,
        "command": "result-skeleton",
        "case_id": case.get("case_id", ""),
        "note": ("Fill every field with real mapped content. If a field cannot "
                 "be mapped, set it to null and explain in notes -- do NOT "
                 "fabricate. status: success|partial|blocked."),
        "skeleton": skeleton,
    }


def _coerce(value, tag):
    """Return (ok, coerced_value, note)."""
    if tag == "any":
        return True, value, None
    if tag == "string":
        return (isinstance(value, str), value, None)
    if tag == "boolean":
        return (isinstance(value, bool), value, None)
    if tag == "array":
        return (isinstance(value, list), value, None)
    if tag == "object":
        return (isinstance(value, dict), value, None)
    if tag == "integer":
        if isinstance(value, bool):
            return False, value, None
        if isinstance(value, int):
            return True, value, None
        if isinstance(value, float) and value.is_integer():
            return True, int(value), "coerced float->integer"
        if isinstance(value, str) and value.strip().lstrip("+-").isdigit():
            return True, int(value.strip()), "coerced string->integer"
        return False, value, None
    if tag == "number":
        if isinstance(value, bool):
            return False, value, None
        if isinstance(value, (int, float)):
            return True, value, None
        if isinstance(value, str):
            try:
                return True, float(value.strip()), "coerced string->number"
            except ValueError:
                return False, value, None
        return False, value, None
    return False, value, "unknown contract type tag %r" % (tag,)


def validate(case, result):
    errors = []
    warnings = []
    contract = case.get("output_contract", {})

    case_id = case.get("case_id")
    if "case_id" not in result:
        errors.append("missing required key: case_id")
    elif result["case_id"] != case_id:
        errors.append("case_id mismatch: result=%r, case=%r"
                      % (result["case_id"], case_id))

    def walk(prefix, contract_map, result_map):
        for key, tag in contract_map.items():
            path = "%s.%s" % (prefix, key) if prefix else key
            if key not in result_map:
                errors.append("missing contract key: %s" % path)
                continue
            value = result_map[key]
            if value is None:
                warnings.append("%s is null (honest null; must be explained "
                                "in notes)" % path)
                continue
            if isinstance(tag, dict):
                if not isinstance(value, dict):
                    errors.append("%s: expected object (nested contract), got %s"
                                  % (path, type(value).__name__))
                    continue
                walk(path, tag, value)
                continue
            ok, _coerced, note = _coerce(value, tag)
            if not ok:
                errors.append("%s: expected %s, got %s (%r)"
                              % (path, tag, type(value).__name__, value)[:200])
            elif note:
                warnings.append("%s: %s" % (path, note))

    walk("", contract, result)

    if "status" in result and result["status"] is not None:
        if result["status"] not in STATUSES:
            errors.append("status must be one of %s, got %r"
                          % ("|".join(STATUSES), result["status"]))

    return errors, warnings


def _write_out(text, out_path):
    if out_path == "-":
        sys.stdout.write(text)
    else:
        with open(out_path, "w", encoding="utf-8") as f:
            f.write(text)


def main(argv=None):
    ap = argparse.ArgumentParser(
        description="result.json skeleton + validation against output_contract.")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p_s = sub.add_parser("result-skeleton")
    p_s.add_argument("--case", required=True)
    p_s.add_argument("--out", required=True, help="Output JSON path or '-'.")

    p_v = sub.add_parser("validate-result")
    p_v.add_argument("--case", required=True)
    p_v.add_argument("--result", required=True)

    args = ap.parse_args(argv)

    if args.cmd == "result-skeleton":
        with open(args.case, "r", encoding="utf-8") as f:
            case = json.load(f)
        sk = build_skeleton(case)
        _write_out(json.dumps(sk, ensure_ascii=False, indent=2) + "\n", args.out)
        print("result-skeleton: %d contract keys -> %s"
              % (len(case.get("output_contract", {})), args.out), file=sys.stderr)
        return 0

    with open(args.case, "r", encoding="utf-8") as f:
        case = json.load(f)
    with open(args.result, "r", encoding="utf-8") as f:
        result = json.load(f)
    errors, warnings = validate(case, result)
    for w in warnings:
        print("WARNING: %s" % w, file=sys.stderr)
    for e in errors:
        print("ERROR: %s" % e, file=sys.stderr)
    if errors:
        print("validate-result: FAIL (%d errors, %d warnings)"
              % (len(errors), len(warnings)), file=sys.stderr)
        return 1
    print("validate-result: PASS (%d warnings)" % len(warnings), file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
