#!/usr/bin/env python3
"""conflict_pairs.py -- validate two-sided conflict-evidence entries.

Usage:
    python3 conflict_pairs.py --work DIR --conflicts FILE.json

Conflict entry schema (see references/evidence_schema.md):
    {"conflict_id": str, "quantity_or_claim": str,
     "side_a": {"record_ids": [str, ...], "value_or_finding": str,
                "location": str},
     "side_b": { ... same ... },
     "status": str  (optional, e.g. "unresolved",
                     "unresolvable-without-harmonization")}

Checks (violation codes):
    missing_side       side_a or side_b absent / not an object
    no_record_ids      a side has no record_ids
    unknown_record     a record_id is not in <work>/canon.jsonl
    empty_value        value_or_finding empty
    not_a_conflict     normalized values of the two sides are IDENTICAL
                       (normalization: lowercase, collapse whitespace,
                       strip surrounding quotes/trailing .。;；)
    missing_location   location empty (page/table/section where the value
                       is stated; if the material carries none, write
                       "location unavailable in provided material")

Writes <work>/conflict_report.json:
    {conflicts: [{conflict_id, verdict: admissible|rejected,
                  violations: [...], sides_summary: {...}}]}
Exit 1 if any entry is rejected. Stdlib only, deterministic.
"""
import argparse
import json
import os
import sys


def load_canon_ids(work):
    path = os.path.join(work, "canon.jsonl")
    ids = set()
    if not os.path.isfile(path):
        return ids
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                rid = json.loads(line).get("id")
            except json.JSONDecodeError:
                continue
            if rid:
                ids.add(rid)
    return ids


def norm_value(v):
    s = " ".join(str(v or "").strip().lower().split())
    return s.strip("\"' .。;；")


def check_side(name, side, canon_ids):
    violations = []
    if not isinstance(side, dict):
        violations.append({"code": "missing_side", "side": name,
                           "detail": "side is absent or not an object"})
        return violations
    ids = side.get("record_ids") or []
    if not ids:
        violations.append({"code": "no_record_ids", "side": name,
                           "detail": "side has no record_ids"})
    for rid in ids:
        if rid not in canon_ids:
            violations.append({"code": "unknown_record", "side": name,
                               "record_id": rid,
                               "detail": "record_id not in canon"})
    if not str(side.get("value_or_finding") or "").strip():
        violations.append({"code": "empty_value", "side": name,
                           "detail": "value_or_finding is empty"})
    if not str(side.get("location") or "").strip():
        violations.append({"code": "missing_location", "side": name,
                           "detail": "location is empty"})
    return violations


def main():
    ap = argparse.ArgumentParser(description="Two-sided conflict-evidence validator")
    ap.add_argument("--work", required=True)
    ap.add_argument("--conflicts", required=True)
    args = ap.parse_args()

    canon_ids = load_canon_ids(args.work)

    with open(args.conflicts, encoding="utf-8") as f:
        data = json.load(f)
    entries = data.get("conflicts", data) if isinstance(data, dict) else data
    if not isinstance(entries, list):
        entries = []

    results = []
    n_rejected = 0
    for c in entries:
        if not isinstance(c, dict):
            continue
        cid = c.get("conflict_id") or "(no conflict_id)"
        violations = []
        side_a, side_b = c.get("side_a"), c.get("side_b")
        violations += check_side("side_a", side_a, canon_ids)
        violations += check_side("side_b", side_b, canon_ids)
        va = norm_value(side_a.get("value_or_finding")) if isinstance(side_a, dict) else ""
        vb = norm_value(side_b.get("value_or_finding")) if isinstance(side_b, dict) else ""
        if va and vb and va == vb:
            violations.append({
                "code": "not_a_conflict",
                "detail": "normalized values are identical on both sides",
                "value": va,
            })
        verdict = "rejected" if violations else "admissible"
        if violations:
            n_rejected += 1
        results.append({
            "conflict_id": cid,
            "verdict": verdict,
            "violations": violations,
            "sides_summary": {
                "quantity_or_claim": str(c.get("quantity_or_claim") or "")[:200],
                "side_a_ids": side_a.get("record_ids") if isinstance(side_a, dict) else [],
                "side_b_ids": side_b.get("record_ids") if isinstance(side_b, dict) else [],
                "status": str(c.get("status") or ""),
            },
        })

    out_path = os.path.join(args.work, "conflict_report.json")
    os.makedirs(args.work, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump({"conflicts": results}, f, ensure_ascii=False, indent=2,
                  sort_keys=True)
        f.write("\n")

    print("conflict_pairs: %d entries, %d admissible, %d rejected -> %s"
          % (len(results), len(results) - n_rejected, n_rejected, out_path))
    for r in results:
        for v in r["violations"]:
            print("  VIOLATION %s: %s (%s)" % (r["conflict_id"], v["code"],
                                               v.get("detail", "")))
    return 1 if n_rejected else 0


if __name__ == "__main__":
    sys.exit(main())
