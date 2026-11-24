#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""budget.py — 预算感知调度: 64 次模型请求 / 900 秒硬预算的规划、记账与降级建议。

子命令:
  plan    按阶段清单给出每阶段请求/秒数配额 (保留 >=10 次请求 / >=120 秒应急储备)。
  log     追加一次用量, 打印剩余量, 越过 70%/90% 时打印 WARN/OVERRUN。
  advise  依据剩余预算与未完成阶段, 给出降级阶梯建议 (先砍润色, 再砍讨论增强)。

台账 (ledger) 为单个 JSON 文件; 仅依赖标准库 (>=3.9)。
"""
import argparse
import json
import os
import sys
from datetime import datetime, timezone

TOTAL_REQUESTS = 64
TOTAL_SECONDS = 900
RESERVE_REQUESTS = 10
RESERVE_SECONDS = 120

# 可选阶段识别: 名字命中即视为该级可砍。保底骨架 (s0/s1 类) 永不建议砍。
TIER1_HINTS = ("polish", "润色", "s4")
TIER2_HINTS = ("enhance", "discuss", "讨论", "增强", "s2", "s3")


def now_iso():
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def stage_tier(name):
    n = name.lower()
    if any(h in n for h in TIER1_HINTS):
        return 1  # 最先砍: 润色
    if any(h in n for h in TIER2_HINTS):
        return 2  # 其次砍: 增强/讨论
    return 0      # 保底: 永不砍


def load_ledger(path):
    if os.path.isfile(path):
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    return None


def save_ledger(path, ledger):
    d = os.path.dirname(os.path.abspath(path))
    os.makedirs(d, exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(ledger, f, ensure_ascii=False, indent=2)
        f.write("\n")
    os.replace(tmp, path)


def used_totals(ledger):
    req = sum(u.get("requests", 0) for u in ledger.get("usage", []))
    sec = sum(u.get("seconds", 0) for u in ledger.get("usage", []))
    return req, sec


def cmd_plan(args):
    stages = [s.strip() for s in args.stages.split(",") if s.strip()]
    if not stages:
        print("ERROR: --stages 为空", file=sys.stderr)
        return 2
    usable_req = TOTAL_REQUESTS - RESERVE_REQUESTS
    usable_sec = TOTAL_SECONDS - RESERVE_SECONDS
    n = len(stages)
    base_req, rem_req = divmod(usable_req, n)
    base_sec, rem_sec = divmod(usable_sec, n)
    plan = {}
    print("BUDGET PLAN — 总预算 %d 请求 / %ds; 储备 %d 请求 / %ds; 可分配 %d 请求 / %ds"
          % (TOTAL_REQUESTS, TOTAL_SECONDS, RESERVE_REQUESTS, RESERVE_SECONDS,
             usable_req, usable_sec))
    for i, s in enumerate(stages):
        r = base_req + (1 if i < rem_req else 0)
        t = base_sec + (1 if i < rem_sec else 0)
        tier = stage_tier(s)
        plan[s] = {"requests": r, "seconds": t, "tier": tier}
        tag = {0: "保底", 1: "可选-润色", 2: "可选-增强"}[tier]
        print("  %-16s %2d 请求 / %3ds   [%s]" % (s, r, t, tag))
    print("  储备            %2d 请求 / %3ds   [永不主动使用]"
          % (RESERVE_REQUESTS, RESERVE_SECONDS))
    ledger = {"total_requests": TOTAL_REQUESTS, "total_seconds": TOTAL_SECONDS,
              "reserve_requests": RESERVE_REQUESTS, "reserve_seconds": RESERVE_SECONDS,
              "stages": stages, "plan": plan, "usage": []}
    if args.ledger:
        save_ledger(args.ledger, ledger)
        print("LEDGER: %s" % args.ledger)
    return 0


def cmd_log(args):
    ledger = load_ledger(args.ledger)
    if ledger is None:
        print("ERROR: 台账不存在, 请先 plan --ledger %s" % args.ledger, file=sys.stderr)
        return 2
    ledger.setdefault("usage", []).append({
        "stage": args.stage, "requests": args.requests,
        "seconds": args.seconds, "ts": now_iso()})
    save_ledger(args.ledger, ledger)
    req, sec = used_totals(ledger)
    rem_req = ledger["total_requests"] - req
    rem_sec = ledger["total_seconds"] - sec
    print("LOG: stage=%s +%d 请求 / +%ds" % (args.stage, args.requests, args.seconds))
    print("  已用 %d/%d 请求 (%.0f%%), %d/%ds (%.0f%%); 剩余 %d 请求 / %ds"
          % (req, ledger["total_requests"], 100.0 * req / ledger["total_requests"],
             sec, ledger["total_seconds"], 100.0 * sec / ledger["total_seconds"],
             rem_req, rem_sec))
    level = 0
    for ratio in (req / ledger["total_requests"], sec / ledger["total_seconds"]):
        if ratio >= 0.90:
            level = max(level, 2)
        elif ratio >= 0.70:
            level = max(level, 1)
    if level == 2:
        print("  OVERRUN: 已越过 90% 预算线, 立即冻结当前草稿并执行 final_check 定稿。")
        return 3
    if level == 1:
        print("  WARN: 已越过 70% 预算线, 运行 advise 获取降级建议。")
        return 0
    print("  OK: 预算健康。")
    return 0


def cmd_advise(args):
    ledger = load_ledger(args.ledger)
    if ledger is None:
        print("ERROR: 台账不存在: %s" % args.ledger, file=sys.stderr)
        return 2
    plan = ledger.get("plan", {})
    done = {u["stage"] for u in ledger.get("usage", [])}
    left = [s for s in ledger.get("stages", []) if s not in done]
    req, sec = used_totals(ledger)
    rem_req = ledger["total_requests"] - req - ledger["reserve_requests"]
    rem_sec = ledger["total_seconds"] - sec - ledger["reserve_seconds"]
    need_req = sum(plan.get(s, {}).get("requests", 0) for s in left)
    need_sec = sum(plan.get(s, {}).get("seconds", 0) for s in left)
    print("ADVISE — 剩余可调度 %d 请求 / %ds; 未完成阶段 %s 计划需 %d 请求 / %ds"
          % (rem_req, rem_sec, left or "[]", need_req, need_sec))
    if not left:
        print("  建议: 所有阶段均已记账, 执行 final_check 定稿。")
        return 0

    def fits(skip_tiers):
        r = sum(plan.get(s, {}).get("requests", 0) for s in left
                if plan.get(s, {}).get("tier", 0) not in skip_tiers)
        t = sum(plan.get(s, {}).get("seconds", 0) for s in left
                if plan.get(s, {}).get("tier", 0) not in skip_tiers)
        return r <= rem_req and t <= rem_sec

    tier1 = [s for s in left if plan.get(s, {}).get("tier") == 1]
    tier2 = [s for s in left if plan.get(s, {}).get("tier") == 2]
    if fits(set()):
        print("  L0 全量执行: 预算足够完成剩余全部阶段, 无需降级。")
    elif fits({1}):
        print("  L1 砍润色: 跳过 %s; 其余阶段照常。" % (tier1 or "[]"))
    elif fits({1, 2}):
        print("  L2 砍润色+增强: 跳过 %s 与 %s; 仅完成保底阶段。"
              % (tier1 or "[]", tier2 or "[]"))
    else:
        print("  L3 冻结定稿: 剩余预算不足完成保底阶段, 立即停止内容工作, "
              "以当前保底骨架执行 final_check, status 据实记 partial。")
    print("  原则: 保底骨架 (tier=保底) 永远在保留之列; 降级只砍可选阶段。")
    return 0


def main():
    p = argparse.ArgumentParser(
        description="预算感知调度: 64 请求 / 900 秒的 plan/log/advise。")
    sub = p.add_subparsers(dest="cmd", required=True)

    pp = sub.add_parser("plan", help="按阶段给出配额建议")
    pp.add_argument("--stages", required=True, help="逗号分隔阶段名, 如 s0_contract,s1_minimum,...")
    pp.add_argument("--ledger", help="台账 JSON 输出路径 (建议总是提供)")
    pp.set_defaults(func=cmd_plan)

    pl = sub.add_parser("log", help="追加用量并报告剩余 (70%% WARN / 90%% OVERRUN)")
    pl.add_argument("--ledger", required=True)
    pl.add_argument("--stage", required=True)
    pl.add_argument("--requests", type=int, required=True)
    pl.add_argument("--seconds", type=int, required=True)
    pl.set_defaults(func=cmd_log)

    pa = sub.add_parser("advise", help="按剩余预算给出降级阶梯建议")
    pa.add_argument("--ledger", required=True)
    pa.set_defaults(func=cmd_advise)

    args = p.parse_args()
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
