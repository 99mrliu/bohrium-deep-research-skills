#!/usr/bin/env python3
"""compile_report.py — 严重度校准与修改建议编译器 for paper-audit skills.

Pure Python 3.8+ standard library. Deterministic. Zero dependencies.
Turns a raw findings list into a reviewable deliverable: calibrated
severities with written 3-axis rationale, executable sentence-level revision
specs, an anti-vague lexicon gate, a fix-priority queue, and a rendered
report.md. It judges the FORM of findings, never the paper itself.

Subcommands:
  lint     --findings F --work DIR        form gate (exit 7 = violations)
  priority --findings F                   fix-order queue
  compile  --findings F --work DIR --out DIR [--case case.json]
                                          report.md + result_fields.json (+quote gate
                                          when work/sentences.jsonl exists)

Exit codes: 0 ok; 3 fatal input; lint 7 violations; compile 4 quote violations.
"""
import argparse
import json
import os
import re
import sys

CATEGORIES = ["fact_check", "citation_support", "method_design",
              "stats_report", "reasoning_chain", "academic_norm"]
TYPES = ["factual_error", "insufficient_evidence", "norm_issue", "suggestion"]
SEVERITIES = ["critical", "major", "minor", "suggestion"]
STATUSES = ["confirmed", "needs_review"]
OPERATIONS = ["rewrite", "insert", "delete", "downgrade_strength",
              "add_citation", "add_data", "recheck"]
RATIONALE_AXES = ["main_conclusion_impact", "fixability", "reproducibility_impact"]

VAGUE_PATTERNS = [
    "建议加强", "建议补充论证", "进一步完善", "建议重视", "加强逻辑",
    "建议完善", "建议补充说明", "建议深入", "strengthen the argument",
    "add more evidence", "further discussion",
]
SEV_RANK = {"critical": 0, "major": 1, "minor": 2, "suggestion": 3}
FIX_RANK = {"easy_single_edit": 0, "moderate_rewrite": 1,
            "needs_new_analysis": 2, "needs_new_data": 3}


def eprint(*a):
    print(*a, file=sys.stderr)


