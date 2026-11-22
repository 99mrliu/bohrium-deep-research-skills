#!/usr/bin/env python3
"""compile_deck.py -- deterministic compiler: deck.spec.json -> .pptx

Two backends, chosen automatically:
  template : python-pptx is importable AND (--template or --start-deck given).
             Real layouts/placeholders of the organizer file are used, so
             master/theme/fonts/footers are genuinely inherited.
  builtin  : bundled pure-stdlib OOXML writer (plain 16:9 theme). The deviation
             from an organizer template is disclosed in compile_report.json.

The compiler NEVER writes slide content by hand elsewhere: the agent authors
exactly one artifact (deck.spec.json); this program does all mechanical work
and records every mechanical decision in compile_report.json.

Constraint policy enforced at build time (see references/text_fit.md):
  * slide-limit   : non-backup slides beyond meta.slide_limit are moved into a
                    clearly-labelled backup section appended after a divider.
  * bullet cap    : bullets beyond meta.max_bullets are demoted into speaker
                    notes with a [DEMOTED:bullet-cap] marker.
  * title policy  : titles may wrap to 2 lines; longer titles are elided with
                    "..." and the full title is preserved in notes.
  * text-fit      : chars-per-line x lines-vs-box heuristic. Width units:
                    CJK char = 2 units, latin char = 1 unit; 1 unit is
                    approximated as 0.5 * font_size (pt) of advance width.
                    Line height = 1.3 * font_size. On estimated overflow the
                    body font walks down BODY_LADDER one step at a time to
                    FONT_FLOOR_PT; if it still overflows at the floor, trailing
                    bullets are demoted to notes with [DEMOTED:text-fit] and a
                    warning is recorded. Text is never shrunk below the floor.
  * evidence      : every slide with evidence locators gets a footer stamped
                    "{footer_prefix}{ref} (p. {page}); ...".
  * images        : inserted with aspect ratio preserved inside a bounding box;
                    PNG size read from the file header (no PIL needed).
  * notes         : real notes-slide text on every slide, including demotions.
"""
import argparse
import json
import math
import os
import struct
import sys
import time
import zipfile
from xml.sax.saxutils import escape

COMPILER_VERSION = "1.0.0"

# --------------------------------------------------------------------------
# Geometry & fit constants (16:9). EMU = 914400 per inch.
# --------------------------------------------------------------------------
EMU = 914400
PT = 12700                      # EMU per point
SLIDE_W = 12192000              # 13.333 in
SLIDE_H = 6858000               # 7.5 in
MARGIN = int(0.55 * EMU)
TITLE_H = int(0.75 * EMU)
CLAIM_H = int(0.42 * EMU)
FOOTER_H = int(0.32 * EMU)

TITLE_FONT_PT = 28
TITLE_FONT_MIN_PT = 22
CLAIM_FONT_PT = 14
FOOTER_FONT_PT = 10
TABLE_FONT_PT = 12
BODY_LADDER = [20, 18, 16, 14, 12]   # shrink ladder, one step at a time
FONT_FLOOR_PT = 12                   # readability floor; never go below
TABLE_MAX_ROWS = 8                   # rows on the slide; surplus -> notes
TITLE_WRAP_UNITS = 110               # ~2 lines of title at TITLE_FONT_MIN_PT


def text_units(s):
    """Display width units: CJK/wide char = 2 units, other = 1 unit."""
    u = 0
    for ch in s:
        u += 2 if ord(ch) >= 0x2E80 else 1
    return u


def estimate_lines(text, font_pt, box_w_emu):
    """Estimated wrapped line count for `text` in a box of width box_w_emu.

    Heuristic: one unit of text is ~0.5 * font_pt wide (proportional fonts
    average ~0.5em advance; CJK glyphs are ~1em = 2 units). Line capacity is
    box_width / (0.5 * font_pt). Conservative on purpose: overestimating lines
    triggers a harmless shrink step; underestimating causes visual overflow.
    """
    if not text:
        return 0
    unit_w = 0.5 * font_pt * PT
    per_line = max(8, int(box_w_emu / unit_w))
    return max(1, math.ceil(text_units(text) / per_line))


def capacity_lines(box_h_emu, font_pt):
    """Whole lines that fit in box_h_emu at font_pt (line height = 1.3em)."""
    return max(1, int(box_h_emu / (font_pt * 1.3 * PT)))


def fit_bullets(bullets, box_w_emu, box_h_emu, decisions, sid):
    """Pick a font size from BODY_LADDER and demote overflow bullets to notes.

    Returns (kept_bullets, font_pt, demoted_list)."""
    demoted = []
    kept = list(bullets)
    for font_pt in BODY_LADDER:
        need = sum(estimate_lines(b, font_pt, box_w_emu) for b in kept) \
            + int(0.4 * len(kept))          # inter-bullet spacing allowance
        if need <= capacity_lines(box_h_emu, font_pt):
            if font_pt != BODY_LADDER[0]:
                decisions.append(f"text-fit: body font shrunk to {font_pt}pt "
                                 f"(ladder step, floor {FONT_FLOOR_PT}pt)")
            return kept, font_pt, demoted
    # still overflowing at the floor: demote trailing bullets, never shrink below floor
    font_pt = FONT_FLOOR_PT
    while kept:
        need = sum(estimate_lines(b, font_pt, box_w_emu) for b in kept) \
            + int(0.4 * len(kept))
        if need <= capacity_lines(box_h_emu, font_pt):
            break
        demoted.insert(0, kept.pop())
    if demoted:
        decisions.append(f"text-fit: {len(demoted)} trailing bullet(s) demoted to notes "
                         f"at readability floor {FONT_FLOOR_PT}pt (estimated overflow)")
    return kept, font_pt, demoted


def png_size(path):
    """Return (width_px, height_px, dpi) from a PNG header; dpi defaults to 96."""
    with open(path, "rb") as f:
        head = f.read(33)
        if head[:8] != b"\x89PNG\r\n\x1a\n" or head[12:16] != b"IHDR":
            raise ValueError(f"not a PNG file: {path}")
        w, h = struct.unpack(">II", head[16:24])
        dpi = 96.0
        f.seek(8)
        while True:
            raw = f.read(8)
            if len(raw) < 8:
                break
            ln, typ = struct.unpack(">I4s", raw)
            if typ == b"pHYs" and ln >= 9:
                xppm, _yppm, unit = struct.unpack(">IIB", f.read(9))
                if unit == 1 and xppm:
                    dpi = xppm * 0.0254
                break
            f.seek(ln + 4, 1)
        return w, h, dpi


