#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
claim_segment.py — 权利要求文本的确定性结构化切分（仅用 Python 标准库）。

功能：
  1. 将权利要求文本切分为带编号的权利要求单元（按 1,2,3,... 顺序编号识别）；
  2. 判定每项权利要求为独立权利要求或从属权利要求（对 "claim N" / "权利要求N"
     等引用做正则检测）；
  3. 将权利要求切分为 前序(preamble) / 过渡语(transition) / 要素(elements)，
     要素按分号、编号子步骤以及 "wherein" / "其中" 从句进一步切分；
  4. 全部切分边界以字符偏移锚定源文本，quote 恒等于 text[span[0]:span[1]]；
  5. 无法切分的区域原样保留于 raw_regions，并置 segmentation_degraded: true；
  6. 检测已声明的 OCR 合并边界行（默认匹配 "OCR MERGE BOUNDARY" 字样），
     标记所有跨越边界的 span（crosses_ocr_boundary: true）。

退出码：0 = 正常完成（含降级情形，降级信息写入 JSON）；2 = 用法/输入错误。
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys

TOOL = "claim_segment.py"
VERSION = "1.0.0"

# 权利要求起始行：可选的 "权利要求"/"Claim" 前缀 + 序号 + 分隔符。
CLAIM_HEADER_RE = re.compile(
    r"^[ \t]*(?:(?:权利要求|Claim|CLAIM|claim)\s*)?(\d{1,3})\s*[\.、．:：]\s*(.*)$"
)

# 过渡语分两层：第一层为高置信过渡语；第一层无命中时才退到第二层。
TRANSITION_TIER1 = [
    "consisting essentially of",
    "consisting of",
    "comprising",
    "characterized in that",
    "characterised in that",
    "wherein the improvement comprises",
    "其特征在于",
    "其改进在于",
]
TRANSITION_TIER2 = [
    "containing",
    "including",
    "包含",
    "包括",
    "含有",
]

# 从属引用检测。
DEP_REF_RES = [
    re.compile(r"\bclaims?\s+(\d+(?:\s*(?:,|or|and|to|\-|–)\s*\d+)*)", re.IGNORECASE),
    re.compile(r"权利要求\s*(\d+(?:\s*[至到、,，或和]\s*\d+)*)"),
]
ANY_PRECEDING_RE = re.compile(
    r"\bany\s+(?:one\s+of\s+the\s+|of\s+the\s+)?preceding\s+claims?\b", re.IGNORECASE
)

# 要素切分：硬分隔（分号）与软分隔（wherein/其中/编号子步骤起点）。
SPLIT_HARD_RE = re.compile(r"[;；]")
SPLIT_SOFT_RE = re.compile(
    r"\bwherein\b|其中|\(\s*[A-Za-z0-9]{1,4}\s*\)|\b\d{1,2}\)", re.IGNORECASE
)

DEFAULT_BOUNDARY_RE = r"OCR[ -]?MERGE[ -]?BOUNDARY"


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def trim_span(text: str, s: int, e: int):
    while s < e and text[s].isspace():
        s += 1
    while e > s and text[e - 1].isspace():
        e -= 1
    return s, e


def _phrase_search(text: str, start: int, end: int, phrase: str):
    seg = text[start:end]
    if phrase.isascii():
        m = re.search(r"\b" + re.escape(phrase) + r"\b", seg, re.IGNORECASE)
    else:
        m = re.search(re.escape(phrase), seg)
    return m


def find_transition(text: str, start: int, end: int):
    """在 [start,end) 内寻找过渡语；先第一层后第二层；同层取最左，并列取最长。"""
    for tier in (TRANSITION_TIER1, TRANSITION_TIER2):
        best = None
        for ph in tier:
            m = _phrase_search(text, start, end, ph)
            if m:
                s, e = start + m.start(), start + m.end()
                if best is None or s < best[0] or (s == best[0] and (e - s) > (best[1] - best[0])):
                    best = (s, e, text[s:e])
        if best is not None:
            return best
    return None


