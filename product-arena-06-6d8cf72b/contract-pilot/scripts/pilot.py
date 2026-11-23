#!/usr/bin/env python3
"""pilot.py -- contract-driven process control for a reading case.

This tool deliberately does NOT read the paper. It guarantees the *process*:
the deliverable exists from minute one, conforms to the case output_contract,
records every change, and never claims a status the evidence cannot support.

Subcommands:
  init       --case CASE.json --out OUTDIR
               Write a skeleton result.json (status in_progress) + plan.json
               with budget checkpoints + open audit-trail.jsonl. Run this
               BEFORE reading anything.
  checkpoint --out OUTDIR --phase P --note "..."
               Append a checkpoint entry; prints the budget guidance for P.
  validate   --case CASE.json --result RESULT.json [--out REPORT.json]
               Schema-subset validation + honesty checks (null-without-reason,
               status inconsistencies, unknown schema keywords as warnings).
  finalize   --case CASE.json --result RESULT.json --out OUTDIR
               Re-validate, downgrade to partial when problems exist (never
               delete authored content), stamp the audit trail, write the
               final result.json into OUTDIR.

Exit codes: init/checkpoint 0; validate/finalize 0 when no hard problems,
2 with hard problems (the report is the repair list, not a veto).
"""
import argparse
import datetime
import json
import os
import re
import sys

JSON_TYPES = {"string": str, "number": (int, float), "integer": int,
              "boolean": bool, "array": list, "object": dict}
KNOWN_KEYS = {"type", "required", "properties", "items", "enum", "default",
              "additionalProperties", "$schema", "$id", "title", "description",
              "minimum", "maximum", "minItems", "maxItems", "minLength",
              "maxLength", "pattern", "uniqueItems", "format", "const"}
CHECKPOINTS = {
    "init": (0, "骨架已落盘：result.json 存在即安全。现在开始阅读材料。"),
    "t40": (40, "应有完整但浅的交付：合同每个必需字段都已有初稿值。"),
    "t70": (70, "每个请求项都应有答案与锚点；剩余时间只做决定性核查与修复。"),
    "t100": (100, "停止新增内容：跑 validate，修复硬问题，finalize。"),
}


def now():
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def load_json(path):
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def audit(out_dir, event, detail=None):
    entry = {"ts": now(), "event": event, "detail": detail}
    with open(os.path.join(out_dir, "audit-trail.jsonl"), "a", encoding="utf-8") as fh:
        fh.write(json.dumps(entry, ensure_ascii=False) + "\n")


# ------------------------------------------------------------- validation
def validate_schema(schema, value, path, problems, warnings):
    if not isinstance(schema, dict):
        return
    for key in schema:
        if key not in KNOWN_KEYS:
            warnings.append("unknown schema keyword %r at %s" % (key, path))
    t = schema.get("type")
    if isinstance(t, list):
        if value is not None and not any(match(one, value) for one in t):
            problems.append("type mismatch at %s: want one of %s" % (path, t))
        return
    if t and value is not None and not match(t, value):
        problems.append("type mismatch at %s: want %s, got %s"
                        % (path, t, type(value).__name__))
        return
    if value is None:
        return
    if t == "object" and isinstance(value, dict):
        for req in schema.get("required", []):
            if req not in value:
                problems.append("missing required field %s.%s" % (path, req))
        for key, sub in schema.get("properties", {}).items():
            if key in value:
                validate_schema(sub, value[key], "%s.%s" % (path, key),
                                problems, warnings)
        if schema.get("additionalProperties") is False:
            for key in value:
                if key not in schema.get("properties", {}):
                    warnings.append("additional property %s.%s not in schema"
                                    % (path, key))
    if t == "array" and isinstance(value, list) and isinstance(schema.get("items"), dict):
        for i, item in enumerate(value):
            validate_schema(schema["items"], item, "%s[%d]" % (path, i),
                            problems, warnings)
    if "enum" in schema and value not in schema["enum"]:
        problems.append("value at %s not in enum %s" % (path, schema["enum"]))
    if "pattern" in schema and isinstance(value, str) \
            and not re.search(schema["pattern"], value):
        problems.append("value at %s fails pattern %s" % (path, schema["pattern"]))
    if "minItems" in schema and isinstance(value, list) and len(value) < schema["minItems"]:
        problems.append("array at %s shorter than minItems" % path)
    if "maxItems" in schema and isinstance(value, list) and len(value) > schema["maxItems"]:
        problems.append("array at %s longer than maxItems" % path)
    if "minLength" in schema and isinstance(value, str) and len(value) < schema["minLength"]:
        problems.append("string at %s shorter than minLength" % path)
    if "maxLength" in schema and isinstance(value, str) and len(value) > schema["maxLength"]:
        problems.append("string at %s longer than maxLength" % path)


def match(t, value):
    if t == "number":
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    if t == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    py = JSON_TYPES.get(t)
    return isinstance(value, py) if py else True


def null_paths(node, path="$"):
    out = []
    if node is None:
        out.append(path)
    elif isinstance(node, dict):
        for k, v in node.items():
            out += null_paths(v, "%s.%s" % (path, k))
    elif isinstance(node, list):
        for i, v in enumerate(node):
            out += null_paths(v, "%s[%d]" % (path, i))
    return out


