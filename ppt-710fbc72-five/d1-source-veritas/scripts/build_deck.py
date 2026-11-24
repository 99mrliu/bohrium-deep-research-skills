"""build_deck.py — build deck.pptx from the (gate-cleaned) slide plan.

Template-native: slides are added via prs.slide_layouts of the TEMPLATE file;
placeholders are filled by type (TITLE / BODY). If a usable placeholder is
missing, a textbox is added within the slide area and the fallback is recorded
in the build log. Only corpus-ledger figures are embedded, aspect ratio
preserved, never stretched. Speaker notes = plan notes + evidence refs.

Usage:
  python3 build_deck.py --plan plan.verified.json --template template.pptx \
      --out /app/output/deck.pptx --log /app/work/build_log.json
"""
from __future__ import annotations

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common  # noqa: E402

KIND_LAYOUT = {
    "title": ["Title Slide", "Title"],
    "background": ["Title and Content", "Title Only"],
    "method": ["Title and Content", "Two Content"],
    "results": ["Title and Content", "Two Content", "Comparison"],
    "discussion": ["Title and Content", "Title Only"],
    "conclusion": ["Title and Content", "Title Only"],
}


def _pick_layout(prs, slide_spec: dict, log_entry: dict):
    from pptx.enum.shapes import PP_PLACEHOLDER  # noqa: F401
    hint = (slide_spec.get("layout_hint") or "").strip().lower()
    kind = (slide_spec.get("kind") or "").strip().lower()
    layouts = list(prs.slide_layouts)
    if hint:
        for lay in layouts:
            if lay.name.lower() == hint:
                return lay
        log_entry.setdefault("notes", []).append(
            f"layout_hint '{hint}' not found in template; falling back")
    for cand in KIND_LAYOUT.get(kind, []) + ["Title and Content", "Title Only"]:
        for lay in layouts:
            if lay.name.lower() == cand.lower():
                return lay
    return layouts[1] if len(layouts) > 1 else layouts[0]


def _fill_title(slide, title: str, log_entry: dict):
    from pptx.util import Inches
    for ph in slide.placeholders:
        if ph.placeholder_format.idx == 0 or "title" in ph.name.lower():
            ph.text = title
            log_entry["title_via"] = f"placeholder '{ph.name}'"
            return True
    # fallback: textbox at top of slide area
    tb = slide.shapes.add_textbox(Inches(0.5), Inches(0.3),
                                  Inches(9), Inches(1.0))
    tb.text_frame.text = title
    log_entry["title_via"] = "textbox-fallback"
    log_entry.setdefault("fallbacks", []).append("title placeholder missing")
    return False


def _fill_body(slide, prs, bullets: list, claim: str, log_entry: dict):
    from pptx.enum.shapes import PP_PLACEHOLDER
    from pptx.util import Inches
    lines = ([claim] if claim else []) + list(bullets or [])
    body_ph = None
    for ph in slide.placeholders:
        pht = ph.placeholder_format.type
        if pht in (PP_PLACEHOLDER.BODY, PP_PLACEHOLDER.OBJECT,
                   PP_PLACEHOLDER.SUBTITLE):
            if ph.placeholder_format.idx != 0:
                body_ph = ph
                break
    if body_ph is not None and lines:
        tf = body_ph.text_frame
        tf.clear()
        for i, line in enumerate(lines):
            p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
            p.text = line
            p.level = 0
        log_entry["body_via"] = f"placeholder '{body_ph.name}'"
        return body_ph
    if lines:
        # fallback textbox within slide area (below title zone)
        w = prs.slide_width
        h = prs.slide_height
        tb = slide.shapes.add_textbox(
            int(w * 0.06), int(h * 0.22), int(w * 0.88), int(h * 0.66))
        tf = tb.text_frame
        tf.word_wrap = True
        for i, line in enumerate(lines):
            p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
            p.text = line
        log_entry["body_via"] = "textbox-fallback"
        log_entry.setdefault("fallbacks", []).append("body placeholder missing")
    return None


