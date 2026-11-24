#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
extract_refs.py — 从论文纯文本（.txt，pdftotext 预抽或 /input 直接给的文本）切分参考文献表，
正则抽取字段初值（作者/年份/标题/期刊/DOI），并抓取正文引文标记 [n] 的语境句。

输出 refs.json：
  refs[]      : index, marker_style, raw 原文, offset/page 起始位置, fields{authors,year,title,journal,doi}
  citations[] : marker, numbers[], context 语境句, offset/page

设计纪律：
  * 仅 Python3 标准库；确定性（同一输入同一输出，不含时间戳）；
  * 抽取结果是"字段初值"，供 lint_refs.py / crossref_check.py 与 Agent 复核，不是最终结论；
  * 找不到参考文献章节、条目为空、字段缺失等情况一律 exit 0 并在 notes 中说明（缺键不崩）。

用法：
  python3 extract_refs.py --input paper.txt --output refs.json
"""
import argparse
import json
import re
import sys

# 参考文献章节标题（独立一行）
REF_HEADING = re.compile(
    r'^[ \t]*(references|参考文献|参考书目|works[ \t]+cited|bibliography)[ \t]*[:：]?[ \t]*$',
    re.IGNORECASE | re.MULTILINE,
)
# 条目编号：[1] 或 1. 或 1、或 1)
ENTRY_MARK = re.compile(
    r'^[ \t]*(?:\[(?P<br>\d{1,3})\]|(?P<plain>\d{1,3})[\.、\)])[ \t]+',
    re.MULTILINE,
)
DOI_TOKEN = re.compile(r'10\.\S+', re.IGNORECASE)
YEAR_PAREN = re.compile(r'[\(（]((?:19|20)\d{2})[a-z]?[\)）]')
YEAR_ANY = re.compile(r'\b((?:19|20)\d{2})\b')
CITE_MARK = re.compile(r'\[(\d{1,3}(?:\s*[-–—,，]\s*\d{1,3})*)\]')
SENT_END = set('。．.!！?？;；\n\f')


def page_of(text, offset):
    """pdftotext 输出以 \f 分页；无 \f 时全部为第 1 页。"""
    return text[:offset].count('\f') + 1


def clean_oneline(s):
    return re.sub(r'\s+', ' ', s).strip()


def parse_fields(raw):
    """从单条文献原文抽取字段初值。任何失败都返回 None 字段，绝不抛异常。"""
    s = clean_oneline(raw)
    fields = {"authors": None, "year": None, "title": None, "journal": None, "doi": None}
    if not s:
        return fields

    work = s
    m = DOI_TOKEN.search(work)
    if m:
        doi = m.group(0).rstrip('.,;，。；')
        fields["doi"] = doi
        # 连同 doi: / DOI: / https://doi.org/ 前缀一起从工作串移除
        work = re.sub(r'(?i)(doi\s*[:：]?\s*|https?://(?:dx\.)?doi\.org/)?' + re.escape(m.group(0)),
                      ' ', work, count=1)
        work = clean_oneline(work)

    my = YEAR_PAREN.search(work) or YEAR_ANY.search(work)
    if my:
        fields["year"] = int(my.group(1))

    # 按句段切分：作者. 标题. 期刊, 年, 卷: 页.
    segs = [x.strip(' .,，') for x in re.split(r'\.\s+', work) if x.strip(' .,，')]
    if segs:
        authors = segs[0]
        authors = re.sub(r'[\(（](?:19|20)\d{2}[a-z]?[\)）]\s*$', '', authors).strip(' .,，')
        fields["authors"] = authors or None
    if len(segs) >= 2:
        fields["title"] = segs[1] or None
    if len(segs) >= 3:
        journal = re.split(r',\s*(?=(?:19|20)\d{2}\b)', segs[2])[0].strip(' ,，')
        fields["journal"] = journal or None
    return fields


def split_entries(refs_text, base_offset, full_text):
    """按行首编号切分条目，返回 (entries, notes)。"""
    entries, notes = [], []
    marks = list(ENTRY_MARK.finditer(refs_text))
    if not marks:
        notes.append("references section found but no numbered entries matched; "
                     "entry splitting requires [n] / n. / n) style markers")
        return entries, notes
    for i, mk in enumerate(marks):
        start = mk.end()
        end = marks[i + 1].start() if i + 1 < len(marks) else len(refs_text)
        raw = refs_text[mk.start():end].strip()
        body = refs_text[start:end].strip()  # 去掉编号标记后的正文，供字段解析
        number = mk.group('br') or mk.group('plain')
        abs_off = base_offset + mk.start()
        entries.append({
            "index": int(number),
            "marker_style": "bracket" if mk.group('br') else "plain",
            "raw": raw,
            "offset": abs_off,
            "page": page_of(full_text, abs_off),
            "fields": parse_fields(body),
        })
    # 编号重复/缺号提示（不判违规，仅记录）
    idxs = [e["index"] for e in entries]
    if len(set(idxs)) != len(idxs):
        notes.append("duplicate entry numbers detected: %s" % sorted(idxs))
    if idxs and sorted(idxs) != list(range(min(idxs), max(idxs) + 1)):
        notes.append("entry numbering is not contiguous: %s" % sorted(idxs))
    return entries, notes


def sentence_context(body, start, end, limit=400):
    """截取包含引文标记的语境句（前后扩展到句界）。"""
    s = start
    while s > 0 and body[s - 1] not in SENT_END:
        s -= 1
    e = end
    while e < len(body) and body[e] not in SENT_END:
        e += 1
    if e < len(body):
        e += 1
    ctx = clean_oneline(body[s:e])
    if len(ctx) > limit:
        ctx = ctx[:limit] + '…'
    return ctx


def extract_citations(body, base_offset, full_text):
    cites = []
    for m in CITE_MARK.finditer(body):
        token = m.group(1)
        numbers = []
        for part in re.split(r'[,，]', token):
            part = part.strip()
            rm = re.match(r'^(\d{1,3})\s*[-–—]\s*(\d{1,3})$', part)
            if rm:
                numbers.extend(range(int(rm.group(1)), int(rm.group(2)) + 1))
            elif part.isdigit():
                numbers.append(int(part))
        cites.append({
            "marker": m.group(0),
            "numbers": numbers,
            "context": sentence_context(body, m.start(), m.end()),
            "offset": base_offset + m.start(),
            "page": page_of(full_text, base_offset + m.start()),
        })
    return cites


def main():
    ap = argparse.ArgumentParser(
        description="切分参考文献表并抽取字段初值 + 正文引文标记语境句，输出 refs.json。"
                    " 任何解析失败均 exit 0 并在 notes 说明。")
    ap.add_argument("--input", required=True, help="论文纯文本路径（.txt）")
    ap.add_argument("--output", required=True, help="输出 refs.json 路径")
    args = ap.parse_args()

    notes = []
    try:
        text = open(args.input, encoding="utf-8", errors="replace").read()
    except OSError as e:
        text = ""
        notes.append("cannot read input file: %s" % e)

    refs, citations = [], []
    section_found = False
    if text:
        hm = REF_HEADING.search(text)
        if hm:
            section_found = True
            body, refs_text = text[:hm.start()], text[hm.end():]
            refs, enotes = split_entries(refs_text, hm.end(), text)
            notes.extend(enotes)
            citations = extract_citations(body, 0, text)
        else:
            notes.append("no References/参考文献 heading found; "
                         "refs list empty, citations scanned over full text")
            citations = extract_citations(text, 0, text)

    out = {
        "tool": "extract_refs.py",
        "version": "1.0",
        "source_file": args.input,
        "references_section_found": section_found,
        "ref_count": len(refs),
        "citation_count": len(citations),
        "refs": refs,
        "citations": citations,
        "notes": notes,
        "caveat": "字段为正则抽取的初值，须由 lint/crossref 与人工复核后才可作结论。",
    }
    try:
        with open(args.output, "w", encoding="utf-8") as f:
            json.dump(out, f, ensure_ascii=False, indent=2)
    except OSError as e:
        print("cannot write output: %s" % e, file=sys.stderr)
        # 仍然 exit 0：缺键/路径问题不应让管线崩溃
    print("extract_refs: %d refs, %d citations -> %s" % (len(refs), len(citations), args.output))
    return 0


if __name__ == "__main__":
    sys.exit(main())
