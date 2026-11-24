#!/usr/bin/env python3
"""budget_ledger.py — 预算编排与断点账本（bundle B 签名脚本 2）。

子命令：
  plan    读取 docs.jsonl 与预算（默认 64 次模型请求），分配请求、裁定每篇文献的
          阅读深度（full/sections/abstract/skip），写 work/run_plan.json 与
          work/state.json（checkpoint）。
  mark    标记某阶段完成（记录产物路径与实耗请求数），追加 change_log。
  status  打印剩余预算与各阶段完成情况（中断恢复入口）。

分配规则（详见 rules/degradation_ladder.md）：
  reserve(verify+repair) 6 次；screening 1 次；
  逐文档 digest 按深度分批（full 每批≤2 篇、sections 每批≤4 篇、abstract 每批≤8 篇，
  每批合并 1 次请求）；主题综合 3–8 次；草稿 2–4 次。
  深度由 tier 与研究问题关键词 token 重叠得分排序决定；超预算时按降级阶梯砍深度与阶段。
"""
import json
import math
import os
import re
import sys
import time

RESERVE_REQUESTS = 6          # verify + repair 保底
SCREENING_REQUESTS = 1        # 筛选标准 + 批量初筛
THEME_MIN, THEME_MAX = 3, 8
DRAFT_MIN, DRAFT_MAX = 2, 4
BATCH_SIZE = {"full": 2, "sections": 4, "abstract": 8}  # 每批≤8 篇
FULL_DEPTH_CAP = 8            # 文献多时的全文精读上限（降级阶梯第一档）
SECTIONS_DEPTH_CAP = 12

PHASES = ["screening", "digests", "themes", "evidence_ledger", "draft", "verify_repair"]
DEFAULT_ARTIFACTS = {
    "screening": "screening_log.json",
    "digests": "digests/",
    "themes": "themes.json",
    "evidence_ledger": "evidence_ledger.jsonl",
    "draft": "review_draft.md",
    "verify_repair": "out:consistency_report.json",
}

STOPWORDS = {"the", "and", "for", "with", "from", "that", "this", "are", "was",
             "were", "has", "have", "been", "its", "their", "between", "among"}


def load_json(path, default):
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    return default


def load_jsonl(path):
    rows = []
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    rows.append(json.loads(line))
    return rows


def rq_tokens(question):
    """研究问题关键词集合：拉丁词（去停用词）+ CJK 二字组。"""
    q = question.lower()
    latin = {w for w in re.findall(r"[a-z][a-z0-9-]{2,}", q) if w not in STOPWORDS}
    cjk = re.findall(r"[一-鿿]+", q)
    bigrams = set()
    for seg in cjk:
        bigrams.update(seg[i:i + 2] for i in range(len(seg) - 1))
    return latin | bigrams


def doc_text(work, doc_id, limit=20000):
    p = os.path.join(work, "pages", f"{doc_id}.jsonl")
    text = ""
    for row in load_jsonl(p):
        text += "\n" + row.get("text", "")
        if len(text) > limit:
            break
    return text[:limit]


def overlap_score(tokens, text):
    if not tokens or not text:
        return 0
    low = text.lower()
    return sum(1 for t in tokens if t in low)


def digest_cost(depths):
    cost = 0
    for depth, size in BATCH_SIZE.items():
        n = sum(1 for d in depths.values() if d == depth)
        cost += math.ceil(n / size) if n else 0
    return cost


