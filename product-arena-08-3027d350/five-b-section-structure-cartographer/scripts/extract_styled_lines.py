#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""extract_styled_lines.py — 行级样式抽取（引擎链自动降级）。

引擎链（按优先级）：
  1. pymupdf（可选）：span 级 text/size/font/flags/bbox/page → 聚成行，mode=styled
  2. pdftotext -bbox（可选）：XHTML 词级坐标，无字号 → 行级几何，mode=geometry
  3. pdftotext -layout（可选）：纯文本，仅页/行序 → mode=text
三者皆不可用时退出码 3（失败），不静默。

核心解析逻辑只用 Python 标准库；pymupdf / pdftotext 仅作可选引擎。

输出 lines.jsonl（每行一个 JSON 对象）：
  page, y0, x0, y1, x1, text, max_size, sizes（字号秩所需统计）,
  bold, engine, mode
另写 <report>（机器可读抽取报告：引擎、降级原因、行数、页数）。

退出码：0=styled 全量成功；2=降级（geometry/text）；3=失败。
"""
import argparse
import json
import os
import re
import shutil
import statistics
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET

BOLD_FLAG_BIT = 16  # pymupdf span flags 第 4 位为 bold


def _round(v, nd=2):
    return round(float(v), nd) if v is not None else None


# ---------------------------------------------------------------- pymupdf
def extract_pymupdf(pdf_path):
    """返回 (lines, info)。抛异常由调用方捕获并降级。"""
    import pymupdf  # 可选引擎，缺失时 ImportError

    doc = pymupdf.open(pdf_path)
    lines = []
    for pno in range(len(doc)):
        page = doc[pno]
        d = page.get_text("dict")
        for block in d.get("blocks", []):
            if block.get("type", 0) != 0:
                continue  # 跳过图片块
            for ln in block.get("lines", []):
                spans = [s for s in ln.get("spans", []) if s.get("text", "").strip()]
                if not spans:
                    continue
                text = "".join(s["text"] for s in ln.get("spans", [])).strip()
                if not text:
                    continue
                sizes = sorted({_round(s["size"]) for s in spans}, reverse=True)
                bold = any(
                    ("Bold" in s.get("font", ""))
                    or ("Black" in s.get("font", ""))
                    or (int(s.get("flags", 0)) & BOLD_FLAG_BIT)
                    for s in spans
                )
                x0, y0, x1, y1 = ln["bbox"]
                lines.append(
                    {
                        "page": pno + 1,
                        "y0": _round(y0),
                        "x0": _round(x0),
                        "y1": _round(y1),
                        "x1": _round(x1),
                        "text": text,
                        "max_size": max(sizes),
                        "sizes": sizes,
                        "bold": bool(bold),
                        "engine": "pymupdf",
                        "mode": "styled",
                    }
                )
    n_pages = len(doc)
    doc.close()
    return lines, {"engine": "pymupdf", "mode": "styled", "pages": n_pages}


# ------------------------------------------------------------ pdftotext
def _run_pdftotext(args, timeout=120):
    exe = shutil.which("pdftotext")
    if not exe:
        raise RuntimeError("pdftotext 不在 PATH")
    return subprocess.run(
        [exe] + args, capture_output=True, text=False, timeout=timeout, check=True
    )


def extract_bbox(pdf_path):
    """pdftotext -bbox：词级几何，按 y 聚合成行；无字号/粗体信息。

    poppler 25 的 -bbox 输出中 <word> 直接挂在 <page> 下（无 <line>），
    故自行按 yMin 邻近度（<= 2pt 或词高 30%）聚行。
    """
    with tempfile.TemporaryDirectory() as td:
        out = os.path.join(td, "out.html")
        _run_pdftotext(["-bbox", pdf_path, out])
        tree = ET.parse(out)
    root = tree.getroot()
    ns = ""
    m = re.match(r"\{.*\}", root.tag)
    if m:
        ns = m.group(0)
    lines = []
    pages = root.findall(f".//{ns}page")
    for pno, pg in enumerate(pages, start=1):
        words = []
        for w in pg.findall(f".//{ns}word"):
            t = (w.text or "").strip()
            if not t:
                continue
            words.append(
                (float(w.get("yMin")), float(w.get("xMin")),
                 float(w.get("yMax")), float(w.get("xMax")), t)
            )
        words.sort(key=lambda w: (w[0], w[1]))
        groups = []  # [ [y0, x0, y1, x1, [word,...]], ... ]
        for y0, x0, y1, x1, t in words:
            if groups:
                g = groups[-1]
                tol = max(2.0, 0.3 * (g[2] - g[0]))
                if abs(y0 - g[0]) <= tol:
                    g[0] = min(g[0], y0)
                    g[1] = min(g[1], x0)
                    g[2] = max(g[2], y1)
                    g[3] = max(g[3], x1)
                    g[4].append((x0, t))
                    continue
            groups.append([y0, x0, y1, x1, [(x0, t)]])
        for y0, x0, y1, x1, ws in groups:
            text = " ".join(t for _, t in sorted(ws)).strip()
            lines.append(
                {
                    "page": pno,
                    "y0": _round(y0),
                    "x0": _round(x0),
                    "y1": _round(y1),
                    "x1": _round(x1),
                    "text": text,
                    "max_size": None,  # -bbox 不提供字号（诚实置空）
                    "sizes": [],
                    "bold": None,
                    "engine": "pdftotext-bbox",
                    "mode": "geometry",
                }
            )
    return lines, {
        "engine": "pdftotext-bbox",
        "mode": "geometry",
        "pages": len(pages),
    }


def extract_layout(pdf_path):
    """pdftotext -layout：纯文本；y0 用行序代替并显式标注。"""
    cp = _run_pdftotext(["-layout", pdf_path, "-"])
    raw = cp.stdout.decode("utf-8", errors="replace")
    pages = raw.split("\f")
    lines = []
    for pno, ptext in enumerate(pages, start=1):
        for ord_idx, t in enumerate(ptext.splitlines()):
            if not t.strip():
                continue
            indent = len(t) - len(t.lstrip())
            lines.append(
                {
                    "page": pno,
                    "y0": float(ord_idx),  # 行序，非真实纵坐标（诚实标注）
                    "x0": float(indent),
                    "y1": None,
                    "x1": None,
                    "text": t.strip(),
                    "max_size": None,
                    "sizes": [],
                    "bold": None,
                    "engine": "pdftotext-layout",
                    "mode": "text",
                }
            )
    n_pages = max(1, len(pages) - (1 if pages and not pages[-1].strip() else 0))
    return lines, {"engine": "pdftotext-layout", "mode": "text", "pages": n_pages}


# ---------------------------------------------------------------- main
def main(argv=None):
    ap = argparse.ArgumentParser(description="行级样式抽取（引擎链自动降级）")
    ap.add_argument("--pdf", required=True, help="输入 PDF 路径")
    ap.add_argument("--out", required=True, help="输出 lines.jsonl 路径")
    ap.add_argument("--report", required=True, help="输出抽取报告 JSON 路径")
    ap.add_argument(
        "--engine",
        default="auto",
        choices=["auto", "pymupdf", "bbox", "layout"],
        help="强制指定引擎（默认 auto：pymupdf → bbox → layout 链式降级）",
    )
    args = ap.parse_args(argv)

    if not os.path.isfile(args.pdf):
        print(f"[extract] 输入不存在: {args.pdf}", file=sys.stderr)
        return 3

    chain = {
        "auto": [("pymupdf", extract_pymupdf), ("bbox", extract_bbox), ("layout", extract_layout)],
        "pymupdf": [("pymupdf", extract_pymupdf)],
        "bbox": [("bbox", extract_bbox)],
        "layout": [("layout", extract_layout)],
    }[args.engine]

    fallbacks = []
    lines, info = None, None
    for name, fn in chain:
        try:
            lines, info = fn(args.pdf)
            info["requested_engine"] = args.engine
            break
        except Exception as e:  # noqa: BLE001 —— 任何失败都记录并降级
            fallbacks.append({"engine": name, "reason": f"{type(e).__name__}: {e}"})

    if lines is None:
        report = {
            "status": "failed",
            "pdf": os.path.abspath(args.pdf),
            "fallbacks": fallbacks,
            "uncertainty": "pymupdf 与 pdftotext 均不可用或失败，无法抽取任何行。",
        }
        with open(args.report, "w", encoding="utf-8") as f:
            json.dump(report, f, ensure_ascii=False, indent=2)
        print(f"[extract] 失败，报告见 {args.report}", file=sys.stderr)
        return 3

    # 阅读顺序按 (page, y0, x0) 排序；多栏重建不在本 skill 范围（见 SKILL.md 限制）
    lines.sort(key=lambda l: (l["page"], l["y0"] if l["y0"] is not None else 0.0,
                              l["x0"] if l["x0"] is not None else 0.0))
    for i, l in enumerate(lines):
        l["line_idx"] = i

    with open(args.out, "w", encoding="utf-8") as f:
        for l in lines:
            f.write(json.dumps(l, ensure_ascii=False) + "\n")

    styled_sizes = [l["max_size"] for l in lines if l.get("max_size")]
    report = {
        "status": "success" if info["mode"] == "styled" else "partial",
        "pdf": os.path.abspath(args.pdf),
        "engine": info["engine"],
        "mode": info["mode"],
        "pages": info["pages"],
        "line_count": len(lines),
        "fallbacks": fallbacks,
        "body_size_median_est": (
            statistics.median(styled_sizes) if styled_sizes else None
        ),
        "uncertainty": (
            []
            if info["mode"] == "styled"
            else [
                f"mode={info['mode']}：字号/粗体不可用，下游仅可用编号与关键词信号。"
            ]
        ),
    }
    with open(args.report, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)

    print(
        f"[extract] engine={info['engine']} mode={info['mode']} "
        f"lines={len(lines)} pages={info['pages']} fallbacks={len(fallbacks)}"
    )
    return 0 if info["mode"] == "styled" else 2


if __name__ == "__main__":
    sys.exit(main())
