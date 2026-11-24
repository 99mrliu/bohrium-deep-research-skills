#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""claim_scan.py — placement-surgeon 阶段 1：论断切分与标记清点。

仅使用 Python 标准库；确定性；无网络访问。

输入：
    --manuscript FILE   UTF-8 文本 / Markdown 稿件，可含章节标题、正文段、
                        图注（行首“图 1.”/“Figure 1.”）、表注（“表 1.”/“Table 1.”）、
                        脚注（行首“注：”）以及末尾的“参考文献”节。
    --out DIR           输出目录，写出 sentences.jsonl 与 markers.jsonl。

切句规则：
    * 中文句读 “。！？；” 一律成界，紧随的闭引号/闭括号并入前句；
    * ASCII “.” 在下列情形不成界：小数点（数字.数字）、缩写词（et al.、Fig.、
      e.g. 等白名单）、后接小写字母、后接中日韩汉字（如“图 1. 示意”）；
    * ASCII “!”“?” 后接字母数字时不成界。

每句给出事实线索（cue）初判：
    number_unit   数字+单位（%、mg、例、名、份、个、倍、周、年、亿、万 等）
    year          19xx/20xx 年份
    report_kw     报道类线索词（研究表明/荟萃分析/随机对照试验/reported 等）
    proper_nouns  ≥3 个大写起头的拉丁词元
    opinion       观点/过渡线索词（综上所述/我们认为/in our view 等）

needs_support 初判 = 存在事实线索 且 不命中 opinion 线索。

标记识别：
    [n] / [n-m] / [n,m] 数字编号标记；（作者, 年）/(Author, year) 著者-年标记。
    “参考文献”节整节排除，不抽取句与标记。

