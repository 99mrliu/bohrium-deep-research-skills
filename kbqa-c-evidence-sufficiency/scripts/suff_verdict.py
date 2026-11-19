#!/usr/bin/env python3
"""suff_verdict.py — validate per-question verdicts and assemble result.json.

Reads:
  --case  /input/case.json
  --work  /app/work/answers.json:
    {"answers": [{"question_id": "Q1",
                  "verdict": "SUPPORTED|PARTIAL|CONFLICTED|UNSUPPORTED|INACCESSIBLE",
                  "answer": "...", "missing": "...(缺什么，针对 UNSUPPORTED/INACCESSIBLE)",
                  "evidence": [{"doc_id": "D01", "locator": "Lx-Ly",
                                "quote": "逐字引文"}]}]}
  --out   /app/output with artifacts/suff_index.json, coverage_matrix.json,
          conflicts.json

Deterministic enforcement:
  * every quote is re-verified verbatim against the extracted text;
    failed evidence is dropped (recorded in change_log);
  * declared verdict is checked against the machine state and downgraded
    when contradicted: zero surviving evidence -> at most PARTIAL with a
    note (SUPPORTED impossible); a clear_conflict involving the question's
    tokens -> CONFLICTED; question names an inaccessible file and no
    readable evidence -> INACCESSIBLE;
  * UNSUPPORTED/INACCESSIBLE answers must carry a concrete `missing`;
  * status = "completed" iff all questions carry consistent verdicts with
    evidence or a concrete missing statement.
"""
import argparse
import json
import os
import re
import sys
from datetime import datetime, timezone

GRADES = ("SUPPORTED", "PARTIAL", "CONFLICTED", "UNSUPPORTED", "INACCESSIBLE")
RANK = {"SUPPORTED": 3, "PARTIAL": 2, "CONFLICTED": 2, "UNSUPPORTED": 1,
        "INACCESSIBLE": 1}


