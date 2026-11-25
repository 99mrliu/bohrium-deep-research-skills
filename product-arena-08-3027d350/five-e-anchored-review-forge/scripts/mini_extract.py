#!/usr/bin/env python3
"""mini_extract.py — 最小提取器：把 PDF 快速变成 blocks.jsonl + page_meta.json。

用途：示例喂数据；评测时若上游已提供 blocks.jsonl 则跳过本脚本（见 SKILL.md）。
本脚本只做"够用"的几何聚块与规则分类，不做抽取算法本体。

引擎链（自动降级，降级原因写入报告）：
  1. pymupdf（span 级 token，带字号 → 可判 title）
  2. pdftotext -bbox（word 级 token，无字号 → title 用兜底规则）
核心聚块/分类逻辑只用标准库；两个引擎都不可用时退出码 3。

退出码：0=成功，2=部分（有页零块或单引擎降级之外的警告），3=失败。

阈值（与 SKILL.md「方法要点」、references/block-schema.md 保持一致）：
  行归并   |y0 差| <= max(2.0, 0.35 * 词高中位数)
  块切分   行距（相邻行 y0 差）> 1.5 * 基准行距（全页正行距的 25 百分位），
           或 x 区间不重叠（容差 2pt）
  caption  文本以 Figure/Fig./Table 开头（忽略大小写）
  equation 含 '=' 且字母占比 < 0.6 且长度 < 120 字符
  heading  单行、<= 60 字符、以编号开头（如 "1." / "2.1 "）
  title    pymupdf：首页块最大字号 >= 1.25 * 全文字号中位数（取首个）；
           pdftotext 兜底：首页首块且单行且 <= 90 字符
  其余 -> body；column 按块中心 x 是否越过页宽中线取 1/2
"""

import argparse
import json
import os
import re
import shutil
import statistics
import subprocess
import sys

EXIT_OK, EXIT_PARTIAL, EXIT_FAIL = 0, 2, 3

LINE_Y_TOL_MIN = 2.0
LINE_Y_TOL_RATIO = 0.35
BLOCK_PITCH_RATIO = 1.5
PITCH_PERCENTILE = 25
X_DISJOINT_PAD = 2.0
CAPTION_RE = re.compile(r"^(figure|fig\.|table)\b", re.IGNORECASE)
HEADING_RE = re.compile(r"^\d+(\.\d+)*[.\s]\s*\S+")
HEADING_MAX_CHARS = 60
EQUATION_MAX_LEN = 120
EQUATION_ALPHA_MAX = 0.6
TITLE_SIZE_RATIO = 1.25
TITLE_FALLBACK_MAX_CHARS = 90
COLUMN_SPLIT_RATIO = 0.5


def sha256_file(path):
    import hashlib
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


# ---------------- 引擎 ----------------

def tokens_via_pymupdf(pdf_path):
    import pymupdf  # 可选依赖，缺失时由调用方降级
    doc = pymupdf.open(pdf_path)
    pages = []
    for pno in range(doc.page_count):
        page = doc[pno]
        toks = []
        for blk in page.get_text("dict").get("blocks", []):
            if blk.get("type", 0) != 0:
                continue
            for line in blk.get("lines", []):
                for sp in line.get("spans", []):
                    text = (sp.get("text") or "").strip()
                    if not text:
                        continue
                    x0, y0, x1, y1 = sp["bbox"]
                    toks.append({"x0": x0, "y0": y0, "x1": x1, "y1": y1,
                                 "text": text, "size": float(sp.get("size", 0))})
        pages.append({"page": pno + 1,
                      "width": float(page.rect.width),
                      "height": float(page.rect.height),
                      "tokens": toks})
    doc.close()
    return pages


def tokens_via_pdftotext(pdf_path, work_dir):
    import xml.etree.ElementTree as ET
    out = os.path.join(work_dir, "_pdftotext_bbox.xhtml")
    proc = subprocess.run(["pdftotext", "-bbox", pdf_path, out],
                          capture_output=True, text=True)
    if proc.returncode != 0:
        raise RuntimeError(f"pdftotext 退出码 {proc.returncode}: {proc.stderr.strip()[:200]}")
    root = ET.parse(out).getroot()
    pages = []
    for el in root.iter():
        if el.tag.split("}")[-1] != "page":
            continue
        toks = []
        for w in el.iter():
            if w.tag.split("}")[-1] != "word":
                continue
            text = (w.text or "").strip()
            if not text:
                continue
            toks.append({"x0": float(w.get("xMin")), "y0": float(w.get("yMin")),
                         "x1": float(w.get("xMax")), "y1": float(w.get("yMax")),
                         "text": text, "size": None})
        pages.append({"page": len(pages) + 1,
                      "width": float(el.get("width")),
                      "height": float(el.get("height")),
                      "tokens": toks})
    os.remove(out)
    return pages


