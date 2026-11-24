#!/usr/bin/env python3
"""gap_tribunal.py -- admissibility tribunal for research-gap claims.

Usage:
    python3 gap_tribunal.py --work DIR --gaps FILE.json [--report FILE.json]

Gap claim schema (see references/evidence_schema.md):
    {"gap_id": str, "statement": str,
     "gap_type": "repeated-unsolved-question" | "method-failure-on-object-or-scale"
               | "conflict-unresolved" | "missing-population-or-setting",
     "exclusion_evidence": {
        "scope_description": str,
        "query_ids": [str, ...],
        "near_misses": [{"record_id": str, "why_not": str}, ...]}}

Checks (violation codes):
    bare_gap_claim        exclusion_evidence missing or empty
                          ("没检索到即空白" is NOT admissible)
    missing_scope         exclusion_evidence present but scope_description empty
    no_near_misses        exclusion_evidence present but near_misses empty
    unknown_query         a query_id is absent from the retrieval report
                          (run retrieval_log.py first, or pass --report)
    irrelevant_near_miss  near-miss record_id not in canon, OR topical overlap
                          with the gap statement below the sanity floor
    empty_why_not         near-miss entry lacks a non-empty why_not reason
    unknown_gap_type      gap_type not in the four-type taxonomy

Topical-overlap rule (a sanity floor, not semantics):
    tokens = lowercase [a-z0-9]+ words of length >= 3, minus a small stopword
    list, plus single CJK characters. A near-miss passes iff
        Jaccard(statement_tokens, record_tokens) >= 0.08
        OR |shared tokens| >= 2
    where record_tokens are computed from title + abstract + keywords.
    No stemming: "method" and "methods" are different tokens.

Reads <work>/canon.jsonl (required for record checks) and the retrieval
report at --report (default <work>/retrieval_report.json). If the report is
missing, every query_id is treated as unknown_query.

Writes <work>/gap_verdicts.json:
    {gaps: [{gap_id, verdict: admissible|rejected, violations: [...],
             evidence_summary: {...}}]}
Exit 1 if any gap is rejected. Stdlib only, deterministic.
"""
import argparse
import json
import os
import re
import sys

TAXONOMY = {
    "repeated-unsolved-question",
    "method-failure-on-object-or-scale",
    "conflict-unresolved",
    "missing-population-or-setting",
}

STOPWORDS = set("""
the and for with that this from are was were has have had not but all can its
our their they them then than thus such into over under between using use used
based via also which when where what how these those been being more most other
some any each may might across within without about above after again against
because before below both could did does doing down during few further here his
itself just like only once out own same she should very while who will your you
whether therefore however thus
""".split())

WORD_RE = re.compile(r"[a-z0-9]+")
CJK_RE = re.compile(r"[\u4e00-\u9fff\u3400-\u4dbf]")
OVERLAP_JACCARD_FLOOR = 0.08
OVERLAP_SHARED_FLOOR = 2


def tokens(text):
    t = str(text or "").lower()
    s = {w for w in WORD_RE.findall(t) if len(w) >= 3 and w not in STOPWORDS}
    s.update(CJK_RE.findall(t))
    return s


def load_canon(work):
    path = os.path.join(work, "canon.jsonl")
    canon = {}
    if not os.path.isfile(path):
        return canon
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue
            rid = rec.get("id")
            if rid:
                canon[rid] = rec
    return canon


def load_report_qids(report_path):
    if not report_path or not os.path.isfile(report_path):
        return None
    try:
        with open(report_path, encoding="utf-8") as f:
            report = json.load(f)
    except json.JSONDecodeError:
        return None
    return {q.get("query_id") for q in report.get("queries", [])}


def evidence_is_empty(ev):
    if not isinstance(ev, dict):
        return True
    scope = str(ev.get("scope_description") or "").strip()
    qids = ev.get("query_ids") or []
    nms = ev.get("near_misses") or []
    return not scope and not qids and not nms


