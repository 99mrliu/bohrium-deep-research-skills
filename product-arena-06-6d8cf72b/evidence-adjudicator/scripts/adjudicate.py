#!/usr/bin/env python3
"""adjudicate.py -- verdict state machine validation + result assembly.

verdicts.json (agent-authored): per question
  {"q_id", "verdict": supported|contradicted|not_reported|ambiguous,
   "answer": <contract value or text>,
   "evidence_for":  [{"anchor": "c1-2", "quote": "verbatim"}],
   "evidence_against": [...],
   "searched": {"for": [terms...], "against": [terms...]},
   "reason": "..."}

Deterministic checks:
  V1. verdict in the state machine;
  V2. every quote is a verbatim substring of its chunk (whitespace-normalized);
  V3. supported/contradicted require >= 1 evidence_for (contradicted usually
      also evidence_against or a numeric comparison in reason);
  V4. not_reported requires searched.for non-empty (you must name what you
      looked for) and empty evidence_for;
  V5. ambiguous requires evidence on both sides or an explicit reason naming
      the conflict;
  V6. every question in the ledger has a verdict entry (coverage).

Then assembles result.json: contract fields come from ``contract_fields`` in
verdicts.json; status success only with zero violations and full coverage.
"""
import argparse
import json
import os
import re
import sys

VERDICTS = ("supported", "contradicted", "not_reported", "ambiguous")


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--case", required=True)
    ap.add_argument("--ledger", required=True)
    ap.add_argument("--chunks", required=True)
    ap.add_argument("--verdicts", required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    case = json.load(open(args.case, encoding="utf-8"))
    ledger = json.load(open(args.ledger, encoding="utf-8"))
    chunks_doc = json.load(open(args.chunks, encoding="utf-8"))
    doc = json.load(open(args.verdicts, encoding="utf-8"))
    verdicts = doc.get("verdicts", [])

    if chunks_doc.get("status") == "unreadable":
        result = {"case_id": case.get("case_id", "unknown"), "status": "failed",
                  "failure": chunks_doc.get("reason"),
                  "handover": chunks_doc.get("handover")}
        _write(args.out, result)
        print(json.dumps({"status": "failed"}))
        return 0

    chunk_idx = {c["anchor"]: c["text"] for c in chunks_doc.get("chunks", [])}
    violations = []
    by_qid = {v.get("q_id"): v for v in verdicts}

    for q in ledger.get("questions", []):
        qid = q["q_id"]
        if qid.startswith("s"):
            continue  # contract slots are covered by contract validation below
        v = by_qid.get(qid)
        if v is None:
            violations.append({"q_id": qid, "check": "V6", "detail": "no verdict entry"})
            continue
        verdict = v.get("verdict")
        if verdict not in VERDICTS:
            violations.append({"q_id": qid, "check": "V1",
                               "detail": "bad verdict %r" % verdict})
            continue
        ef = v.get("evidence_for", []) or []
        ea = v.get("evidence_against", []) or []
        for side, evs in (("for", ef), ("against", ea)):
            for i, e in enumerate(evs):
                anchor = e.get("anchor", "")
                quote = re.sub(r"\s+", " ", e.get("quote", "")).strip()
                if anchor not in chunk_idx:
                    violations.append({"q_id": qid, "check": "V2",
                                       "detail": "anchor %s not in chunks" % anchor})
                elif quote and quote not in re.sub(r"\s+", " ", chunk_idx[anchor]):
                    violations.append({"q_id": qid, "check": "V2",
                                       "detail": "%s evidence[%d] quote not verbatim"
                                                 % (side, i)})
        if verdict in ("supported", "contradicted") and not ef:
            violations.append({"q_id": qid, "check": "V3",
                               "detail": "verdict %s without evidence_for" % verdict})
        if verdict == "not_reported":
            if not (v.get("searched", {}).get("for")):
                violations.append({"q_id": qid, "check": "V4",
                                   "detail": "not_reported requires searched.for terms"})
            if ef:
                violations.append({"q_id": qid, "check": "V4",
                                   "detail": "not_reported must not cite evidence_for"})
        if verdict == "ambiguous" and not ea and not v.get("reason"):
            violations.append({"q_id": qid, "check": "V5",
                               "detail": "ambiguous needs opposing evidence or a reason"})

    result = {"case_id": case.get("case_id", "unknown")}
    result.update(doc.get("contract_fields", {}))
    problems = []
    contract = case.get("output_contract", {})
    for req in contract.get("required", []):
        if req not in result:
            problems.append("missing required field: " + req)
    result["status"] = "success" if not violations and not problems else "partial"
    result["adjudication"] = {
        "verdicts": {v["q_id"]: v["verdict"] for v in verdicts},
        "violations": violations, "contract_problems": problems,
        "coverage": "%d/%d" % (
            sum(1 for q in ledger.get("questions", [])
                if q["q_id"].startswith("q") and q["q_id"] in by_qid),
            sum(1 for q in ledger.get("questions", []) if q["q_id"].startswith("q")))}
    result["sources"] = doc.get("sources",
                                [{"doc_id": chunks_doc.get("doc_id"),
                                  "sha256": chunks_doc.get("sha256"),
                                  "backend": chunks_doc.get("backend")}])
    result["uncertainty"] = doc.get("uncertainty", [])
    result["limits"] = doc.get("limits", [])
    _write(args.out, result)
    print(json.dumps({"status": result["status"], "violations": len(violations),
                      "contract_problems": len(problems)}, ensure_ascii=False))
    return 0


def _write(out_dir, result):
    os.makedirs(out_dir, exist_ok=True)
    with open(os.path.join(out_dir, "result.json"), "w", encoding="utf-8") as fh:
        json.dump(result, fh, ensure_ascii=False, indent=2)


if __name__ == "__main__":
    main()
