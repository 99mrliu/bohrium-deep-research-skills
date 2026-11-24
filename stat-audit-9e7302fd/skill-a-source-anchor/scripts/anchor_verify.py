#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""anchor_verify.py — 锚定核验门:无锚不立案。

对每条候选发现的 `quote`(逐字摘录)在原文中做机器核验。只有通过核验的发现
才允许进入审查单;未通过的写入 rejects 文件留痕,最终以非零退出码告知上游。

规范化规则(引用匹配前对原文与 quote 施加同一变换,规则公开、可复现):
  1. 全角字符(FF01–FF5E)转半角;表列特殊全角标点(、。「」""''—–等)映射到半角;
  2. 全角空格 U+3000 视为空白;
  3. 任意连续空白(空格/\\t/\\n/\\f/全角空格)折叠为单个半角空格,首尾空白去除。
规范化过程维护【规范化字符下标 → 原始文本字符下标】的映射表(可逆),
因此返回的 char_start/char_end 始终索引【原始提取文本】,而不是规范化后的文本。

定位输出:借助 anchors.jsonl 把命中的原始偏移换算为 {page, line, end_page, end_line},
并截取命中点前后各 40 字符作为 context 供人工复核。

输入(三选二):
  --findings  候选发现 JSONL(必需),每行至少含 "quote" 字段,可选 approx_page/hint
  --anchors   anchors.jsonl(必需),由 pdf_to_anchored_text.py 生成
  --raw       原始提取文本(推荐;与 anchors.jsonl 偏移严格对应)
  --text      锚点文本(无 --raw 时使用;按固定 12 字符前缀剥离标记还原,
              还原长度将与 anchors.jsonl 校验,不一致即报错退出 2,绝不带病核验)
输出:
  --out       通过核验的发现 JSONL(追加 anchor{page,line,end_page,end_line,
              char_start,char_end,context} 与 verdict="verified")
  --rejects   未通过核验的发现 JSONL(追加 verdict="failed" 与 reject_reason)
