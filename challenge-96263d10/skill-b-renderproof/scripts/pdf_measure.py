#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""pdf_measure.py -- 在渲染出的 PDF 上实测版式事实（不信 XML，只信页面）。

测量项：
  page.size / page.count    -- 解析 /MediaBox（stdlib 字节扫描）
  fonts                     -- /BaseFont 清单 + 内嵌判定（/FontFile|FontFile2|FontFile3
                               计数，启发式，详见 references/render-method.md）
  text margins / columns    -- 调 pdftotext -bbox-layout 取每个词的字形框，
                               求版心实测边距与栏间隙；pdftotext 缺失则记 UNMEASURED
退出码: 0 完成（含部分 UNMEASURED）; 2 PDF 不可读。

用法:
  python3 pdf_measure.py 文件.pdf --out measurements.json
环境变量 PDFTOTEXT 可指定 pdftotext 路径。
"""
import argparse, json, os, re, shutil, subprocess, sys, xml.etree.ElementTree as ET

PT2CM = 1.0 / 28.3465

def scan_media_boxes(raw):
    boxes = []
    for m in re.finditer(rb"/MediaBox\s*\[\s*([-\d.]+)\s+([-\d.]+)\s+([-\d.]+)\s+([-\d.]+)\s*\]", raw):
        x0, y0, x1, y1 = (float(g) for g in m.groups())
        boxes.append({"w_pt": x1 - x0, "h_pt": y1 - y0,
                      "w_cm": round((x1 - x0) * PT2CM, 3), "h_cm": round((y1 - y0) * PT2CM, 3)})
    uniq = []
    for b in boxes:
        if b not in uniq:
            uniq.append(b)
    return uniq, len(boxes)

def scan_fonts(raw):
    fonts = sorted(set(m.group(1).decode("latin-1") for m in re.finditer(rb"/BaseFont\s*/([A-Za-z0-9+_,.\-]+)", raw)))
    embeds = len(re.findall(rb"/FontFile[23]?\b", raw))
    # 启发式：FontFile 流不少于去重字体数则视为全部内嵌（base-14 字体可不内嵌）
    base14 = {"Courier", "Courier-Bold", "Courier-Oblique", "Courier-BoldOblique",
              "Helvetica", "Helvetica-Bold", "Helvetica-Oblique", "Helvetica-BoldOblique",
              "Times-Roman", "Times-Bold", "Times-Italic", "Times-BoldItalic", "Symbol", "ZapfDingbats"}
    non_base = [f for f in fonts if f.split("+")[-1] not in base14]
    return {"fonts": fonts, "non_base14_fonts": non_base, "font_file_streams": embeds,
            "embedded_all_heuristic": embeds >= len(fonts) if fonts else True}

def bbox_measure(pdf_path):
    pdftotext = os.environ.get("PDFTOTEXT") or shutil.which("pdftotext")
    if not pdftotext:
        return {"status": "UNMEASURED", "reason": "pdftotext not found"}
    p = subprocess.run([pdftotext, "-bbox-layout", pdf_path, "-"],
                       capture_output=True, text=True, timeout=300)
    if p.returncode != 0:
        return {"status": "UNMEASURED", "reason": (p.stderr or "pdftotext failed")[:300]}
    pages = []
    for pm in re.finditer(r"<page[^>]*width=\"([\d.]+)\" height=\"([\d.]+)\"[^>]*>(.*?)</page>",
                          p.stdout, re.S):
        pw, ph, body = float(pm.group(1)), float(pm.group(2)), pm.group(3)
        words = [(float(w.group(1)), float(w.group(2)), float(w.group(3)), float(w.group(4)))
                 for w in re.finditer(r"<word xMin=\"([\d.]+)\" yMin=\"([\d.]+)\" xMax=\"([\d.]+)\" yMax=\"([\d.]+)\"", body)]
        if not words:
            pages.append({"width_pt": pw, "height_pt": ph, "words": 0})
            continue
        x0 = min(w[0] for w in words); x1 = max(w[2] for w in words)
        y0 = min(w[1] for w in words); y1 = max(w[3] for w in words)
        # 栏检测：页宽中部 25%–75% 区间内找宽度>=8pt 的无字竖带；
        # 真栏缝要求两侧各有 >=3 个词（排除单栏 ragged-right 的空带误判）
        gutter = None
        lo, hi = pw * 0.25, pw * 0.75
        x = lo
        while x + 8 <= hi:
            if not any(w[0] < x + 8 and w[2] > x for w in words):
                left_n = sum(1 for w in words if w[2] <= x)
                right_n = sum(1 for w in words if w[0] >= x + 8)
                if left_n >= 3 and right_n >= 3:
                    gutter = round(x, 1)
                    break
            x += 2.0
        pages.append({"width_pt": pw, "height_pt": ph, "words": len(words),
                      "margin_left_cm": round(x0 * PT2CM, 3),
                      "margin_right_cm": round((pw - x1) * PT2CM, 3),
                      "margin_top_cm": round(y0 * PT2CM, 3),
                      "margin_bottom_cm": round((ph - y1) * PT2CM, 3),
                      "gutter_at_pt": gutter,
                      "columns_detected": 2 if gutter else 1})
    return {"status": "OK", "tool": pdftotext, "pages": pages}

def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("pdf")
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    try:
        raw = open(a.pdf, "rb").read()
        if not raw.startswith(b"%PDF"):
            raise ValueError("missing %PDF header")
    except (OSError, ValueError) as e:
        print("ERROR: PDF 不可读: %s" % e, file=sys.stderr)
        sys.exit(2)

    boxes, nbox = scan_media_boxes(raw)
    fonts = scan_fonts(raw)
    bbox = bbox_measure(a.pdf)
    out = {"pdf": a.pdf, "page_count_media_boxes": nbox, "page_sizes": boxes,
           "fonts": fonts, "text_geometry": bbox}
    json.dump(out, open(a.out, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    gm = "OK" if bbox.get("status") == "OK" else "UNMEASURED"
    print("pages=%d sizes=%s fonts=%d embedded_all=%s geometry=%s -> %s" % (
        nbox, [(b["w_cm"], b["h_cm"]) for b in boxes], len(fonts["fonts"]),
        fonts["embedded_all_heuristic"], gm, a.out))

if __name__ == "__main__":
    main()
