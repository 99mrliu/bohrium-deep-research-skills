#!/usr/bin/env python3
"""assemble_result.py -- write the contracted result.json for a kb case.

Copies ``contract_fields`` from the authored atoms document into the exact
fields required by the case output_contract, checks required keys and the
simple type subset, folds in the kb_lint verdict, and assigns an honest
status. Never deletes authored content; partial is a first-class outcome.
"""
import argparse
import json
import os
import sys

TYPES = {"string": str, "number": (int, float), "integer": int,
         "boolean": bool, "array": list, "object": dict}


def check(schema, value, path, problems):
    t = schema.get("type") if isinstance(schema, dict) else None
    if isinstance(t, list):
        if not any(_match(one, value) for one in t):
            problems.append("type mismatch at %s: want one of %s" % (path, t))
        return
    if t and not _match(t, value):
        problems.append("type mismatch at %s: want %s" % (path, t))
        return
    if t == "object" and isinstance(value, dict):
        for req in schema.get("required", []):
            if req not in value:
                problems.append("missing required field %s.%s" % (path, req))
        for key, sub in schema.get("properties", {}).items():
            if key in value:
                check(sub, value[key], "%s.%s" % (path, key), problems)
    if t == "array" and isinstance(value, list) and isinstance(schema.get("items"), dict):
        for i, item in enumerate(value):
            check(schema["items"], item, "%s[%d]" % (path, i), problems)


def _match(t, value):
    if value is None:
        return True  # null handled by null-reason policy upstream
    if t == "number":
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    if t == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    py = TYPES.get(t)
    return isinstance(value, py) if py else True


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--case", required=True)
    ap.add_argument("--atoms", required=True)
    ap.add_argument("--lint", help="kb_lint report json")
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    with open(args.case, encoding="utf-8") as fh:
        case = json.load(fh)
    with open(args.atoms, encoding="utf-8") as fh:
        doc = json.load(fh)
    lint_report = None
    if args.lint and os.path.exists(args.lint):
        with open(args.lint, encoding="utf-8") as fh:
            lint_report = json.load(fh)

    result = {"case_id": case.get("case_id", "unknown")}
    result.update(doc.get("contract_fields", {}))
    problems = []
    check(case.get("output_contract", {}), result, "$", problems)
    if result["case_id"] != case.get("case_id", result["case_id"]):
        problems.append("case_id mismatch")

    lint_fail = bool(lint_report and lint_report.get("hard_violations"))
    if lint_fail:
        problems.append("kb_lint hard violations: %d"
                        % len(lint_report["hard_violations"]))
    result["status"] = "partial" if problems else "success"
    result["checks"] = {"contract_problems": problems,
                        "kb_lint": (lint_report or {}).get("verdict", "not-run"),
                        "kb_warnings": len((lint_report or {}).get("warnings", []))}
    result["sources"] = doc.get("sources", [])
    result["uncertainty"] = doc.get("uncertainty", [])
    result["limits"] = doc.get("limits", [])
    os.makedirs(args.out, exist_ok=True)
    with open(os.path.join(args.out, "result.json"), "w", encoding="utf-8") as fh:
        json.dump(result, fh, ensure_ascii=False, indent=2)
    print(json.dumps({"status": result["status"], "problems": len(problems)},
                     ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
