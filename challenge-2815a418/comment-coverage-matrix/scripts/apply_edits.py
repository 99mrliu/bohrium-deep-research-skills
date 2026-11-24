#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""apply_edits.py — 最小锚点落稿引擎。

edits.json -> revised-manuscript.md（带 CHG 标记）+ changes.json + apply_report.json
锚点为 baseline 中的逐字片段，必须恰好唯一命中；0 次或多次命中一律进 pending_review，
绝不模糊替换。

edits.json 结构:
{"edits": [
  {"chg_id": "CHG-01", "sub_ids": ["R1.1"], "anchor": "逐字原文片段",
   "action": "replace|insert_after|insert_before|delete",
   "new_text": "新文本（delete 可省略）", "section": "方法", "note": "说明"}
]}

用法:
  python3 apply_edits.py --manuscript baseline.md --edits edits.json --outdir /app/output
"""
import argparse, json, os, re, sys
from datetime import datetime, timezone

ACTIONS = {"replace", "insert_after", "insert_before", "delete"}


def wrap(chg_id, text):
    return "<!-- %s begin -->\n%s\n<!-- %s end -->" % (chg_id, text, chg_id)


def paragraph_index(text, marker):
    """含 marker 的段落在全文中的段序（按空行分段，从 1 起）。"""
    pos = text.find(marker)
    if pos < 0:
        return None
    idx = 1
    for m in re.finditer(r'\n\s*\n', text):
        if m.end() <= pos:
            idx += 1
        else:
            break
    return idx


def main():
    ap = argparse.ArgumentParser(description="最小锚点落稿引擎")
    ap.add_argument("--manuscript", required=True)
    ap.add_argument("--edits", required=True)
    ap.add_argument("--outdir", required=True)
    a = ap.parse_args()
    for p in (a.manuscript, a.edits):
        if not os.path.exists(p):
            print("[apply_edits] FATAL: file not found: %s" % p, file=sys.stderr)
            sys.exit(2)
    text = open(a.manuscript, encoding="utf-8").read()
    spec = json.load(open(a.edits, encoding="utf-8"))
    edits = spec.get("edits", [])
    if not edits:
        print("[apply_edits] WARN: edits.json 为空，输出与基线一致", file=sys.stderr)

    applied, pending = [], []
    for e in edits:
        chg = e.get("chg_id", "").strip()
        anchor = e.get("anchor", "")
        act = e.get("action", "replace")
        new_text = e.get("new_text", "")
        sub_ids = e.get("sub_ids", [])
        if not chg or not anchor or act not in ACTIONS:
            pending.append({"chg_id": chg or "?", "reason": "缺 chg_id/anchor 或 action 非法（须 ∈ %s）" % sorted(ACTIONS)})
            continue
        if not sub_ids:
            pending.append({"chg_id": chg, "reason": "sub_ids 为空：每处改动必须归属至少一个子要求"})
            continue
        if act != "delete" and not new_text.strip():
            pending.append({"chg_id": chg, "reason": "action=%s 但 new_text 为空" % act})
            continue
        n = text.count(anchor)
        if n != 1:
            pending.append({"chg_id": chg, "reason": "锚点命中 %d 次（须恰好 1 次），未落稿；请换更长的逐字锚点" % n,
                            "anchor_preview": anchor[:60]})
            continue
        if act == "replace":
            repl = wrap(chg, new_text)
        elif act == "delete":
            repl = "<!-- %s delete: removed 「%s」 -->" % (chg, anchor[:80])
        elif act == "insert_after":
            repl = anchor + "\n" + wrap(chg, new_text)
        else:  # insert_before
            repl = wrap(chg, new_text) + "\n" + anchor
        text = text.replace(anchor, repl, 1)
        applied.append({"chg_id": chg, "action": act, "sub_ids": sub_ids,
                        "section": e.get("section", ""), "note": e.get("note", ""),
                        "anchor_preview": anchor[:60]})

    # 计算每个已应用 CHG 在修订稿中的段序
    changes = []
    for e in applied:
        para = paragraph_index(text, "<!-- %s begin -->" % e["chg_id"]) or \
               paragraph_index(text, "<!-- %s delete" % e["chg_id"])
        changes.append({"chg_id": e["chg_id"], "sub_ids": e["sub_ids"],
                        "section": e["section"], "paragraph": para,
                        "action": e["action"], "note": e["note"],
                        "anchor_preview": e["anchor_preview"], "status": "applied"})

    os.makedirs(a.outdir, exist_ok=True)
    p_rev = os.path.join(a.outdir, "revised-manuscript.md")
    p_chg = os.path.join(a.outdir, "changes.json")
    p_rep = os.path.join(a.outdir, "apply_report.json")
    with open(p_rev, "w", encoding="utf-8") as f:
        f.write(text)
    with open(p_chg, "w", encoding="utf-8") as f:
        json.dump({"changes": changes,
                   "generated_by": "apply_edits.py",
                   "generated_at": datetime.now(timezone.utc).isoformat(timespec='seconds')},
                  f, ensure_ascii=False, indent=2)
    with open(p_rep, "w", encoding="utf-8") as f:
        json.dump({"applied": len(applied), "pending_review": pending,
                   "pending_count": len(pending)}, f, ensure_ascii=False, indent=2)
    print("[apply_edits] applied=%d pending=%d -> %s" % (len(applied), len(pending), p_rev))
    if pending:
        print("[apply_edits] WARN: %d 处改动未落稿（见 apply_report.json 的 pending_review），请修锚点重跑" % len(pending), file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
