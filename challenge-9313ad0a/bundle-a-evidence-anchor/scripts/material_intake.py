#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""material_intake.py — 科研材料入库与分页工具（仅依赖 Python 3.10+ 标准库）。

用法：
    python3 scripts/material_intake.py --out /app/work/material FILE [FILE...]

行为约定：
  * .pdf 文件：若 shutil.which("pdftotext") 可用，则通过 subprocess 调用
    `pdftotext -layout <file> -` 提取文本；若 pdftotext 不可用或执行失败，
    记录警告并将该文件列入 unreadable（跳过，不崩溃）。
  * .txt / .md 文件：直接读取；其他扩展名按纯文本处理并记录警告。
  * 按换页符 \\f 切分页面；文本中无 \\f 时视为单页。
  * 无效 UTF-8：以 errors='replace' 解码，并将 U+FFFD 出现次数记为警告。
  * 不存在的文件：列入 unreadable 并给出原因，不崩溃。

输出（写入 --out 目录）：
  * pages.jsonl        每行一个 JSON 对象：
                       {"file", "page", "char_start", "char_end", "text"}
                       char_start/char_end 为该页文本在本文件全部页文本
                       （按页序拼接、不含换页符）中的字符偏移。
  * material_index.json
                       {"materials": [{"file", "type", "pages", "chars",
                                        "sha256", "tool", "warnings": [...]}],
                        "unreadable": [{"file", "reason"}]}

退出码：至少一份材料读取成功为 0；否则为 2。
输出为确定性结果：不写入时间戳，材料按命令行给定顺序处理。
"""

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys

TEXT_EXTS = {".txt", ".md"}
REPLACEMENT_CHAR = "�"


def decode_utf8(raw):
    """以 UTF-8 解码，替换非法字节，返回 (文本, U+FFFD 计数)。"""
    text = raw.decode("utf-8", errors="replace")
    return text, text.count(REPLACEMENT_CHAR)


def split_pages(text):
    """按换页符 \\f 切页；去掉由末尾换页符产生的空尾页；无 \\f 时为单页。"""
    pages = text.split("\f")
    if pages and pages[-1] == "":
        pages.pop()
    return pages


def read_pdf(path):
    """调用 pdftotext 提取 PDF 文本。返回 (文本或 None, 警告列表, 工具名)。"""
    tool = "pdftotext -layout"
    if shutil.which("pdftotext") is None:
        return None, ["pdftotext 不可用（PATH 中未找到），跳过该 PDF"], tool
    proc = subprocess.run(
        ["pdftotext", "-layout", path, "-"],
        capture_output=True,
        check=False,
    )
    if proc.returncode != 0:
        err = proc.stderr.decode("utf-8", errors="replace").strip()
        return None, ["pdftotext 执行失败（返回码 %d）：%s" % (proc.returncode, err)], tool
    text, bad = decode_utf8(proc.stdout)
    warnings = []
    if bad:
        warnings.append("UTF-8 解码替换字符 U+FFFD 共 %d 处" % bad)
    return text, warnings, tool


def read_text_file(path, raw, ext):
    """读取纯文本类材料。返回 (文本, 警告列表, 工具名)。"""
    text, bad = decode_utf8(raw)
    warnings = []
    if ext not in TEXT_EXTS:
        warnings.append("未识别的扩展名 %s，按纯文本处理" % (ext or "(无)"))
    if bad:
        warnings.append("UTF-8 解码替换字符 U+FFFD 共 %d 处" % bad)
    return text, warnings, "direct-read"


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="科研材料入库：PDF/TXT/MD 分页并生成 pages.jsonl 与 material_index.json"
    )
    parser.add_argument("--out", required=True, help="输出目录，例如 /app/work/material")
    parser.add_argument("files", nargs="+", help="材料文件路径列表")
    args = parser.parse_args(argv)

    os.makedirs(args.out, exist_ok=True)

    materials = []
    unreadable = []
    page_records = []

    for path in args.files:
        if not os.path.isfile(path):
            unreadable.append({"file": path, "reason": "文件不存在或不是常规文件"})
            continue

        ext = os.path.splitext(path)[1].lower()
        with open(path, "rb") as fh:
            raw = fh.read()
        sha256 = hashlib.sha256(raw).hexdigest()

        if ext == ".pdf":
            text, warnings, tool = read_pdf(path)
            if text is None:
                unreadable.append({
                    "file": path,
                    "reason": warnings[0] if warnings else "PDF 文本提取失败",
                })
                continue
        else:
            text, warnings, tool = read_text_file(path, raw, ext)

        pages = split_pages(text)
        if ext == ".pdf" and not any(p.strip() for p in pages):
            warnings.append("未提取到任何文本：PDF 可能已加密或缺少文本层（扫描件）")

        offset = 0
        for page_no, page_text in enumerate(pages, start=1):
            page_records.append({
                "file": path,
                "page": page_no,
                "char_start": offset,
                "char_end": offset + len(page_text),
                "text": page_text,
            })
            offset += len(page_text)

        materials.append({
            "file": path,
            "type": ext.lstrip(".") or "unknown",
            "pages": len(pages),
            "chars": len(text),
            "sha256": sha256,
            "tool": tool,
            "warnings": warnings,
        })

    pages_path = os.path.join(args.out, "pages.jsonl")
    with open(pages_path, "w", encoding="utf-8") as fh:
        for rec in page_records:
            fh.write(json.dumps(rec, ensure_ascii=False) + "\n")

    index = {"materials": materials, "unreadable": unreadable}
    index_path = os.path.join(args.out, "material_index.json")
    with open(index_path, "w", encoding="utf-8") as fh:
        json.dump(index, fh, ensure_ascii=False, indent=2)
        fh.write("\n")

    print("已读取材料 %d 份，共 %d 页；无法读取 %d 份。"
          % (len(materials), len(page_records), len(unreadable)))
    print("pages.jsonl -> %s" % pages_path)
    print("material_index.json -> %s" % index_path)
    for item in unreadable:
        print("警告：无法读取 %s（%s）" % (item["file"], item["reason"]), file=sys.stderr)

    return 0 if materials else 2


if __name__ == "__main__":
    sys.exit(main())
