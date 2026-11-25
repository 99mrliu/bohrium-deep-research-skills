#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""truth_build.py — 由快照对机械构造增量真值。

规则（详见 references/truth_construction.md）：
  added（t_now 有、t_prev 无）中的每条记录按 published 日期与窗口 [start, end]（两端含）分类：
    published 在窗口内          -> truth_new（应被发现的新增）
    published 早于窗口起点      -> truth_backfill（晚入库的旧文献，不应报为 new）
    published 晚于窗口终点      -> truth_out_of_window（不属于本窗口）
    published 缺失/无法解析     -> unclassifiable（诚实单列，不猜测）

真值只能来自快照对。若只有单份快照，本脚本不应被调用；上层流程须降级 partial。

仅使用 Python3 标准库，完全离线。
"""
import argparse
import datetime
import json
import sys


def load_json(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def dump_json(path, obj):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)
        f.write("\n")


def parse_date(s):
    if not s:
        return None
    try:
        return datetime.date.fromisoformat(str(s)[:10])
    except ValueError:
        return None


def main(argv=None):
    ap = argparse.ArgumentParser(description="由快照对构造增量真值")
    ap.add_argument("--aligned", required=True, help="snapshot_align.py 输出的 aligned.json")
    ap.add_argument("--window-start", default=None, help="窗口起点 YYYY-MM-DD（含）")
    ap.add_argument("--window-end", default=None, help="窗口终点 YYYY-MM-DD（含）")
    ap.add_argument("--out", required=True, help="输出 truth.json 路径")
    args = ap.parse_args(argv)

    aligned = load_json(args.aligned)
    ws = parse_date(args.window_start)
    we = parse_date(args.window_end)
    if args.window_start and ws is None:
        raise SystemExit("ERROR: window-start 无法解析: %r" % args.window_start)
    if args.window_end and we is None:
        raise SystemExit("ERROR: window-end 无法解析: %r" % args.window_end)

    truth_new, truth_backfill, truth_ow, unclass = [], [], [], []
    for item in aligned.get("added", []):
        pub = parse_date(item.get("published"))
        if pub is None:
            entry = dict(item)
            entry["unclassifiable_reason"] = "published 缺失或无法解析: %r" % item.get("published")
            unclass.append(entry)
        elif ws is not None and pub < ws:
            truth_backfill.append(item)
        elif we is not None and pub > we:
            truth_ow.append(item)
        else:
            truth_new.append(item)

    out = {
        "source_basis": "snapshot_pair (t_prev import state + t_now current snapshot)",
        "snapshots": {"prev": aligned.get("prev_path"), "now": aligned.get("now_path")},
        "window": {"start": args.window_start, "end": args.window_end, "inclusive": True},
        "counts": {
            "added_total": len(aligned.get("added", [])),
            "new": len(truth_new),
            "backfill": len(truth_backfill),
            "out_of_window": len(truth_ow),
            "unclassifiable": len(unclass),
        },
        "truth_new": truth_new,
        "truth_backfill": truth_backfill,
        "truth_out_of_window": truth_ow,
        "unclassifiable": unclass,
        "construction_note": (
            "真值由快照对机械构造：t_now 有而 t_prev 无者为新增候选，再按 published 与窗口分类。"
            "未做任何人工标注或外部检索；单快照场景不得调用本脚本。"
        ),
    }
    dump_json(args.out, out)
    print("truth: new=%d backfill=%d out_of_window=%d unclassifiable=%d (added_total=%d)"
          % (len(truth_new), len(truth_backfill), len(truth_ow), len(unclass),
             len(aligned.get("added", []))))
    return 0


if __name__ == "__main__":
    sys.exit(main())
