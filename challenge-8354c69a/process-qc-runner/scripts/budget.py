#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""budget.py — 预算台账：模型请求数、墙钟时间、降级决策。

平台预算（本题）：约 64 次模型请求 / 900 秒 / 每响应 16384 tokens。
模型请求数只有 Agent 自己知道——每次发起分析性请求后运行一次 tick。

  python3 budget.py init --work /app/work [--requests 64] [--seconds 900]
  python3 budget.py tick --work /app/work [--n 1]     # 记 n 次模型请求
  python3 budget.py report --work /app/work           # 用量 + 降级建议

降级阈值（写死在策略里，report 输出依据）：
  用量 <50%      : 正常推进
  50-80%         : 不再开新分析支线，优先填满契约字段
  >80%           : 立即收尾——当前结论按现状写入 result.json，置 partial 并
                   在 limitations 说明「预算耗尽，以下字段为当前最佳版本」
"""
import argparse
import json
import os
import time

LEDGER = "budget_ledger.json"


def load(work):
    p = os.path.join(work, LEDGER)
    return json.load(open(p, encoding="utf-8")) if os.path.exists(p) else None


def cmd_init(a):
    os.makedirs(a.work, exist_ok=True)
    led = {"requests_budget": a.requests, "seconds_budget": a.seconds,
           "requests_used": 0, "t0": time.time(), "events": ["init"]}
    json.dump(led, open(os.path.join(a.work, LEDGER), "w", encoding="utf-8"),
              ensure_ascii=False, indent=2)
    print("[budget] init: %d requests / %d s" % (a.requests, a.seconds))


def cmd_tick(a):
    led = load(a.work)
    if led is None:
        raise SystemExit("先运行 budget.py init")
    led["requests_used"] += a.n
    led["events"].append("tick +%d (累计 %d)" % (a.n, led["requests_used"]))
    json.dump(led, open(os.path.join(a.work, LEDGER), "w", encoding="utf-8"),
              ensure_ascii=False, indent=2)
    print("[budget] requests_used=%d/%d" % (led["requests_used"],
                                            led["requests_budget"]))


def cmd_report(a):
    led = load(a.work)
    if led is None:
        raise SystemExit("先运行 budget.py init")
    elapsed = time.time() - led["t0"]
    req_frac = led["requests_used"] / led["requests_budget"]
    sec_frac = elapsed / led["seconds_budget"]
    usage = max(req_frac, sec_frac)
    if usage < 0.5:
        advice = "正常推进"
    elif usage < 0.8:
        advice = "不再开新分析支线，优先填满契约字段"
    else:
        advice = ("立即收尾：当前结论按现状写入 result.json，status=partial，"
                  "limitations 注明预算耗尽")
    rep = {"requests_used": led["requests_used"],
           "requests_budget": led["requests_budget"],
           "elapsed_s": round(elapsed, 1), "seconds_budget": led["seconds_budget"],
           "usage_frac": round(usage, 3), "advice": advice}
    print(json.dumps(rep, ensure_ascii=False, indent=2))


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("init")
    p.add_argument("--work", default="/app/work")
    p.add_argument("--requests", type=int, default=64)
    p.add_argument("--seconds", type=int, default=900)
    p.set_defaults(fn=cmd_init)
    p = sub.add_parser("tick")
    p.add_argument("--work", default="/app/work")
    p.add_argument("--n", type=int, default=1)
    p.set_defaults(fn=cmd_tick)
    p = sub.add_parser("report")
    p.add_argument("--work", default="/app/work")
    p.set_defaults(fn=cmd_report)
    a = ap.parse_args()
    a.fn(a)


if __name__ == "__main__":
    main()
