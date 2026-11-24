#!/usr/bin/env python3
"""build_native.py -- build a natively-editable PPTX from deck.json.

Pillar 1 of ppt-native-edit-proofer:
  * python-pptx native shapes only (text boxes / real table shapes / pictures)
  * no hardcoded private fonts: font names are left unset so text inherits the
    template theme fonts
  * body text >= 14 pt, footnote-class text (footer/caption/table cells)
    >= 10 pt (configurable in deck.json meta)
  * speaker notes on every slide, per-slide evidence footer
  * numeric sidecar JSON for every figure

Usage:
    python3 build_native.py deck.json [--template t.pptx] --fig-dir figs/ \
        --fonts font_report.json --out presentation.pptx \
        --report build_report.json
Exit 2 if python-pptx is missing (honest failure, no fake pptx).
"""
import argparse
import json
import os
import sys

try:
    from pptx import Presentation
    from pptx.util import Inches, Pt
    from pptx.enum.text import PP_ALIGN
except ImportError:
    sys.stderr.write(
        "build_native: ERROR python-pptx not installed; cannot build a "
        "natively editable pptx (engine: none). Install python-pptx.\n")
    sys.exit(2)

FOOTNOTE_ROLES = ("footer", "caption", "table_cell")


def load_json(path, default=None):
    if path and os.path.isfile(path):
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)
    return default


def delete_all_slides(prs):
    """Remove pre-existing slides from a template presentation."""
    sldIdLst = prs.slides._sldIdLst
    for sldId in list(sldIdLst):
        rId = sldId.get(
            "{http://schemas.openxmlformats.org/officeDocument/2006/"
            "relationships}id")
        prs.part.drop_rel(rId)
        sldIdLst.remove(sldId)


TITLE_TYPES = {1, 3}        # TITLE, CENTER_TITLE
BODY_TYPES = {2, 7}         # BODY, OBJECT (real content areas)


def pick_layout(prs, want_body):
    """Pick a layout by name first, then by placeholder typing.

    want_body=True  -> prefer 'Title and Content' (title + BODY/OBJECT ph)
    want_body=False -> prefer 'Title Slide' (CENTER_TITLE + SUBTITLE)
    """
    def classify(layout):
        types = {ph.placeholder_format.type for ph in layout.placeholders}
        return bool(types & TITLE_TYPES), bool(types & BODY_TYPES)

    named = "content" if want_body else "title slide"
    for layout in prs.slide_layouts:
        t, b = classify(layout)
        if named in (layout.name or "").lower() and t and (b or not want_body):
            return layout
    fallback = None
    for layout in prs.slide_layouts:
        t, b = classify(layout)
        if want_body and t and b:
            return layout
        if not want_body and t and fallback is None:
            fallback = layout
    return fallback or prs.slide_layouts[0]


def remove_unused_placeholders(slide, keep_ids):
    for ph in list(slide.placeholders):
        if ph.placeholder_format.idx not in keep_ids:
            ph._element.getparent().remove(ph._element)


def set_runs(para, text, size_pt, bold=False):
    run = para.add_run()
    run.text = text
    run.font.size = Pt(size_pt)      # font name unset -> theme font inherited
    run.font.bold = bold
    return run


def add_textbox(slide, left, top, width, height, name):
    tb = slide.shapes.add_textbox(left, top, width, height)
    tb.name = name
    tb.text_frame.word_wrap = True
    return tb


def evidence_footer(slide, slide_w, slide_h, footer_text, foot_pt):
    tb = add_textbox(slide, Inches(0.3), slide_h - Inches(0.42),
                     slide_w - Inches(0.6), Inches(0.36), "EvidenceFooter")
    p = tb.text_frame.paragraphs[0]
    set_runs(p, footer_text, foot_pt)
    return tb


def add_notes(slide, notes):
    if notes:
        slide.notes_slide.notes_text_frame.text = notes


def footer_line(slide_def, idx):
    srcs = []
    for b in slide_def.get("bullets", []):
        if isinstance(b, dict) and b.get("source"):
            s = b["source"]
            srcs.append("%s %s" % (s.get("ref", "?"), s.get("locator", "")))
    for ev in slide_def.get("evidence", []):
        srcs.append("%s %s" % (ev.get("ref", "?"), ev.get("locator", "")))
    tag = " | sources: " + "; ".join(srcs) if srcs else ""
    return "slide %d | synthetic demo, fictional data%s" % (idx, tag)