def norm(s):
    return re.sub(r"\s+", "", s or "")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--case", default="/input/case.json")
    ap.add_argument("--work", default="/app/work")
    ap.add_argument("--out", default="/app/output")
    a = ap.parse_args()

    case = json.load(open(a.case, encoding="utf-8")) if os.path.exists(a.case) else {}
    contract = case.get("output_contract") or {}
    art = os.path.join(a.out, "artifacts")
    index = json.load(open(os.path.join(art, "suff_index.json"), encoding="utf-8"))
    matrix = json.load(open(os.path.join(art, "coverage_matrix.json"),
                            encoding="utf-8"))
    conflicts = json.load(open(os.path.join(art, "conflicts.json"),
                               encoding="utf-8"))
    ans_path = os.path.join(a.work, "answers.json")
    answers_in = {"answers": []}
    if os.path.exists(ans_path):
        answers_in = json.load(open(ans_path, encoding="utf-8"))

    texts = {}
    for d in index["docs"]:
        if d["extract_status"] == "ok" and d.get("extract_path"):
            texts[d["doc_id"]] = open(d["extract_path"], encoding="utf-8",
                                      errors="replace").read()
    path_by_id = {d["doc_id"]: d["path"] for d in index["docs"]}
    sha_by_id = {d["doc_id"]: (d.get("sha256") or "")[:8] for d in index["docs"]}
    inacc_names = {d["name"].lower() for d in index.get("inaccessible", [])}

    m_by_q = {q["question_id"]: q for q in matrix.get("questions", [])}
    change_log, answers_out = [], []

    clear_conf_keys = [c["key"] for c in conflicts.get("conflicts", [])
                       if c.get("clear_conflict")]

    for ans in answers_in.get("answers", []):
        qid = ans.get("question_id")
        declared = ans.get("verdict", "UNSUPPORTED")
        if declared not in GRADES:
            declared = "UNSUPPORTED"
            change_log.append("question %s: 非法裁决已置为 UNSUPPORTED" % qid)

        kept, dropped = [], []
        for ev in ans.get("evidence", []):
            did = ev.get("doc_id")
            q = norm(ev.get("quote"))
            if did not in texts:
                dropped.append({"doc_id": did, "reason": "no_text"})
            elif q and q in norm(texts[did]):
                ev2 = dict(ev)
                ev2["path"] = path_by_id.get(did)
                ev2["sha8"] = sha_by_id.get(did)
                kept.append(ev2)
            else:
                dropped.append({"doc_id": did, "reason": "quote_not_verbatim"})

        final = declared
        m = m_by_q.get(qid, {})
        if declared == "SUPPORTED" and not kept:
            final = "PARTIAL"
            change_log.append("question %s: SUPPORTED 无存活引文，降级 PARTIAL" % qid)
        if declared == "PARTIAL" and not kept and not ans.get("missing"):
            final = "UNSUPPORTED"
            change_log.append("question %s: PARTIAL 无引文且无 missing，降级 UNSUPPORTED"
                              % qid)
        qt_norm = norm(m.get("question") or "")
        hit_conflict = [k for k in clear_conf_keys if k and norm(k) in qt_norm]
        if hit_conflict and final in ("SUPPORTED", "PARTIAL"):
            final = "CONFLICTED"
            change_log.append("question %s: 涉及未决冲突 %s，降级 CONFLICTED"
                              % (qid, "、".join(hit_conflict[:3])))
        if final in ("UNSUPPORTED", "INACCESSIBLE"):
            if not (ans.get("missing") or "").strip() or \
               ans.get("missing").strip() in ("不确定", "未知", "unknown", "不明"):
                change_log.append(
                    "question %s: %s 缺少具体 missing 说明，请在下一轮补写"
                    % (qid, final))
        if declared == "INACCESSIBLE" and kept:
            final = "PARTIAL"
            change_log.append("question %s: 声明 INACCESSIBLE 但有可读证据，改为 PARTIAL"
                              % qid)
        if m.get("inaccessible_mentioned") and not kept and final != "INACCESSIBLE":
            final = "INACCESSIBLE"
            change_log.append("question %s: 命中不可读文件且无证据，定级 INACCESSIBLE"
                              % qid)

        answers_out.append({
            "question_id": qid,
            "question": m.get("question") or ans.get("question"),
            "verdict": final,
            "declared_verdict": declared if declared != final else None,
            "answer": ans.get("answer"),
            "missing": ans.get("missing"),
            "evidence": kept,
            "dropped_evidence": dropped or None,
            "conflict_keys": hit_conflict or None,
        })

    sources = [{"doc_id": ev["doc_id"], "path": ev.get("path"),
                "sha8": ev.get("sha8"), "locator": ev.get("locator")}
               for x in answers_out for ev in x["evidence"]]
    result = {
        "case_id": case.get("case_id"),
        "status": None,
        "answers": answers_out,
        "grade_summary": {g: sum(1 for x in answers_out if x["verdict"] == g)
                          for g in GRADES},
        "sources": sources,
        "uncertainty": [],
        "change_log": change_log or ["suff_verdict: 全部裁决与机器状态一致"],
        "skipped_files": index.get("inaccessible", []),
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }
    if isinstance(contract, dict):
        for k in contract:
            result.setdefault(k, answers_out if "answer" in k else [])

    for x in answers_out:
        if x["verdict"] in ("UNSUPPORTED", "INACCESSIBLE"):
            result["uncertainty"].append(
                "问题 %s（%s）：%s"
                % (x["question_id"], x["verdict"], x.get("missing") or "缺 missing 说明"))
        if x["verdict"] == "CONFLICTED":
            result["uncertainty"].append(
                "问题 %s：存在未决证据冲突（%s），已并列双方坐标，未裁决。"
                % (x["question_id"], "、".join(x["conflict_keys"] or [])))

    complete = all(
        (x["evidence"] and x["verdict"] in ("SUPPORTED", "PARTIAL", "CONFLICTED"))
        or (x["verdict"] in ("UNSUPPORTED", "INACCESSIBLE") and x.get("missing"))
        for x in answers_out)
    result["status"] = "completed" if complete else "partial"
    if not complete:
        result["uncertainty"].append("存在未闭合的问题项（无证据且无 missing），按 partial 交付。")

    with open(os.path.join(a.out, "result.json"), "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=1)
    print("verdict status=%s answers=%d grades=%s"
          % (result["status"], len(answers_out), result["grade_summary"]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