def allocate(depths, budget):
    """在预算内分配各阶段请求；超预算按降级阶梯收缩。返回 (allocation, degradations)。"""
    alloc = {"reserve": RESERVE_REQUESTS, "screening": SCREENING_REQUESTS,
             "digests": 0, "themes": THEME_MIN, "evidence_ledger": 0,
             "draft": DRAFT_MIN + 1, "verify_repair": RESERVE_REQUESTS}
    degradations = []

    def total():
        alloc["digests"] = digest_cost(depths)
        alloc["evidence_ledger"] = max(2, alloc["themes"] - 1)
        return sum(alloc.values()) - alloc["verify_repair"]  # reserve 与 verify_repair 同笔

    def grand_total():
        return total()

    # 文献多时的初始深度档：超过上限即预降级
    ranked = sorted(depths, key=lambda d: -depth_rank.get(d, 0))
    full_like = [d for d in ranked if depths[d] == "full"]
    if len(full_like) > FULL_DEPTH_CAP:
        for d in full_like[FULL_DEPTH_CAP:]:
            depths[d] = "sections"
        degradations.append(f"文献数较多：全文精读限定前 {FULL_DEPTH_CAP} 篇（按关键词重叠排序），其余降章节精读")
    sec_like = [d for d in ranked if depths[d] == "sections"]
    if len(sec_like) > SECTIONS_DEPTH_CAP:
        for d in sec_like[SECTIONS_DEPTH_CAP:]:
            depths[d] = "abstract"
        degradations.append(f"章节精读限定前 {SECTIONS_DEPTH_CAP} 篇，其余仅摘要")

    # 降级阶梯：草稿润色 → 主题细分 → 深度 full→sections→abstract → 尾部 skip
    if grand_total() > budget:
        alloc["draft"] = DRAFT_MIN
        degradations.append("预算不足：砍草稿润色轮次（draft → 2 次）")
    if grand_total() > budget:
        alloc["themes"] = THEME_MIN
        degradations.append("预算不足：砍主题细分（themes → 3 次单轮综合）")
    if grand_total() > budget:
        order = sorted((d for d in depths if depths[d] == "full"),
                       key=lambda d: depth_rank.get(d, 0))
        while order and grand_total() > budget:
            depths[order.pop(0)] = "sections"  # 从得分最低的 full 开始降
        degradations.append("预算不足：低相关文献阅读深度 full → sections")
    if grand_total() > budget:
        order = sorted((d for d in depths if depths[d] == "sections"),
                       key=lambda d: depth_rank.get(d, 0))
        while order and grand_total() > budget:
            depths[order.pop(0)] = "abstract"
        degradations.append("预算不足：低相关文献阅读深度 sections → abstract")
    if grand_total() > budget:
        order = sorted((d for d in depths if depths[d] in ("full", "sections", "abstract")),
                       key=lambda d: depth_rank.get(d, 0))
        while order and grand_total() > budget:
            depths[order.pop(0)] = "skip"
        degradations.append("预算不足：尾部低相关文献跳过精读（仅入筛选记录）")
    alloc["digests"] = digest_cost(depths)
    alloc["evidence_ledger"] = max(2, alloc["themes"] - 1)
    alloc["total"] = sum(v for k, v in alloc.items() if k != "total" and k != "verify_repair")
    if alloc["total"] > budget:
        degradations.append(
            f"保底组合（reserve 6 + screening 1 + themes 3 + evidence 2 + draft 2 = "
            f"{alloc['total']}）仍超出预算 {budget}：按保底执行，交付 status=partial 并逐项说明")
    return alloc, degradations


depth_rank = {}  # allocate() 内部使用的排序缓存


def cmd_plan(args):
    work = args.work
    profile = load_json(os.path.join(work, "case_profile.json"), {})
    docs = load_jsonl(os.path.join(work, "docs.jsonl"))
    groups = load_json(os.path.join(work, "dup_groups.json"), [])
    dup_of = {}
    for g in groups:
        rep = g.get("representative") or (g.get("members") or [None])[0]
        for m in g.get("members", []):
            if m != rep:
                dup_of[m] = rep

    tokens = rq_tokens(profile.get("research_question", ""))
    global depth_rank
    depths, scores, notes = {}, {}, []
    for d in docs:
        did, tier = d["doc_id"], d.get("tier")
        if did in dup_of:
            depths[did] = "skip"
            notes.append(f"{did}：近重复（代表篇 {dup_of[did]}），不重复分配阅读预算")
            continue
        if tier in ("metadata_only", "failed"):
            depths[did] = "skip"
            notes.append(f"{did}：tier={tier}，无全文可读，仅入筛选记录")
            continue
        if tier == "abstract_only":
            depths[did] = "abstract"
        else:
            depths[did] = "full"
        scores[did] = overlap_score(tokens, doc_text(work, did))
    depth_rank = scores

    # 按重叠得分排序：在同档深度内重排——得分最高的 fulltext 保持 full
    alloc, degradations = allocate(depths, args.budget)

    reading_plan = []
    for d in docs:
        did = d["doc_id"]
        reading_plan.append({
            "doc_id": did, "tier": d.get("tier"), "depth": depths.get(did, "skip"),
            "overlap_score": scores.get(did),
            "duplicate_of": dup_of.get(did),
            "batch_hint": f"{depths.get(did, 'skip')} 档每批≤{BATCH_SIZE.get(depths.get(did), 0)} 篇合并 1 次请求"
            if depths.get(did) in BATCH_SIZE else "不分配 digest 请求",
        })

    plan = {
        "case_id": profile.get("case_id", "unknown_case"),
        "budget_total": args.budget,
        "reserve_verify_repair": RESERVE_REQUESTS,
        "allocation": alloc,
        "reading_plan": reading_plan,
        "degradations": degradations,
        "notes": notes,
        "phases": [{"phase": p, "planned_artifact": DEFAULT_ARTIFACTS[p]} for p in PHASES],
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
    }
    with open(os.path.join(work, "run_plan.json"), "w", encoding="utf-8") as f:
        json.dump(plan, f, ensure_ascii=False, indent=2)

    state = {
        "case_id": plan["case_id"],
        "budget_total": args.budget,
        "requests_used": 0,
        "phases": {p: {"status": "pending", "artifact": None, "requests": 0}
                   for p in PHASES},
        "updated_at": plan["created_at"],
    }
    if not os.path.exists(os.path.join(work, "state.json")):
        with open(os.path.join(work, "state.json"), "w", encoding="utf-8") as f:
            json.dump(state, f, ensure_ascii=False, indent=2)

    # change_log：规划条目覆盖所有阶段，保证可审计
    log_path = os.path.join(work, "change_log.json")
    log = load_json(log_path, [])
    log.append(f"plan: 预算 {args.budget}，分配 {alloc}，降级 {len(degradations)} 项")
    for p in PHASES:
        log.append(f"plan: 阶段 {p} 已规划（产物 {DEFAULT_ARTIFACTS[p]}，pending）")
    with open(log_path, "w", encoding="utf-8") as f:
        json.dump(log, f, ensure_ascii=False, indent=2)

    print(json.dumps({"budget": args.budget, "planned_total": alloc["total"],
                      "depths": {r["doc_id"]: r["depth"] for r in reading_plan},
                      "degradations": len(degradations)}, ensure_ascii=False))


