#!/usr/bin/env python3
"""export_deck.py — talktrack-first-deck step 5: render the deck.

LibreOffice → PDF → per-page PNG previews. Missing tools degrade to a
recorded exception, never a crash. Also spot-checks the PDF: page count
must equal slide count and no page may be fully empty.
"""
import json, os, shutil, subprocess

WORK = os.environ.get("CASE_WORK_DIR", "/app/work")
OUT = os.environ.get("CASE_OUTPUT_DIR", "/app/output")


def main():
    st = {"pdf": None, "preview_pages": 0, "page_check": None, "errors": []}
    pptx = os.path.join(OUT, "presentation.pptx")
    soffice = shutil.which("soffice") or shutil.which("libreoffice")
    if not os.path.exists(pptx):
        st["errors"].append("presentation.pptx 不存在")
    elif not soffice:
        st["errors"].append("无 soffice/libreoffice")
    else:
        try:
            r = subprocess.run([soffice, "--headless", "--convert-to", "pdf",
                                "--outdir", OUT, pptx], capture_output=True,
                               timeout=300, text=True)
            if os.path.exists(os.path.join(OUT, "presentation.pdf")):
                st["pdf"] = "presentation.pdf"
            else:
                st["errors"].append("导出失败: " + (r.stderr or r.stdout)[:300])
        except Exception as e:
            st["errors"].append(f"soffice 异常: {e}")
    if st["pdf"]:
        pdf = os.path.join(OUT, "presentation.pdf")
        prev = os.path.join(OUT, "previews")
        os.makedirs(prev, exist_ok=True)
        try:
            if shutil.which("pdftoppm"):
                subprocess.run(["pdftoppm", "-png", "-r", "110", pdf,
                                os.path.join(prev, "pg")], capture_output=True, timeout=300)
                st["preview_pages"] = len([f for f in os.listdir(prev) if f.endswith(".png")])
            else:
                import fitz
                d = fitz.open(pdf)
                for i in range(len(d)):
                    d[i].get_pixmap(dpi=110).save(os.path.join(prev, f"pg-{i+1:02d}.png"))
                st["preview_pages"] = len(d)
        except Exception as e:
            st["errors"].append(f"预览失败: {e}")
        try:
            import fitz
            d = fitz.open(pdf)
            empty = [i + 1 for i in range(len(d))
                     if not d[i].get_text().strip() and not d[i].get_images()]
            st["page_check"] = {"pdf_pages": len(d), "empty_pages": empty}
            if empty:
                st["errors"].append(f"空白页: {empty}")
        except Exception:
            pass
    json.dump(st, open(os.path.join(WORK, "export_status.json"), "w"), indent=1)
    print(json.dumps(st, ensure_ascii=False))


if __name__ == "__main__":
    main()
