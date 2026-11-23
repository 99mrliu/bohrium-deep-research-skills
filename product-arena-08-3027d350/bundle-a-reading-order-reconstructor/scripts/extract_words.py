#!/usr/bin/env python3
"""extract_words.py — 词级坐标抽取层（阅读顺序重建技能 A 的第 1 步）。

把一份科研 PDF 抽成统一的词表 words.tsv：
    page\tx0\ty0\tx1\ty1\ttext
坐标单位为 PDF point（左上原点）。引擎回退链：
    1. PyMuPDF (pymupdf/fitz)      —— 最精确的词框
    2. pdftotext -bbox (poppler)   —— XHTML <word> 框，含页尺寸
    3. pdftotext -layout           —— 无坐标的版式文本，仅作降级兜底
任何失败都不抛异常给调用方，而是写 extract_report.json 并用退出码表达状态：
    0=成功，2=部分（仅 layout 兜底，无坐标），3=加密/无文字层/不可读（如实报告）。

用法：
    python3 extract_words.py --pdf paper.pdf --out /app/work
    python3 extract_words.py --tsv existing_words.tsv --out /app/work   # 已有词表时透传
"""
import argparse
import json
import os
import re
import shutil
import subprocess
import sys

REPORT_NAME = "extract_report.json"
WORDS_NAME = "words.tsv"
META_NAME = "pages_meta.json"


