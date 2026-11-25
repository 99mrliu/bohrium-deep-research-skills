#!/usr/bin/env python3
"""contract_lint.py -- machine-lint a result.json deliverable against the
case contract and the field plan, with automatic status downgrade.

Stdlib only. No network, no pip.

CLI:
  --case PATH    case.json (required)
  --result PATH  result.json to lint (required)
  --plan PATH    contract_plan.json from contract_parse.py (required)
  --out PATH     lint_report.json destination
                 (default: <result dir>/lint_report.json)

Checks:
  (a) case_id identical to case.json            -> mismatch is FATAL (exit 1)
  (b) every required plan path exists, non-null, and type-consistent, or has
      a documented reason in `uncertainty`
  (c) status consistency: null required fields or unresolved uncertainty
      entries forbid "success" -> auto-downgrade to "partial" (result.json is
      rewritten) and record
  (d) every claim-like leaf (dict containing a numeric "value") needs a
      non-empty "source"/"locator" sibling or a non-empty top-level "sources"
  (e) where the contract shape carries a "unit" sibling, numeric content in
      that dict requires the unit to be filled

Exit codes: 0 clean, 2 violations found and/or downgrade applied (deliverable
still written), 1 fatal.
"""
import argparse
import json
import os
import sys
import datetime


def is_number(v):
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def type_ok(expected, value):
    if expected in (None, "any"):
        return True
    if expected == "number":
        return is_number(value)
    if expected == "string":
        return isinstance(value, str)
    if expected == "boolean":
        return isinstance(value, bool)
    if expected == "object":
        return isinstance(value, dict)
    if expected == "array":
        return isinstance(value, list)
    return True


def resolve(path, result):
    """Resolve a plan path against the result. '<seg>[]' expands over list
    elements. Returns (nodes, missing_flag)."""
    if path in ("", "/"):
        return [result], False
    segs = [s for s in path.split("/") if s]
    nodes = [result]
    for seg in segs:
        nxt = []
        if seg.endswith("[]"):
            key = seg[:-2]
            for n in nodes:
                if isinstance(n, dict) and isinstance(n.get(key), list):
                    nxt.extend(n[key])
        else:
            for n in nodes:
                if isinstance(n, dict) and seg in n:
                    nxt.append(n[seg])
        if not nxt:
            return [], True
        nodes = nxt
    return nodes, False


def uncertainty_entries(result):
    u = result.get("uncertainty", [])
    return u if isinstance(u, list) else [u]


def is_documented(path, entries):
    for e in entries:
        if isinstance(e, dict) and e.get("path") == path:
            return True
        if isinstance(e, str) and path in e:
            return True
    return False


def is_unresolved(e):
    if isinstance(e, dict):
        return e.get("resolved") is not True
    return True  # bare strings are unresolved notes


def walk_dicts(node, path=""):
    if isinstance(node, dict):
        yield node, path or "/"
        for k, v in node.items():
            yield from walk_dicts(v, (path or "") + "/" + str(k))
    elif isinstance(node, list):
        for i, v in enumerate(node):
            yield from walk_dicts(v, "%s[%d]" % (path or "/", i))


def has_numeric_content(d):
    for v in d.values():
        if is_number(v):
            return True
        if isinstance(v, list) and v and all(is_number(x) for x in v):
            return True
    return False


