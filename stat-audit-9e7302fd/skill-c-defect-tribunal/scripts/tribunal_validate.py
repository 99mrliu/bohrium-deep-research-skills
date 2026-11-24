#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""tribunal_validate.py — 对抗裁决日志（JSONL）一致性校验与汇总。

校验 scripts 配套于 defect-tribunal-audit 技能：对裁决庭产出的 adjudication_log.jsonl
逐行检查必填字段与一致性规则，并输出"类别 × 严重度"汇总表供审查单使用。

必填字段（每条记录）：
    id, facet, category, severity, quote, location,
    defense: {q1, q2, q3, q4}, ruling, rationale

一致性规则：
    1. ruling=维持       → defense.q1..q4 必须全部非空作答；
    2. category=事实错误 → 必须有非空 internal_evidence（与指控冲突的原文内部证据）；
    3. severity=critical → 必须有非空 consequence（哪条结论将不成立）；
    4. ruling=转待复核   → 必须有非空 missing_material（所缺材料）；
    5. ruling=驳回       → rationale 必须非空（驳回依据，留痕义务）。

退出码：0 = 全部通过；1 = 存在违规或文件/解析错误（逐条列出）；2 = 命令行参数错误。
仅依赖 python3 标准库。
"""

import argparse
import json
import sys
from collections import Counter

CATEGORIES = ["事实错误", "证据不足", "规范问题", "建议", "待复核"]
SEVERITIES = ["critical", "major", "minor", "editorial"]
RULINGS = ["维持", "降级", "改类", "转待复核", "驳回"]
ACCEPTED_RULINGS = ("维持", "降级", "改类")  # 计入审查单正文/汇总表
DEFENSE_KEYS = ("q1", "q2", "q3", "q4")


def _nes(value):
    """non-empty string 判定。"""
    return isinstance(value, str) and value.strip() != ""


def validate_record(rec, lineno):
    """返回该记录的违规信息列表（空列表 = 通过）。"""
    v = []
    tag = "第%d行" % lineno
    if not isinstance(rec, dict):
        return ["%s: 记录不是 JSON 对象" % tag]

    rid = rec.get("id")
    if not _nes(rid):
        v.append("%s: 缺少必填字段 id（非空字符串）" % tag)
    else:
        tag = "%s(id=%s)" % (tag, rid)

    if not _nes(rec.get("facet")):
        v.append("%s: 缺少必填字段 facet" % tag)

    cat = rec.get("category")
    if cat not in CATEGORIES:
        v.append("%s: category 取值非法: %r（允许: %s）"
                 % (tag, cat, "/".join(CATEGORIES)))

    sev = rec.get("severity")
    if sev not in SEVERITIES:
        v.append("%s: severity 取值非法: %r（允许: %s）"
                 % (tag, sev, "/".join(SEVERITIES)))

    if not _nes(rec.get("quote")):
        v.append("%s: 缺少必填字段 quote（逐字原文引用）" % tag)
    if not _nes(rec.get("location")):
        v.append("%s: 缺少必填字段 location（原文位置）" % tag)

    defense = rec.get("defense")
    if not isinstance(defense, dict):
        v.append("%s: 缺少必填字段 defense（须为含 q1..q4 的对象）" % tag)
        defense = {}
    else:
        for k in DEFENSE_KEYS:
            if k not in defense:
                v.append("%s: defense 缺少 %s" % (tag, k))

    ruling = rec.get("ruling")
    if ruling not in RULINGS:
        v.append("%s: ruling 取值非法: %r（允许: %s）"
                 % (tag, ruling, "/".join(RULINGS)))

    rationale_ok = _nes(rec.get("rationale"))
    if not rationale_ok:
        if ruling == "驳回":
            v.append("%s: 一致性违规: ruling=驳回 必须填写 rationale（驳回依据，留痕义务）" % tag)
        else:
            v.append("%s: 缺少必填字段 rationale（一句话裁决理由）" % tag)

    # ---- 一致性规则 ----
    if ruling == "维持":
        for k in DEFENSE_KEYS:
            if not _nes(defense.get(k)):
                v.append("%s: 一致性违规: ruling=维持 要求辩护四问全部非空作答，%s 为空" % (tag, k))

    if cat == "事实错误" and not _nes(rec.get("internal_evidence")):
        v.append("%s: 一致性违规: category=事实错误 必须给出 internal_evidence（与指控冲突的原文内部证据）" % tag)

    if sev == "critical" and not _nes(rec.get("consequence")):
        v.append("%s: 一致性违规: severity=critical 必须给出 consequence（说明哪条结论将不成立）" % tag)

    if ruling == "转待复核" and not _nes(rec.get("missing_material")):
        v.append("%s: 一致性违规: ruling=转待复核 必须给出 missing_material（所缺材料）" % tag)

    return v


def render_summary(records):
    """生成汇总表文本：类别 × 严重度（仅计入 维持/降级/改类）+ 留痕计数。"""
    table = Counter()
    ruling_counts = Counter()
    n = 0
    for rec in records:
        if not isinstance(rec, dict):
            continue
        n += 1
        ruling = rec.get("ruling")
        ruling_counts[ruling] += 1
        cat, sev = rec.get("category"), rec.get("severity")
        if ruling in ACCEPTED_RULINGS and cat in CATEGORIES and sev in SEVERITIES:
            table[(cat, sev)] += 1

    lines = []
    lines.append("===== 对抗裁决汇总表 =====")
    lines.append("记录总数: %d" % n)
    lines.append("裁决分布: " + "，".join("%s %d 条" % (r, ruling_counts.get(r, 0)) for r in RULINGS))
    lines.append("")
    lines.append("入卷发现（ruling ∈ 维持/降级/改类）按 类别 × 严重度 计数：")
    head = "类别".ljust(10) + "".join(s.rjust(11) for s in SEVERITIES) + "合计".rjust(8)
    lines.append(head)
    lines.append("-" * len(head))
    total = 0
    for cat in CATEGORIES:
        row = [table.get((cat, s), 0) for s in SEVERITIES]
        subtotal = sum(row)
        total += subtotal
        lines.append(cat.ljust(10) + "".join(str(x).rjust(11) for x in row) + str(subtotal).rjust(8))
    lines.append("-" * len(head))
    lines.append("合计".ljust(10) + "".join(
        str(sum(table.get((c, s), 0) for c in CATEGORIES)).rjust(11) for s in SEVERITIES)
        + str(total).rjust(8))
    lines.append("")
    lines.append("留痕（仅入审查单附录，不入正文）：驳回 %d 条；转待复核 %d 条"
                 % (ruling_counts.get("驳回", 0), ruling_counts.get("转待复核", 0)))
    return "\n".join(lines)


def main(argv=None):
    ap = argparse.ArgumentParser(
        prog="tribunal_validate.py",
        description="校验对抗裁决日志（JSONL）的必填字段与一致性规则，并输出 类别×严重度 汇总表。"
                    "存在任何违规时退出码为 1 并逐条列出；全部通过时退出码为 0。")
    ap.add_argument("logfile", help="裁决日志 JSONL 文件路径（每行一条裁决记录）")
    ap.add_argument("--summary", metavar="PATH", default=None,
                    help="将汇总表同时写入指定文件（默认仅打印到 stdout）")
    ap.add_argument("--no-summary", action="store_true",
                    help="不输出汇总表，仅做校验")
    args = ap.parse_args(argv)

    try:
        with open(args.logfile, "r", encoding="utf-8") as f:
            raw_lines = f.read().splitlines()
    except OSError as e:
        print("错误: 无法读取 %s: %s" % (args.logfile, e), file=sys.stderr)
        return 1

    records = []
    record_linenos = []
    violations = []
    for i, line in enumerate(raw_lines, 1):
        if line.strip() == "":
            continue
        try:
            rec = json.loads(line)
        except json.JSONDecodeError as e:
            violations.append("第%d行: JSON 解析失败: %s" % (i, e))
            continue
        records.append(rec)
        record_linenos.append(i)

    seen_ids = {}
    for rec, real_ln in zip(records, record_linenos):
        if isinstance(rec, dict) and _nes(rec.get("id")):
            rid = rec["id"]
            if rid in seen_ids:
                violations.append("第%d行: id 重复: %r（首次出现于第%d行）"
                                  % (real_ln, rid, seen_ids[rid]))
            else:
                seen_ids[rid] = real_ln
        violations.extend(validate_record(rec, real_ln))

    summary = render_summary(records)
    if not args.no_summary:
        print(summary)
        if args.summary:
            try:
                with open(args.summary, "w", encoding="utf-8") as f:
                    f.write(summary + "\n")
            except OSError as e:
                print("错误: 无法写入汇总文件 %s: %s" % (args.summary, e), file=sys.stderr)
                return 1

    if violations:
        print("", file=sys.stderr)
        print("校验未通过: 共 %d 处违规：" % len(violations), file=sys.stderr)
        for m in violations:
            print("  - " + m, file=sys.stderr)
        return 1

    print("")
    print("校验通过: %d 条记录，0 处违规。" % len(records))
    return 0


if __name__ == "__main__":
    sys.exit(main())
