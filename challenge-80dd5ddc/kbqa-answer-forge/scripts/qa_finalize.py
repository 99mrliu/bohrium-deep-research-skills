#!/usr/bin/env python3
"""qa_finalize.py — 问答生产线收尾：组装 result.json 并执行硬性闸门。

读取模型撰写的 work/answers.json（格式见 references/citation_contract.md），
结合 citation_verification.json 的核验报告：
  - pass=false 的引文所属论断强制降级：evidence 清空、claim 保留但
    verification="unsupported"，并在 uncertainty 留痕；
  - 无任何核验通过证据的论断不得标 "passed"；
  - 只有全部问题处理完毕且引文全过时 status 才允许 "completed"，
    否则 "partial" 并逐条说明原因；
  - 自动汇总 sources（被实际引用文件的 file_id/relpath/sha8）、
    retrieval_log 的阴性检索记录并入 uncertainty。
退出码恒 0。
"""
import argparse
import json
import os
import sys
import time


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--input", default="/input")
    ap.add_argument("--work", default="/app/work")
    ap.add_argument("--out", default="/app/output")
    a = ap.parse_args()

    def load(p, default):
        try:
            with open(p, encoding="utf-8") as f:
                return json.load(f)
        except (OSError, json.JSONDecodeError):
            return default

    case = load(os.path.join(a.input, "case.json"), {})
    questions = load(os.path.join(a.work, "questions.json"),
                     {"questions": [], "output_contract_fields": []})
    ver = load(os.path.join(a.out, "citation_verification.json"),
               {"results": [], "verdict": "no_citations"})
    index = load(os.path.join(a.work, "kb_index.json"), {"files": []})
    answers = load(os.path.join(a.work, "answers.json"), {"answers": []})

    pass_map = {}   # citation_id / claim_id -> bool
    for r in ver.get("results", []):
        for key in (r.get("citation_id"), r.get("claim_id")):
            if key:
                pass_map[key] = pass_map.get(key, True) and r["pass"]

    by_id = {e["file_id"]: e for e in index.get("files", [])}
    used_sources, uncertainty, change_log = {}, [], []
    out_answers, n_done = [], 0
    for ans in answers.get("answers", []):
        qid = ans.get("question_id", "?")
        claims, has_evidence = [], False
        for cl in ans.get("claims", []):
            cid = cl.get("claim_id", "?")
            ev = cl.get("evidence", [])
            ok = bool(ev) and all(pass_map.get(e.get("citation_id", cid), False)
                                  for e in ev)
            if ev and not ok:
                uncertainty.append("问题 %s 论断 %s 的引文未通过机器核验，已降级为 unsupported"
                                   % (qid, cid))
                ev = []
            if ok:
                has_evidence = True
                for e in cl.get("evidence", []):
                    fe = by_id.get(e.get("file_id"))
                    if fe:
                        used_sources[fe["file_id"]] = {
                            "file_id": fe["file_id"], "relpath": fe["relpath"],
                            "sha8": (fe["sha256"] or "")[:8]}
            claims.append({"claim_id": cid, "claim": cl.get("claim", ""),
                           "evidence": ev if ok else [],
                           "verification": "passed" if ok else
                           ("unsupported" if cl.get("evidence") else "no_evidence"),
                           "paraphrase": bool(cl.get("paraphrase"))})
        state = "no_basis" if (ans.get("answer") and "无依据" in str(ans.get("answer"))) else \
                ("answered" if (ans.get("answer") and (has_evidence or not claims)) else "pending")
        if state in ("answered", "no_basis"):
            n_done += 1
        out_answers.append({"question_id": qid, "answer": ans.get("answer"),
                            "claims": claims, "state": state})

    # 阴性检索记录并入 uncertainty（"搜过但没有"的可复核证据）
    neg = []
    try:
        with open(os.path.join(a.work, "retrieval_log.jsonl"), encoding="utf-8") as f:
            for line in f:
                e = json.loads(line)
                if e.get("negative"):
                    neg.append(e)
    except OSError:
        pass
    for e in neg:
        uncertainty.append("检索无命中（%s）：%r —— 支持'库中无依据'结论" %
                           (e["question_id"], e["query"][:80]))

    total_q = len(questions.get("questions", [])) or len(out_answers)
    completed = (total_q > 0 and n_done >= total_q
                 and ver.get("verdict") in ("all_passed", "no_citations"))
    status = "completed" if completed else "partial"
    if not completed:
        reasons = []
        if total_q and n_done < total_q:
            reasons.append("%d/%d 问题未完成" % (total_q - n_done, total_q))
        if ver.get("verdict") == "has_failures":
            reasons.append("存在未通过核验的引文（已降级，详见 citation_verification.json）")
        if not reasons:
            reasons.append("无问题可答或流程未走完")
        uncertainty.extend(reasons)
    change_log.append({"ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                       "event": "finalize: assembled result.json, status=" + status})

    result = {"case_id": case.get("case_id") or case.get("id") or "unknown",
              "status": status,
              "answers": out_answers,
              "sources": sorted(used_sources.values(), key=lambda s: s["file_id"]),
              "uncertainty": uncertainty,
              "change_log": change_log,
              "citation_verification_summary": {
                  "total": ver.get("total"), "passed": ver.get("passed"),
                  "failed": ver.get("failed"), "verdict": ver.get("verdict")}}
    for fld in questions.get("output_contract_fields", []):
        if fld not in result:
            result[fld] = None
            uncertainty.append("output_contract 字段 %r 无对应内容，置 null" % fld)
    with open(os.path.join(a.out, "result.json"), "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    print(json.dumps({"status": status, "answered": n_done, "total_questions": total_q,
                      "sources": len(used_sources),
                      "citation_verdict": ver.get("verdict")}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
