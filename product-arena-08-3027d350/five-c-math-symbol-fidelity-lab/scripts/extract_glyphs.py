#!/usr/bin/env python3
"""extract_glyphs.py — 字符/词级抽取(math-symbol-fidelity-lab 第 1 步)

引擎链:
  1. pymupdf rawdict(首选,char 级): 每字符 {c, codepoint, bbox, origin, size, font, flags, page}
  2. pdftotext -bbox(降级,word 级): 每词 {text, bbox, page}; 无字号/字体,
     无法做上下标判定 → mode=word, 该页在报告中标 partial。

用法:
  python3 extract_glyphs.py PDF --out glyphs.jsonl --report extract_report.json
          [--engine auto|pymupdf|pdftotext]

退出码: 0=全部 char 级成功, 2=存在降级(部分页 word 级或部分页失败), 3=失败。
核心逻辑仅标准库; pymupdf 为可选引擎, 缺失时自动降级并在报告写明 engine 与原因。
"""

import argparse
import json
import shutil
import subprocess
import sys
import time
import xml.etree.ElementTree as ET

XHTML_NS = "{http://www.w3.org/1999/xhtml}"


def extract_pymupdf(pdf_path: str):
    """返回 (records, page_modes, error)。records 为 char 级 dict 列表。"""
    try:
        import pymupdf  # noqa: PLC0415
    except ImportError as e:
        return None, None, f"pymupdf 不可用: {e}"
    records = []
    page_modes = {}
    try:
        doc = pymupdf.open(pdf_path)
    except Exception as e:  # 文件损坏等
        return None, None, f"pymupdf 打开失败: {e}"
    try:
        gid = 0
        for pno in range(len(doc)):
            page = doc[pno]
            page_modes[pno + 1] = "char"
            raw = page.get_text("rawdict")
            for block in raw.get("blocks", []):
                for line in block.get("lines", []):
                    for span in line.get("spans", []):
                        font = span.get("font", "")
                        size = float(span.get("size", 0.0))
                        flags = int(span.get("flags", 0))
                        for ch in span.get("chars", []):
                            c = ch.get("c", "")
                            records.append({
                                "gid": gid,
                                "mode": "char",
                                "page": pno + 1,
                                "c": c,
                                "codepoint": ord(c) if len(c) == 1 else None,
                                "font": font,
                                "size": round(size, 3),
                                "flags": flags,
                                "bbox": [round(v, 2) for v in ch.get("bbox", (0, 0, 0, 0))],
                                "origin": [round(v, 2) for v in ch.get("origin", (0, 0))],
                            })
                            gid += 1
    finally:
        doc.close()
    return records, page_modes, None


def extract_pdftotext(pdf_path: str):
    """pdftotext -bbox 降级: word 级。返回 (records, page_modes, error)。"""
    if shutil.which("pdftotext") is None:
        return None, None, "pdftotext 不在 PATH 中"
    try:
        proc = subprocess.run(
            ["pdftotext", "-bbox", pdf_path, "-"],
            capture_output=True, timeout=120,
        )
    except Exception as e:
        return None, None, f"pdftotext 执行失败: {e}"
    if proc.returncode != 0:
        return None, None, f"pdftotext 退出码 {proc.returncode}: {proc.stderr.decode('utf-8', 'replace')[:400]}"
    try:
        root = ET.fromstring(proc.stdout.decode("utf-8", "replace"))
    except ET.ParseError as e:
        return None, None, f"pdftotext -bbox 输出解析失败: {e}"
    records = []
    page_modes = {}
    gid = 0
    for pno, page in enumerate(root.iter(f"{XHTML_NS}page"), start=1):
        page_modes[pno] = "word"
        for word in page.iter(f"{XHTML_NS}word"):
            records.append({
                "gid": gid,
                "mode": "word",
                "page": pno,
                "c": None,
                "text": word.text or "",
                "codepoint": None,
                "font": None,
                "size": None,
                "flags": None,
                "bbox": [round(float(word.get(a)), 2) for a in ("xMin", "yMin", "xMax", "yMax")],
                "origin": None,
            })
            gid += 1
    return records, page_modes, None


def main() -> int:
    ap = argparse.ArgumentParser(description="字符/词级抽取 → glyphs.jsonl")
    ap.add_argument("pdf", help="输入 PDF 路径")
    ap.add_argument("--out", required=True, help="glyphs.jsonl 输出路径")
    ap.add_argument("--report", required=True, help="extract_report.json 输出路径")
    ap.add_argument("--engine", choices=["auto", "pymupdf", "pdftotext"], default="auto")
    args = ap.parse_args()

    report = {
        "tool": "extract_glyphs",
        "pdf": args.pdf,
        "requested_engine": args.engine,
        "engine": None,
        "degrade_reason": None,
        "page_modes": {},
        "degraded_pages": [],
        "counts": {},
        "ts": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
    }

    records, page_modes, err = None, None, None
    if args.engine in ("auto", "pymupdf"):
        records, page_modes, err = extract_pymupdf(args.pdf)
        if records is not None:
            report["engine"] = "pymupdf-rawdict"
        elif args.engine == "pymupdf":
            report["degrade_reason"] = err
            _write_reports(args, [], report)
            print(f"ERROR: {err}", file=sys.stderr)
            return 3
        else:
            report["degrade_reason"] = f"pymupdf 失败, 降级 pdftotext: {err}"

    if records is None:
        records, page_modes, err2 = extract_pdftotext(args.pdf)
        if records is None:
            report["degrade_reason"] = (report.get("degrade_reason") or "") + f"; pdftotext 亦失败: {err2}"
            _write_reports(args, [], report)
            print(f"ERROR: {err2}", file=sys.stderr)
            return 3
        report["engine"] = "pdftotext-bbox"
        if report["degrade_reason"] is None:
            report["degrade_reason"] = "按 --engine=pdftotext 强制使用词级降级引擎"

    n_char = sum(1 for r in records if r["mode"] == "char")
    n_word = sum(1 for r in records if r["mode"] == "word")
    report["page_modes"] = {str(k): v for k, v in sorted(page_modes.items())}
    report["degraded_pages"] = [p for p, m in sorted(page_modes.items()) if m != "char"]
    report["counts"] = {
        "records": len(records),
        "char_records": n_char,
        "word_records": n_word,
        "pages": len(page_modes),
    }
    _write_reports(args, records, report)
    print(json.dumps({"engine": report["engine"], "records": len(records),
                      "degraded_pages": report["degraded_pages"]}, ensure_ascii=False))
    return 2 if report["degraded_pages"] else 0


def _write_reports(args, records, report) -> None:
    with open(args.out, "w", encoding="utf-8") as f:
        for r in records:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    with open(args.report, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)


if __name__ == "__main__":
    sys.exit(main())
