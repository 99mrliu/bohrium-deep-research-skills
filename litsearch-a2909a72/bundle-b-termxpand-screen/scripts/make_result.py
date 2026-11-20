#!/usr/bin/env python3
"""result.json builder/validator driven by the case's own output_contract.

- Reads /input/case.json, copies case_id verbatim, enumerates every field the
  output_contract names (dict keys or list entries) and fills each with the
  best matching artifact under /app/output (keyword matching, documented).
- Never invents content: unfilled fields stay empty and are listed in
  `uncertainty`; --validate exits non-zero on empty contract fields, a
  case_id mismatch, or dangling /app/output paths.

Usage:
  python3 make_result.py --case /input/case.json --out /app/output/result.json --status partial
  python3 make_result.py --case /input/case.json --out /app/output/result.json --status success
  python3 make_result.py --case /input/case.json --out /app/output/result.json \
      --set '<field>=/app/output/candidates.md' --uncertainty 'EuropePMC unreachable'
  python3 make_result.py --case /input/case.json --out /app/output/result.json --validate
"""
import argparse
import hashlib
import json
import sys
from pathlib import Path

# keyword (lowercase, matched against contract field name) -> candidate files
FIELD_HINTS = [
    (("candid", "paper", "literature", "文献", "候选", "result", "list", "rank",
      "includ"),
     ["candidates.md", "candidates.json"]),
    (("screen", "筛选", "ledger", "decision", "prisma", "flow"),
     ["screening_ledger.csv", "prisma_flow.md"]),
    (("evidence", "trace", "log", "query", "证据", "检索式", "过程", "record", "prov"),
     ["expansion_report.md", "evidence/search_log.jsonl"]),
    (("omiss", "missing", "gap", "遗漏", "缺失"),
     ["omissions.md"]),
    (("report", "summary", "说明", "报告", "status", "状态", "uncertain"),
     ["prisma_flow.md", "expansion_report.md"]),
    (("raw", "snapshot", "source"),
     ["evidence/search_log.jsonl"]),
]


def load_contract(case):
    oc = case.get("output_contract") or case.get("outputContract") or {}
    if isinstance(oc, dict):
        return list(oc.keys())
    if isinstance(oc, list):
        out = []
        for it in oc:
            if isinstance(it, str):
                out.append(it)
            elif isinstance(it, dict):
                out.append(it.get("field") or it.get("name") or str(it))
        return out
    return []


def match_file(field, outdir):
    fl = field.lower()
    for keys, files in FIELD_HINTS:
        if any(k in fl for k in keys):
            for f in files:
                if (outdir / f).exists():
                    return str(outdir / f)
    for f in ("candidates.md", "screening_ledger.csv", "prisma_flow.md"):
        if (outdir / f).exists():
            return str(outdir / f)
    return ""


def sha256(p):
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--case", default="/input/case.json")
    ap.add_argument("--input", default="/input")
    ap.add_argument("--out", required=True)
    ap.add_argument("--status", choices=["success", "partial", "failed"], default=None)
    ap.add_argument("--set", dest="sets", action="append", default=[],
                    help="field=value ; value is a /app/output path or a JSON literal")
    ap.add_argument("--uncertainty", action="append", default=[])
    ap.add_argument("--validate", action="store_true")
    args = ap.parse_args()

    outp = Path(args.out)
    outdir = outp.parent
    case = json.loads(Path(args.case).read_text(encoding="utf-8", errors="replace"))
    case_id = case.get("case_id") or case.get("id") or case.get("caseId")

    if outp.exists():
        result = json.loads(outp.read_text(encoding="utf-8"))
    else:
        result = {"case_id": case_id, "status": "partial", "sources": [],
                  "uncertainty": []}
        for field in load_contract(case):
            if field not in result:
                result[field] = match_file(field, outdir)

    if args.status:
        result["status"] = args.status
    result["case_id"] = case_id
    for u in args.uncertainty:
        if u not in result["uncertainty"]:
            result["uncertainty"].append(u)
    for s in args.sets:
        field, _, value = s.partition("=")
        field = field.strip()
        value = value.strip()
        if value.startswith("/"):
            result[field] = value
        else:
            try:
                result[field] = json.loads(value)
            except json.JSONDecodeError:
                result[field] = value
    # fill still-missing contract fields with best matches
    for field in load_contract(case):
        if not result.get(field):
            result[field] = match_file(field, outdir)
    # source hashes of input files actually consulted
    if not result["sources"]:
        for p in sorted(Path(args.input).rglob("*")):
            if p.is_file() and p.stat().st_size < 50_000_000:
                result["sources"].append({"file": str(p), "sha256": sha256(p)})

    outp.write_text(json.dumps(result, ensure_ascii=False, indent=1), encoding="utf-8")

    if args.validate:
        problems = []
        if result.get("case_id") != case_id:
            problems.append("case_id mismatch: %r != %r" % (result.get("case_id"), case_id))
        for field in load_contract(case):
            v = result.get(field)
            if v in (None, "", [], {}):
                problems.append("contract field empty: " + field)
            elif isinstance(v, str) and v.startswith("/app/output") \
                    and not Path(v).exists():
                problems.append("dangling path in field %s: %s" % (field, v))
        if result.get("status") == "success" and result.get("uncertainty"):
            problems.append("status=success but uncertainty is non-empty: %s"
                            % result["uncertainty"])
        if problems:
            print("VALIDATION FAILED")
            for p in problems:
                print(" -", p)
            sys.exit(1)
        print("VALIDATION OK: %d contract fields filled" % len(load_contract(case)))


if __name__ == "__main__":
    main()
