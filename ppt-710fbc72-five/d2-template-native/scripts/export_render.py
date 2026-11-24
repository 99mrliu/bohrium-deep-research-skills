#!/usr/bin/env python3
"""Render deck.pptx -> deck.pdf -> preview/slide-N.png and QA the render.

Uses soffice (LibreOffice) for PDF conversion and pdftoppm for PNGs.
Missing tools are recorded as `degraded` — never fatal, never faked.

Usage:
    python3 export_render.py --deck deck.pptx --outdir /app/output \
        --report qa_report.json
"""
import argparse
import json
import os
import shutil
import subprocess
import sys

SOFFICE_CANDIDATES = ["/opt/homebrew/bin/soffice", "/usr/bin/soffice",
                      "/usr/local/bin/soffice"]


def find_tool(name, candidates=()):
    for c in candidates:
        if os.path.exists(c):
            return c
    return shutil.which(name)


def pdf_page_count(pdf_path):
    try:
        import pymupdf
        with pymupdf.open(pdf_path) as doc:
            return doc.page_count
    except Exception:
        return None


def pptx_slide_count(pptx_path):
    try:
        from pptx import Presentation
        return len(Presentation(pptx_path).slides._sldIdLst)
    except Exception:
        return None


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--deck", required=True)
    ap.add_argument("--outdir", required=True)
    ap.add_argument("--report", required=True)
    args = ap.parse_args(argv)

    qa = {"deck": args.deck, "pdf": None, "pdf_generated": False,
          "pptx_slides": pptx_slide_count(args.deck),
          "pdf_pages": None, "page_parity": None, "pages": [],
          "tools": {}, "degraded": []}

    preview_dir = os.path.join(args.outdir, "preview")
    os.makedirs(preview_dir, exist_ok=True)

    soffice = find_tool("soffice", SOFFICE_CANDIDATES)
    qa["tools"]["soffice"] = soffice
    pdf_path = None
    if soffice is None:
        qa["degraded"].append(
            "soffice not found: PDF export skipped (no render evidence)")
    else:
        try:
            proc = subprocess.run(
                [soffice, "--headless", "--norestore", "--convert-to", "pdf",
                 "--outdir", args.outdir, args.deck],
                capture_output=True, text=True, timeout=180)
            qa["tools"]["soffice_returncode"] = proc.returncode
            if proc.returncode != 0:
                qa["degraded"].append(
                    f"soffice exited {proc.returncode}: "
                    f"{(proc.stderr or proc.stdout)[:300]}")
        except subprocess.TimeoutExpired:
            qa["degraded"].append("soffice conversion timed out (180s)")
        candidate = os.path.join(
            args.outdir,
            os.path.splitext(os.path.basename(args.deck))[0] + ".pdf")
        if os.path.exists(candidate):
            pdf_path = candidate
            qa["pdf"] = pdf_path
            qa["pdf_generated"] = True
        elif "soffice" in qa["tools"] and not qa["degraded"]:
            qa["degraded"].append("soffice ran but produced no PDF")

    if pdf_path:
        qa["pdf_pages"] = pdf_page_count(pdf_path)
        if qa["pdf_pages"] is not None and qa["pptx_slides"] is not None:
            qa["page_parity"] = qa["pdf_pages"] == qa["pptx_slides"]
            if not qa["page_parity"]:
                qa["degraded"].append(
                    f"page count mismatch: pptx={qa['pptx_slides']} "
                    f"pdf={qa['pdf_pages']}")

        pdftoppm = find_tool("pdftoppm")
        qa["tools"]["pdftoppm"] = pdftoppm
        if pdftoppm is None:
            qa["degraded"].append(
                "pdftoppm not found: PNG previews skipped")
        else:
            prefix = os.path.join(preview_dir, "slide")
            try:
                proc = subprocess.run(
                    [pdftoppm, "-png", "-r", "100", pdf_path, prefix],
                    capture_output=True, text=True, timeout=180)
                if proc.returncode != 0:
                    qa["degraded"].append(
                        f"pdftoppm exited {proc.returncode}: "
                        f"{proc.stderr[:300]}")
            except subprocess.TimeoutExpired:
                qa["degraded"].append("pdftoppm timed out (180s)")
            n = qa["pdf_pages"] or 0
            for i in range(1, n + 1):
                png = f"{prefix}-{i}.png"
                ok = os.path.exists(png) and os.path.getsize(png) > 0
                qa["pages"].append({
                    "page": i, "png": png if ok else None,
                    "rendered": bool(ok),
                    "bytes": os.path.getsize(png) if ok else 0})
            missing = [p["page"] for p in qa["pages"] if not p["rendered"]]
            if missing:
                qa["degraded"].append(f"pages without PNG render: {missing}")

    qa["render_ok"] = bool(qa["pdf_generated"]
                           and qa["page_parity"] is not False
                           and (not qa["pages"]
                                or all(p["rendered"] for p in qa["pages"])))
    with open(args.report, "w", encoding="utf-8") as f:
        json.dump(qa, f, ensure_ascii=False, indent=2)
    print(f"[export_render] pdf={qa['pdf_generated']} "
          f"pages={qa['pdf_pages']}/{qa['pptx_slides']} "
          f"parity={qa['page_parity']} degraded={len(qa['degraded'])} "
          f"-> {args.report}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
