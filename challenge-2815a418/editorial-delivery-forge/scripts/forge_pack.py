#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""forge_pack.py — 交付件锻造器（同源生成，编号一致）。

从 /app/work 的同一数据源（decisions.json + changes.json + apply_report.json +
revised_marked.md）锻造全部编辑部交付件，写入输出目录：
  - revised-manuscript.md    修订稿（内嵌 CHG 标记 + 文末修改摘要表）
  - response-letter.md       结构化回复信（信头占位/总述统计/逐条块/收口两表）
  - change-locations.json    修改定位表（CHG → 章节/行号/锚点上下文/关联 R#.#）
  - evidence-checklist.json  证据清单（EV → 状态/关联 R#.#、CHG）
  - change_record.md         修改记录（before/after 全文对照）

编号体系 R#.# ↔ CHG-## ↔ EV-## 全局唯一：所有产物由本脚本一次生成，禁止手工另写。

仅依赖 Python 3 标准库。

用法：
  python3 forge_pack.py --work /app/work --out /app/output [--case /input/case.json]
"""
import argparse
import json
import os
import sys
from datetime import datetime, timezone

DECISION_LABEL = {
    "accept": "接受",
    "partial": "部分接受",
    "decline": "婉拒（附说明）",
    "unable": "无法完成（附说明）",
}
ACTION_LABEL = {
    "replace": "替换",
    "insert_after": "后插",
    "insert_before": "前插",
    "delete": "删除",
}
EVIDENCE_LABEL = {
    "provided": "已提供",
    "pending": "待补（未到位）",
    "impossible": "无法提供",
}


def load_json(path, default=None):
    if not os.path.exists(path):
        if default is not None:
            return default
        raise FileNotFoundError(path)
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def w(outdir, name, text):
    path = os.path.join(outdir, name)
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)
    return path


def main():
    ap = argparse.ArgumentParser(description="同源锻造编辑部交付件")
    ap.add_argument("--work", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--case", default=None, help="case.json（取 case_id / output_contract）")
    args = ap.parse_args()

    decisions = load_json(os.path.join(args.work, "decisions.json"))
    changes_doc = load_json(os.path.join(args.work, "changes.json"), {"changes": []})
    report = load_json(os.path.join(args.work, "apply_report.json"), {})
    with open(os.path.join(args.work, "revised_marked.md"), "r", encoding="utf-8") as f:
        marked = f.read()
    case = load_json(args.case, {}) if args.case else {}

    case_id = decisions.get("case_id") or case.get("case_id") or "UNKNOWN-CASE"
    title = decisions.get("manuscript_title", "（稿件标题待填）")
    rds = decisions.get("reviewer_decisions", [])
    evidence = decisions.get("evidence", [])
    uncertainties = decisions.get("uncertainties", [])
    changes = changes_doc["changes"]
    applied = [c for c in changes if c["status"] == "applied"]
    now = datetime.now(timezone.utc).isoformat()

    rid_to_chgs = {}
    for c in changes:
        for rid in c.get("linked_rids", []):
            rid_to_chgs.setdefault(rid, []).append(c["chg_id"])
    eid_to_chgs = {}
    for c in changes:
        for eid in c.get("evidence_ids", []):
            eid_to_chgs.setdefault(eid, []).append(c["chg_id"])

    # ---- 一致性检查（警告不阻断） ----
    warnings = []
    for d in rds:
        chgs = [c for c in rid_to_chgs.get(d["rid"], [])
                if any(x["chg_id"] == c and x["status"] == "applied" for x in changes)]
        if d["decision"] == "accept" and not chgs:
            warnings.append("%s 裁决为「接受」但无已落实的 CHG 修改" % d["rid"])
    for c in changes:
        if c["status"] != "applied":
            warnings.append("%s 落稿失败（%s），仍待人工处理" % (c["chg_id"], c.get("fail_reason", "")))
    known_eids = {e["eid"] for e in evidence}
    for c in changes:
        for eid in c.get("evidence_ids", []):
            if eid not in known_eids:
                warnings.append("%s 引用了未在证据清单登记的 %s" % (c["chg_id"], eid))

    # ---- 统计 ----
    comment_ids = sorted({d.get("comment_id", d["rid"].split(".")[0]) for d in rds})
    n_dec = {k: sum(1 for d in rds if d["decision"] == k) for k in DECISION_LABEL}
    stats_line = ("共收到 %d 条意见、%d 个子要求；裁决：接受 %d、部分接受 %d、婉拒 %d、"
                  "无法完成 %d；落实正文修改 %d 处（另 %d 处落稿失败待处理）。") % (
        len(comment_ids), len(rds), n_dec["accept"], n_dec["partial"], n_dec["decline"],
        n_dec["unable"], len(applied), len(changes) - len(applied))

    os.makedirs(args.out, exist_ok=True)

    # ---- 1) revised-manuscript.md ----
    lines = []
    lines.append("# 修订稿（带修改标记）")
    lines.append("")
    lines.append("> - 案例：%s" % case_id)
    lines.append("> - 稿件标题：%s" % title)
    lines.append("> - 标记约定：`⟦CHG-##-BEGIN⟧…⟦CHG-##-END⟧` 为本次新增/替换文本；"
                 "`⟦CHG-##-BEGIN⟧【已删除】⟦CHG-##-END⟧` 为删除处；"
                 "`【待补数据 EV-##】` 为诚实占位，提交前须替换为真实数据。")
    lines.append("> - 声明：本稿由辅助代理基于组织方给出的**意见摘要**修订，"
                 "不代表审稿人原文逐字要求，亦不代表编辑部已接收。")
    lines.append("> - 生成时间：%s" % now)
    lines.append("")
    lines.append("---")
    lines.append("")
    lines.append(marked.rstrip())
    lines.append("")
    lines.append("---")
    lines.append("")
    lines.append("## 附录：修改摘要表")
    lines.append("")
    lines.append("| CHG 编号 | 关联意见 | 位置 | 修改类型 | 修改摘要 |")
    lines.append("|---|---|---|---|---|")
    for c in changes:
        loc = "%s 第%s行" % (c.get("section") or "?", c.get("line") or "?")
        if c["status"] != "applied":
            loc = "落稿失败：" + c.get("fail_reason", "")
        summ = (c.get("reason") or "").replace("|", "\\|").replace("\n", " ")
        lines.append("| %s | %s | %s | %s | %s |" % (
            c["chg_id"], "、".join(c.get("linked_rids", [])) or "—", loc,
            ACTION_LABEL.get(c["action"], c["action"]), summ or "—"))
    lines.append("")
    revised_path = w(args.out, "revised-manuscript.md", "\n".join(lines))

    # ---- 2) response-letter.md ----
    L = []
    L.append("# 审稿回复信（草案，待通讯作者审定）")
    L.append("")
    L.append("## 信头（占位待填）")
    L.append("")
    L.append("- 稿件编号：%s" % (decisions.get("manuscript_id") or "＿＿＿＿（待填）"))
    L.append("- 稿件标题：%s" % title)
    L.append("- 通讯作者：%s" % (decisions.get("corresponding_author") or "＿＿＿＿（待填）"))
    L.append("- 日期：%s" % (decisions.get("date") or "＿＿＿＿（待填）"))
    L.append("- 责任编辑：%s" % (decisions.get("editor_name") or "＿＿＿＿（待填）"))
    L.append("")
    L.append("尊敬的编辑与审稿专家：")
    L.append("")
    L.append("感谢您对本文的审阅。以下回复基于编辑部转达的**意见摘要**整理，"
             "如有与意见原文出入之处，以原文为准并恳请指正。")
    L.append("")
    L.append("## 一、总述")
    L.append("")
    L.append(stats_line)
    L.append("")
    L.append("## 二、逐条回复")
    by_comment = {}
    for d in rds:
        by_comment.setdefault(d.get("comment_id", d["rid"].split(".")[0]), []).append(d)
    for cid in sorted(by_comment):
        ds = by_comment[cid]
        reviewer = ds[0].get("reviewer", cid)
        csum = ds[0].get("comment_summary", "")
        L.append("")
        L.append("### 意见 %s（%s）" % (cid, reviewer))
        if csum:
            L.append("")
            L.append("意见摘要：%s" % csum)
        for d in ds:
            chgs = rid_to_chgs.get(d["rid"], [])
            evs = sorted({e for c in changes if c["chg_id"] in chgs for e in c.get("evidence_ids", [])})
            L.append("")
            L.append("**子要求 %s**" % d["rid"])
            L.append("")
            L.append("- 意见要点：%s" % d.get("summary", "（见意见摘要）"))
            L.append("- 裁决：%s" % DECISION_LABEL.get(d["decision"], d["decision"]))
            L.append("- 回应说明：%s" % d.get("response_text", d.get("rationale", "（待补）")))
            L.append("- 关联修改：%s" % ("、".join(chgs) if chgs else "—（无正文改动）"))
            L.append("- 关联证据：%s" % ("、".join(evs) if evs else "—"))
    L.append("")
    L.append("## 三、收口表")
    L.append("")
    L.append("### 表 A：裁决汇总")
    L.append("")
    L.append("| 子要求 | 裁决 | 关联修改 | 关联证据 |")
    L.append("|---|---|---|---|")
    for d in rds:
        chgs = rid_to_chgs.get(d["rid"], [])
        evs = sorted({e for c in changes if c["chg_id"] in chgs for e in c.get("evidence_ids", [])})
        L.append("| %s | %s | %s | %s |" % (
            d["rid"], DECISION_LABEL.get(d["decision"], d["decision"]),
            "、".join(chgs) if chgs else "—", "、".join(evs) if evs else "—"))
    L.append("")
    L.append("### 表 B：修改—证据对照")
    L.append("")
    L.append("| CHG 编号 | 关联意见 | 关联证据 | 证据状态 | 位置 |")
    L.append("|---|---|---|---|---|")
    for c in changes:
        evs = c.get("evidence_ids", [])
        estat = "、".join(EVIDENCE_LABEL.get(next((e["status"] for e in evidence if e["eid"] == ev), "?"), "?") for ev in evs) or "—"
        loc = "%s 第%s行" % (c.get("section") or "?", c.get("line") or "?") if c["status"] == "applied" else "落稿失败"
        L.append("| %s | %s | %s | %s | %s |" % (
            c["chg_id"], "、".join(c.get("linked_rids", [])) or "—",
            "、".join(evs) or "—", estat, loc))
    L.append("")
    L.append("此致")
    L.append("敬礼！")
    L.append("")
    L.append("（本回复信为草案，信头与落款信息待通讯作者补全后方可提交。）")
    L.append("")
    letter_path = w(args.out, "response-letter.md", "\n".join(L))

    # ---- 3) change-locations.json ----
    locs = []
    for c in changes:
        locs.append({
            "chg_id": c["chg_id"],
            "action": c["action"],
            "status": c["status"],
            "fail_reason": c.get("fail_reason") or None,
            "section": c.get("section"),
            "line": c.get("line"),
            "anchor_excerpt": (c.get("anchor") or "")[:80],
            "linked_rids": c.get("linked_rids", []),
            "evidence_ids": c.get("evidence_ids", []),
        })
    w(args.out, "change-locations.json",
      json.dumps({"case_id": case_id, "generated_at": now, "locations": locs},
                 ensure_ascii=False, indent=2))

    # ---- 4) evidence-checklist.json ----
    ev_list = []
    for e in evidence:
        eid = e["eid"]
        linked_chgs = eid_to_chgs.get(eid, [])
        linked_rids = sorted({rid for c in changes if c["chg_id"] in linked_chgs
                              for rid in c.get("linked_rids", [])})
        ev_list.append({
            "eid": eid,
            "description": e.get("description", ""),
            "status": e.get("status", "pending"),
            "status_label": EVIDENCE_LABEL.get(e.get("status", "pending"), e.get("status", "")),
            "note": e.get("note", ""),
            "linked_rids": e.get("linked_rids", linked_rids),
            "linked_chgs": linked_chgs,
        })
    w(args.out, "evidence-checklist.json",
      json.dumps({"case_id": case_id, "generated_at": now,
                  "summary": {k: sum(1 for e in ev_list if e["status"] == k) for k in EVIDENCE_LABEL},
                  "evidence": ev_list}, ensure_ascii=False, indent=2))

    # ---- 5) change_record.md ----
    R = []
    R.append("# 修改记录（change record）")
    R.append("")
    R.append("- 案例：%s" % case_id)
    R.append("- 生成时间：%s" % now)
    R.append("- 落稿状态：%s（%d/%d 成功）" % (
        report.get("status", "?"), report.get("applied", len(applied)), report.get("total_edits", len(changes))))
    R.append("")
    if warnings:
        R.append("## 一致性警告")
        R.append("")
        for wr in warnings:
            R.append("- ⚠ %s" % wr)
        R.append("")
    R.append("## 逐条修改")
    for c in changes:
        R.append("")
        R.append("### %s（%s，%s）" % (c["chg_id"], ACTION_LABEL.get(c["action"], c["action"]), c["status"]))
        R.append("")
        R.append("- 关联意见：%s" % ("、".join(c.get("linked_rids", [])) or "—"))
        R.append("- 关联证据：%s" % ("、".join(c.get("evidence_ids", [])) or "—"))
        R.append("- 位置：%s" % ("%s 第%s行" % (c.get("section"), c.get("line")) if c["status"] == "applied" else "落稿失败：" + c.get("fail_reason", "")))
        R.append("- 修改理由：%s" % (c.get("reason") or "—"))
        R.append("")
        R.append("**修改前（before）：**")
        R.append("")
        R.append("```text")
        R.append(c.get("old_text") or "（新增，无原文）")
        R.append("```")
        R.append("")
        R.append("**修改后（after）：**")
        R.append("")
        R.append("```text")
        R.append(c.get("new_text") or ("（删除）" if c["action"] == "delete" else "（未落稿）"))
        R.append("```")
    R.append("")
    if uncertainties:
        R.append("## 不确定性")
        R.append("")
        for u in uncertainties:
            R.append("- %s" % u)
        R.append("")
    w(args.out, "change_record.md", "\n".join(R))

    print("forge_pack: -> %s" % args.out)
    print("  revised-manuscript.md / response-letter.md / change-locations.json / "
          "evidence-checklist.json / change_record.md")
    if warnings:
        print("  warnings: %d（见 change_record.md）" % len(warnings))
    return 0


if __name__ == "__main__":
    sys.exit(main())
