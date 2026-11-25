#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
budget_ledger.py — 预算台账

逐次记录模型请求消耗与剩余、阶段墙钟时间；预留 reserve（终检与 result.json
填充所需请求数）；逼近阈值时发出降级信号（ok / warn / critical）。

子命令：
  init    初始化台账（--force 才允许覆盖已有台账）
  charge  记一笔消耗：--stage S --requests R [--seconds F] [--note ...]
  status  输出台账状态与降级信号（默认 JSON）

退出码：0 成功；2 用法/状态错误；3 运行时失败。
仅使用 Python 标准库。本脚本只记账与发信号，不做任何判定内容。
"""
import argparse
import json
import os
import sys
from datetime import datetime, timezone

DEFAULT_WORK = os.environ.get("BRG_WORK", "/app/work")
LEDGER_NAME = "budget_ledger.json"

SIGNAL_ACTION = {
    "ok": "维持当前档位，按 run_plan.json 继续。",
    "warn": "建议降一级（见 references/degradation_ladder.md）：跳过低优先级阶段，保住 fill/final_check。",
    "critical": "立即降至 L3：停止一切非必要模型调用，仅用预留请求完成 fill 与 final_check，"
                "以最小诚实 partial 落盘。",
}


def now_iso():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def ledger_path(work):
    return os.path.join(work, LEDGER_NAME)


def load_json(path):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError):
        return None


def save_ledger(work, ledger):
    tmp = ledger_path(work) + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(ledger, f, ensure_ascii=False, indent=2)
        f.write("\n")
    os.replace(tmp, ledger_path(work))  # 原子替换，崩溃不留半个文件


def remaining_min_requests(work, done_stages):
    """从 run_plan.json 计算未完成的启用阶段所需的最小请求数（无计划则按 0）。"""
    plan = load_json(os.path.join(work, "run_plan.json"))
    if not plan:
        return 0
    return sum(p.get("est_requests", 0) for p in plan.get("phases", [])
               if p.get("name") not in done_stages)


def done_stage_set(work):
    cp = load_json(os.path.join(work, "checkpoint.json"))
    if not cp:
        return set()
    return set((cp.get("stages") or {}).keys())


def compute_status(work, ledger):
    events = ledger.get("events", [])
    spent = sum(e.get("requests", 0) for e in events)
    elapsed = sum(e.get("seconds", 0.0) for e in events)
    budget_req = ledger["budget_requests"]
    budget_sec = ledger["budget_seconds"]
    reserve = ledger["reserve_requests"]
    remaining = budget_req - spent
    need_min = remaining_min_requests(work, done_stage_set(work))

    req_signal = "ok"
    if remaining <= reserve:
        req_signal = "critical"
    elif remaining < reserve + need_min:
        req_signal = "warn"
    time_signal = "ok"
    if budget_sec > 0:
        if elapsed >= 0.9 * budget_sec:
            time_signal = "critical"
        elif elapsed >= 0.75 * budget_sec:
            time_signal = "warn"
    rank = {"ok": 0, "warn": 1, "critical": 2}
    signal = req_signal if rank[req_signal] >= rank[time_signal] else time_signal

    per_stage = {}
    for e in events:
        s = per_stage.setdefault(e.get("stage", "?"), {"requests": 0, "seconds": 0.0})
        s["requests"] += e.get("requests", 0)
        s["seconds"] += e.get("seconds", 0.0)

    return {
        "spent_requests": spent,
        "remaining_requests": remaining,
        "reserve_requests": reserve,
        "remaining_stage_min_requests": need_min,
        "elapsed_seconds": round(elapsed, 1),
        "budget_requests": budget_req,
        "budget_seconds": budget_sec,
        "per_stage": per_stage,
        "signal": signal,
        "signal_reasons": {
            "requests": req_signal,
            "wall_clock": time_signal,
        },
        "suggested_action": SIGNAL_ACTION[signal],
    }


def cmd_init(args):
    path = ledger_path(args.work)
    if os.path.exists(path) and not args.force:
        print("[ledger] 错误：台账已存在（%s）。如需重置请显式加 --force；"
              "断点续跑时切勿重置台账，已消耗的预算必须继续计数。" % path, file=sys.stderr)
        return 2
    if args.budget_requests <= args.reserve:
        print("[ledger] 错误：预算请求数必须大于预留数。", file=sys.stderr)
        return 2
    os.makedirs(args.work, exist_ok=True)
    ledger = {
        "version": 1,
        "created_at": now_iso(),
        "budget_requests": args.budget_requests,
        "budget_seconds": args.budget_seconds,
        "reserve_requests": args.reserve,
        "events": [],
    }
    save_ledger(args.work, ledger)
    print("[ledger] 已初始化 %s（requests=%d, seconds=%s, reserve=%d）"
          % (path, args.budget_requests, args.budget_seconds, args.reserve))
    return 0


def cmd_charge(args):
    ledger = load_json(ledger_path(args.work))
    if ledger is None:
        print("[ledger] 错误：台账不存在，请先 init。", file=sys.stderr)
        return 2
    if args.requests < 0 or args.seconds < 0:
        print("[ledger] 错误：requests/seconds 不得为负。", file=sys.stderr)
        return 2
    ledger.setdefault("events", []).append({
        "ts": now_iso(),
        "stage": args.stage,
        "requests": args.requests,
        "seconds": args.seconds,
        "note": args.note or "",
    })
    save_ledger(args.work, ledger)
    st = compute_status(args.work, ledger)
    print("[ledger] charge stage=%s requests=%d seconds=%.1f → 已用 %d/%d，剩余 %d（预留 %d），信号=%s"
          % (args.stage, args.requests, args.seconds,
             st["spent_requests"], st["budget_requests"],
             st["remaining_requests"], st["reserve_requests"], st["signal"]))
    if st["signal"] != "ok":
        print("[ledger] 降级信号 %s：%s" % (st["signal"], st["suggested_action"]))
    return 0


def cmd_status(args):
    ledger = load_json(ledger_path(args.work))
    if ledger is None:
        print("[ledger] 错误：台账不存在，请先 init。", file=sys.stderr)
        return 2
    st = compute_status(args.work, ledger)
    print(json.dumps(st, ensure_ascii=False, indent=2))
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(description="预算台账：记录模型请求与墙钟消耗，发出降级信号")
    ap.add_argument("--work", default=DEFAULT_WORK, help="中间产物目录（默认 %(default)s，可用 BRG_WORK 覆盖）")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("init", help="初始化台账")
    p.add_argument("--budget-requests", type=int, default=64)
    p.add_argument("--budget-seconds", type=float, default=900)
    p.add_argument("--reserve", type=int, default=2, help="预留请求数（fill 1 + final_check 1）")
    p.add_argument("--force", action="store_true", help="允许覆盖已存在的台账")
    p.set_defaults(func=cmd_init)

    p = sub.add_parser("charge", help="记一笔消耗")
    p.add_argument("--stage", required=True)
    p.add_argument("--requests", type=int, required=True)
    p.add_argument("--seconds", type=float, default=0.0)
    p.add_argument("--note", default="")
    p.set_defaults(func=cmd_charge)

    p = sub.add_parser("status", help="输出状态与降级信号")
    p.set_defaults(func=cmd_status)

    args = ap.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:
        print("[ledger] 致命错误: %r" % e, file=sys.stderr)
        sys.exit(3)
