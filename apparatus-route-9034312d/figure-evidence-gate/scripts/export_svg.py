#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""export_svg.py — SVG → PDF/PNG 导出回退链（纯标准库，绝不抛异常，必写报告）。

用法:
    python3 export_svg.py <figure.svg> [--pdf out.pdf] [--png out.png]
                                       [--report export_report.json]

回退链（每个目标格式独立尝试，全部失败才算该格式 unavailable）:
    1. cairosvg     （Python 可选依赖，import 失败即跳过）
    2. rsvg-convert （PATH 查找）
    3. inkscape     （PATH 查找）
    4. Chrome/Chromium headless（macOS /Applications/Google Chrome.app 路径 +
       google-chrome / chromium / chromium-browser 命令名）
       PDF: --headless --print-to-pdf（HTML 包装器按 SVG 尺寸设 @page）
       PNG: --headless --screenshot --window-size=W,H --force-device-scale-factor=2

无论成败都会写出 export_report.json，逐次记录每个尝试的工具/目标/状态/详情。
"""
import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile

CHROME_CANDIDATES = [
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",  # macOS
    "google-chrome", "google-chrome-stable", "chromium", "chromium-browser", "chrome",
]
MM_PER_PX = 25.4 / 96.0


def svg_size_px(svg_path):
    """解析 SVG 尺寸，返回 (w_px, h_px)。支持 px/mm 单位与 viewBox，兜底 800x600。"""
    try:
        with open(svg_path, "r", encoding="utf-8") as f:
            head = f.read(4000)
        m = re.search(r"<svg\b[^>]*>", head, re.S)
        tag = m.group(0) if m else head

        def attr(name):
            a = re.search(name + r'\s*=\s*"([0-9.]+)\s*(mm|px|pt)?"', tag)
            return (float(a.group(1)), a.group(2) or "px") if a else None

        def to_px(v, unit):
            return v * 96.0 / 25.4 if unit == "mm" else (v * 96.0 / 72.0 if unit == "pt" else v)

        w, h = attr("width"), attr("height")
        if w and h:
            return max(1, int(to_px(*w))), max(1, int(to_px(*h)))
        vb = re.search(r'viewBox\s*=\s*"[\d.\-]+\s+[\d.\-]+\s+([\d.]+)\s+([\d.]+)"', tag)
        if vb:
            return max(1, int(float(vb.group(1)))), max(1, int(float(vb.group(2))))
    except Exception:
        pass
    return 800, 600


def find_chrome():
    for c in CHROME_CANDIDATES:
        if os.path.isabs(c):
            if os.path.isfile(c):
                return c
        else:
            p = shutil.which(c)
            if p:
                return p
    return None


def file_url(path):
    return "file://" + os.path.abspath(path)


def ok_file(path, min_bytes=200):
    try:
        return os.path.isfile(path) and os.path.getsize(path) >= min_bytes
    except OSError:
        return False


# ---- 各工具的导出实现：成功返回 "ok"，不可用返回 "unavailable"，失败抛 RuntimeError ----

def run_cairosvg(svg, target, out, size):
    import cairosvg  # noqa: F401  故意延迟 import；ImportError 由上层捕获记 unavailable
    if target == "pdf":
        cairosvg.svg2pdf(url=svg, write_to=out)
    else:
        cairosvg.svg2png(url=svg, write_to=out, scale=2.0)
    return "ok"


def run_rsvg(svg, target, out, size):
    exe = shutil.which("rsvg-convert")
    if not exe:
        return "unavailable"
    cmd = [exe, "-o", out]
    if target == "pdf":
        cmd += ["-f", "pdf"]
    else:
        cmd += ["-z", "2.0", "-f", "png"]
    cmd.append(svg)
    subprocess.run(cmd, check=True, capture_output=True, timeout=180)
    return "ok"


def run_inkscape(svg, target, out, size):
    exe = shutil.which("inkscape")
    if not exe:
        return "unavailable"
    if target == "pdf":
        cmd = [exe, svg, "--export-type=pdf", f"--export-filename={out}"]
    else:
        cmd = [exe, svg, "--export-type=png", "--export-dpi=192",
               f"--export-filename={out}"]
    subprocess.run(cmd, check=True, capture_output=True, timeout=240)
    return "ok"


def run_chrome(svg, target, out, size):
    exe = find_chrome()
    if not exe:
        return "unavailable"
    w_px, h_px = size
    base = [exe, "--headless=new", "--disable-gpu", "--hide-scrollbars",
            "--no-first-run", "--no-default-browser-check",
            "--default-background-color=FFFFFFFF"]
    if target == "png":
        cmd = base + [f"--screenshot={os.path.abspath(out)}",
                      f"--window-size={w_px},{h_px}",
                      "--force-device-scale-factor=2",
                      file_url(svg)]
        subprocess.run(cmd, check=True, capture_output=True, timeout=180)
        return "ok"
    # pdf：HTML 包装器，按 SVG 像素尺寸换算毫米设置 @page
    w_mm, h_mm = w_px * MM_PER_PX, h_px * MM_PER_PX
    html_path = None
    try:
        with tempfile.NamedTemporaryFile("w", suffix=".html", delete=False,
                                         encoding="utf-8") as fh:
            html_path = fh.name
            fh.write("<!DOCTYPE html><html><head><meta charset='utf-8'><style>"
                     f"@page {{ size: {w_mm:.2f}mm {h_mm:.2f}mm; margin: 0; }}"
                     "html,body { margin:0; padding:0; }"
                     f"img {{ width:{w_mm:.2f}mm; height:{h_mm:.2f}mm; display:block; }}"
                     "</style></head><body>"
                     f'<img src="{file_url(svg)}"></body></html>')
        cmd = base + [f"--print-to-pdf={os.path.abspath(out)}", file_url(html_path)]
        subprocess.run(cmd, check=True, capture_output=True, timeout=180)
        return "ok"
    finally:
        if html_path:
            try:
                os.unlink(html_path)
            except OSError:
                pass


TOOLS = [("cairosvg", run_cairosvg), ("rsvg-convert", run_rsvg),
         ("inkscape", run_inkscape), ("chrome-headless", run_chrome)]


def export_one(svg, target, out, size, report):
    """为单个目标格式沿回退链尝试；把每次尝试追加进 report['attempts']。"""
    for name, fn in TOOLS:
        entry = {"tool": name, "target": target, "status": None, "detail": ""}
        try:
            st = fn(svg, target, out, size)
            if st == "unavailable":
                entry["status"] = "unavailable"
                entry["detail"] = "工具未安装/未找到"
            elif ok_file(out):
                entry["status"] = "ok"
                report["attempts"].append(entry)
                return {"status": "ok", "tool": name, "path": os.path.abspath(out),
                        "bytes": os.path.getsize(out)}
            else:
                entry["status"] = "failed"
                entry["detail"] = "命令成功但输出文件缺失或过小"
        except ImportError as exc:
            entry["status"] = "unavailable"
            entry["detail"] = f"import 失败: {exc}"
        except subprocess.CalledProcessError as exc:
            err = exc.stderr.decode("utf-8", "ignore")[:300] if isinstance(exc.stderr, bytes) \
                else str(exc.stderr)[:300]
            entry["status"] = "failed"
            entry["detail"] = f"退出码 {exc.returncode}: {err}"
        except Exception as exc:
            entry["status"] = "failed"
            entry["detail"] = f"{type(exc).__name__}: {exc}"[:300]
        report["attempts"].append(entry)
    return {"status": "unavailable", "tool": None, "path": None}


def main(argv=None):
    ap = argparse.ArgumentParser(description="SVG → PDF/PNG 导出回退链")
    ap.add_argument("svg")
    ap.add_argument("--pdf", default=None)
    ap.add_argument("--png", default=None)
    ap.add_argument("--report", default="export_report.json")
    args = ap.parse_args(argv)

    report = {"tool": "export_svg.py",
              "svg": os.path.abspath(args.svg),
              "attempts": [],
              "pdf": {"status": "not-requested"},
              "png": {"status": "not-requested"},
              "overall": "failed"}
    try:
        if not os.path.isfile(args.svg):
            report["error"] = f"SVG 不存在: {args.svg}"
            if args.pdf:
                report["pdf"] = {"status": "failed", "detail": report["error"]}
            if args.png:
                report["png"] = {"status": "failed", "detail": report["error"]}
        else:
            size = svg_size_px(args.svg)
            report["canvas_px"] = {"w": size[0], "h": size[1]}
            if args.pdf:
                report["pdf"] = export_one(args.svg, "pdf", args.pdf, size, report)
            if args.png:
                report["png"] = export_one(args.svg, "png", args.png, size, report)
            oks = [r["status"] for r in (report["pdf"], report["png"])
                   if r["status"] != "not-requested"]
            if oks and all(s == "ok" for s in oks):
                report["overall"] = "ok"
            elif any(s == "ok" for s in oks):
                report["overall"] = "partial: 部分格式不可用，保留 SVG 源文件"
            else:
                report["overall"] = "partial: 导出工具全部不可用，仅交付 SVG 源文件"
    except Exception as exc:  # 兜底：任何意外都不阻止写报告
        report["error"] = f"{type(exc).__name__}: {exc}"
    try:
        with open(args.report, "w", encoding="utf-8") as f:
            json.dump(report, f, ensure_ascii=False, indent=2)
    except Exception as exc:
        print(f"[export_svg] 无法写报告 {args.report}: {exc}", file=sys.stderr)
        return 2
    print(f"[export_svg] overall={report['overall']} "
          f"pdf={report['pdf'].get('status')} png={report['png'].get('status')} "
          f"-> {args.report}")
    return 0  # 永不非零退出：导出失败是环境事实，已如实记录


if __name__ == "__main__":
    sys.exit(main())
