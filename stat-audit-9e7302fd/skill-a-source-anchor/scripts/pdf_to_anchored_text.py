#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""pdf_to_anchored_text.py — 提取论文全文并生成「带锚点文本」与「锚点索引」。

输入:
  - .txt 纯文本(通常由 `pdftotext -layout` 或 pdf-text-tool 预先生成;本技能示例即直接用 .txt)
  - .pdf 文件(本脚本通过 subprocess 调用系统 `pdftotext -layout`;
    若 pdftotext 不可用,打印清晰报错并以非零码退出,绝不静默伪造文本)

输出:
  1. 锚点文本(--text-out): 每行加固定宽度前缀 "[P<页:3位> L<行:3位>] ",页与页之间以换页符 \\f 分隔。
  2. 锚点索引(--anchors-out, JSONL): 每行一条
       {"page": <页码>, "line": <行号>, "char_start": <起>, "char_end": <止>}
     其中 char_start/char_end 索引的是【未加任何标记的原始提取文本】,
     与 anchor_verify.py 的还原文本逻辑互为逆运算。
  3. 可选 --raw-out: 同时落盘一份原始提取文本(推荐保留,供核验门直接使用,避免还原文本被编辑器改动)。

页码/行号固定 3 位宽度,前缀长度恒为 12 字符,保证锚点文本可无损还原为原始文本。
换页符 \\f 被识别为页边界(兼容 pdftotext 的分页输出)。

仅使用 Python 标准库。任何失败均以非零退出码结束:
  2 = 输入/环境错误(文件不存在、非 UTF-8、PDF 但无 pdftotext、pdftotext 执行失败)
  1 = 输出写入失败
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys

PAGE_SEP = "\f"          # 换页符,作为页边界
MARKER_WIDTH = 12        # "[P001 L003] " 的固定字符数


def extract_text(input_path: str) -> str:
    """读取输入文本;PDF 则调用 pdftotext -layout。失败时打印错误并退出码 2。"""
    if not os.path.isfile(input_path):
        sys.stderr.write("错误: 输入文件不存在: %s\n" % input_path)
        sys.exit(2)
    if input_path.lower().endswith(".pdf"):
        exe = shutil.which("pdftotext")
        if exe is None:
            sys.stderr.write(
                "错误: 输入为 PDF,但系统中未找到 pdftotext。\n"
                "请先安装 poppler(提供 pdftotext),或改用 pdf-text-tool 生成 .txt 后重试。\n"
            )
            sys.exit(2)
        proc = subprocess.run(
            [exe, "-layout", input_path, "-"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        if proc.returncode != 0:
            sys.stderr.write(
                "错误: pdftotext 执行失败(exit=%d): %s\n"
                % (proc.returncode, proc.stderr.decode("utf-8", "replace"))
            )
            sys.exit(2)
        # 解码失败的字节替换为 U+FFFD,交由 source_integrity.py 的乱码率检测诚实上报
        return proc.stdout.decode("utf-8", "replace")
    try:
        with open(input_path, "r", encoding="utf-8") as fh:
            return fh.read()
    except UnicodeDecodeError as exc:
        sys.stderr.write("错误: 输入文本不是合法 UTF-8: %s\n" % exc)
        sys.exit(2)


def build_anchored(text: str):
    """返回 (anchored_text, records)。records 的偏移量索引原始 text。"""
    pages = text.split(PAGE_SEP)
    anchored_pages = []
    records = []
    page_start = 0
    for pi, page in enumerate(pages, start=1):
        lines = page.split("\n")
        pos = page_start
        anchored_lines = []
        for li, line in enumerate(lines, start=1):
            anchored_lines.append("[P%03d L%03d] %s" % (pi, li, line))
            records.append(
                {"page": pi, "line": li, "char_start": pos, "char_end": pos + len(line)}
            )
            pos += len(line) + 1  # +1 为行尾 \n(末行的 +1 不被使用,由 page_start 重新对齐)
        anchored_pages.append("\n".join(anchored_lines))
        page_start += len(page) + 1  # +1 为被 split 消耗的页间 \f
    return PAGE_SEP.join(anchored_pages), records


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        description="提取论文全文并生成带锚点文本与 anchors.jsonl(stdlib-only)。"
    )
    ap.add_argument("input", help="输入文件:.txt(推荐)或 .pdf(需系统 pdftotext)")
    ap.add_argument("--text-out", default=None,
                    help="锚点文本输出路径(默认 <input>.anchored.txt)")
    ap.add_argument("--anchors-out", default=None,
                    help="锚点索引 JSONL 输出路径(默认 <input>.anchors.jsonl)")
    ap.add_argument("--raw-out", default=None,
                    help="可选:同时输出原始提取文本(推荐保留供核验门使用)")
    args = ap.parse_args(argv)

    text = extract_text(args.input)
    anchored, records = build_anchored(text)

    text_out = args.text_out or (args.input + ".anchored.txt")
    anchors_out = args.anchors_out or (args.input + ".anchors.jsonl")
    try:
        with open(text_out, "w", encoding="utf-8") as fh:
            fh.write(anchored)
        with open(anchors_out, "w", encoding="utf-8") as fh:
            for rec in records:
                fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
        if args.raw_out:
            with open(args.raw_out, "w", encoding="utf-8") as fh:
                fh.write(text)
    except OSError as exc:
        sys.stderr.write("错误: 输出写入失败: %s\n" % exc)
        return 1

    n_pages = text.split(PAGE_SEP)
    sys.stderr.write(
        "完成: %d 页, %d 行, %d 字符 -> %s , %s%s\n"
        % (
            len(n_pages),
            len(records),
            len(text),
            text_out,
            anchors_out,
            (" , " + args.raw_out) if args.raw_out else "",
        )
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
