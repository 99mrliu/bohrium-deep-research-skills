#!/usr/bin/env python3
"""contract_parse.py -- parse a case's output_contract into a flat field plan
and materialize a skeleton result.json (the minute-zero partial deliverable).

Stdlib only. No network, no pip.

CLI:
  --case PATH   case.json (required)
  --task PATH   task.md (optional; used only for degraded fallback contract)
  --work DIR    working directory; contract_plan.json is written here (required)
  --out  DIR    directory for result_skeleton.json (default: --work)

Exit codes: 0 normal, 2 degraded (output_contract missing; minimal contract
derived from task.md), 1 fatal.
"""
import argparse
import json
import os
import re
import sys
import datetime

META_DEFAULTS = {
    "status": "partial",
    "sources": [],
    "uncertainty": [],
    "change_records": [],
}

OPTIONAL_KEY_SUFFIX = "?"
OPTIONAL_VALUE_RE = re.compile(r"(?i)^\s*optional\b|\(optional\)")


def type_name(v):
    if isinstance(v, bool):
        return "boolean"
    if isinstance(v, (int, float)):
        return "number"
    if isinstance(v, str):
        return "string"
    if isinstance(v, dict):
        return "object"
    if isinstance(v, list):
        return "array"
    return "any"


def is_optional(key, value):
    if isinstance(key, str) and key.endswith(OPTIONAL_KEY_SUFFIX):
        return True
    if isinstance(value, str) and OPTIONAL_VALUE_RE.search(value):
        return True
    if isinstance(value, dict) and value.get("optional") is True:
        return True
    return False


def clean_key(key):
    if isinstance(key, str) and key.endswith(OPTIONAL_KEY_SUFFIX):
        return key[:-1]
    return key


def plan_entry(path, expected_type, required=True):
    return {
        "path": path,
        "expected_type": expected_type,
        "required": bool(required),
        "filled": False,
        "fill_source": None,
    }


def flatten(contract, path, plan, required=True):
    """Recursively flatten a contract node into plan entries.

    Dicts recurse per key; lists contribute an array entry plus an element
    template under '<path>[]' (first element is the template); scalars are
    leaves typed by their template value.
    """
    path = path or "/"
    if isinstance(contract, dict):
        if not contract:
            plan.append(plan_entry(path, "object", required))
            return
        for k, v in contract.items():
            req = required and not is_optional(k, v)
            flatten(v, path.rstrip("/") + "/" + clean_key(str(k)), plan, req)
    elif isinstance(contract, list):
        plan.append(plan_entry(path, "array", required))
        if contract:
            # element template: first element governs
            flatten(contract[0], path.rstrip("/") + "[]", plan, required)
    else:
        plan.append(plan_entry(path, type_name(contract), required))


def skeletonize(contract):
    """Mirror the contract shape with null leaves."""
    if isinstance(contract, dict):
        out = {}
        for k, v in contract.items():
            out[clean_key(str(k))] = skeletonize(v)
        return out
    if isinstance(contract, list):
        if not contract:
            return []
        return [skeletonize(contract[0])]
    return None


QUESTION_LINE_RE = re.compile(
    r"^\s*(?:Q\d+\s*[:.)]|[-*+]|\d+[.)])\s+(?P<q>.+?\??)\s*$", re.IGNORECASE
)


def derive_minimal_contract(task_text):
    """Degraded fallback: build a minimal contract from task.md question lines."""
    questions = []
    for line in (task_text or "").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        m = QUESTION_LINE_RE.match(line)
        if m:
            questions.append(m.group("q").strip())
        elif line.endswith("?") and len(line) > 8:
            questions.append(line)
    if not questions:
        questions = ["(no question lines found in task.md)"]
    answers = {}
    for i, q in enumerate(questions, 1):
        answers["q%d" % i] = {"question": q, "answer": "", "evidence": ""}
    return {"answers": answers}, questions


def main(argv=None):
    ap = argparse.ArgumentParser(description="Parse output_contract into a field plan + skeleton result.")
    ap.add_argument("--case", required=True)
    ap.add_argument("--task", default=None)
    ap.add_argument("--work", required=True)
    ap.add_argument("--out", default=None)
    args = ap.parse_args(argv)

    try:
        with open(args.case, "r", encoding="utf-8") as f:
            case = json.load(f)
    except (OSError, json.JSONDecodeError) as e:
        print(json.dumps({"error": "cannot load case.json: %s" % e}))
        return 1

    case_id = case.get("case_id")
    if case_id is None:
        print(json.dumps({"error": "case.json has no case_id"}))
        return 1

    work = args.work
    out_dir = args.out or args.work
    os.makedirs(work, exist_ok=True)
    os.makedirs(out_dir, exist_ok=True)

    degraded = False
    prefilled_questions = []
    contract = case.get("output_contract")
    if contract is None:
        degraded = True
        task_text = ""
        if args.task:
            try:
                with open(args.task, "r", encoding="utf-8") as f:
                    task_text = f.read()
            except OSError:
                pass
        contract, prefilled_questions = derive_minimal_contract(task_text)

    plan = []
    flatten(contract, "", plan)

    skeleton = skeletonize(contract)
    if isinstance(skeleton, dict):
        result = skeleton
    else:
        # exotic top-level shape (list or scalar): wrap so honesty fields survive
        result = {"contract_payload": skeleton}
    result["case_id"] = case_id
    for k, v in META_DEFAULTS.items():
        if k not in result:
            result[k] = v

    # In degraded mode the question text is evidence itself: pre-fill it.
    if degraded and prefilled_questions:
        by_path = {e["path"]: e for e in plan}
        for i, q in enumerate(prefilled_questions, 1):
            p = "/answers/q%d/question" % i
            node = result.get("answers", {}).get("q%d" % i)
            if isinstance(node, dict):
                node["question"] = q
            if p in by_path:
                by_path[p]["filled"] = True
                by_path[p]["fill_source"] = "task.md (degraded contract)"

    plan_doc = {
        "case_id": case_id,
        "generated_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "degraded": degraded,
        "n_fields": len(plan),
        "n_required": sum(1 for e in plan if e["required"]),
        "fields": plan,
    }
    plan_path = os.path.join(work, "contract_plan.json")
    with open(plan_path, "w", encoding="utf-8") as f:
        json.dump(plan_doc, f, ensure_ascii=False, indent=2)

    skel_path = os.path.join(out_dir, "result_skeleton.json")
    with open(skel_path, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    summary = {
        "case_id": case_id,
        "degraded": degraded,
        "n_fields": len(plan),
        "n_required": plan_doc["n_required"],
        "plan": plan_path,
        "skeleton": skel_path,
        "status": result.get("status"),
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 2 if degraded else 0


if __name__ == "__main__":
    sys.exit(main())
