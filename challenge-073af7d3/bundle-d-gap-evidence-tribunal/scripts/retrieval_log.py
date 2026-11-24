#!/usr/bin/env python3
"""retrieval_log.py -- validate a retrieval/screening query log.

Usage:
    python3 retrieval_log.py --work DIR --log FILE.jsonl

Log format: one JSON object per line:
    {"query_id": str, "query_string": str, "source": str, "date": str,
     "hits": int, "kept": int,
     "excluded": [{"record_ref": str, "reason": str}, ...]}

Checks per line:
    * closure: hits == kept + len(excluded)            -> closure_violation (fatal)
    * every excluded entry has a non-empty "reason"    -> empty_exclusion_reason (fatal)
    * well-formed hits/kept/excluded fields            -> malformed_line (fatal)
    * excluded record_ref resolution against <work>/canon.jsonl ids:
        - ref in canon            -> resolved (silent)
        - ref not in canon        -> listed under external_refs (NOT fatal:
                                     external refs are allowed but flagged)
        - canon file missing      -> all refs flagged "canon_missing_cannot_resolve"

Writes <work>/retrieval_report.json:
    {queries: [...], total_hits: int,
     closure_violations: [...], other_violations: [...], external_refs: [...]}

Exit 1 on any fatal violation, else 0. Stdlib only, deterministic.
"""
import argparse
import json
import os
import sys


def load_canon_ids(work):
    path = os.path.join(work, "canon.jsonl")
    if not os.path.isfile(path):
        return None
    ids = set()
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                ids.add(json.loads(line).get("id"))
            except json.JSONDecodeError:
                pass
    ids.discard(None)
    return ids


def main():
    ap = argparse.ArgumentParser(description="Validate a retrieval/screening query log")
    ap.add_argument("--work", required=True)
    ap.add_argument("--log", required=True)
    args = ap.parse_args()

    canon_ids = load_canon_ids(args.work)
    queries, closure, other, external = [], [], [], []
    total_hits = 0

    with open(args.log, encoding="utf-8") as f:
        lines = f.readlines()

    for ln, raw in enumerate(lines, 1):
        s = raw.strip()
        if not s:
            continue
        try:
            rec = json.loads(s)
        except json.JSONDecodeError:
            other.append({"line": ln, "code": "malformed_line",
                          "detail": "invalid JSON"})
            continue
        if not isinstance(rec, dict):
            other.append({"line": ln, "code": "malformed_line",
                          "detail": "line is not a JSON object"})
            continue

        qid = rec.get("query_id") or "line-%d" % ln
        hits, kept = rec.get("hits"), rec.get("kept")
        excluded = rec.get("excluded")
        if excluded is None:
            excluded = []

        well_formed = True
        if not isinstance(hits, int) or hits < 0 or not isinstance(kept, int) or kept < 0:
            other.append({"line": ln, "query_id": qid, "code": "malformed_line",
                          "detail": "hits/kept must be non-negative integers"})
            well_formed = False
        if not isinstance(excluded, list):
            other.append({"line": ln, "query_id": qid, "code": "malformed_line",
                          "detail": "excluded must be a list"})
            well_formed = False
            excluded = []

        if well_formed:
            total_hits += hits
            if hits != kept + len(excluded):
                closure.append({
                    "line": ln, "query_id": qid, "code": "closure_violation",
                    "hits": hits, "kept": kept, "excluded_count": len(excluded),
                    "detail": "hits != kept + len(excluded)",
                })

        for i, e in enumerate(excluded):
            if not isinstance(e, dict):
                other.append({"line": ln, "query_id": qid,
                              "code": "empty_exclusion_reason", "index": i,
                              "detail": "excluded entry is not an object"})
                continue
            reason = str(e.get("reason") or "").strip()
            if not reason:
                other.append({"line": ln, "query_id": qid,
                              "code": "empty_exclusion_reason", "index": i,
                              "detail": "excluded entry lacks a non-empty reason"})
            ref = e.get("record_ref")
            if ref:
                ref = str(ref)
                if canon_ids is None:
                    external.append({"query_id": qid, "record_ref": ref,
                                     "note": "canon_missing_cannot_resolve"})
                elif ref not in canon_ids:
                    external.append({"query_id": qid, "record_ref": ref,
                                     "note": "not_in_canon_external"})

        queries.append({
            "query_id": qid,
            "query_string": rec.get("query_string", ""),
            "source": rec.get("source", ""),
            "date": rec.get("date", ""),
            "hits": hits if isinstance(hits, int) else None,
            "kept": kept if isinstance(kept, int) else None,
            "excluded_count": len(excluded),
        })

    report = {
        "queries": queries,
        "total_hits": total_hits,
        "closure_violations": closure,
        "other_violations": other,
        "external_refs": external,
    }
    out_path = os.path.join(args.work, "retrieval_report.json")
    os.makedirs(args.work, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2, sort_keys=True)
        f.write("\n")

    fatal = len(closure) + len(other)
    print("retrieval_log: %d queries, total_hits=%d, closure_violations=%d, "
          "other_violations=%d, external_refs=%d -> %s"
          % (len(queries), total_hits, len(closure), len(other), len(external),
             out_path))
    return 1 if fatal else 0


if __name__ == "__main__":
    sys.exit(main())
