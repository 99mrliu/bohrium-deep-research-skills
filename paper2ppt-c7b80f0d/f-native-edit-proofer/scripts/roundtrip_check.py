#!/usr/bin/env python3
"""roundtrip_check.py -- reopen-verify the finished pptx (pillar 3a).

Proof by re-opening, not by self-declaration:
  * OOXML zip integrity (zipfile.testzip + required parts)
  * slide count vs expectation (optional --expect build_report.json)
  * per-slide shape inventory, notes presence
  * picture blobs decodable after round-trip
  * real table shapes survive

Usage:
    python3 roundtrip_check.py presentation.pptx --report roundtrip_report.json \
        [--expect build_report.json]
Exit 1 on any failed check, 2 if unreadable.
"""
import argparse
import io
import json
import os
import sys
import zipfile

REQUIRED_PARTS = ["[Content_Types].xml", "ppt/presentation.xml"]


def main():
    ap = argparse.ArgumentParser(description="Round-trip reopen check of a "
                                     "pptx file.")
    ap.add_argument("pptx")
    ap.add_argument("--report", required=True)
    ap.add_argument("--expect", default=None,
                    help="build_report.json for slide-count expectation")
    args = ap.parse_args()

    checks = []

    def add(check, ok, detail):
        checks.append({"check": check, "pass": bool(ok), "detail": detail})

    # --- zip / OOXML integrity (stdlib) ---
    try:
        with zipfile.ZipFile(args.pptx) as zf:
            bad = zf.testzip()
            add("zip_integrity", bad is None,
                "corrupt member: %s" % bad if bad else "all members CRC-ok")
            names = set(zf.namelist())
            missing = [p for p in REQUIRED_PARTS if p not in names]
            add("ooxml_required_parts", not missing,
                "missing: %s" % missing if missing else "present")
            n_notes = sum(1 for n in names if n.startswith("ppt/notesSlides/")
                          and n.endswith(".xml"))
    except (OSError, zipfile.BadZipFile) as exc:
        add("zip_integrity", False, str(exc))
        _write(args.report, args.pptx, checks)
        return 1

    # --- reopen with python-pptx ---
    try:
        from pptx import Presentation
    except ImportError:
        add("reopen_python-pptx", False, "tool_missing: python-pptx")
        _write(args.report, args.pptx, checks)
        return 2
    try:
        prs = Presentation(args.pptx)
        add("reopen_python-pptx", True, "opened")
    except Exception as exc:
        add("reopen_python-pptx", False, str(exc))
        _write(args.report, args.pptx, checks)
        return 1

    slides = list(prs.slides)
    expected = None
    if args.expect and os.path.isfile(args.expect):
        with open(args.expect, encoding="utf-8") as fh:
            expected = json.load(fh).get("slide_count")
    add("slide_count", expected is None or len(slides) == expected,
        "slides=%d expected=%s" % (len(slides), expected))

    notes_ok = shapes_ok = pics_ok = tables = 0
    per_slide = []
    for i, slide in enumerate(slides, start=1):
        n_shapes = len(slide.shapes)
        has_notes = (slide.has_notes_slide and
                     bool(slide.notes_slide.notes_text_frame.text.strip()))
        notes_ok += 1 if has_notes else 0
        shapes_ok += 1 if n_shapes else 0
        npics = 0
        for shape in slide.shapes:
            if shape.shape_type == 13:
                npics += 1
                blob = shape.image.blob
                magic = blob[:8] == b"\x89PNG\r\n\x1a\n" or \
                    blob[:3] == b"\xff\xd8\xff"
                try:
                    from PIL import Image
                    with Image.open(io.BytesIO(blob)) as im:
                        im.verify()
                    dec = True
                except ImportError:
                    dec = magic
                except Exception:
                    dec = False
                pics_ok += 1 if dec else 0
                add("picture_decode_s%d" % i, dec,
                    "%s %d bytes" % (shape.name, len(blob)))
            if shape.has_table:
                tables += 1
        per_slide.append({"slide": i, "shapes": n_shapes,
                          "pictures": npics, "notes": has_notes})
    add("notes_present_all", notes_ok == len(slides),
        "%d/%d slides have notes" % (notes_ok, len(slides)))
    add("shapes_nonempty", shapes_ok == len(slides),
        "%d/%d slides have >=1 shape" % (shapes_ok, len(slides)))
    add("notes_parts_consistent", n_notes >= notes_ok,
        "%d notesSlide parts in zip" % n_notes)

    ok = all(c["pass"] for c in checks)
    _write(args.report, args.pptx, checks,
           extra={"slide_count": len(slides), "native_tables": tables,
                  "per_slide": per_slide, "verdict": "PASS" if ok else "FAIL"})
    print("roundtrip_check: verdict=%s slides=%d tables=%d checks=%d -> %s"
          % ("PASS" if ok else "FAIL", len(slides), tables, len(checks),
             args.report))
    return 0 if ok else 1


def _write(report_path, pptx, checks, extra=None):
    doc = {"pptx": os.path.abspath(pptx), "checks": checks,
           "verdict": "PASS" if all(c["pass"] for c in checks) else "FAIL"}
    if extra:
        doc.update(extra)
    os.makedirs(os.path.dirname(os.path.abspath(report_path)), exist_ok=True)
    with open(report_path, "w", encoding="utf-8") as fh:
        json.dump(doc, fh, ensure_ascii=False, indent=2)


if __name__ == "__main__":
    sys.exit(main())
