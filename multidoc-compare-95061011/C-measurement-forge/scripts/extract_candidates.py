#!/usr/bin/env python3
"""extract_candidates.py — 从段落索引或裸文本语料中自动提出候选测量记录。

输入(二选一):
  --paras FILE.jsonl   每行 {"document_id","paragraph_id","text"} 的段落索引
  --corpus FILE...     一个或多个 .md/.txt 文件; 空行分段, 自动建索引
                       document_id 取文件主名, paragraph_id 自动编号 "P001"...; 可用 --doc-prefix
输出:
  -o candidates.jsonl  每行一条候选: {candidate_id, document_id, paragraph_id, quote(所在句,
                       逐字), value_raw, value, unit, unit_status, window(整段),
                       condition_hints, status: "proposed"}

抽取策略: 数值正则命中后, 取其后的单位候选子串, 用 units.parse_unit 最长可解析前缀判定
单位; 解析失败保留原文并标 unit_status=unparsed(上层按 unregistered 处置: 不换算)。

agent 职责: 逐条确认/丢弃(status), 补 quantity_kind 与 metric_definition(口径随值走),
核对 quote 逐字。本脚本只提候选, 不做判读。
"""
import argparse
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from units import parse_unit  # noqa: E402

NUM_RE = re.compile(r"(?<![\w.])(\d+(?:\.\d+)?|\.\d+)(?:[eE][-+]?\d+)?")
# 单位候选子串: 紧跟数字的字母/符号段, 允许一次 '/' 复合与上标/负指数写法
UNIT_TAIL_RE = re.compile(
    r"^[ \t]*([A-Za-zµμ%‰°℃Ω·*]+(?:\^?-?\d+|[⁻¹²³⁴⁵⁶⁷⁸⁹⁰]+)?"
    r"(?:\s*/\s*[A-Za-zµμ]+(?:\^?-?\d+|[⁻¹²³]+)?|"
    r"\s+[A-Za-zµμ]+(?:\^?-?\d+|[⁻¹²³]+)?)*)"
)
CONDITION_KEYWORDS = [
    "catalyst", "dosage", "dose", "concentration", "C0", "initial", "pH",
    "temperature", "°C", "℃", "room temperature", "light", "lamp", "Xe", "xenon",
    "LED", "UV", "visible", "wavelength", "nm", "irradiation", "irradiated",
    "under", "stirring", "rpm", "aeration", "dark", "adsorption", "PMS", "H2O2",
    "scavenger", "kinetic", "pseudo-first-order", "reactor", "volume", "mL",
]

SENT_SPLIT_RE = re.compile(r"(?<=[.!?。！？;；])\s+|\n+")


def split_sentences(text):
    """粗糙分句, 保留原句字符串(逐字)。"""
    parts = SENT_SPLIT_RE.split(text)
    return [p for p in (x.strip() for x in parts) if p]


def longest_parseable_unit(tail: str):
    """在数字后文本 tail 中找最长可解析单位前缀。返回 (unit_str, parsed) 或 (None, None)。"""
    m = UNIT_TAIL_RE.match(tail)
    cand = m.group(1).strip() if m else ""
    if not cand:
        return None, None
    cand = cand.rstrip(".,;:)]}")
    # 从长到短按字符回退, 首个 parse 成功的前缀胜出
    s = cand
    while s:
        p = parse_unit(s)
        if p is not None:
            return s, p
        s = s[:-1].rstrip()
    return cand, None  # 有候选但不可解析 -> 保留原文


def condition_hints(paragraph_text: str):
    low = paragraph_text.lower()
    hits = []
    for kw in CONDITION_KEYWORDS:
        if kw.lower() in low:
            hits.append(kw)
    return hits


def iter_paragraphs_from_jsonl(path):
    with open(path, "r", encoding="utf-8") as f:
        for ln, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            rec = json.loads(line)
            doc = rec.get("document_id") or rec.get("source_document_id") or "UNKNOWN"
            pid = rec.get("paragraph_id") or f"P{ln:03d}"
            text = rec.get("text", "")
            yield doc, pid, text


def iter_paragraphs_from_corpus(paths, doc_prefix=None):
    for path in paths:
        base = os.path.splitext(os.path.basename(path))[0]
        doc = f"{doc_prefix}{base}" if doc_prefix else base
        with open(path, "r", encoding="utf-8") as f:
            content = f.read()
        blocks = [b.strip() for b in re.split(r"\n\s*\n", content) if b.strip()]
        for i, b in enumerate(blocks, 1):
            yield doc, f"P{i:03d}", re.sub(r"\s*\n\s*", " ", b)


def extract(paragraph_iter):
    n = 0
    for doc, pid, text in paragraph_iter:
        hints = condition_hints(text)
        for sent in split_sentences(text):
            for m in NUM_RE.finditer(sent):
                value_raw = m.group(0)
                try:
                    value = float(value_raw)
                except ValueError:
                    continue
                tail = sent[m.end():]
                unit, parsed = longest_parseable_unit(tail)
                if parsed is not None:
                    unit_status = "parsed"
                elif unit is not None:
                    unit_status = "unparsed"
                else:
                    unit_status = "none"
                # 纯年份/编号等噪声: 无单位且数值像年份 -> 仍提出但提示
                noise = unit is None and re.fullmatch(r"(19|20)\d{2}", value_raw)
                n += 1
                yield {
                    "candidate_id": f"C-{n:04d}",
                    "document_id": doc,
                    "paragraph_id": pid,
                    "quote": sent,
                    "value_raw": value_raw,
                    "value": value,
                    "unit": unit,
                    "unit_status": unit_status,
                    "window": text,
                    "condition_hints": hints,
                    "suspected_noise": bool(noise),
                    "status": "proposed",
                }


def main(argv=None):
    ap = argparse.ArgumentParser(description="提出候选测量记录")
    ap.add_argument("--paras", help="段落索引 jsonl (document_id, paragraph_id, text)")
    ap.add_argument("--corpus", nargs="*", help="裸文本/markdown 语料文件")
    ap.add_argument("--doc-prefix", default=None, help="裸语料 document_id 前缀")
    ap.add_argument("-o", "--output", required=True, help="输出 candidates.jsonl")
    args = ap.parse_args(argv)

    if not args.paras and not args.corpus:
        ap.error("必须给 --paras 或 --corpus")
    if args.paras:
        it = iter_paragraphs_from_jsonl(args.paras)
    else:
        it = iter_paragraphs_from_corpus(args.corpus, args.doc_prefix)

    count = 0
    with open(args.output, "w", encoding="utf-8") as out:
        for cand in extract(it):
            out.write(json.dumps(cand, ensure_ascii=False) + "\n")
            count += 1
    print(f"extract_candidates: wrote {count} candidates -> {args.output}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
