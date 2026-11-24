#!/usr/bin/env python3
"""matrix_check.py -- claim-citation-aligner stage 2.5: machine gate on the
claim x citation alignment matrix.

Checks every row of alignment_matrix.jsonl:
  C1 schema: required fields present, non-empty
  C2 verdict vocabulary: supported | partially_supported | not_supported |
                         undeterminable
  C3 scope_check vocabulary on all four dimensions
  C4 quote verbatim: quote is an exact substring of the page text holding
     the cited sentence (whitespace-collapsed comparison)
  C5 sentence_id exists in citation_scan output
  C6 completeness: every citing sentence has >= 1 row; every cited ref_id
     appears in >= 1 row
  C7 sub_claim is not a verbatim copy of the whole sentence (prevents
     whole-sentence padding masquerading as decomposition)

Writes matrix_report.json; exit 1 if any check fails.
"""
import argparse
import json
import re
import sys

VERDICTS = {"supported", "partially_supported", "not_supported",
            "undeterminable"}
SCOPE_DIMS = ("population", "condition", "causal_strength", "quantification")
SCOPE_VALS = {"match", "narrower_in_source", "unclear"}
REQUIRED = ("sentence_id", "sub_claim_id", "sub_claim", "quote", "ref_id",
            "verdict", "basis")


def collapse(s: str) -> str:
    return re.sub(r"\s+", " ", s or "").strip()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pages", required=True)
    ap.add_argument("--scan", required=True)
    ap.add_argument("--matrix", required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    pages = {}
    for line in open(args.pages, encoding="utf-8"):
        if line.strip():
            pg = json.loads(line)
            pages[pg["page"]] = collapse(pg["text"])
    scan = json.load(open(args.scan, encoding="utf-8"))
    sent_by_id = {c["sentence_id"]: c for c in scan["citing_sentences"]}
    cited_refs = set()
    for c in scan["citing_sentences"]:
        cited_refs.update(c["ref_ids"])

    rows, violations = [], []
    with open(args.matrix, encoding="utf-8") as fh:
        for ln, line in enumerate(fh, 1):
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except ValueError as e:
                violations.append({"row": ln, "check": "C1",
                                   "detail": f"invalid JSON: {e}"})

    seen_sent, seen_refs, seen_ids = set(), set(), set()
    for i, r in enumerate(rows, 1):
        tag = {"row": i, "sub_claim_id": r.get("sub_claim_id")}
        missing = [k for k in REQUIRED
                   if k not in r or r[k] in (None, "", [])]
        if missing:
            violations.append({**tag, "check": "C1",
                               "detail": f"missing/empty fields: {missing}"})
            continue
        if r["sub_claim_id"] in seen_ids:
            violations.append({**tag, "check": "C1",
                               "detail": "duplicate sub_claim_id"})
        seen_ids.add(r["sub_claim_id"])
        if r["verdict"] not in VERDICTS:
            violations.append({**tag, "check": "C2",
                               "detail": f"bad verdict '{r['verdict']}'"})
        sc = r.get("scope_check", {})
        for d in SCOPE_DIMS:
            if sc.get(d) not in SCOPE_VALS:
                violations.append({**tag, "check": "C3",
                                   "detail": f"scope_check.{d} invalid"})
        sid = r["sentence_id"]
        sent = sent_by_id.get(sid)
        if sent is None:
            violations.append({**tag, "check": "C5",
                               "detail": f"sentence_id '{sid}' not in scan"})
            continue
        seen_sent.add(sid)
        if isinstance(r["ref_id"], int):
            seen_refs.add(r["ref_id"])
        page_text = pages.get(sent["page"], "")
        if collapse(r["quote"]) not in page_text:
            violations.append({**tag, "check": "C4",
                               "detail": "quote not verbatim on page "
                                         f"{sent['page']}"})
        if collapse(r["sub_claim"]) == collapse(sent["sentence"]):
            violations.append({**tag, "check": "C7",
                               "detail": "sub_claim copies the whole sentence"})

    for sid in sent_by_id:
        if sid not in seen_sent:
            violations.append({"row": None, "check": "C6",
                               "detail": f"citing sentence {sid} has no "
                                         "matrix row"})
    for rid in sorted(cited_refs - seen_refs):
        violations.append({"row": None, "check": "C6",
                           "detail": f"ref_id {rid} cited but absent from "
                                     "matrix"})

    report = {"rows": len(rows), "violations": violations,
              "passed": not violations,
              "verdict_counts": {}}
    for r in rows:
        v = r.get("verdict")
        if v in VERDICTS:
            report["verdict_counts"][v] = \
                report["verdict_counts"].get(v, 0) + 1
    with open(args.out, "w", encoding="utf-8") as fh:
        json.dump(report, fh, ensure_ascii=False, indent=2)
    print(json.dumps({"rows": len(rows), "violations": len(violations),
                      "passed": not violations}, ensure_ascii=False))
    sys.exit(0 if not violations else 1)


if __name__ == "__main__":
    main()
