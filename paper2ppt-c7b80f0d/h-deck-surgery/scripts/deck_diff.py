#!/usr/bin/env python3
"""deck_diff.py — 页级机器 diff：增/删/移/标题变更/文本变更/备注变更。

用法:
    python3 deck_diff.py <old.pptx> <new.pptx> --report deck_diff.json

匹配策略：以逐页 text_hash 序列做 SequenceMatcher 对齐；
replace 块内按序配对，逐对比较标题/正文/备注；哈希相同但整体顺序不同则报 moved。
"""
from __future__ import annotations

import argparse
import difflib
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import deck_common as dc


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="比较两个 pptx，输出页级 diff JSON")
    ap.add_argument("old", help="旧版本 pptx（如 versions/v1.pptx）")
    ap.add_argument("new", help="新版本 pptx（如最终 deck）")
    ap.add_argument("--report", required=True, help="输出 deck_diff.json")
    args = ap.parse_args(argv)

    for p in (args.old, args.new):
        if not os.path.exists(p):
            print(f"error: deck not found: {p}", file=sys.stderr)
            return 2
    a = dc.load_deck(args.old)
    b = dc.load_deck(args.new)
    ha = [s["text_hash"] for s in a["slides"]]
    hb = [s["text_hash"] for s in b["slides"]]

    sm = difflib.SequenceMatcher(a=ha, b=hb, autojunk=False)
    added, removed, modified, unchanged = [], [], [], 0
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag == "equal":
            for k in range(i2 - i1):
                sa, sb = a["slides"][i1 + k], b["slides"][j1 + k]
                if sa["full_hash"] == sb["full_hash"]:
                    unchanged += 1
                else:
                    modified.append({
                        "slide_old": sa["index"], "slide_new": sb["index"],
                        "title_change": None, "text_changed": False,
                        "notes_changed": True,
                        "detail": "notes changed (text identical)",
                    })
            continue
        if tag == "delete":
            removed += [a["slides"][i]["index"] for i in range(i1, i2)]
            continue
        if tag == "insert":
            added += [{"slide_new": b["slides"][j]["index"],
                       "title": b["slides"][j]["title"]} for j in range(j1, j2)]
            continue
        # replace 块：按序配对，剩余记增/删
        block_a = list(range(i1, i2))
        block_b = list(range(j1, j2))
        for k in range(min(len(block_a), len(block_b))):
            sa, sb = a["slides"][block_a[k]], b["slides"][block_b[k]]
            entry = {
                "slide_old": sa["index"], "slide_new": sb["index"],
                "title_change": (
                    {"from": sa["title"], "to": sb["title"]}
                    if sa["title"] != sb["title"] else None
                ),
                "text_changed": sa["text_hash"] != sb["text_hash"],
                "notes_changed": sa["notes"] != sb["notes"],
                "detail": "title/text/notes modified",
            }
            modified.append(entry)
        removed += [a["slides"][i]["index"] for i in block_a[len(block_b):]]
        added += [{"slide_new": b["slides"][j]["index"],
                   "title": b["slides"][j]["title"]} for j in block_b[len(block_a):]]

    moved = []
    if sorted(ha) == sorted(hb) and ha != hb:
        for j, h in enumerate(hb, start=1):
            i = ha.index(h) + 1
            if i != j:
                moved.append({"from": i, "to": j})

    report = {
        "old": os.path.abspath(args.old),
        "new": os.path.abspath(args.new),
        "engine": f"{a['engine']}->{b['engine']}",
        "old_slides": a["slide_count"],
        "new_slides": b["slide_count"],
        "unchanged": unchanged,
        "added": added,
        "removed": removed,
        "moved": moved,
        "modified": modified,
        "summary": (
            f"{a['slide_count']}->{b['slide_count']} slides; "
            f"added={len(added)} removed={len(removed)} moved={len(moved)} "
            f"modified={len(modified)} unchanged={unchanged}"
        ),
    }
    dc.dump_json(report, args.report)
    print(f"diff ok: {report['summary']} -> {args.report}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
