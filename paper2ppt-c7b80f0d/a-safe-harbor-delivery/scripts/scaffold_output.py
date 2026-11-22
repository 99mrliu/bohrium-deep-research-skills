#!/usr/bin/env python3
"""scaffold_output.py — Phase P0: create a COMPLETE, VALID, HONESTLY-PARTIAL deliverable set.

Stdlib only. Idempotent: never overwrites richer existing values in result.json
(a value whose dict has status=="pending" is treated as a placeholder).

Usage:
  python3 scaffold_output.py --case /input/case.json --task /input/task.md \
      --outdir /app/output --workdir /app/work
"""
import argparse
import json
import os
import re
import sys
from datetime import datetime, timezone

DEFAULT_TIME_BUDGET_S = 900
DEFAULT_REQUEST_BUDGET = 64

# Main-line page types in strict priority order (lowest priority dropped first
# when a slide limit bites: backup -> limitations -> extra evidence).
BASE_PLAN = [
    ("title", "Title page"),
    ("problem", "Problem & background"),
    ("gap", "Gap & research question"),
    ("method", "Method overview"),
    ("evidence-1", "Key result — Figure/Table 1"),
    ("evidence-2", "Key result — Figure/Table 2"),
    ("limitations", "Limitations"),
    ("conclusions", "Conclusions & takeaways"),
    ("backup", "Backup / supplementary"),
]
# Removal order when the plan must shrink (first entry removed first).
DROP_ORDER = ["backup", "limitations", "evidence-2", "gap", "evidence-1", "problem"]

PLACEHOLDER_BULLETS = {
    "title": ["[pending: paper title from PDF header]",
              "[pending: authors, venue, year]",
              "[pending: presenter name & date]"],
    "problem": ["[pending: extract problem statement from §Introduction]"],
    "gap": ["[pending: extract gap & research question from §Introduction / §Related Work]"],
    "method": ["[pending: extract method overview from §Method]"],
    "limitations": ["[pending: extract limitations from §Discussion / §Conclusion]"],
    "conclusions": ["[pending: 2–3 takeaway bullets from §Conclusion]"],
    "backup": ["[pending: supplementary tables / ablations]"],
}


def placeholder_bullets(stype):
    if stype.startswith("evidence"):
        k = stype.split("-", 1)[1]
        return ["[pending: key result for Figure/Table %s, verbatim from §Experiments]" % k,
                "[pending: exact metric values with section/table anchor]"]
    return list(PLACEHOLDER_BULLETS.get(stype, ["[pending]"]))


def placeholder_notes(stype, nxt):
    return "TODO: speaker notes — 30–45s talk track; transition to next slide (%s)." % nxt


def utcnow():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def load_json_tolerant(path):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        return {}
    except Exception as e:
        sys.stderr.write("WARN: could not parse %s (%s); continuing with empty case\n" % (path, e))
        return {}


def extract_case_id(case):
    for k in ("case_id", "caseId", "id", "name"):
        v = case.get(k)
        if isinstance(v, (str, int)) and str(v).strip():
            return str(v)
    return "unknown-case"


def extract_contract_fields(case):
    """Return list of required output-contract field names, tolerating shapes."""
    oc = case.get("output_contract") or case.get("outputContract") or {}
    if isinstance(oc, list):  # contract given directly as a list
        raw = oc
    elif isinstance(oc, dict):
        raw = None
        for k in ("required_fields", "required", "fields", "requiredFields", "outputs"):
            if k in oc:
                raw = oc[k]
                break
        if raw is None:
            raw = []
    else:
        raw = []
    names = []
    if isinstance(raw, dict):
        raw = list(raw.keys())
    for item in raw if isinstance(raw, list) else []:
        if isinstance(item, str) and item.strip():
            names.append(item.strip())
        elif isinstance(item, dict):
            for k in ("name", "field", "key", "id"):
                if isinstance(item.get(k), str) and item[k].strip():
                    names.append(item[k].strip())
                    break
    # de-dup, keep order
    seen, out = set(), []
    for n in names:
        if n not in seen:
            seen.add(n)
            out.append(n)
    return out


def extract_constraints(case, task_text):
    c = {}

    def pick(*keys, src=case):
        for k in keys:
            if k in src and src[k] not in (None, ""):
                return src[k]
        return None

    cons = case.get("constraints") if isinstance(case.get("constraints"), dict) else {}
    c["audience"] = pick("audience", src=cons) or pick("audience")
    c["duration_minutes"] = pick("duration_minutes", "duration", "time_limit", src=cons) \
        or pick("duration_minutes", "duration")
    c["slide_limit"] = pick("slide_limit", "max_slides", "slideLimit", src=cons) \
        or pick("slide_limit", "max_slides")
    c["language"] = pick("language", "lang", src=cons) or pick("language")
    c["template_path"] = pick("template", "template_path", "templatePath", src=cons) \
        or pick("template", "template_path")
    c["starting_deck"] = pick("starting_deck", "start_deck", "base_deck", src=cons) \
        or pick("starting_deck", "start_deck")
    # last-resort hints from task.md free text
    if not c["slide_limit"]:
        m = re.search(r"(\d{1,2})\s*(?:slides?|页|张)", task_text or "")
        if m:
            c["slide_limit"] = int(m.group(1))
    if not c["language"] and task_text:
        if re.search(r"[\u4e00-\u9fff]", task_text):
            c["language"] = "zh"
    try:
        c["slide_limit"] = int(c["slide_limit"]) if c["slide_limit"] else None
    except (TypeError, ValueError):
        c["slide_limit"] = None
    return c


