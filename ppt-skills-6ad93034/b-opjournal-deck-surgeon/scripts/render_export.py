#!/usr/bin/env python3
"""render_export.py — opjournal-deck-surgeon step 5.

Export presentation.pptx to PDF and per-page PNG previews. Never blocks:
missing converter is recorded in work/export_status.json and the run
continues (the editable deck remains the primary deliverable).
"""
import json, os, shutil, subprocess

WORK = os.environ.get("CASE_WORK_DIR", "/app/work")
OUT = os.environ.get("CASE_OUTPUT_DIR", "/app/output")


def main():
    st = {"pdf": None, "preview_pages": 0, "converter": None, "errors": []}
    pptx = os.path.join(OUT, "presentation.pptx")
    if not os.path.exists(pptx):
        st["errors"].append("presentation.pptx 不存在")
    else:
        soffice = shutil.which("soffice") or shutil.which("libreoffice")
        if not soffice:
            st["errors"].append("无 soffice/libreoffice")
        else:
            try:
                r = subprocess.run([soffice, "--headless", "--convert-to", "pdf",
                                    "--outdir", OUT, pptx],
                                   capture_output=True, timeout=300, text=True)
                if os.path.exists(os.path.join(OUT, "presentation.pdf")):
                    st["pdf"] = "presentation.pdf"
                    st["converter"] = os.path.basename(soffice)
                else:
                    st["errors"].append("soffice 未产出 PDF: " + (r.stderr or r.stdout)[:300])
            except Exception as e:
                st["errors"].append(f"soffice 异常: {e}")
    if st["pdf"]:
        prev = os.path.join(OUT, "previews")
        os.makedirs(prev, exist_ok=True)
        pdf = os.path.join(OUT, "presentation.pdf")
        if shutil.which("pdftoppm"):
            try:
                subprocess.run(["pdftoppm", "-png", "-r", "110", pdf,
                                os.path.join(prev, "page")], capture_output=True, timeout=300)
                st["preview_pages"] = len([f for f in os.listdir(prev) if f.endswith(".png")])
            except Exception as e:
                st["errors"].append(f"pdftoppm 异常: {e}")
        else:
            try:
                import fitz
                d = fitz.open(pdf)
                for i in range(len(d)):
                    d[i].get_pixmap(dpi=110).save(os.path.join(prev, f"page-{i+1:02d}.png"))
                st["preview_pages"] = len(d)
            except Exception as e:
                st["errors"].append(f"预览渲染失败: {e}")
    json.dump(st, open(os.path.join(WORK, "export_status.json"), "w"), indent=1)
    print(json.dumps(st, ensure_ascii=False))


if __name__ == "__main__":
    main()
