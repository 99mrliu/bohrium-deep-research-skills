#!/usr/bin/env python3
"""edit_lint.py -- machine gate for native editability (pillar 2).

Static scan of the finished pptx:
  1. text-as-image suspicion : slide with pictures but zero text
  2. font inventory vs whitelist (theme fonts + safe fonts)
  3. placeholder residue     : "Click to add ..." text or empty placeholders
  4. minimum font size       : body >= 14 pt, footnote-class >= 10 pt
  5. native table validation : real table shapes have text cells only
  6. image decodability      : magic bytes (+ PIL full decode when available)

Usage:
    python3 edit_lint.py presentation.pptx --report editability_report.json
Exit 1 when any ERROR finding exists, 0 otherwise, 2 if pptx unreadable.
"""
import argparse
import io
import json
import os
import re
import sys
import zipfile

try:
    from pptx import Presentation
    from pptx.util import Emu
    _HAS_PPTX = True
except ImportError:
    _HAS_PPTX = False

SAFE_FONTS = {
    "arial", "helvetica", "times new roman", "times", "calibri",
    "calibri light", "dejavu sans", "dejavu serif", "noto sans",
    "noto serif", "noto sans cjk sc", "noto serif cjk sc", "pingfang sc",
    "microsoft yahei", "simsun", "songti sc", "liberation sans",
    "liberation serif",
}
FOOTNOTE_NAME_PAT = re.compile(r"footer|footnote|caption", re.I)
BODY_MIN_PT = 14.0
FOOT_MIN_PT = 10.0


def theme_fonts(pptx_path):
    """Parse theme1.xml for major/minor latin typefaces (stdlib zip)."""
    fonts = set()
    try:
        with zipfile.ZipFile(pptx_path) as zf:
            for name in zf.namelist():
                if re.match(r"ppt/theme/theme\d+\.xml$", name):
                    xml = zf.read(name).decode("utf-8", "replace")
                    fonts.update(re.findall(
                        r'<a:latin[^>]*typeface="([^"]+)"', xml))
    except (OSError, zipfile.BadZipFile):
        pass
    return {f for f in fonts if f and not f.startswith("+")}


def img_ok(blob):
    if blob[:8] == b"\x89PNG\r\n\x1a\n" or blob[:3] == b"\xff\xd8\xff":
        pass
    else:
        return False, "bad magic bytes"
    try:
        from PIL import Image  # soft import
        with Image.open(io.BytesIO(blob)) as im:
            im.verify()
        return True, "PIL-verify"
    except ImportError:
        return True, "magic-bytes-only (PIL missing)"
    except Exception as exc:
        return False, "PIL decode failed: %s" % exc


def iter_runs(shape):
    if not shape.has_text_frame:
        return
    for para in shape.text_frame.paragraphs:
        for run in para.runs:
            yield run


