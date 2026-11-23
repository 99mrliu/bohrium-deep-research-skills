#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""export_svg.py — SVG → PDF/PNG 导出，工具回退链（纯标准库）。

用法:
    python3 export_svg.py figure.svg [--pdf out.pdf] [--png out.png]
                                     [--report export_report.json]

回退顺序（每种格式独立尝试，任一成功即止）:
    1. cairosvg   （Python 包，延迟 import）
    2. rsvg-convert（PATH）
    3. inkscape   （PATH）
    4. Chrome/Chromium headless：
         PDF: --headless --print-to-pdf（HTML 包装器按毫米尺寸设置 @page）
         PNG: --headless --screenshot --window-size=WxH --force-device-scale-factor=2
       macOS 路径 /Applications/Google Chrome.app/Contents/MacOS/Google Chrome
       以及 google-chrome / chromium / chromium-browser。

任何失败都不抛出异常；无论结果如何总是写出 export_report.json 如实记录。
退出码：所有请求格式均成功 → 0；部分/全部失败 → 0（报告记录状态，SVG 源文件仍是
有效交付物）；仅当输入 SVG 不存在时返回 1。
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
CHROME_PATHS = [
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    "/Applications/Chromium.app/Contents/MacOS/Chromium",
]
CHROME_NAMES = ["google-chrome", "google-chrome-stable", "chromium",
                "chromium-browser", "chrome"]


def svg_mm_size(svg_path):
    """从 <svg> 根标签解析毫米尺寸；失败回退 180x100。"""
    try:
        with open(svg_path, "r", encoding="utf-8") as f:
            head = f.read(3000)
        w = re.search(r'width="([0-9.]+)mm"', head)
        h = re.search(r'height="([0-9.]+)mm"', head)
        if w and h:
            return float(w.group(1)), float(h.group(1))
        vb = re.search(r'viewBox="[0-9.\- ]+? ([0-9.]+) ([0-9.]+)"', head)
        if vb:
            return float(vb.group(1)) / MM_TO_PX, float(vb.group(2)) / MM_TO_PX
    except Exception:
        pass
    return 180.0, 100.0


def file_url(path):
    return "file://" + os.path.abspath(path)


def run(cmd, timeout=180):
    proc = subprocess.run(cmd, capture_output=True, timeout=timeout)
    if proc.returncode != 0:
        err = (proc.stderr or b"").decode("utf-8", "ignore")[:400]
        raise RuntimeError("退出码 %d: %s" % (proc.returncode, err))


# ---------------------------------------------------------------- 各工具 ----
def export_cairosvg(svg, target, out, w_mm, h_mm):
    import cairosvg  # 故意延迟 import，缺失即抛 ImportError 进入下一回退
    if target == "pdf":
        cairosvg.svg2pdf(url=svg, write_to=out)
    else:
        cairosvg.svg2png(url=svg, write_to=out, scale=2.0)


def export_rsvg(svg, target, out, w_mm, h_mm):
    exe = shutil.which("rsvg-convert")
    if not exe:
        raise RuntimeError("rsvg-convert 不在 PATH")
    if target == "pdf":
        run([exe, "-f", "pdf", "-o", out, svg])
    else:
        run([exe, "-z", "2.0", "-o", out, svg])


def export_inkscape(svg, target, out, w_mm, h_mm):
    exe = shutil.which("inkscape")
    if not exe:
        raise RuntimeError("inkscape 不在 PATH")
    if target == "pdf":
        run([exe, svg, "--export-type=pdf", "--export-filename=%s" % out])
    else:
        run([exe, svg, "--export-type=png", "--export-dpi=192",
             "--export-filename=%s" % out])


def find_chrome():
    for p in CHROME_PATHS:
        if os.path.exists(p):
            return p
    for name in CHROME_NAMES:
        p = shutil.which(name)
        if p:
            return p
    return None