def _embed_figures(slide, prs, figures: list, log_entry: dict):
    """Add pictures aspect-ratio preserved, never stretched."""
    from PIL import Image
    w = int(prs.slide_width)
    h = int(prs.slide_height)
    n = len(figures)
    for i, fg in enumerate(figures):
        path = fg.get("path")
        if not path or not os.path.exists(path):
            log_entry.setdefault("fallbacks", []).append(
                f"figure missing at build time: {path}")
            continue
        with Image.open(path) as im:
            iw, ih = im.size
        # target box: right column if body exists, else centered; multi-figure
        # splits horizontally
        box_w = int(w * (0.42 if n == 1 else 0.42 / n))
        box_h = int(h * 0.55)
        scale = min(box_w / iw, box_h / ih)
        pic_w, pic_h = int(iw * scale), int(ih * scale)
        left = int(w * 0.55) + i * (box_w + int(w * 0.02))
        top = int(h * 0.25)
        slide.shapes.add_picture(path, left, top, width=pic_w, height=pic_h)
        log_entry.setdefault("figures_embedded", []).append({
            "ref": fg.get("ref"), "path": path,
            "native_px": [iw, ih], "placed_emu": [pic_w, pic_h],
            "aspect_preserved": True,
            "sha256": common.sha256_file(path)})


def build(plan: dict, template_path: str, out_path: str) -> dict:
    from pptx import Presentation

    prs = Presentation(template_path)
    log = {"template": os.path.abspath(template_path),
           "template_sha256": common.sha256_file(template_path),
           "preexisting_slides": len(prs.slides._sldIdLst),
           "layouts_available": [l.name for l in prs.slide_layouts],
           "slides": []}

    for sidx, spec in enumerate(plan.get("slides", [])):
        entry = {"slide": sidx, "kind": spec.get("kind"),
                 "title": spec.get("title", "")}
        layout = _pick_layout(prs, spec, entry)
        entry["layout_used"] = layout.name
        slide = prs.slides.add_slide(layout)
        _fill_title(slide, spec.get("title", ""), entry)
        body = _fill_body(slide, prs, spec.get("bullets", []),
                          spec.get("claim", ""), entry)
        if spec.get("figures"):
            if body is not None:
                # keep body text clear of the right-hand figure zone
                body.width = int(prs.slide_width * 0.5)
                entry.setdefault("notes", []).append(
                    "body width narrowed to 50% for figure zone")
            _embed_figures(slide, prs, spec["figures"], entry)
        # speaker notes = plan notes + evidence refs
        notes = spec.get("notes", "") or ""
        ev_lines = ["evidence: " + "; ".join(
            f"{e.get('type')}:{e.get('ref')}"
            for e in spec.get("evidence", []) or [])] if spec.get("evidence") else []
        notes_text = notes + ("\n" if notes and ev_lines else "") + "\n".join(ev_lines)
        if notes_text.strip():
            slide.notes_slide.notes_text_frame.text = notes_text
        entry["has_notes"] = bool(notes_text.strip())
        log["slides"].append(entry)

    os.makedirs(os.path.dirname(os.path.abspath(out_path)), exist_ok=True)
    prs.save(out_path)
    log["deck"] = os.path.abspath(out_path)
    log["deck_sha256"] = common.sha256_file(out_path)
    log["slide_count"] = len(log["slides"]) + log["preexisting_slides"]
    return log


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--plan", required=True)
    ap.add_argument("--template", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--log", required=True)
    args = ap.parse_args()
    plan = common.load_json(args.plan)
    if plan is None:
        print(f"[build_deck] ERROR: plan not found: {args.plan}")
        return 2
    log = build(plan, args.template, args.out)
    common.dump_json(log, args.log)
    print(f"[build_deck] slides={len(log['slides'])} "
          f"layouts={sorted({s['layout_used'] for s in log['slides']})}")
    print(f"[build_deck] deck -> {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