退出码: 0 = 全部通过; 1 = 存在未通过项(门是真实的); 2 = 输入/运行错误。
"""
from __future__ import annotations

import argparse
import bisect
import json
import os
import re
import sys

PAGE_SEP = "\f"
MARKER_RE = re.compile(r"^\[P\d{3} L\d{3}\] ")
MARKER_WIDTH = 12

# 特殊全角标点 → 半角(FF01–FF5E 区间之外的常用项)
SPECIAL_MAP = {
    "、": ",", "。": ".", "“": '"', "”": '"', "‘": "'", "’": "'",
    "【": "[", "】": "]", "《": "<", "》": ">", "—": "-", "–": "-",
    "…": "...", "～": "~", "「": '"', "」": '"', "〔": "[", "〕": "]",
    "·": ".",
}


def to_halfwidth(ch: str) -> str:
    o = ord(ch)
    if o == 0x3000:  # 全角空格 → 普通空格(随后按空白折叠)
        return " "
    if 0xFF01 <= o <= 0xFF5E:
        return chr(o - 0xFEE0)
    return SPECIAL_MAP.get(ch, ch)


def normalize_with_map(text: str):
    """返回 (规范化文本, 映射表)。映射表[i] = 规范化第 i 字符在原文中的下标。"""
    out = []
    imap = []
    for i, ch in enumerate(text):
        for c in to_halfwidth(ch):
            if c.isspace():
                if out and out[-1] != " ":
                    out.append(" ")
                    imap.append(i)
            else:
                out.append(c)
                imap.append(i)
    while out and out[-1] == " ":
        out.pop()
        imap.pop()
    return "".join(out), imap


def strip_markers(anchored: str) -> str:
    """剥离锚点文本的固定宽度行首标记,还原原始文本。"""
    pages = anchored.split(PAGE_SEP)
    raw_pages = []
    for page in pages:
        raw_lines = []
        for ln in page.split("\n"):
            if MARKER_RE.match(ln):
                raw_lines.append(ln[MARKER_WIDTH:])
            else:
                raw_lines.append(ln)
        raw_pages.append("\n".join(raw_lines))
    return PAGE_SEP.join(raw_pages)


def load_anchors(path: str):
    records = []
    with open(path, "r", encoding="utf-8") as fh:
        for ln in fh:
            ln = ln.strip()
            if ln:
                records.append(json.loads(ln))
    if not records:
        sys.stderr.write("错误: anchors.jsonl 为空: %s\n" % path)
        sys.exit(2)
    records.sort(key=lambda r: r["char_start"])
    return records


def locate(records, starts, offset: int):
    """在 anchors 记录中查找包含原始偏移 offset 的行,返回 (page, line)。"""
    idx = bisect.bisect_right(starts, offset) - 1
    idx = max(0, min(idx, len(records) - 1))
    rec = records[idx]
    return rec["page"], rec["line"]


def verify(findings_path, raw_text, records):
    ntext, nmap = normalize_with_map(raw_text)
    starts = [r["char_start"] for r in records]
    verified = []
    rejects = []

    with open(findings_path, "r", encoding="utf-8") as fh:
        for lineno, ln in enumerate(fh, start=1):
            ln = ln.strip()
            if not ln:
                continue
            try:
                finding = json.loads(ln)
            except json.JSONDecodeError as exc:
                rejects.append({"_line": lineno, "verdict": "failed",
                                "reject_reason": "JSONL 解析失败: %s" % exc})
                continue
            quote = finding.get("quote")
            if not isinstance(quote, str) or not quote.strip():
                finding["verdict"] = "failed"
                finding["reject_reason"] = "缺少非空 quote 字段:无逐字摘录不得立案"
                rejects.append(finding)
                continue
            nq, _ = normalize_with_map(quote)
            if not nq:
                finding["verdict"] = "failed"
                finding["reject_reason"] = "quote 规范化后为空(纯空白/纯标点)"
                rejects.append(finding)
                continue

            hits = []
            pos = ntext.find(nq)
            while pos != -1:
                hits.append(pos)
                pos = ntext.find(nq, pos + 1)
            if not hits:
                finding["verdict"] = "failed"
                finding["reject_reason"] = (
                    "quote 在规范化后的原文中无精确匹配;"
                    "请重新复制粘贴原文摘录,或将该发现降级为「待复核」"
                )
                rejects.append(finding)
                continue

            # 多义命中时优先采用 approx_page 提示;否则取首次命中并如实标注多义
            chosen = hits[0]
            ambiguous = len(hits) > 1
            hint = finding.get("approx_page") or finding.get("hint_page")
            if ambiguous and isinstance(hint, int):
                for h in hits:
                    p0, _ = locate(records, starts, nmap[h])
                    if p0 == hint:
                        chosen = h
                        ambiguous = False
                        break

            s = chosen
            e = chosen + len(nq)
            char_start = nmap[s]
            char_end = nmap[e - 1] + 1
            p0, l0 = locate(records, starts, char_start)
            p1, l1 = locate(records, starts, max(char_start, char_end - 1))
            ctx = raw_text[max(0, char_start - 40): char_end + 40]
            ctx = " ".join(ctx.split())
            finding["anchor"] = {
                "page": p0, "line": l0,
                "end_page": p1, "end_line": l1,
                "char_start": char_start, "char_end": char_end,
                "context": ctx,
                "occurrences": len(hits),
            }
            if ambiguous:
                finding["anchor"]["note"] = (
                    "该摘录在原文中出现 %d 次,取首次命中;如需特指请补 approx_page" % len(hits)
                )
            finding["verdict"] = "verified"
            verified.append(finding)
    return verified, rejects


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        description="锚定核验门:逐字引用机器核验;存在未通过项时退出码为 1。"
    )
    ap.add_argument("--findings", required=True, help="候选发现 JSONL(每行含 quote 字段)")
    ap.add_argument("--anchors", required=True, help="anchors.jsonl(pdf_to_anchored_text.py 产物)")
    ap.add_argument("--raw", default=None, help="原始提取文本路径(推荐)")
    ap.add_argument("--text", default=None, help="锚点文本路径(无 --raw 时使用)")
    ap.add_argument("--out", required=True, help="通过核验的发现 JSONL 输出路径")
    ap.add_argument("--rejects", required=True, help="未通过项 JSONL 输出路径")
    args = ap.parse_args(argv)

    if not args.raw and not args.text:
        sys.stderr.write("错误: 必须提供 --raw(原始提取文本)或 --text(锚点文本)之一\n")
        return 2
    for p in [args.findings, args.anchors, args.raw or args.text]:
        if not os.path.isfile(p):
            sys.stderr.write("错误: 文件不存在: %s\n" % p)
            return 2

    try:
        if args.raw:
            with open(args.raw, "r", encoding="utf-8") as fh:
                raw_text = fh.read()
        else:
            with open(args.text, "r", encoding="utf-8") as fh:
                raw_text = strip_markers(fh.read())
    except UnicodeDecodeError as exc:
        sys.stderr.write("错误: 文本不是合法 UTF-8: %s\n" % exc)
        return 2

    records = load_anchors(args.anchors)
    max_end = max(r["char_end"] for r in records)
    if len(raw_text) < max_end:
        sys.stderr.write(
            "错误: 文本长度(%d)小于 anchors 最大偏移(%d),"
            "文本与锚点索引不对应(可能锚点文本被编辑导致还原失真);"
            "请改用 --raw 传入原始提取文本。\n" % (len(raw_text), max_end)
        )
        return 2

    verified, rejects = verify(args.findings, raw_text, records)

    try:
        with open(args.out, "w", encoding="utf-8") as fh:
            for item in verified:
                fh.write(json.dumps(item, ensure_ascii=False) + "\n")
        with open(args.rejects, "w", encoding="utf-8") as fh:
            for item in rejects:
                fh.write(json.dumps(item, ensure_ascii=False) + "\n")
    except OSError as exc:
        sys.stderr.write("错误: 输出写入失败: %s\n" % exc)
        return 2

    sys.stderr.write(
        "核验完成: 通过 %d 条, 拒绝 %d 条 -> %s , %s\n"
        % (len(verified), len(rejects), args.out, args.rejects)
    )
    return 1 if rejects else 0


if __name__ == "__main__":
    sys.exit(main())