def export_chrome(svg, target, out, w_mm, h_mm):
    exe = find_chrome()
    if not exe:
        raise RuntimeError("未找到 Chrome/Chromium（含 macOS .app 路径）")
    w_px = max(1, int(round(w_mm * MM_TO_PX)))
    h_px = max(1, int(round(h_mm * MM_TO_PX)))
    common = [exe, "--headless=new", "--disable-gpu", "--hide-scrollbars",
              "--no-first-run", "--no-default-browser-check",
              "--default-background-color=FFFFFFFF"]
    if target == "png":
        run(common + ["--screenshot=%s" % os.path.abspath(out),
                      "--window-size=%d,%d" % (w_px, h_px),
                      "--force-device-scale-factor=2",
                      file_url(svg)], timeout=120)
    else:
        # HTML 包装器：@page 设为 SVG 毫米尺寸、零边距，保证 PDF 页面正确
        fd, html_path = tempfile.mkstemp(suffix=".html")
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write("<!DOCTYPE html><html><head><meta charset='utf-8'><style>"
                    "@page { size: %smm %smm; margin: 0; }"
                    "html,body { margin:0; padding:0; }"
                    "img { width:%smm; height:%smm; display:block; }"
                    "</style></head><body><img src=\"%s\"></body></html>"
                    % (w_mm, h_mm, w_mm, h_mm, file_url(svg)))
        try:
            run(common + ["--print-to-pdf=%s" % os.path.abspath(out),
                          "--no-pdf-header-footer",
                          file_url(html_path)], timeout=120)
        finally:
            try:
                os.unlink(html_path)
            except OSError:
                pass
    if not os.path.exists(out):
        raise RuntimeError("chrome 未生成输出文件: %s" % out)


TOOLS = [("cairosvg", export_cairosvg),
         ("rsvg-convert", export_rsvg),
         ("inkscape", export_inkscape),
         ("chrome-headless", export_chrome)]


def main(argv):
    ap = argparse.ArgumentParser(description="SVG → PDF/PNG 导出（回退链）")
    ap.add_argument("svg")
    ap.add_argument("--pdf", default=None)
    ap.add_argument("--png", default=None)
    ap.add_argument("--report", default="export_report.json")
    args = ap.parse_args(argv[1:])

    report = {"svg": os.path.abspath(args.svg), "attempts": [],
              "pdf": {"status": "not-requested", "tool": None, "path": None},
              "png": {"status": "not-requested", "tool": None, "path": None},
              "overall": "ok"}
    if not os.path.exists(args.svg):
        report["overall"] = "failed: SVG 不存在"
        with open(args.report, "w", encoding="utf-8") as f:
            json.dump(report, f, ensure_ascii=False, indent=2, sort_keys=True)
        print("[export_svg] SVG 不存在: %s" % args.svg, file=sys.stderr)
        return 1

    w_mm, h_mm = svg_mm_size(args.svg)
    report["canvas_mm"] = {"w": w_mm, "h": h_mm}

    targets = []
    if args.pdf:
        targets.append(("pdf", args.pdf))
    if args.png:
        targets.append(("png", args.png))
    if not targets:
        targets = [("pdf", os.path.splitext(args.svg)[0] + ".pdf"),
                   ("png", os.path.splitext(args.svg)[0] + ".png")]

    for target, out in targets:
        done = False
        for name, fn in TOOLS:
            try:
                fn(args.svg, target, out, w_mm, h_mm)
                if os.path.exists(out):
                    report["attempts"].append(
                        {"tool": name, "target": target, "status": "ok"})
                    report[target] = {"status": "ok", "tool": name,
                                      "path": os.path.abspath(out)}
                    done = True
                    break
                report["attempts"].append(
                    {"tool": name, "target": target, "status": "failed",
                     "detail": "命令返回 0 但未生成文件"})
            except ImportError as exc:
                report["attempts"].append(
                    {"tool": name, "target": target, "status": "skipped",
                     "detail": "不可用: %s" % exc})
            except Exception as exc:
                report["attempts"].append(
                    {"tool": name, "target": target, "status": "failed",
                     "detail": "%s: %s" % (type(exc).__name__, exc)})
        if not done:
            report[target] = {"status": "unavailable", "tool": None, "path": None}

    bad = [t for t, _ in targets if report[t]["status"] != "ok"]
    if bad:
        report["overall"] = ("partial: %s 导出不可用，已如实记录；"
                             "SVG 源文件不受影响" % "/".join(bad))
    with open(args.report, "w", encoding="utf-8", newline="\n") as f:
        json.dump(report, f, ensure_ascii=False, indent=2, sort_keys=True)
    print("[export_svg] pdf=%s png=%s -> %s"
          % (report["pdf"]["status"], report["png"]["status"], args.report))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
