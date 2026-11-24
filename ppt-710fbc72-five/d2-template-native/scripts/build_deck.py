#!/usr/bin/env python3
"""Build deck.pptx STRICTLY from the template's own masters/layouts.

Rules (see references/ooxml-inheritance.md):
  * The base PPTX (starting deck, else template) is opened as THE
    Presentation — slides are added only via its slide_layouts.
  * Pre-existing slides of a starting deck are deleted first (recorded).
  * Placeholders are filled by idx/type from the plan. No fonts, colors or
    theme attributes are ever set — everything inherits from the template.
  * If the chosen layout lacks a needed placeholder, fall back per the
    substitution table, or add a plain textbox inside the layout's content
    bounds and record the substitution — never a blank default look.
  * Images are placed aspect-preserved inside the content bounds.
  * Speaker notes come from plan.notes.

Usage:
    python3 build_deck.py --base BASE.pptx --plan slide_plan.json \
        --inventory template_inventory.json --out deck.pptx \
        --report build_report.json
"""
import argparse
import json
import os
import sys

EMU_PER_INCH = 914400

# Documented substitution order when a requested layout name is missing.
LAYOUT_FALLBACK_ORDER = ["Title and Content", "Title Only", "Blank"]


def load_json(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def layout_by_name(prs, name):
    for master in prs.slide_masters:
        for layout in master.slide_layouts:
            if layout.name == name:
                return layout
    return None


def inventory_layout(inventory, name):
    for lay in inventory.get("layouts", []):
        if lay["name"] == name:
            return lay
    return None


def content_bounds(inventory, layout_name, prs):
    """Content area for a layout: largest non-title placeholder, else a
    margin box under the title area. Returns (x, y, cx, cy) EMU."""
    lay = inventory_layout(inventory, layout_name)
    if lay:
        cands = [p for p in lay["placeholders"]
                 if p["idx"] != 0 and p["x"] is not None]
        if cands:
            big = max(cands, key=lambda p: (p["cx"] or 0) * (p["cy"] or 0))
            return big["x"], big["y"], big["cx"], big["cy"]
        title = next((p for p in lay["placeholders"]
                      if p["idx"] == 0 and p["y"] is not None), None)
        if title:
            y = title["y"] + (title["cy"] or 0) + int(0.2 * EMU_PER_INCH)
            m = int(0.5 * EMU_PER_INCH)
            return m, y, prs.slide_width - 2 * m, prs.slide_height - y - m
    m = int(0.5 * EMU_PER_INCH)
    return m, int(1.6 * EMU_PER_INCH), prs.slide_width - 2 * m, \
        prs.slide_height - int(2.1 * EMU_PER_INCH)


def fit_box(img_w, img_h, box_x, box_y, box_cx, box_cy):
    """Aspect-preserved fit of image into box, centered."""
    scale = min(box_cx / img_w, box_cy / img_h)
    w, h = int(img_w * scale), int(img_h * scale)
    x = box_x + (box_cx - w) // 2
    y = box_y + (box_cy - h) // 2
    return x, y, w, h


def delete_existing_slides(prs):
    """Remove every pre-existing slide (starting-deck cleanup)."""
    deleted = []
    sldIdLst = prs.slides._sldIdLst
    for sldId in list(sldIdLst):
        r_id = sldId.get(
            "{http://schemas.openxmlformats.org/officeDocument/2006/"
            "relationships}id")
        prs.part.drop_rel(r_id)
        sldIdLst.remove(sldId)
        deleted.append({"rId": r_id})
    return deleted


def pick_layout(prs, inventory, requested, substitutions, slide_no):
    layout = layout_by_name(prs, requested) if requested else None
    if layout is not None:
        return layout, requested, False
    legal = [l["name"] for l in inventory.get("layouts", [])]
    for cand in LAYOUT_FALLBACK_ORDER:
        if cand in legal:
            fallback = layout_by_name(prs, cand)
            substitutions.append({
                "slide": slide_no, "kind": "layout_fallback",
                "requested": requested, "used": cand,
                "reason": "requested layout not present in template",
            })
            return fallback, cand, True
    first = prs.slide_masters[0].slide_layouts[0]
    substitutions.append({
        "slide": slide_no, "kind": "layout_fallback",
        "requested": requested, "used": first.name,
        "reason": "no fallback layout found; using first template layout",
    })
    return first, first.name, True


def fill_title(slide, title, bounds, substitutions, slide_no):
    if slide.shapes.title is not None:
        slide.shapes.title.text_frame.text = title
        return "placeholder"
    if not title:
        return "none"
    x, y, cx, _ = bounds
    tb = slide.shapes.add_textbox(x, int(0.3 * EMU_PER_INCH), cx,
                                  int(1.0 * EMU_PER_INCH))
    tb.text_frame.text = title
    substitutions.append({
        "slide": slide_no, "kind": "title_textbox",
        "reason": "layout has no title placeholder; added plain textbox "
                  "inside layout bounds",
    })
    return "textbox"


def fill_body(slide, bullets, bounds, substitutions, slide_no,
              resize_to=None):
    """Fill bullets into the layout's body placeholder (or a recorded
    textbox substitution). `resize_to`=(x, cx) narrows the placeholder on
    this slide only (geometry override; inheritance by idx is untouched)."""
    if not bullets:
        return "none"
    body_ph = None
    for ph in slide.placeholders:
        if ph.placeholder_format.idx == 0:
            continue
        t = str(ph.placeholder_format.type)
        if any(k in t for k in ("BODY", "OBJECT", "SUBTITLE")):
            body_ph = ph
            break
    if body_ph is None:
        x, y, cx, cy = bounds
        tb = slide.shapes.add_textbox(x, y, cx, cy)
        tf = tb.text_frame
        substitutions.append({
            "slide": slide_no, "kind": "body_textbox",
            "reason": "layout lacks a body/object placeholder; added plain "
                      "textbox inside layout content bounds",
        })
    else:
        tf = body_ph.text_frame
        if resize_to is not None:
            x, cx = resize_to
            if body_ph.left is not None and body_ph.left != x:
                body_ph.left = x
            if body_ph.width is not None and body_ph.width != cx:
                body_ph.width = cx
    tf.word_wrap = True
    for i, item in enumerate(bullets):
        if isinstance(item, (list, tuple)):
            text, level = item[0], int(item[1])
        else:
            text, level = str(item), 0
        para = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
        para.text = text
        para.level = min(level, 4)
    return "placeholder" if body_ph is not None else "textbox"


def place_figures(slide, figures, bounds, slide_no, report):
    placed = []
    if not figures:
        return placed
    from PIL import Image
    bx, by, bcx, bcy = bounds
    n = len(figures)
    slot_w = bcx // n
    for i, fig in enumerate(figures):
        path = fig.get("path", "")
        if not path or not os.path.exists(path):
            report.setdefault("missing_figures", []).append(
                {"slide": slide_no, "ref": fig.get("ref"), "path": path})
            continue
        with Image.open(path) as im:
            iw, ih = im.size
        slot_x = bx + i * slot_w
        x, y, w, h = fit_box(iw, ih, slot_x, by, slot_w, bcy)
        pic = slide.shapes.add_picture(path, x, y, w, h)
        placed.append({"ref": fig.get("ref"), "path": path,
                       "x": x, "y": y, "cx": w, "cy": h,
                       "aspect_preserved": True,
                       "name": pic.name})
    return placed


def build(base_path, plan, inventory, out_path):
    from pptx import Presentation

    prs = Presentation(base_path)
    report = {"base": base_path,
              "n_preexisting_slides": len(prs.slides._sldIdLst),
              "deleted_slides": [], "substitutions": [],
              "geometry_overrides": [],
              "slides": [], "missing_figures": []}

    if report["n_preexisting_slides"]:
        report["deleted_slides"] = delete_existing_slides(prs)

    for no, spec in enumerate(plan.get("slides", []), start=1):
        layout, used_name, _ = pick_layout(
            prs, inventory, spec.get("layout"),
            report["substitutions"], no)
        slide = prs.slides.add_slide(layout)
        bounds = content_bounds(inventory, used_name, prs)

        entry = {"slide": no, "kind": spec.get("kind"),
                 "title": spec.get("title", ""),
                 "layout_requested": spec.get("layout"),
                 "layout_used": used_name,
                 "placeholders_filled": []}

        how = fill_title(slide, spec.get("title", ""), bounds,
                         report["substitutions"], no)
        if how == "placeholder":
            entry["placeholders_filled"].append({"idx": 0, "role": "title"})
        # When a slide carries BOTH bullets and figures, split the layout's
        # content bounds: body keeps the left ~55%, figures take the right
        # ~45% (aspect-preserved). Narrowing the body placeholder is a
        # slide-local geometry override, recorded in geometry_overrides;
        # placeholder inheritance (idx -> layout) is untouched.
        bullets = spec.get("bullets", [])
        figures = spec.get("figures", [])
        body_bounds, fig_bounds = bounds, bounds
        resize_to = None
        if bullets and figures:
            bx, by, bcx, bcy = bounds
            body_w = int(bcx * 0.55)
            gap = int(0.15 * EMU_PER_INCH)
            body_bounds = (bx, by, body_w, bcy)
            fig_bounds = (bx + body_w + gap, by, bcx - body_w - gap, bcy)
            resize_to = (bx, body_w)
            report["geometry_overrides"].append({
                "slide": no, "kind": "body_narrowed_for_figures",
                "reason": "slide has both bullets and figures; body "
                          "placeholder narrowed to left 55% of content "
                          "bounds, figures placed in right 45%",
                "body_bounds_emu": body_bounds,
                "figure_bounds_emu": fig_bounds,
            })

        how = fill_body(slide, bullets, body_bounds,
                        report["substitutions"], no, resize_to=resize_to)
        if how == "placeholder":
            idxs = [ph.placeholder_format.idx for ph in slide.placeholders
                    if ph.placeholder_format.idx != 0]
            entry["placeholders_filled"].append(
                {"idx": idxs[0] if idxs else None, "role": "body"})
        entry["figures"] = place_figures(
            slide, figures, fig_bounds, no, report)

        notes = spec.get("notes", "")
        if notes:
            slide.notes_slide.notes_text_frame.text = notes
        entry["notes_chars"] = len(notes)
        report["slides"].append(entry)

    prs.save(out_path)
    # sanity: re-open
    check = Presentation(out_path)
    report["n_slides_built"] = len(check.slides._sldIdLst)
    report["slide_size_emu"] = [check.slide_width, check.slide_height]
    return report


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--base", required=True,
                    help="starting deck (preferred) or template pptx")
    ap.add_argument("--plan", required=True, help="slide_plan.json")
    ap.add_argument("--inventory", required=True,
                    help="template_inventory.json from inspect_template.py")
    ap.add_argument("--out", required=True, help="output deck.pptx")
    ap.add_argument("--report", required=True, help="output build_report.json")
    args = ap.parse_args(argv)

    plan = load_json(args.plan)
    inventory = load_json(args.inventory)
    report = build(args.base, plan, inventory, args.out)
    with open(args.report, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    print(f"[build_deck] base={os.path.basename(args.base)} "
          f"deleted={len(report['deleted_slides'])} "
          f"built={report['n_slides_built']} "
          f"substitutions={len(report['substitutions'])} "
          f"missing_figures={len(report['missing_figures'])} -> {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
