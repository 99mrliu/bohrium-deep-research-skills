#!/usr/bin/env python3
"""budget_ledger.py — 把 900 秒 / 64 次模型请求的硬预算变成显式调度对象。

子命令:
  init    --workdir DIR [--seconds 900] [--requests 64]
  tick    --workdir DIR [--request] [--seconds N] [--note TEXT]
  status  --workdir DIR [--json]

水位(watermark) = max(已用秒/总秒, 已用请求/总请求):
  normal  0–70%   正常推进
  tight   70–85%  收紧：只做必做项，砍掉可选打磨
  floor   >85%    保底：立即收尾写 result.json，停止一切非必要请求

设计约束:
  - 所有状态落盘 workdir/budget.json，Agent 每一步先查水位再行动。
  - 不使用任何绝对时间戳：耗时全部来自 tick 的 --seconds 参数，输出完全确定。
  - 写盘原子化(tmp+rename)，中断不会留下半个 JSON。
仅依赖 python3 标准库。
"""
import argparse
import json
import os
import sys
import tempfile

SCHEMA = "budget-ledger/v1"

ADVICE = {
    "normal": "正常(0-70%): 按 references/runbook.md 正常推进",
    "tight": "收紧(70-85%): 只做必做项, 砍掉可选打磨与重跑",
    "floor": "保底(>85%): 立即收尾, promote 已有成果并写 result.json, 停止非必要请求",
}


def atomic_write_json(path, obj):
    d = os.path.dirname(os.path.abspath(path))
    os.makedirs(d, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=d, prefix=".budget-", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(obj, fh, ensure_ascii=False, indent=2, sort_keys=True)
            fh.write("\n")
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def ledger_path(workdir):
    return os.path.join(workdir, "budget.json")


def load(workdir):
    p = ledger_path(workdir)
    if not os.path.exists(p):
        sys.stderr.write("ERROR: %s 不存在, 先运行 budget_ledger.py init\n" % p)
        raise SystemExit(2)
    with open(p, encoding="utf-8") as fh:
        return json.load(fh)


def frac_used(b):
    fs = b["used_seconds"] / b["total_seconds"] if b["total_seconds"] else 1.0
    fr = b["used_requests"] / b["total_requests"] if b["total_requests"] else 1.0
    return max(fs, fr)


def level_of(b):
    f = frac_used(b)
    if f > 0.85:
        return "floor"
    if f >= 0.70:
        return "tight"
    return "normal"


def print_status(b):
    f = frac_used(b)
    lv = level_of(b)
    ps = 100.0 * b["used_seconds"] / b["total_seconds"] if b["total_seconds"] else 100.0
    pr = 100.0 * b["used_requests"] / b["total_requests"] if b["total_requests"] else 100.0
    print("[budget] seconds=%d/%d (%.1f%%) requests=%d/%d (%.1f%%) watermark=%.1f%% level=%s"
          % (b["used_seconds"], b["total_seconds"], ps,
             b["used_requests"], b["total_requests"], pr,
             100.0 * f, lv))
    print("[budget] %s" % ADVICE[lv])
    return lv


def cmd_init(args):
    b = {
        "schema": SCHEMA,
        "total_seconds": args.seconds,
        "total_requests": args.requests,
        "used_seconds": 0,
        "used_requests": 0,
        "events": [],
    }
    atomic_write_json(ledger_path(args.workdir), b)
    print("[budget] init total=%ds/%d requests -> %s"
          % (args.seconds, args.requests, ledger_path(args.workdir)))
    print_status(b)


def cmd_tick(args):
    if not args.request and args.seconds is None:
        sys.stderr.write("ERROR: tick 需要 --request 或 --seconds N (或两者)\n")
        raise SystemExit(2)
    b = load(args.workdir)
    secs = args.seconds or 0
    if args.request:
        b["used_requests"] += 1
    b["used_seconds"] += secs
    b["events"].append({
        "kind": "request" if args.request else "elapsed",
        "seconds": secs,
        "note": args.note or "",
    })
    atomic_write_json(ledger_path(args.workdir), b)
    lv = print_status(b)
    if lv == "floor":
        print("[budget] ACTION: 进入保底水位, 下一动作必须是收尾(见 runbook T780-T900)")


def cmd_status(args):
    b = load(args.workdir)
    if args.json:
        out = dict(b)
        out["watermark"] = round(frac_used(b), 4)
        out["level"] = level_of(b)
        print(json.dumps(out, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print_status(b)
        print("[budget] events=%d" % len(b["events"]))


def main():
    ap = argparse.ArgumentParser(description="900s/64-request budget ledger (stdlib only)")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("init", help="初始化预算账本")
    p.add_argument("--workdir", required=True)
    p.add_argument("--seconds", type=int, default=900)
    p.add_argument("--requests", type=int, default=64)
    p.set_defaults(fn=cmd_init)

    p = sub.add_parser("tick", help="记录一次模型请求或一段耗时")
    p.add_argument("--workdir", required=True)
    p.add_argument("--request", action="store_true", help="计一次模型请求")
    p.add_argument("--seconds", type=int, default=None, help="本步耗时秒数")
    p.add_argument("--note", default="")
    p.set_defaults(fn=cmd_tick)

    p = sub.add_parser("status", help="查看当前水位")
    p.add_argument("--workdir", required=True)
    p.add_argument("--json", action="store_true")
    p.set_defaults(fn=cmd_status)

    args = ap.parse_args()
    args.fn(args)


if __name__ == "__main__":
    main()