def validate_result(case, result):
    problems, warnings = [], []
    contract = case.get("output_contract", {})
    validate_schema(contract, result, "$", problems, warnings)
    if result.get("case_id") != case.get("case_id", result.get("case_id")):
        problems.append("case_id missing or mismatched")
    reasons = result.get("null_reasons", {}) or {}
    unexplained = [p for p in null_paths(result)
                   if p not in reasons and not p.startswith("$.null_reasons")]
    for p in unexplained:
        problems.append("null without reason at %s" % p)
    status = result.get("status")
    if status == "success" and problems:
        problems.append("status says success but %d problems remain" % len(problems))
    if status in ("failed", "refused") and not result.get("failure") \
            and not result.get("reason"):
        problems.append("failed/refused status needs a failure/reason field")
    return {"problems": problems, "warnings": warnings,
            "unexplained_nulls": unexplained,
            "verdict": "pass" if not problems else "fail"}


# -------------------------------------------------------------- commands
def cmd_init(args):
    case = load_json(args.case)
    os.makedirs(args.out, exist_ok=True)
    result = {"case_id": case.get("case_id", "unknown"), "status": "in_progress",
              "null_reasons": {},
              "note": "skeleton written by pilot init before reading; replace "
                      "with real content and run validate/finalize"}
    with open(os.path.join(args.out, "result.json"), "w", encoding="utf-8") as fh:
        json.dump(result, fh, ensure_ascii=False, indent=2)
    plan = {
        "case_id": case.get("case_id"),
        "budget": {"model_requests": 64, "seconds": 900},
        "checkpoints": {k: {"at_percent": v[0], "expectation": v[1]}
                        for k, v in CHECKPOINTS.items()},
        "required_fields": _required_paths(case.get("output_contract", {})),
        "rule": "deliver early, improve incrementally; never spend the budget "
                "building adjacent tooling",
    }
    with open(os.path.join(args.out, "plan.json"), "w", encoding="utf-8") as fh:
        json.dump(plan, fh, ensure_ascii=False, indent=2)
    audit(args.out, "init", {"case_id": case.get("case_id")})
    print(json.dumps({"plan": args.out + "/plan.json",
                      "required_fields": plan["required_fields"]}, ensure_ascii=False))
    return 0


def _required_paths(schema, path="$"):
    out = []
    if isinstance(schema, dict) and schema.get("type") == "object":
        for req in schema.get("required", []):
            out.append(path + "." + req)
        for key, sub in schema.get("properties", {}).items():
            out += _required_paths(sub, path + "." + key)
    return out


def cmd_checkpoint(args):
    pct, guidance = CHECKPOINTS.get(args.phase, (None, "custom checkpoint"))
    audit(args.out, "checkpoint", {"phase": args.phase, "note": args.note})
    print(json.dumps({"phase": args.phase, "at_percent": pct,
                      "guidance": guidance}, ensure_ascii=False))
    return 0


def cmd_validate(args):
    case = load_json(args.case)
    result = load_json(args.result)
    report = validate_result(case, result)
    if args.out:
        with open(args.out, "w", encoding="utf-8") as fh:
            json.dump(report, fh, ensure_ascii=False, indent=2)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["verdict"] == "pass" else 2


def cmd_finalize(args):
    case = load_json(args.case)
    result = load_json(args.result)
    report = validate_result(case, result)
    if report["verdict"] == "pass":
        if result.get("status") in (None, "in_progress"):
            result["status"] = "success"
    else:
        if result.get("status") == "success":
            result["status"] = "partial"  # honesty downgrade, content preserved
        result.setdefault("status", "partial")
        gaps = result.setdefault("limits", [])
        for p in report["problems"]:
            if p not in gaps:
                gaps.append("finalize gap: " + p)
    result["validation"] = report
    os.makedirs(args.out, exist_ok=True)
    with open(os.path.join(args.out, "result.json"), "w", encoding="utf-8") as fh:
        json.dump(result, fh, ensure_ascii=False, indent=2)
    audit(args.out, "finalize", {"verdict": report["verdict"],
                                 "status": result["status"]})
    print(json.dumps({"status": result["status"],
                      "problems": len(report["problems"]),
                      "warnings": len(report["warnings"])}, ensure_ascii=False))
    return 0 if report["verdict"] == "pass" else 2


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("init")
    p.add_argument("--case", required=True)
    p.add_argument("--out", required=True)
    p.set_defaults(fn=cmd_init)
    p = sub.add_parser("checkpoint")
    p.add_argument("--out", required=True)
    p.add_argument("--phase", required=True, choices=list(CHECKPOINTS) + ["custom"])
    p.add_argument("--note", default="")
    p.set_defaults(fn=cmd_checkpoint)
    p = sub.add_parser("validate")
    p.add_argument("--case", required=True)
    p.add_argument("--result", required=True)
    p.add_argument("--out")
    p.set_defaults(fn=cmd_validate)
    p = sub.add_parser("finalize")
    p.add_argument("--case", required=True)
    p.add_argument("--result", required=True)
    p.add_argument("--out", required=True)
    p.set_defaults(fn=cmd_finalize)
    args = ap.parse_args()
    sys.exit(args.fn(args))


if __name__ == "__main__":
    main()
