#!/usr/bin/env python3
"""evidence_scan.py — 简版证据锚点扫描：从 paper.pdf 抽 caption / 带单位数值 / limitations 句。

用法:
    python3 evidence_scan.py <paper.pdf> --report evidence.json

PDF 文本提取降级链：pdftotext(subprocess) -> pymupdf -> pypdf。
所有 quote 均为 PDF 提取文本中的逐字子串（仅压缩连续空白），供 content_map 溯源。
"""
from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import deck_common as dc

UNIT_RE = re.compile(
    r"(\d+(?:\.\d+)?)\s*(ms|eV|keV|MeV|GeV|%|Hz|kHz|MHz|GHz|K|nm|µm|um|mm|cm|kg|mA|V)(?![\w])"
)
N_COUNT_RE = re.compile(r"\bn\s*=\s*(\d+)\b")
CAPTION_RE = re.compile(r"\b(Figure|Table)\s+(\d+)\s*[:.]\s*([^.;]{0,200})")
LIMIT_RE = re.compile(r"limitation", re.IGNORECASE)


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", s).strip()


def extract_pages(pdf_path: str) -> tuple[str, list[str]]:
    """返回 (engine, per-page texts)。降级链 pdftotext -> pymupdf -> pypdf。"""
    # 1) pdftotext (subprocess)
    try:
        out = subprocess.run(
            ["pdftotext", "-layout", pdf_path, "-"],
            capture_output=True, timeout=120, check=True,
        )
        text = out.stdout.decode("utf-8", errors="replace")
        pages = text.split("\f")
        while pages and not pages[-1].strip():
            pages.pop()
        if any(p.strip() for p in pages):
            return "pdftotext", pages
    except (FileNotFoundError, subprocess.SubprocessError, OSError):
        pass
    # 2) pymupdf
    try:
        import pymupdf  # type: ignore

        doc = pymupdf.open(pdf_path)
        pages = [page.get_text() for page in doc]
        doc.close()
        if any(p.strip() for p in pages):
            return "pymupdf", pages
    except ImportError:
        pass
    except Exception:
        pass
    # 3) pypdf
    try:
        from pypdf import PdfReader  # type: ignore

        reader = PdfReader(pdf_path)
        pages = [(p.extract_text() or "") for p in reader.pages]
        return "pypdf", pages
    except ImportError:
        raise RuntimeError(
            "no PDF text engine available: install poppler(pdftotext), pymupdf or pypdf"
        )


def _sentences(page_text: str) -> list[str]:
    flat = _norm(page_text)
    # 朴素分句：句号/分号后接空白；保留原句逐字内容
    parts = re.split(r"(?<=[.;])\s+", flat)
    return [p for p in parts if p]


def scan(pdf_path: str) -> dict:
    engine, pages = extract_pages(pdf_path)
    captions, numbers, limitations = [], [], []
    page_texts = []
    for pno, ptext in enumerate(pages, start=1):
        ptext = ptext or ""
        page_texts.append(_norm(ptext)[:20000])
        for m in CAPTION_RE.finditer(_norm(ptext)):
            captions.append(
                {
                    "kind": m.group(1).lower(),
                    "label": f"{m.group(1)} {m.group(2)}",
                    "page": pno,
                    "quote": _norm(m.group(0)),
                }
            )
        for sent in _sentences(ptext):
            for m in UNIT_RE.finditer(sent):
                numbers.append(
                    {"value": m.group(1), "unit": m.group(2), "page": pno, "quote": sent}
                )
            for m in N_COUNT_RE.finditer(sent):
                numbers.append(
                    {"value": m.group(1), "unit": "count(n)", "page": pno, "quote": sent}
                )
            if LIMIT_RE.search(sent) and len(sent.split()) >= 10:
                limitations.append({"page": pno, "quote": sent})
    # 去重（同 value+unit+page）
    seen = set()
    uniq_numbers = []
    for n in numbers:
        key = (n["value"], n["unit"], n["page"])
        if key not in seen:
            seen.add(key)
            uniq_numbers.append(n)
    return {
        "source": os.path.abspath(pdf_path),
        "engine": engine,
        "pages": len(pages),
        "captions": captions,
        "numbers": uniq_numbers,
        "limitations": limitations,
        "page_texts": page_texts,
    }


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        description="扫描 paper.pdf，抽取 Figure/Table caption、带单位数值、limitations 句"
    )
    ap.add_argument("pdf", help="论文 PDF 路径")
    ap.add_argument("--report", required=True, help="输出 evidence.json 路径")
    args = ap.parse_args(argv)

    if not os.path.exists(args.pdf):
        print(f"error: pdf not found: {args.pdf}", file=sys.stderr)
        return 2
    try:
        ev = scan(args.pdf)
    except RuntimeError as e:
        # 降级链全部不可用：诚实 tool_missing，仍产出空骨架
        ev = {
            "source": os.path.abspath(args.pdf),
            "engine": "tool_missing",
            "pages": 0,
            "captions": [],
            "numbers": [],
            "limitations": [],
            "page_texts": [],
            "error": str(e),
        }
        dc.dump_json(ev, args.report)
        print(f"tool_missing: {e}; empty evidence written to {args.report}", file=sys.stderr)
        return 3
    dc.dump_json(ev, args.report)
    print(
        f"evidence ok: engine={ev['engine']} pages={ev['pages']} "
        f"captions={len(ev['captions'])} numbers={len(ev['numbers'])} "
        f"limitations={len(ev['limitations'])}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
