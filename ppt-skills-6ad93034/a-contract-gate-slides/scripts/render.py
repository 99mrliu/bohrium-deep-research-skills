#!/usr/bin/env python3
"""render.py — Step 7 of contract-gate-slides.

Export output/presentation.pptx to PDF (LibreOffice headless) and rasterize
per-page PNG previews. Degrades gracefully: if no converter exists, records
the failure in work/render_status.json and exits 0 (the deck is still the
primary deliverable; result.py will report status accordingly).
"""
import json, os, shutil, subprocess, sys

WORK = os.environ.get("CASE_WORK_DIR", "/app/work")
OUT = os.environ.get("CASE_OUTPUT_DIR", "/app/output")


def main():
    pptx = os.path.join(OUT, "presentation.pptx")
    status = {"pdf": None, "previews": 0, "converter": None, "errors": []}
    if not os.path.exists(pptx):
        status["errors"].append("presentation.pptx 不存在")
        json.dump(status, open(os.path.join(WORK, "render_status.json"), "w"), indent=1)
        print(json.dumps(status))
        return
    soffice = shutil.which("soffice") or shutil.which("libreoffice")
    if soffice:
        try:
            r = subprocess.run([soffice, "--headless", "--convert-to", "pdf",
                                "--outdir", OUT, pptx],
                               capture_output=True, timeout=300, text=True)
            pdf = os.path.join(OUT, "presentation.pdf")
            if os.path.exists(pdf):
                status["pdf"] = "presentation.pdf"
                status["converter"] = os.path.basename(soffice)
            else:
                status["errors"].append("soffice 未产出 PDF: " + (r.stderr or r.stdout)[:300])
        except Exception as e:
            status["errors"].append(f"soffice 异常: {e}")
    else:
        status["errors"].append("环境无 soffice/libreoffice，跳过 PDF 导出")

    if status["pdf"]:
        pdf = os.path.join(OUT, "presentation.pdf")
        prev = os.path.join(OUT, "previews")
        os.makedirs(prev, exist_ok=True)
        if shutil.which("pdftoppm"):
            try:
                subprocess.run(["pdftoppm", "-png", "-r", "110", pdf,
                                os.path.join(prev, "slide")],
                               capture_output=True, timeout=300)
                status["previews"] = len([f for f in os.listdir(prev) if f.endswith(".png")])
            except Exception as e:
                status["errors"].append(f"pdftoppm 异常: {e}")
        else:
            try:
                import fitz
                d = fitz.open(pdf)
                for i in range(len(d)):
                    d[i].get_pixmap(dpi=110).save(os.path.join(prev, f"slide-{i+1:02d}.png"))
                status["previews"] = len(d)
            except Exception as e:
                status["errors"].append(f"预览渲染失败: {e}")
    json.dump(status, open(os.path.join(WORK, "render_status.json"), "w"), indent=1)
    print(json.dumps(status, ensure_ascii=False))


if __name__ == "__main__":
    main()
