#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""render.py -- 把可编辑产物真实渲染成 PDF + PNG 预览（下游证据链第一步）。

渲染器探测顺序：环境变量 SOFFICE -> PATH 里的 soffice/libreoffice -> 常见安装位。
找不到渲染器不伪造产物：写 render_status.json(status=unavailable) 并以退出码 3
结束，由调用方在 result.json 的 limits 里诚实声明。
pdftoppm 缺失时只交 PDF（status=pdf_only）。

用法:
  python3 render.py 交付件.docx --outdir /app/output/preview [--dpi 110]
退出码: 0 完整渲染; 1 渲染失败; 3 渲染器缺失; 2 输入不存在
"""
import argparse, json, os, shutil, subprocess, sys, time

def find_renderer():
    env = os.environ.get("SOFFICE")
    cands = [env] if env else []
    cands += ["soffice", "libreoffice",
              "/usr/bin/soffice", "/usr/local/bin/soffice",
              "/opt/libreoffice/program/soffice",
              "/Applications/LibreOffice.app/Contents/MacOS/soffice"]
    for c in cands:
        if c and shutil.which(c):
            return shutil.which(c)
        if c and os.path.isfile(c) and os.access(c, os.X_OK):
            return c
    return None

def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("docx")
    ap.add_argument("--outdir", required=True)
    ap.add_argument("--dpi", type=int, default=110)
    a = ap.parse_args()

    os.makedirs(a.outdir, exist_ok=True)
    status = {"input": a.docx, "outdir": a.outdir, "time": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
              "renderer": None, "pdf": None, "pngs": [], "status": "failed", "commands": []}
    if not os.path.isfile(a.docx):
        status["error"] = "input not found"
        json.dump(status, open(os.path.join(a.outdir, "render_status.json"), "w"), indent=2)
        sys.exit(2)

    soffice = find_renderer()
    if not soffice:
        status.update(status="unavailable",
                      error="no soffice/libreoffice found; declare in result.json limits")
        json.dump(status, open(os.path.join(a.outdir, "render_status.json"), "w"), indent=2)
        print("RENDERER UNAVAILABLE -> render_status.json (declare in limits)")
        sys.exit(3)
    status["renderer"] = soffice

    cmd = [soffice, "--headless", "--norestore", "--convert-to", "pdf",
           "--outdir", a.outdir, a.docx]
    status["commands"].append(cmd)
    p = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
    status["convert_returncode"] = p.returncode
    base = os.path.splitext(os.path.basename(a.docx))[0]
    pdf = os.path.join(a.outdir, base + ".pdf")
    if p.returncode != 0 or not os.path.isfile(pdf):
        status["error"] = (p.stderr or p.stdout or "conversion failed")[:500]
        json.dump(status, open(os.path.join(a.outdir, "render_status.json"), "w"), indent=2)
        sys.exit(1)
    status["pdf"] = pdf

    pdftoppm = shutil.which("pdftoppm") or os.environ.get("PDFTOPPM")
    if pdftoppm:
        prefix = os.path.join(a.outdir, "page")
        cmd2 = [pdftoppm, "-png", "-r", str(a.dpi), pdf, prefix]
        status["commands"].append(cmd2)
        p2 = subprocess.run(cmd2, capture_output=True, text=True, timeout=300)
        status["pdftoppm_returncode"] = p2.returncode
        status["pngs"] = sorted(f for f in os.listdir(a.outdir)
                                if f.startswith("page") and f.endswith(".png"))
        status["status"] = "rendered"
    else:
        status["status"] = "pdf_only"
        status["note"] = "pdftoppm not found; PDF only, no PNG previews"
    json.dump(status, open(os.path.join(a.outdir, "render_status.json"), "w"), indent=2)
    print("render status=%s pdf=%s pngs=%d" % (status["status"], status["pdf"], len(status["pngs"])))
    sys.exit(0)

if __name__ == "__main__":
    main()
