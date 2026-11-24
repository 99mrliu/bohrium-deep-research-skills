#!/usr/bin/env python3
"""extract_facts.py — 从论文 PDF 构建事实池 facts.json（红队复核的锚点）。

事实池内容：
  - pages: 分页纯文本（供 R3 逐字校验）
  - captions: Figure/Table caption 索引（供 R2/R8）
  - numeric_anchors: 带单位数值锚点（供 R1）
  - sections: 章节列表（供 R5）
  - limitation_hints: limitation/future work 线索句（供 R7）

PDF 文本提取降级链：pdftotext(subprocess) -> pymupdf -> pypdf。
确定性：同一 PDF 输出完全一致；不写时间戳。

用法：extract_facts.py <paper.pdf> --out facts.json
退出码：0 成功；2 提取失败（所有引擎不可用或 PDF 无文本）。
"""
import argparse
import json
import re
import shutil
import subprocess
import sys

# 单位按长度降序排列，保证 "ms" 优先于 "m"、"kHz" 优先于 "Hz"。
UNITS = [
    "samples", "datasets", "points", "epochs",
    "kHz", "MHz", "kW", "keV", "MeV", "mV", "mA",
    "mm", "cm", "km", "kg", "mg", "ms", "min",
    "%", "dB", "Hz", "eV", "Pa",
    "s", "m", "g", "K", "V", "A", "W", "J",
]
NUM_RE = re.compile(r"[-+]?\d+(?:\.\d+)?\s*(?:" + "|".join(UNITS) + r")(?![A-Za-z])")
CAPTION_RE = re.compile(r"^\s*((?:Figure|Table)\s+\d+)\s*[.:]\s*(.+)$")
SECTION_RE = re.compile(r"^\s*(\d+)\.?\s+([A-Z][A-Za-z][A-Za-z /-]{2,40})\s*$")
LIMIT_RE = re.compile(r"limitation|limitations|future work", re.IGNORECASE)


def norm(s: str) -> str:
    """空白归一化：折行/多空格统一为单空格，保证跨行逐字匹配稳定。"""
    return re.sub(r"\s+", " ", s).strip()


def extract_pages(pdf_path):
    """返回 (pages: list[str] | None, engine: str)。按降级链尝试。"""
    if shutil.which("pdftotext"):
        try:
            r = subprocess.run(
                ["pdftotext", pdf_path, "-"],
                capture_output=True, text=True, timeout=120,
            )
            if r.returncode == 0 and r.stdout.strip():
                pages = r.stdout.split("\f")
                while pages and not pages[-1].strip():
                    pages.pop()
                if pages:
                    return pages, "pdftotext"
        except Exception:
            pass  # 落入下一引擎
    try:
        import fitz  # pymupdf
        try:
            doc = fitz.open(pdf_path)
            pages = [page.get_text() for page in doc]
            doc.close()
            if any(p.strip() for p in pages):
                return pages, "pymupdf"
        except Exception:
            pass
    except ImportError:
        pass
    try:
        from pypdf import PdfReader
        reader = PdfReader(pdf_path)
        pages = [(p.extract_text() or "") for p in reader.pages]
        if any(p.strip() for p in pages):
            return pages, "pypdf"
    except ImportError:
        pass
    except Exception:
        pass
    return None, "none"


def find_captions(pages):
    caps = []
    for i, text in enumerate(pages, 1):
        for line in text.splitlines():
            m = CAPTION_RE.match(line)
            if m:
                caps.append({
                    "kind": m.group(1).split()[0].lower(),
                    "label": norm(m.group(1)),
                    "text": norm(m.group(2)),
                    "page": i,
                })
    return caps


def find_anchors(pages):
    found = set()
    for text in pages:
        for m in NUM_RE.finditer(text):
            found.add(norm(m.group(0)))
    return sorted(found)


def find_sections(pages):
    seen, out = set(), []
    for i, text in enumerate(pages, 1):
        for line in text.splitlines():
            m = SECTION_RE.match(line)
            if m and m.group(1) not in seen:
                seen.add(m.group(1))
                out.append({"number": m.group(1), "title": norm(m.group(2)), "page": i})
    return out


def find_limitations(pages):
    hints = []
    for i, text in enumerate(pages, 1):
        for sent in re.split(r"(?<=[.!?])\s+", norm(text)):
            if LIMIT_RE.search(sent):
                hints.append({"page": i, "sentence": sent})
    return hints[:20]


def main(argv=None):
    ap = argparse.ArgumentParser(description="从论文 PDF 提取事实池 facts.json")
    ap.add_argument("pdf", help="论文 PDF 路径")
    ap.add_argument("--out", required=True, help="输出 facts.json 路径")
    args = ap.parse_args(argv)

    pages, engine = extract_pages(args.pdf)
    if pages is None:
        print(
            "ERROR: 无法提取 PDF 文本。降级链 pdftotext/pymupdf/pypdf 均失败；"
            "可能是加密 PDF、纯扫描件或依赖全部缺失（tool_missing）。",
            file=sys.stderr,
        )
        return 2

    facts = {
        "source": args.pdf,
        "engine": engine,
        "page_count": len(pages),
        "pages": [{"page": i, "text": t} for i, t in enumerate(pages, 1)],
        "captions": find_captions(pages),
        "numeric_anchors": find_anchors(pages),
        "sections": find_sections(pages),
        "limitation_hints": find_limitations(pages),
    }
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(facts, f, ensure_ascii=False, indent=2)
        f.write("\n")
    print(
        f"engine={engine} pages={len(pages)} captions={len(facts['captions'])} "
        f"anchors={len(facts['numeric_anchors'])} sections={len(facts['sections'])} "
        f"limitation_hints={len(facts['limitation_hints'])} -> {args.out}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
