#!/usr/bin/env python3
"""finalize.py — 汇总规划/执行产物,按 case.json 的 output_contract 生成 result.json。

用法: python3 finalize.py --case /input/case.json --work /app/work --out /app/output
"""
import argparse, json, os, time

def load(p, default=None):
    try:
        if p.endswith(".jsonl"):
            return [json.loads(l) for l in open(p, encoding="utf-8") if l.strip()]
        return json.load(open(p, encoding="utf-8"))
    except Exception:
        return default

def contract_fields(case):
    c = case.get("output_contract")
    if isinstance(c, list):
        return [str(x) for x in c]
    if isinstance(c, dict):
        if isinstance(c.get("fields"), list):
            return [str(x) for x in c["fields"]]
        return sorted(c.keys())
    return []

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--case", required=True)
    ap.add_argument("--work", required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()
    os.makedirs(args.out, exist_ok=True)
    case = load(args.case, {})
    decomp = load(os.path.join(args.work, "decomposition.json"))
    plan = load(os.path.join(args.work, "retrieval_plan.json"))
    rounds = load(os.path.join(args.work, "rounds.jsonl"), [])
    cov = load(os.path.join(args.out, "coverage_matrix.json")) or \
          load(os.path.join(args.work, "coverage_matrix.json"), {})
    uncertainty, missing = [], []
    if decomp is None:
        missing.append("decomposition.json(拆解未完成或未通过校验)")
    if plan is None:
        missing.append("retrieval_plan.json(计划未编译)")
    if not rounds:
        uncertainty.append("轮次日志为空:计划已编译但检索未执行或未记账")
    if not cov:
        uncertainty.append("coverage_matrix.json 未生成:缺口分析未完成")
    matrix = (cov or {}).get("matrix", [])
    for m in matrix:
        if m.get("cell") == "not_searched":
            uncertainty.append("%s 从未检索,无法判断其证据状况" % m["sq"])
        elif m.get("cell") == "gap":
            uncertainty.append("%s 检索 %d 轮未达标(低置信缺口)" % (m["sq"], m.get("rounds", 0)))
    status = "blocked" if (decomp is None and not case) else \
             ("partial" if (missing or uncertainty) else "complete")
    sqs_out = [{"id": s["id"], "facet": s.get("facet"), "question": s.get("question"),
                "acceptance": s.get("acceptance"), "depends_on": s.get("depends_on", []),
                "queries": s.get("queries", {})} for s in (decomp or {}).get("sqs", [])]
    evidence = [{"round": r["seq"], "sq": r.get("sq"), "query": r.get("query"),
                 "source": r.get("source"), "returned": r.get("returned"),
                 "new_relevant": r.get("new_relevant"), "evidence_rids": r.get("evidence_rids", []),
                 "status": r.get("status")} for r in rounds]
    satisfied = [m["sq"] for m in matrix if m.get("cell") == "satisfied"]
    layer_ct = len({tuple(s.get("depends_on", [])) for s in (decomp or {}).get("sqs", [])}) or 1
    base = {
        "case_id": case.get("case_id"),
        "summary": "研究问题拆解为 %d 个子问题,编译 %d 个检索动作(计划调用 %s 次);"
                   "实际执行 %d 轮,停止判据=%s(%s);达标 SQ %d/%d。"
                   % (len(sqs_out),
                      len((plan or {}).get("actions", [])),
                      (plan or {}).get("budget", {}).get("planned_calls", "?"),
                      len(rounds), (cov or {}).get("stop_decision", "未停止"),
                      (cov or {}).get("stop_reason", ""), len(satisfied), len(matrix)),
        "subquestions": sqs_out,
        "retrieval_plan": plan,
        "rounds": evidence,
        "coverage": matrix,
        "gap_analysis": (cov or {}).get("gaps", []),
        "stop_decision": (cov or {}).get("stop_decision"),
        "stop_reason": (cov or {}).get("stop_reason"),
        "evidence_log": {"rounds": "rounds.jsonl (append-only, roundlog.py verify 可校验)",
                         "plan": "retrieval_plan.json",
                         "coverage": "coverage_matrix.json"},
        "sources": [{"kind": "file", "path": p} for p in
                    ["decomposition.json", "retrieval_plan.json", "rounds.jsonl"]
                    if os.path.exists(os.path.join(args.work, p))],
        "status": status,
        "uncertainty": uncertainty,
        "missing_steps": missing,
        "method": "rqplan-b-question-planner: decompose→plan→roundlog→coverage→finalize",
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
    }
    result = dict(base)
    for f in contract_fields(case):
        if f not in result:
            result[f] = []
            uncertainty.append("output_contract 字段 %s 无对应产物,留空" % f)
    result["uncertainty"] = uncertainty
    json.dump(result, open(os.path.join(args.out, "result.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=2)
    print(json.dumps({"ok": True, "status": status,
                      "contract_fields": len(contract_fields(case))}, ensure_ascii=False))

if __name__ == "__main__":
    main()
