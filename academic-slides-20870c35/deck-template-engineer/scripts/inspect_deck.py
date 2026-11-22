#!/usr/bin/env python3
"""Inspect a PPTX: slide size, masters, layouts, placeholders, theme fonts,
and an inventory of existing slides with their layout relationships.

Usage:
  python3 inspect_deck.py file.pptx --out inspect.json

Needs python-pptx. The report feeds layout mapping (references/template-forensics.md).
"""
import argparse
import json
import sys

PH_ATTRS = ("idx", "type")


def placeholder_info(ph):
    info = {"idx": ph.placeholder_format.idx,
            "type": str(ph.placeholder_format.type)}
    for attr in ("left", "top", "width", "height"):
        val = getattr(ph, attr, None)
        info[attr] = int(val) if val is not None else None
    return info


def theme_fonts(prs):
    fonts = {}
    try:
        master = prs.slide_masters[0]
        theme = master.part.part_related_by(
            "http://schemas.openxmlformats.org/officeDocument/2006/relationships/theme")
        from lxml import etree
        root = etree.fromstring(theme.blob)
        ns = {"a": "http://schemas.openxmlformats.org/drawingml/2006/main"}
        for tag, key in (("majorFont", "major"), ("minorFont", "minor")):
            node = root.find(f".//a:{tag}/a:latin", ns)
            if node is not None:
                fonts[key] = node.get("typeface")
    except Exception as exc:  # theme may be absent or non-standard
        fonts["error"] = f"theme not readable: {exc}"
    return fonts


def inspect(path):
    try:
        from pptx import Presentation
    except ImportError:
        sys.exit("python-pptx not available; record forensics as unverified")
    prs = Presentation(path)
    report = {
        "file": path,
        "slide_size_emu": [int(prs.slide_width), int(prs.slide_height)],
        "slide_count": len(prs.slides.__iter__.__self__._sldIdLst),
        "masters": [],
        "theme_fonts": theme_fonts(prs),
        "slides": [],
    }
    for m_idx, master in enumerate(prs.slide_masters):
        m_entry = {"index": m_idx,
                   "name": master.name or f"master-{m_idx}", "layouts": []}
        for l_idx, layout in enumerate(master.slide_layouts):
            m_entry["layouts"].append({
                "index": l_idx, "name": layout.name,
                "placeholders": [placeholder_info(ph) for ph in layout.placeholders]})
        report["masters"].append(m_entry)
    for s_idx, slide in enumerate(prs.slides, 1):
        layout = slide.slide_layout
        master_name = layout.slide_master.name or "?"
        texts = []
        pictures = 0
        empty_prompts = 0
        for shape in slide.shapes:
            if shape.shape_type == 13:  # PICTURE
                pictures += 1
            if shape.is_placeholder and shape.has_text_frame and not shape.text_frame.text.strip():
                empty_prompts += 1
            if shape.has_text_frame and shape.text_frame.text.strip():
                texts.append(shape.text_frame.text.strip().replace("\n", " / ")[:80])
        notes = ""
        if slide.has_notes_slide:
            notes = slide.notes_slide.notes_text_frame.text.strip()[:80]
        report["slides"].append({
            "index": s_idx, "layout": layout.name, "master": master_name,
            "shapes": len(slide.shapes), "pictures": pictures,
            "empty_placeholders": empty_prompts,
            "has_notes": bool(notes), "texts_preview": texts[:4]})
    return report


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("deck")
    ap.add_argument("--out", required=True)
    args = ap.parse_args()
    report = inspect(args.deck)
    with open(args.out, "w", encoding="utf-8") as fh:
        json.dump(report, fh, ensure_ascii=False, indent=1)
    layouts = sum(len(m["layouts"]) for m in report["masters"])
    print(f"inspected {args.deck}: {report['slide_count']} slides, "
          f"{len(report['masters'])} masters, {layouts} layouts -> {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