def split_elements(text: str, start: int, end: int):
    """把 [start,end) 切分为要素 span 列表；每个 quote 都是原文逐字子串。"""
    events = []  # (pos, kind, next_start)
    for m in SPLIT_HARD_RE.finditer(text, start, end):
        events.append((m.start(), "hard", m.end()))
    for m in SPLIT_SOFT_RE.finditer(text, start, end):
        events.append((m.start(), "soft", m.start()))
    # 同一位置既有分号又有软分隔时，先按分号切。
    events.sort(key=lambda x: (x[0], 0 if x[1] == "hard" else 1))

    raw_spans = []
    cur = start
    for pos, kind, nxt in events:
        if pos < cur:
            continue  # 软分隔落在已被消费的区域内
        raw_spans.append((cur, pos))
        cur = nxt
    raw_spans.append((cur, end))

    elements = []
    for s, e in raw_spans:
        s2, e2 = trim_span(text, s, e)
        while s2 < e2 and text[s2] in ":：":  # 过渡语后的冒号不并入首个要素
            s2 += 1
        s2, e2 = trim_span(text, s2, e2)
        if s2 >= e2:
            continue
        q = text[s2:e2]
        if not re.search(r"[\w一-鿿]", q):
            continue  # 纯标点碎片（如残留逗号）不构成要素
        if q in ("and", "and", "以及", "和", "并且"):
            continue
        low = q.lower()
        if low.startswith("wherein") or q.startswith("其中"):
            kind2 = "wherein_clause"
        elif re.match(r"^\(\s*[A-Za-z0-9]{1,4}\s*\)", q) or re.match(r"^\d{1,2}\)", q):
            kind2 = "substep"
        else:
            kind2 = "element"
        elements.append(
            {"index": len(elements) + 1, "kind": kind2, "span": [s2, e2], "quote": q}
        )
    return elements


def classify_claim(text: str, s: int, e: int):
    seg = text[s:e]
    refs = []
    ref_span = None
    for rx in DEP_REF_RES:
        m = rx.search(seg)
        if m:
            refs += [int(x) for x in re.findall(r"\d+", m.group(1))]
            if ref_span is None:
                ref_span = (s + m.start(), s + m.end())
    any_prec = bool(ANY_PRECEDING_RE.search(seg))
    refs = sorted(set(refs))
    dependent = bool(refs) or any_prec
    return ("dependent" if dependent else "independent"), refs, any_prec, ref_span


def find_boundaries(text: str, pattern: str):
    try:
        rx = re.compile(pattern)
    except re.error as exc:
        raise ValueError("非法的边界正则表达式: %s" % exc)
    out = []
    for m in rx.finditer(text):
        ls = text.rfind("\n", 0, m.start()) + 1
        le = text.find("\n", m.end())
        if le == -1:
            le = len(text)
        s2, e2 = trim_span(text, ls, le)
        out.append({"span": [s2, e2], "quote": text[s2:e2]})
    return out


def _crosses(span, bounds):
    return any(span[0] < b["span"][1] and b["span"][0] < span[1] for b in bounds)


