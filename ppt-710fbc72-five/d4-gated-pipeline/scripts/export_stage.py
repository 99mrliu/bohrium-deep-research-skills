#!/usr/bin/env python3
"""export_stage.py — S7 导出与渲染。

pptx --(soffice)--> deck.pdf --(pdftoppm，缺失时退回 pymupdf 栅格)--> preview/slide-*.png
任何工具缺失只记 degraded，不伪造、不中断；页数一致性写入 export_report.json 供 S8 裁决。
"""
from __future__ import annotations

import glob
import os
import shutil
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from stage_machine import StageFailure, now_iso, read_json, write_json


def run(ctx) -> list:
    pptx_path = os.path.join(ctx.output, "deck.pptx")
    if not os.path.isfile(pptx_path):
        raise StageFailure("deck.pptx 不存在（S6 未完成）", hint=ctx.default_resume_cmd())
    tools_state = read_json(os.path.join(ctx.work, "tools.json"), default={}) or {}
    tools = tools_state.get("tools", {})
    export_dir = os.path.join(ctx.work, "export")
    preview_dir = os.path.join(ctx.output, "preview")
    os.makedirs(export_dir, exist_ok=True)
    os.makedirs(preview_dir, exist_ok=True)
    for old in glob.glob(os.path.join(preview_dir, "*.png")):
        os.remove(old)

    degraded = list(tools_state.get("degraded_tools", []))
    outputs = []
    pdf_path = None
    renderer = None

    # pptx 页数（python-pptx 权威值）
    try:
        from pptx import Presentation
        pptx_slides = len(Presentation(pptx_path).slides._sldIdLst)
    except Exception as e:
        raise StageFailure(f"无法回读 deck.pptx: {e}", hint=ctx.default_resume_cmd())

    # 1) soffice 转 PDF
    soffice = (tools.get("soffice") or {}).get("path")
    if soffice and os.path.isfile(soffice):
        profile = os.path.join(ctx.work, "lo_profile")
        cmd = [soffice, "--headless", "--norestore",
               f"-env:UserInstallation=file://{profile}",
               "--convert-to", "pdf", "--outdir", export_dir, pptx_path]
        try:
            r = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
            produced = os.path.join(export_dir, "deck.pdf")
            if r.returncode == 0 and os.path.isfile(produced):
                pdf_path = os.path.join(ctx.output, "deck.pdf")
                shutil.copyfile(produced, pdf_path)
                outputs.append(pdf_path)
            else:
                degraded.append(f"soffice 转换失败 rc={r.returncode}: {(r.stderr or r.stdout)[-200:]}")
        except subprocess.TimeoutExpired:
            degraded.append("soffice 转换超时(300s)")
    else:
        degraded.append("soffice 不可用：跳过 PDF 导出")

    # 2) PDF 页数
    pdf_pages = None
    if pdf_path:
        try:
            import pymupdf
        except ImportError:
            import fitz as pymupdf
        doc = pymupdf.open(pdf_path)
        pdf_pages = doc.page_count
        doc.close()

    # 3) PNG 预览
    preview_count = 0
    if pdf_path:
        pdftoppm = (tools.get("pdftoppm") or {}).get("path")
        if pdftoppm:
            prefix = os.path.join(preview_dir, "slide")
            try:
                r = subprocess.run([pdftoppm, "-png", "-r", "110", pdf_path, prefix],
                                   capture_output=True, text=True, timeout=300)
                if r.returncode != 0:
                    degraded.append(f"pdftoppm 失败 rc={r.returncode}: {(r.stderr or '')[-200:]}")
            except subprocess.TimeoutExpired:
                degraded.append("pdftoppm 超时(300s)")
            renderer = "soffice+pdftoppm"
        else:
            renderer = "soffice+pymupdf-fallback"
            try:
                import pymupdf
            except ImportError:
                import fitz as pymupdf
            doc = pymupdf.open(pdf_path)
            for i in range(doc.page_count):
                pix = doc.load_page(i).get_pixmap(dpi=110)
                pix.save(os.path.join(preview_dir, f"slide-{i + 1}.png"))
            doc.close()
            degraded.append("pdftoppm 缺失：预览使用 pymupdf 栅格化回退")
        previews = sorted(glob.glob(os.path.join(preview_dir, "slide-*.png")))
        preview_count = len(previews)
        outputs.extend(previews)

    parity = None
    if pdf_pages is not None:
        parity = (pdf_pages == pptx_slides)

    report = {
        "pptx": pptx_path,
        "pptx_slides": pptx_slides,
        "pdf": pdf_path,
        "pdf_pages": pdf_pages,
        "parity": parity,
        "preview_dir": preview_dir,
        "preview_count": preview_count,
        "renderer": renderer,
        "degraded": degraded,
        "exported_at": now_iso(),
    }
    rp = os.path.join(ctx.work, "export_report.json")
    write_json(rp, report)
    outputs.append(rp)
    print(f"[S7] 导出完成：pdf_pages={pdf_pages} pptx_slides={pptx_slides} "
          f"parity={parity} previews={preview_count} renderer={renderer}", flush=True)
    return outputs
