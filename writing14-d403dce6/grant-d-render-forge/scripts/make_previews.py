#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""make_previews.py — 真实渲染 docx/pdf 预览；工具缺失时诚实降级，绝不伪造。

探测 soffice（docx→pdf）与 pdftoppm（pdf→png，-png -r 110）：
  - 两者可用且渲染成功：生成真实 PDF 与 PNG，status=ok，退出码 0；
  - 任一工具缺失：不写任何假产物，只写 preview_status.json 说明缺哪个工具、
    哪个产物未生成，status=degraded，退出码 0（--strict 时退出码 1）；
  - 工具存在但渲染失败 / 输入不存在：status=error，退出码 1。

环境变量（测试降级路径用）：MAKE_PREVIEWS_SOFFICE / MAKE_PREVIEWS_PDFTOPPM
置为 none 可模拟对应工具缺失，置为路径列表（os.pathsep 分隔）可指定候选。

用法：
  python3 make_previews.py 输入.docx --outdir 预览目录 [--strict]
  python3 make_previews.py 输入.pdf  --outdir 预览目录   # 只渲染 PNG

退出码：0 成功或诚实降级（非 strict）；1 错误或 strict 下降级；2 参数错误。
"""
import argparse
import glob
import json
import os
import shutil
import subprocess
import sys
import tempfile

SOFFICE_CANDIDATES = (
    "soffice",
    "libreoffice",
    "/Applications/LibreOffice.app/Contents/MacOS/soffice",
    "/usr/bin/soffice",
    "/usr/local/bin/soffice",
    "/opt/homebrew/bin/soffice",
)
PDFTOPPM_CANDIDATES = (
    "pdftoppm",
    "/usr/bin/pdftoppm",
    "/usr/local/bin/pdftoppm",
    "/opt/homebrew/bin/pdftoppm",
)
DPI = "110"
SOFFICE_TIMEOUT = 180


def tool_candidates(env_var, defaults):
    """候选路径可被环境变量覆盖；置为 none/空 可模拟工具缺失（测试降级路径用）。"""
    override = os.environ.get(env_var)
    if override is not None:
        if override.strip().lower() in ("", "none", "false"):
            return []
        return [p for p in override.split(os.pathsep) if p]
    return list(defaults)


def find_tool(candidates):
    for cand in candidates:
        if os.path.sep in cand:
            if os.path.isfile(cand) and os.access(cand, os.X_OK):
                return cand
        else:
            found = shutil.which(cand)
            if found:
                return found
    return None


def product_info(path, base):
    return {"path": os.path.relpath(path, base), "bytes": os.path.getsize(path)}


def write_status(outdir, status):
    with open(os.path.join(outdir, "preview_status.json"), "w", encoding="utf-8") as fh:
        json.dump(status, fh, ensure_ascii=False, indent=2, sort_keys=True)
        fh.write("\n")


def main(argv=None):
    ap = argparse.ArgumentParser(
        description="用 soffice/pdftoppm 真实渲染 docx/pdf 预览；缺失时诚实降级。")
    ap.add_argument("input", help="输入 .docx 或 .pdf 文件")
    ap.add_argument("--outdir", required=True, help="预览产物输出目录")
    ap.add_argument("--strict", action="store_true",
                    help="严格模式：工具缺失导致降级时退出码 1")
    args = ap.parse_args(argv)

    if not os.path.isfile(args.input):
        print("错误：输入文件不存在 %s" % args.input, file=sys.stderr)
        return 1
    os.makedirs(args.outdir, exist_ok=True)
    outdir = os.path.abspath(args.outdir)
    src = os.path.abspath(args.input)
    stem = os.path.splitext(os.path.basename(src))[0]

    soffice = find_tool(tool_candidates("MAKE_PREVIEWS_SOFFICE", SOFFICE_CANDIDATES))
    pdftoppm = find_tool(tool_candidates("MAKE_PREVIEWS_PDFTOPPM", PDFTOPPM_CANDIDATES))

    status = {
        "status": "ok",
        "input": os.path.basename(src),
        "tools": {"soffice": soffice, "pdftoppm": pdftoppm},
        "missing_tools": [],
        "products": {"pdf": None, "pngs": []},
        "missing_products": [],
        "notes": [],
    }

    def degraded(note):
        status["status"] = "degraded"
        status["notes"].append(note)
        print("降级：%s" % note)

    def fail(note):
        status["status"] = "error"
        status["notes"].append(note)
        write_status(outdir, status)
        print("错误：%s" % note, file=sys.stderr)
        return 1

    # 第一阶段：获得 PDF
    pdf_path = None
    if src.lower().endswith(".pdf"):
        pdf_path = src
        status["products"]["pdf"] = product_info(pdf_path, outdir) \
            if pdf_path.startswith(outdir) else {"path": pdf_path, "bytes": os.path.getsize(pdf_path)}
        status["notes"].append("输入即 PDF，跳过 docx→pdf 转换。")
    else:
        if soffice is None:
            status["missing_tools"].append("soffice")
            status["missing_products"].append("pdf")
            degraded("未找到 soffice（LibreOffice），无法生成 PDF 预览。")
        else:
            profile = tempfile.mkdtemp(prefix="soffice_profile_")
            try:
                proc = subprocess.run(
                    [soffice, "--headless", "--norestore",
                     "-env:UserInstallation=file://" + profile,
                     "--convert-to", "pdf", "--outdir", outdir, src],
                    capture_output=True, text=True, timeout=SOFFICE_TIMEOUT)
            except subprocess.TimeoutExpired:
                return fail("soffice 转换超时（%d 秒）。" % SOFFICE_TIMEOUT)
            finally:
                shutil.rmtree(profile, ignore_errors=True)
            candidate = os.path.join(outdir, stem + ".pdf")
            if proc.returncode != 0 or not os.path.isfile(candidate) \
                    or os.path.getsize(candidate) == 0:
                return fail("soffice 转换失败：rc=%s stderr=%s"
                            % (proc.returncode, proc.stderr.strip()[:300]))
            pdf_path = candidate
            status["products"]["pdf"] = product_info(pdf_path, outdir)
            print("PDF 已生成: %s（%d 字节）"
                  % (pdf_path, os.path.getsize(pdf_path)))

    # 第二阶段：PDF → PNG
    if pdftoppm is None:
        status["missing_tools"].append("pdftoppm")
        status["missing_products"].append("png")
        degraded("未找到 pdftoppm（poppler），无法生成 PNG 页面预览。")
    elif pdf_path is not None:
        prefix = os.path.join(outdir, stem)
        proc = subprocess.run(
            [pdftoppm, "-png", "-r", DPI, pdf_path, prefix],
            capture_output=True, text=True, timeout=120)
        pngs = sorted(glob.glob(prefix + "-*.png"))
        pngs = [p for p in pngs if os.path.getsize(p) > 0]
        if proc.returncode != 0 or not pngs:
            return fail("pdftoppm 渲染失败：rc=%s stderr=%s"
                        % (proc.returncode, proc.stderr.strip()[:300]))
        status["products"]["pngs"] = [product_info(p, outdir) for p in pngs]
        print("PNG 已生成 %d 页: %s" % (len(pngs), ", ".join(
            os.path.basename(p) for p in pngs)))
    elif "png" not in status["missing_products"]:
        status["missing_products"].append("png")
        degraded("无 PDF 可供渲染，PNG 预览未生成。")

    write_status(outdir, status)
    print("preview_status.json 已写出，status=%s" % status["status"])
    if status["status"] != "ok" and args.strict:
        print("严格模式：降级即失败。", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
