#!/usr/bin/env python3
"""result.py -- output-contract mirroring for the audit-trail-polish skill.

Commands:
  result-skeleton  --case <case.json> --out <skeleton.json>
      Generate a result skeleton from the case's real output_contract,
      preserving nested keys and declared types. Never hand-write contract
      fields: that is the biggest structural risk in this contest.
  fill-result      --case <case.json> --artifacts <dir> --out <result.json>
      Fill the skeleton from produced artifacts via an alias table and type
      coercion. Fields that cannot be mapped stay null (honest null) and are
      recorded in notes -- fabricating content to fill a field is forbidden.
  validate-result  --case <case.json> --result <result.json>
      Check required fields, declared types and case_id consistency.
      Exit code 0 = pass, 1 = fail.

Contract dialect handled here: output_contract = {"fields": {name: spec}} where
spec may declare "type" (string or list of strings), "required" (bool),
"aliases" (list of alternative names) and "description".
Python 3 standard library only; deterministic output.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# Canonical artifact resolvers. A contract field maps to a canonical name if
# its own name OR any of its aliases matches (case-insensitive).
CANONICAL = {
    "polished_text": {"kind": "file_text", "file": "polished.md"},
    "changes": {"kind": "changes_entries", "file": "changes.json"},
    "review_html": {"kind": "file_text", "file": "review.html"},
    "change_log": {"kind": "file_text", "file": "change-log.md"},
    "status": {"kind": "literal", "value": "success"},
    "uncertainty": {"kind": "null"},
}

TYPE_DEFAULTS = {
    "string": "", "array": [], "object": {}, "number": 0, "integer": 0,
    "boolean": False, "null": None,
}

JSON_TYPES = {
    "string": str, "array": list, "object": dict, "number": (int, float),
    "integer": int, "boolean": bool,
}


def load_case(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def contract_fields(case):
    oc = case.get("output_contract", {})
    if isinstance(oc, dict) and "fields" in oc:
        return oc["fields"]
    if isinstance(oc, dict):  # bare {name: spec} dialect
        return oc
    return {}


def spec_types(spec):
    t = spec.get("type", "null") if isinstance(spec, dict) else "null"
    return t if isinstance(t, list) else [t]


def canonical_for(name, spec):
    cands = [name] + list(spec.get("aliases", []) if isinstance(spec, dict) else [])
    for c in cands:
        if c.lower() in CANONICAL:
            return c.lower()
    return None


def cmd_skeleton(args):
    case = load_case(args.case)
    skeleton = {
        "case_id": case.get("case_id"),
        "status": None,
        "sources": [],
        "uncertainty": None,
        "notes": [],
    }
    for name, spec in contract_fields(case).items():
        types = spec_types(spec)
        skeleton[name] = TYPE_DEFAULTS.get(types[0])
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(skeleton, ensure_ascii=False, indent=2,
                              sort_keys=True) + "\n", encoding="utf-8")
    print("result-skeleton: %d contract field(s) -> %s"
          % (len(contract_fields(case)), out))
    return 0


def resolve_artifact(canon, artifacts):
    spec = CANONICAL[canon]
    kind = spec["kind"]
    if kind == "literal":
        return spec["value"]
    if kind == "null":
        return None
    p = Path(artifacts) / spec["file"]
    if not p.exists():
        raise FileNotFoundError(str(p))
    if kind == "file_text":
        return p.read_text(encoding="utf-8")
    if kind == "changes_entries":
        data = json.loads(p.read_text(encoding="utf-8"))
        return [{
            "sid": e["sid"], "status": e["status"], "types": e["types"],
            "original": e["original"], "revised": e["revised"],
            "reason": e["reason"], "basis": e["basis"],
        } for e in data["entries"]]
    raise ValueError("unknown resolver kind: %s" % kind)


def coerce(value, types):
    """Best-effort type coercion; returns (value, coerced_flag)."""
    if value is None:
        return None, False
    for t in types:
        py = JSON_TYPES.get(t)
        if py and isinstance(value, py) and not (t != "boolean"
                                                 and isinstance(value, bool)):
            return value, False
    if "string" in types and isinstance(value, (list, dict)):
        return json.dumps(value, ensure_ascii=False), True
    if ("array" in types or "object" in types) and isinstance(value, str):
        try:
            parsed = json.loads(value)
            return parsed, True
        except ValueError:
            return value, False
    if "number" in types and isinstance(value, str):
        try:
            return float(value), True
        except ValueError:
            return value, False
    return value, False


def cmd_fill(args):
    case = load_case(args.case)
    result = {
        "case_id": case.get("case_id"),
        "status": "blocked",
        "sources": ["case.json source_text (synthetic example / 合成示例)"],
        "uncertainty": None,
        "notes": [],
    }
    for name, spec in contract_fields(case).items():
        types = spec_types(spec)
        canon = canonical_for(name, spec)
        value = None
        if canon:
            try:
                value = resolve_artifact(canon, args.artifacts)
            except FileNotFoundError as exc:
                result["notes"].append(
                    "field '%s' mapped to '%s' but artifact missing: %s"
                    % (name, canon, exc))
        else:
            result["notes"].append(
                "field '%s' has no artifact mapping; left null (honest null, "
                "no fabricated content)" % name)
        value, coerced = coerce(value, types)
        if coerced:
            result["notes"].append("field '%s' type-coerced to %s"
                                   % (name, "/".join(types)))
        result[name] = value
    if result.get("polished_text") and result.get("changes") is not None:
        result["status"] = "success"
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, ensure_ascii=False, indent=2,
                              sort_keys=True) + "\n", encoding="utf-8")
    print("fill-result: wrote %s (status=%s)" % (out, result["status"]))
    return 0


def cmd_validate(args):
    case = load_case(args.case)
    result = json.loads(Path(args.result).read_text(encoding="utf-8"))
    errors = []
    if result.get("case_id") != case.get("case_id"):
        errors.append("case_id mismatch: result=%r case=%r"
                      % (result.get("case_id"), case.get("case_id")))
    for key in ("status", "sources", "uncertainty"):
        if key not in result:
            errors.append("missing honesty key '%s'" % key)
    notes_text = " ".join(result.get("notes", [])) \
        if isinstance(result.get("notes"), list) else ""
    for name, spec in contract_fields(case).items():
        required = bool(spec.get("required")) if isinstance(spec, dict) else True
        types = spec_types(spec)
        if name not in result:
            if required:
                errors.append("required contract field '%s' missing" % name)
            continue
        value = result[name]
        if value is None:
            if "null" not in types and required and name not in notes_text:
                errors.append(
                    "required field '%s' is null without an explanatory note "
                    "(honest null requires a notes entry)" % name)
            continue
        if not any(t in JSON_TYPES and isinstance(value, JSON_TYPES[t])
                   and (t == "boolean" or not isinstance(value, bool))
                   for t in types):
            errors.append("field '%s' has type %s, expected %s"
                          % (name, type(value).__name__, "/".join(types)))
    if result.get("status") not in ("success", "partial", "blocked"):
        errors.append("status must be success|partial|blocked")
    if result.get("status") == "partial" and not notes_text:
        errors.append("status=partial requires concrete limitations in notes")
    if errors:
        for e in errors:
            print("validate-result: FAIL: %s" % e)
        return 1
    print("validate-result: PASS (%d contract fields, case_id=%s)"
          % (len(contract_fields(case)), result.get("case_id")))
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(description="output-contract skeleton / fill / validate")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("result-skeleton")
    p.add_argument("--case", required=True)
    p.add_argument("--out", required=True)
    p.set_defaults(fn=cmd_skeleton)

    p = sub.add_parser("fill-result")
    p.add_argument("--case", required=True)
    p.add_argument("--artifacts", required=True)
    p.add_argument("--out", required=True)
    p.set_defaults(fn=cmd_fill)

    p = sub.add_parser("validate-result")
    p.add_argument("--case", required=True)
    p.add_argument("--result", required=True)
    p.set_defaults(fn=cmd_validate)

    args = ap.parse_args(argv)
    return args.fn(args)


if __name__ == "__main__":
    sys.exit(main())
