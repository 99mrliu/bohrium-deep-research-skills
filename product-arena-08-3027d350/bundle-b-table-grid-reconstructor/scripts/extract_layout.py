#!/usr/bin/env python3
"""extract_layout.py — 保版式文本抽取层（表格结构重建技能 B 的第 1 步）。

把科研 PDF 按页抽成"保空白版式"文本（空格对齐的列是后续表格检测的依据）：
    1. pdftotext -layout（poppler，首选：空格列对齐最好）
    2. PyMuPDF get_text("text", sort=True)（降级：列对齐较弱，报告注明）
输出 /app/work/pages/pageNN.txt 与 extract_report.json。
已有版式文本时可用 --layout-dir 直接透传。
退出码 0=成功；2=部分（降级引擎或部分页无文字）；3=加密/无文字层/不可用。
"""
import argparse
import glob
import json
import os
import shutil
import subprocess
import sys


def _report(out_dir, report, code):
    os.makedirs(out_dir, exist_ok=True)
    with open(os.path.join(out_dir, "extract_report.json"), "w",
              encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    print(json.dumps(report, ensure_ascii=False))
    return code


def _split_formfeed(text):
    pages = text.split("\f")
    return [p for p in pages if p.strip()] or pages[:1]


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    src = ap.add_mutually_exclusive_group(required=True)
    src.add_argument("--pdf")
    src.add_argument("--layout-dir", help="已有 page*.txt 目录，透传")
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    pages_dir = os.path.join(args.out, "pages")
    os.makedirs(pages_dir, exist_ok=True)

    if args.layout_dir:
        src_files = sorted(glob.glob(os.path.join(args.layout_dir, "*.txt")))
        if not src_files:
            return _report(args.out, {"status": "failed",
                                      "reason": "layout_dir_empty"}, 3)
        n = 0
        for p in src_files:
            n += 1
            shutil.copyfile(p, os.path.join(pages_dir, f"page{n:02d}.txt"))
        return _report(args.out, {"status": "ok", "engine": "external-layout",
                                  "pages": n,
                                  "note": "外部版式文本透传"}, 0)

    exe = shutil.which("pdftotext")
    if exe:
        tmp = os.path.join(args.out, "_layout_all.txt")
        proc = subprocess.run(
            [exe, "-layout", "-enc", "UTF-8", args.pdf, tmp],
            capture_output=True, text=True)
        err = ((proc.stderr or "") + (proc.stdout or "")).lower()
        if proc.returncode != 0:
            reason = ("encrypted_pdf" if "password" in err
                      else f"pdftotext_failed:{err.strip()[:200]}")
            return _report(args.out, {"status": "failed", "reason": reason,
                                      "handoff": "加密 PDF 需先解密后重跑"}, 3)
        with open(tmp, encoding="utf-8") as f:
            pages = _split_formfeed(f.read())
        os.remove(tmp)
        empty = 0
        for i, p in enumerate(pages, start=1):
            if not p.strip():
                empty += 1
            with open(os.path.join(pages_dir, f"page{i:02d}.txt"), "w",
                      encoding="utf-8") as f:
                f.write(p)
        if not any(p.strip() for p in pages):
            return _report(args.out, {
                "status": "failed", "reason": "no_text_layer",
                "handoff": "疑似扫描件，先经平台 ocr-tool 取得文本后回灌"}, 3)
        status = "ok" if empty == 0 else "partial"
        return _report(args.out, {
            "status": status, "engine": "pdftotext-layout", "pages": len(pages),
            "empty_pages": empty,
            "uncertainty": ([f"{empty} 页无文字（图片页或扫描页），已留空"]
                            if empty else [])},
            0 if status == "ok" else 2)

    try:
        try:
            import pymupdf as fitz  # noqa: N813
        except ImportError:
            import fitz  # noqa: N813
        doc = fitz.open(args.pdf)
        if doc.needs_pass:
            return _report(args.out, {"status": "failed",
                                      "reason": "encrypted_pdf"}, 3)
        n = 0
        for page in doc:
            n += 1
            with open(os.path.join(pages_dir, f"page{n:02d}.txt"), "w",
                      encoding="utf-8") as f:
                f.write(page.get_text("text", sort=True))
        doc.close()
        return _report(args.out, {
            "status": "partial", "engine": "pymupdf-sorted-text", "pages": n,
            "uncertainty": ["降级引擎的空格列对齐较弱，表格检测置信度会降低"]}, 2)
    except ImportError:
        return _report(args.out, {
            "status": "failed", "reason": "no_extractor_available",
            "handoff": "安装 poppler(pdftotext) 或 pymupdf 后重跑"}, 3)
    except Exception as exc:
        return _report(args.out, {"status": "failed",
                                  "reason": f"extract_error:{exc}"}, 3)


if __name__ == "__main__":
    sys.exit(main())
