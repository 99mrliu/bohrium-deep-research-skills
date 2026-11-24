#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ledger_extract.py — 源文证据台账提取器（skill-a-factsentry）

扫描科研源文（md/txt，可多个文件），用确定性正则提取证据条目，输出 evidence_ledger.json：
  - number      数字条目（数值 + 可选单位：%、mg/L、°C、倍、n=、p<、r= 等）
  - figure_ref  图表引用（图1 / 图 S1 / Fig. 2 / Figure 2 / 表3 / Table S1）
  - citation    引用标记（[1]、[1-3]、[1,3]、(Author, 2020)、(Author et al., 2020)）
  - strength    论断强度词（证实/表明/初步表明/提示/可能/相关/
                demonstrates/suggests/may/correlates …）
每条含 id、kind、anchor（原文锚句）、locator（file:line）。

设计要点（确定性、仅标准库）：
  - 无时间戳、无随机、无网络；同一输入必得同一输出。
  - 图表引用 / 引用标记 / 统计量（n=5、p<0.05）的字符区间先做掩码，
    数字扫描跳过掩码区间，避免把「图1」「[1-3]」中的数字误记为数字条目。
  - 化学式中紧贴字母的数字（如 Co3O4 的 3）不计入。
  - 无单位的 1900–2099 四位整数视为年份，不计入数字条目。

退出码：0 = 成功；2 = 用法或输入/输出错误。

用法：
  python3 ledger_extract.py 源文1.md [源文2.txt ...] -o evidence_ledger.json