def build(deck, template, fig_dir, out_path):
    prs = Presentation(template) if template and os.path.isfile(template) \
        else Presentation()
    if template and os.path.isfile(template):
        delete_all_slides(prs)
    meta = deck.get("meta", {})
    body_pt = float(meta.get("body_pt_min", 14))
    foot_pt = float(meta.get("footnote_pt_min", 10))
    title_pt = float(meta.get("title_pt", 28))
    sw, sh = prs.slide_width, prs.slide_height
    title_layout = pick_layout(prs, want_body=False)
    body_layout = pick_layout(prs, want_body=True)

    stats = {"slides": 0, "tables": 0, "pictures": 0, "textboxes": 0,
             "notes": 0, "footers": 0, "sidecars": [],
             "min_body_pt_seen": None, "min_foot_pt_seen": None}

    def track(size_pt, role):
        key = ("min_foot_pt_seen" if role in FOOTNOTE_ROLES
               else "min_body_pt_seen")
        cur = stats[key]
        stats[key] = size_pt if cur is None else min(cur, size_pt)

    for idx, sd in enumerate(deck.get("slides", []), start=1):
        role = sd.get("role", "bullets")
        layout = title_layout if role == "title" else body_layout
        slide = prs.slides.add_slide(layout)

        # --- title (placeholder idx 0 when present) ---
        keep = set()
        title_txt = sd.get("title", "")
        if slide.shapes.title is not None:
            slide.shapes.title.text_frame.clear()
            set_runs(slide.shapes.title.text_frame.paragraphs[0],
                     title_txt, title_pt if role == "title" else
                     float(sd.get("title_pt", 20)), bold=True)
            track(title_pt if role == "title" else 20, "title")
            keep.add(0)
        else:
            tb = add_textbox(slide, Inches(0.4), Inches(0.25),
                             sw - Inches(0.8), Inches(0.9), "TitleBox")
            set_runs(tb.text_frame.paragraphs[0], title_txt, title_pt,
                     bold=True)
            track(title_pt, "title")
            stats["textboxes"] += 1

        # --- subtitle (title slide) ---
        if role == "title":
            sub = sd.get("subtitle", "")
            body_ph = next((ph for ph in slide.placeholders
                            if ph.placeholder_format.type == 4), None)  # SUBTITLE
            if body_ph is not None:
                body_ph.text_frame.clear()
                set_runs(body_ph.text_frame.paragraphs[0], sub, 16)
                track(16, "body")
                keep.add(body_ph.placeholder_format.idx)
            elif sub:
                tb = add_textbox(slide, Inches(0.4), Inches(2.2),
                                 sw - Inches(0.8), Inches(1.0), "SubtitleBox")
                set_runs(tb.text_frame.paragraphs[0], sub, 16)
                track(16, "body")
                stats["textboxes"] += 1

        # --- figure (native picture + numeric sidecar) ---
        # placed before bullets so bullet box top can be computed dynamically
        content_bottom = Inches(1.3)   # running lower edge of placed content
        fig = sd.get("figure")
        if fig:
            path = os.path.join(fig_dir, fig["file"])
            if not os.path.isfile(path):
                raise FileNotFoundError("figure missing: %s" % path)
            pic_w = Inches(float(fig.get("width_in", 4.8)))
            pic = slide.shapes.add_picture(
                path, int((sw - pic_w) / 2), Inches(1.35), width=pic_w)
            pic.name = "Figure:%s" % fig["file"]
            stats["pictures"] += 1
            content_bottom = pic.top + pic.height
            if fig.get("caption"):
                tb = add_textbox(slide, Inches(0.4),
                                 content_bottom + Inches(0.05),
                                 sw - Inches(0.8), Inches(0.35),
                                 "FigureCaption")
                set_runs(tb.text_frame.paragraphs[0], fig["caption"],
                         float(fig.get("caption_pt", max(foot_pt, 11))))
                track(float(fig.get("caption_pt", max(foot_pt, 11))),
                      "caption")
                stats["textboxes"] += 1
                content_bottom += Inches(0.45)
            sidecar = fig.get("sidecar")
            if sidecar:
                dst = os.path.join(os.path.dirname(os.path.abspath(out_path)),
                                   os.path.basename(sidecar))
                with open(os.path.join(fig_dir, sidecar),
                          encoding="utf-8") as fh:
                    data = json.load(fh)
                with open(dst, "w", encoding="utf-8") as fh:
                    json.dump(data, fh, ensure_ascii=False, indent=2)
                stats["sidecars"].append(os.path.basename(dst))

        # --- real native table shape ---
        tbl = sd.get("table")
        if tbl:
            cols = tbl["columns"]
            rows = tbl["rows"]
            cell_pt = float(tbl.get("cell_pt", max(foot_pt, 12)))
            if tbl.get("caption"):
                tb = add_textbox(slide, Inches(0.6), Inches(1.25),
                                 sw - Inches(1.2), Inches(0.35),
                                 "TableCaption")
                set_runs(tb.text_frame.paragraphs[0], tbl["caption"],
                         float(tbl.get("caption_pt", max(foot_pt, 11))))
                track(float(tbl.get("caption_pt", max(foot_pt, 11))),
                      "caption")
                stats["textboxes"] += 1
            gf = slide.shapes.add_table(
                len(rows) + 1, len(cols), Inches(0.6), Inches(1.7),
                sw - Inches(1.2), Inches(0.4 * (len(rows) + 1)))
            gf.name = "NativeTable"
            table = gf.table
            for c, name in enumerate(cols):
                cell = table.cell(0, c)
                cell.text_frame.clear()
                set_runs(cell.text_frame.paragraphs[0], str(name), cell_pt,
                         bold=True)
            for r, row in enumerate(rows, start=1):
                for c, val in enumerate(row):
                    cell = table.cell(r, c)
                    cell.text_frame.clear()
                    set_runs(cell.text_frame.paragraphs[0], str(val), cell_pt)
            track(cell_pt, "table_cell")
            stats["tables"] += 1
            content_bottom = gf.top + gf.height

        # --- bullets ---
        bullets = sd.get("bullets", [])
        if bullets:
            body_ph = next((ph for ph in slide.placeholders
                            if ph.placeholder_format.type in BODY_TYPES),
                           None)
            tf = None
            if body_ph is not None and role not in ("title", "figure",
                                                    "table"):
                tf = body_ph.text_frame
                tf.clear()
                tf.word_wrap = True
                keep.add(body_ph.placeholder_format.idx)
            else:
                top = content_bottom + Inches(0.15)
                if role not in ("figure", "table"):
                    top = Inches(1.3)
                tb = add_textbox(slide, Inches(0.4), top, sw - Inches(0.8),
                                 sh - top - Inches(0.55), "BulletBox")
                tf = tb.text_frame
                stats["textboxes"] += 1
            for j, b in enumerate(bullets):
                if isinstance(b, dict):
                    text, size = b.get("text", ""), float(b.get("size_pt",
                                                                 body_pt))
                else:
                    text, size = str(b), body_pt
                p = tf.paragraphs[0] if j == 0 else tf.add_paragraph()
                set_runs(p, "- " + text, size)
                track(size, "body")

        # --- evidence listing slide ---
        evs = sd.get("evidence")
        if evs:
            tb = add_textbox(slide, Inches(0.4), Inches(1.3),
                             sw - Inches(0.8), sh - Inches(2.0),
                             "EvidenceList")
            tf = tb.text_frame
            for j, ev in enumerate(evs):
                p = tf.paragraphs[0] if j == 0 else tf.add_paragraph()
                set_runs(p, "[s%s] %s %s: \"%s\""
                         % (ev.get("slide", "?"), ev.get("ref", "?"),
                            ev.get("locator", ""), ev.get("quote", "")),
                         float(ev.get("size_pt", body_pt)))
                track(float(ev.get("size_pt", body_pt)), "body")
            stats["textboxes"] += 1

        remove_unused_placeholders(slide, keep)
        evidence_footer(slide, sw, sh,
                        sd.get("footer") or footer_line(sd, idx), foot_pt)
        track(foot_pt, "footer")
        stats["footers"] += 1
        add_notes(slide, sd.get("notes", ""))
        if sd.get("notes"):
            stats["notes"] += 1
        stats["slides"] += 1

    os.makedirs(os.path.dirname(os.path.abspath(out_path)), exist_ok=True)
    prs.save(out_path)
    return stats, len(prs.slides.__iter__.__self__._sldIdLst)