def fit_image_in_box(w_emu, h_emu, bx, by, bw, bh):
    """Aspect-preserving fit of an image inside a bounding box; returns off/ext."""
    scale = min(bw / w_emu, bh / h_emu)
    w, h = int(w_emu * scale), int(h_emu * scale)
    return bx + (bw - w) // 2, by + (bh - h) // 2, w, h


# --------------------------------------------------------------------------
# Planning: spec -> render plans (backend independent). All mechanical
# decisions are made here so both backends enforce identical constraints.
# --------------------------------------------------------------------------
def build_plans(spec, spec_dir, report):
    meta = spec.get("meta", {})
    limit = meta.get("slide_limit", 20)
    max_bullets = meta.get("max_bullets", 6)
    prefix = meta.get("footer_prefix", "Source: ")

    slides = list(spec.get("slides", []))
    main = [s for s in slides if s.get("kind") != "backup"]
    backup = [s for s in slides if s.get("kind") == "backup"]

    overflow = []
    if len(main) > limit:
        overflow = main[limit:]
        main = main[:limit]
        report["warnings"].append(
            f"slide-limit: {len(overflow)} slide(s) over meta.slide_limit={limit} "
            "moved to backup section")
    if overflow:
        divider = {"id": "_backup_divider", "kind": "backup",
                   "title": "Backup / Appendix",
                   "claim": "Overflow slides beyond the talk limit; not part of the timed talk.",
                   "bullets": [f"{s.get('id')}: {s.get('title') or s.get('claim', '')[:60]}"
                               for s in overflow + backup],
                   "notes": "Divider inserted by the compiler because the spec exceeded "
                            "meta.slide_limit. The following slides are backup only."}
        ordered = main + [divider] + overflow + backup
    else:
        ordered = main + backup

    plans = []
    for idx, s in enumerate(ordered):
        sid = s.get("id", f"slide-{idx + 1}")
        kind = s.get("kind", "content")
        dec = []
        title = (s.get("title") or s.get("claim") or "").strip()
        if text_units(title) > TITLE_WRAP_UNITS:
            full = title
            cut = title[:TITLE_WRAP_UNITS // 2].rstrip() + " ..."
            dec.append("title-policy: title elided for slide real estate; "
                       "full title preserved in speaker notes")
            title = cut
            s = dict(s, notes=(s.get("notes", "") + f"\n[FULL TITLE] {full}"))

        bullets = list(s.get("bullets", []))
        demoted = []
        if len(bullets) > max_bullets:
            demoted = bullets[max_bullets:]
            bullets = bullets[:max_bullets]
            dec.append(f"bullet-cap: {len(demoted)} bullet(s) over meta.max_bullets="
                       f"{max_bullets} demoted to notes [DEMOTED:bullet-cap]")

        # body box estimate per kind (builtin geometry; the template backend
        # uses the same ladder before filling real placeholders)
        body_top = MARGIN + TITLE_H + CLAIM_H + int(0.12 * EMU)
        body_h = SLIDE_H - FOOTER_H - int(0.15 * EMU) - body_top
        if kind == "figure":
            body_w = int((SLIDE_W - 2 * MARGIN) * 0.44)
        elif kind == "two-column":
            body_w = int((SLIDE_W - 2 * MARGIN - int(0.3 * EMU)) / 2)
        elif kind == "table":
            body_w = SLIDE_W - 2 * MARGIN
            body_h = int(body_h * 0.42)
        else:
            body_w = SLIDE_W - 2 * MARGIN
        kept, font_pt, fit_demoted = fit_bullets(bullets, body_w, body_h, dec, sid)
        demoted_all = [(b, "bullet-cap") for b in demoted] + \
                      [(b, "text-fit") for b in fit_demoted]

        notes = s.get("notes", "").strip()
        for b, why in demoted_all:
            notes += f"\n[DEMOTED:{why}] {b}"

        footer = ""
        ev = s.get("evidence") or []
        if ev:
            parts = []
            for e in ev:
                ref = e.get("ref", "")
                parts.append(f"{ref} (p. {e['page']})" if e.get("page") else ref)
            footer = prefix + "; ".join(parts)

        # table compaction
        table = s.get("table")
        table_note = None
        if table:
            rows = table.get("rows", [])
            if len(rows) > TABLE_MAX_ROWS:
                extra = rows[TABLE_MAX_ROWS:]
                table = {"columns": table["columns"], "rows": rows[:TABLE_MAX_ROWS]}
                table_note = ("[DEMOTED:table-rows] %d surplus row(s) moved to notes: %s"
                              % (len(extra), json.dumps(extra, ensure_ascii=False)))
                notes += "\n" + table_note
                dec.append(f"table-compaction: {len(extra)} row(s) over {TABLE_MAX_ROWS} "
                           "moved to notes [DEMOTED:table-rows]")

        img = s.get("image")
        img_path = None
        if img and img.get("path"):
            p = img["path"]
            img_path = p if os.path.isabs(p) else os.path.join(spec_dir, p)
            if not os.path.isfile(img_path):
                dec.append(f"image-missing: {p} not found; placeholder box drawn")
                report["warnings"].append(f"{sid}: image not found: {p}")
                img_path = None

        plans.append({
            "n": idx + 1, "id": sid, "kind": kind,
            "title": title or sid,
            "claim": (s.get("claim") or "").strip(),
            "bullets": kept, "font_pt": font_pt,
            "footer": footer, "notes": notes,
            "image_path": img_path,
            "image_caption": (img or {}).get("caption", ""),
            "table": table,
            "evidence": ev,
            "decisions": dec,
        })
        report["decisions"].append({"slide": sid, "kind": kind, "actions": dec})
    report["slide_count"] = {
        "spec": len(slides), "emitted": len(plans),
        "slide_limit": limit, "backup_overflow": len(overflow),
        "backup_declared": len(backup),
    }
    return plans


# ==========================================================================
# Builtin backend: pure-stdlib minimal OOXML writer (16:9 plain theme)
# ============================================================================
NS_A = "http://schemas.openxmlformats.org/drawingml/2006/main"
NS_R = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
NS_P = "http://schemas.openxmlformats.org/presentationml/2006/main"
XML_DECL = '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\r\n'

DK1, LT1, ACCENT, GRAY = "1F3864", "FFFFFF", "4472C4", "595959"


def _txbody(paras, anchor_top=True):
    """paras: list of dicts {text, size, bold, italic, color, bullet, align}."""
    body = "<a:bodyPr wrap=\"square\" anchor=\"%s\"><a:normAutofit/></a:bodyPr><a:lstStyle/>" % (
        "t" if anchor_top else "ctr")
    out = [body]
    for p in paras:
        rpr = f'<a:rPr lang="en-US" sz="{int(p.get("size", 18) * 100)}"'
        if p.get("bold"):
            rpr += ' b="1"'
        if p.get("italic"):
            rpr += ' i="1"'
        rpr += f'><a:solidFill><a:srgbClr val="{p.get("color", "000000")}"/></a:solidFill></a:rPr>'
        align = f' algn="{p["align"]}"' if p.get("align") else ""
        if p.get("bullet"):
            ppr = f'<a:pPr marL="228600" indent="-228600"{align}><a:buFont typeface="Arial"/><a:buChar char="\u2022"/></a:pPr>'
        else:
            ppr = f"<a:pPr{align}/>" if align else ""
        out.append(f"<a:p>{ppr}<a:r>{rpr}<a:t>{escape(p['text'])}</a:t></a:r></a:p>")
    if not paras:
        out.append("<a:p/>")
    return "<p:txBody>" + "".join(out) + "</p:txBody>"


def _sp(sid, name, x, y, cx, cy, paras, fill=None):
    fillxml = (f'<a:solidFill><a:srgbClr val="{fill}"/></a:solidFill>' if fill
               else "<a:noFill/>")
    return (f'<p:sp><p:nvSpPr><p:cNvPr id="{sid}" name="{escape(name)}"/>'
            f'<p:cNvSpPr><a:spLocks noGrp="1"/></p:cNvSpPr><p:nvPr/></p:nvSpPr>'
            f'<p:spPr><a:xfrm><a:off x="{x}" y="{y}"/><a:ext cx="{cx}" cy="{cy}"/></a:xfrm>'
            f'<a:prstGeom prst="rect"><a:avLst/></a:prstGeom>{fillxml}</p:spPr>'
            + _txbody(paras) + "</p:sp>")


def _pic(sid, name, rid, x, y, cx, cy):
    return (f'<p:pic><p:nvPicPr><p:cNvPr id="{sid}" name="{escape(name)}"/>'
            f'<p:cNvPicPr><a:picLocks noChangeAspect="1"/></p:cNvPicPr><p:nvPr/></p:nvPicPr>'
            f'<p:blipFill><a:blip r:embed="{rid}"/><a:stretch><a:fillRect/></a:stretch></p:blipFill>'
            f'<p:spPr><a:xfrm><a:off x="{x}" y="{y}"/><a:ext cx="{cx}" cy="{cy}"/></a:xfrm>'
            f'<a:prstGeom prst="rect"><a:avLst/></a:prstGeom></p:spPr></p:pic>')


def _slide_xml(plan, img_rid=None, img_frame=None):
    shapes = []
    nid = 2
    body_top = MARGIN + TITLE_H + CLAIM_H + int(0.12 * EMU)
    body_h = SLIDE_H - FOOTER_H - int(0.15 * EMU) - body_top
    full_w = SLIDE_W - 2 * MARGIN
    kind = plan["kind"]

    if kind == "title":
        shapes.append(_sp(nid, "Title", MARGIN, int(2.2 * EMU), full_w, int(1.6 * EMU),
                          [{"text": plan["title"], "size": 40, "bold": True,
                            "color": DK1, "align": "ctr"}], )); nid += 1
        sub = plan["claim"] or plan["footer"]
        if sub:
            shapes.append(_sp(nid, "Subtitle", MARGIN, int(3.9 * EMU), full_w,
                              int(0.8 * EMU),
                              [{"text": sub, "size": 18, "color": GRAY, "align": "ctr"}]))
            nid += 1
    elif kind == "section" or (kind == "backup" and plan["id"] == "_backup_divider"):
        shapes.append(_sp(nid, "SectionTitle", MARGIN, int(2.6 * EMU), full_w,
                          int(1.2 * EMU),
                          [{"text": plan["title"], "size": 32, "bold": True,
                            "color": ACCENT, "align": "ctr"}])); nid += 1
        if plan["bullets"]:
            shapes.append(_sp(nid, "SectionList", int(1.6 * EMU), int(3.9 * EMU),
                              SLIDE_W - int(3.2 * EMU), int(2.2 * EMU),
                              [{"text": b, "size": 14, "color": GRAY, "bullet": True}
                               for b in plan["bullets"][:8]])); nid += 1
    else:
        shapes.append(_sp(nid, "Title", MARGIN, int(0.25 * EMU), full_w, TITLE_H,
                          [{"text": plan["title"], "size": TITLE_FONT_PT, "bold": True,
                            "color": DK1}])); nid += 1
        if plan["claim"] and plan["claim"] != plan["title"]:
            shapes.append(_sp(nid, "Claim", MARGIN, int(0.25 * EMU) + TITLE_H,
                              full_w, CLAIM_H,
                              [{"text": plan["claim"], "size": CLAIM_FONT_PT,
                                "italic": True, "color": ACCENT}], fill="EDF2FA"))
            nid += 1
        fp = plan["font_pt"]
        if kind == "figure" and (img_rid or plan["image_path"] is None and plan["image_caption"]):
            bw = int(full_w * 0.44)
            shapes.append(_sp(nid, "Body", MARGIN, body_top, bw, body_h,
                              [{"text": b, "size": fp, "bullet": True}
                               for b in plan["bullets"]])); nid += 1
            ix = MARGIN + bw + int(0.25 * EMU)
            iw = SLIDE_W - MARGIN - ix
            if img_rid and img_frame:
                shapes.append(_pic(nid, "Figure", img_rid, *img_frame)); nid += 1
            else:
                shapes.append(_sp(nid, "FigurePlaceholder", ix, body_top, iw,
                                  int(body_h * 0.8),
                                  [{"text": "[IMAGE PLACEHOLDER]", "size": 14,
                                    "color": GRAY, "align": "ctr"}])); nid += 1
            if plan["image_caption"]:
                shapes.append(_sp(nid, "Caption", ix, body_top + int(body_h * 0.82),
                                  iw, int(body_h * 0.18),
                                  [{"text": plan["image_caption"], "size": 11,
                                    "italic": True, "color": GRAY, "align": "ctr"}]))
                nid += 1
        elif kind == "two-column":
            half = (full_w - int(0.3 * EMU)) // 2
            half_n = math.ceil(len(plan["bullets"]) / 2)
            cols = [plan["bullets"][:half_n], plan["bullets"][half_n:]]
            for c, bl in enumerate(cols):
                shapes.append(_sp(nid, f"Column{c + 1}",
                                  MARGIN + c * (half + int(0.3 * EMU)), body_top,
                                  half, body_h,
                                  [{"text": b, "size": fp, "bullet": True} for b in bl]))
                nid += 1
        elif kind == "table" and plan["table"]:
            if plan["bullets"]:
                shapes.append(_sp(nid, "Body", MARGIN, body_top, full_w,
                                  int(body_h * 0.4),
                                  [{"text": b, "size": fp, "bullet": True}
                                   for b in plan["bullets"]])); nid += 1
            tb = plan["table"]
            lines = ["  |  ".join(tb["columns"])] + \
                    ["  |  ".join(str(c) for c in r) for r in tb["rows"]]
            shapes.append(_sp(nid, "Table", MARGIN, body_top + int(body_h * 0.42),
                              full_w, int(body_h * 0.58),
                              [{"text": ln, "size": TABLE_FONT_PT,
                                "bold": (i == 0), "color": DK1 if i == 0 else "000000"}
                               for i, ln in enumerate(lines)])); nid += 1
        else:
            shapes.append(_sp(nid, "Body", MARGIN, body_top, full_w, body_h,
                              [{"text": b, "size": fp, "bullet": True}
                               for b in plan["bullets"]])); nid += 1
    # footer: evidence + page number, stamped on every slide
    if plan["footer"]:
        shapes.append(_sp(nid, "EvidenceFooter", MARGIN, SLIDE_H - FOOTER_H - int(0.05 * EMU),
                          int(full_w * 0.85), FOOTER_H,
                          [{"text": plan["footer"], "size": FOOTER_FONT_PT, "color": GRAY}]))
        nid += 1
    shapes.append(_sp(nid, "PageNum", SLIDE_W - MARGIN - int(0.5 * EMU),
                      SLIDE_H - FOOTER_H - int(0.05 * EMU), int(0.5 * EMU), FOOTER_H,
                      [{"text": str(plan["n"]), "size": FOOTER_FONT_PT, "color": GRAY,
                        "align": "r"}]))
    sp_tree = ('<p:nvGrpSpPr><p:cNvPr id="1" name=""/><p:cNvGrpSpPr/><p:nvPr/></p:nvGrpSpPr>'
               '<p:grpSpPr><a:xfrm><a:off x="0" y="0"/><a:ext cx="0" cy="0"/>'
               '<a:chOff x="0" y="0"/><a:chExt cx="0" cy="0"/></a:xfrm></p:grpSpPr>'
               + "".join(shapes))
    return (XML_DECL +
            f'<p:sld xmlns:a="{NS_A}" xmlns:r="{NS_R}" xmlns:p="{NS_P}">'
            f"<p:cSld><p:spTree>{sp_tree}</p:spTree></p:cSld>"
            '<p:clrMapOvr><a:masterClrMapping/></p:clrMapOvr></p:sld>')


def _notes_xml(plan):
    paras = [{"text": ln, "size": 12} for ln in plan["notes"].split("\n") if ln.strip()]
    if not paras:
        paras = [{"text": "(no notes)", "size": 12}]
    sp_tree = ('<p:nvGrpSpPr><p:cNvPr id="1" name=""/><p:cNvGrpSpPr/><p:nvPr/></p:nvGrpSpPr>'
               '<p:grpSpPr><a:xfrm><a:off x="0" y="0"/><a:ext cx="0" cy="0"/>'
               '<a:chOff x="0" y="0"/><a:chExt cx="0" cy="0"/></a:xfrm></p:grpSpPr>'
               f'<p:sp><p:nvSpPr><p:cNvPr id="2" name="Notes Placeholder"/>'
               f'<p:cNvSpPr><a:spLocks noGrp="1"/></p:cNvSpPr>'
               f'<p:nvPr><p:ph type="body" idx="1"/></p:nvPr></p:nvSpPr>'
               f'<p:spPr><a:xfrm><a:off x="685800" y="457200"/><a:ext cx="5486400" cy="6858000"/></a:xfrm>'
               f'<a:prstGeom prst="rect"><a:avLst/></a:prstGeom><a:noFill/></p:spPr>'
               + _txbody(paras) + "</p:sp>")
    return (XML_DECL +
            f'<p:notes xmlns:a="{NS_A}" xmlns:r="{NS_R}" xmlns:p="{NS_P}">'
            f"<p:cSld><p:spTree>{sp_tree}</p:spTree></p:cSld>"
            '<p:clrMapOvr><a:masterClrMapping/></p:clrMapOvr></p:notes>')


def _theme_xml():
    fills = "".join('<a:solidFill><a:schemeClr val="phClr"/></a:solidFill>' for _ in range(3))
    lns = "".join(
        f'<a:ln w="{w}" cap="flat" cmpd="sng" algn="ctr"><a:solidFill><a:schemeClr val="phClr"/></a:solidFill>'
        f'<a:prstDash val="solid"/></a:ln>'
        for w in (6350, 12700, 19050))
    effs = "".join("<a:effectStyle><a:effectLst/></a:effectStyle>" for _ in range(3))
    return (XML_DECL +
            f'<a:theme xmlns:a="{NS_A}" name="PptSpecCompiler Plain">'
            '<a:themeElements><a:clrScheme name="Office">'
            '<a:dk1><a:sysClr val="windowText" lastClr="000000"/></a:dk1>'
            '<a:lt1><a:sysClr val="window" lastClr="FFFFFF"/></a:lt1>'
            f'<a:dk2><a:srgbClr val="{DK1}"/></a:dk2><a:lt2><a:srgbClr val="E7E6E6"/></a:lt2>'
            f'<a:accent1><a:srgbClr val="{ACCENT}"/></a:accent1>'
            '<a:accent2><a:srgbClr val="ED7D31"/></a:accent2>'
            '<a:accent3><a:srgbClr val="A5A5A5"/></a:accent3>'
            '<a:accent4><a:srgbClr val="FFC000"/></a:accent4>'
            '<a:accent5><a:srgbClr val="5B9BD5"/></a:accent5>'
            '<a:accent6><a:srgbClr val="70AD47"/></a:accent6>'
            '<a:hlink><a:srgbClr val="0563C1"/></a:hlink>'
            '<a:folHlink><a:srgbClr val="954F72"/></a:folHlink></a:clrScheme>'
            '<a:fontScheme name="Office"><a:majorFont><a:latin typeface="Calibri Light"/>'
            '<a:ea typeface=""/><a:cs typeface=""/></a:majorFont>'
            '<a:minorFont><a:latin typeface="Calibri"/><a:ea typeface=""/><a:cs typeface=""/></a:minorFont>'
            '</a:fontScheme>'
            f'<a:fmtScheme name="Office"><a:fillStyleLst>{fills}</a:fillStyleLst>'
            f'<a:lnStyleLst>{lns}</a:lnStyleLst><a:effectStyleLst>{effs}</a:effectStyleLst>'
            f'<a:bgFillStyleLst>{fills}</a:bgFillStyleLst></a:fmtScheme>'
            '</a:themeElements></a:theme>')


def _lvls(sizes):
    out = []
    for i, sz in enumerate(sizes, 1):
        out.append(f'<a:lvl{i}pPr marL="{342900 * i}" indent="-342900">'
                   f'<a:defRPr sz="{sz}"/></a:lvl{i}pPr>')
    return "".join(out)


def _master_xml():
    body = _lvls([1800, 1600, 1400, 1200, 1200, 1200, 1200, 1200, 1200])
    sp_tree = ('<p:nvGrpSpPr><p:cNvPr id="1" name=""/><p:cNvGrpSpPr/><p:nvPr/></p:nvGrpSpPr>'
               '<p:grpSpPr><a:xfrm><a:off x="0" y="0"/><a:ext cx="0" cy="0"/>'
               '<a:chOff x="0" y="0"/><a:chExt cx="0" cy="0"/></a:xfrm></p:grpSpPr>')
    return (XML_DECL +
            f'<p:sldMaster xmlns:a="{NS_A}" xmlns:r="{NS_R}" xmlns:p="{NS_P}">'
            '<p:cSld><p:bg><p:bgPr><a:solidFill><a:srgbClr val="FFFFFF"/></a:solidFill>'
            "<a:effectLst/></p:bgPr></p:bg>"
            f"<p:spTree>{sp_tree}</p:spTree></p:cSld>"
            '<p:clrMap bg1="lt1" tx1="dk1" bg2="lt2" tx2="dk2" accent1="accent1" '
            'accent2="accent2" accent3="accent3" accent4="accent4" accent5="accent5" '
            'accent6="accent6" hlink="hlink" folHlink="folHlink"/>'
            '<p:sldLayoutIdLst><p:sldLayoutId id="2147483649" r:id="rId1"/></p:sldLayoutIdLst>'
            f'<p:txStyles><p:titleStyle><a:lvl1pPr><a:defRPr sz="2800" b="1"/></a:lvl1pPr></p:titleStyle>'
            f"<p:bodyStyle>{body}</p:bodyStyle>"
            '<p:otherStyle><a:lvl1pPr><a:defRPr sz="1800"/></a:lvl1pPr></p:otherStyle></p:txStyles>'
            "</p:sldMaster>")


def _layout_xml():
    sp_tree = ('<p:nvGrpSpPr><p:cNvPr id="1" name=""/><p:cNvGrpSpPr/><p:nvPr/></p:nvGrpSpPr>'
               '<p:grpSpPr><a:xfrm><a:off x="0" y="0"/><a:ext cx="0" cy="0"/>'
               '<a:chOff x="0" y="0"/><a:chExt cx="0" cy="0"/></a:xfrm></p:grpSpPr>')
    return (XML_DECL +
            f'<p:sldLayout xmlns:a="{NS_A}" xmlns:r="{NS_R}" xmlns:p="{NS_P}" '
            'matchingName="Blank" type="blank" preserve="1">'
            f'<p:cSld name="Blank"><p:spTree>{sp_tree}</p:spTree></p:cSld>'
            '<p:clrMapOvr><a:masterClrMapping/></p:clrMapOvr></p:sldLayout>')


def _notes_master_xml():
    sp_tree = ('<p:nvGrpSpPr><p:cNvPr id="1" name=""/><p:cNvGrpSpPr/><p:nvPr/></p:nvGrpSpPr>'
               '<p:grpSpPr><a:xfrm><a:off x="0" y="0"/><a:ext cx="0" cy="0"/>'
               '<a:chOff x="0" y="0"/><a:chExt cx="0" cy="0"/></a:xfrm></p:grpSpPr>')
    return (XML_DECL +
            f'<p:notesMaster xmlns:a="{NS_A}" xmlns:r="{NS_R}" xmlns:p="{NS_P}">'
            f"<p:cSld><p:spTree>{sp_tree}</p:spTree></p:cSld>"
            '<p:clrMap bg1="lt1" tx1="dk1" bg2="lt2" tx2="dk2" accent1="accent1" '
            'accent2="accent2" accent3="accent3" accent4="accent4" accent5="accent5" '
            'accent6="accent6" hlink="hlink" folHlink="folHlink"/>'
            '<p:notesStyle><a:lvl1pPr><a:defRPr sz="1200"/></a:lvl1pPr></p:notesStyle>'
            "</p:notesMaster>")


REL = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
PKG_REL = "http://schemas.openxmlformats.org/package/2006/relationships"


def _rels_xml(rels):
    items = "".join(f'<Relationship Id="{rid}" Type="{REL}/{typ}" Target="{tgt}"/>'
                    for rid, typ, tgt in rels)
    return (XML_DECL +
            f'<Relationships xmlns="{PKG_REL}">{items}</Relationships>')


def compile_builtin(plans, out_path, report):
    n = len(plans)
    overrides = [
        ("/ppt/presentation.xml", "presentationml.presentation.main+xml"),
        ("/ppt/slideMasters/slideMaster1.xml", "presentationml.slideMaster+xml"),
        ("/ppt/slideLayouts/slideLayout1.xml", "presentationml.slideLayout+xml"),
        ("/ppt/notesMasters/notesMaster1.xml", "presentationml.notesMaster+xml"),
        ("/ppt/theme/theme1.xml", "drawingml.theme+xml"),
        ("/ppt/presProps.xml", "presentationml.presProps+xml"),
        ("/ppt/viewProps.xml", "presentationml.viewProps+xml"),
        ("/ppt/tableStyles.xml", "presentationml.tableStyles+xml"),
        ("/docProps/core.xml", "package.core-properties+xml"),
        ("/docProps/app.xml", "extended-properties+xml"),
    ]
    for i in range(1, n + 1):
        overrides.append((f"/ppt/slides/slide{i}.xml", "presentationml.slide+xml"))
        overrides.append((f"/ppt/notesSlides/notesSlide{i}.xml", "presentationml.notesSlide+xml"))
    def _ctype(part, kind):
        base = "application/vnd.openxmlformats-officedocument."
        if kind == "package.core-properties+xml":
            return f'<Override PartName="{part}" ContentType="application/vnd.openxmlformats-package.core-properties+xml"/>'
        if kind == "extended-properties+xml":
            return f'<Override PartName="{part}" ContentType="application/vnd.openxmlformats-officedocument.extended-properties+xml"/>'
        return f'<Override PartName="{part}" ContentType="{base}{kind}"/>'
    ct = (XML_DECL +
          '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
          '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
          '<Default Extension="xml" ContentType="application/xml"/>'
          '<Default Extension="png" ContentType="image/png"/>'
          + "".join(_ctype(p, t) for p, t in overrides) + "</Types>")

    pres_rels = [("rId1", "slideMaster", "slideMasters/slideMaster1.xml")]
    for i in range(1, n + 1):
        pres_rels.append((f"rId{i + 1}", "slide", f"slides/slide{i}.xml"))
    rid = n + 2
    pres_rels += [(f"rId{rid}", "notesMaster", "notesMasters/notesMaster1.xml"),
                  (f"rId{rid + 1}", "theme", "theme/theme1.xml"),
                  (f"rId{rid + 2}", "presProps", "presProps.xml"),
                  (f"rId{rid + 3}", "viewProps", "viewProps.xml"),
                  (f"rId{rid + 4}", "tableStyles", "tableStyles.xml")]
    sld_ids = "".join(f'<p:sldId id="{255 + i}" r:id="rId{i + 1}"/>' for i in range(1, n + 1))
    pres_xml = (XML_DECL +
                f'<p:presentation xmlns:a="{NS_A}" xmlns:r="{NS_R}" xmlns:p="{NS_P}">'
                '<p:sldMasterIdLst><p:sldMasterId id="2147483648" r:id="rId1"/></p:sldMasterIdLst>'
                f"<p:sldIdLst>{sld_ids}</p:sldIdLst>"
                f'<p:notesMasterIdLst><p:notesMasterId r:id="rId{rid}"/></p:notesMasterIdLst>'
                '<p:sldSz cx="12192000" cy="6858000" type="screen16x9"/>'
                '<p:notesSz cx="6858000" cy="9144000"/>'
                '<p:defaultTextStyle><a:defPPr><a:defRPr lang="en-US"/></a:defPPr></p:defaultTextStyle>'
                "</p:presentation>")

    now = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    core = (XML_DECL +
            '<cp:coreProperties xmlns:cp="http://schemas.openxmlformats.org/package/2006/metadata/core-properties" '
            'xmlns:dc="http://purl.org/dc/elements/1.1/" xmlns:dcterms="http://purl.org/dc/terms/" '
            'xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">'
            '<dc:title>deck</dc:title><dc:creator>ppt-spec-compiler</dc:creator>'
            f'<dcterms:created xsi:type="dcterms:W3CDTF">{now}</dcterms:created>'
            f'<dcterms:modified xsi:type="dcterms:W3CDTF">{now}</dcterms:modified>'
            "</cp:coreProperties>")
    app = (XML_DECL +
           '<Properties xmlns="http://schemas.openxmlformats.org/officeDocument/2006/extended-properties">'
           "<Application>ppt-spec-compiler builtin backend</Application>"
           f"<Slides>{n}</Slides><Notes>{n}</Notes></Properties>")
    pres_props = (XML_DECL +
                  f'<p:presentationPr xmlns:a="{NS_A}" xmlns:r="{NS_R}" xmlns:p="{NS_P}"/>')
    view_props = (XML_DECL +
                  f'<p:viewPr xmlns:a="{NS_A}" xmlns:r="{NS_R}" xmlns:p="{NS_P}">'
                  '<p:normalViewPr><p:restoredLeft sz="15620"/><p:restoredTop sz="94660"/>'
                  "</p:normalViewPr></p:viewPr>")
    table_styles = (XML_DECL +
                    f'<a:tblStyleLst xmlns:a="{NS_A}" '
                    'def="{5C22544A-7EE6-4342-B048-85BDC9FD1C3A}"/>')

    os.makedirs(os.path.dirname(os.path.abspath(out_path)), exist_ok=True)
    media = {}
    with zipfile.ZipFile(out_path, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("[Content_Types].xml", ct)
        z.writestr("_rels/.rels", _rels_xml([
            ("rId1", "officeDocument", "ppt/presentation.xml"),
            ("rId2", "metadata/core-properties", "docProps/core.xml"),
            ("rId3", "extended-properties", "docProps/app.xml")]))
        z.writestr("docProps/core.xml", core)
        z.writestr("docProps/app.xml", app)
        z.writestr("ppt/presentation.xml", pres_xml)
        z.writestr("ppt/_rels/presentation.xml.rels", _rels_xml(pres_rels))
        z.writestr("ppt/presProps.xml", pres_props)
        z.writestr("ppt/viewProps.xml", view_props)
        z.writestr("ppt/tableStyles.xml", table_styles)
        z.writestr("ppt/theme/theme1.xml", _theme_xml())
        z.writestr("ppt/slideMasters/slideMaster1.xml", _master_xml())
        z.writestr("ppt/slideMasters/_rels/slideMaster1.xml.rels", _rels_xml([
            ("rId1", "slideLayout", "../slideLayouts/slideLayout1.xml"),
            ("rId2", "theme", "../theme/theme1.xml")]))
        z.writestr("ppt/slideLayouts/slideLayout1.xml", _layout_xml())
        z.writestr("ppt/slideLayouts/_rels/slideLayout1.xml.rels", _rels_xml([
            ("rId1", "slideMaster", "../slideMasters/slideMaster1.xml")]))
        z.writestr("ppt/notesMasters/notesMaster1.xml", _notes_master_xml())
        z.writestr("ppt/notesMasters/_rels/notesMaster1.xml.rels", _rels_xml([
            ("rId1", "theme", "../theme/theme1.xml")]))
        for i, plan in enumerate(plans, 1):
            img_rid, img_frame = None, None
            slide_rels = [("rId1", "slideLayout", "../slideLayouts/slideLayout1.xml"),
                          ("rId2", "notesSlide", f"../notesSlides/notesSlide{i}.xml")]
            if plan["image_path"]:
                try:
                    wpx, hpx, dpi = png_size(plan["image_path"])
                    key = os.path.basename(plan["image_path"])
                    if key not in media:
                        with open(plan["image_path"], "rb") as f:
                            media[key] = f.read()
                    img_rid = "rId3"
                    slide_rels.append(("rId3", "image", f"../media/{key}"))
                    w_emu = int(wpx / dpi * EMU)
                    h_emu = int(hpx / dpi * EMU)
                    bw = int((SLIDE_W - 2 * MARGIN) * 0.50)
                    bx = SLIDE_W - MARGIN - bw
                    body_top = MARGIN + TITLE_H + CLAIM_H + int(0.12 * EMU)
                    body_h = SLIDE_H - FOOTER_H - int(0.15 * EMU) - body_top
                    img_frame = fit_image_in_box(w_emu, h_emu, bx, body_top,
                                                 bw, int(body_h * 0.8))
                    report["decisions"][i - 1]["actions"].append(
                        f"image: {key} {wpx}x{hpx}px @{dpi:.0f}dpi placed aspect-preserved")
                except Exception as e:  # unreadable image -> placeholder
                    report["warnings"].append(f"{plan['id']}: image unreadable ({e}); placeholder drawn")
                    plan["image_path"] = None
            z.writestr(f"ppt/slides/slide{i}.xml", _slide_xml(plan, img_rid, img_frame))
            z.writestr(f"ppt/slides/_rels/slide{i}.xml.rels", _rels_xml(slide_rels))
            z.writestr(f"ppt/notesSlides/notesSlide{i}.xml", _notes_xml(plan))
            z.writestr(f"ppt/notesSlides/_rels/notesSlide{i}.xml.rels", _rels_xml([
                ("rId1", "slide", f"../slides/slide{i}.xml")]))
        for key, data in media.items():
            z.writestr(f"ppt/media/{key}", data)
    return out_path


# ==========================================================================
# Template backend: python-pptx against an organizer template / starting deck
# ==========================================================================
def _import_pptx():
    try:
        import pptx  # noqa: F401
        return True
    except Exception:
        return False


def _pick_layout(prs, kind):
    layouts = list(prs.slide_layouts)
    def find(*keys, exclude=()):
        for l in layouts:
            nm = (l.name or "").lower()
            if any(k in nm for k in keys) and not any(e in nm for e in exclude):
                return l
        return None
    if kind == "title":
        return find("title", exclude=("section",)) or layouts[0]
    if kind == "section" or kind == "backup":
        return find("section") or find("title", exclude=("section",)) or layouts[min(1, len(layouts) - 1)]
    lay = find("title and content") or find("content") or find("title and body")
    if lay:
        return lay
    for l in layouts:  # any layout with a title + a body/object placeholder
        types = set()
        for ph in l.placeholders:
            try:
                t = ph.placeholder_format.type
                if t is not None:
                    types.add(int(t))
            except Exception:
                pass
        if types & {0, 13} and types & {2, 7}:   # TITLE/CENTER_TITLE + BODY/OBJECT
            return l
    return find("blank") or layouts[-1]


def _fill_bullets(tf, bullets, font_pt=None, shrank=False):
    tf.clear()
    tf.word_wrap = True
    for i, b in enumerate(bullets):
        para = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
        run = para.add_run()
        run.text = b
        if shrank and font_pt:
            run.font.size = _pptx_util().Pt(font_pt)


def _pptx_util():
    from pptx import util
    return util


def _set_notes(slide, notes_text):
    slide.notes_slide.notes_text_frame.text = notes_text


def _stamp_footer(slide, prs, footer_text, page_n, report, sid):
    from pptx.util import Emu, Pt
    from pptx.enum.shapes import PP_PLACEHOLDER
    if not footer_text:
        return
    for ph in slide.placeholders:
        if ph.placeholder_format.type == PP_PLACEHOLDER.FOOTER:
            ph.text_frame.text = footer_text
            report["decisions"][-1]["actions"].append("footer: stamped into template footer placeholder")
            return
    tb = slide.shapes.add_textbox(Emu(int(0.55 * EMU)), Emu(prs.slide_height - int(0.37 * EMU)),
                                  Emu(prs.slide_width - int(1.1 * EMU)), Emu(int(0.3 * EMU)))
    r = tb.text_frame.paragraphs[0].add_run()
    r.text = footer_text
    r.font.size = Pt(FOOTER_FONT_PT)
    report["decisions"][-1]["actions"].append(
        "footer: no footer placeholder on slide; stamped small text box (theme untouched)")


def _fill_slide(slide, plan, prs, report):
    from pptx.util import Emu, Pt
    from pptx.enum.shapes import PP_PLACEHOLDER
    if slide.shapes.title is not None:
        slide.shapes.title.text_frame.text = plan["title"]
    body_ph, pic_ph = None, None
    for ph in slide.placeholders:
        t = ph.placeholder_format.type
        if t in (PP_PLACEHOLDER.BODY, PP_PLACEHOLDER.OBJECT) and body_ph is None:
            body_ph = ph
        elif t == PP_PLACEHOLDER.PICTURE and pic_ph is None:
            pic_ph = ph
    shrank = plan["font_pt"] != BODY_LADDER[0]
    if plan["bullets"] and body_ph is not None:
        _fill_bullets(body_ph.text_frame, plan["bullets"], plan["font_pt"], shrank)
    elif plan["bullets"]:
        tb = slide.shapes.add_textbox(Emu(int(0.55 * EMU)), Emu(int(1.6 * EMU)),
                                      Emu(prs.slide_width - int(1.1 * EMU)),
                                      Emu(prs.slide_height - int(2.2 * EMU)))
        _fill_bullets(tb.text_frame, plan["bullets"], plan["font_pt"], True)
        report["decisions"][-1]["actions"].append(
            "layout had no body placeholder; added plain text box (deviation recorded)")
    if plan["image_path"]:
        if pic_ph is not None:
            pic_ph.insert_picture(plan["image_path"])
        else:
            if body_ph is not None:
                l, t, w, h = body_ph.left, body_ph.top, body_ph.width, body_ph.height
            else:
                l, t = Emu(int(0.55 * EMU)), Emu(int(1.6 * EMU))
                w, h = Emu(prs.slide_width - int(1.1 * EMU)), Emu(prs.slide_height - int(2.2 * EMU))
            wpx, hpx, dpi = png_size(plan["image_path"])
            x, y, w2, h2 = fit_image_in_box(int(wpx / dpi * EMU), int(hpx / dpi * EMU),
                                            int(l), int(t), int(w), int(h))
            slide.shapes.add_picture(plan["image_path"], Emu(x), Emu(y), Emu(w2), Emu(h2))
    if plan["table"]:
        tb = plan["table"]
        rows, cols = len(tb["rows"]) + 1, len(tb["columns"])
        top = int(0.5 * prs.slide_height) if plan["bullets"] else int(1.6 * EMU)
        gf = slide.shapes.add_table(rows, cols, Emu(int(0.55 * EMU)), Emu(top),
                                    Emu(prs.slide_width - int(1.1 * EMU)),
                                    Emu(min(int(0.35 * EMU) * rows, int(3.2 * EMU))))
        for j, c in enumerate(tb["columns"]):
            gf.table.cell(0, j).text = str(c)
        for i, row in enumerate(tb["rows"], 1):
            for j, c in enumerate(row):
                gf.table.cell(i, j).text = str(c)
    _stamp_footer(slide, prs, plan["footer"], plan["n"], report, plan["id"])
    _set_notes(slide, plan["notes"])


def compile_template(plans, template_path, start_deck_path, out_path, report):
    from pptx import Presentation
    src = start_deck_path or template_path
    prs = Presentation(src)
    existing = list(prs.slides)
    if start_deck_path:
        # rewrite-in-order mode
        for i, plan in enumerate(plans):
            report["decisions"].append({"slide": plan["id"], "kind": plan["kind"],
                                        "actions": []})
            if i < len(existing):
                slide = existing[i]
                for shp in list(slide.shapes):
                    if not shp.is_placeholder:
                        shp._element.getparent().remove(shp._element)
                report["decisions"][-1]["actions"].append(
                    f"start-deck: rewrote existing slide {i + 1} in place")
                for ph in slide.placeholders:  # clear placeholders we do not fill
                    try:
                        ph.text_frame.clear()
                    except Exception:
                        pass
                _fill_slide(slide, plan, prs, report)
            else:
                slide = prs.slides.add_slide(_pick_layout(prs, plan["kind"]))
                report["decisions"][-1]["actions"].append(
                    f"start-deck: appended new slide {i + 1} from layout")
                _fill_slide(slide, plan, prs, report)
        for j in range(len(existing) - 1, len(plans) - 1, -1):
            sldIdLst = prs.slides._sldIdLst
            el = list(sldIdLst)[j]
            prs.part.drop_rel(el.get(f"{{{NS_R}}}id"))
            sldIdLst.remove(el)
            report["decisions"].append({"slide": f"leftover-{j + 1}", "kind": "removed",
                                        "actions": [f"start-deck: removed leftover slide {j + 1}"]})
    else:
        for j in range(len(existing) - 1, -1, -1):  # template sample slides are not content
            sldIdLst = prs.slides._sldIdLst
            el = list(sldIdLst)[j]
            prs.part.drop_rel(el.get(f"{{{NS_R}}}id"))
            sldIdLst.remove(el)
        if existing:
            report["warnings"].append(
                f"template contained {len(existing)} sample slide(s); removed before filling")
        for plan in plans:
            report["decisions"].append({"slide": plan["id"], "kind": plan["kind"],
                                        "actions": []})
            slide = prs.slides.add_slide(_pick_layout(prs, plan["kind"]))
            master_name = slide.slide_layout.slide_master.name or "(unnamed)"
            report["decisions"][-1]["actions"].append(
                f"layout: {slide.slide_layout.name!r} from template master {master_name!r}")
            _fill_slide(slide, plan, prs, report)
    os.makedirs(os.path.dirname(os.path.abspath(out_path)), exist_ok=True)
    prs.save(out_path)
    return out_path


# ==========================================================================
def main(argv=None):
    ap = argparse.ArgumentParser(description="Compile deck.spec.json into a .pptx deck.")
    ap.add_argument("--spec", default="deck.spec.json")
    ap.add_argument("--out", default="/app/output/deck.pptx")
    ap.add_argument("--template", default=None, help="organizer template .pptx")
    ap.add_argument("--start-deck", default=None, help="organizer starting deck .pptx to adapt")
    ap.add_argument("--report", default=None, help="compile_report.json path (default: <out>.compile_report.json)")
    ap.add_argument("--force-builtin", action="store_true", help="skip the template backend")
    args = ap.parse_args(argv)

    report = {"compiler": f"compile_deck.py {COMPILER_VERSION}",
              "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
              "spec": os.path.abspath(args.spec), "out": os.path.abspath(args.out),
              "backend": None, "backend_reason": None, "deviations": [],
              "decisions": [], "warnings": [], "errors": []}
    report_path = args.report or os.path.splitext(args.out)[0] + ".compile_report.json"

    try:
        with open(args.spec, "r", encoding="utf-8") as f:
            spec = json.load(f)
    except (OSError, json.JSONDecodeError) as e:
        print(f"compile_deck: FATAL cannot read spec: {e}", file=sys.stderr)
        return 2
    spec_dir = os.path.dirname(os.path.abspath(args.spec))

    have_pptx = _import_pptx()
    use_template = (not args.force_builtin) and have_pptx and \
        (args.template or args.start_deck)
    if use_template:
        report["backend"] = "template"
        report["backend_reason"] = ("python-pptx importable and organizer file provided; "
                                    "filling real layouts/placeholders of "
                                    + os.path.basename(args.start_deck or args.template))
    else:
        report["backend"] = "builtin"
        reasons = []
        if not have_pptx:
            reasons.append("python-pptx not importable")
        if not (args.template or args.start_deck):
            reasons.append("no organizer template/starting deck provided")
        report["backend_reason"] = "; ".join(reasons)
        if args.template or args.start_deck:
            report["deviations"].append(
                "organizer template was provided but python-pptx is unavailable; "
                "output uses the builtin plain 16:9 theme, NOT the organizer master/fonts")
        else:
            report["deviations"].append(
                "no organizer template; builtin plain 16:9 theme used "
                "(not the organizer's master, fonts, or footers)")

    plans = build_plans(spec, spec_dir, report)
    try:
        if use_template:
            compile_template(plans, args.template, args.start_deck, args.out, report)
        else:
            compile_builtin(plans, args.out, report)
    except Exception as e:
        report["errors"].append(f"build failed: {e}")
        with open(report_path, "w", encoding="utf-8") as f:
            json.dump(report, f, indent=2, ensure_ascii=False)
        print(f"compile_deck: FATAL build failed: {e}", file=sys.stderr)
        return 1

    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)
    print(f"compile_deck: OK backend={report['backend']} slides={len(plans)} "
          f"-> {args.out}\n  report: {report_path}")
    if report["deviations"]:
        print("  deviations: " + " | ".join(report["deviations"]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
