#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""claim_check.py — 比较性论断校验。

纯标准库、确定性、无网络。

功能：
  扫描章节草稿中的比较级论断句（优于/超过/相当/不劣于/显著/outperform/
  comparable 等模式），逐句核对：
    a) 论断句或其所在段落是否有“指标名 + 数值”；
    b) 论断涉及的数值能否在材料 / 基线台账中定位；
    c) 是否有统计支撑声明（重复次数、±标准差、显著性检验）；
       含“显著/significantly”的论断必须有统计支撑。
  无支撑论断逐条列出，给出降级改写或标注 [待确认] 的建议。

用法：
  python3 claim_check.py --draft <章节草稿> [--input <材料目录/文件>]
                         [--baselines <baselines.json>] --out <输出目录>

输出：
  <out>/claims_report.json / <out>/claims_report.md
退出码：存在无支撑论断时为 1，否则为 0。
"""
import argparse
import json
import os
import re
import sys

CLAIM_PATTERNS = re.compile(
    r"优于|超过|胜过|强于|领先|不亚于|不劣于|相当|可比|持平|"
    r"outperform|outperforms|surpass|surpasses|exceed|exceeds|"
    r"superior|better than|comparable|on par|competitive",
    re.IGNORECASE)
STRONG_WORDS = re.compile(r"显著|明显优于|大幅|significant", re.IGNORECASE)
ALL_BASELINES = re.compile(r"所有基线|全部基线|all baselines", re.IGNORECASE)

METRIC_WORDS = (
    r"top-?[15]\s*accuracy|accuracy|acc|f1(?:-score)?|auroc|auc|rmse|mse|mae|"
    r"bleu|rouge(?:-l)?|precision|recall|map|perplexity|ppl|wer|cer|psnr|ssim")
RE_METRIC_VALUE = re.compile(
    r"(%s)\s*(?:of|is|=|:|为|达到|达|分别为|：)?\s*(\d{1,3}(?:\.\d+)?)\s*%%?"
    % METRIC_WORDS, re.IGNORECASE)
RE_VALUE_METRIC = re.compile(
    r"(\d{1,3}(?:\.\d+)?)\s*%%?\s*(?:\(|（)?\s*(%s)" % METRIC_WORDS,
    re.IGNORECASE)
RE_NUMBER = re.compile(r"\d{1,3}(?:\.\d+)?")

STAT_SUPPORT = re.compile(
    r"±|\+/-|std|标准差|t-?test|wilcoxon|bootstrap|p\s*[<≤=]\s*0?\.\d+|"
    r"显著性检验|置信区间|置信水平|重复\s*\d+\s*次|\d+\s*次重复|"
    r"\d+\s*(?:runs?|seeds?)\b", re.IGNORECASE)

SCAN_EXTS = {".txt", ".md", ".log", ".yaml", ".yml", ".json", ".csv"}


def collect_numbers_from_materials(inputs):
    """材料中出现的全部数值（字符串与浮点双索引），用于论断数值定位。"""
    numbers = set()
    files = []
    for item in inputs or []:
        if os.path.isfile(item):
            files.append(item)
        elif os.path.isdir(item):
            for root, dirs, names in os.walk(item):
                dirs.sort()
                for n in sorted(names):
                    if os.path.splitext(n)[1].lower() in SCAN_EXTS:
                        files.append(os.path.join(root, n))
    for p in sorted(dict.fromkeys(files)):
        try:
            with open(p, "r", encoding="utf-8", errors="replace") as f:
                text = f.read()
        except OSError:
            continue
        for m in RE_NUMBER.finditer(text):
            numbers.add(m.group(0))
    return numbers


def numbers_from_baselines(path):
    numbers = set()
    if not path or not os.path.isfile(path):
        return numbers
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            obj = json.load(f)
    except (OSError, ValueError):
        return numbers
    for b in obj.get("baselines", []):
        for m in b.get("metrics", []):
            if m.get("value"):
                numbers.add(str(m["value"]))
    return numbers


def num_eq(a, b):
    if a == b:
        return True
    try:
        return abs(float(a) - float(b)) < 1e-9
    except ValueError:
        return False


def split_sentences(text):
    """逐行按中/英文句读切句，返回 (行号, 句子)；跳过标题与空行。"""
    out = []
    for lineno, line in enumerate(text.splitlines(), 1):
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        for piece in re.split(r"(?<=[。！？!?；;])|(?<=[.])\s+", stripped):
            piece = piece.strip()
            if piece:
                out.append((lineno, piece))
    return out


def paragraphs(text):
    """段落 = 空行分隔的文本块。"""
    return [blk for blk in re.split(r"\n\s*\n", text) if blk.strip()]


def main():
    ap = argparse.ArgumentParser(description="比较性论断校验")
    ap.add_argument("--draft", required=True, help="章节草稿路径")
    ap.add_argument("--input", action="append", default=None,
                    help="材料目录或文件，用于数值定位，可重复")
    ap.add_argument("--baselines", default=None,
                    help="baseline_mine 产出的 baselines.json（可选）")
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    try:
        with open(args.draft, "r", encoding="utf-8", errors="replace") as f:
            draft_text = f.read()
    except OSError as e:
        print("错误：无法读取草稿 %s：%s" % (args.draft, e), file=sys.stderr)
        return 2

    known_numbers = collect_numbers_from_materials(args.input)
    known_numbers |= numbers_from_baselines(args.baselines)

    reported_baselines = []
    if args.baselines and os.path.isfile(args.baselines):
        try:
            with open(args.baselines, "r", encoding="utf-8",
                      errors="replace") as f:
                bobj = json.load(f)
            reported_baselines = [b["name"] for b in bobj.get("baselines", [])
                                  if b.get("source_type") == "原报"]
        except (OSError, ValueError):
            pass

    paras = paragraphs(draft_text)
    claims = []
    for lineno, sent in split_sentences(draft_text):
        if not CLAIM_PATTERNS.search(sent):
            continue
        window = sent
        for blk in paras:
            if sent in blk:
                window = blk
                break
        metric_hits = (RE_METRIC_VALUE.findall(window) +
                       [(b, a) for a, b in RE_VALUE_METRIC.findall(window)])
        claim_numbers = [m.group(0) for m in RE_NUMBER.finditer(sent)]
        window_numbers = [m.group(0) for m in RE_NUMBER.finditer(window)]
        locatable = [n for n in window_numbers
                     if any(num_eq(n, k) for k in known_numbers)]
        stat_in_window = bool(STAT_SUPPORT.search(window))
        stat_in_draft = bool(STAT_SUPPORT.search(draft_text))
        strong = bool(STRONG_WORDS.search(sent))

        reasons, suggestion = [], []
        has_metric_value = bool(metric_hits)
        if not has_metric_value:
            reasons.append("论断句及所在段落缺少“指标名+数值”")
        if not claim_numbers:
            reasons.append("论断句本身不含数值，无法直接定位证据")
        if not locatable:
            reasons.append("论断相关数值无法在材料/台账中定位")
        if strong and not (stat_in_window or stat_in_draft):
            reasons.append("使用“显著”类强措辞但无重复实验/显著性检验等统计支撑")
        notes = []
        if ALL_BASELINES.search(sent) and reported_baselines:
            notes.append("论断覆盖“所有基线”，但台账中存在原报值基线（%s），"
                         "非同等条件，建议将论断限定在同等条件对照组内"
                         % "、".join(reported_baselines))

        unsupported = bool(reasons)
        if unsupported:
            suggestion.append("降级为描述性写法：仅陈述“在相同划分下，本文方法"
                              "<指标>=<数值>，基线<名称>=<数值>”，不使用比较级")
            suggestion.append("或保留论断但标注 [待确认]，并列入人工确认项")
        elif notes:
            suggestion.append("论断有数值支撑，但建议按备注限定范围")

        claims.append({
            "sentence": sent.replace("\n", " ").strip(),
            "line": lineno,
            "status": "unsupported" if unsupported else "supported",
            "checks": {
                "metric_value_in_window": has_metric_value,
                "numbers_in_sentence": claim_numbers,
                "numbers_locatable": sorted(set(locatable)),
                "stat_support_in_window": stat_in_window,
                "stat_support_in_draft": stat_in_draft,
                "strong_wording": strong,
            },
            "reasons": reasons,
            "notes": notes,
            "suggestion": suggestion,
        })

    unsupported = [c for c in claims if c["status"] == "unsupported"]
    result = {
        "tool": "claim_check",
        "draft": args.draft,
        "claim_count": len(claims),
        "unsupported_count": len(unsupported),
        "claims": claims,
    }
    os.makedirs(args.out, exist_ok=True)
    jpath = os.path.join(args.out, "claims_report.json")
    with open(jpath, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    mpath = os.path.join(args.out, "claims_report.md")
    with open(mpath, "w", encoding="utf-8") as f:
        f.write("# 比较性论断校验报告（claim_check 自动产出）\n\n")
        f.write("论断总数 %d；无支撑 %d。\n\n" % (len(claims), len(unsupported)))
        for c in claims:
            mark = "❌ 无支撑" if c["status"] == "unsupported" else "✅ 有支撑"
            f.write("## [%s] 草稿第 %d 行\n\n" % (mark, c["line"]))
            f.write("> %s\n\n" % c["sentence"])
            if c["reasons"]:
                f.write("问题：\n")
                for r in c["reasons"]:
                    f.write("- %s\n" % r)
            if c["notes"]:
                f.write("备注：\n")
                for n in c["notes"]:
                    f.write("- %s\n" % n)
            if c["suggestion"]:
                f.write("建议：\n")
                for s in c["suggestion"]:
                    f.write("- %s\n" % s)
            f.write("\n")

    print("claim_check：论断 %d 句，无支撑 %d 句 -> %s, %s"
          % (len(claims), len(unsupported), jpath, mpath))
    for c in unsupported:
        print("  ! 第%d行无支撑：%s" % (c["line"], c["sentence"][:60]))
    return 1 if unsupported else 0


if __name__ == "__main__":
    sys.exit(main())