def main(argv=None):
    ap = argparse.ArgumentParser(description="Lint result.json against the output contract.")
    ap.add_argument("--case", required=True)
    ap.add_argument("--result", required=True)
    ap.add_argument("--plan", required=True)
    ap.add_argument("--out", default=None)
    args = ap.parse_args(argv)

    try:
        with open(args.case, "r", encoding="utf-8") as f:
            case = json.load(f)
        with open(args.result, "r", encoding="utf-8") as f:
            result = json.load(f)
        with open(args.plan, "r", encoding="utf-8") as f:
            plan_doc = json.load(f)
    except (OSError, json.JSONDecodeError) as e:
        print(json.dumps({"error": "cannot load input: %s" % e}))
        return 1

    out_path = args.out or os.path.join(os.path.dirname(os.path.abspath(args.result)),
                                        "lint_report.json")
    violations = []
    fatal = False
    downgraded = False

    def add(check, path, message):
        violations.append({"check": check, "path": path, "message": message})

    # (a) case_id identity -- fatal on mismatch
    case_id = case.get("case_id")
    result_id = result.get("case_id") if isinstance(result, dict) else None
    if result_id != case_id:
        fatal = True
        add("case_id", "/case_id",
            "FATAL: result case_id %r does not match case.json case_id %r"
            % (result_id, case_id))

    fields = plan_doc.get("fields", []) if isinstance(plan_doc, dict) else []
    unc = uncertainty_entries(result) if isinstance(result, dict) else []
    null_required = []

    # (b) plan coverage
    if not fatal:
        for entry in fields:
            path = entry.get("path", "")
            expected = entry.get("expected_type")
            required = entry.get("required", True)
            nodes, missing = resolve(path, result)
            if missing or not nodes:
                if required and not is_documented(path, unc):
                    add("coverage", path, "required path missing from result")
                    null_required.append(path)
                continue
            for node in nodes:
                if node is None:
                    if required and not is_documented(path, unc):
                        add("coverage", path, "required field is null (no documented reason)")
                        null_required.append(path)
                elif not type_ok(expected, node):
                    add("type", path,
                        "expected type %s, got %s" % (expected, type(node).__name__))

    # (c) status consistency / auto-downgrade
    unresolved_unc = [e for e in unc if is_unresolved(e)]
    status = result.get("status") if isinstance(result, dict) else None
    if not fatal:
        if status is None:
            add("status", "/status", "result has no status field")
        elif status == "success" and (null_required or unresolved_unc):
            result["status"] = "partial"
            downgraded = True
            reasons = []
            if null_required:
                reasons.append("%d required field(s) null/missing" % len(null_required))
            if unresolved_unc:
                reasons.append("%d unresolved uncertainty entr(ies)" % len(unresolved_unc))
            add("status", "/status",
                'auto-downgraded "success" -> "partial": ' + "; ".join(reasons))
            with open(args.result, "w", encoding="utf-8") as f:
                json.dump(result, f, ensure_ascii=False, indent=2)

    # (d) claim-like leaves need a locator
    if not fatal and isinstance(result, dict):
        top_sources = result.get("sources")
        has_top_sources = isinstance(top_sources, list) and len(top_sources) > 0
        for d, p in walk_dicts(result):
            if is_number(d.get("value")):
                loc = d.get("source") or d.get("locator")
                if not loc and not has_top_sources:
                    add("locator", p,
                        'claim-like leaf (numeric "value") lacks source/locator '
                        "and top-level sources is empty")

    # (e) units for numeric content where the contract shape has a unit sibling
    if not fatal:
        unit_paths = [e.get("path", "") for e in fields
                      if e.get("path", "").endswith("/unit")]
        for upath in unit_paths:
            parent_path = upath[: -len("/unit")] or "/"
            parents, missing = resolve(parent_path, result)
            if missing:
                continue
            units, _ = resolve(upath, result)
            for parent in parents:
                if isinstance(parent, dict) and has_numeric_content(parent):
                    if not any(u not in (None, "") for u in units):
                        add("unit", upath,
                            "numeric content present but contract-shaped unit is empty")

    report = {
        "case_id": case_id,
        "generated_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "result": os.path.abspath(args.result),
        "fatal": fatal,
        "downgraded": downgraded,
        "n_violations": len(violations),
        "violations": violations,
        "null_required_paths": null_required,
        "unresolved_uncertainty": len(unresolved_unc),
        "final_status": (result.get("status") if isinstance(result, dict) else None),
    }
    os.makedirs(os.path.dirname(os.path.abspath(out_path)) or ".", exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)

    print(json.dumps({
        "fatal": fatal,
        "downgraded": downgraded,
        "n_violations": len(violations),
        "final_status": report["final_status"],
        "lint_report": out_path,
    }, ensure_ascii=False, indent=2))

    if fatal:
        return 1
    if violations or downgraded:
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