"""

import argparse
import json
import os
import re
import sys

VERSION = "1.0.0"

# ---------------------------------------------------------------------------
# 论断强度阶梯（与 references/claim_strength_ladder.md 保持一致）
# 级别：0 推测 < 1 提示/初步 < 1.5 相关 < 2 表明 < 2.5 实证 < 3 证实 < 4 因果断言
# ---------------------------------------------------------------------------
CN_STRENGTH = [
    ("初步表明", 1.0, "tentative"),
    ("初步显示", 1.0, "tentative"),
    ("提示", 1.0, "tentative"),
    ("可能", 0.0, "hedge"),
    ("或许", 0.0, "hedge"),
    ("有望", 0.0, "hedge"),
    ("相关", 1.5, "correlation"),
    ("关联", 1.5, "correlation"),
    ("表明", 2.0, "show"),
    ("显示", 2.0, "show"),
    ("证实", 3.0, "confirm"),
    ("证明", 3.0, "confirm"),
    ("确证", 3.0, "confirm"),
    ("导致", 4.0, "causal"),
    ("致使", 4.0, "causal"),
    ("治愈", 4.0, "causal"),
    ("根治", 4.0, "causal"),
    ("消除", 4.0, "causal"),
]
CN_STRENGTH.sort(key=lambda w: -len(w[0]))  # 最长优先，避免「初步表明」中的「表明」重复计数

# 拉丁词干 + 常见词形变化后缀；词边界防止 because 命中 cause、maybe 命中 may
LAT_STRENGTH = [
    ("demonstrate", 2.5, "demonstrate"),
    ("suggest", 1.0, "tentative"),
    ("indicate", 1.0, "tentative"),
    ("hint", 1.0, "tentative"),
    ("show", 2.0, "show"),
    ("reveal", 2.0, "show"),
    ("confirm", 3.0, "confirm"),
    ("prove", 3.0, "confirm"),
    ("may", 0.0, "hedge"),
    ("might", 0.0, "hedge"),
    ("could", 0.0, "hedge"),
    ("possibly", 0.0, "hedge"),
    ("correlate", 1.5, "correlation"),
    ("associate", 1.5, "correlation"),
    ("cause", 4.0, "causal"),
    ("cure", 4.0, "causal"),
    ("eliminate", 4.0, "causal"),
]

LEVEL_LABELS = {
    0.0: "推测(0)",
    1.0: "提示/初步(1)",
    1.5: "相关(1.5)",
    2.0: "表明(2)",
    2.5: "实证(2.5)",
    3.0: "证实(3)",
    4.0: "因果断言(4)",
}

# ---------------------------------------------------------------------------
# 单位与数字
# ---------------------------------------------------------------------------
UNITS = [
    # 复合/多字符单位在前，单字符在后（正则交替按顺序尝试）
    "m²/g", "m2/g", "mg/L", "μg/L", "g/L", "mmol/L", "mol/L", "mAh/g", "kWh",
    "MPa", "kPa", "wt%", "vol%", "mol%", "at%", "°C", "℃",
    "min", "mA", "mV", "keV", "eV", "nm", "μm", "µm", "mm", "cm", "km",
    "mL", "μL", "bar", "atm", "Pa",
    "小时", "分钟", "倍", "次", "天", "年", "组", "个", "种",
    "%", "％",
    "s", "h", "m", "L", "g", "W", "K", "V", "A",
]
_UNIT_ALT = "(?:" + "|".join(re.escape(u) for u in UNITS) + ")"

NUM_RE = re.compile(r"(?<![A-Za-z0-9_.])([+-]?\d+(?:\.\d+)?)\s*(" + _UNIT_ALT + r")?")
STAT_RE = re.compile(r"(?<![A-Za-z0-9])(n|p|r|R)\s*([<≤=＜>≥])\s*(\d+(?:\.\d+)?)")

FIG_RE = re.compile(r"(?:图\s*(S?\d+[A-Za-z]?)|Fig(?:ure)?\.?\s*(S?\d+[A-Za-z]?))", re.IGNORECASE)
TAB_RE = re.compile(r"(?:表\s*(S?\d+[A-Za-z]?)|Table\.?\s*(S?\d+[A-Za-z]?))", re.IGNORECASE)

CIT_NUM_RE = re.compile(r"\[\s*\d+(?:\s*[-–,，]\s*\d+)*\s*\]")
CIT_AUTHOR_RE = re.compile(
    r"\(([A-Z][A-Za-zÀ-ÿ\-]+)(\s+et\s+al\.?)?\s*,?\s*((?:19|20)\d{2}[a-z]?)\)")

SENT_SPLIT = re.compile(r"[。！？；!?;]")
LEADING_MARK_RE = re.compile(r"^\s*(?:#+\s*|\d+[.、)]\s*|[-*+]\s+)")

# ---------------------------------------------------------------------------
# 归一化
# ---------------------------------------------------------------------------

def norm_unit(u):
    if not u:
        return ""
    u = u.strip().replace("％", "%").replace("℃", "°C").replace("µ", "μ")
    return re.sub(r"\s+", "", u)


def norm_value(v):
    """数值字符串归一化：95.10 与 95.1 等价。"""
    return "%g" % float(v)


def number_key(value, unit):
    return "%s|%s" % (norm_value(value), norm_unit(unit))


def norm_op(op):
    return {"＜": "<", "＞": ">", "≤": "<=", "≥": ">="}.get(op, op)


def figref_key(ref_type, ref_id):
    return "%s:%s" % (ref_type, ref_id.upper())


def norm_citation_num(raw):
    return re.sub(r"\s+", "", raw).replace("，", ",").replace("–", "-")


# ---------------------------------------------------------------------------
# 句子切分与锚句
# ---------------------------------------------------------------------------

def _segments(line):
    segs = []
    start = 0
    for m in SENT_SPLIT.finditer(line):
        segs.append((start, m.start()))
        start = m.end()
    segs.append((start, len(line)))
    return [(a, b) for a, b in segs if line[a:b].strip()]


def anchor_of(line, pos, maxlen=200):
    for a, b in _segments(line):
        if a <= pos <= b:
            return line[a:b].strip()[:maxlen]
    return line.strip()[:maxlen]


# ---------------------------------------------------------------------------
# 论断强度词扫描
# ---------------------------------------------------------------------------

def _overlap(spans, a, b):
    return any(a < sb and sa < b for sa, sb in spans)


def find_strengths(line):
    """返回 [(start, word, level, category), ...]。"""
    found = []
    spans = []
    for word, level, cat in CN_STRENGTH:
        idx = line.find(word)
        while idx >= 0:
            if not _overlap(spans, idx, idx + len(word)):
                found.append((idx, word, level, cat))
                spans.append((idx, idx + len(word)))
            idx = line.find(word, idx + 1)
    for stem, level, cat in LAT_STRENGTH:
        rx = re.compile(r"(?<![A-Za-z])" + stem + r"(?:s|es|ed|ing)?(?![A-Za-z])",
                        re.IGNORECASE)
        for m in rx.finditer(line):
            if not _overlap(spans, m.start(), m.end()):
                found.append((m.start(), m.group(0), level, cat))
                spans.append((m.start(), m.end()))
    found.sort(key=lambda t: t[0])
    return found


# ---------------------------------------------------------------------------
# 相似度（供 fact_check 复用）：CJK 二字组 + 拉丁词 + 数字
# ---------------------------------------------------------------------------

def shingles(text):
    text = text.lower()
    tokens = set(re.findall(r"[a-z]+|\d+(?:\.\d+)?", text))
    for run in re.findall(r"[一-鿿]+", text):
        if len(run) == 1:
            tokens.add(run)
        else:
            for i in range(len(run) - 1):
                tokens.add(run[i:i + 2])
    return tokens


def jaccard(a, b):
    if not a or not b:
        return 0.0
    inter = len(a & b)
    return inter / float(len(a) + len(b) - inter)


# ---------------------------------------------------------------------------
# 主扫描
# ---------------------------------------------------------------------------

def scan_text(text, fname, counters):
    """扫描一段文本，返回台账条目列表。counters 用于跨文件连续编号。"""
    entries = []

    def next_id(prefix):
        counters[prefix] = counters.get(prefix, 0) + 1
        return "%s-%03d" % (prefix, counters[prefix])

    for lineno, line in enumerate(text.splitlines(), 1):
        locator = "%s:%d" % (fname, lineno)
        mask = []  # 图表引用 / 引用标记 / 统计量 的字符区间

        # --- 图表引用 ---
        for rx, ref_type in ((FIG_RE, "fig"), (TAB_RE, "tab")):
            for m in rx.finditer(line):
                ref_id = m.group(1) or m.group(2)
                mask.append(m.span())
                entries.append({
                    "id": next_id(ref_type),
                    "kind": "figure_ref",
                    "ref_type": ref_type,
                    "ref_id": ref_id.upper(),
                    "key": figref_key(ref_type, ref_id),
                    "raw": m.group(0),
                    "anchor": anchor_of(line, m.start()),
                    "locator": locator,
                })

        # --- 引用标记 ---
        for m in CIT_NUM_RE.finditer(line):
            mask.append(m.span())
            entries.append({
                "id": next_id("cit"),
                "kind": "citation",
                "style": "numeric",
                "key": "cite:" + norm_citation_num(m.group(0)),
                "raw": m.group(0),
                "anchor": anchor_of(line, m.start()),
                "locator": locator,
            })
        for m in CIT_AUTHOR_RE.finditer(line):
            mask.append(m.span())
            entries.append({
                "id": next_id("cit"),
                "kind": "citation",
                "style": "author-year",
                "key": "cite:%s:%s" % (m.group(1).lower(), m.group(3)),
                "raw": m.group(0),
                "anchor": anchor_of(line, m.start()),
                "locator": locator,
            })

        # --- 统计量（n=5 / p<0.05 / r=0.93）---
        for m in STAT_RE.finditer(line):
            mask.append(m.span())
            stat = m.group(1).lower()
            unit = stat + norm_op(m.group(2))
            entries.append({
                "id": next_id("num"),
                "kind": "number",
                "value": m.group(3),
                "unit": unit,
                "key": number_key(m.group(3), unit),
                "raw": m.group(0),
                "anchor": anchor_of(line, m.start()),
                "locator": locator,
            })

        # --- 数字条目（跳过掩码区间；标题/列表序号掩为空白，保持偏移不变）---
        scan_line = LEADING_MARK_RE.sub(lambda m: " " * len(m.group(0)), line)
        for m in NUM_RE.finditer(scan_line):
            a, b = m.span(1)
            if any(a < mb and ma < b for ma, mb in mask):
                continue
            value, unit = m.group(1), m.group(2) or ""
            # 单位后的字符检查：单字符拉丁单位后不得紧跟字母/数字（防止 5 gs 之类误配）
            if unit and len(unit) == 1 and unit.isascii() and unit.isalpha():
                end = m.end()
                if end < len(scan_line) and re.match(r"[A-Za-z0-9]", scan_line[end]):
                    continue
            # 无单位四位年份（1900–2099）不计入
            if not unit and re.fullmatch(r"(19|20)\d{2}", value):
                continue
            entries.append({
                "id": next_id("num"),
                "kind": "number",
                "value": value,
                "unit": norm_unit(unit),
                "key": number_key(value, unit),
                "raw": m.group(0).strip(),
                "anchor": anchor_of(line, m.start()),
                "locator": locator,
            })

        # --- 论断强度词 ---
        for pos, word, level, cat in find_strengths(line):
            entries.append({
                "id": next_id("str"),
                "kind": "strength",
                "word": word,
                "level": level,
                "level_label": LEVEL_LABELS[level],
                "category": cat,
                "anchor": anchor_of(line, pos),
                "locator": locator,
            })

    return entries


def build_ledger(paths):
    counters = {}
    entries = []
    for path in paths:
        with open(path, "r", encoding="utf-8") as f:
            text = f.read()
        entries.extend(scan_text(text, path, counters))
    counts = {}
    for e in entries:
        counts[e["kind"]] = counts.get(e["kind"], 0) + 1
    return {
        "tool": "ledger_extract",
        "version": VERSION,
        "sources": list(paths),
        "counts": counts,
        "entries": entries,
    }


def main(argv=None):
    ap = argparse.ArgumentParser(
        description="源文证据台账提取器：从科研源文（md/txt）提取数字/图表/引用/论断强度条目。",
        epilog="退出码：0=成功；2=用法或输入/输出错误。")
    ap.add_argument("inputs", nargs="+", help="源文文件路径（可多个）")
    ap.add_argument("-o", "--out", default="evidence_ledger.json",
                    help="输出台账 JSON 路径（默认 evidence_ledger.json）")
    args = ap.parse_args(argv)

    for p in args.inputs:
        if not os.path.isfile(p):
            print("ERROR: 源文不存在：%s" % p, file=sys.stderr)
            return 2
    try:
        ledger = build_ledger(args.inputs)
    except (OSError, UnicodeDecodeError) as e:
        print("ERROR: 读取源文失败：%s" % e, file=sys.stderr)
        return 2

    out_dir = os.path.dirname(os.path.abspath(args.out))
    if not os.path.isdir(out_dir):
        print("ERROR: 输出目录不存在：%s" % out_dir, file=sys.stderr)
        return 2
    try:
        with open(args.out, "w", encoding="utf-8") as f:
            json.dump(ledger, f, ensure_ascii=False, indent=2)
            f.write("\n")
    except OSError as e:
        print("ERROR: 写入台账失败：%s" % e, file=sys.stderr)
        return 2

    c = ledger["counts"]
    print("ledger_extract: %d 条证据条目 -> %s "
          "(number=%d, figure_ref=%d, citation=%d, strength=%d)"
          % (len(ledger["entries"]), args.out,
             c.get("number", 0), c.get("figure_ref", 0),
             c.get("citation", 0), c.get("strength", 0)))
    if not ledger["entries"]:
        print("WARNING: 未提取到任何证据条目，请确认源文内容与编码（需 UTF-8）。",
              file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