def segment_text(text: str, boundary_pattern: str = DEFAULT_BOUNDARY_RE) -> dict:
    bounds = find_boundaries(text, boundary_pattern)

    # 1) 识别权利要求起始行（序号必须自 1 起连续递增）。
    headers = []  # (number, header_start, content_start)
    expected = 1
    offset = 0
    for line in text.split("\n"):
        m = CLAIM_HEADER_RE.match(line)
        if m and int(m.group(1)) == expected:
            header_start = offset + m.start(0)
            content_start = offset + m.start(2)
            headers.append((expected, header_start, content_start))
            expected += 1
        offset += len(line) + 1  # +1 for the '\n' removed by split

    result = {
        "tool": TOOL,
        "tool_version": VERSION,
        "text_sha256": sha256_text(text),
        "text_length": len(text),
        "num_claims": 0,
        "segmentation_degraded": False,
        "contains_ocr_boundary": bool(bounds),
        "ocr_boundaries": bounds,
        "front_matter": None,
        "claims": [],
        "raw_regions": [],
        "notes": [],
    }

    if not headers:
        s, e = trim_span(text, 0, len(text))
        result["segmentation_degraded"] = True
        result["raw_regions"].append(
            {
                "span": [s, e],
                "quote": text[s:e],
                "reason": "no_claim_boundaries",
                "note": "未识别到任何按 1,2,3,... 顺序编号的权利要求起始行；全文原样保留。",
            }
        )
        result["notes"].append("切分降级：未发现权利要求编号边界。")
        return result

    # 前导材料（标题、说明行等）不计入权利要求，但记录其 span。
    fm_s, fm_e = trim_span(text, 0, headers[0][1])
    if fm_s < fm_e:
        result["front_matter"] = {
            "span": [fm_s, fm_e],
            "quote": text[fm_s:fm_e],
            "note": "权利要求 1 之前的材料，未参与切分。",
        }

    # 2) 逐项切分。
    for i, (num, h_start, c_start) in enumerate(headers):
        c_end = headers[i + 1][1] if i + 1 < len(headers) else len(text)
        h_end = c_end
        h_s2, h_e2 = trim_span(text, h_start, h_end)
        c_s2, _ = trim_span(text, c_start, h_end)

        claim = {
            "number": num,
            "span": [h_s2, h_e2],
            "quote": text[h_s2:h_e2],
            "content_span": [c_s2, h_e2],
            "type": None,
            "references": [],
            "any_preceding_reference": False,
            "preamble": None,
            "transition": None,
            "elements": [],
            "status": "ok",
            "segmentation_partial": False,
            "crosses_ocr_boundary": _crosses([h_s2, h_e2], bounds),
        }

        ctype, refs, any_prec, ref_span = classify_claim(text, h_s2, h_e2)
        claim["type"] = ctype
        claim["references"] = refs
        claim["any_preceding_reference"] = any_prec

        trans = find_transition(text, c_s2, h_e2)
        if trans is not None:
            t_s, t_e, t_q = trans
            p_s, p_e = trim_span(text, c_s2, t_s)
            if p_s < p_e:
                claim["preamble"] = {"span": [p_s, p_e], "quote": text[p_s:p_e]}
            claim["transition"] = {
                "phrase_matched": t_q,
                "span": [t_s, t_e],
                "quote": t_q,
            }
            claim["elements"] = split_elements(text, t_e, h_e2)
        elif ctype == "dependent" and ref_span is not None:
            # 从属权利要求常无过渡语：以引用部分为前序，其余按 wherein/分号切。
            p_s, p_e = trim_span(text, c_s2, ref_span[1])
            claim["preamble"] = {"span": [p_s, p_e], "quote": text[p_s:p_e]}
            claim["elements"] = split_elements(text, ref_span[1], h_e2)
            claim["status"] = "ok_no_transition_dependent"
        else:
            # 无法定位过渡语：整体保留，标记部分切分。
            p_s, p_e = trim_span(text, c_s2, h_e2)
            if p_s < p_e:
                claim["preamble"] = {"span": [p_s, p_e], "quote": text[p_s:p_e]}
            claim["status"] = "no_transition"
            claim["segmentation_partial"] = True
            result["segmentation_degraded"] = True
            result["notes"].append(
                "权利要求 %d 未定位到过渡语，仅保留整体文本（raw retained）。" % num
            )

        for el in claim["elements"]:
            el["crosses_ocr_boundary"] = _crosses(el["span"], bounds)

        result["claims"].append(claim)

    result["num_claims"] = len(result["claims"])
    if any(c["crosses_ocr_boundary"] for c in result["claims"]):
        result["notes"].append(
            "存在跨越已声明 OCR 合并边界的权利要求 span；相关边界偏移见 ocr_boundaries。"
        )
    return result


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        description="权利要求文本的确定性结构化切分（输出带字符 span 与逐字 quote 的 JSON）。"
    )
    ap.add_argument("--input", required=True, help="权利要求纯文本文件路径（UTF-8）。")
    ap.add_argument("--output", default=None, help="输出 JSON 路径；缺省写到标准输出。")
    ap.add_argument(
        "--boundary-regex",
        default=DEFAULT_BOUNDARY_RE,
        help="OCR 合并边界行的正则表达式（默认：%(default)s）。",
    )
    args = ap.parse_args(argv)

    try:
        with open(args.input, "r", encoding="utf-8") as fh:
            text = fh.read()
    except OSError as exc:
        print("用法/输入错误：无法读取输入文件 %s：%s" % (args.input, exc), file=sys.stderr)
        return 2

    try:
        result = segment_text(text, args.boundary_regex)
    except ValueError as exc:
        print("用法错误：%s" % exc, file=sys.stderr)
        return 2

    result["source_path"] = args.input
    payload = json.dumps(result, ensure_ascii=False, indent=2)
    if args.output:
        try:
            with open(args.output, "w", encoding="utf-8") as fh:
                fh.write(payload + "\n")
        except OSError as exc:
            print("用法/输入错误：无法写入输出文件 %s：%s" % (args.output, exc), file=sys.stderr)
            return 2
    else:
        sys.stdout.write(payload + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
