#!/usr/bin/env python3
"""roundlog.py — append-only 检索轮次日志 + 饱和检测 + 停止判据裁决。

子命令:
  append --work /app/work --sq SQ-1 --query "..." [--source f.json]
         --returned N --new-relevant M [--evidence "rid1,rid2"] [--status ok|failed]
         [--note "..."]
  status --work /app/work            # 输出每 SQ 轮次、饱和状态与全局停止决定
  verify --work /app/work            # 日志完整性(序列号连续,无改笔)

停止判据(与 resources/stop_rules.md 一致):
  evidence_sufficient: 每个 SQ 均 saturated 或达到 acceptance_k
  marginal_gain_low:   连续 2 轮"全局"新增相关=0,且仍有 SQ 未达标
  handoff_to_human:    最近 2 笔日志 status=failed(接口异常)
  continue:            以上皆不满足
"""
import argparse, json, os, time

K_DEFAULT = 3

def load_rounds(work):
    p = os.path.join(work, "rounds.jsonl")
    if not os.path.exists(p):
        return []
    return [json.loads(l) for l in open(p, encoding="utf-8") if l.strip()]

def acceptance_k(decomp, sq):
    if not decomp:
        return K_DEFAULT
    for s in decomp.get("sqs", []):
        if s.get("id") == sq:
            import re
            m = re.search(r"≥\s*(\d+)", str(s.get("acceptance", "")))
            return int(m.group(1)) if m else K_DEFAULT
    return K_DEFAULT

def decide(work):
    rounds = load_rounds(work)
    decomp = None
    dp = os.path.join(work, "decomposition.json")
    if os.path.exists(dp):
        decomp = json.load(open(dp, encoding="utf-8"))
    sqs = [s["id"] for s in decomp.get("sqs", [])] if decomp else sorted({r.get("sq") for r in rounds if r.get("sq")})
    per = {sq: [] for sq in sqs}
    for i, r in enumerate(rounds):
        rr = dict(r); rr["_seq"] = i + 1
        if r.get("sq") in per:
            per[r["sq"]].append(rr)
    state = {}
    for sq in sqs:
        rs = per[sq]
        k = acceptance_k(decomp, sq)
        rel_so_far = sum(r.get("new_relevant", 0) for r in rs)
        tail = [r.get("new_relevant", 0) for r in rs[-2:]]
        saturated = len(rs) >= 2 and all(x == 0 for x in tail) and len(tail) == 2
        satisfied = rel_so_far >= k
        state[sq] = {"rounds": len(rs), "relevant_so_far": rel_so_far,
                     "acceptance_k": k, "saturated": saturated, "satisfied": satisfied}
    fails = [r for r in rounds[-2:] if r.get("status") == "failed"]
    global_tail = [r.get("new_relevant", 0) for r in rounds[-2:]] if len(rounds) >= 2 else None
    unsatisfied = [sq for sq, st in state.items() if not (st["satisfied"] or st["saturated"])]
    if len(fails) >= 2:
        stop, reason = "handoff_to_human", "最近 2 笔日志为接口失败,继续检索的边际价值不可评估"
    elif state and not unsatisfied:
        stop = "evidence_sufficient"
        reason = "全部 SQ 达到 acceptance 或已饱和(连续2轮新增相关=0)"
    elif global_tail and all(x == 0 for x in global_tail) and unsatisfied:
        stop = "marginal_gain_low"
        reason = "连续 2 轮全局新增相关=0,仍未达标的 SQ: %s -> 转入缺口分析" % ",".join(unsatisfied)
    else:
        stop, reason = "continue", "存在未达标且未饱和的 SQ,按计划继续检索"
    return {"rounds_total": len(rounds), "per_sq": state, "stop": stop != "continue",
            "stop_decision": stop, "reason": reason}

def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    p1 = sub.add_parser("append")
    p1.add_argument("--work", required=True)
    p1.add_argument("--sq", required=True)
    p1.add_argument("--query", required=True)
    p1.add_argument("--source", default="")
    p1.add_argument("--returned", type=int, default=0)
    p1.add_argument("--new-relevant", type=int, default=0)
    p1.add_argument("--evidence", default="")
    p1.add_argument("--status", default="ok", choices=["ok", "failed"])
    p1.add_argument("--note", default="")
    p2 = sub.add_parser("status")
    p2.add_argument("--work", required=True)
    p3 = sub.add_parser("verify")
    p3.add_argument("--work", required=True)
    args = ap.parse_args()
    if args.cmd == "append":
        os.makedirs(args.work, exist_ok=True)
        rounds = load_rounds(args.work)
        entry = {"seq": len(rounds) + 1, "ts": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
                 "sq": args.sq, "query": args.query, "source": args.source,
                 "returned": args.returned, "new_relevant": args.new_relevant,
                 "evidence_rids": [x.strip() for x in args.evidence.split(",") if x.strip()],
                 "status": args.status, "note": args.note}
        with open(os.path.join(args.work, "rounds.jsonl"), "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
        d = decide(args.work)
        print(json.dumps({"ok": True, "seq": entry["seq"],
                          "stop_decision": d["stop_decision"], "reason": d["reason"]},
                         ensure_ascii=False))
    elif args.cmd == "status":
        print(json.dumps(decide(args.work), ensure_ascii=False, indent=2))
    else:
        rounds = load_rounds(args.work)
        bad = [r["seq"] for i, r in enumerate(rounds) if r["seq"] != i + 1]
        print(json.dumps({"ok": not bad, "entries": len(rounds),
                          "gaps": bad}, ensure_ascii=False))

if __name__ == "__main__":
    main()