# ---------------- 聚块与分类（纯标准库） ----------------

def cluster_page(page):
    """token -> 行 -> 块。返回块列表（保留 size 供 title 判定）。"""
    toks = sorted(page["tokens"], key=lambda t: (t["y0"], t["x0"]))
    if not toks:
        return []
    h_med = statistics.median(t["y1"] - t["y0"] for t in toks) or 10.0
    y_tol = max(LINE_Y_TOL_MIN, LINE_Y_TOL_RATIO * h_med)

    lines = []
    for t in toks:
        if lines and abs(t["y0"] - lines[-1]["y0"]) <= y_tol:
            ln = lines[-1]
            ln["tokens"].append(t)
            ln["y0"] = min(ln["y0"], t["y0"])
            ln["y1"] = max(ln["y1"], t["y1"])
        else:
            lines.append({"tokens": [t], "y0": t["y0"], "y1": t["y1"]})
    for ln in lines:
        ln["tokens"].sort(key=lambda t: t["x0"])
        ln["x0"] = min(t["x0"] for t in ln["tokens"])
        ln["x1"] = max(t["x1"] for t in ln["tokens"])
        ln["text"] = " ".join(t["text"] for t in ln["tokens"])
        ln["sizes"] = [t["size"] for t in ln["tokens"] if t["size"]]

    # 基准行距：全页正行距（相邻行 y0 差）的 25 百分位。
    # 用 y0 差而非 bbox 间隙，规避 pymupdf/pdftotext 行框含上下留白导致的
    # "段落间隙被吃掉"问题。
    pitches = sorted(lines[i + 1]["y0"] - lines[i]["y0"]
                     for i in range(len(lines) - 1))
    pos = [p for p in pitches if p > 0.5]
    base_pitch = pos[max(0, (len(pos) - 1) * PITCH_PERCENTILE // 100)] if pos else None
    pitch_thresh = BLOCK_PITCH_RATIO * base_pitch if base_pitch else None

    blocks = []
    prev_line = None
    for ln in lines:
        new_block = True
        if blocks:
            prev = blocks[-1]
            pitch = ln["y0"] - prev_line["y0"]
            x_disjoint = (ln["x0"] > prev["x1"] + X_DISJOINT_PAD or
                          prev["x0"] > ln["x1"] + X_DISJOINT_PAD)
            if (pitch_thresh is None or pitch <= pitch_thresh) and not x_disjoint:
                new_block = False
        prev_line = ln
        if new_block:
            blocks.append({"lines": [ln],
                           "x0": ln["x0"], "y0": ln["y0"],
                           "x1": ln["x1"], "y1": ln["y1"]})
        else:
            prev = blocks[-1]
            prev["lines"].append(ln)
            prev["x0"] = min(prev["x0"], ln["x0"])
            prev["x1"] = max(prev["x1"], ln["x1"])
            prev["y1"] = max(prev["y1"], ln["y1"])
    for b in blocks:
        b["text"] = "\n".join(ln["text"] for ln in b["lines"])
        b["sizes"] = [s for ln in b["lines"] for s in ln["sizes"]]
    return blocks


def alpha_ratio(text):
    letters = sum(1 for c in text if c.isalpha())
    return letters / max(len(text), 1)


def assign_kinds(pages_blocks, engine):
    """就地设置 kind/column。返回警告列表。"""
    warnings = []
    all_sizes = [s for pb in pages_blocks for b in pb["blocks"] for s in b["sizes"]]
    size_med = statistics.median(all_sizes) if all_sizes else None
    title_taken = False
    for pb in pages_blocks:
        page_w = pb["width"]
        for b in pb["blocks"]:
            text = b["text"]
            one_line = len(b["lines"]) == 1
            cx = (b["x0"] + b["x1"]) / 2.0
            b["column"] = 1 if cx < page_w * COLUMN_SPLIT_RATIO else 2
            kind = "body"
            if CAPTION_RE.match(text):
                kind = "caption"
            elif ("=" in text and len(text) < EQUATION_MAX_LEN
                  and alpha_ratio(text) < EQUATION_ALPHA_MAX):
                kind = "equation"
            elif one_line and len(text) <= HEADING_MAX_CHARS and HEADING_RE.match(text):
                kind = "heading"
            elif not title_taken and pb["page"] == 1 and b is pb["blocks"][0]:
                if size_med and b["sizes"] and max(b["sizes"]) >= TITLE_SIZE_RATIO * size_med:
                    kind = "title"
                elif engine.startswith("pdftotext") and one_line \
                        and len(text) <= TITLE_FALLBACK_MAX_CHARS:
                    kind = "title"
                    warnings.append("title 由 pdftotext 兜底规则判定（无字号信息）")
                if kind == "title":
                    title_taken = True
            b["kind"] = kind
    return warnings


# ---------------- 主流程 ----------------

def main():
    ap = argparse.ArgumentParser(description="最小提取器：PDF -> blocks.jsonl + page_meta.json")
    ap.add_argument("--pdf", required=True)
    ap.add_argument("--out-dir", required=True)
    args = ap.parse_args()

    os.makedirs(args.out_dir, exist_ok=True)
    report = {"script": "mini_extract.py", "pdf": os.path.abspath(args.pdf),
              "engine": None, "degraded_from": None, "degrade_reason": None,
              "warnings": [], "status": "failed"}
    blocks_path = os.path.join(args.out_dir, "blocks.jsonl")
    meta_path = os.path.join(args.out_dir, "page_meta.json")

    if not os.path.isfile(args.pdf):
        report["warnings"].append(f"PDF 不存在: {args.pdf}")
        return finish(report, args.out_dir, EXIT_FAIL)

    pages = None
    try:
        pages = tokens_via_pymupdf(args.pdf)
        report["engine"] = "pymupdf"
    except Exception as e1:  # noqa: BLE001 — 任何 pymupdf 失败都降级
        if shutil.which("pdftotext"):
            try:
                pages = tokens_via_pdftotext(args.pdf, args.out_dir)
                report["engine"] = "pdftotext -bbox"
                report["degraded_from"] = "pymupdf"
                report["degrade_reason"] = f"{type(e1).__name__}: {e1}"[:300]
            except Exception as e2:  # noqa: BLE001
                report["warnings"].append(
                    f"pymupdf 失败({e1}); pdftotext 失败({e2})"[:400])
        else:
            report["warnings"].append(
                f"pymupdf 不可用({e1}); 且无 pdftotext 可降级"[:400])
    if pages is None:
        return finish(report, args.out_dir, EXIT_FAIL)

    pages_blocks = []
    for p in pages:
        pages_blocks.append({"page": p["page"], "width": p["width"],
                             "height": p["height"], "blocks": cluster_page(p)})
    report["warnings"].extend(assign_kinds(pages_blocks, report["engine"]))

    empty_pages = [pb["page"] for pb in pages_blocks if not pb["blocks"]]
    total_blocks = sum(len(pb["blocks"]) for pb in pages_blocks)
    if total_blocks == 0:
        report["warnings"].append("全文未提取到任何文本块")
        return finish(report, args.out_dir, EXIT_FAIL)
    if empty_pages:
        report["warnings"].append(f"以下页零文本块: {empty_pages}")

    order = 0
    kind_counts = {}
    with open(blocks_path, "w", encoding="utf-8") as f:
        for pb in pages_blocks:
            for i, b in enumerate(pb["blocks"], start=1):
                order += 1
                kind_counts[b["kind"]] = kind_counts.get(b["kind"], 0) + 1
                rec = {"id": f"p{pb['page']}.b{i}", "page": pb["page"],
                       "kind": b["kind"],
                       "bbox": [round(b["x0"], 2), round(b["y0"], 2),
                                round(b["x1"], 2), round(b["y1"], 2)],
                       "text": b["text"], "column": b["column"], "order": order}
                f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    with open(meta_path, "w", encoding="utf-8") as f:
        json.dump({"pages": [{"page": pb["page"], "width": round(pb["width"], 2),
                              "height": round(pb["height"], 2)}
                             for pb in pages_blocks]},
                  f, ensure_ascii=False, indent=2)
        f.write("\n")

    report.update({
        "pages": len(pages_blocks), "blocks": total_blocks,
        "kind_counts": kind_counts,
        "outputs": {"blocks_jsonl": blocks_path, "page_meta_json": meta_path},
        "input_sha256": sha256_file(args.pdf),
        "status": "partial" if (empty_pages or report["degraded_from"]
                                or report["warnings"]) else "success",
    })
    code = EXIT_PARTIAL if report["status"] == "partial" else EXIT_OK
    return finish(report, args.out_dir, code)


def finish(report, out_dir, code):
    report["exit_code"] = code
    path = os.path.join(out_dir, "extract.report.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
        f.write("\n")
    print(json.dumps(report, ensure_ascii=False))
    return code


if __name__ == "__main__":
    sys.exit(main())
