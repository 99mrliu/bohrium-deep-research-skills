#!/usr/bin/env python3
"""Assemble result.json from verified answers and lint it against the case
output_contract. Exit code is non-zero when the contract check fails, so the
result cannot be submitted unchecked.

Contract checks:
  - case_id present and equal to the case's case_id;
  - every output_contract field present;
  - status in {complete, partial};
  - no claim appears in answers that the gate rejected.

Usage: custody_contract.py CASE_JSON WORK_DIR OUT_JSON
"""
import json
import os
import shutil
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import custody_journal  # noqa: E402

VALID_STATUS = {"complete", "partial"}


def main():
    case_p, work, out_p = sys.argv[1], sys.argv[2], sys.argv[3]
    case = json.load(open(case_p, encoding="utf-8"))
    contract = case.get("output_contract") or case.get("outputContract") or {}
    fields = list(contract.keys()) if isinstance(contract, dict) else list(contract or [])

    def load(name, default):
        p = os.path.join(work, name)
        if os.path.exists(p):
            try:
                return json.load(open(p, encoding="utf-8"))
            except Exception:
                return default
        return default

    gate = load("verified_answers.json", {})
    verified = gate.get("verified", [])
    rejected = gate.get("rejected", [])
    answers = []
    for card in verified:
        if card.get("status") == "not_found":
            answers.append({"question_id": card.get("question_id"),
                            "question": card.get("question"),
                            "status": "not_found",
                            "searched_terms": card.get("searched_terms"),
                            "coverage_files": card.get("coverage_files")})
        else:
            answers.append({"question_id": card.get("question_id"),
                            "question": card.get("question"),
                            "status": "answered",
                            "claim": card.get("claim"),
                            "evidence": {"file": card.get("file"),
                                         "sha256": card.get("sha256"),
                                         "quote": card.get("quote"),
                                         "char_start": card.get("char_start"),
                                         "char_end": card.get("char_end")}})
    uncertainty = []
    for r in rejected:
        uncertainty.append("论断被核验门拦截：%s（%s）" % (
            str(r["card"].get("claim"))[:60], "; ".join(r["reasons"])))

    result = {
        "case_id": case.get("case_id") or case.get("id") or "unknown",
        "status": "complete" if gate else "partial",
        "summary": "证据卡 %d 张过门、%d 张被拦截；保管链见 journal.jsonl" % (
            len(verified), len(rejected)),
        "answers": answers,
        "rejected_claims": [{"claim": r["card"].get("claim"),
                             "reasons": r["reasons"]} for r in rejected],
        "sources": load("sources_manifest.json", {}).get("sources", []),
        "uncertainty": uncertainty,
        "custody": {"journal": "journal.jsonl", "gate": "verified_answers.json",
                    "replay": "REPLAY.md"},
    }
    alias = {"results": "answers", "evidence": "answers", "files": "sources",
             "notes": "uncertainty", "errors": "uncertainty"}
    for f in fields:
        if f not in result:
            result[f] = result.get(alias.get(f))
            if result[f] is None:
                uncertainty.append("output_contract 字段 %r 无对应产物，置 null" % f)

    os.makedirs(os.path.dirname(out_p), exist_ok=True)
    with open(out_p, "w", encoding="utf-8") as fp:
        json.dump(result, fp, ensure_ascii=False, indent=2)
    custody_journal.append(work, "assemble_result",
                           "result.json assembled", out_p)

    failures = []
    cid = case.get("case_id") or case.get("id")
    if cid and result["case_id"] != cid:
        failures.append("case_id mismatch: %r != %r" % (result["case_id"], cid))
    for f in fields:
        if f not in result:
            failures.append("missing contract field: %s" % f)
    if result["status"] not in VALID_STATUS:
        failures.append("invalid status: %r" % result["status"])
    rejected_claims = {str(r["card"].get("claim")) for r in rejected}
    for a in answers:
        if a.get("claim") in rejected_claims:
            failures.append("rejected claim leaked into answers: %r"
                            % a.get("claim"))
    report = {"contract_fields": fields, "failures": failures,
              "ok": not failures}
    with open(os.path.join(work, "contract_report.json"), "w",
              encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    for extra in ("journal.jsonl", "verified_answers.json",
                  "sources_manifest.json", "contract_report.json"):
        src = os.path.join(work, extra)
        if os.path.exists(src):
            shutil.copy(src, os.path.join(os.path.dirname(out_p), extra))
    print(json.dumps(report, ensure_ascii=False))
    sys.exit(0 if not failures else 1)


if __name__ == "__main__":
    main()
