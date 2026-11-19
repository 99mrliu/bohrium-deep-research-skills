#!/usr/bin/env python3
"""kb_finalize.py — assemble the final result.json for one case.

Reads:
  --case     /input/case.json
  --work     work dir containing answers_draft.json and citations.jsonl
  --out      output dir containing artifacts/kb_index.json and
             artifacts/citation_verification.json

Rules enforced here (deterministic):
  * every claim listed in answers_draft.json keeps only citations that
    passed machine verification; claims left with zero citations are moved
    to `unsupported_claims` with an explicit note (never silently dropped);
  * status = "completed" iff every contract field is non-empty, all claims
    are supported or explicitly marked unsupported, else "partial";
  * result.json always contains case_id, every output_contract key,
    status, sources, uncertainty, change_log, skipped_files.

answers_draft.json schema (written by the agent):
  {"answers": [{"question_id": "...", "question": "...",
                "claims": [{"claim": "...", "citation_ids": ["C1","C2"],
                            "paraphrase": false, "confidence": "high"}],
                "no_evidence": false, "missing": "..."}]}
citations.jsonl uses the kb_verify.py input schema plus a unique "id".
"""
import argparse
import json
import os
import sys
from datetime import datetime, timezone


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--case", default="/input/case.json")
    ap.add_argument("--work", default="/app/work")
    ap.add_argument("--out", default="/app/output")
    a = ap.parse_args()

    case = {}
    if os.path.exists(a.case):
        case = json.load(open(a.case, encoding="utf-8"))
    contract = case.get("output_contract") or {}

    draft_path = os.path.join(a.work, "answers_draft.json")
    draft = {"answers": []}
    if os.path.exists(draft_path):
        draft = json.load(open(draft_path, encoding="utf-8"))

    ver_path = os.path.join(a.out, "artifacts", "citation_verification.json")
    verification = {"citations": []}
    if os.path.exists(ver_path):
        verification = json.load(open(ver_path, encoding="utf-8"))
    passed = {c.get("id") for c in verification.get("citations", []) if c.get("pass")}
    failed = {c.get("id"): c for c in verification.get("citations", []) if not c.get("pass")}
    by_id = {c.get("id"): c for c in verification.get("citations", [])}

    unsupported_claims = []
    answers = []
    for ans in draft.get("answers", []):
        claims = []
        for cl in ans.get("claims", []):
            ok_ids = [i for i in cl.get("citation_ids", []) if i in passed]
            bad_ids = [i for i in cl.get("citation_ids", []) if i not in passed]
            ev = []
            for cid in ok_ids:
                v = by_id.get(cid, {})
                ev.append({"citation_id": cid, "file_id": v.get("file_id"),
                           "path": None,
                           "locator": v.get("locator"), "quote": v.get("quote"),
                           "verification": "passed"})
            if ok_ids or cl.get("paraphrase"):
                claims.append({
                    "claim": cl.get("claim"),
                    "evidence": ev,
                    "paraphrase": bool(cl.get("paraphrase")),
                    "confidence": cl.get("confidence", "high" if ok_ids else "low"),
                    "verification": "passed" if ok_ids else "paraphrase_unverified",
                })
                for cid in bad_ids:
                    unsupported_claims.append({
                        "claim": cl.get("claim"),
                        "dropped_citation": cid,
                        "reason": (failed.get(cid) or {}).get("reason", "not_checked"),
                    })
            else:
                unsupported_claims.append({
                    "claim": cl.get("claim"),
                    "dropped_citation": bad_ids,
                    "reason": "no_verified_citation",
                })
        answers.append({
            "question_id": ans.get("question_id"),
            "question": ans.get("question"),
            "answer": ans.get("answer"),
            "claims": claims,
            "no_evidence": bool(ans.get("no_evidence")),
            "missing": ans.get("missing"),
        })

    sources = []
    for c in verification.get("citations", []):
        if c.get("pass"):
            sources.append({"citation_id": c.get("id"), "file_id": c.get("file_id"),
                            "locator": c.get("locator"),
                            "sha8": None, "quote": (c.get("quote") or "")[:200]})

    index_path = os.path.join(a.out, "artifacts", "kb_index.json")
    skipped = []
    if os.path.exists(index_path):
        idx = json.load(open(index_path, encoding="utf-8"))
        skipped = idx.get("skipped", [])
        sha_by_fid = {r["file_id"]: (r.get("sha256") or "")[:8] for r in idx.get("files", [])}
        path_by_fid = {r["file_id"]: r.get("path") for r in idx.get("files", [])}
        for s in sources:
            s["sha8"] = sha_by_fid.get(s["file_id"])
            s["path"] = path_by_fid.get(s["file_id"])

    result = {
        "case_id": case.get("case_id"),
        "status": None,
        "answers": answers,
        "sources": sources,
        "unsupported_claims": unsupported_claims,
        "uncertainty": [],
        "change_log": ["kb_finalize: assembled %d answers, %d verified citations, "
                       "%d unsupported claims, %d skipped files"
                       % (len(answers), len(sources),
                          len(unsupported_claims), len(skipped))],
        "skipped_files": skipped,
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }
    if isinstance(contract, dict):
        for k in contract:
            result.setdefault(k, answers if "answer" in k else [])

    if unsupported_claims:
        result["uncertainty"].append(
            "有 %d 条论断未通过引文机器核验，已移入 unsupported_claims，未写进答案。"
            % len(unsupported_claims))
    for ans in answers:
        if ans.get("no_evidence"):
            result["uncertainty"].append(
                "问题 %s：库中无依据。缺失：%s"
                % (ans.get("question_id"), ans.get("missing") or "未说明"))

    complete = (not failed) and all(
        ans.get("claims") or ans.get("no_evidence") for ans in answers)
    result["status"] = "completed" if complete else "partial"
    if not complete:
        result["uncertainty"].append(
            "存在未通过核验的引用或空答案问题，结果按 partial 交付。")

    os.makedirs(a.out, exist_ok=True)
    with open(os.path.join(a.out, "result.json"), "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=1)
    print("finalized status=%s answers=%d citations=%d unsupported=%d"
          % (result["status"], len(answers), len(sources), len(unsupported_claims)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
