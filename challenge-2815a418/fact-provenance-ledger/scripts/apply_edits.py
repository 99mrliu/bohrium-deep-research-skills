#!/usr/bin/env python3
"""apply_edits.py — 最小锚点落稿引擎。

读取 edits.json：
  [{"change_id": "CHG-01", "sub_request": "R1.1", "action": "修改",
     "anchor": "基线中的逐字片段", "new_text": "替换/插入文本"}, ...]

action 取值：
  新增 / insert_after   —— 在 anchor 之后插入 new_text
  新增前 / insert_before —— 在 anchor 之前插入 new_text
  修改 / replace         —— 用 new_text 替换 anchor
  删除 / delete          —— 删除 anchor（new_text 忽略）

规则：
  - anchor 必须在基线中**逐字且唯一**匹配才落稿；未命中或不唯一 → pending_review，绝不猜位置。
  - 落稿处自动打 <!-- CHG-xx begin --> / <!-- CHG-xx end --> 标记。
  - 所有编辑基于同一基线原文定位（先全文校验所有 anchor，再按位置从后往前应用，
    避免前面改动破坏后面 anchor 的匹配）。
  - 派生 changes.json（机器可读的修改记录）与 apply_report.json。

用法：
  python3 apply_edits.py --baseline 基线.md --edits edits.json \
      --out 修订稿.md --changes changes.json --report apply_report.json
仅 Python 3 标准库。
"""
import argparse
import json
import os
import sys

ACTION_ALIASES = {
    "新增": "insert_after", "insert_after": "insert_after",
    "新增前": "insert_before", "insert_before": "insert_before",
    "修改": "replace", "replace": "replace",
    "删除": "delete", "delete": "delete",
}


def main():
    ap = argparse.ArgumentParser(description="锚点落稿引擎")
    ap.add_argument("--baseline", required=True)
    ap.add_argument("--edits", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--changes", required=True)
    ap.add_argument("--report", required=True)
    args = ap.parse_args()

    with open(args.baseline, "r", encoding="utf-8") as f:
        baseline = f.read()
    with open(args.edits, "r", encoding="utf-8") as f:
        edits = json.load(f)
    if isinstance(edits, dict):
        edits = edits.get("edits", [])

    applied, pending = [], []
    plan = []  # (start, end, replacement, change_id, sub_request, action)

    for e in edits:
        cid = e.get("change_id") or "CHG-??"
        sub = e.get("sub_request", "")
        action = ACTION_ALIASES.get(e.get("action", ""))
        anchor = e.get("anchor", "")
        new_text = e.get("new_text", "")
        if action is None:
            pending.append({"change_id": cid, "sub_request": sub,
                            "reason": "unknown action: %r" % e.get("action")})
            continue
        if not anchor:
            pending.append({"change_id": cid, "sub_request": sub,
                            "reason": "empty anchor"})
            continue
        count = baseline.count(anchor)
        if count == 0:
            pending.append({"change_id": cid, "sub_request": sub,
                            "reason": "anchor not found (未命中)，拒绝猜位置"})
            continue
        if count > 1:
            pending.append({"change_id": cid, "sub_request": sub,
                            "reason": "anchor not unique (%d 处)，拒绝猜位置" % count})
            continue
        pos = baseline.index(anchor)
        begin = "<!-- %s begin -->" % cid
        end = "<!-- %s end -->" % cid
        if action == "insert_after":
            start, stop = pos + len(anchor), pos + len(anchor)
            replacement = begin + "\n" + new_text + "\n" + end
        elif action == "insert_before":
            start, stop = pos, pos
            replacement = begin + "\n" + new_text + "\n" + end + "\n"
        elif action == "replace":
            start, stop = pos, pos + len(anchor)
            replacement = begin + "\n" + new_text + "\n" + end + "\n"
        else:  # delete
            start, stop = pos, pos + len(anchor)
            replacement = begin + end
        # 冲突检测：与已计划的替换区间重叠则挂起
        overlap = any(not (stop <= a or start >= b) for a, b, *_ in plan)
        if overlap:
            pending.append({"change_id": cid, "sub_request": sub,
                            "reason": "anchor 区间与其他编辑重叠"})
            continue
        plan.append((start, stop, replacement, cid, sub, action))

    text = baseline
    for start, stop, replacement, cid, sub, action in sorted(plan, reverse=True):
        text = text[:start] + replacement + text[stop:]
        applied.append({"change_id": cid, "sub_request": sub, "action": action,
                        "anchor_offset": start})
    applied.reverse()

    for p in [args.out, args.changes, args.report]:
        os.makedirs(os.path.dirname(os.path.abspath(p)), exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as f:
        f.write(text)

    changes = [{"change_id": a["change_id"], "sub_request": a["sub_request"],
                "action": a["action"],
                "location": "%s offset=%d" % (os.path.basename(args.out),
                                              a["anchor_offset"]),
                "status": "applied"} for a in applied]
    changes += [{"change_id": p["change_id"], "sub_request": p["sub_request"],
                 "action": None, "location": None,
                 "status": "pending_review", "reason": p["reason"]}
                for p in pending]
    with open(args.changes, "w", encoding="utf-8") as f:
        json.dump({"changes": changes}, f, ensure_ascii=False, indent=2)

    report = {"baseline": args.baseline, "edits": args.edits, "out": args.out,
              "applied": len(applied), "pending_review": len(pending),
              "pending": pending}
    with open(args.report, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)

    print("apply_edits: %d applied, %d pending_review -> %s"
          % (len(applied), len(pending), args.out))
    if pending:
        for p in pending:
            print("  PENDING %s: %s" % (p["change_id"], p["reason"]),
                  file=sys.stderr)


if __name__ == "__main__":
    main()
