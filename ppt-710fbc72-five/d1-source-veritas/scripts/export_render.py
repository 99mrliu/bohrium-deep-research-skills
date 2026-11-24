"""export_render.py — export deck.pdf + preview PNGs and QA the render.

Uses soffice (LibreOffice) at /opt/homebrew/bin/soffice or PATH, then
pdftoppm for per-page PNGs. If a tool is absent the stage is marked
degraded honestly — nothing is faked.

Usage:
  python3 export_render.py --deck /app/output/deck.pptx \
      --outdir /app/output --qa /app/output/qa_report.json
"""
from __future__ import annotations

import argparse
import glob
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common  # noqa: E402


def _pptx_slide_count(deck_path: str) -> int:
    from pptx import Presentation
    return len(Presentation(deck_path).slides._sldIdLst)


def _pdf_page_count(pdf_path: str) -> int:
    import pymupdf
    with pymupdf.open(pdf_path) as doc:
        return doc.page_count


def export(deck_path: str, outdir: str) -> dict:
    os.makedirs(outdir, exist_ok=True)
    preview_dir = os.path.join(outdir, "preview")
    os.makedirs(preview_dir, exist_ok=True)
    qa = {"deck": os.path.abspath(deck_path),
          "deck_sha256": common.sha256_file(deck_path),
          "degraded": [], "pdf": None, "previews": [],
          "slide_count_pptx": None, "page_count_pdf": None,
          "counts_match": None, "per_page_ok": None}

    qa["slide_count_pptx"] = _pptx_slide_count(deck_path)

    soffice = common.find_tool(["soffice", "libreoffice"])
    if not soffice:
        qa["degraded"].append(
            "soffice (LibreOffice) not found: PDF/PNG export skipped; "
            "deck.pptx is still valid and editable")
        qa["per_page_ok"] = False
        return qa

    pdf_path = os.path.join(outdir, "deck.pdf")
    try:
        subprocess.run(
            [soffice, "--headless", "--convert-to", "pdf",
             "--outdir", outdir, deck_path],
            check=True, capture_output=True, timeout=300, text=True)
    except Exception as exc:  # noqa: BLE001
        qa["degraded"].append(f"soffice conversion failed: {exc}")
        qa["per_page_ok"] = False
        return qa

    produced = os.path.join(outdir, os.path.splitext(os.path.basename(deck_path))[0] + ".pdf")
    if produced != pdf_path and os.path.exists(produced):
        os.replace(produced, pdf_path)
    if not os.path.exists(pdf_path):
        qa["degraded"].append("soffice ran but deck.pdf was not produced")
        qa["per_page_ok"] = False
        return qa
    qa["pdf"] = os.path.abspath(pdf_path)
    qa["pdf_sha256"] = common.sha256_file(pdf_path)
    qa["page_count_pdf"] = _pdf_page_count(pdf_path)
    qa["counts_match"] = qa["page_count_pdf"] == qa["slide_count_pptx"]

    pdftoppm = common.find_tool(["pdftoppm"])
    if not pdftoppm:
        qa["degraded"].append("pdftoppm not found: PNG previews skipped")
    else:
        prefix = os.path.join(preview_dir, "slide")
        try:
            subprocess.run([pdftoppm, "-png", "-r", "110", pdf_path, prefix],
                           check=True, capture_output=True, timeout=300, text=True)
        except Exception as exc:  # noqa: BLE001
            qa["degraded"].append(f"pdftoppm failed: {exc}")
        pages = sorted(glob.glob(prefix + "-*.png"),
                       key=lambda p: int(p.rsplit("-", 1)[1].split(".")[0]))
        for p in pages:
            qa["previews"].append({"file": os.path.abspath(p),
                                   "bytes": os.path.getsize(p),
                                   "sha256": common.sha256_file(p)})

    # per-page render verdict
    if qa["page_count_pdf"]:
        if pdftoppm and qa["previews"]:
            ok = (len(qa["previews"]) == qa["page_count_pdf"]
                  and all(p["bytes"] > 2000 for p in qa["previews"]))
            qa["per_page_ok"] = ok
            if not ok:
                qa["degraded"].append(
                    "preview count/size mismatch vs pdf pages")
        else:
            qa["per_page_ok"] = qa["counts_match"] is True
    return qa


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--deck", required=True)
    ap.add_argument("--outdir", required=True)
    ap.add_argument("--qa", required=True)
    args = ap.parse_args()
    qa = export(args.deck, args.outdir)
    common.dump_json(qa, args.qa)
    print(f"[export_render] pdf={'yes' if qa['pdf'] else 'NO'} "
          f"previews={len(qa['previews'])} "
          f"counts_match={qa['counts_match']} degraded={len(qa['degraded'])}")
    print(f"[export_render] qa -> {args.qa}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
