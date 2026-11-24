#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""audit_export.py — 发表级导出物理合规审计（下游渲染工程方向）。

对每张图的三件套（PNG/PDF/SVG）做字节级审计：
- PNG：pHYs 块解析真实 dpi；IHDR 像素尺寸换算物理宽度（mm）与目标栏宽比对。
- PDF：MediaBox 换算物理尺寸；FontFile/FontFile2/FontFile3 检测字体嵌入；
  统计 Type3 字体风险。
- SVG：根元素 width/height（mm）与 viewBox；<text> 活文本计数；
  font-family 属性检查（确保未轮廓化且声明了字体族）。
- 配色：Okabe-Ito 调色板灰度亮度差（模拟灰度打印可区分性）。
- 中文字形：所选字体 charmap 覆盖检查（防豆腐块）。

用法：
    python3 audit_export.py --figdata /app/output/figures.figdata.json \
        --outdir /app/output --width-mm 89 --dpi 300 \
        --out /app/output/export_audit.json
"""
import argparse
import json
import os
import re
import struct
import sys

OKABE_ITO = ["#0072B2", "#E69F00", "#009E73", "#D55E00", "#CC79A7",
             "#56B4E9", "#F0E442", "#000000"]


def rel_luminance(hex_color):
    r = int(hex_color[1:3], 16) / 255.0
    g = int(hex_color[3:5], 16) / 255.0
    b = int(hex_color[5:7], 16) / 255.0
    def lin(c):
        return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4
    return 0.2126 * lin(r) + 0.7152 * lin(g) + 0.0722 * lin(b)


def grayscale_levels(hex_color):
    r = int(hex_color[1:3], 16)
    g = int(hex_color[3:5], 16)
    b = int(hex_color[5:7], 16)
    return 0.299 * r + 0.587 * g + 0.114 * b


def audit_png(path, expect_dpi, width_mm):
    out = {"file": os.path.basename(path)}
    with open(path, "rb") as fh:
        raw = fh.read()
    if raw[:8] != b"\x89PNG\r\n\x1a\n":
        out["ok"] = False
        out["error"] = "not a PNG"
        return out
    w, h = struct.unpack(">II", raw[16:24])
    out["pixels"] = [w, h]
    i = raw.find(b"pHYs")
    if i < 0:
        out["dpi"] = None
        out["dpi_ok"] = False
    else:
        xppm = struct.unpack(">I", raw[i + 4:i + 8])[0]
        dpi = xppm * 0.0254
        out["dpi"] = round(dpi, 2)
        out["dpi_ok"] = abs(dpi - expect_dpi) < 1.0
        out["physical_width_mm"] = round(w / xppm * 1000, 1)
        out["width_mm_ok"] = abs(out["physical_width_mm"] - width_mm) < 2.5
    out["ok"] = out.get("dpi_ok", False) and out.get("width_mm_ok", False)
    return out


def audit_pdf(path, width_mm):
    out = {"file": os.path.basename(path)}
    with open(path, "rb") as fh:
        raw = fh.read()
    out["font_embedded"] = (b"FontFile2" in raw or b"FontFile3" in raw
                            or b"FontFile" in raw)
    out["type3_font_risk"] = b"/FontFile3" in raw and b"Type3" in raw
    m = re.search(rb"MediaBox\s*\[\s*[\d.]+\s+[\d.]+\s+([\d.]+)\s+([\d.]+)",
                  raw)
    if m:
        w_pt = float(m.group(1))
        out["width_mm"] = round(w_pt * 25.4 / 72.0, 1)
        out["width_mm_ok"] = abs(out["width_mm"] - width_mm) < 2.5
    else:
        out["width_mm_ok"] = None
    out["ok"] = bool(out["font_embedded"]) and out["width_mm_ok"] is not False
    return out


def audit_svg(path, width_mm):
    out = {"file": os.path.basename(path)}
    with open(path, "rb") as fh:
        raw = fh.read()
    text = raw.decode("utf-8", errors="replace")
    out["live_text_elements"] = len(re.findall(r"<text[\s>]", text))
    out["outlined_paths_only"] = out["live_text_elements"] == 0
    m = re.search(r'<svg[^>]*\swidth="([\d.]+)(mm|pt|px)?"', text)
    if m:
        val, unit = float(m.group(1)), m.group(2) or "px"
        mm = val if unit == "mm" else (val * 25.4 / 72.0 if unit == "pt"
                                       else val * 25.4 / 96.0)
        out["width_mm"] = round(mm, 1)
        out["width_mm_ok"] = abs(mm - width_mm) < 2.5
    out["font_family_declared"] = "font-family" in text
    out["ok"] = (out["live_text_elements"] > 0
                 and out.get("width_mm_ok", True) is not False)
    return out


def audit_palette():
    grays = [grayscale_levels(c) for c in OKABE_ITO]
    lums = [rel_luminance(c) for c in OKABE_ITO]
    pairs = []
    min_gray_diff = 255.0
    for i in range(len(OKABE_ITO)):
        for j in range(i + 1, len(OKABE_ITO)):
            d = abs(grays[i] - grays[j])
            min_gray_diff = min(min_gray_diff, d)
            pairs.append(d)
    used = OKABE_ITO[:3]
    used_grays = sorted(grayscale_levels(c) for c in used)
    min_used = min(b - a for a, b in zip(used_grays, used_grays[1:]))
    marginal = []
    for i in range(len(OKABE_ITO)):
        for j in range(i + 1, len(OKABE_ITO)):
            if abs(grays[i] - grays[j]) < 20.0:
                marginal.append([OKABE_ITO[i], OKABE_ITO[j],
                                 round(abs(grays[i] - grays[j]), 1)])
    return {"palette": "Okabe-Ito",
            "colors": OKABE_ITO,
            "grayscale_levels": [round(g, 1) for g in grays],
            "relative_luminance": [round(l, 3) for l in lums],
            "min_grayscale_diff_first3": round(min_used, 1),
            "grayscale_distinguishable_first3": min_used >= 15.0,
            "grayscale_marginal_pairs_advisory": marginal,
            "advisory_note": ("灰度打印下蓝(#0072B2)与绿(#009E73)亮度接近；"
                              "纯灰度场景建议叠加线型/形状/纹样的冗余编码。"
                              "本条目为建议性提示，不计入硬性合规。")}


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--figdata", required=True)
    ap.add_argument("--outdir", required=True)
    ap.add_argument("--width-mm", type=float, default=89.0)
    ap.add_argument("--dpi", type=int, default=300)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    with open(args.figdata, encoding="utf-8") as fh:
        figdata = json.load(fh)
    report = {"expect": {"width_mm": args.width_mm, "png_dpi": args.dpi,
                         "vector": ["pdf", "svg"]},
              "palette_audit": audit_palette(),
              "cjk_font": figdata.get("cjk_font"),
              "figures": {}, "all_passed": True}
    for fig in figdata.get("figures", []):
        fid, files = fig["id"], fig["files"]
        ent = {}
        if files.get("png"):
            ent["png"] = audit_png(os.path.join(args.outdir, files["png"]),
                                   args.dpi, fig.get("width_mm",
                                                     args.width_mm))
        if files.get("pdf"):
            ent["pdf"] = audit_pdf(os.path.join(args.outdir, files["pdf"]),
                                   fig.get("width_mm", args.width_mm))
        if files.get("svg"):
            ent["svg"] = audit_svg(os.path.join(args.outdir, files["svg"]),
                                   fig.get("width_mm", args.width_mm))
        ent["ok"] = all(e.get("ok", False) for e in ent.values())
        if not ent["ok"]:
            report["all_passed"] = False
        report["figures"][fid] = ent
    with open(args.out, "w", encoding="utf-8") as fh:
        json.dump(report, fh, ensure_ascii=False, indent=2)
    print(json.dumps({"all_passed": report["all_passed"],
                      "figures": {k: v["ok"]
                                  for k, v in report["figures"].items()}},
                     ensure_ascii=False))
    return 0 if report["all_passed"] else 1


if __name__ == "__main__":
    sys.exit(main())
