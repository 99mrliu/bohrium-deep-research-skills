#!/usr/bin/env python3
"""evidence_scan.py -- 扫描论文 PDF，产出 evidence.json。

产出：分页文本、Figure/Table caption 索引（含页码）、数值锚点（值+单位+上下文+页码）。
文本提取降级链：pdftotext(subprocess) -> pymupdf -> pypdf。三链全断则非零退出。

用法：
    python3 evidence_scan.py paper.pdf --out evidence.json
"""
import argparse
import json
import re
import shutil
import subprocess
import sys

CAPTION_RE = re.compile(r"^\s*(Figure|Table)\s+(\d+)\s*[:.]\s*(.+?)\s*$")
# 单位较长的放前面，避免 "W/(m·K)" 被 "K" 截断
UNIT_RE = re.compile(
    r"(?P<value>\d+(?:\.\d+)?)\s*"
    r"(?P<unit>W/\(m·K\)|W/mK|K/min|°C|meV|GPa|kPa|MPa|nm|mm|ms|min|K|h|%)"
    r"(?=\s|$|[.,;:)\]])"
)


def extract_with_pdftotext(pdf_path):
    if not shutil.which("pdftotext"):
        return None
    try:
        out = subprocess.run(
            ["pdftotext", "-layout", pdf_path, "-"],
            capture_output=True, text=True, timeout=120,
        )
    except Exception:
        return None
    if out.returncode != 0 or not out.stdout.strip():
        return None
    pages = [p for p in out.stdout.split("\f")]
    # pdftotext 末尾常带一个空页
    while pages and not pages[-1].strip():
        pages.pop()
    return pages if any(p.strip() for p in pages) else None


def extract_with_pymupdf(pdf_path):
    try:
        import fitz  # pymupdf
    except ImportError:
        return None
    try:
        doc = fitz.open(pdf_path)
        pages = [page.get_text("text") for page in doc]
        doc.close()
    except Exception:
        return None
    return pages if pages and any(p.strip() for p in pages) else None


def extract_with_pypdf(pdf_path):
    try:
        from pypdf import PdfReader
    except ImportError:
        return None
    try:
        reader = PdfReader(pdf_path)
        pages = [(p.extract_text() or "") for p in reader.pages]
    except Exception:
        return None
    return pages if pages and any(p.strip() for p in pages) else None


def extract_pages(pdf_path):
    for name, fn in (
        ("pdftotext", extract_with_pdftotext),
        ("pymupdf", extract_with_pymupdf),
        ("pypdf", extract_with_pypdf),
    ):
        pages = fn(pdf_path)
        if pages:
            return name, pages
    return None, None


def scan(pdf_path):
    engine, pages = extract_pages(pdf_path)
    if engine is None:
        print(
            "ERROR: all PDF text extractors failed (pdftotext/pymupdf/pypdf). "
            "The PDF may be encrypted or a scanned image without OCR.",
            file=sys.stderr,
        )
        return None
    figures, tables, anchors = [], [], []
    for pno, text in enumerate(pages, start=1):
        for line in text.splitlines():
            m = CAPTION_RE.match(line)
            if m:
                entry = {
                    "ref": f"{m.group(1)} {m.group(2)}",
                    "caption": f"{m.group(1)} {m.group(2)}: {m.group(3)}",
                    "page": pno,
                }
                (figures if m.group(1) == "Figure" else tables).append(entry)
            for um in UNIT_RE.finditer(line):
                anchors.append({
                    "id": len(anchors),
                    "value": um.group("value"),
                    "unit": um.group("unit"),
                    "context": line.strip(),
                    "page": pno,
                })
    return {
        "engine": engine,
        "pdf": pdf_path,
        "page_count": len(pages),
        "pages": [{"page": i + 1, "text": t} for i, t in enumerate(pages)],
        "figures": figures,
        "tables": tables,
        "anchors": anchors,
    }


def main() -> int:
    ap = argparse.ArgumentParser(description="Scan a paper PDF into evidence.json.")
    ap.add_argument("pdf", help="path to paper.pdf")
    ap.add_argument("--out", required=True, help="output evidence.json path")
    args = ap.parse_args()
    result = scan(args.pdf)
    if result is None:
        return 2
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    print(
        f"engine={result['engine']} pages={result['page_count']} "
        f"figures={len(result['figures'])} tables={len(result['tables'])} "
        f"anchors={len(result['anchors'])} -> {args.out}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
