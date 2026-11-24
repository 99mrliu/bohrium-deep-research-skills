#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""apply_edits.py — 只通过锚点把修改落进基线，产出修订稿 + changes.json。

edits.json 格式（列表）：
  [{
    "change_id":   "CHG-01",               # 唯一改动编号
    "sub_request": "R1.1",                 # 对应意见子要求编号
    "action":      "新增" | "修改" | "删除",
    "anchor":      "A004",                 # 目标锚点号
    "position":    "after" | "before",     # 可选，仅"新增"有效，默认 after
    "new_text":    "……",                   # "新增"/"修改"必填，"删除"忽略
    "summary":     "一句话改动说明"
  }]

落稿规则（绝不猜位置）：
  1. 锚点 quote 必须在当前稿件中恰好出现 1 次，否则进 pending_review；
  2. "修改"：整段替换为 new_text；
     "新增"：在锚点段之后（或之前）插入 new_text 作为新段；
     "删除"：整段移除，仅留标记；
  3. 每处落稿打标记 <!-- CHG-xx begin: R#.# --> … <!-- CHG-xx end -->。

产物：
  --out      revised-manuscript.md
  --changes  changes.json（每条：change_id、comment_refs、anchor{anchor_id,
             heading, paragraph_index, quote}、action、before/after 摘要）
  --report   apply_report.json（applied 与 pending_review 清单及原因）

pending_review 原因：unknown_anchor / anchor_not_found /
anchor_not_unique / empty_new_text / invalid_action。
仅使用 Python 3 标准库。
"""
import argparse
import json
import sys

MAX_SNIPPET = 200


def snippet(s):
    s = (s or "").strip()
    return s if len(s) <= MAX_SNIPPET else s[:MAX_SNIPPET] + "……"


def main():
    ap = argparse.ArgumentParser(description="锚点落稿引擎")
    ap.add_argument("--baseline", required=True, help="基线稿件路径")
    ap.add_argument("--anchors", required=True, help="anchor_map.py 产出的 anchors.json")
    ap.add_argument("--edits", required=True, help="Agent 手写的 edits.json")
    ap.add_argument("--out", required=True, help="修订稿输出 revised-manuscript.md")
    ap.add_argument("--changes", required=True, help="changes.json 输出路径")
    ap.add_argument("--report", required=True, help="apply_report.json 输出路径")
    args = ap.parse_args()

    with open(args.baseline, "r", encoding="utf-8") as f:
        work = f.read()
    with open(args.anchors, "r", encoding="utf-8") as f:
        anchors = {a["anchor_id"]: a for a in json.load(f)}
    with open(args.edits, "r", encoding="utf-8") as f:
        edits = json.load(f)

    changes = []
    applied = []
    pending = []
    seen_ids = set()

    def pend(edit, reason, detail):
        pending.append({
            "change_id": edit.get("change_id"),
            "sub_request": edit.get("sub_request"),
            "anchor": edit.get("anchor"),
            "reason": reason,
            "detail": detail,
        })

    for edit in edits:
        cid = edit.get("change_id", "")
        sub = edit.get("sub_request", "")
        action = edit.get("action", "")
        aid = edit.get("anchor", "")
        new_text = edit.get("new_text", "") or ""
        position = edit.get("position", "after")

        if not cid:
            pend(edit, "invalid_action", "缺少 change_id")
            continue
        if cid in seen_ids:
            pend(edit, "invalid_action", "change_id 重复: %s" % cid)
            continue
        seen_ids.add(cid)
        if action not in ("新增", "修改", "删除"):
            pend(edit, "invalid_action", "action 必须为 新增/修改/删除，收到: %r" % action)
            continue
        if aid not in anchors:
            pend(edit, "unknown_anchor", "锚点号 %s 不在 anchors.json 中" % aid)
            continue
        quote = anchors[aid]["quote"]
        count = work.count(quote)
        if count == 0:
            pend(edit, "anchor_not_found",
                 "锚点 %s 的 quote 在当前稿件中未命中（可能基线漂移或前序改动覆盖）" % aid)
            continue
        if count > 1:
            pend(edit, "anchor_not_unique",
                 "锚点 %s 的 quote 在当前稿件中出现 %d 次，拒绝猜测位置" % (aid, count))
            continue
        if action in ("新增", "修改") and not new_text.strip():
            pend(edit, "empty_new_text", "action=%s 但 new_text 为空" % action)
            continue

        begin = "<!-- %s begin: %s -->" % (cid, sub)
        end = "<!-- %s end -->" % cid
        if action == "修改":
            replacement = "%s\n%s\n%s" % (begin, new_text, end)
        elif action == "新增":
            block = "%s\n%s\n%s" % (begin, new_text, end)
            if position == "before":
                replacement = "%s\n\n%s" % (block, quote)
            else:
                replacement = "%s\n\n%s" % (quote, block)
        else:  # 删除
            replacement = "%s\n%s" % (begin, end)

        work = work.replace(quote, replacement, 1)

        refs = [r.strip() for r in sub.replace("，", ",").split(",") if r.strip()]
        changes.append({
            "change_id": cid,
            "comment_refs": refs,
            "anchor": {
                "anchor_id": aid,
                "heading": anchors[aid]["heading"],
                "paragraph_index": anchors[aid]["paragraph_index"],
                "quote": quote,
            },
            "action": action,
            "summary": edit.get("summary", ""),
            "before": snippet(quote) if action != "新增" else "",
            "after": snippet(new_text),
        })
        applied.append(cid)

    with open(args.out, "w", encoding="utf-8") as f:
        f.write(work)
    with open(args.changes, "w", encoding="utf-8") as f:
        json.dump(changes, f, ensure_ascii=False, indent=2)
    report = {
        "applied": applied,
        "pending_review": pending,
        "stats": {"edits_total": len(edits), "applied": len(applied),
                  "pending": len(pending)},
    }
    with open(args.report, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)

    print("落稿 %d/%d 处 -> %s" % (len(applied), len(edits), args.out))
    if pending:
        print("pending_review %d 处（见 %s）：" % (len(pending), args.report))
        for p in pending:
            print("  - %s [%s] %s" % (p["change_id"], p["reason"], p["detail"]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
