#!/usr/bin/env python3
"""Contract-driven result.json builder/validator for snapshot-trust-gate.

Reads /input/case.json, takes the original case_id and EVERY field named by
output_contract, and assembles /app/output/result.json. Nothing is invented:
fields are filled from real artifact paths, sources are hashed input files, and
anything unfinished stays visible via status=partial plus uncertainty notes.

Usage:
  make_result.py --case /input/case.json --out /app/output/result.json --status partial
  make_result.py --case /input/case.json --out /app/output/result.json --status success
  make_result.py --case /input/case.json --out /app/output/result.json \
      --set candidate_literature=/app/output/candidates.md
  make_result.py --case /input/case.json --out /app/output/result.json --validate
"""
import argparse
import hashlib
import json
import os
import sys

# heuristic field -> artifact mapping (order matters: first existing file wins)
FIELD_HINTS = [
    (("candidate", "literature", "papers", "results", "ranked"),
     ["candidates.md", "candidates.json"]),
    (("evidence", "screening", "trace", "query", "log", "provenance"),
     ["search_report.md", "evidence/evidence_index.json"]),
    (("quarantine", "trust", "quality"),
     ["quarantine_report.md"]),
    (("corpus", "verified"),
     ["verified_corpus.json"]),
    (("status", "report", "uncertainty", "state"),
     ["search_report.md"]),
]


def sha12(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()[:12]


def contract_fields(case):
    oc = case.get("output_contract") or case.get("outputContract") or {}
    if isinstance(oc, dict):
        return list(oc.keys())
    if isinstance(oc, list):
        return [x["name"] if isinstance(x, dict) and "name" in x else str(x)
                for x in oc]
    return []


def pick_artifact(field, out_dir):
    low = field.lower()
    for keys, files in FIELD_HINTS:
        if any(k in low for k in keys):
            for rel in files:
                p = os.path.join(out_dir, rel)
                if os.path.isfile(p):
                    return p
    return None


def build(case_path, out_path, status, sets, uncertainties):
    case = json.load(open(case_path, encoding="utf-8"))
    out_dir = os.path.dirname(os.path.abspath(out_path)) or "."
    result = {}
    if os.path.isfile(out_path):
        result = json.load(open(out_path, encoding="utf-8"))
    result["case_id"] = case.get("case_id") or case.get("id") or "UNKNOWN"
    result["status"] = status

    for field in contract_fields(case):
        if field in sets:
            result[field] = sets[field]
        elif field not in result or not result[field]:
            art = pick_artifact(field, out_dir)
            if art:
                result[field] = art
            else:
                result.setdefault(field, None)

    srcs = []
    in_dir = os.path.dirname(os.path.abspath(case_path))
    for dirpath, _d, files in os.walk(in_dir):
        for fn in sorted(files):
            p = os.path.join(dirpath, fn)
            if os.path.isfile(p):
                srcs.append({"path": p, "sha256_12": sha12(p),
                             "bytes": os.path.getsize(p)})
    result["sources"] = srcs
    notes = list(result.get("uncertainty") or [])
    notes.extend(u for u in uncertainties if u not in notes)
    result["uncertainty"] = notes
    result["generated_by"] = "snapshot-trust-gate make_result.py (offline, stdlib)"
    os.makedirs(out_dir, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=1)
    return result


def validate(case_path, out_path):
    case = json.load(open(case_path, encoding="utf-8"))
    result = json.load(open(out_path, encoding="utf-8"))
    errors = []
    cid = case.get("case_id") or case.get("id")
    if cid and result.get("case_id") != cid:
        errors.append("case_id mismatch: %r != %r" % (result.get("case_id"), cid))
    for field in contract_fields(case):
        v = result.get(field)
        if v in (None, "", [], {}):
            errors.append("contract field %r is empty" % field)
        elif isinstance(v, str) and v.startswith("/") and not os.path.isfile(v):
            errors.append("contract field %r points to missing file %s" % (field, v))
    if result.get("status") == "success" and result.get("uncertainty"):
        errors.append("status=success but uncertainty is non-empty: %s"
                      % result["uncertainty"])
    if result.get("status") not in ("success", "partial", "failed"):
        errors.append("status must be success|partial|failed")
    for e in errors:
        print("VALIDATE ERROR:", e)
    if not errors:
        print("VALIDATE OK: %d contract fields, case_id=%s, status=%s"
              % (len(contract_fields(case)), result.get("case_id"),
                 result.get("status")))
    return 1 if errors else 0


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--case", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--status", default=None, choices=["success", "partial", "failed"])
    ap.add_argument("--set", dest="sets", action="append", default=[],
                    metavar="FIELD=PATH")
    ap.add_argument("--uncertainty", action="append", default=[])
    ap.add_argument("--validate", action="store_true")
    args = ap.parse_args()
    if args.validate:
        sys.exit(validate(args.case, args.out))
    sets = {}
    for s in args.sets:
        k, _, v = s.partition("=")
        sets[k.strip()] = v.strip()
    result = build(args.case, args.out, args.status or "partial", sets,
                   args.uncertainty)
    filled = sum(1 for f in contract_fields(json.load(open(args.case)))
                 if result.get(f))
    print("WROTE %s status=%s contract_fields_filled=%d uncertainty=%d"
          % (args.out, result["status"], filled, len(result["uncertainty"])))


if __name__ == "__main__":
    main()