def build_slide_plan(slide_limit):
    plan = [{"type": t, "label": l} for t, l in BASE_PLAN]
    if slide_limit and slide_limit >= 1:
        if slide_limit < 4:
            plan = [p for p in plan if p["type"] in ("title", "method", "conclusions")][:slide_limit]
        else:
            drop = list(DROP_ORDER)
            while len(plan) > slide_limit and drop:
                victim = drop.pop(0)
                plan = [p for p in plan if p["type"] != victim]
            plan = plan[:slide_limit]
    for i, p in enumerate(plan):
        p["index"] = i + 1
        p["status"] = "pending"
        p["bullets"] = placeholder_bullets(p["type"])
        nxt = plan[i + 1]["label"] if i + 1 < len(plan) else "end of deck"
        p["notes"] = placeholder_notes(p["type"], nxt)
        p["title"] = p["label"]
    return plan


def is_placeholder(v):
    return isinstance(v, dict) and v.get("status") == "pending"


def main(argv=None):
    ap = argparse.ArgumentParser(description="P0 scaffold: valid partial deliverable set")
    ap.add_argument("--case", default="/input/case.json")
    ap.add_argument("--task", default="/input/task.md")
    ap.add_argument("--outdir", default="/app/output")
    ap.add_argument("--workdir", default="/app/work")
    ap.add_argument("--time-budget", type=int, default=DEFAULT_TIME_BUDGET_S)
    ap.add_argument("--request-budget", type=int, default=DEFAULT_REQUEST_BUDGET)
    args = ap.parse_args(argv)

    os.makedirs(args.outdir, exist_ok=True)
    os.makedirs(args.workdir, exist_ok=True)

    case = load_json_tolerant(args.case)
    try:
        with open(args.task, "r", encoding="utf-8") as f:
            task_text = f.read()
    except Exception:
        task_text = ""

    case_id = extract_case_id(case)
    fields = extract_contract_fields(case)
    cons = extract_constraints(case, task_text)
    now = utcnow()

    # ---- result.json (merge: keep existing non-placeholder values) ---------- #
    rpath = os.path.join(args.outdir, "result.json")
    existing = load_json_tolerant(rpath) if os.path.exists(rpath) else {}
    result = dict(existing) if isinstance(existing, dict) else {}
    result["case_id"] = result.get("case_id") or case_id
    if result.get("status") not in ("success", "partial", "unable_to_determine"):
        result["status"] = "partial"
    for f in fields:
        if f not in result or is_placeholder(result.get(f)):
            result[f] = {"status": "pending",
                         "detail": "not yet produced; P0 scaffold placeholder"}
    result.setdefault("sources", [])
    unc = list(result.get("uncertainty") or [])
    for u in ["Paper content not yet extracted (P0 scaffold).",
              "Slides contain honest [pending: ...] placeholders only.",
              "Render verification not yet performed."]:
        if u not in unc:
            unc.append(u)
    result["uncertainty"] = unc
    result["change_record"] = result.get("change_record") or []
    result["scaffold"] = {"created_at": result.get("scaffold", {}).get("created_at", now),
                          "updated_at": now, "phase": "P0",
                          "contract_fields": fields}
    with open(rpath, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    # ---- session_state.json (create once; refresh timestamps on rerun) ------ #
    spath = os.path.join(args.workdir, "session_state.json")
    if os.path.exists(spath):
        state = load_json_tolerant(spath)
        state.setdefault("phase", "P0")
        state["updated_at"] = now
    else:
        state = {
            "case_id": case_id,
            "phase": "P0",
            "created_at": now,
            "updated_at": now,
            "budget": {
                "time_budget_s": args.time_budget,
                "request_budget": args.request_budget,
                "started_at": now,
                "checkpoints": {
                    "P0_scaffold_done_pct": 10,
                    "P1_extract_plan_done_pct": 35,
                    "P2_slide_upgrades_done_pct": 80,
                    "P3_render_verify_done_pct": 95,
                    "P4_finalize_reserve_s": 120,
                },
            },
            "constraints": cons,
            "contract_fields": fields,
            "deck_path": os.path.join(args.outdir, "deck.pptx"),
            "backend": None,
            "slide_plan": build_slide_plan(cons.get("slide_limit")),
        }
    with open(spath, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)

    print("scaffold OK")
    print("  case_id        :", case_id)
    print("  contract fields:", fields or "(none declared)")
    print("  slide limit    :", cons.get("slide_limit") or "(none)")
    print("  template       :", cons.get("template_path") or "(none)")
    print("  slide plan     :", [p["type"] for p in state["slide_plan"]])
    print("  result.json    :", rpath)
    print("  session_state  :", spath)
    return 0


if __name__ == "__main__":
    sys.exit(main())
