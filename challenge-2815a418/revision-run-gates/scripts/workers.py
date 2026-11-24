#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""workers.py — 确定性工人函数（不调用模型）：材料清单/锚点图、判断骨架、锚点落稿、
回复信骨架、派生产物（change-locations / evidence-checklist / change_record）。
被 run_gates.py 作为库调用；仅使用 Python 3 标准库。"""
import json
import os
import re

ALLOWED_ACTIONS = ["revise", "clarify", "cannot", "reject"]
EVIDENCE_STATUSES = ["已落实", "部分落实", "无法补做", "待核实"]
MARK_FMT = "⟦{}⟧"
_CHG_RE = re.compile(r"^CHG-\d{3}$")
_HEAD_RE = re.compile(r"^#{1,6}\s*(意见\s*\d+.*)$")
_ITEM_RE = re.compile(r"^\s*[-*]\s*(\d+\.\d+)\s*[：:、]?\s*(.+)$")


def read_text(p):
    with open(p, encoding="utf-8") as f:
        return f.read()


def write_text(p, s):
    d = os.path.dirname(p)
    if d:
        os.makedirs(d, exist_ok=True)
    tmp = p + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(s)
    os.replace(tmp, p)


def write_json(p, obj):
    write_text(p, json.dumps(obj, ensure_ascii=False, indent=2) + "\n")


def read_json_opt(p):
    try:
        with open(p, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


# ---------------------------------------------------------------- 材料与锚点图
def build_anchor_map(text):
    """把基线稿拆成带行号锚点的清单，供 Agent 选取逐字锚点。"""
    anchors = []
    for i, ln in enumerate(text.splitlines(), 1):
        s = ln.strip()
        if not s:
            continue
        anchors.append({
            "anchor_id": "L%03d" % i,
            "kind": "heading" if s.startswith("#") else "para",
            "preview": s[:60],
        })
    return anchors


# ---------------------------------------------------------------- 意见拆解
def parse_requirements(text):
    """把 reviewer-comments.md 拆成子要求列表：[{req_id, block, text}]。
    识别 '## 意见 N' 分块与 '- X.Y …' 子要求行。"""
    reqs = []
    cur = "未分块"
    for ln in text.splitlines():
        h = _HEAD_RE.match(ln.strip())
        if h:
            cur = h.group(1).strip()
            continue
        m = _ITEM_RE.match(ln)
        if m:
            reqs.append({"req_id": m.group(1), "block": cur, "text": m.group(2).strip()})
    return reqs


def write_gate_skeletons(work, reqs):
    """生成 decisions.json / edits.json 判断骨架；已存在（Agent 已填）则不覆盖。"""
    dpath = os.path.join(work, "decisions.json")
    epath = os.path.join(work, "edits.json")
    if not os.path.exists(dpath):
        write_json(dpath, {
            "_filled": False,
            "_说明": "人判门文件：逐条为每个 req_id 填 action(revise/clarify/cannot/reject)、"
                     "rationale（理由）、evidence_status（已落实/部分落实/无法补做/待核实）。",
            "judgments": [
                {"req_id": r["req_id"], "意见摘要": r["text"][:80],
                 "action": "", "rationale": "", "evidence_status": ""}
                for r in reqs
            ],
        })
    if not os.path.exists(epath):
        write_json(epath, {
            "_filled": False,
            "_说明": "落稿文件：action=revise 的子要求须至少一条 edit。"
                     "anchor_quote 必须是基线稿中逐字且唯一的原文片段；"
                     "replacement 为替换后的新文本（脚本自动追加 ⟦CHG-xxx⟧ 标记）。",
            "_edit_template": {"chg_id": "CHG-001", "req_id": "1.1",
                               "anchor_quote": "基线原文逐字片段", "replacement": "新文本"},
            "edits": [],
        })
    return dpath, epath


def check_decisions_filled(work):
    """判断门校验：decisions.json 与 edits.json 是否已填好。返回 (ok, missing)。"""
    missing = []
    d = read_json_opt(os.path.join(work, "decisions.json"))
    e = read_json_opt(os.path.join(work, "edits.json"))
    if d is None:
        return False, ["decisions.json 缺失或不是合法 JSON"]
    if e is None:
        return False, ["edits.json 缺失或不是合法 JSON"]
    judgments = d.get("judgments") or []
    if not judgments:
        missing.append("decisions.json 的 judgments 为空")
    for j in judgments:
        rid = j.get("req_id", "?")
        act = j.get("action")
        if act not in ALLOWED_ACTIONS:
            missing.append("%s: action 未填或非法（%r），允许 %s" % (rid, act, ALLOWED_ACTIONS))
        if not (j.get("rationale") or "").strip():
            missing.append("%s: rationale 为空" % rid)
        if act == "cannot" and j.get("evidence_status") not in ("无法补做", "待核实"):
            missing.append("%s: action=cannot 时 evidence_status 须为 无法补做/待核实" % rid)
    edits = e.get("edits") or []
    seen = set()
    for ed in edits:
        cid = ed.get("chg_id", "")
        if not _CHG_RE.match(cid):
            missing.append("edit 的 chg_id 非法（须 CHG-NNN）：%r" % cid)
        if cid in seen:
            missing.append("chg_id 重复：%s" % cid)
        seen.add(cid)
        if not (ed.get("anchor_quote") or ""):
            missing.append("%s: anchor_quote 为空" % cid)
        if not (ed.get("replacement") or ""):
            missing.append("%s: replacement 为空" % cid)
    known = {j.get("req_id") for j in judgments}
    edit_reqs = {ed.get("req_id") for ed in edits}
    for j in judgments:
        if j.get("action") == "revise" and j.get("req_id") not in edit_reqs:
            missing.append("%s: action=revise 但 edits.json 无对应 edit" % j.get("req_id"))
    for ed in edits:
        if ed.get("req_id") not in known:
            missing.append("%s: req_id %r 不在 decisions.json 中" % (ed.get("chg_id"), ed.get("req_id")))
    return (not missing), missing


# ---------------------------------------------------------------- 锚点落稿
def apply_edits(baseline_text, edits):
    """逐字唯一匹配落稿。返回 (revised_text, changes)。
    单个 edit 失败不阻断其余 edit，失败记入 changes['failures']。"""
    revised = baseline_text
    applied, failures = [], []
    for ed in edits:
        cid = ed.get("chg_id", "?")
        anchor = ed.get("anchor_quote", "")
        repl = ed.get("replacement", "")
        if baseline_text.count(anchor) == 0:
            failures.append({"chg_id": cid, "req_id": ed.get("req_id"),
                             "anchor_quote": anchor, "error": "ANCHOR_NOT_FOUND"})
            continue
        n = revised.count(anchor)
        if n != 1:
            failures.append({"chg_id": cid, "req_id": ed.get("req_id"),
                             "anchor_quote": anchor, "error": "ANCHOR_NOT_UNIQUE",
                             "occurrences": n})
            continue
        revised = revised.replace(anchor, repl.rstrip() + " " + MARK_FMT.format(cid), 1)
        applied.append({"chg_id": cid, "req_id": ed.get("req_id"),
                        "anchor_quote": anchor, "replacement": repl, "status": "applied"})
    return revised, {"applied": applied, "failures": failures}


# ---------------------------------------------------------------- 回复信骨架
_ACTION_LABEL = {"revise": "已修改", "clarify": "已澄清",
                 "cannot": "无法补做", "reject": "不采纳（附理由）"}


def build_letter(case_id, judgments, changes, reqs):
    """从 decisions + changes 生成逐条回复信骨架（Agent 可润色，不得改变事实陈述）。"""
    chg_by_req = {}
    for c in changes.get("applied", []):
        chg_by_req.setdefault(c.get("req_id"), []).append(c["chg_id"])
    req_text = {r["req_id"]: r["text"] for r in reqs}
    lines = [
        "# 审稿回复信（草案）", "",
        "case_id: %s" % case_id, "",
        "尊敬的编辑与审稿人：", "",
        "以下为针对审稿意见的逐条回复草案。本信仅基于给定基线稿与意见摘要生成，"
        "不代表补做了任何新实验，也不代表编辑部的任何接收决定。", "",
    ]
    for j in judgments:
        rid = j.get("req_id", "?")
        act = j.get("action", "?")
        lines.append("## 意见 %s" % rid)
        lines.append("- 意见摘要：%s" % req_text.get(rid, j.get("意见摘要", "")))
        lines.append("- 处理决定：%s" % _ACTION_LABEL.get(act, act))
        if act == "cannot":
            lines.append("- 说明：本次修订无法完成该要求（理由如下），"
                         "已在交付物的 uncertainty 中如实披露。")
        lines.append("- 理由：%s" % (j.get("rationale") or ""))
        ids = chg_by_req.get(rid, [])
        if ids:
            lines.append("- 修改定位：" + "、".join(MARK_FMT.format(i) for i in ids))
        lines.append("")
    lines.append("（草案完。Agent 可润色措辞，但不得改变处理决定与事实陈述。）")
    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------- 派生产物
def derive_change_locations(changes, baseline_text):
    items = []
    for c in changes.get("applied", []):
        idx = baseline_text.find(c["anchor_quote"])
        items.append({
            "chg_id": c["chg_id"], "req_id": c.get("req_id"),
            "baseline_line": (baseline_text[:idx].count("\n") + 1) if idx >= 0 else None,
            "anchor_preview": c["anchor_quote"][:40],
            "marker": MARK_FMT.format(c["chg_id"]),
        })
    return {"items": items, "failures": changes.get("failures", [])}


def derive_evidence_checklist(judgments, changes):
    applied_reqs = {c.get("req_id") for c in changes.get("applied", [])}
    items = []
    for j in judgments:
        rid, act = j.get("req_id"), j.get("action")
        if act == "cannot":
            st = "无法补做"
        elif act == "reject":
            st = "待核实"
        elif rid in applied_reqs:
            st = "已落实"
        else:
            st = j.get("evidence_status") or "部分落实"
        items.append({"req_id": rid, "action": act, "status": st,
                      "note": j.get("rationale", "")})
    return {"items": items}


def change_record_md(changes):
    lines = ["# 修改记录", "",
             "| CHG | 意见 | 锚点（基线原文，截断） | 状态 |",
             "|---|---|---|---|"]
    for c in changes.get("applied", []):
        lines.append("| %s | %s | %s… | 已落稿 |"
                     % (c["chg_id"], c.get("req_id", ""), c["anchor_quote"][:30]))
    for f in changes.get("failures", []):
        lines.append("| %s | %s | %s… | 失败：%s |"
                     % (f.get("chg_id", "?"), f.get("req_id", ""),
                        str(f.get("anchor_quote", ""))[:30], f.get("error", "")))
    return "\n".join(lines) + "\n"
