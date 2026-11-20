#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""risk_grade.py — 结论风险分级规则引擎。

对每条结论按触发规则打分，输出 confidence grade（high/medium/low）、
触发规则清单与人工复核清单。规则口径的人读版本见 rules/risk_grading.md。

输入：结论清单 JSON：
{"conclusions": [{
    "claim_id": "C1",
    "statement": "...",
    "fields_present": ["quote", "locator", "status", ...],   # 已具备字段
    "evidence_verified": true/false,                          # 引文是否已过 quote_audit
    "match_mode": "verbatim"|"ocr_tolerant"|null,
    "ocr_uncertain": true/false,
    "status_value": "授权|失效|...|未知"|null,
    "status_query_date": "YYYY-MM-DD"|null,
    "family_scope_known": true/false,                         # 同族口径是否明确
    "corpus_coverage": "complete"|"partial"|"unknown",        # 语料覆盖
    "source_count": 1                                         # 独立来源数
}]}

触发规则与分值：
  R-G1 字段缺失                  +2/缺项（至多 +4）
  R-G2 状态过期（查询日期>180天） +2；90–180 天 +1
  R-G3 同族口径不明              +1
  R-G4 语料覆盖不全              partial +1 / unknown +2
  R-G5 OCR 不确定                +1（ocr_uncertain 或 match_mode=ocr_tolerant）
  R-G6 单一来源                  +1
  R-G7 引文未核验                +3 且强制 low
  R-G8 法律状态未知              +2
分级：0 分 high；1–3 分 medium；≥4 分或 R-G7 触发 low。

