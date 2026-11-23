#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""extract_pages.py — PDF/纯文本 → 分页文本 pages.jsonl

用途
----
把论文材料统一为带页码的文本层，供 quote_audit.py / num_drift.py 做保真机检。
- PDF 输入：调用外部命令 pdftotext -layout（Poppler），按 \\f 分页符切页。
- .txt 输入：按 "=== PAGE n ===" 标记切页；无标记时按每 ~3000 字符虚拟分页。

输出 pages.jsonl：每行一个 JSON 对象：
  {"page": n, "chars": m, "text": "...", "suspect_scan": true?,
   "printed_page": 12|null, "header_lines": [...], "footer_lines": [...]}

退出码
------
0  成功（可能含 suspect_scan 警告）
1  运行失败（文件不存在 / pdftotext 缺失或报错 / 输出无法写出）
2  命令行用法错误（argparse）

pdftotext 缺失时的降级：仅支持 .txt 输入，PDF 输入会以退出码 1 报错并
提示改用纯文本或安装 Poppler。绝不静默吞掉该失败。
"""

import argparse
import json
import os
import re
import shutil
import subprocess
import sys

DEFAULT_MAX_CHARS = 3000
SUSPECT_SCAN_CHARS = 50

PAGE_MARKER_RE = re.compile(r"^\s*===\s*PAGE\s+(\d+)\s*===\s*$", re.MULTILINE)


def guess_printed_page(header_lines, footer_lines):
    """从页眉/页脚候选行猜印刷页码。返回 int 或 None。"""
    candidates = list(footer_lines) + list(header_lines)  # 页脚页码更常见
    for line in candidates:
        s = line.strip()
        m = re.match(r"^[-–—\s]*第?\s*(\d{1,4})\s*页\s*[-–—\s]*$", s)
        if m:
            return int(m.group(1))
        m = re.match(r"^[-–—\s]*[Pp]age\s+(\d{1,4})\s*$", s)
        if m:
            return int(m.group(1))
        m = re.match(r"^(\d{1,4})\s*[/／|]\s*\d{1,4}$", s)  # "12 / 34"
        if m:
            return int(m.group(1))
        m = re.match(r"^(\d{1,4})$", s)  # 孤立的短数字行
        if m:
            return int(m.group(1))
    return None


def make_page_record(index, text):
    lines = [ln for ln in text.splitlines() if ln.strip()]
    header_lines = [ln.strip() for ln in lines[:2]]
    footer_lines = [ln.strip() for ln in lines[-2:]] if lines else []
    rec = {
        "page": index,
        "chars": len(text),
        "text": text,
        "printed_page": guess_printed_page(header_lines, footer_lines),
        "header_lines": header_lines,
        "footer_lines": footer_lines,
    }
    if len(text.strip()) < SUSPECT_SCAN_CHARS:
        rec["suspect_scan"] = True
    return rec


def extract_from_pdf(path):
    """用 pdftotext -layout 抽取；返回页文本列表。"""
    pdftotext = shutil.which("pdftotext")
    if pdftotext is None:
        raise RuntimeError(
            "未找到 pdftotext（Poppler）。降级方案：把论文转为带 '=== PAGE n ===' "
            "标记的 .txt 后重试；扫描件需先 OCR（本脚本不做 OCR，见 SKILL.md 异常处理表）。"
        )
    proc = subprocess.run(
        [pdftotext, "-layout", path, "-"],
        capture_output=True,
        timeout=120,
    )
    if proc.returncode != 0:
        err = proc.stderr.decode("utf-8", errors="replace").strip()
        raise RuntimeError(f"pdftotext 执行失败（exit {proc.returncode}）：{err}")
    raw = proc.stdout.decode("utf-8", errors="replace")
    pages = raw.split("\f")
    # pdftotext 通常在末尾多产生一个空页
    pages = [p for p in pages]
    if pages and not pages[-1].strip():
        pages = pages[:-1]
    if not pages:
        raise RuntimeError("pdftotext 未产出任何文本页（可能是纯扫描件，无文本层）。")
    return pages


def extract_from_txt(path, max_chars):
    with open(path, "r", encoding="utf-8", errors="replace") as f:
        raw = f.read()
    marks = list(PAGE_MARKER_RE.finditer(raw))
    pages = []
    if marks:
        for i, mk in enumerate(marks):
            start = mk.end()
            end = marks[i + 1].start() if i + 1 < len(marks) else len(raw)
            pages.append(raw[start:end].strip("\n"))
    else:
        # 虚拟分页：每 max_chars 字符一页，尽量在换行处断开
        buf, start = [], 0
        i = 0
        n = len(raw)
        while i < n:
            j = min(i + max_chars, n)
            if j < n:
                nl = raw.rfind("\n", i, j)
                if nl > i + max_chars // 2:
                    j = nl
            pages.append(raw[i:j])
            i = j
    return [p for p in pages] or [""]


def main(argv=None):
    ap = argparse.ArgumentParser(
        description="PDF/纯文本 → 分页文本 pages.jsonl（保真机检的上游数据层）",
        epilog="退出码：0 成功；1 运行失败；2 用法错误。",
    )
    ap.add_argument("--input", "-i", required=True, help="输入 PDF 或 .txt 路径")
    ap.add_argument(
        "--output",
        "-o",
        default="pages.jsonl",
        help="输出 pages.jsonl 路径（默认 ./pages.jsonl）",
    )
    ap.add_argument(
        "--max-chars",
        type=int,
        default=DEFAULT_MAX_CHARS,
        help=f"无页码标记的 .txt 虚拟分页字符数（默认 {DEFAULT_MAX_CHARS}）",
    )
    args = ap.parse_args(argv)

    if not os.path.isfile(args.input):
        print(f"错误：输入文件不存在：{args.input}", file=sys.stderr)
        return 1

    lower = args.input.lower()
    try:
        if lower.endswith(".pdf"):
            raw_pages = extract_from_pdf(args.input)
            source_kind = "pdf(pdftotext -layout)"
        else:
            raw_pages = extract_from_txt(args.input, args.max_chars)
            source_kind = "txt(页标记/虚拟分页)"
    except RuntimeError as e:
        print(f"错误：{e}", file=sys.stderr)
        return 1
    except subprocess.TimeoutExpired:
        print("错误：pdftotext 超时（120s）。", file=sys.stderr)
        return 1

    records = []
    suspect = 0
    for idx, text in enumerate(raw_pages, start=1):
        rec = make_page_record(idx, text)
        if rec.get("suspect_scan"):
            suspect += 1
        records.append(rec)

    out = {"_meta": {
        "generator": "extract_pages.py",
        "source": os.path.abspath(args.input),
        "source_kind": source_kind,
        "total_pages": len(records),
        "suspect_scan_pages": suspect,
        "note": "page 为 PDF 物理页序（从 1 起）；printed_page 为页眉页脚猜测的印刷页码，可能为 null。",
    }}
    try:
        with open(args.output, "w", encoding="utf-8") as f:
            f.write(json.dumps(out, ensure_ascii=False) + "\n")
            for rec in records:
                f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    except OSError as e:
        print(f"错误：无法写出 {args.output}：{e}", file=sys.stderr)
        return 1

    print(f"[extract_pages] 来源={source_kind} 页数={len(records)} "
          f"疑似扫描页={suspect} → {args.output}")
    if suspect:
        print("警告：存在 chars<50 的页（suspect_scan=true），可能是扫描页，"
              "这些页上的 quote 将无法通过机检，需人工处理。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
