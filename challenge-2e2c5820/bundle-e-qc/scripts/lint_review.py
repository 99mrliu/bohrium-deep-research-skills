#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""lint_review.py — 审查报告（review_report.md）自洽性 lint，支撑质控门 G3/G4。

用法:
    python3 lint_review.py <review.md> [--strict] [--min-anchors N]

规则:
    R1 每个结论词（可行/有条件可行/不可行/无法判定）之后、下一标题前（≤300 字符窗内）
       必须出现「条件」或「理由」说明                      —— 警告
    R2 「有条件可行」必须存在编号条件条目（同节优先，全文兜底）—— 硬违规
    R3 禁用语「建议进一步确认」必须挂在编号条目上（否则是空头意见）—— 警告
    R4 证据锚点（[L12]、（第X节） 等定位符）总数低于阈值   —— 警告
    R5 同一 plan_id 被赋予两个不同结论                     —— 硬违规

退出码: 0 通过；2 存在硬违规（或 --strict 下存在警告）。
"""
import argparse
import re
import sys

VERDICT_RE = re.compile(r"有条件可行|不可行|无法判定|可行(?![性度])")
PLAN_RE = re.compile(r"plan[_A-Za-z0-9-]+|方案[A-Za-z0-9甲乙丙丁一二三四五六七八九十]")
NUMBERED_RE = re.compile(r"^\s*(?:\d+\s*[.、)]|（\d+）|第[一二三四五六七八九十\d]+条)", re.M)
HEADING_RE = re.compile(r"^#{1,6}\s", re.M)
ANCHOR_RES = (re.compile(r"\[L\d+\]"), re.compile(r"（第[^）]{1,15}节）"))
BANNED = "建议进一步确认"
R1_WINDOW = 300
HARD_RULES = ("R2", "R5")


def line_no(text, pos):
    return text.count("\n", 0, pos) + 1


def count_anchors(text):
    return sum(len(r.findall(text)) for r in ANCHOR_RES)


def lint(text, min_anchors):
    """返回 issues: [(rule, severity, message), ...]，severity ∈ {硬违规, 警告}。"""
    issues = []
    lines = text.splitlines()

    # R1 / R2：逐结论词检查
    for m in VERDICT_RE.finditer(text):
        verdict = m.group(0)
        nxt = HEADING_RE.search(text, m.end())
        sec_end = nxt.start() if nxt else len(text)
        ln = line_no(text, m.start())
        seg = text[m.end():min(m.end() + R1_WINDOW, sec_end)]
        if not re.search(r"条件|理由", seg):
            issues.append(("R1", "警告",
                           "第%d行：结论词「%s」之后缺少「条件/理由」说明" % (ln, verdict)))
        if verdict == "有条件可行":
            region = text[m.start():sec_end]
            if not NUMBERED_RE.search(region) and not NUMBERED_RE.search(text):
                issues.append(("R2", "硬违规",
                               "第%d行：「有条件可行」未找到编号条件条目（同节及全文均无）" % ln))

    # R3：禁用语必须挂在编号条目上
    for i, line in enumerate(lines, 1):
        if BANNED in line and not NUMBERED_RE.match(line):
            issues.append(("R3", "警告",
                           "第%d行：「%s」未挂在编号条件条目上（空头意见）" % (i, BANNED)))

    # R4：证据锚点密度
    n_anchor = count_anchors(text)
    if n_anchor < min_anchors:
        issues.append(("R4", "警告",
                       "证据锚点密度不足：仅 %d 个（要求 ≥%d，形如 [L12] 或 （第X节））"
                       % (n_anchor, min_anchors)))

    # R5：同一 plan_id 结论冲突（按行关联；无 plan_id 的行继承最近标题中的 plan）
    plan_verdicts = {}
    context = None
    for i, line in enumerate(lines, 1):
        plans = PLAN_RE.findall(line)
        verdicts = VERDICT_RE.findall(line)
        if HEADING_RE.match(line):
            context = plans[0] if plans else None
        targets = plans if plans else ([context] if context else [])
        for v in verdicts:
            for t in targets:
                plan_verdicts.setdefault(t, {}).setdefault(v, i)
    for pid, vd in sorted(plan_verdicts.items()):
        if len(vd) > 1:
            detail = "；".join("「%s」(第%d行)" % (v, ln) for v, ln in sorted(vd.items()))
            issues.append(("R5", "硬违规",
                           "同一方案 %s 被赋予互相冲突的结论：%s" % (pid, detail)))
    return issues


def summarize(text):
    """供 selfcheck 解析的计数行。"""
    return None


def main(argv=None):
    ap = argparse.ArgumentParser(description="审查报告自洽性 lint（R1-R5）")
    ap.add_argument("review_md")
    ap.add_argument("--strict", action="store_true", help="警告也按失败处理（exit 2）")
    ap.add_argument("--min-anchors", type=int, default=3, help="证据锚点数量阈值（默认 3）")
    args = ap.parse_args(argv)

    try:
        with open(args.review_md, "r", encoding="utf-8") as f:
            text = f.read()
    except OSError as e:
        print("错误：无法读取审查报告: %s" % e, file=sys.stderr)
        return 2

    issues = lint(text, args.min_anchors)
    hard = [x for x in issues if x[1] == "硬违规"]
    warn = [x for x in issues if x[1] == "警告"]
    for rule, sev, msg in issues:
        print("[%s][%s] %s" % (sev, rule, msg))
    print("lint 结果：%d 个硬违规，%d 个警告。" % (len(hard), len(warn)))

    if hard or (args.strict and warn):
        print("lint 未通过。")
        return 2
    print("lint 通过。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
