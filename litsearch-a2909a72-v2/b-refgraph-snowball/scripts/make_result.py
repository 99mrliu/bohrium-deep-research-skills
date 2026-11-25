#!/usr/bin/env python3
"""Contract-driven result.json assembler/validator for refgraph-snowball.

Takes /input/case.json, preserves the original case_id, fills EVERY field the
case's output_contract names with a real artifact path (or a --set override),
hashes the input tree into `sources`, and keeps unfinished work visible via
status=partial plus uncertainty notes. Nothing is invented: unmapped fields
stay null until the agent maps them explicitly.

Usage:
  make_result.py --case /input/case.json --out /app/output/result.json --status partial
  make_result.py --case /input/case.json --out /app/output/result.json --status success
  make_result.py --case /input/case.json --out /app/output/result.json \
      --set citation_graph=/app/output/graph.json
  make_result.py --case /input/case.json --out /app/output/result.json --validate
"""
import argparse
import hashlib
import json
import os
import sys

# Field-name -> artifact heuristics, tuned to refgraph-snowball outputs.
# Evaluated top to bottom; the first keyword hit wins, then the first file
# that actually exists under the output directory.
FIELD_HINTS = [
    (("unresolved", "dangling", "ledger"),
     ["unresolved_references.md"]),
    (("candidate", "literature", "papers", "ranked", "snowball", "records"),
     ["candidates.md", "candidates.json"]),
    (("graph", "network", "citation"),
     ["graph.json"]),
    (("evidence", "trace", "provenance", "manifest", "hash"),
     ["evidence/evidence_index.json", "search_report.md"]),
    (("status", "report", "uncertainty", "state", "digest", "summary"),
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


def guess_artifact(field, out_dir):
    low = field.lower()
    for keywords, rels in FIELD_HINTS:
        if any(k in low for k in keywords):
            for rel in rels:
                p = os.path.join(out_dir, rel)
                if os.path.isfile(p):
                    return p
    return None


def build(case_path, out_path, status, sets, uncertainties):
    with open(case_path, encoding="utf-8") as f:
        case = json.load(f)
    out_dir = os.path.dirname(os.path.abspath(out_path)) or "."
    result = {}
    if os.path.isfile(out_path):
        with open(out_path, encoding="utf-8") as f:
            result = json.load(f)
    result["case_id"] = case.get("case_id") or case.get("id") or "UNKNOWN"
    result["status"] = status

    for field in contract_fields(case):
        if field in sets:
            result[field] = sets[field]
        elif not result.get(field):
            art = guess_artifact(field, out_dir)
            if art:
                result[field] = art
            else:
                result.setdefault(field, None)

    sources = []
    in_dir = os.path.dirname(os.path.abspath(case_path))
    for dirpath, _d, files in os.walk(in_dir):
        for fn in sorted(files):
            p = os.path.join(dirpath, fn)
            if os.path.isfile(p) and not os.path.islink(p):
                sources.append({"path": p, "sha256_12": sha12(p),
                                "bytes": os.path.getsize(p)})
    result["sources"] = sources
    notes = list(result.get("uncertainty") or [])
    notes.extend(u for u in uncertainties if u not in notes)
    result["uncertainty"] = notes
    result["generated_by"] = "refgraph-snowball make_result.py (offline, stdlib)"
    os.makedirs(out_dir, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=1)
    return result


def validate(case_path, out_path):
    with open(case_path, encoding="utf-8") as f:
        case = json.load(f)
    with open(out_path, encoding="utf-8") as f:
        result = json.load(f)
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
    ap.add_argument("--status", default=None,
                    choices=["success", "partial", "failed"])
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
    with open(args.case, encoding="utf-8") as f:
        filled = sum(1 for f in contract_fields(json.load(f)) if result.get(f))
    print("WROTE %s status=%s contract_fields_filled=%d uncertainty=%d"
          % (args.out, result["status"], filled, len(result["uncertainty"])))


if __name__ == "__main__":
    main()
