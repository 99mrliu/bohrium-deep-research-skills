#!/usr/bin/env python3
"""Render a PPTX and run the automated QA checks of references/render-playbook.md.

Usage:
  python3 render_qa.py deck.pptx --outdir /app/output --out render_qa.json
      [--expected-pages N] [--theme-fonts "FontA,FontB"] [--soffice PATH]

Pipeline: soffice -> PDF (outdir), pdftoppm -> per-page PNGs (outdir/preview),
then checks: page count, blank pages, out-of-bounds text (pdftotext -bbox),
font usage (pdffonts), images (pdfimages -list), empty placeholders (re-open deck).

Missing tools degrade the report to `unverified` for that check instead of
failing the run -- record reality, never invent a pass.
"""
import argparse
import glob
import json
import os
import re
import shutil
import subprocess
import sys


def which(name, given=None):
    return given or shutil.which(name)


def run(cmd, **kw):
    return subprocess.run(cmd, capture_output=True, text=True, **kw)


def convert(soffice, deck, outdir):
    profile = f"-env:UserInstallation=file:///tmp/lo_profile_{os.getpid()}"
    proc = run([soffice, profile, "--headless", "--convert-to", "pdf",
                "--outdir", outdir, deck], timeout=300)
    pdf = os.path.join(outdir, os.path.splitext(os.path.basename(deck))[0] + ".pdf")
    if not os.path.exists(pdf) or os.path.getsize(pdf) == 0:
        return None, f"conversion failed: {proc.stdout.strip()} {proc.stderr.strip()}".strip()
    return pdf, None


def pdf_pages(pdf, pdftotext):
    out = run([pdftotext, pdf, "-"]).stdout
    pages = out.split("\f")
    if pages and not pages[-1].strip():
        pages.pop()
    return pages


def blank_pages(pages, pdf, pdfimages):
    blanks = []
    img_pages = set()
    if pdfimages:
        for line in run([pdfimages, "-list", pdf]).stdout.splitlines()[2:]:
            cols = line.split()
            if cols and cols[0].isdigit():
                img_pages.add(int(cols[0]))
    for i, text in enumerate(pages, 1):
        if len(text.strip()) < 3 and i not in img_pages:
            blanks.append(i)
    return blanks


def overflow_suspects(pdf, pdftotext):
    suspects = []
    out = run([pdftotext, "-bbox", pdf, "-"]).stdout
    page_w = page_h = None
    cur = 0
    for line in out.splitlines():
        m = re.search(r'<page width="([\d.]+)" height="([\d.]+)"', line)
        if m:
            page_w, page_h = float(m.group(1)), float(m.group(2))
            cur += 1
            continue
        m = re.search(r'<word xMin="([\d.]+)" yMin="([\d.]+)" '
                      r'xMax="([\d.]+)" yMax="([\d.]+)"', line)
        if m and page_w:
            x0, y0, x1, y1 = (float(g) for g in m.groups())
            if x0 < -2 or y0 < -2 or x1 > page_w + 2 or y1 > page_h + 2:
                suspects.append({"page": cur, "word_box": [x0, y0, x1, y1],
                                 "page_box": [page_w, page_h]})
    return suspects[:50]


def fonts_used(pdf, pdffonts):
    fonts = []
    for line in run([pdffonts, pdf]).stdout.splitlines()[2:]:
        cols = line.split()
        if cols:
            fonts.append(cols[0])
    return sorted(set(fonts))


def deck_placeholder_residue(deck):
    try:
        from pptx import Presentation
    except ImportError:
        return None
    prs = Presentation(deck)
    residue = []
    for i, slide in enumerate(prs.slides, 1):
        for shape in slide.shapes:
            if shape.is_placeholder and shape.has_text_frame \
                    and not shape.text_frame.text.strip():
                residue.append({"slide": i,
                                "placeholder_idx": shape.placeholder_format.idx})
    return residue


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("deck")
    ap.add_argument("--outdir", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--expected-pages", type=int)
    ap.add_argument("--theme-fonts", default="")
    ap.add_argument("--soffice")
    args = ap.parse_args()

    soffice = which("soffice", args.soffice)
    pdftotext, pdftoppm = which("pdftotext"), which("pdftoppm")
    pdffonts, pdfimages = which("pdffonts"), which("pdfimages")

    report = {"deck": args.deck, "checks": {}, "tools": {
        "soffice": soffice or "missing", "pdftotext": pdftotext or "missing",
        "pdftoppm": pdftoppm or "missing", "pdffonts": pdffonts or "missing"}}

    if not soffice:
        report["render"] = "unverified: no soffice available"
    else:
        ver = run([soffice, "--version"]).stdout.strip()
        report["tools"]["soffice_version"] = ver
        pdf, err = convert(soffice, args.deck, args.outdir)
        if err:
            report["render"] = f"unverified: {err}"
        else:
            report["render"] = "rendered"
            report["pdf"] = pdf
            if pdftoppm:
                preview = os.path.join(args.outdir, "preview")
                os.makedirs(preview, exist_ok=True)
                run([pdftoppm, "-png", "-r", "110", pdf,
                     os.path.join(preview, "page")])
                report["previews"] = sorted(glob.glob(os.path.join(preview, "page-*.png")))
            if pdftotext:
                pages = pdf_pages(pdf, pdftotext)
                report["checks"]["page_count"] = {
                    "pdf_pages": len(pages),
                    "expected": args.expected_pages,
                    "pass": args.expected_pages is None or len(pages) == args.expected_pages}
                report["checks"]["blank_pages"] = {
                    "pages": blank_pages(pages, pdf, pdfimages),
                    "pass": not blank_pages(pages, pdf, pdfimages)}
                suspects = overflow_suspects(pdf, pdftotext)
                report["checks"]["overflow"] = {
                    "suspects": suspects, "pass": not suspects,
                    "note": "suspects are nominations; confirm visually on previews"}
            if pdffonts:
                used = fonts_used(pdf, pdffonts)
                theme = [f.strip() for f in args.theme_fonts.split(",") if f.strip()]
                substituted = [f for f in used if theme and not any(
                    t.split("+")[-1].lower() in f.lower() or
                    f.split("+")[-1].lower() in t.lower() for t in theme)]
                report["checks"]["fonts"] = {
                    "used": used, "theme": theme,
                    "not_in_theme": substituted,
                    "pass": not substituted,
                    "note": "base-14 and subset fonts may be render-side; remap or record"}

    residue = deck_placeholder_residue(args.deck)
    report["checks"]["placeholder_residue"] = (
        {"unverified": "python-pptx missing"} if residue is None else
        {"residue": residue, "pass": not residue,
         "note": "empty title/layout prompts on slides with real content elsewhere "
                 "are usually fine; empty body prompts are not"})

    fails = [k for k, v in report["checks"].items()
             if isinstance(v, dict) and v.get("pass") is False]
    report["summary"] = {"render": report["render"],
                         "failing_checks": fails,
                         "verdict": "issues" if fails else "clean"}
    with open(args.out, "w", encoding="utf-8") as fh:
        json.dump(report, fh, ensure_ascii=False, indent=1)
    print(f"render QA: {report['render']}; failing checks: {fails or 'none'} -> {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
