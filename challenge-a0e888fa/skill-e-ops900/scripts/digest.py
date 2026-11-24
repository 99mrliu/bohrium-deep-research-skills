#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""digest.py — 紧凑摘要器：把一个产物目录压成 <2KB 的人读摘要。

为 16384 tokens/响应 的预算设计：Agent 不需要 cat 整个 CSV，只需要知道
"几张表、几行几列、台账几类动作各几条、复核队列前几行、result.json 的
status"。退出码：0 正常；2 参数错误。
"""
import argparse
import csv
import json
import os
import sys


def summarize_csv(path, head=3):
    with open(path, encoding="utf-8-sig", newline="") as f:
        rows = list(csv.reader(f))
    if not rows:
        return "空表"
    out = ["%d 行 x %d 列 | 表头: %s" % (len(rows) - 1, len(rows[0]),
                                        ",".join(rows[0])[:120])]
    if os.path.basename(path) == "ledger.csv" and "action" in rows[0]:
        ai = rows[0].index("action")
        acts = {}
        for r in rows[1:]:
            if ai < len(r):
                acts[r[ai]] = acts.get(r[ai], 0) + 1
        out.append("动作统计: %s" % json.dumps(acts, ensure_ascii=False))
    for r in rows[1:1 + head]:
        out.append("  " + " | ".join(c[:24] for c in r))
    if len(rows) - 1 > head:
        out.append("  … 其余 %d 行省略" % (len(rows) - 1 - head))
    return "\n".join(out)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("dir", help="产物目录")
    ap.add_argument("--max-bytes", type=int, default=1900)
    args = ap.parse_args()
    if not os.path.isdir(args.dir):
        print("ERROR: 目录不存在", file=sys.stderr)
        sys.exit(2)
    parts = ["# 产物摘要（digest.py 生成）", ""]
    for name in sorted(os.listdir(args.dir)):
        p = os.path.join(args.dir, name)
        if not os.path.isfile(p):
            continue
        parts.append("## %s (%d B)" % (name, os.path.getsize(p)))
        if name.endswith(".csv"):
            parts.append(summarize_csv(p))
        elif name == "result.json":
            r = json.load(open(p, encoding="utf-8"))
            parts.append("case_id=%s status=%s keys=%s" % (
                r.get("case_id"), r.get("status"),
                ",".join(sorted(r.keys()))[:150]))
        elif name.endswith(".json"):
            d = json.load(open(p, encoding="utf-8"))
            parts.append(json.dumps(d, ensure_ascii=False)[:300])
        parts.append("")
    text = "\n".join(parts)
    b = text.encode("utf-8")
    if len(b) > args.max_bytes:
        text = b[:args.max_bytes].decode("utf-8", errors="ignore") + "\n…[截断]"
    print(text)


if __name__ == "__main__":
    main()
