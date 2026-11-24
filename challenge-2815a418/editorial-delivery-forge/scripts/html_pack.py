#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""html_pack.py — 自包含 HTML 审查包生成器。

生成单文件、零外部依赖的 review_pack.html，供编辑/评审一键目检：
  - 头部：案例信息 + 状态徽标（落稿状态、裁决统计、证据统计）；
  - 改动卡片：每条 CHG 一张卡（before/after 对照 + 定位 + 对应子要求），带 id 锚点；
  - 覆盖矩阵：子要求 R#.# × 裁决 × 证据状态 × 修改定位（可点击跳转到改动卡片）；
  - 证据清单表；不确定性列表。

仅依赖 Python 3 标准库。

用法：
  python3 html_pack.py --work /app/work --out /app/output [--case /input/case.json]
"""
import argparse
import html
import json
import os
import sys
from datetime import datetime, timezone

DECISION_LABEL = {"accept": "接受", "partial": "部分接受", "decline": "婉拒", "unable": "无法完成"}
DECISION_CLASS = {"accept": "ok", "partial": "warn", "decline": "muted", "unable": "bad"}
EVIDENCE_LABEL = {"provided": "已提供", "pending": "待补", "impossible": "无法提供"}
EVIDENCE_CLASS = {"provided": "ok", "pending": "warn", "impossible": "bad"}
ACTION_LABEL = {"replace": "替换", "insert_after": "后插", "insert_before": "前插", "delete": "删除"}

CSS = """
:root{--ok:#1a7f37;--warn:#9a6700;--bad:#cf222e;--muted:#57606a;--line:#d0d7de;--bg:#f6f8fa}
*{box-sizing:border-box}
body{font-family:-apple-system,"PingFang SC","Hiragino Sans GB","Noto Sans CJK SC","Microsoft YaHei",sans-serif;
 margin:0;background:var(--bg);color:#1f2328;line-height:1.65}
.wrap{max-width:980px;margin:0 auto;padding:28px 20px 80px}
h1{font-size:22px;border-bottom:2px solid var(--line);padding-bottom:8px}
h2{font-size:17px;margin-top:36px;border-left:4px solid #0969da;padding-left:10px}
.meta{color:var(--muted);font-size:13px}
.badge{display:inline-block;padding:2px 10px;border-radius:12px;font-size:12px;font-weight:600;margin:2px 4px 2px 0;border:1px solid}
.badge.ok{color:var(--ok);border-color:var(--ok);background:#dafbe1}
.badge.warn{color:var(--warn);border-color:var(--warn);background:#fff8c5}
.badge.bad{color:var(--bad);border-color:var(--bad);background:#ffebe9}
.badge.muted{color:var(--muted);border-color:var(--muted);background:#eaeef2}
table{border-collapse:collapse;width:100%;font-size:13px;background:#fff;margin:10px 0}
th,td{border:1px solid var(--line);padding:6px 10px;text-align:left;vertical-align:top}
th{background:#f0f3f6}
.card{background:#fff;border:1px solid var(--line);border-radius:8px;padding:14px 18px;margin:14px 0}
.card h3{margin:0 0 6px;font-size:15px}
.card .loc{font-size:12px;color:var(--muted)}
.diff{display:grid;grid-template-columns:1fr 1fr;gap:10px;margin-top:10px}
.diff .col{border:1px solid var(--line);border-radius:6px;padding:8px 10px;font-size:13px;white-space:pre-wrap;word-break:break-all}
.diff .before{background:#ffebe9}
.diff .after{background:#dafbe1}
.diff .tag{font-size:11px;font-weight:700;color:var(--muted)}
a{color:#0969da;text-decoration:none}
a:hover{text-decoration:underline}
ul.unc{background:#fff8c5;border:1px solid #d4a72c;border-radius:8px;padding:10px 14px 10px 32px}
.notice{background:#ddf4ff;border:1px solid #54aeff;border-radius:8px;padding:10px 14px;font-size:13px;margin:12px 0}
"""


def load_json(path, default=None):
    if not path or not os.path.exists(path):
        return default
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def esc(s):
    return html.escape(str(s if s is not None else ""))


def badge(label, cls):
    return '<span class="badge %s">%s</span>' % (cls, esc(label))


def main():
    ap = argparse.ArgumentParser(description="生成自包含 HTML 审查包")
    ap.add_argument("--work", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--case", default=None)
    args = ap.parse_args()

    decisions = load_json(os.path.join(args.work, "decisions.json"), {})
    changes = load_json(os.path.join(args.work, "changes.json"), {"changes": []})["changes"]
    report = load_json(os.path.join(args.work, "apply_report.json"), {})
    locs = load_json(os.path.join(args.out, "change-locations.json"), {}).get("locations", [])
    ev_doc = load_json(os.path.join(args.out, "evidence-checklist.json"), {"evidence": []})
    case = load_json(args.case, {}) if args.case else {}

    case_id = decisions.get("case_id") or case.get("case_id") or "UNKNOWN-CASE"
    title = decisions.get("manuscript_title", "（稿件标题待填）")
    rds = decisions.get("reviewer_decisions", [])
    evidence = ev_doc.get("evidence", [])
    uncertainties = decisions.get("uncertainties", [])
    loc_by_chg = {l["chg_id"]: l for l in locs}
    ev_by_id = {e["eid"]: e for e in evidence}
    rid_to_chgs = {}
    for c in changes:
        for rid in c.get("linked_rids", []):
            rid_to_chgs.setdefault(rid, []).append(c)

    P = []
    P.append("<!DOCTYPE html>")
    P.append('<html lang="zh"><head><meta charset="utf-8">')
    P.append('<meta name="viewport" content="width=device-width,initial-scale=1">')
    P.append("<title>审查包 review_pack — %s</title>" % esc(case_id))
    P.append("<style>%s</style></head><body><div class=\"wrap\">" % CSS)

    # ---- 头部 ----
    P.append("<h1>审稿修改审查包 review_pack</h1>")
    P.append('<p class="meta">案例：<b>%s</b> ｜ 稿件：%s ｜ 生成时间：%s<br>' % (
        esc(case_id), esc(title), esc(datetime.now(timezone.utc).isoformat())))
    P.append("本页为自包含审查文件（无外部资源）。声明：基于组织方给出的<b>意见摘要</b>修订，"
             "不代表审稿人原文逐字要求；未补做任何真实实验；不代表编辑部已接收。</p>")
    n_dec = {k: sum(1 for d in rds if d["decision"] == k) for k in DECISION_LABEL}
    n_ev = {k: sum(1 for e in evidence if e["status"] == k) for k in EVIDENCE_LABEL}
    applied = sum(1 for c in changes if c["status"] == "applied")
    P.append("<p>")
    P.append(badge("落稿 %s：%d/%d" % (report.get("status", "?"), applied, len(changes)),
                   "ok" if applied == len(changes) else "warn"))
    for k in ("accept", "partial", "decline", "unable"):
        if n_dec[k]:
            P.append(badge("%s %d" % (DECISION_LABEL[k], n_dec[k]), DECISION_CLASS[k]))
    for k in ("provided", "pending", "impossible"):
        if n_ev[k]:
            P.append(badge("证据%s %d" % (EVIDENCE_LABEL[k], n_ev[k]), EVIDENCE_CLASS[k]))
    P.append("</p>")

    # ---- 覆盖矩阵 ----
    P.append("<h2>覆盖矩阵（子要求 × 裁决 × 证据状态 × 定位）</h2>")
    P.append('<table><tr><th>子要求</th><th>意见要点</th><th>裁决</th><th>关联修改（点击跳转）</th><th>证据状态</th></tr>')
    for d in rds:
        chgs = rid_to_chgs.get(d["rid"], [])
        chg_links = " ".join('<a href="#chg-%s">%s</a>' % (esc(c["chg_id"]), esc(c["chg_id"]))
                             for c in chgs) or "—"
        evs = sorted({e for c in chgs for e in c.get("evidence_ids", [])})
        ev_html = " ".join(badge("%s %s" % (ev, EVIDENCE_LABEL.get(ev_by_id.get(ev, {}).get("status", "?"), "?")),
                                 EVIDENCE_CLASS.get(ev_by_id.get(ev, {}).get("status", ""), "muted"))
                           for ev in evs) or "—"
        P.append("<tr><td><b>%s</b></td><td>%s</td><td>%s</td><td>%s</td><td>%s</td></tr>" % (
            esc(d["rid"]), esc(d.get("summary", "")),
            badge(DECISION_LABEL.get(d["decision"], d["decision"]), DECISION_CLASS.get(d["decision"], "muted")),
            chg_links, ev_html))
    P.append("</table>")

    # ---- 改动卡片 ----
    P.append("<h2>改动卡片（before / after 对照）</h2>")
    for c in changes:
        loc = loc_by_chg.get(c["chg_id"], {})
        loc_txt = ("%s 第%s行" % (loc.get("section"), loc.get("line"))
                   if c["status"] == "applied" else "落稿失败：%s" % c.get("fail_reason", ""))
        P.append('<div class="card" id="chg-%s">' % esc(c["chg_id"]))
        P.append("<h3>%s ｜ %s ｜ %s</h3>" % (
            esc(c["chg_id"]), esc(ACTION_LABEL.get(c["action"], c["action"])),
            badge("已落实" if c["status"] == "applied" else "待处理",
                  "ok" if c["status"] == "applied" else "bad")))
        P.append('<div class="loc">定位：%s ｜ 子要求：%s ｜ 证据：%s</div>' % (
            esc(loc_txt), esc("、".join(c.get("linked_rids", [])) or "—"),
            esc("、".join(c.get("evidence_ids", [])) or "—")))
        if c.get("reason"):
            P.append('<div class="loc">修改理由：%s</div>' % esc(c["reason"]))
        P.append('<div class="diff"><div class="col before"><span class="tag">BEFORE（修改前）</span><br>%s</div>'
                 '<div class="col after"><span class="tag">AFTER（修改后）</span><br>%s</div></div>' % (
                     esc(c.get("old_text") or "（新增，无原文）"),
                     esc(c.get("new_text") or ("（删除）" if c["action"] == "delete" else "（未落稿）"))))
        P.append("</div>")

    # ---- 证据清单 ----
    P.append("<h2>证据清单（未到位证据如实标注）</h2>")
    P.append('<table><tr><th>EV 编号</th><th>描述</th><th>状态</th><th>关联子要求</th><th>关联修改</th><th>备注</th></tr>')
    for e in evidence:
        P.append("<tr><td><b>%s</b></td><td>%s</td><td>%s</td><td>%s</td><td>%s</td><td>%s</td></tr>" % (
            esc(e["eid"]), esc(e.get("description", "")),
            badge(EVIDENCE_LABEL.get(e["status"], e["status"]), EVIDENCE_CLASS.get(e["status"], "muted")),
            esc("、".join(e.get("linked_rids", [])) or "—"),
            " ".join('<a href="#chg-%s">%s</a>' % (esc(x), esc(x)) for x in e.get("linked_chgs", [])) or "—",
            esc(e.get("note", ""))))
    P.append("</table>")

    # ---- 不确定性 ----
    P.append("<h2>不确定性</h2>")
    if uncertainties:
        P.append('<ul class="unc">')
        for u in uncertainties:
            P.append("<li>%s</li>" % esc(u))
        P.append("</ul>")
    else:
        P.append('<p class="meta">（无）</p>')
    P.append('<p class="meta">生成工具：editorial-delivery-forge / html_pack.py ｜ 产物与 revised-manuscript.md、'
             'response-letter.md、change-locations.json、evidence-checklist.json 同源生成，编号一致。</p>')
    P.append("</div></body></html>")

    os.makedirs(args.out, exist_ok=True)
    out_path = os.path.join(args.out, "review_pack.html")
    with open(out_path, "w", encoding="utf-8") as f:
        f.write("\n".join(P))
    print("html_pack: -> %s（改动卡片 %d，子要求 %d，证据 %d）" % (out_path, len(changes), len(rds), len(evidence)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
