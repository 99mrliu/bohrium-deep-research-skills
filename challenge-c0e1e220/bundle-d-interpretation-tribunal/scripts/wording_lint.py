#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""wording_lint.py — 结果解释措辞纪律机器检查（interpretation-tribunal 重心 1）。

用法：
  python3 wording_lint.py [--file /app/output/report.md] [--result /app/output/result.json]

违例码：
  BANNED_PHRASE      禁用语（证明/证实/完全无效/毫无作用/显著所以重要/
                     统计上显著因此/差异不存在/观察性比较中的因果措辞"导致、引起"）
  P_WORDING          p 值表述未采用「在 α=… 水平下…（不）具有统计学意义」句式，
                     或出现「p=0.0x，证明/说明/表明有效」类组合
  CI_MISREAD         把 95% 置信区间误读为个体/数据/测量值/样本的取值范围
  MISSING_PRACTICAL  含「具有统计学意义」结论的段落缺少独立的实际意义句
                     （须含效应量数值或最小实际重要差异 Δ 讨论）
  UNHEDGED_PARTIAL   result.json status=partial 时报告缺少不确定性说明段

规则范围：markdown 表格行（| 开头）与代码围栏内的原始统计量清单不属于
「解释性表述」，不参与措辞判定。任一违例打印行号并 exit 1；全过 exit 0。
"""
import argparse
import json
import os
import re
import sys

VERSION = "1.0.0"

# 禁用语表（出处理由见 references/wording-rules.md）
BANNED_PHRASES = [
    "证明", "证实了", "证实", "完全无效", "毫无作用", "毫无效果",
    "显著所以重要", "统计上显著因此", "差异不存在",
    "导致", "引起",
]

P_PATTERN = re.compile(r"(p\s*[=<＝]|p\s*值|p-value|p 值)", re.IGNORECASE)
P_LEVEL_PATTERN = re.compile(r"在\s*α\s*=\s*[0-9.]+\s*水平下")
P_COMBO_BAD = re.compile(r"(证明|说明|表明)[^。；]{0,6}(有效|效果显着|效果显著)")

CI_MISREAD_PATTERNS = [
    re.compile(r"95\s*%\s*的(个体|数据|测量值|样本|观测值|观测)[^。；]{0,25}"
               r"(落在|位于|分布于|处于)[^。；]{0,12}区间"),
    re.compile(r"(落在|位于|分布于|处于)(该|此)?(置信)?区间[^。；]{0,15}"
               r"(个体|数据|测量值|样本)"),
    re.compile(r"个体取值范围"),
    re.compile(r"区间[^。；]{0,8}(包含|涵盖|覆盖)[^。；]{0,8}95\s*%[^。；]{0,8}"
               r"(个体|数据|测量值|样本|观测)"),
]
CI_NEGATION_GUARD = re.compile(r"(并非|不是|而非|不表示|不能理解为|并非指)$")

PRACTICAL_PATTERN = re.compile(
    r"(效应量|Hedges g|Cohen's d|η²|ω²|ε²|中位数差|置信区间为)[^。]{0,40}[0-9]"
    r"|最小实际重要差异|实际重要差异阈值|Δ")


def iter_prose_lines(text):
    """产出 (行号, 行文本)：跳过表格行与代码围栏。"""
    in_fence = False
    for lineno, line in enumerate(text.splitlines(), start=1):
        stripped = line.strip()
        if stripped.startswith("```"):
            in_fence = not in_fence
            continue
        if in_fence or stripped.startswith("|"):
            continue
        yield lineno, line


def split_sentences(line):
    """按中文句末点号切分（句内允许「；」连接子句），保留非空片段。"""
    parts = re.split(r"(?<=[。！？])", line)
    return [p.strip() for p in parts if p.strip()]


def lint_report(report_path, result_path=None):
    """返回违例字符串列表（空 = 通过）。"""
    with open(report_path, encoding="utf-8") as f:
        text = f.read()
    violations = []

    def vio(code, lineno, msg):
        violations.append("%s: line %d: %s" % (code, lineno, msg))

    prose = list(iter_prose_lines(text))

    # ---- BANNED_PHRASE / P_WORDING / CI_MISREAD（句级）----
    for lineno, line in prose:
        for sent in split_sentences(line):
            for phrase in BANNED_PHRASES:
                if phrase in sent:
                    vio("BANNED_PHRASE", lineno,
                        "命中禁用语「%s」：%s" % (phrase, sent[:60]))
            if P_PATTERN.search(sent):
                if not (P_LEVEL_PATTERN.search(sent) and "具有统计学意义" in sent):
                    vio("P_WORDING", lineno,
                        "p 值表述须采用「在 α=… 水平下…（不）具有统计学意义」"
                        "句式：%s" % sent[:70])
                if P_COMBO_BAD.search(sent):
                    vio("P_WORDING", lineno,
                        "检出 p 值与「证明/说明/表明有效」组合：%s" % sent[:70])
            for pat in CI_MISREAD_PATTERNS:
                for m in pat.finditer(sent):
                    prefix = sent[max(0, m.start() - 6):m.start()]
                    if CI_NEGATION_GUARD.search(prefix):
                        continue
                    vio("CI_MISREAD", lineno,
                        "置信区间被误读为个体取值范围：%s" % sent[:70])
                    break

    # ---- MISSING_PRACTICAL（段级）----
    paragraphs = re.split(r"\n\s*\n", text)
    for para in paragraphs:
        # 找到段落起始行号
        idx = text.find(para)
        lineno = text[:idx].count("\n") + 1 if idx >= 0 else 0
        plain = "\n".join(l for _, l in
                          [(0, x) for x in para.splitlines()
                           if not x.strip().startswith("|")])
        if "具有统计学意义" in plain and "不具有统计学意义" not in plain:
            if not PRACTICAL_PATTERN.search(plain):
                vio("MISSING_PRACTICAL", lineno,
                    "含「具有统计学意义」结论的段落缺少独立的实际意义句"
                    "（须含效应量数值或最小实际重要差异 Δ 讨论）：%s"
                    % plain.replace("\n", " ")[:70])

    # ---- UNHEDGED_PARTIAL ----
    rp = result_path
    if rp is None:
        cand = os.path.join(os.path.dirname(os.path.abspath(report_path)),
                            "result.json")
        rp = cand if os.path.exists(cand) else None
    if rp and os.path.exists(rp):
        try:
            with open(rp, encoding="utf-8") as f:
                result = json.load(f)
        except json.JSONDecodeError:
            result = None
        if result and result.get("status") == "partial":
            if "不确定" not in text:
                vio("UNHEDGED_PARTIAL", 0,
                    "result.json status=partial，但报告缺少不确定性说明段")

    return violations


def main(argv=None):
    ap = argparse.ArgumentParser(description="结果解释措辞纪律 lint")
    ap.add_argument("--file", default="/app/output/report.md",
                    help="待检查的 report.md 路径")
    ap.add_argument("--result", default=None,
                    help="result.json 路径（默认取 report 同目录）")
    args = ap.parse_args(argv)
    if not os.path.exists(args.file):
        print("找不到报告文件: %s" % args.file, file=sys.stderr)
        return 2
    violations = lint_report(args.file, args.result)
    if violations:
        for v in violations:
            print("VIOLATION %s" % v)
        print("wording_lint: %d 项违例" % len(violations))
        return 1
    print("wording_lint: PASS（%s 未发现措辞违例）" % args.file)
    return 0


if __name__ == "__main__":
    sys.exit(main())
