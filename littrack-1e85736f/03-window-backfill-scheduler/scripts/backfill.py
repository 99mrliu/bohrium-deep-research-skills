#!/usr/bin/env python3
"""backfill.py — 延迟入库补抓事件生成。

触发条件（assigned_items.json 中 classification == "backfill"）：
- published 归一化区间完整落在某个**已关闭**窗口；
- 条目本轮才在源中出现（indexed 落在当前窗口；indexed 缺失时按本轮处理并记 flag）。

事件字段：原窗口号 original_window、延迟时长 delay_days
（indexed 时间 − published 区间 latest，取保守下界）、原因 reason=late_indexing、
published/indexed 的归一化值与 locator。

用法：
  python3 backfill.py --work-dir <dir> --out backfill_events.json
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from window_common import dump_json, load_json, parse_instant  # noqa: E402


def build_events(assigned):
    events = []
    for rec in assigned.get("items", []):
        if rec.get("classification") != "backfill":
            continue
        pub, idx = rec.get("published"), rec.get("indexed")
        delay_days = None
        if pub and idx:
            delta = parse_instant(idx["earliest"]) - parse_instant(pub["latest"])
            delay_days = round(delta.total_seconds() / 86400.0, 4)
        flags = list(rec.get("flags", []))
        if rec.get("arrival_window") and not rec.get("arrival_in_current_window"):
            flags.append("arrival_not_in_current_window")
        events.append({
            "doi": rec.get("doi"),
            "title": rec.get("title"),
            "source": rec.get("source"),
            "original_window": rec.get("content_window"),
            "arrival_window": rec.get("arrival_window"),
            "published_utc": {"earliest": pub["earliest"], "latest": pub["latest"],
                              "precision": pub["precision"]} if pub else None,
            "indexed_utc": idx["earliest"] if idx else None,
            "delay_days": delay_days,
            "reason": "late_indexing",
            "explanation": "published 落在已关闭窗口 %s，但本轮才在源 %s 中出现，"
                           "补抓回原窗口并计入本轮新增（单独标记）"
                           % (rec.get("content_window"), rec.get("source")),
            "locators": {
                "item": rec.get("item_locator"),
                "published": pub.get("locator") if pub else None,
                "indexed": idx.get("locator") if idx else None,
            },
            "flags": flags,
        })
    return events


def main(argv=None):
    ap = argparse.ArgumentParser(description="延迟入库补抓事件生成")
    ap.add_argument("--work-dir", required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args(argv)
    assigned = load_json(os.path.join(args.work_dir, "assigned_items.json"))
    events = build_events(assigned)
    dump_json({"backfill_count": len(events), "events": events}, args.out)
    print("backfill -> %s | events=%d" % (args.out, len(events)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