退出码：0 正常；2 参数/读文件错误。
"""

import argparse
import json
import os
import re
import sys

CN_TERMINATORS = "。！？；"
ASCII_TERMINATORS = ".!?"
CLOSERS = "”’\"')）】」』》"

ABBREV = {
    "al", "fig", "figs", "eq", "eqs", "ref", "refs", "dr", "prof", "vs",
    "etc", "cf", "no", "nos", "ca", "inc", "ltd", "e.g", "i.e", "mr",
    "mrs", "ms", "st", "approx", "dept",
}

HEADING_RE = re.compile(
    r"^(#{1,6}\s|\d+\s*[、.．]?\s+\S|[一二三四五六七八九十百]+[、.．]\s*\S)"
)
CAPTION_RE = re.compile(r"^\s*(?:图|表)\s*\d+|^\s*(?:Figure|Fig\.|Table)\s*\d+", re.I)
FOOTNOTE_RE = re.compile(r"^\s*(?:注|注释|脚注)\s*[:：]")
REFERENCES_RE = re.compile(
    r"^\s*(?:参考文献|References|REFERENCES|Bibliography)\s*:?\s*$"
)

NUM_UNIT_RE = re.compile(
    r"\d+(?:\.\d+)?\s*(?:%|％|℃|°C|mg|μg|µg|kg|g|mL|ml|L|mmol|mol|mm|cm|km|"
    r"Hz|kDa|μM|mM|h|min|例|名|份|篇|种|个|家|项|株|剂|倍|周|天|岁|分|"
    r"万人次|万人|亿人|亿|万)"
)
YEAR_RE = re.compile(r"(?:19|20)\d{2}\s*年?")
PROPER_RE = re.compile(r"[A-Z][A-Za-z0-9-]{1,}")

REPORT_KWS = [
    "研究表明", "研究报道", "研究显示", "据报道", "研究发现", "已证实",
    "已有研究", "实验证明", "结果显示", "数据表明", "荟萃分析",
    "随机对照试验", "横断面研究", "队列研究", "调查报告", "对照实验",
    "demonstrated", "reported", "showed", "has been shown",
    "study found", "et al.",
]
OPINION_KWS = [
    "综上所述", "我们认为", "笔者认为", "总而言之", "总体而言", "笔者认为",
    "in our view", "we believe", "we think", "in our opinion",
]

BRACKET_RE = re.compile(r"\[\s*\d+(?:\s*[-–—,，]\s*\d+)*\s*\]")
AUTHORYEAR_RE = re.compile(
    r"[（(][^（）()\n]{0,80}?(?:19|20)\d{2}[a-z]?[^（）()\n]{0,30}?[)）]"
)


def is_ascii_boundary(text, i):
    """判断 ASCII 句读字符 text[i] 是否为句子边界。"""
    c = text[i]
    n = len(text)
    prev = text[i - 1] if i > 0 else ""
    nxt = text[i + 1] if i + 1 < n else ""
    if c == ".":
        if prev.isdigit() and nxt.isdigit():
            return False  # 小数点
        m = re.search(r"([A-Za-z]+(?:\.[A-Za-z]+)*)$", text[:i])
        if m and m.group(1).lower() in ABBREV:
            return False  # et al. / Fig. / e.g. 等缩写
        j = i + 1
        while j < n and text[j] in " \t":
            j += 1
        if j >= n or text[j] == "\n":
            return True
        nc = text[j]
        if nc.islower():
            return False  # 小写后接大写启发式的另一半：后接小写绝不成界
        if "\u4e00" <= nc <= "\u9fff":
            return False  # 中文章节编号/图号，如“图 1. 示意”
        if nc.isupper() or nc.isdigit() or nc in "（(\"'“":
            return True
        return False
    # "!" / "?"
    if nxt.isalnum():
        return False
    return True


def split_sentences(text):
    """把段落文本切成句子，返回 [(start, end)] 局部偏移列表（含边界符与闭引号）。"""
    spans = []
    n = len(text)
    start = 0
    i = 0
    while i < n:
        c = text[i]
        boundary = False
        if c in CN_TERMINATORS:
            boundary = True
        elif c in ASCII_TERMINATORS:
            boundary = is_ascii_boundary(text, i)
        if boundary:
            j = i + 1
            while j < n and text[j] in CLOSERS:
                j += 1
            if text[start:j].strip():
                spans.append((start, j))
            start = j
            i = j
        else:
            i += 1
    if start < n and text[start:].strip():
        spans.append((start, n))
    return spans


def detect_cues(text):
    cues = []
    if NUM_UNIT_RE.search(text):
        cues.append("number_unit")
    if YEAR_RE.search(text):
        cues.append("year")
    low = text.lower()
    for kw in REPORT_KWS:
        if kw in text or kw in low:
            cues.append("report_kw")
            break
    if len(PROPER_RE.findall(text)) >= 3:
        cues.append("proper_nouns")
    opinion = False
    for kw in OPINION_KWS:
        if kw in text or kw in low:
            opinion = True
            break
    if opinion:
        cues.append("opinion")
    needs_support = bool(set(cues) & {"number_unit", "year", "report_kw",
                                      "proper_nouns"}) and not opinion
    return cues, needs_support


def expand_refs(raw):
    """把 [2-4] / [2,4] 展开为 [2,3,4] / [2,4]；著者-年标记原样返回。"""
    inner = raw.strip()[1:-1]
    refs = []
    for part in re.split(r"[,，]", inner):
        part = part.strip()
        m = re.match(r"^(\d+)\s*[-–—]\s*(\d+)$", part)
        if m:
            a, b = int(m.group(1)), int(m.group(2))
            refs.extend(range(a, b + 1) if a <= b else [a])
        elif part.isdigit():
            refs.append(int(part))
    return refs


def build_blocks(lines):
    """把行列表分块：[(zone, [(lineno, text), ...])]，空行分块。"""
    blocks = []
    cur = []
    for lineno, ltext in lines:
        if ltext.strip() == "":
            if cur:
                blocks.append(cur)
                cur = []
        else:
            cur.append((lineno, ltext))
    if cur:
        blocks.append(cur)

    zoned = []
    in_references = False
    for blk in blocks:
        first = blk[0][1]
        if in_references:
            zone = "references"
        elif REFERENCES_RE.match(first.strip()):
            zone = "references"
            in_references = True
        elif CAPTION_RE.match(first):
            zone = "caption"
        elif FOOTNOTE_RE.match(first):
            zone = "footnote"
        elif HEADING_RE.match(first):
            zone = "heading"
        elif len(blk) == 1 and not any(
            ch in first for ch in CN_TERMINATORS + ASCII_TERMINATORS
        ):
            zone = "heading"  # 单行且无句读：视为标题/题名
        else:
            zone = "body"
        zoned.append((zone, blk))
    return zoned


def scan_manuscript(path):
    """扫描稿件，返回 (sentences, markers, full_text, stats)。"""
    with open(path, "r", encoding="utf-8") as fh:
        full_text = fh.read()

    raw_lines = full_text.splitlines(keepends=True)
    lines = []          # [(lineno, linetext_keepends)]
    line_offsets = []   # 每行起始全局偏移
    off = 0
    for idx, ltext in enumerate(raw_lines, start=1):
        lines.append((idx, ltext))
        line_offsets.append(off)
        off += len(ltext)

    blocks = build_blocks(lines)

    sentences = []
    markers = []
    s_seq = 0
    p_seq = 0
    m_seq = 0
    ref_lines = 0

    for zone, blk in blocks:
        if zone in ("references", "heading"):
            if zone == "references":
                ref_lines += len(blk)
            continue
        p_seq += 1
        pid = "P%03d" % p_seq
        blk_start = line_offsets[blk[0][0] - 1]
        blk_text = "".join(t for _, t in blk)
        spans = split_sentences(blk_text)
        for (a, b) in spans:
            s_seq += 1
            sid = "S%03d" % s_seq
            # 让 char_start/char_end 与 text 严格对齐（剥离首尾空白/换行）
            seg_full = blk_text[a:b]
            a2 = a + (len(seg_full) - len(seg_full.lstrip()))
            b2 = a + len(seg_full.rstrip())
            seg = blk_text[a2:b2]
            gstart = blk_start + a2
            gend = blk_start + b2
            line_start = blk[0][0] + blk_text[:a2].count("\n")
            line_end = blk[0][0] + blk_text[:b2].count("\n")
            cues, needs_support = detect_cues(seg)
            sentences.append({
                "id": sid,
                "paragraph": pid,
                "zone": zone,
                "text": seg,
                "line_start": line_start,
                "line_end": line_end,
                "char_start": gstart,
                "char_end": gend,
                "cues": cues,
                "needs_support": needs_support,
            })
        # 标记抽取（正文/图注/脚注区；参考文献区已排除）
        for regex, kind in ((BRACKET_RE, "numeric"), (AUTHORYEAR_RE, "author-year")):
            for m in regex.finditer(blk_text):
                raw = m.group(0)
                if kind == "author-year" and not re.search(r"[A-Za-z一-鿿]", raw):
                    continue
                gpos = blk_start + m.start()
                # 所属句
                sid = None
                for s in sentences:
                    if s["char_start"] <= gpos < s["char_end"]:
                        sid = s["id"]
                        break
                # 行号与列号
                lno = blk[0][0] + blk_text[:m.start()].count("\n")
                lstart = blk_text.rfind("\n", 0, m.start()) + 1
                col = m.start() - lstart + 1
                m_seq += 1
                refs = expand_refs(raw) if kind == "numeric" else raw
                markers.append({
                    "id": "M%03d" % m_seq,
                    "raw": raw,
                    "kind": kind,
                    "refs": refs,
                    "line": lno,
                    "col": col,
                    "sentence": sid,
                    "paragraph": pid,
                    "zone": zone,
                })

    markers.sort(key=lambda m: (m["line"], m["col"]))
    for i, m in enumerate(markers, start=1):
        m["id"] = "M%03d" % i

    stats = {
        "sentences": len(sentences),
        "markers": len(markers),
        "paragraphs": p_seq,
        "references_lines_excluded": ref_lines,
    }
    return sentences, markers, full_text, stats


def main():
    ap = argparse.ArgumentParser(description="论断切分与标记清点（placement-surgeon 阶段 1）")
    ap.add_argument("--manuscript", required=True, help="UTF-8 文本/Markdown 稿件")
    ap.add_argument("--out", required=True, help="输出目录")
    args = ap.parse_args()

    if not os.path.isfile(args.manuscript):
        print("错误：稿件不存在：%s" % args.manuscript, file=sys.stderr)
        return 2
    sentences, markers, _text, stats = scan_manuscript(args.manuscript)

    os.makedirs(args.out, exist_ok=True)
    sp = os.path.join(args.out, "sentences.jsonl")
    mp = os.path.join(args.out, "markers.jsonl")
    with open(sp, "w", encoding="utf-8") as fh:
        for s in sentences:
            fh.write(json.dumps(s, ensure_ascii=False) + "\n")
    with open(mp, "w", encoding="utf-8") as fh:
        for m in markers:
            fh.write(json.dumps(m, ensure_ascii=False) + "\n")
    print(json.dumps({"sentences_jsonl": sp, "markers_jsonl": mp,
                      "stats": stats}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
