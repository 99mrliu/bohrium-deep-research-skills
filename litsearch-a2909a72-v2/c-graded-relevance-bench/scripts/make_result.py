#!/usr/bin/env python3
"""result.json assembler and checker for graded-relevance-bench.

The deliverable contract is driven entirely by /input/case.json: this tool
copies the original case_id and guarantees that EVERY field named by
output_contract is present, pointing at a real artifact produced by the
grading engine. Nothing is fabricated: unmapped fields stay null (and the
validator will fail loudly until you --set them), sources are the hashed
files that shipped with the case, and unfinished work stays visible through
status=partial plus uncertainty notes.

Usage:
  make_result.py --case /input/case.json --out /app/output/result.json \
      --status partial
  make_result.py --case /input/case.json --out /app/output/result.json \
      --status success --clear-uncertainty
  make_result.py --case /input/case.json --out /app/output/result.json \
      --set borderline_queue=/app/output/borderline_queue.json
  make_result.py --case /input/case.json --out /app/output/result.json \
      --uncertainty "borderline adjudication still open"
  make_result.py --case /input/case.json --out /app/output/result.json \
      --validate
"""
import argparse
import hashlib
import json
import os
import sys

# Field-name keyword -> artifact candidates, first existing file wins.
# Tuned to the artifacts grade_relevance.py writes into --out.
ARTIFACT_HINTS = [
    (("graded", "candidate", "ranked", "literature", "papers", "records"),
     ["graded_candidates.md", "graded_candidates.json"]),
    (("borderline", "queue", "adjudicat", "ledger"),
     ["borderline_queue.json", "adjudication_ledger.md"]),
    (("evidence", "manifest", "provenance", "trace", "hash"),
     ["evidence/evidence_index.json"]),
    (("ranking", "report", "digest", "quality", "status"),
     ["ranking_report.md"]),
]

VALID_STATUS = ("success", "partial", "failed")


def file_sha12(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()[:12]


def declared_fields(case):
    """Field names from output_contract, tolerant of dict or list shapes."""
    oc = case.get("output_contract") or case.get("outputContract") or {}
    if isinstance(oc, dict):
        return list(oc.keys())
    if isinstance(oc, list):
        names = []
        for item in oc:
            if isinstance(item, dict) and "name" in item:
                names.append(str(item["name"]))
            elif isinstance(item, str):
                names.append(item)
        return names
    return []


def guess_artifact(field_name, out_dir):
    low = field_name.lower()
    for keywords, rel_paths in ARTIFACT_HINTS:
        if any(k in low for k in keywords):
            for rel in rel_paths:
                cand = os.path.join(out_dir, rel)
                if os.path.isfile(cand):
                    return cand
    return None


def inventory_sources(case_path):
    """Every file that shipped next to case.json, hashed, as provenance."""
    root = os.path.dirname(os.path.abspath(case_path))
    entries = []
    for dirpath, _sub, files in os.walk(root):
        for fn in sorted(files):
            p = os.path.join(dirpath, fn)
            if os.path.isfile(p) and not os.path.islink(p):
                entries.append({"path": p, "sha256_12": file_sha12(p),
                                "bytes": os.path.getsize(p)})
    return entries


def assemble(case_path, out_path, status, explicit_sets, new_uncertainties,
             clear_uncertainty):
    with open(case_path, encoding="utf-8") as f:
        case = json.load(f)
    out_dir = os.path.dirname(os.path.abspath(out_path)) or "."
    result = {}
    if os.path.isfile(out_path):
        with open(out_path, encoding="utf-8") as f:
            result = json.load(f)

    result["case_id"] = case.get("case_id") or case.get("id") or "UNKNOWN"
    result["status"] = status

    for field in declared_fields(case):
        if field in explicit_sets:
            result[field] = explicit_sets[field]
        elif not result.get(field):
            artifact = guess_artifact(field, out_dir)
            result[field] = artifact if artifact else None

    result["sources"] = inventory_sources(case_path)

    notes = [] if clear_uncertainty else list(result.get("uncertainty") or [])
    for u in new_uncertainties:
        if u not in notes:
            notes.append(u)
    result["uncertainty"] = notes
    result["generated_by"] = ("graded-relevance-bench make_result.py "
                              "(offline, stdlib)")
    os.makedirs(out_dir, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=1)
    return result


def check(case_path, out_path):
    with open(case_path, encoding="utf-8") as f:
        case = json.load(f)
    if not os.path.isfile(out_path):
        print("CHECK FAIL: %s does not exist" % out_path)
        return 1
    with open(out_path, encoding="utf-8") as f:
        result = json.load(f)
    problems = []
    cid = case.get("case_id") or case.get("id")
    if cid and result.get("case_id") != cid:
        problems.append("case_id mismatch: result has %r, case has %r"
                        % (result.get("case_id"), cid))
    if result.get("status") not in VALID_STATUS:
        problems.append("status %r is not one of success|partial|failed"
                        % result.get("status"))
    for field in declared_fields(case):
        value = result.get(field)
        if value in (None, "", [], {}):
            problems.append("contract field %r is empty — fill it with "
                            "--set %s=/app/output/<artifact>" % (field, field))
        elif isinstance(value, str) and value.startswith("/") \
                and not os.path.isfile(value):
            problems.append("contract field %r points to a missing file: %s"
                            % (field, value))
    if result.get("status") == "success" and result.get("uncertainty"):
        problems.append("status=success but uncertainty is non-empty: %s — "
                        "resolve or downgrade to partial"
                        % result["uncertainty"])
    for p in problems:
        print("CHECK FAIL:", p)
    if not problems:
        print("CHECK PASS: %d contract fields filled, case_id=%s, status=%s"
              % (len(declared_fields(case)), result.get("case_id"),
                 result.get("status")))
    return 1 if problems else 0


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--case", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--status", choices=VALID_STATUS, default=None)
    ap.add_argument("--set", dest="explicit_sets", action="append",
                    default=[], metavar="FIELD=PATH",
                    help="pin a contract field to a concrete artifact path")
    ap.add_argument("--uncertainty", action="append", default=[],
                    help="append an honest limitation note (repeatable)")
    ap.add_argument("--clear-uncertainty", action="store_true",
                    help="drop accumulated uncertainty notes (use when the "
                         "issues they described are resolved)")
    ap.add_argument("--validate", action="store_true",
                    help="check an existing result.json against the contract")
    args = ap.parse_args()

    if args.validate:
        sys.exit(check(args.case, args.out))

    explicit_sets = {}
    for pair in args.explicit_sets:
        key, sep, value = pair.partition("=")
        if not sep:
            sys.stderr.write("ERROR: --set expects FIELD=PATH, got %r\n" % pair)
            sys.exit(2)
        explicit_sets[key.strip()] = value.strip()

    result = assemble(args.case, args.out, args.status or "partial",
                      explicit_sets, args.uncertainty,
                      args.clear_uncertainty)
    with open(args.case, encoding="utf-8") as f:
        fields = declared_fields(json.load(f))
    filled = sum(1 for field in fields if result.get(field))
    print("RESULT_JSON written: %s | status=%s | contract fields %d/%d "
          "filled | uncertainty notes=%d"
          % (args.out, result["status"], filled, len(fields),
             len(result["uncertainty"])))


if __name__ == "__main__":
    main()