def check_gap(gap, canon, canon_tokens, report_qids):
    violations = []
    gid = gap.get("gap_id") or "(no gap_id)"

    gtype = gap.get("gap_type")
    if gtype not in TAXONOMY:
        violations.append({"code": "unknown_gap_type",
                           "detail": "gap_type %r not in taxonomy" % gtype})

    stmt_tokens = tokens(gap.get("statement", ""))
    ev = gap.get("exclusion_evidence")
    n_queries, n_near = 0, 0
    max_shared = 0

    if evidence_is_empty(ev):
        violations.append({
            "code": "bare_gap_claim",
            "detail": "missing/empty exclusion_evidence; "
                      "'not found in retrieval' alone is a retrieval-omission "
                      "suspect, not a research gap",
        })
    else:
        scope = str(ev.get("scope_description") or "").strip()
        if not scope:
            violations.append({"code": "missing_scope",
                               "detail": "scope_description is empty"})
        qids = ev.get("query_ids") or []
        n_queries = len(qids)
        for qid in qids:
            if report_qids is None or qid not in report_qids:
                violations.append({"code": "unknown_query", "query_id": qid,
                                   "detail": "query_id not in retrieval report"})
        nms = ev.get("near_misses") or []
        n_near = len(nms)
        if not nms:
            violations.append({"code": "no_near_misses",
                               "detail": "near_misses list is empty"})
        for i, nm in enumerate(nms):
            if not isinstance(nm, dict):
                violations.append({"code": "irrelevant_near_miss", "index": i,
                                   "detail": "near-miss entry is not an object"})
                continue
            rid = nm.get("record_id")
            why_not = str(nm.get("why_not") or "").strip()
            if not why_not:
                violations.append({"code": "empty_why_not", "record_id": rid,
                                   "detail": "near-miss lacks a why_not reason"})
            if rid not in canon:
                violations.append({"code": "irrelevant_near_miss",
                                   "record_id": rid,
                                   "detail": "record_id not in canon"})
                continue
            rtoks = canon_tokens[rid]
            shared = stmt_tokens & rtoks
            max_shared = max(max_shared, len(shared))
            union = stmt_tokens | rtoks
            jaccard = (len(shared) / len(union)) if union else 0.0
            if not (jaccard >= OVERLAP_JACCARD_FLOOR
                    or len(shared) >= OVERLAP_SHARED_FLOOR):
                violations.append({
                    "code": "irrelevant_near_miss", "record_id": rid,
                    "detail": "topical overlap below sanity floor",
                    "jaccard": round(jaccard, 4),
                    "shared_tokens": sorted(shared),
                })

    summary = {
        "n_queries": n_queries,
        "n_near_misses": n_near,
        "max_shared_tokens": max_shared,
        "scope": str((ev or {}).get("scope_description") or "")[:200]
        if isinstance(ev, dict) else "",
    }
    return gid, violations, summary


def main():
    ap = argparse.ArgumentParser(description="Gap-claim admissibility tribunal")
    ap.add_argument("--work", required=True)
    ap.add_argument("--gaps", required=True)
    ap.add_argument("--report", default=None,
                    help="retrieval_report.json path "
                         "(default: <work>/retrieval_report.json)")
    args = ap.parse_args()

    canon = load_canon(args.work)
    canon_tokens = {
        rid: tokens(" ".join([
            rec.get("title", ""), rec.get("abstract", ""),
            " ".join(rec.get("keywords") or [])]))
        for rid, rec in canon.items()
    }
    report_path = args.report or os.path.join(args.work, "retrieval_report.json")
    report_qids = load_report_qids(report_path)

    with open(args.gaps, encoding="utf-8") as f:
        data = json.load(f)
    gaps = data.get("gaps", data) if isinstance(data, dict) else data
    if not isinstance(gaps, list):
        gaps = []

    results = []
    n_rejected = 0
    for gap in gaps:
        if not isinstance(gap, dict):
            continue
        gid, violations, summary = check_gap(gap, canon, canon_tokens,
                                             report_qids)
        verdict = "rejected" if violations else "admissible"
        if violations:
            n_rejected += 1
        results.append({"gap_id": gid, "verdict": verdict,
                        "violations": violations, "evidence_summary": summary})

    out_path = os.path.join(args.work, "gap_verdicts.json")
    os.makedirs(args.work, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump({"gaps": results}, f, ensure_ascii=False, indent=2,
                  sort_keys=True)
        f.write("\n")

    print("gap_tribunal: %d gaps, %d admissible, %d rejected -> %s"
          % (len(results), len(results) - n_rejected, n_rejected, out_path))
    for r in results:
        for v in r["violations"]:
            print("  VIOLATION %s: %s (%s)" % (r["gap_id"], v["code"],
                                               v.get("detail", "")))
    return 1 if n_rejected else 0


if __name__ == "__main__":
    sys.exit(main())
