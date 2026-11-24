#!/usr/bin/env python3
"""export_render.py — deck.pptx → deck.pdf（soffice）→ preview/slide-N.png（pdftoppm）+ qa_report.json。

工具缺失只记 degraded，不中断、不伪造：哪一步缺工具，qa_report 就如实写哪一步。
页数一致性（pptx 页数 == PDF 页数 == PNG 张数）写入 qa_report.page_parity。
"""
from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common  # noqa: E402

SOFFICE_CANDIDATES = ["/opt/homebrew/bin/soffice", "/usr/bin/soffice",
                      "/usr/local/bin/soffice",
                      "/Applications/LibreOffice.app/Contents/MacOS/soffice"]


def find_tool(name, candidates=()):
    for c in candidates:
        if Path(c).exists():
            return c
    return shutil.which(name)


def export(work, output):
    work, output = Path(work), Path(output)
    deck = output / "deck.pptx"
    qa = {"deck": str(deck), "generated_at": common.now_iso(),
          "tools": {}, "steps": [], "degraded": [], "page_parity": None}
    if not deck.exists():
        qa["degraded"].append("deck.pptx 不存在，导出跳过")
        common.write_json(output / "qa_report.json", qa)
        print("[export_render] deck.pptx 缺失，degraded")
        return qa

    import fitz  # 用于数 PDF 页数
    from pptx import Presentation
    qa["pptx_slides"] = n_pptx = len(Presentation(str(deck)).slides._sldIdLst)

    # --- pptx -> pdf ---
    soffice = find_tool("soffice", SOFFICE_CANDIDATES)
    qa["tools"]["soffice"] = soffice or "缺失"
    pdf = output / "deck.pdf"
    if soffice:
        try:
            r = subprocess.run([soffice, "--headless", "--convert-to", "pdf",
                                "--outdir", str(output), str(deck)],
                               capture_output=True, text=True, timeout=300)
            ok = pdf.exists()
            qa["steps"].append({"step": "pptx->pdf", "ok": ok,
                                "stdout_tail": (r.stdout or "")[-300:],
                                "stderr_tail": (r.stderr or "")[-300:]})
            if not ok:
                qa["degraded"].append(f"soffice 转换未产出 deck.pdf (rc={r.returncode})")
        except Exception as e:  # noqa: BLE001
            qa["degraded"].append(f"soffice 调用异常: {e}")
    else:
        qa["degraded"].append("soffice 缺失：无法导出 deck.pdf")

    # --- pdf -> png ---
    preview = output / "preview"
    pdftoppm = find_tool("pdftoppm")
    qa["tools"]["pdftoppm"] = pdftoppm or "缺失"
    if pdf.exists():
        doc = fitz.open(str(pdf))
        qa["pdf_pages"] = doc.page_count
        doc.close()
        if pdftoppm:
            preview.mkdir(parents=True, exist_ok=True)
            try:
                r = subprocess.run([pdftoppm, "-png", "-r", "110", str(pdf),
                                    str(preview / "slide")],
                                   capture_output=True, text=True, timeout=300)
                pngs = sorted(preview.glob("slide-*.png"))
                qa["steps"].append({"step": "pdf->png", "ok": bool(pngs),
                                    "stderr_tail": (r.stderr or "")[-300:]})
                qa["png_count"] = len(pngs)
                if not pngs:
                    qa["degraded"].append("pdftoppm 未产出 PNG")
            except Exception as e:  # noqa: BLE001
                qa["degraded"].append(f"pdftoppm 调用异常: {e}")
        else:
            qa["degraded"].append("pdftoppm 缺失：无法生成 preview PNG")
    else:
        qa["pdf_pages"] = 0

    n_pdf = qa.get("pdf_pages", 0)
    n_png = qa.get("png_count", 0)
    qa["page_parity"] = {
        "pptx_slides": n_pptx, "pdf_pages": n_pdf, "png_count": n_png,
        "parity": bool(n_pdf == n_pptx and (n_png in (0, n_pptx))),
        "note": "pdf_pages==pptx_slides 且（无 PNG 或 PNG 张数相同）记为一致；"
                "png_count=0 仅在 pdftoppm 缺失时出现并已记 degraded",
    }
    qa["status"] = "degraded" if qa["degraded"] else "ok"
    common.write_json(output / "qa_report.json", qa)
    print(f"[export_render] status={qa['status']} parity={qa['page_parity']['parity']} "
          f"(pptx={n_pptx}, pdf={n_pdf}, png={n_png}) degraded={qa['degraded']}")
    return qa


def main(argv=None):
    ap = argparse.ArgumentParser(description="导出 PDF/PNG 预览并做页数一致性 QA")
    ap.add_argument("--work", required=True)
    ap.add_argument("--output", required=True)
    args = ap.parse_args(argv)
    qa = export(args.work, args.output)
    return 0 if qa.get("pdf_pages") else 1


if __name__ == "__main__":
    sys.exit(main())
