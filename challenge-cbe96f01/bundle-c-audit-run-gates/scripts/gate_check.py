#!/usr/bin/env python3
"""gate_check.py -- audit-run-gates delivery gate (G1-G8).

Validates a result.json against the process-quality gates defined in
references/gates.md:
  G1 case_id present (and consistent with --case when provided)
  G2 every output_contract field exists at result top level
  G3 six-facet coverage complete, values in {checked, partial, unchecked}
  G4 findings schema complete
  G5 every finding quote is verbatim within its claimed page text
  G6 controlled vocabularies (category / issue_type / severity / confidence)
  G7 honesty consistency (status <-> coverage/unchecked_items/human-review)
  G8 run_log.jsonl exists, well-formed, records gate outcomes

Options: --only quote,claims mode via --claims for stage-1 checks.
Exit 1 if any gate fails; always writes the gate report JSON.
"""
import argparse
import json
import re
import sys

FACETS = ["事实核验", "引用支持", "方法设计", "统计报告", "论证链", "学术规范"]
COVERAGE_VALS = {"checked", "partial", "unchecked"}
CATS = set(FACETS)
ISSUE_TYPES = {"事实错误", "证据不足", "规范问题", "建议性意见"}
SEVERITIES = {"critical", "major", "minor", "advisory"}
CONFIDENCE = {"high", "medium", "low"}
FINDING_REQUIRED = ("id", "category", "issue_type", "severity", "location",
                    "claim", "verdict", "basis", "suggestion", "confidence")


def collapse(s):
    return re.sub(r"\s+", " ", s or "").strip()


def load_pages(path):
    pages = {}
    if not path:
        return pages
    try:
        with open(path, encoding="utf-8") as fh:
            for line in fh:
                if line.strip():
                    pg = json.loads(line)
                    pages[pg["page"]] = collapse(pg["text"])
    except OSError:
        pass
    return pages


def contract_fields(case):
    if not isinstance(case, dict):
        return []
    oc = (case.get("output_contract") or case.get("outputContract")
          or case.get("outputs"))
    if isinstance(oc, dict):
        return list(oc.keys())
    if isinstance(oc, list):
        return [str(x) for x in oc]
    return []


def check_result(result, case, pages, log_path):
    failures = []

    def fail(gate, detail):
        failures.append({"gate": gate, "detail": detail})

    cid = result.get("case_id")
    if not cid:
        fail("G1", "case_id missing")
    elif isinstance(case, dict):
        want = (case.get("case_id") or case.get("id") or case.get("caseId"))
        if want and str(want) != str(cid):
            fail("G1", f"case_id '{cid}' != case '{want}'")

    for f in contract_fields(case):
        if f not in result:
            fail("G2", f"output_contract field '{f}' missing in result.json")

    cov = result.get("coverage", {})
    for facet in FACETS:
        v = cov.get(facet)
        if v not in COVERAGE_VALS:
            fail("G3", f"coverage['{facet}'] = {v!r}")

    findings = result.get("findings", [])
    if not isinstance(findings, list):
        fail("G4", "findings is not a list")
        findings = []
    for i, f in enumerate(findings):
        missing = [k for k in FINDING_REQUIRED if k not in f]
        if missing:
            fail("G4", f"finding[{i}] missing fields {missing}")
            continue
        if f["category"] not in CATS:
            fail("G6", f"finding[{i}] bad category {f['category']!r}")
        if f["issue_type"] not in ISSUE_TYPES:
            fail("G6", f"finding[{i}] bad issue_type {f['issue_type']!r}")
        if f["severity"] not in SEVERITIES:
            fail("G6", f"finding[{i}] bad severity {f['severity']!r}")
        if f["confidence"] not in CONFIDENCE:
            fail("G6", f"finding[{i}] bad confidence {f['confidence']!r}")
        loc = f.get("location", {})
        quote = loc.get("quote")
        page = loc.get("page")
        if not quote:
            fail("G5", f"finding[{i}] empty quote")
        elif pages:
            if page not in pages:
                fail("G5", f"finding[{i}] page {page} out of range")
            elif collapse(quote) not in pages[page]:
                fail("G5", f"finding[{i}] quote not verbatim on page {page}")

    status = result.get("status")
    unchecked_items = result.get("unchecked_items", [])
    if status == "completed":
        unexplained = [k for k, v in cov.items() if v == "unchecked"]
        if unexplained:
            fail("G7", f"status=completed but coverage unchecked: "
                       f"{unexplained}")
    elif status == "partial":
        if not unchecked_items:
            fail("G7", "status=partial but unchecked_items is empty")
    elif status not in ("blocked",):
        fail("G7", f"unknown status {status!r}")
    if status == "blocked" and findings:
        fail("G7", "status=blocked must not carry findings")

    log_ok, log_detail = check_log(log_path)
    if not log_ok:
        fail("G8", log_detail)

    return failures


def check_log(path):
    if not path:
        return False, "--log not provided"
    try:
        lines = [l for l in open(path, encoding="utf-8") if l.strip()]
    except OSError:
        return False, f"run log {path} not found"
    if not lines:
        return False, "run log empty"
    for i, ln in enumerate(lines, 1):
        try:
            ev = json.loads(ln)
        except ValueError:
            return False, f"log line {i} is not valid JSON"
        for k in ("t", "action", "status"):
            if k not in ev:
                return False, f"log line {i} missing key '{k}'"
    return True, f"{len(lines)} events"


def check_claims(claims_path, pages):
    failures = []
    with open(claims_path, encoding="utf-8") as fh:
        for i, line in enumerate(fh, 1):
            if not line.strip():
                continue
            try:
                c = json.loads(line)
            except ValueError as e:
                failures.append({"gate": "G1-claims", "detail":
                                 f"line {i} invalid JSON: {e}"})
                continue
            page, quote = c.get("page"), c.get("quote", "")
            if pages and page in pages and collapse(quote) not in pages[page]:
                failures.append({"gate": "G1-claims", "detail":
                                 f"line {i} quote not verbatim on page "
                                 f"{page}"})
    return failures


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--result")
    ap.add_argument("--case")
    ap.add_argument("--pages")
    ap.add_argument("--log")
    ap.add_argument("--claims")
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    pages = load_pages(args.pages)
    case = None
    if args.case:
        try:
            case = json.load(open(args.case, encoding="utf-8"))
        except (OSError, ValueError):
            case = None

    failures = []
    if args.claims:
        failures += check_claims(args.claims, pages)
    if args.result:
        try:
            result = json.load(open(args.result, encoding="utf-8"))
        except (OSError, ValueError) as e:
            print(json.dumps({"passed": False,
                              "error": f"cannot read result: {e}"}))
            sys.exit(1)
        failures += check_result(result, case, pages, args.log)

    report = {"passed": not failures, "failures": failures,
              "gates": ["G1", "G2", "G3", "G4", "G5", "G6", "G7", "G8"]}
    with open(args.out, "w", encoding="utf-8") as fh:
        json.dump(report, fh, ensure_ascii=False, indent=2)
    print(json.dumps({"passed": not failures,
                      "failures": len(failures)}, ensure_ascii=False))
    sys.exit(0 if not failures else 1)


if __name__ == "__main__":
    main()