CLI：grade --conclusions FILE --report OUT.json [--checklist-md OUT.md]
退出码：0 成功；1 输入非法。仅依赖标准库。
"""
import argparse
import datetime
import json
import sys
from pathlib import Path

REQUIRED_FIELDS = ["quote", "locator", "source_kind", "status", "query_date", "sources"]

RULE_DESC = {
    "R-G1": "字段缺失：结论缺少必需字段",
    "R-G2": "状态过期：法律状态查询日期距今过久",
    "R-G3": "同族口径不明：观察到的链接不构成完整同族，未声明口径",
    "R-G4": "语料覆盖不全：有限语料未覆盖全部目标范围",
    "R-G5": "OCR 不确定：引文来自 OCR 容忍匹配或 OCR 质量存疑",
    "R-G6": "单一来源：结论仅有一个独立来源支撑",
    "R-G7": "引文未核验：结论所附引文未通过确定性回核",
    "R-G8": "法律状态未知：当前官方法律状态未知，结论带不确定性",
}

REVIEW_ACTIONS = {
    "R-G1": "补齐缺失字段后再出结论；无法补齐的在 uncertainty 中声明",
    "R-G2": "重新查询官方登记簿，更新 query_date 与 staleness 备注",
    "R-G3": "在结论中写明'仅观察到的链接，不构成完整同族'，必要时人工核查 INPADOC",
    "R-G4": "列出未覆盖的语料缺口（如未提供的同族成员/对比文件），结论限缩到已覆盖范围",
    "R-G5": "回到原件（PDF 渲染页）人工比对 OCR 存疑引文",
    "R-G6": "补充第二独立来源；补不到则在结论中标注'单一来源'",
    "R-G7": "先跑 scripts/quote_audit.py 修复引文，再重新分级",
    "R-G8": "按 rules/legal_status_protocol.md 执行登记优先查询；仍未知则保持'未知'措辞",
}


def _parse_date(s):
    try:
        return datetime.date.fromisoformat(s)
    except (ValueError, TypeError):
        return None


def grade_conclusion(c, today=None):
    """对单条结论打分。返回 {score, grade, triggered:[{rule,desc,points}], review_checklist}。"""
    today = today or datetime.date.today()
    triggered = []

    # R-G1 字段缺失
    present = set(c.get("fields_present") or [])
    missing = [f for f in REQUIRED_FIELDS if f not in present]
    if missing:
        pts = min(4, 2 * len(missing))
        triggered.append({"rule": "R-G1", "desc": RULE_DESC["R-G1"] + "（缺: %s）" % ",".join(missing),
                          "points": pts})

    # R-G2 状态过期
    qd = _parse_date(c.get("status_query_date"))
    if c.get("status_query_date") is not None:
        if qd is None:
            triggered.append({"rule": "R-G2", "desc": RULE_DESC["R-G2"] + "（日期非法）", "points": 2})
        else:
            age = (today - qd).days
            if age > 180:
                triggered.append({"rule": "R-G2", "desc": RULE_DESC["R-G2"] + "（%d 天）" % age, "points": 2})
            elif age > 90:
                triggered.append({"rule": "R-G2", "desc": RULE_DESC["R-G2"] + "（%d 天）" % age, "points": 1})

    # R-G3 同族口径
    if c.get("family_scope_known") is False:
        triggered.append({"rule": "R-G3", "desc": RULE_DESC["R-G3"], "points": 1})

    # R-G4 语料覆盖
    cov = c.get("corpus_coverage")
    if cov == "partial":
        triggered.append({"rule": "R-G4", "desc": RULE_DESC["R-G4"] + "（partial）", "points": 1})
    elif cov == "unknown":
        triggered.append({"rule": "R-G4", "desc": RULE_DESC["R-G4"] + "（unknown）", "points": 2})

    # R-G5 OCR 不确定
    if c.get("ocr_uncertain") or c.get("match_mode") == "ocr_tolerant":
        triggered.append({"rule": "R-G5", "desc": RULE_DESC["R-G5"], "points": 1})

    # R-G6 单一来源
    sc = c.get("source_count")
    if isinstance(sc, int) and sc <= 1:
        triggered.append({"rule": "R-G6", "desc": RULE_DESC["R-G6"], "points": 1})

    # R-G7 引文未核验（致命）
    fatal = False
    if c.get("evidence_verified") is False:
        triggered.append({"rule": "R-G7", "desc": RULE_DESC["R-G7"], "points": 3})
        fatal = True

    # R-G8 法律状态未知
    if c.get("status_value") == "未知":
        triggered.append({"rule": "R-G8", "desc": RULE_DESC["R-G8"], "points": 2})

    score = sum(t["points"] for t in triggered)
    if fatal or score >= 4:
        grade = "low"
    elif score >= 1:
        grade = "medium"
    else:
        grade = "high"
    checklist = [REVIEW_ACTIONS[t["rule"]] for t in triggered]
    return {"score": score, "grade": grade, "triggered": triggered,
            "review_checklist": checklist}


def main(argv=None):
    ap = argparse.ArgumentParser(description="结论风险分级规则引擎")
    ap.add_argument("--conclusions", required=True, help="结论清单 JSON")
    ap.add_argument("--report", default=None, help="分级报告 JSON 输出路径")
    ap.add_argument("--checklist-md", default=None, help="人工复核清单 Markdown 输出路径")
    args = ap.parse_args(argv)

    p = Path(args.conclusions)
    if not p.exists():
        print("ERROR: 结论清单不存在: %s" % args.conclusions, file=sys.stderr)
        return 1
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        print("ERROR: JSON 解析失败: %s" % e, file=sys.stderr)
        return 1
    conclusions = data.get("conclusions")
    if not isinstance(conclusions, list):
        print("ERROR: 必须含 conclusions 数组", file=sys.stderr)
        return 1

    graded = []
    for c in conclusions:
        if not isinstance(c, dict) or not c.get("claim_id"):
            print("ERROR: 结论缺少 claim_id: %r" % (c,), file=sys.stderr)
            return 1
        g = grade_conclusion(c)
        graded.append({
            "claim_id": c["claim_id"],
            "statement": c.get("statement"),
            "score": g["score"],
            "grade": g["grade"],
            "triggered_rules": g["triggered"],
            "review_checklist": g["review_checklist"],
        })
        rules = ",".join(t["rule"] for t in g["triggered"]) or "无"
        print("[%s] %s score=%d 触发规则: %s" % (g["grade"].upper(), c["claim_id"], g["score"], rules))

    report = {"conclusions_file": str(args.conclusions),
              "grading_date": datetime.date.today().isoformat(),
              "total": len(graded),
              "grades": {t: sum(1 for g in graded if g["grade"] == t)
                         for t in ("high", "medium", "low")},
              "results": graded}
    if args.report:
        Path(args.report).write_text(json.dumps(report, ensure_ascii=False, indent=2),
                                     encoding="utf-8")
        print("分级报告已写入: %s" % args.report)

    if args.checklist_md:
        lines = ["# 人工复核清单（review_checklist）", "",
                 "> 由 risk_grade.py 自动生成；分级日期 %s。" % report["grading_date"], ""]
        for g in graded:
            if not g["review_checklist"]:
                continue
            lines.append("## %s（grade=%s, score=%d）" % (g["claim_id"], g["grade"], g["score"]))
            for item in g["review_checklist"]:
                lines.append("- [ ] %s" % item)
            lines.append("")
        if all(not g["review_checklist"] for g in graded):
            lines.append("全部结论 grade=high，无强制复核项。")
        Path(args.checklist_md).write_text("\n".join(lines), encoding="utf-8")
        print("人工复核清单已写入: %s" % args.checklist_md)
    return 0


if __name__ == "__main__":
    sys.exit(main())
