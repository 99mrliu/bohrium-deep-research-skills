#!/usr/bin/env python3
"""coverage.py — SQ×来源覆盖矩阵与缺口分类(只从轮次日志导出,不凭印象)。

用法:
  python3 coverage.py --case /input/case.json --work /app/work

单元格取值: satisfied(达到 acceptance) / saturated(饱和无新增) / gap(检索过未达标) /
            not_searched(未检索,无法判断)。
缺口分类: searched_but_absent = 高置信研究空白; not_searched = 无法判断。
输出 /app/output/coverage_matrix.json 与 /app/output/gap_analysis.json。
"""
import argparse, json, os

def load_rounds(work):
    p = os.path.join(work, "rounds.jsonl")
    if not os.path.exists(p):
        return []
    return [json.loads(l) for l in open(p, encoding="utf-8") if l.strip()]

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--case", required=True)
    ap.add_argument("--work", required=True)
    ap.add_argument("--out", default=None)
    args = ap.parse_args()
    out = args.out or "/app/output"
    os.makedirs(out, exist_ok=True)
    decomp = json.load(open(os.path.join(args.work, "decomposition.json"), encoding="utf-8"))
    rounds = load_rounds(args.work)
    import subprocess, sys
    st = json.loads(subprocess.run(
        [sys.executable, os.path.join(os.path.dirname(os.path.abspath(__file__)), "roundlog.py"),
         "status", "--work", args.work], capture_output=True, text=True).stdout)
    matrix, gaps = [], []
    for s in decomp.get("sqs", []):
        sq = s["id"]
        rs = [r for r in rounds if r.get("sq") == sq]
        sources = sorted({r.get("source") or "(未注明)" for r in rs})
        per = st["per_sq"].get(sq, {})
        if per.get("satisfied"):
            cell = "satisfied"
        elif per.get("saturated"):
            cell = "saturated"
        elif rs:
            cell = "gap"
        else:
            cell = "not_searched"
        searched = bool(rs)
        matrix.append({"sq": sq, "facet": s.get("facet"), "question": s.get("question"),
                       "acceptance": s.get("acceptance"), "cell": cell,
                       "rounds": len(rs), "sources": sources,
                       "relevant_so_far": per.get("relevant_so_far", 0),
                       "acceptance_k": per.get("acceptance_k")})
        if cell != "satisfied":
            gaps.append({"sq": sq, "cell": cell,
                         "classification": "searched_but_absent(高置信研究空白)" if cell == "saturated" else
                                           ("gap(检索过未达标,低置信)" if searched else "not_searched(无法判断)"),
                         "evidence": "该 SQ 已检索 %d 轮且饱和仍无达标证据" % len(rs) if cell == "saturated" else
                                     ("已检索 %d 轮未达标,可追加 W3 补检" % len(rs) if searched else
                                      "从未检索,禁止据此断言空白")})
    result = {"matrix": matrix, "stop_decision": st["stop_decision"],
              "stop_reason": st["reason"], "gaps": gaps,
              "rule": "空白只从本矩阵导出; not_searched 不得写成研究空白"}
    json.dump(result, open(os.path.join(out, "coverage_matrix.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=2)
    json.dump(result, open(os.path.join(out, "gap_analysis.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=2)
    print(json.dumps({"ok": True, "satisfied": sum(1 for m in matrix if m["cell"] == "satisfied"),
                      "gaps": len(gaps), "stop_decision": st["stop_decision"]}, ensure_ascii=False))

if __name__ == "__main__":
    main()
