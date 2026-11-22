#!/usr/bin/env python3
"""build_deck.py — Step 6 of contract-gate-slides.

Build output/presentation.pptx from work/plan.json strictly on the case
template (create mode) or starting deck (edit mode). Rules enforced here:
  - text goes into placeholders only; no run-level font names are ever set
    (theme fonts inherit; exported PDF keeps the template look);
  - figures are real crops from the paper PDF, inserted at native aspect;
  - every slide gets a 9 pt gray source line and speaker notes.

Edit mode: plan slides with "action": "keep" leave the corresponding
starting-deck slide untouched; "replace" (default for indices inside the
starting deck) rewrites title/bullets/notes; slides beyond the starting
deck length are appended with template layouts.
"""
import json, os, struct, sys

IN = os.environ.get("CASE_INPUT_DIR", "/input")
WORK = os.environ.get("CASE_WORK_DIR", "/app/work")
OUT = os.environ.get("CASE_OUTPUT_DIR", "/app/output")


def png_size(path):
    with open(path, "rb") as f:
        head = f.read(26)
    if head[:8] == b"\x89PNG\r\n\x1a\n":
        w, h = struct.unpack(">II", head[16:24])
        return w, h
    return 4, 3


def pick_layouts(prs):
    """Choose (title_layout, body_layout) preferring placeholder-rich layouts."""
    from pptx.enum.shapes import PP_PLACEHOLDER
    title_lay = body_lay = None
    for lay in prs.slide_layouts:
        phs = {ph.placeholder_format.type for ph in lay.placeholders}
        has_title = PP_PLACEHOLDER.TITLE in phs or PP_PLACEHOLDER.CENTER_TITLE in phs
        has_body = any(t in phs for t in (PP_PLACEHOLDER.BODY, PP_PLACEHOLDER.OBJECT))
        if body_lay is None and has_title and has_body:
            body_lay = lay
        if title_lay is None and PP_PLACEHOLDER.CENTER_TITLE in phs:
            title_lay = lay
    lays = list(prs.slide_layouts)
    if body_lay is None:
        body_lay = lays[1] if len(lays) > 1 else lays[0]
    if title_lay is None:
        title_lay = lays[0]
    return title_lay, body_lay


def set_bullets(ph, bullets):
    tf = ph.text_frame
    tf.clear()
    first = True
    for b in bullets:
        p = tf.paragraphs[0] if first else tf.add_paragraph()
        first = False
        p.text = b.get("text", "")
        # never set font name/size here: inherit from the layout


def add_source_line(slide, prs, text):
    from pptx.util import Inches, Pt
    from pptx.dml.color import RGBColor
    from pptx.enum.text import PP_ALIGN
    box = slide.shapes.add_textbox(Inches(0.35), prs.slide_height - Inches(0.42),
                                   prs.slide_width - Inches(0.7), Inches(0.32))
    tf = box.text_frame
    tf.word_wrap = True
    p = tf.paragraphs[0]
    p.alignment = PP_ALIGN.LEFT
    run = p.add_run()
    run.text = "来源：" + text
    # size+color only (no typeface) — allowed formatting for the source line
    run.font.size = Pt(9)
    run.font.color.rgb = RGBColor(0x88, 0x88, 0x88)


def place_figure(slide, prs, img_path, has_bullets):
    from pptx.util import Emu
    pw, ph = png_size(img_path)
    W, H = prs.slide_width, prs.slide_height
    if has_bullets:
        box_w = int(W * 0.44)
        box_h = int(H * 0.55)
        left = int(W * 0.53)
        top = int(H * 0.22)
    else:
        box_w = int(W * 0.7)
        box_h = int(H * 0.62)
        left = int(W * 0.15)
        top = int(H * 0.22)
    scale = min(box_w / pw, box_h / ph)
    w, h = int(pw * scale), int(ph * scale)
    slide.shapes.add_picture(img_path, left + (box_w - w) // 2,
                             top + (box_h - h) // 2, w, h)


def set_notes(slide, notes):
    slide.notes_slide.notes_text_frame.text = notes or ""


def fill_slide(slide, prs, spec, figs, out):
    title_lay = None
    # title
    ttl = None
    for ph in slide.placeholders:
        if ph.placeholder_format.type in (13, 15):  # TITLE / CENTER_TITLE
            ttl = ph
            break
    if ttl is None and slide.shapes.title is not None:
        ttl = slide.shapes.title
    if ttl is not None:
        ttl.text = spec.get("title", "")
    # bullets
    bullets = [b for b in (spec.get("bullets") or []) if b.get("text", "").strip()]
    body = None
    for ph in slide.placeholders:
        if ph.placeholder_format.type in (2, 7):  # BODY / OBJECT
            body = ph
            break
    if body is not None and bullets:
        set_bullets(body, bullets)
    # figure
    fid = spec.get("figure")
    if fid:
        f = next((x for x in figs if x["id"] == fid and x.get("crop")), None)
        if f:
            img = os.path.join(out, f["crop"])
            if os.path.exists(img):
                place_figure(slide, prs, img, has_bullets=bool(bullets))
    # source line
    anchors = [b.get("anchor", "") for b in bullets if b.get("anchor")]
    src_bits = []
    if anchors:
        src_bits.append("、".join(dict.fromkeys(anchors)).replace("p", "论文 p"))
    if fid:
        cap = next((x["caption"] for x in figs if x["id"] == fid), "")
        src_bits.append(f"{fid}: {cap[:60]}")
    add_source_line(slide, prs, "；".join(src_bits) or "任务材料")
    set_notes(slide, spec.get("notes"))


def main():
    from pptx import Presentation
    brief = json.load(open(os.path.join(WORK, "case_brief.json"), encoding="utf-8"))
    plan = json.load(open(os.path.join(WORK, "plan.json"), encoding="utf-8"))
    figs = json.load(open(os.path.join(WORK, "paper_figs.json"), encoding="utf-8"))
    slides = plan["slides"]
    os.makedirs(OUT, exist_ok=True)

    mode = brief.get("mode", "create")
    base = brief.get("template_pptx")
    if mode == "edit" and brief.get("starting_deck_pptx"):
        base = brief["starting_deck_pptx"]
    if base and os.path.exists(base):
        prs = Presentation(base)
    else:
        prs = Presentation()  # fallback recorded by survey assumptions
    title_lay, body_lay = pick_layouts(prs)

    n_existing = len(prs.slides._sldIdLst)
    if mode == "edit" and n_existing:
        # surgical adaptation of the starting deck
        for spec in slides:
            idx = spec["slide"] - 1
            action = spec.get("action") or ("replace" if idx < n_existing else "new")
            if action == "keep" and idx < n_existing:
                continue
            if idx < n_existing:
                slide = prs.slides[idx]
                fill_slide(slide, prs, spec, figs, OUT)
            else:
                lay = title_lay if spec["role"] == "title" else body_lay
                slide = prs.slides.add_slide(lay)
                fill_slide(slide, prs, spec, figs, OUT)
    else:
        # create mode: add all slides on template layouts
        for spec in slides:
            lay = title_lay if spec["role"] == "title" else body_lay
            slide = prs.slides.add_slide(lay)
            fill_slide(slide, prs, spec, figs, OUT)

    path = os.path.join(OUT, "presentation.pptx")
    prs.save(path)
    print(json.dumps({"saved": path, "slides": len(prs.slides._sldIdLst),
                      "mode": mode, "base": os.path.basename(base) if base else None},
                     ensure_ascii=False))


if __name__ == "__main__":
    main()
