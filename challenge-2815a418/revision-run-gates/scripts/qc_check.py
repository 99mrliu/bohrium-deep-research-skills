#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""qc_check.py — 五维机器回检（外加产物存在性前置检查与材料外数字警告）。

维度：
  1. coverage   子要求覆盖：回复信逐条答到每个 req_id
  2. anchor     锚点 quote 逐字命中基线（落稿失败即失败）
  3. revised    修订稿确有改动且与 changes.json 对齐（标记与替换文本都在）
  4. chg        CHG 编号三方一致：修订稿标记 == changes.json == 回复信
  5. evidence   证据状态合法；action=cannot 强制 无法补做/待核实 且回复信如实说明「无法」
  +. tone       禁用语气词扫描（不得冒称逐字要求/补做实验/已接收等）
  +. numbers    材料外数字警告（warn，不阻断）

写 qc_report.json；任一 fail → overall=fail，exit 1。仅用 Python 3 标准库。
"""
import argparse
import datetime
import json
import os
import re
import sys

FORBIDDEN = ["编辑部已接收", "已被接收", "审稿人逐字要求", "已补做实验", "补做了实验",
             "新增实验表明", "原作者已完成修改"]
ALLOWED_EVIDENCE = {"已落实", "部分落实", "无法补做", "待核实"}
NUM_RE = re.compile(r"\d+(?:\.\d+)?%?")
MARK_RE = re.compile(r"⟦(CHG-\d{3})⟧")


def load_text(p):
    if not p or not os.path.exists(p):
        return None
    with open(p, encoding="utf-8") as f:
        return f.read()


def load_json(p):
    t = load_text(p)
    if t is None:
        return None
    try:
        return json.loads(t)
    except Exception:
        return None


def finish(out, checks):
    overall = "fail" if any(c["status"] == "fail" for c in checks) else "pass"
    warnings = [c["details"] for c in checks if c["status"] == "warn"]
    report = {"overall": overall, "checks": checks, "warnings": warnings,
              "ts": datetime.datetime.now().isoformat(timespec="seconds")}
    d = os.path.dirname(out)
    if d:
        os.makedirs(d, exist_ok=True)
    tmp = out + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
        f.write("\n")
    os.replace(tmp, out)
    for c in checks:
        print("[%s] %s — %s" % (c["status"].upper(), c["name"], c["details"]))
    print("QC-OVERALL: %s" % overall.upper())
    return 0 if overall == "pass" else 1


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    for k in ["baseline", "revised", "letter", "changes", "decisions", "evidence", "out"]:
        ap.add_argument("--" + k, required=True)
    a = ap.parse_args(argv)

    checks = []

    def rec(name, ok, details, level="fail"):
        checks.append({"name": name, "status": "pass" if ok else level,
                       "details": details if isinstance(details, (str, list)) else str(details)})

    baseline = load_text(a.baseline)
    revised = load_text(a.revised)
    letter = load_text(a.letter)
    changes = load_json(a.changes)
    decisions = load_json(a.decisions)
    evidence = load_json(a.evidence)

    missing = [k for k, v in [("baseline", baseline), ("revised", revised),
                              ("letter", letter), ("changes", changes),
                              ("decisions", decisions), ("evidence", evidence)] if v is None]
    rec("artifacts_present", not missing,
        ("缺失：" + ", ".join(missing)) if missing else "全部存在")
    if missing:
        return finish(a.out, checks)

    judgments = decisions.get("judgments", [])
    applied = changes.get("applied", [])
    failures = changes.get("failures", [])

    # 1 子要求覆盖
    miss = [j.get("req_id") for j in judgments
            if j.get("req_id") and j["req_id"] not in letter]
    rec("coverage_子要求逐条覆盖", not miss,
        ("回复信未覆盖：%s" % miss) if miss
        else "%d 条子要求均在回复信中出现" % len(judgments))

    # 2 锚点逐字命中基线（apply 阶段的失败即锚点未命中/不唯一）
    bad = ["%s(%s)" % (f.get("chg_id"), f.get("error")) for f in failures]
    rec("anchor_逐字命中", not bad,
        ("落稿失败：%s" % bad) if bad else "全部锚点逐字唯一命中基线")

    # 3 修订稿确有改动且与 changes.json 对齐
    probs = []
    if applied and revised.strip() == baseline.strip():
        probs.append("存在已声明修改但修订稿与基线完全一致")
    for c in applied:
        if ("⟦%s⟧" % c["chg_id"]) not in revised:
            probs.append("%s 的 CHG 标记不在修订稿中" % c["chg_id"])
        if c.get("replacement", "").rstrip() not in revised:
            probs.append("%s 的 replacement 不在修订稿中" % c["chg_id"])
    rec("revised_确有改动且对齐", not probs, probs or "修订稿与 changes.json 对齐")

    # 4 CHG 编号三方一致
    m_rev = set(MARK_RE.findall(revised))
    m_let = set(MARK_RE.findall(letter))
    m_chg = {c["chg_id"] for c in applied}
    ok4 = (m_rev == m_chg) and (m_let == m_chg)
    rec("chg_三方一致", ok4, "revised=%s changes=%s letter=%s"
        % (sorted(m_rev), sorted(m_chg), sorted(m_let)))

    # 5 证据状态合法（补做类强制）
    probs5 = []
    ev_items = evidence.get("items", [])
    ev_by_req = {i.get("req_id"): i for i in ev_items}
    for i in ev_items:
        if i.get("status") not in ALLOWED_EVIDENCE:
            probs5.append("%s 证据状态非法：%r" % (i.get("req_id"), i.get("status")))
    for j in judgments:
        if j.get("action") == "cannot":
            rid = j.get("req_id")
            it = ev_by_req.get(rid)
            if not it or it.get("status") not in ("无法补做", "待核实"):
                probs5.append("%s action=cannot 但证据状态不是 无法补做/待核实" % rid)
            idx = letter.find(rid or "\x00")
            section = letter[idx:idx + 400] if idx >= 0 else ""
            if "无法" not in section:
                probs5.append("%s 回复信对应段落未如实说明「无法」" % rid)
    rec("evidence_状态合法", not probs5, probs5 or "证据状态全部合法")

    # 6 禁用语气红线
    hits = [p for p in FORBIDDEN if (p in revised) or (p in letter)]
    rec("tone_禁用语气", not hits,
        ("命中禁用表述：%s" % hits) if hits else "未命中红线表述")

    # 7 材料外数字（警告；先剔除 CHG 标记自身的数字）
    revised_clean = MARK_RE.sub("", revised)
    extra_nums = sorted(set(NUM_RE.findall(revised_clean)) - set(NUM_RE.findall(baseline)))
    rec("numbers_材料外数字", not extra_nums,
        ("修订稿出现基线外数字：%s（需人工核对来源）" % extra_nums) if extra_nums
        else "无材料外数字", level="warn")

    return finish(a.out, checks)


if __name__ == "__main__":
    sys.exit(main())
