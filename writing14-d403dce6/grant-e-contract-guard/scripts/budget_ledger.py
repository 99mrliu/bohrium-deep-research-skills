#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""budget_ledger.py — 预算账本：跟踪 64 次模型请求 / 900 秒预算的消耗与降级建议。

子命令：
  init    建账本 ledger.json（--budget-requests、--budget-seconds）
  tick    记录一次消耗：--kind model_request（请求数+1 且耗时累加）或
          --kind stage（仅累加阶段耗时）；--elapsed 秒数由调用方传入（必填）
  status  输出已用/剩余/百分比与阈值告警，并把 degradation_advice 写回账本

阈值：任一维度 ≥70% → warn；≥90% → critical（进入保底交付模式）。

退出码：0 正常（低于 warn）；2 warn（≥70%）；3 critical（≥90%）；
        1 输入/环境错误。warn/critical 不是脚本故障，而是给调用方的预算信号，
        脚本可用 `... || true` 或显式判断退出码处理。

确定性：不读墙钟；所有耗时由 --elapsed 传入；相同命令序列产出字节一致。
"""
import argparse
import json
import sys
import os

WARN_PCT = 0.70
CRITICAL_PCT = 0.90

DEGRADATION_ADVICE = [
    "立即停止新增扩写与额外检索，不再发起非必要模型请求。",
    "对已写完的章节只做合同字段补全与四态标注检查，不重写。",
    "把未完成的章节以【待申请人确认：…】占位并逐条写入缺口清单（gaps/uncertainty）。",
    "立即就地更新 result.json：status=partial、reason 说明预算耗尽边界、列出已完成与缺口。",
    "调用 checkpoint.py save 保存当前快照，确保截断后可恢复到最近合法状态。",
    "最后运行 contract_probe.py --validate 确认 result.json 合同合法后再交付。",
]


def eprint(msg):
    sys.stderr.write(msg + "\n")


def load_ledger(path):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        eprint("错误：账本不存在：%s（先运行 init）" % path)
        sys.exit(1)
    except (json.JSONDecodeError, OSError) as exc:
        eprint("错误：无法读取账本 %s：%s" % (path, exc))
        sys.exit(1)


def save_ledger(path, ledger):
    try:
        os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(ledger, f, ensure_ascii=False, indent=2, sort_keys=True)
            f.write("\n")
    except OSError as exc:
        eprint("错误：无法写入账本 %s：%s" % (path, exc))
        sys.exit(1)


def level_of(ledger):
    req_pct = ledger["used_requests"] / ledger["budget_requests"] if ledger["budget_requests"] else 1.0
    sec_pct = ledger["used_seconds"] / ledger["budget_seconds"] if ledger["budget_seconds"] else 1.0
    pct = max(req_pct, sec_pct)
    if pct >= CRITICAL_PCT:
        return "critical", req_pct, sec_pct
    if pct >= WARN_PCT:
        return "warn", req_pct, sec_pct
    return "ok", req_pct, sec_pct


def report(ledger):
    level, req_pct, sec_pct = level_of(ledger)
    print("预算账本状态：level=%s" % level)
    print("  请求：已用 %d / %d（%.1f%%），剩余 %d" % (
        ledger["used_requests"], ledger["budget_requests"],
        req_pct * 100, ledger["budget_requests"] - ledger["used_requests"]))
    print("  耗时：已用 %d / %d 秒（%.1f%%），剩余 %d 秒" % (
        ledger["used_seconds"], ledger["budget_seconds"],
        sec_pct * 100, ledger["budget_seconds"] - ledger["used_seconds"]))
    if level in ("warn", "critical"):
        print("  降级建议（degradation_advice）：")
        for i, a in enumerate(DEGRADATION_ADVICE, 1):
            print("    %d. %s" % (i, a))
    return {"ok": 0, "warn": 2, "critical": 3}[level]


def cmd_init(args):
    if args.budget_requests <= 0 or args.budget_seconds <= 0:
        eprint("错误：预算必须为正整数。")
        sys.exit(1)
    ledger = {
        "budget_requests": args.budget_requests,
        "budget_seconds": args.budget_seconds,
        "used_requests": 0,
        "used_seconds": 0,
        "events": [],
        "degradation_advice": [],
    }
    save_ledger(args.ledger, ledger)
    print("账本已初始化：%s（%d 请求 / %d 秒）" % (args.ledger, args.budget_requests, args.budget_seconds))
    sys.exit(0)


def cmd_tick(args):
    if args.elapsed < 0:
        eprint("错误：--elapsed 不能为负。")
        sys.exit(1)
    ledger = load_ledger(args.ledger)
    if args.kind == "model_request":
        ledger["used_requests"] += 1
    ledger["used_seconds"] += args.elapsed
    ledger["events"].append({
        "seq": len(ledger["events"]) + 1,
        "kind": args.kind,
        "elapsed": args.elapsed,
        "note": args.note or "",
        "used_requests_after": ledger["used_requests"],
        "used_seconds_after": ledger["used_seconds"],
    })
    level, _, _ = level_of(ledger)
    ledger["degradation_advice"] = list(DEGRADATION_ADVICE) if level in ("warn", "critical") else []
    save_ledger(args.ledger, ledger)
    print("tick #%d：kind=%s elapsed=%ds note=%s" % (
        len(ledger["events"]), args.kind, args.elapsed, args.note or ""))
    sys.exit(report(ledger))


def cmd_status(args):
    ledger = load_ledger(args.ledger)
    level, _, _ = level_of(ledger)
    ledger["degradation_advice"] = list(DEGRADATION_ADVICE) if level in ("warn", "critical") else []
    save_ledger(args.ledger, ledger)
    sys.exit(report(ledger))


def main():
    ap = argparse.ArgumentParser(
        description="预算账本：init 建账 / tick 记账 / status 查询与降级建议。",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="退出码：0 正常；2 warn（≥70%）；3 critical（≥90%）；1 输入或环境错误。")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("init", help="初始化账本")
    p.add_argument("--ledger", default="/app/work/ledger.json", help="账本路径")
    p.add_argument("--budget-requests", type=int, default=64, help="模型请求预算（默认 64）")
    p.add_argument("--budget-seconds", type=int, default=900, help="耗时预算秒数（默认 900）")
    p.set_defaults(func=cmd_init)

    p = sub.add_parser("tick", help="记录一次消耗")
    p.add_argument("--ledger", default="/app/work/ledger.json", help="账本路径")
    p.add_argument("--kind", choices=["model_request", "stage"], required=True,
                   help="model_request：请求数+1 并累加耗时；stage：仅累加耗时")
    p.add_argument("--elapsed", type=int, required=True,
                   help="本次耗时秒数（由调用方传入，不读墙钟，保证确定性）")
    p.add_argument("--note", default="", help="备注（阶段名等）")
    p.set_defaults(func=cmd_tick)

    p = sub.add_parser("status", help="查询状态与降级建议")
    p.add_argument("--ledger", default="/app/work/ledger.json", help="账本路径")
    p.set_defaults(func=cmd_status)

    args = ap.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