def main():
    ap = argparse.ArgumentParser(description="Build natively-editable pptx "
                                     "from deck.json (python-pptx).")
    ap.add_argument("deck")
    ap.add_argument("--template", default=None)
    ap.add_argument("--fig-dir", default=".")
    ap.add_argument("--fonts", default=None, help="font_report.json (advisory)")
    ap.add_argument("--out", required=True)
    ap.add_argument("--report", required=True)
    args = ap.parse_args()

    with open(args.deck, encoding="utf-8") as fh:
        deck = json.load(fh)
    fonts = load_json(args.fonts, default={}) or {}

    stats, nslides = build(deck, args.template, args.fig_dir, args.out)
    report = {
        "engine": "python-pptx",
        "out": os.path.abspath(args.out),
        "template_used": bool(args.template and os.path.isfile(args.template)),
        "slide_count": nslides,
        "font_policy": "theme-inherited (no explicit font names)",
        "font_probe_suggestion": fonts.get("suggested_body_font"),
        "stats": stats,
        "size_rules": {
            "body_pt_min": deck.get("meta", {}).get("body_pt_min", 14),
            "footnote_pt_min": deck.get("meta", {}).get("footnote_pt_min", 10),
        },
    }
    with open(args.report, "w", encoding="utf-8") as fh:
        json.dump(report, fh, ensure_ascii=False, indent=2)
    print("build_native: slides=%d tables=%d pictures=%d notes=%d -> %s"
          % (nslides, stats["tables"], stats["pictures"], stats["notes"],
             args.out))
    return 0


if __name__ == "__main__":
    sys.exit(main())
