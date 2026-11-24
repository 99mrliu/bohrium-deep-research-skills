#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""apply_edits.py — 最小锚点落稿引擎。

把 edits.json 中定义的修改以「逐字唯一锚点」方式落到基线稿件上：
  - 每处修改在文本中包上可见标记 ⟦CHG-##-BEGIN⟧…⟦CHG-##-END⟧；
  - 产出 work/revised_marked.md（带标记全文）、work/changes.json（逐条修改明细）、
    work/apply_report.json（汇总 + pending_review 列表）。
锚点找不到或不唯一时不中断：该修改记 failed 并进入 pending_review，由 Agent 修正后重跑。

仅依赖 Python 3 标准库。

用法：
  python3 apply_edits.py --baseline materials/manuscript-baseline.md \
      --edits /app/work/edits.json --work /app/work
"""
import argparse
import json
import os
import sys
from datetime import datetime, timezone

MARK_BEGIN = "\u27e6{chg}-BEGIN\u27e7"  # ⟦CHG-01-BEGIN⟧
MARK_END = "\u27e6{chg}-END\u27e7"

ACTIONS = ("replace", "insert_after", "insert_before", "delete")


def load_json(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def find_section(lines, lineno):
    """返回 lineno（1 起始）之前最近的 markdown 标题，无则返回 '(卷首)'。"""
    sec = "(卷首)"
    for i, line in enumerate(lines[:lineno], start=1):
        s = line.strip()
        if s.startswith("#"):
            sec = s.lstrip("#").strip() or sec
    return sec


def main():
    ap = argparse.ArgumentParser(description="最小锚点落稿引擎")
    ap.add_argument("--baseline", required=True, help="基线稿件 markdown 路径")
    ap.add_argument("--edits", required=True, help="edits.json 路径")
    ap.add_argument("--work", required=True, help="工作目录（写 revised_marked.md / changes.json / apply_report.json）")
    args = ap.parse_args()

    with open(args.baseline, "r", encoding="utf-8") as f:
        text = f.read()
    edits_doc = load_json(args.edits)
    edits = edits_doc.get("edits", [])

    changes = []
    pending = []
    cur = text
    for idx, e in enumerate(edits, start=1):
        chg = e.get("chg_id") or "CHG-%02d" % idx
        anchor = e.get("anchor", "")
        action = e.get("action", "replace")
        new_text = e.get("new_text", "")
        rec = {
            "chg_id": chg,
            "action": action,
            "anchor": anchor,
            "old_text": "",
            "new_text": new_text,
            "linked_rids": e.get("linked_rids", []),
            "evidence_ids": e.get("evidence_ids", []),
            "reason": e.get("reason", ""),
            "status": "failed",
            "fail_reason": "",
            "line": None,
            "section": None,
        }
        if action not in ACTIONS:
            rec["fail_reason"] = "unknown_action:%s" % action
        elif not anchor:
            rec["fail_reason"] = "empty_anchor"
        else:
            count = cur.count(anchor)
            if count == 0:
                rec["fail_reason"] = "anchor_not_found"
            elif count > 1:
                rec["fail_reason"] = "anchor_not_unique(%d)" % count
            else:
                begin = MARK_BEGIN.format(chg=chg)
                end = MARK_END.format(chg=chg)
                if action == "replace":
                    rec["old_text"] = anchor
                    repl = begin + new_text + end
                    cur = cur.replace(anchor, repl, 1)
                elif action == "delete":
                    rec["old_text"] = anchor
                    repl = begin + "【已删除】" + end
                    cur = cur.replace(anchor, repl, 1)
                elif action == "insert_after":
                    repl = anchor + begin + new_text + end
                    cur = cur.replace(anchor, repl, 1)
                else:  # insert_before
                    repl = begin + new_text + end + anchor
                    cur = cur.replace(anchor, repl, 1)
                pos = cur.index(begin)
                lineno = cur[:pos].count("\n") + 1
                rec["line"] = lineno
                rec["section"] = find_section(cur.splitlines(), lineno)
                rec["status"] = "applied"
        if rec["status"] != "applied":
            pending.append({"chg_id": chg, "fail_reason": rec["fail_reason"], "anchor": anchor})
        changes.append(rec)

    os.makedirs(args.work, exist_ok=True)
    marked_path = os.path.join(args.work, "revised_marked.md")
    with open(marked_path, "w", encoding="utf-8") as f:
        f.write(cur)
    with open(os.path.join(args.work, "changes.json"), "w", encoding="utf-8") as f:
        json.dump({"changes": changes}, f, ensure_ascii=False, indent=2)

    n_applied = sum(1 for c in changes if c["status"] == "applied")
    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "baseline": os.path.abspath(args.baseline),
        "edits": os.path.abspath(args.edits),
        "total_edits": len(changes),
        "applied": n_applied,
        "failed": len(changes) - n_applied,
        "status": "applied" if not pending else "pending_review",
        "pending_review": pending,
        "revised_marked": marked_path,
    }
    with open(os.path.join(args.work, "apply_report.json"), "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)

    print("apply_edits: %d/%d applied, status=%s -> %s" % (n_applied, len(changes), report["status"], args.work))
    return 0


if __name__ == "__main__":
    sys.exit(main())