def cmd_mark(args):
    work = args.work
    state_path = os.path.join(work, "state.json")
    state = load_json(state_path, None)
    if state is None:
        raise SystemExit("state.json 不存在：先运行 budget_ledger.py plan")
    if args.phase not in state["phases"]:
        raise SystemExit(f"未知阶段 {args.phase}；合法值：{list(state['phases'])}")
    artifact = args.artifact
    if artifact is None:
        default = DEFAULT_ARTIFACTS[args.phase]
        if default.startswith("out:"):
            if not args.out:
                raise SystemExit(f"阶段 {args.phase} 的默认产物在 out 目录，请显式给 --artifact")
            artifact = os.path.join(args.out, default[4:])
        else:
            artifact = os.path.join(work, default)
    ph = state["phases"][args.phase]
    ph["status"] = "completed"
    ph["artifact"] = artifact
    ph["requests"] = args.requests
    state["requests_used"] += args.requests
    state["updated_at"] = time.strftime("%Y-%m-%dT%H:%M:%S")
    with open(state_path, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)

    log_path = os.path.join(work, "change_log.json")
    log = load_json(log_path, [])
    log.append(f"{args.phase}: completed，产物 {artifact}，实耗 {args.requests} 次请求"
               f"（累计 {state['requests_used']}/{state['budget_total']}）")
    with open(log_path, "w", encoding="utf-8") as f:
        json.dump(log, f, ensure_ascii=False, indent=2)
    print(json.dumps({"marked": args.phase, "requests_used": state["requests_used"],
                      "remaining": state["budget_total"] - state["requests_used"]},
                     ensure_ascii=False))


def cmd_status(args):
    state = load_json(os.path.join(args.work, "state.json"), None)
    if state is None:
        raise SystemExit("state.json 不存在：先运行 budget_ledger.py plan")
    remaining = state["budget_total"] - state["requests_used"]
    done = [p for p, v in state["phases"].items() if v["status"] == "completed"]
    pending = [p for p, v in state["phases"].items() if v["status"] != "completed"]
    print(json.dumps({
        "case_id": state["case_id"],
        "budget_total": state["budget_total"],
        "requests_used": state["requests_used"],
        "remaining": remaining,
        "completed_phases": done,
        "pending_phases": pending,
        "updated_at": state["updated_at"],
    }, ensure_ascii=False, indent=2))


def main(argv):
    import argparse
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("plan")
    p.add_argument("--work", required=True)
    p.add_argument("--budget", type=int, default=64)
    p = sub.add_parser("mark")
    p.add_argument("--work", required=True)
    p.add_argument("--phase", required=True, choices=PHASES)
    p.add_argument("--artifact", default=None)
    p.add_argument("--requests", type=int, default=1)
    p.add_argument("--out", default=None)
    p = sub.add_parser("status")
    p.add_argument("--work", required=True)
    args = ap.parse_args(argv)
    {"plan": cmd_plan, "mark": cmd_mark, "status": cmd_status}[args.cmd](args)


if __name__ == "__main__":
    main(sys.argv[1:])