def atomic_write(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        fh.write(data)
    os.replace(tmp, path)


def atomic_write_json(path, obj):
    atomic_write(path, json.dumps(obj, ensure_ascii=False, indent=2) + "\n")


def load_findings(path):
    with open(path, encoding="utf-8") as fh:
        findings = json.load(fh)
    if not isinstance(findings, list):
        raise ValueError("findings must be a JSON array")
    return findings


# -------------------------------------------------------------------- lint
def lint_findings(findings):
    violations, warnings = [], []
    for i, f in enumerate(findings):
        fid = f.get("id", "#%d" % i)
        for req in ("id", "sentence_id", "quote", "category", "type",
                    "severity", "status", "evidence", "revision"):
            if req not in f or f[req] in (None, ""):
                violations.append({"id": fid, "problem": "missing field: %s" % req})
        if f.get("category") and f["category"] not in CATEGORIES:
            violations.append({"id": fid, "problem": "category %r not in %s"
                               % (f["category"], CATEGORIES)})
        if f.get("type") and f["type"] not in TYPES:
            violations.append({"id": fid, "problem": "type %r not in %s"
                               % (f["type"], TYPES)})
        if f.get("severity") and f["severity"] not in SEVERITIES:
            violations.append({"id": fid, "problem": "severity %r not in %s"
                               % (f["severity"], SEVERITIES)})
        if f.get("status") and f["status"] not in STATUSES:
            violations.append({"id": fid, "problem": "status %r not in %s"
                               % (f["status"], STATUSES)})

        rat = f.get("rationale")
        if f.get("status") == "confirmed":
            if not isinstance(rat, dict):
                violations.append({"id": fid, "problem":
                                   "confirmed finding requires rationale{3 axes}"})
            else:
                for ax in RATIONALE_AXES:
                    if not rat.get(ax):
                        violations.append({"id": fid, "problem":
                                           "rationale missing axis: %s" % ax})
                fx = rat.get("fixability")
                if fx and fx not in FIX_RANK:
                    violations.append({"id": fid, "problem":
                                       "fixability %r not in %s" % (fx, list(FIX_RANK))})

        rev = f.get("revision") or ""
        if rev:
            if len(rev) < 30:
                violations.append({"id": fid, "problem":
                                   "revision too short to be executable (<30 chars)"})
            for pat in VAGUE_PATTERNS:
                if pat in rev:
                    violations.append({"id": fid, "problem":
                                       "vague revision lexicon hit: %r" % pat})
            op = (f.get("revision_op") or "")
            if op not in OPERATIONS:
                violations.append({"id": fid, "problem":
                                   "revision_op must be one of %s" % OPERATIONS})
            sid = f.get("sentence_id") or ""
            if sid and sid not in rev and f.get("revision_op") != "insert":
                warnings.append({"id": fid, "problem":
                                 "revision does not name its sentence id %s" % sid})
    sevs = [f.get("severity") for f in findings if f.get("severity")]
    if len(sevs) >= 4 and len(set(sevs)) == 1:
        warnings.append({"id": "GLOBAL", "problem":
                         "all %d findings share severity %r; 严重度一律相同通常是定级失真，"
                         "请逐条复核 rationale" % (len(sevs), sevs[0])})
    return violations, warnings


def cmd_lint(args):
    try:
        findings = load_findings(args.findings)
    except (OSError, ValueError) as e:
        eprint("FATAL: %s" % e)
        return 3
    violations, warnings = lint_findings(findings)
    atomic_write_json(os.path.join(args.work, "lint_report.json"), {
        "violations": violations, "warnings": warnings,
        "checked": len(findings)})
    for v in violations:
        eprint("VIOLATION %s: %s" % (v["id"], v["problem"]))
    for w in warnings:
        eprint("WARNING %s: %s" % (w["id"], w["problem"]))
    if violations:
        return 7
    print(json.dumps({"status": "ok", "checked": len(findings),
                      "warnings": len(warnings)}, ensure_ascii=False))
    return 0


# ---------------------------------------------------------------- priority
def fix_order(findings):
    def key(f):
        sev = SEV_RANK.get(f.get("severity"), 9)
        fx = FIX_RANK.get((f.get("rationale") or {}).get("fixability"), 9)
        return (sev, fx)
    return sorted(findings, key=key)


def cmd_priority(args):
    try:
        findings = load_findings(args.findings)
    except (OSError, ValueError) as e:
        eprint("FATAL: %s" % e)
        return 3
    queue = [{"order": i + 1, "id": f.get("id"), "severity": f.get("severity"),
              "fixability": (f.get("rationale") or {}).get("fixability"),
              "revision_op": f.get("revision_op")}
             for i, f in enumerate(fix_order(findings))]
    print(json.dumps({"fix_queue": queue}, ensure_ascii=False, indent=1))
    return 0


# ----------------------------------------------------------------- compile
def cmd_compile(args):
    try:
        findings = load_findings(args.findings)
    except (OSError, ValueError) as e:
        eprint("FATAL: %s" % e)
        return 3
    violations, warnings = lint_findings(findings)
    if violations:
        for v in violations:
            eprint("VIOLATION %s: %s (run lint first and fix)" % (v["id"], v["problem"]))
        return 7

    # optional verbatim quote gate
    spath = os.path.join(args.work, "sentences.jsonl")
    if os.path.isfile(spath):
        sents = {}
        with open(spath, encoding="utf-8") as fh:
            for ln in fh:
                r = json.loads(ln)
                sents[r["id"]] = r["text"]
        problems = []
        for f in findings:
            sid, q = f.get("sentence_id"), f.get("quote", "")
            if sid not in sents:
                problems.append({"id": f.get("id"), "problem": "unknown sentence_id %r" % sid})
            elif not q or q not in sents[sid]:
                problems.append({"id": f.get("id"),
                                 "problem": "quote not verbatim substring of %s" % sid})
        if problems:
            atomic_write_json(os.path.join(args.work, "quote_problems.json"), problems)
            for p in problems:
                eprint("QUOTE VIOLATION %(id)s: %(problem)s" % p)
            return 4

    ordered = fix_order(findings)
    lines = ["# 论文逻辑与论证审查报告", "",
             "共 %d 条 finding（critical %d / major %d / minor %d / suggestion %d；待复核 %d）。"
             % (len(findings),
                sum(1 for f in findings if f.get("severity") == "critical"),
                sum(1 for f in findings if f.get("severity") == "major"),
                sum(1 for f in findings if f.get("severity") == "minor"),
                sum(1 for f in findings if f.get("severity") == "suggestion"),
                sum(1 for f in findings if f.get("status") == "needs_review")),
             "", "按修复优先级排序：", ""]
    for i, f in enumerate(ordered):
        rat = f.get("rationale") or {}
        lines += [
            "## %d. [%s] %s — %s" % (i + 1, (f.get("severity") or "?").upper(),
                                     f.get("id"), f.get("category")),
            "",
            "- 位置：%s" % f.get("sentence_id"),
            "- 原文：> %s" % f.get("quote"),
            "- 类型：%s / 状态：%s" % (f.get("type"), f.get("status")),
            "- 依据：%s" % f.get("evidence"),
            "- 定级理由：主结论影响=%s；可修正性=%s；可复现性影响=%s"
            % (rat.get("main_conclusion_impact"), rat.get("fixability"),
               rat.get("reproducibility_impact")),
            "- 修改建议（%s）：%s" % (f.get("revision_op"), f.get("revision")),
            ""]
    if warnings:
        lines += ["## 形式告警", ""] + ["- %s: %s" % (w["id"], w["problem"])
                                        for w in warnings]
    atomic_write(os.path.join(args.out, "report.md"), "\n".join(lines) + "\n")

    fields = {
        "findings": ordered,
        "fix_queue": [{"order": i + 1, "id": f.get("id"),
                       "severity": f.get("severity"),
                       "revision_op": f.get("revision_op")}
                      for i, f in enumerate(ordered)],
        "severity_distribution": {s: sum(1 for f in findings
                                         if f.get("severity") == s)
                                  for s in SEVERITIES},
        "lint_warnings": warnings,
    }
    if args.case and os.path.isfile(args.case):
        with open(args.case, encoding="utf-8") as fh:
            case = json.load(fh)
        if "case_id" in case:
            fields["case_id"] = case["case_id"]
    atomic_write_json(os.path.join(args.out, "result_fields.json"), fields)
    print(json.dumps({"status": "ok", "findings": len(findings),
                      "report": os.path.join(args.out, "report.md")},
                     ensure_ascii=False))
    return 0


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("lint")
    p.add_argument("--findings", required=True)
    p.add_argument("--work", required=True)
    p.set_defaults(fn=cmd_lint)
    p = sub.add_parser("priority")
    p.add_argument("--findings", required=True)
    p.set_defaults(fn=cmd_priority)
    p = sub.add_parser("compile")
    p.add_argument("--findings", required=True)
    p.add_argument("--work", required=True)
    p.add_argument("--out", required=True)
    p.add_argument("--case")
    p.set_defaults(fn=cmd_compile)
    args = ap.parse_args()
    sys.exit(args.fn(args))


if __name__ == "__main__":
    main()
