#!/usr/bin/env python3
"""make_result.py -- contract-driven result.json builder/validator.

Assembles /app/output/result.json from /input/case.json: the original case_id
plus EVERY field named by output_contract. Nothing is invented -- fields are
filled from real artifact paths produced by the retrieval run and the warden
audit, input files are hashed into `sources`, and unfinished work stays
visible through status=partial plus non-empty `uncertainty`.

Field hints are tuned to this bundle's artifacts:
  candidates.md / candidates.json   (the ranked, provenance-bearing pool)
  run_log.jsonl                     (the PRISMA-style pipeline ledger)
  audit_report.md / audit_report.json (the warden's gate verdict)

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

# (field-name substrings, candidate artifact paths relative to the out dir);
# first existing file wins. Paths under run/ cover runs that were not staged.
FIELD_HINTS = [
    (("candidate", "literature", "papers", "ranked", "bibliograph"),
     ["candidates.md", "candidates.json",
      "run/candidates.md", "run/candidates.json"]),
    (("run", "log", "trace", "pipeline", "flow", "screening", "search"),
     ["run_log.jsonl", "run/run_log.jsonl"]),
    (("audit", "warden", "gate", "integrity", "verif"),
     ["audit_report.md", "audit_report.json"]),
    (("evidence", "provenance", "snapshot", "source"),
     ["audit_report.md", "candidates.json", "run/candidates.json"]),
    (("status", "report", "uncertainty", "state", "summary"),
     ["audit_report.md", "candidates.md"]),
]


def hash12(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()[:12]


def load_json(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def contract_fields(case):
    oc = case.get("output_contract") or case.get("outputContract") or {}
    if isinstance(oc, dict):
        return list(oc.keys())
    if isinstance(oc, list):
        return [x["name"] if isinstance(x, dict) and "name" in x else str(x)
                for x in oc]
    return []


def map_field(field, out_dir):
    low = field.lower()
    for keys, rels in FIELD_HINTS:
        if any(k in low for k in keys):
            for rel in rels:
                p = os.path.join(out_dir, rel)
                if os.path.isfile(p):
                    return p
    return None


def cmd_build(case_path, out_path, status, sets, uncertainties):
    case = load_json(case_path)
    out_dir = os.path.dirname(os.path.abspath(out_path)) or "."
    result = load_json(out_path) if os.path.isfile(out_path) else {}
    result["case_id"] = case.get("case_id") or case.get("id") or "UNKNOWN"
    result["status"] = status

    for field in contract_fields(case):
        if field in sets:
            result[field] = sets[field]
        elif not result.get(field):
            hit = map_field(field, out_dir)
            if hit:
                result[field] = hit
            else:
                result.setdefault(field, None)

    sources = []
    in_dir = os.path.dirname(os.path.abspath(case_path))
    for dirpath, _d, files in os.walk(in_dir):
        for fn in sorted(files):
            p = os.path.join(dirpath, fn)
            if os.path.isfile(p):
                sources.append({"path": p, "sha256_12": hash12(p),
                                "bytes": os.path.getsize(p)})
    result["sources"] = sources

    notes = list(result.get("uncertainty") or [])
    for u in uncertainties:
        if u not in notes:
            notes.append(u)
    result["uncertainty"] = notes
    result["generated_by"] = ("retrieval-run-warden make_result.py "
                              "(offline, stdlib)")
    os.makedirs(out_dir, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=1)
    return result


def cmd_validate(case_path, out_path):
    case = load_json(case_path)
    result = load_json(out_path)
    problems = []
    want_id = case.get("case_id") or case.get("id")
    if want_id and result.get("case_id") != want_id:
        problems.append("case_id mismatch: result has %r, case has %r"
                        % (result.get("case_id"), want_id))
    for field in contract_fields(case):
        v = result.get(field)
        if v in (None, "", [], {}):
            problems.append("contract field %r is empty" % field)
        elif isinstance(v, str) and v.startswith("/") \
                and not os.path.isfile(v):
            problems.append("contract field %r points to missing file %s"
                            % (field, v))
    if result.get("status") not in ("success", "partial", "failed"):
        problems.append("status must be success|partial|failed, got %r"
                        % result.get("status"))
    if result.get("status") == "success" and result.get("uncertainty"):
        problems.append("status=success but uncertainty is non-empty: %s"
                        % result["uncertainty"])
    if result.get("status") == "partial" and not result.get("uncertainty"):
        problems.append("status=partial but uncertainty is empty -- say what "
                        "is missing")
    for p in problems:
        print("VALIDATE ERROR:", p)
    if not problems:
        print("VALIDATE OK: %d contract fields, case_id=%s, status=%s"
              % (len(contract_fields(case)), result.get("case_id"),
                 result.get("status")))
    return 1 if problems else 0


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
        sys.exit(cmd_validate(args.case, args.out))
    sets = {}
    for s in args.sets:
        k, _, v = s.partition("=")
        sets[k.strip()] = v.strip()
    result = cmd_build(args.case, args.out, args.status or "partial",
                       sets, args.uncertainty)
    n_filled = sum(1 for f in contract_fields(load_json(args.case))
                   if result.get(f))
    print("WROTE %s status=%s contract_fields_filled=%d uncertainty=%d"
          % (args.out, result["status"], n_filled,
             len(result["uncertainty"])))


if __name__ == "__main__":
    main()
