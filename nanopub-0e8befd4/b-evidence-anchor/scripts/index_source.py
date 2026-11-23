#!/usr/bin/env python3
"""index_source.py — 把论文材料建成页/行/偏移三级可复定位索引（纯标准库）。

支持：
  .pdf  —— 优先 pdftotext -layout（逐页），失败回退 PyMuPDF（如已安装）；
  .txt/.md/其他文本 —— 直接读取，\f 分页，否则单页。

输出 JSON：{source: {id, path, sha256, backend, page_count},
            pages: [{page, text, lines: [{line, start, end, text}]}]}
原文不改写；匹配归一化由 verify_anchors.py 负责。
"""
import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys

VERSION = "1.0.0"


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def extract_pdf_pages(path):
    """返回 (pages_text, backend)。pages_text: List[str]，下标即页序。"""
    if shutil.which("pdftotext"):
        proc = subprocess.run(["pdftotext", "-layout", path, "-"],
                              capture_output=True)
        if proc.returncode != 0:
            raise RuntimeError("pdftotext 失败: "
                               f"{proc.stderr.decode('utf-8', 'replace')[:300]}")
        text = proc.stdout.decode("utf-8", "replace")
        pages = text.split("\f")
        while pages and not pages[-1].strip():
            pages.pop()
        if not pages:
            raise RuntimeError("pdftotext 提取为空：疑似扫描件无文本层，"
                               "按 SKILL.md 异常流程（OCR 或 partial）处理。")
        return pages, "pdftotext-layout"
    try:
        import fitz  # PyMuPDF
    except ImportError:
        raise RuntimeError("无可用 PDF 文本提取后端：pdftotext 不在 PATH，"
                           "PyMuPDF 未安装。扫描件请按 SKILL.md 异常流程处理。")
    doc = fitz.open(path)
    pages = [page.get_text("text") for page in doc]
    doc.close()
    return pages, "pymupdf-text"


def extract_text_pages(path):
    with open(path, "rb") as fh:
        raw = fh.read()
    text = raw.decode("utf-8", "replace")
    pages = text.split("\f")
    return pages, "raw-text"


def build_index(pages_text):
    pages = []
    for i, ptext in enumerate(pages_text, 1):
        lines = []
        pos = 0
        for ln, line in enumerate(ptext.splitlines(keepends=True), 1):
            lines.append({"line": ln, "start": pos, "end": pos + len(line),
                          "text": line.rstrip("\n").rstrip("\r")})
            pos += len(line)
        pages.append({"page": i, "text": ptext, "lines": lines})
    return pages


def main():
    ap = argparse.ArgumentParser(description="源材料页/行/偏移索引")
    ap.add_argument("--input", required=True)
    ap.add_argument("--source-id", required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    if not os.path.isfile(args.input):
        print(f"E_INPUT 不存在: {args.input}", file=sys.stderr)
        return 2
    ext = os.path.splitext(args.input)[1].lower()
    try:
        if ext == ".pdf":
            pages_text, backend = extract_pdf_pages(args.input)
        else:
            pages_text, backend = extract_text_pages(args.input)
    except RuntimeError as exc:
        print(f"E_BACKEND {exc}", file=sys.stderr)
        return 2

    index = {
        "tool": "index_source", "version": VERSION,
        "source": {
            "id": args.source_id,
            "path": os.path.abspath(args.input),
            "sha256": sha256_file(args.input),
            "backend": backend,
            "page_count": len(pages_text),
            "chars": sum(len(t) for t in pages_text),
        },
        "pages": build_index(pages_text),
    }
    os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as fh:
        json.dump(index, fh, ensure_ascii=False)
        fh.write("\n")
    print(json.dumps({"source_id": args.source_id, "backend": backend,
                      "pages": len(pages_text), "sha256": index["source"]["sha256"]},
                     ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
