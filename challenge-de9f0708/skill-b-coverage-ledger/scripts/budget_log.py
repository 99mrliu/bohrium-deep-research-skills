#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""budget_log.py — 追加式预算账:记录相位耗时与模型请求数估计,超阈值给止损建议。

用法:
    python3 budget_log.py --log /app/work/budget.jsonl --phase intake \
        --seconds 5 --requests 1
    python3 budget_log.py --log /app/work/budget.jsonl --status   # 只看账不追加

阈值(默认贴合执行预算 64 请求/900 秒的 75% 预警线):
    --limit-requests 48 --limit-seconds 720
超阈值时输出 "止损建议:立即固化当前结果" 并建议下一步动作。任何异常 exit 0。
"""
import argparse
import json
import os
import sys


def load_entries(path):
    entries = []
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                    if isinstance(obj, dict):
                        entries.append(obj)
                except ValueError:
                    continue
    except OSError:
        pass
    return entries


def totals(entries):
    secs = 0
    reqs = 0
    for e in entries:
        try:
            secs += float(e.get("seconds", 0) or 0)
        except (TypeError, ValueError):
            pass
        try:
            reqs += int(e.get("requests", 0) or 0)
        except (TypeError, ValueError):
            pass
    return secs, reqs


def main(argv=None):
    ap = argparse.ArgumentParser(description="预算账:追加记录相位耗时/请求数,超阈值给止损建议")
    ap.add_argument("--log", required=True, help="JSONL 预算账文件路径")
    ap.add_argument("--phase", default=None, help="相位名(intake/review:<facet>/coverage/compose/final)")
    ap.add_argument("--seconds", type=float, default=0.0, help="本相位耗时秒数(估计)")
    ap.add_argument("--requests", type=int, default=0, help="本相位模型请求数(估计)")
    ap.add_argument("--note", default="", help="备注")
    ap.add_argument("--status", action="store_true", help="只输出当前账目汇总,不追加")
    ap.add_argument("--limit-requests", type=int, default=48, help="请求数预警阈值(默认 48)")
    ap.add_argument("--limit-seconds", type=float, default=720.0, help="耗时预警阈值秒(默认 720)")
    args = ap.parse_args(argv)

    entries = load_entries(args.log)
    if not args.status:
        entry = {
            "seq": len(entries) + 1,
            "phase": args.phase or "unspecified",
            "seconds": args.seconds,
            "requests": args.requests,
            "note": args.note,
        }
        entries.append(entry)
        try:
            os.makedirs(os.path.dirname(os.path.abspath(args.log)), exist_ok=True)
            with open(args.log, "a", encoding="utf-8") as f:
                f.write(json.dumps(entry, ensure_ascii=False) + "\n")
        except OSError as exc:
            print(json.dumps({"ok": False, "error": "无法写入预算账: %s" % exc},
                             ensure_ascii=False))
            return 0

    secs, reqs = totals(entries)
    over_req = reqs >= args.limit_requests
    over_sec = secs >= args.limit_seconds
    advice = ""
    if over_req or over_sec:
        advice = ("止损建议:立即固化当前结果——运行 coverage_check.py 将当前 findings "
                  "对账进 result.json,确认 status 诚实(partial 亦可),"
                  "未覆盖面进入 not_reviewed,然后停止新增审查动作,直接进入 compose/终审。")
    print(json.dumps({
        "ok": True,
        "entries": len(entries),
        "total_seconds": round(secs, 1),
        "total_requests": reqs,
        "limit_seconds": args.limit_seconds,
        "limit_requests": args.limit_requests,
        "over_budget": bool(over_req or over_sec),
        "advice": advice,
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
