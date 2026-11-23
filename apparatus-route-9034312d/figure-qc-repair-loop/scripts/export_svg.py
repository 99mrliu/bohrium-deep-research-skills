#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""export_svg.py — SVG → PDF/PNG 导出，带回退链（纯标准库 + 外部工具探测）。

回退顺序（每种格式独立尝试，前一工具失败自动换下一个）:
  1. cairosvg（Python 可选依赖）
  2. rsvg-convert（PATH）
  3. inkscape（PATH）
  4. Chrome/Chromium headless：
     macOS /Applications/Google Chrome.app/Contents/MacOS/Google Chrome，
     以及 google-chrome / chromium / chromium-browser；
     PDF 走 --print-to-pdf（HTML 包装器，@page 按 SVG 毫米尺寸），
     PNG 走 --screenshot --window-size --force-device-scale-factor=2。

设计原则：永不抛异常；无论成败都写出 export_report.json 如实记录每次尝试。
产物是否有效（存在/非零/文件头）由 qc_figure.py 的 EXPORT_FAIL 判定。

用法:
  python3 export_svg.py figure.svg [--pdf out.pdf] [--png out.png]
      [--report export_report.json]
"""
import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile

MM_TO_PX = 96.0 / 25.4
CHROME_CANDIDATES = [
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    "google-chrome", "google-chrome-stable", "chromium", "chromium-browser",
]


def svg_mm_size(svg_path):
    try:
        with open(svg_path, "r", encoding="utf-8") as f:
            head = f.read(4000)
        w = re.search(r'width="([0-9.]+)\s*mm"', head)
        h = re.search(r'height="([0-9.]+)\s*mm"', head)
        if w and h:
            return float(w.group(1)), float(h.group(1))
        vb = re.search(r'viewBox="[^"]*?([0-9.]+)\s+([0-9.]+)\s*"', head)
        if vb:
            return float(vb.group(1)), float(vb.group(2))
    except Exception:
        pass
    return 180.0, 100.0


def find_chrome():
    for c in CHROME_CANDIDATES:
        if os.path.isabs(c):
            if os.path.exists(c):
                return c
        else:
            p = shutil.which(c)
            if p:
                return p
    return None


def file_url(path):
    return "file://" + os.path.abspath(path)


# ---- 各工具实现：成功返回 True，不可用/失败抛 RuntimeError ----

def via_cairosvg(svg, fmt, out, w_mm, h_mm):
    import cairosvg  # 延迟导入：缺失即 ImportError → 进入下一回退
    if fmt == "pdf":
        cairosvg.svg2pdf(url=svg, write_to=out)
    else:
        cairosvg.svg2png(url=svg, write_to=out, scale=2.0)
    return os.path.exists(out)


def via_rsvg(svg, fmt, out, w_mm, h_mm):
    exe = shutil.which("rsvg-convert")
    if not exe:
        raise RuntimeError("rsvg-convert 不在 PATH")
    if fmt == "pdf":
        cmd = [exe, "-f", "pdf", "-o", out, svg]
    else:
        cmd = [exe, "-z", "2.0", "-f", "png", "-o", out, svg]
    subprocess.run(cmd, check=True, capture_output=True, timeout=180)
    return os.path.exists(out)


def via_inkscape(svg, fmt, out, w_mm, h_mm):
    exe = shutil.which("inkscape")
    if not exe:
        raise RuntimeError("inkscape 不在 PATH")
    if fmt == "pdf":
        cmd = [exe, svg, "--export-type=pdf", f"--export-filename={out}"]
    else:
        cmd = [exe, svg, "--export-type=png", "--export-dpi=300",
               f"--export-filename={out}"]
    subprocess.run(cmd, check=True, capture_output=True, timeout=240)
    return os.path.exists(out)


def via_chrome(svg, fmt, out, w_mm, h_mm):
    exe = find_chrome()
    if not exe:
        raise RuntimeError("未找到 Chrome/Chromium（含 macOS Chrome.app 路径）")
    w_px = max(1, int(round(w_mm * MM_TO_PX)))
    h_px = max(1, int(round(h_mm * MM_TO_PX)))
    if fmt == "png":
        cmd = [exe, "--headless=new", "--disable-gpu", "--hide-scrollbars",
               "--no-first-run", "--no-default-browser-check",
               "--default-background-color=FFFFFFFF",
               f"--window-size={w_px},{h_px}",
               "--force-device-scale-factor=2",
               f"--screenshot={os.path.abspath(out)}", file_url(svg)]
        subprocess.run(cmd, check=True, capture_output=True, timeout=180)
        return os.path.exists(out)
    # pdf：HTML 包装器 + @page 毫米尺寸
    html = tempfile.NamedTemporaryFile("w", suffix=".html", delete=False,
                                       encoding="utf-8")
    try:
        html.write("<!DOCTYPE html><html><head><meta charset='utf-8'><style>"
                   f"@page {{ size: {w_mm}mm {h_mm}mm; margin: 0; }}"
                   "html,body{margin:0;padding:0;}"
                   f"img{{width:{w_mm}mm;height:{h_mm}mm;display:block;}}"
                   "</style></head><body>"
                   f"<img src=\"{file_url(svg)}\"></body></html>")
        html.close()
        cmd = [exe, "--headless=new", "--disable-gpu", "--no-first-run",
               "--no-default-browser-check",
               f"--print-to-pdf={os.path.abspath(out)}", file_url(html.name)]
        subprocess.run(cmd, check=True, capture_output=True, timeout=180)
        return os.path.exists(out)
    finally:
        try:
            os.unlink(html.name)
        except OSError:
            pass


TOOLS = [("cairosvg", via_cairosvg), ("rsvg-convert", via_rsvg),
         ("inkscape", via_inkscape), ("chrome-headless", via_chrome)]


def main(argv):
    ap = argparse.ArgumentParser()
    ap.add_argument("svg")
    ap.add_argument("--pdf", default=None)
    ap.add_argument("--png", default=None)
    ap.add_argument("--report", default="export_report.json")
    args = ap.parse_args(argv[1:])

    report = {"svg": os.path.abspath(args.svg), "attempts": [],
              "pdf": {"status": "not-requested", "tool": None, "path": None},
              "png": {"status": "not-requested", "tool": None, "path": None},
              "overall": "unknown"}
    try:
        if not os.path.exists(args.svg):
            report["overall"] = "failed: SVG 不存在"
            report["attempts"].append({"tool": None, "status": "failed",
                                       "detail": f"SVG 不存在: {args.svg}"})
        else:
            w_mm, h_mm = svg_mm_size(args.svg)
            report["canvas_mm"] = {"w": w_mm, "h": h_mm}
            targets = []
            if args.pdf:
                targets.append(("pdf", args.pdf))
            if args.png:
                targets.append(("png", args.png))
            for fmt, out in targets:
                done = False
                for name, fn in TOOLS:
                    try:
                        if fn(args.svg, fmt, out, w_mm, h_mm) \
                                and os.path.getsize(out) > 0:
                            report["attempts"].append(
                                {"tool": name, "target": fmt, "status": "ok"})
                            report[fmt] = {"status": "ok", "tool": name,
                                           "path": os.path.abspath(out)}
                            done = True
                            break
                        raise RuntimeError("产物缺失或为零字节")
                    except ImportError as exc:
                        report["attempts"].append(
                            {"tool": name, "target": fmt, "status": "skipped",
                             "detail": f"不可用: {exc}"})
                    except subprocess.CalledProcessError as exc:
                        err = exc.stderr
                        err = err.decode("utf-8", "ignore")[:300] \
                            if isinstance(err, bytes) else str(err)
                        report["attempts"].append(
                            {"tool": name, "target": fmt, "status": "failed",
                             "detail": f"退出码 {exc.returncode}: {err}"})
                    except Exception as exc:
                        report["attempts"].append(
                            {"tool": name, "target": fmt, "status": "failed",
                             "detail": f"{type(exc).__name__}: {exc}"})
                if not done:
                    report[fmt] = {"status": "unavailable", "tool": None,
                                   "path": None}
            asked = [f for f, _ in targets]
            bad = [f for f in asked if report[f]["status"] != "ok"]
            report["overall"] = ("ok" if not bad else
                                 "partial: 不可用格式: " + ",".join(bad)
                                 + "（仅保留 SVG 源文件并如实声明）")
    except Exception as exc:
        report["overall"] = f"failed: {type(exc).__name__}: {exc}"
    try:
        with open(args.report, "w", encoding="utf-8") as f:
            json.dump(report, f, ensure_ascii=False, indent=2)
    except OSError as exc:
        print(f"[export_svg] 报告写入失败: {exc}", file=sys.stderr)
        return 1
    print(f"[export_svg] pdf={report['pdf']['status']} "
          f"png={report['png']['status']} overall={report['overall']}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
