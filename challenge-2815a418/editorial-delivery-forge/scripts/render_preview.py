#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""render_preview.py — 交付件预览渲染器。

把交付件 markdown 用 matplotlib 逐段排版到 A4 比例页面（8.27in × 11.69in），
每页一张 PNG 存入 preview/，并合并输出 preview.pdf，供编辑/评审目检。

降级规则（均不阻断，exit 0）：
  - matplotlib 缺失：只写 render_manifest.json（degraded=true，注明原因）；
  - 中文字体缺失：按回退链探测（PingFang SC → Hiragino Sans GB → STSong →
    Noto Sans CJK SC → Noto Sans CJK → WenQuanYi Zen Hei → Microsoft YaHei），
    全部缺失仍真实渲染（中文呈占位框）并在 manifest 注明 cjk_font_available=false。

除 matplotlib 外仅依赖标准库。

用法：
  python3 render_preview.py --outdir /app/output/preview file1.md [file2.md ...]
"""
import argparse
import json
import os
import sys
from datetime import datetime, timezone

FONT_FALLBACK = ["PingFang SC", "Hiragino Sans GB", "STSong", "Noto Sans CJK SC",
                 "Noto Sans CJK JP", "Noto Sans CJK", "WenQuanYi Zen Hei", "Microsoft YaHei"]
PAGE_W_IN, PAGE_H_IN = 8.27, 11.69  # A4
DPI = 110


def char_units(ch):
    return 1.0 if ord(ch) >= 0x2E80 else 0.55


def wrap_line(text, max_units):
    """按显示宽度折行（CJK 按 1，ASCII 按 0.55 估算）。"""
    if not text:
        return [""]
    out, cur, curw = [], "", 0.0
    for ch in text:
        u = char_units(ch)
        if curw + u > max_units and cur:
            out.append(cur)
            cur, curw = ch, u
        else:
            cur += ch
            curw += u
    if cur or not out:
        out.append(cur)
    return out


def md_to_lines(md_text):
    """把 markdown 转为 (text, fontsize, bold) 行序列。"""
    rows = []
    for raw in md_text.splitlines():
        line = raw.rstrip()
        fs, bold = 10.0, False
        stripped = line.lstrip()
        if stripped.startswith("### "):
            fs, bold, line = 11.5, True, stripped[4:]
        elif stripped.startswith("## "):
            fs, bold, line = 13.0, True, stripped[3:]
        elif stripped.startswith("# "):
            fs, bold, line = 15.0, True, stripped[2:]
        elif stripped.startswith(">"):
            fs, line = 9.0, "  " + stripped.lstrip("> ")
        elif stripped.startswith("|---"):
            continue  # 跳过分隔行
        elif stripped.startswith("```"):
            continue
        for w in wrap_line(line, 46.0 * (10.0 / fs)):
            rows.append((w, fs, bold))
        if not line:
            pass
    return rows


def main():
    ap = argparse.ArgumentParser(description="交付件预览渲染器")
    ap.add_argument("--outdir", required=True)
    ap.add_argument("files", nargs="+")
    args = ap.parse_args()

    os.makedirs(args.outdir, exist_ok=True)
    manifest = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "matplotlib_available": False,
        "cjk_font_available": False,
        "font_used": None,
        "font_fallback_chain": FONT_FALLBACK,
        "degraded": True,
        "degraded_reasons": [],
        "page_spec": "A4 ratio %.2fin x %.2fin @ %ddpi" % (PAGE_W_IN, PAGE_H_IN, DPI),
        "files": {},
        "pdf": None,
    }

    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        from matplotlib import font_manager
        from matplotlib.backends.backend_pdf import PdfPages
    except Exception as exc:  # 降级：matplotlib 缺失
        manifest["degraded_reasons"].append("matplotlib 不可用：%s" % exc)
        with open(os.path.join(args.outdir, "render_manifest.json"), "w", encoding="utf-8") as f:
            json.dump(manifest, f, ensure_ascii=False, indent=2)
        print("render_preview: DEGRADED (matplotlib 不可用)，已写 render_manifest.json，不阻断。")
        return 0

    manifest["matplotlib_available"] = True
    try:
        available = {f.name for f in font_manager.fontManager.ttflist}
    except Exception:
        available = set()
    font = next((c for c in FONT_FALLBACK if c in available), None)
    if font:
        manifest["font_used"] = font
        manifest["cjk_font_available"] = True
        plt.rcParams["font.family"] = [font, "DejaVu Sans"]
        manifest["degraded"] = False
    else:
        manifest["degraded_reasons"].append(
            "未探测到中文字体（回退链：%s）；中文将以占位框渲染，仍属真实渲染输出。" % " / ".join(FONT_FALLBACK))
        plt.rcParams["font.family"] = ["DejaVu Sans"]
    plt.rcParams["axes.unicode_minus"] = False

    pdf_path = os.path.join(args.outdir, "preview.pdf")
    pdf = PdfPages(pdf_path)
    try:
        for path in args.files:
            stem = os.path.splitext(os.path.basename(path))[0]
            try:
                with open(path, "r", encoding="utf-8") as f:
                    md = f.read()
            except OSError as exc:
                manifest["files"][stem] = {"error": str(exc), "pages": 0, "pngs": []}
                manifest["degraded_reasons"].append("读取失败 %s：%s" % (path, exc))
                continue
            rows = md_to_lines(md)
            # 分页
            pages, cur, y = [], [], None
            y_top, y_bottom, margin_x = 0.955, 0.055, 0.075
            y = y_top
            for text, fs, bold in rows:
                step = (fs * 1.75) / (PAGE_H_IN * 72.0)
                if y - step < y_bottom:
                    pages.append(cur)
                    cur, y = [], y_top
                cur.append((text, fs, bold, y))
                y -= step
            pages.append(cur)
            total = len(pages)
            pngs = []
            for n, page in enumerate(pages, start=1):
                fig = plt.figure(figsize=(PAGE_W_IN, PAGE_H_IN), dpi=DPI)
                ax = fig.add_axes([0, 0, 1, 1])
                ax.set_xlim(0, 1)
                ax.set_ylim(0, 1)
                ax.axis("off")
                ax.text(margin_x, 0.982, "%s — 第 %d/%d 页" % (os.path.basename(path), n, total),
                        fontsize=8, color="#666666", va="top")
                ax.plot([margin_x, 1 - margin_x], [0.972, 0.972], color="#cccccc", lw=0.6)
                for text, fs, bold, yy in page:
                    ax.text(margin_x, yy, text, fontsize=fs,
                            fontweight="bold" if bold else "normal",
                            color="#111111", va="top")
                png_name = "%s-p%03d.png" % (stem, n)
                png_path = os.path.join(args.outdir, png_name)
                fig.savefig(png_path, dpi=DPI, facecolor="white")
                pdf.savefig(fig)
                plt.close(fig)
                pngs.append(png_name)
            manifest["files"][stem] = {"source": os.path.abspath(path), "pages": total, "pngs": pngs}
    finally:
        pdf.close()
    manifest["pdf"] = os.path.abspath(pdf_path)

    with open(os.path.join(args.outdir, "render_manifest.json"), "w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2)
    n_png = sum(len(v.get("pngs", [])) for v in manifest["files"].values())
    print("render_preview: %d 个文件，共 %d 页 PNG + preview.pdf -> %s%s" % (
        len(manifest["files"]), n_png, args.outdir,
        "（降级：%s）" % "; ".join(manifest["degraded_reasons"]) if manifest["degraded"] else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main())
