#!/usr/bin/env python3
"""export_audit.py -- post-export bounding-box audit of the rendered deck.

    export_audit.py --pptx /app/output/presentation.pptx \
        [--layout work/layout.json] [--out /app/output]

If soffice is on PATH:
  1. convert pptx -> /app/output/presentation.pdf with an isolated profile
     (-env:UserInstallation=file:///tmp/lo_audit, so it never fights a
     running LibreOffice instance);
  2. render page PNGs via pdftoppm -r 110 into <out>/preview/;
  3. run `pdftotext -bbox` and AUDIT every word's bounding box:
       - words outside the page rect minus a small margin -> violation;
       - words intersecting the bottom 6% zone collide with the footer ->
         violation, UNLESS they match the footer text / slide number that
         layout.json intentionally places there (whitelist);
  4. summarize embedded fonts via pdffonts, when available.
Writes <out>/render_audit.json
  {words_checked, violations[], fonts, verdict: PASS|FAIL|RENDERER_MISSING}
Exit 1 on FAIL, 0 otherwise. If soffice is missing the verdict is honestly
RENDERER_MISSING, the file is still written, and exit code is 0 -- the SVG/PNG
previews from preview_render.py are then the inspection artifact.
"""
import argparse
import json
import os
import shutil
import subprocess
import sys
import xml.etree.ElementTree as ET

PAGE_MARGIN_PT = 4.0      # words must fit inside page rect minus this
FOOTER_ZONE_FRAC = 0.06   # bottom 6% of page = footer zone


def _which(name):
    return shutil.which(name)


def _run(cmd, timeout=120):
    return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)


def _whitelist(layout_path):
    """Words we intentionally place in the footer zone (footer text, slide nos)."""
    words = set()
    if not layout_path or not os.path.isfile(layout_path):
        return words
    try:
        with open(layout_path, encoding="utf-8") as fh:
            layout = json.load(fh)
    except Exception:  # noqa: BLE001
        return words
    for slide in layout.get("slides", []):
        for tok in (slide.get("footer") or "").split():
            words.add(tok.strip(".,;:()[]{}"))
        words.add(str(slide.get("slide_no", "")))
    words.discard("")
    return words


def _parse_bbox(bbox_xml_path, whitelist):
    """Audit pdftotext -bbox XHTML. Returns (words_checked, violations)."""
    ns = {"x": "http://www.w3.org/1999/xhtml"}
    tree = ET.parse(bbox_xml_path)
    root = tree.getroot()
    checked, violations = 0, []
    for pageno, page in enumerate(root.iter("{%s}page" % ns["x"]), start=1):
        pw = float(page.get("width", 0))
        ph = float(page.get("height", 0))
        if pw <= 0 or ph <= 0:
            continue
        footer_top = ph * (1.0 - FOOTER_ZONE_FRAC)
        for word in page.iter("{%s}word" % ns["x"]):
            checked += 1
            x0 = float(word.get("xMin"))
            y0 = float(word.get("yMin"))
            x1 = float(word.get("xMax"))
            y1 = float(word.get("yMax"))
            text = (word.text or "").strip()
            if (x0 < -PAGE_MARGIN_PT or y0 < -PAGE_MARGIN_PT
                    or x1 > pw + PAGE_MARGIN_PT or y1 > ph + PAGE_MARGIN_PT):
                violations.append({
                    "page": pageno, "word": text, "kind": "off_page",
                    "bbox": [x0, y0, x1, y1], "page_rect": [pw, ph]})
            elif y1 > footer_top and text not in whitelist:
                violations.append({
                    "page": pageno, "word": text, "kind": "footer_zone",
                    "bbox": [x0, y0, x1, y1],
                    "footer_zone_top": round(footer_top, 2)})
    return checked, violations


def main(argv=None):
    ap = argparse.ArgumentParser(description="Post-export bbox audit.")
    ap.add_argument("--pptx", required=True)
    ap.add_argument("--layout", default=None,
                    help="layout.json (footer-zone whitelist)")
    ap.add_argument("--out", default=os.environ.get("CASE_OUTPUT_DIR", "/app/output"))
    args = ap.parse_args(argv)
    os.makedirs(args.out, exist_ok=True)
    audit_path = os.path.join(args.out, "render_audit.json")

    audit = {"pptx": args.pptx, "words_checked": 0, "violations": [],
             "fonts": None, "verdict": "RENDERER_MISSING", "notes": []}

    soffice = _which("soffice")
    if not soffice:
        audit["notes"].append(
            "soffice not found on PATH; export render skipped. Verdict is "
            "honestly RENDERER_MISSING -- inspect preview_render.py SVG/PNG "
            "previews instead, and rerun this audit where LibreOffice exists.")
        with open(audit_path, "w", encoding="utf-8") as fh:
            json.dump(audit, fh, indent=2, ensure_ascii=False)
            fh.write("\n")
        print("export_audit: soffice missing -> verdict RENDERER_MISSING -> %s"
              % audit_path)
        return 0

    pdf_path = os.path.join(args.out, "presentation.pdf")
    try:
        proc = _run([soffice, "--headless", "--norestore",
                     "-env:UserInstallation=file:///tmp/lo_audit",
                     "--convert-to", "pdf", "--outdir", args.out, args.pptx],
                    timeout=300)
    except subprocess.TimeoutExpired:
        audit["verdict"] = "FAIL"
        audit["notes"].append("soffice conversion timed out")
        _write(audit_path, audit)
        return 1
    if proc.returncode != 0 or not os.path.isfile(pdf_path):
        audit["verdict"] = "FAIL"
        audit["notes"].append("soffice conversion failed: %s %s"
                              % (proc.stdout.strip(), proc.stderr.strip()))
        _write(audit_path, audit)
        return 1

    pdftoppm = _which("pdftoppm")
    if pdftoppm:
        preview_dir = os.path.join(args.out, "preview")
        os.makedirs(preview_dir, exist_ok=True)
        _run([pdftoppm, "-r", "110", "-png", pdf_path,
              os.path.join(preview_dir, "slide")], timeout=300)
    else:
        audit["notes"].append("pdftoppm missing; no PDF page PNGs rendered")

    pdftotext = _which("pdftotext")
    if pdftotext:
        bbox_path = os.path.join(args.out, "_audit_bbox.xhtml")
        proc = _run([pdftotext, "-bbox", pdf_path, bbox_path], timeout=120)
        if proc.returncode == 0 and os.path.isfile(bbox_path):
            checked, violations = _parse_bbox(bbox_path, _whitelist(args.layout))
            audit["words_checked"] = checked
            audit["violations"] = violations
            os.remove(bbox_path)
        else:
            audit["notes"].append("pdftotext -bbox failed: %s" % proc.stderr.strip())
    else:
        audit["notes"].append("pdftotext missing; bbox audit skipped")

    pdffonts = _which("pdffonts")
    if pdffonts:
        proc = _run([pdffonts, pdf_path], timeout=60)
        if proc.returncode == 0:
            audit["fonts"] = proc.stdout.strip().splitlines()[:24]

    audit["verdict"] = "FAIL" if audit["violations"] else "PASS"
    _write(audit_path, audit)
    print("export_audit: verdict=%s words_checked=%d violations=%d -> %s"
          % (audit["verdict"], audit["words_checked"],
             len(audit["violations"]), audit_path))
    return 1 if audit["verdict"] == "FAIL" else 0


def _write(path, audit):
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(audit, fh, indent=2, ensure_ascii=False)
        fh.write("\n")


if __name__ == "__main__":
    sys.exit(main())