def main():
    ap = argparse.ArgumentParser(description="Static editability gate for "
                                     "native pptx.")
    ap.add_argument("pptx")
    ap.add_argument("--report", required=True)
    args = ap.parse_args()

    if not _HAS_PPTX:
        sys.stderr.write("edit_lint: ERROR python-pptx missing; cannot "
                         "open pptx (tool_missing)\n")
        return 2
    try:
        prs = Presentation(args.pptx)
    except Exception as exc:
        sys.stderr.write("edit_lint: ERROR cannot open %s: %s\n"
                         % (args.pptx, exc))
        return 2

    errors, warnings, findings = [], [], []
    fonts_seen, sizes_seen = set(), []
    n_tables = n_pictures = 0
    theme = theme_fonts(args.pptx)

    for sidx, slide in enumerate(prs.slides, start=1):
        text_chars = 0
        pic_count = 0
        for shape in slide.shapes:
            stype = shape.shape_type
            name = shape.name or ""
            # placeholder residue
            if shape.is_placeholder:
                txt = shape.text_frame.text if shape.has_text_frame else ""
                if not txt.strip():
                    errors.append({"slide": sidx, "check": "placeholder_free",
                                   "detail": "empty placeholder '%s'" % name})
            if shape.has_text_frame:
                txt = shape.text_frame.text
                text_chars += len(txt.strip())
                if re.search(r"click to add", txt, re.I):
                    errors.append({"slide": sidx, "check": "placeholder_free",
                                   "detail": "residual prompt text in "
                                             "'%s'" % name})
                for run in iter_runs(shape):
                    if run.font.name:
                        fonts_seen.add(run.font.name)
                    sz = run.font.size
                    if sz is not None:
                        pt = sz.pt
                        sizes_seen.append(pt)
                        foot = bool(FOOTNOTE_NAME_PAT.search(name))
                        limit = FOOT_MIN_PT if foot else BODY_MIN_PT
                        if pt < limit:
                            errors.append({
                                "slide": sidx, "check": "min_font_size",
                                "detail": "run %.1fpt < %.0fpt in '%s' "
                                          "(%s)" % (pt, limit, name,
                                                    "footnote-class" if foot
                                                    else "body")})
            if stype == 13:  # PICTURE
                pic_count += 1
                n_pictures += 1
                try:
                    ok, how = img_ok(shape.image.blob)
                except Exception as exc:
                    ok, how = False, "image.blob error: %s" % exc
                if not ok:
                    errors.append({"slide": sidx, "check": "image_decodable",
                                   "detail": "%s: %s" % (name, how)})
                if re.search(r"table", name, re.I):
                    warnings.append({"slide": sidx,
                                     "check": "table_native",
                                     "detail": "picture named like a table: "
                                               "%s" % name})
            if shape.has_table:
                n_tables += 1
                bad = 0
                for row in shape.table.rows:
                    for cell in row.cells:
                        if cell.text_frame.text is None:
                            bad += 1
                if bad:
                    errors.append({"slide": sidx, "check": "table_native",
                                   "detail": "%d unreadable cells" % bad})
                findings.append({"slide": sidx, "check": "table_native",
                                 "detail": "native table %dx%d OK"
                                 % (len(shape.table.rows),
                                    len(shape.table.columns))})
        if pic_count and text_chars == 0:
            errors.append({"slide": sidx, "check": "text_as_image",
                           "detail": "slide has %d picture(s) but no text "
                                     "shape content" % pic_count})

    # font whitelist verdict (theme fonts are always allowed)
    font_bad = sorted(f for f in fonts_seen
                      if f.lower() not in SAFE_FONTS and f not in theme)
    for f in font_bad:
        errors.append({"check": "font_whitelist",
                       "detail": "explicit font '%s' not in safe whitelist "
                                 "nor theme fonts" % f})

    report = {
        "pptx": os.path.abspath(args.pptx),
        "slides": len(prs.slides._sldIdLst),
        "theme_fonts": sorted(theme),
        "explicit_fonts": sorted(fonts_seen),
        "font_policy_ok": not font_bad,
        "min_run_pt": min(sizes_seen) if sizes_seen else None,
        "native_tables": n_tables,
        "pictures": n_pictures,
        "errors": errors,
        "warnings": warnings,
        "findings": findings,
        "verdict": "PASS" if not errors else "FAIL",
    }
    os.makedirs(os.path.dirname(os.path.abspath(args.report)), exist_ok=True)
    with open(args.report, "w", encoding="utf-8") as fh:
        json.dump(report, fh, ensure_ascii=False, indent=2)
    print("edit_lint: verdict=%s errors=%d warnings=%d min_pt=%s -> %s"
          % (report["verdict"], len(errors), len(warnings),
             report["min_run_pt"], args.report))
    for e in errors:
        print("  ERROR s%s %s: %s" % (e.get("slide", "-"), e["check"],
                                      e["detail"]), file=sys.stderr)
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
