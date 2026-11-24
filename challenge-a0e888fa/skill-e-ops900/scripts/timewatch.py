#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""timewatch.py — 预算哨兵：记录阶段耗时，对照 900 秒预算给出降级建议。

用法：
  timewatch.py start --workdir /app/work            # 开工打点
  timewatch.py mark 读案完成 --workdir /app/work     # 阶段打点
  timewatch.py status --workdir /app/work            # 查看预算与建议

预算模型：总 900s。建议水位：>600s 进入"收口"（只做报告与 result.json），
>750s 进入"保底"（立即落盘 partial）。退出码：0。
"""
import argparse
import json
import os
import sys
import time

BUDGET = 900.0
STATE = "timewatch.json"


def load(workdir):
    p = os.path.join(workdir, STATE)
    if os.path.isfile(p):
        return json.load(open(p, encoding="utf-8"))
    return None


def advice(elapsed):
    if elapsed > 750:
        return "保底：立即写 result.json(partial) 与已有产物，停止新分析"
    if elapsed > 600:
        return "收口：停止新工序，只做报告重算与 result.json 填充"
    if elapsed > 450:
        return "过半：不再开新工具，按既有管道推进"
    return "充裕"


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("cmd", choices=["start", "mark", "status"])
    ap.add_argument("label", nargs="?", default="")
    ap.add_argument("--workdir", required=True)
    args = ap.parse_args()
    os.makedirs(args.workdir, exist_ok=True)
    p = os.path.join(args.workdir, STATE)
    now = time.time()
    st = load(args.workdir)
    if args.cmd == "start":
        st = {"t0": now, "marks": []}
        json.dump(st, open(p, "w"))
        print(json.dumps({"status": "started", "budget_s": BUDGET}))
        return
    if not st:
        print("ERROR: 未 start", file=sys.stderr)
        sys.exit(2)
    elapsed = now - st["t0"]
    if args.cmd == "mark":
        st["marks"].append({"label": args.label, "elapsed_s": round(elapsed, 1)})
        json.dump(st, open(p, "w"), ensure_ascii=False)
    print(json.dumps({"elapsed_s": round(elapsed, 1),
                      "remaining_s": round(BUDGET - elapsed, 1),
                      "marks": st["marks"][-5:],
                      "advice": advice(elapsed)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