def _write_report(out_dir, report, code):
    os.makedirs(out_dir, exist_ok=True)
    with open(os.path.join(out_dir, REPORT_NAME), "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    return code


def _try_pymupdf(pdf_path, out_dir):
    try:
        try:
            import pymupdf as fitz  # noqa: N813
        except ImportError:
            import fitz  # noqa: N813
    except Exception:
        return None
    words, meta = [], []
    try:
        doc = fitz.open(pdf_path)
        if doc.needs_pass:
            return {"error": "encrypted_pdf", "engine": "pymupdf"}
        for pno, page in enumerate(doc, start=1):
            rect = page.rect
            meta.append({"page": pno, "width": round(rect.width, 2),
                         "height": round(rect.height, 2)})
            for w in page.get_text("words"):
                x0, y0, x1, y1, text = w[0], w[1], w[2], w[3], w[4]
                if text.strip():
                    words.append((pno, x0, y0, x1, y1, text))
        doc.close()
    except Exception as exc:  # 引擎存在但打开失败，回退
        return {"error": f"pymupdf_failed:{exc.__class__.__name__}", "engine": "pymupdf"}
    if not words:
        return {"error": "no_text_layer", "engine": "pymupdf",
                "hint": "页面上没有可抽取的文字层，疑似扫描件，需要 OCR"}
    return {"words": words, "meta": meta, "engine": "pymupdf"}


_BBOX_WORD_RE = re.compile(
    r'<word\s+xMin="([\d.]+)"\s+yMin="([\d.]+)"\s+xMax="([\d.]+)"\s+yMax="([\d.]+)"[^>]*>'
    r"(.*?)</word>", re.S)
_BBOX_PAGE_RE = re.compile(r'<page\s+width="([\d.]+)"\s+height="([\d.]+)"')


def _html_unescape(s):
    return (s.replace("&lt;", "<").replace("&gt;", ">").replace("&quot;", '"')
             .replace("&#39;", "'").replace("&amp;", "&"))


def _try_pdftotext_bbox(pdf_path, out_dir):
    exe = shutil.which("pdftotext")
    if not exe:
        return None
    xhtml_path = os.path.join(out_dir, "_bbox_tmp.html")
    proc = subprocess.run(
        [exe, "-bbox", "-enc", "UTF-8", pdf_path, xhtml_path],
        capture_output=True, text=True)
    err = (proc.stderr or "") + (proc.stdout or "")
    if proc.returncode != 0:
        os.path.exists(xhtml_path) and os.remove(xhtml_path)
        if "Incorrect password" in err or "password" in err.lower():
            return {"error": "encrypted_pdf", "engine": "pdftotext-bbox"}
        return {"error": f"pdftotext_failed:{err.strip()[:200]}",
                "engine": "pdftotext-bbox"}
    try:
        with open(xhtml_path, encoding="utf-8") as f:
            content = f.read()
    finally:
        os.path.exists(xhtml_path) and os.remove(xhtml_path)
    words, meta = [], []
    chunks = _BBOX_PAGE_RE.split(content)
    # chunks: [head, w1, h1, rest1, w2, h2, rest2, ...]
    for i in range(1, len(chunks) - 2, 3):
        pw, ph = float(chunks[i]), float(chunks[i + 1])
        body = chunks[i + 2]
        pno = len(meta) + 1
        meta.append({"page": pno, "width": pw, "height": ph})
        for m in _BBOX_WORD_RE.finditer(body):
            text = _html_unescape(m.group(5)).strip()
            if text:
                words.append((pno, float(m.group(1)), float(m.group(2)),
                              float(m.group(3)), float(m.group(4)), text))
    if not meta:
        return {"error": "pdftotext_bbox_no_pages", "engine": "pdftotext-bbox"}
    if not words:
        return {"error": "no_text_layer", "engine": "pdftotext-bbox",
                "hint": "页面上没有可抽取的文字层，疑似扫描件，需要 OCR"}
    return {"words": words, "meta": meta, "engine": "pdftotext-bbox"}


def _try_pdftotext_layout(pdf_path, out_dir):
    exe = shutil.which("pdftotext")
    if not exe:
        return None
    layout_path = os.path.join(out_dir, "raw_layout.txt")
    proc = subprocess.run(
        [exe, "-layout", "-enc", "UTF-8", pdf_path, layout_path],
        capture_output=True, text=True)
    if proc.returncode != 0 or not os.path.exists(layout_path):
        return {"error": f"pdftotext_layout_failed:{(proc.stderr or '')[:200]}",
                "engine": "pdftotext-layout"}
    with open(layout_path, encoding="utf-8") as f:
        text = f.read()
    if not text.strip():
        return {"error": "no_text_layer", "engine": "pdftotext-layout",
                "hint": "页面上没有可抽取的文字层，疑似扫描件，需要 OCR"}
    return {"layout_only": True, "engine": "pdftotext-layout"}


def _write_words(words, out_dir):
    path = os.path.join(out_dir, WORDS_NAME)
    with open(path, "w", encoding="utf-8") as f:
        f.write("page\tx0\ty0\tx1\ty1\ttext\n")
        for pno, x0, y0, x1, y1, text in words:
            f.write(f"{pno}\t{x0:.2f}\t{y0:.2f}\t{x1:.2f}\t{y1:.2f}\t{text}\n")
    return path


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    src = ap.add_mutually_exclusive_group(required=True)
    src.add_argument("--pdf", help="输入 PDF 路径")
    src.add_argument("--tsv", help="已有 words.tsv 直接透传（校验格式）")
    ap.add_argument("--out", required=True, help="工作目录，如 /app/work")
    args = ap.parse_args()
    os.makedirs(args.out, exist_ok=True)

    if args.tsv:
        n = 0
        with open(args.tsv, encoding="utf-8") as f_in, \
                open(os.path.join(args.out, WORDS_NAME), "w", encoding="utf-8") as f_out:
            for line in f_in:
                f_out.write(line)
                n += 1
        report = {"status": "ok", "engine": "external-tsv",
                  "words": max(n - 1, 0), "note": "外部词表透传，坐标未重新校验"}
        print(json.dumps(report, ensure_ascii=False))
        return _write_report(args.out, report, 0)

    attempts, result = [], None
    for fn in (_try_pymupdf, _try_pdftotext_bbox, _try_pdftotext_layout):
        r = fn(args.pdf, args.out)
        if r is None:
            attempts.append({"engine": fn.__name__, "available": False})
            continue
        attempts.append({"engine": r.get("engine"),
                         "available": True,
                         "error": r.get("error")})
        if "error" not in r:
            result = r
            break

    if result is None:
        last_err = next((a["error"] for a in reversed(attempts) if a.get("error")),
                        "no_extractor_available")
        report = {"status": "failed", "reason": last_err,
                  "attempts": attempts,
                  "handoff": "加密 PDF 需先解密；扫描件需走 OCR（平台提供 ocr-tool）后再回读本技能",
                  "uncertainty": ["未取得任何文字层，无法判断版面结构"]}
        print(json.dumps(report, ensure_ascii=False))
        return _write_report(args.out, report, 3)

    if result.get("layout_only"):
        report = {"status": "partial", "engine": result["engine"],
                  "attempts": attempts,
                  "note": "仅有无坐标的 layout 文本，无法做列序重建；已写出 raw_layout.txt",
                  "uncertainty": ["阅读顺序未重建，按抽取器原顺序保留"],
                  "handoff": "可用人工阅读顺序标注后进入下游"}
        print(json.dumps(report, ensure_ascii=False))
        return _write_report(args.out, report, 2)

    path = _write_words(result["words"], args.out)
    with open(os.path.join(args.out, META_NAME), "w", encoding="utf-8") as f:
        json.dump(result["meta"], f, ensure_ascii=False, indent=2)
    report = {"status": "ok", "engine": result["engine"],
              "pages": len(result["meta"]), "words": len(result["words"]),
              "attempts": attempts, "words_tsv": path,
              "pages_meta": os.path.join(args.out, META_NAME)}
    print(json.dumps(report, ensure_ascii=False))
    return _write_report(args.out, report, 0)


if __name__ == "__main__":
    sys.exit(main())
