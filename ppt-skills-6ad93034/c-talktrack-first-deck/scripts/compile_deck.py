#!/usr/bin/env python3
"""compile_deck.py — talktrack-first-deck step 4: derive slides from narration.

Compiles the linted talktrack.md into output/presentation.pptx on the case
template (or starting deck in edit mode): page title from the [Sn] header,
bullets from "- " lines (anchor suffixes become the source line, not slide
text), notes from the narration paragraphs, figure from {fig:id}. No font
names are ever set — template typography inherits untouched.

Also writes work/derived_map.json (slide -> seconds/anchors/figure) for
wrap_up.py.
"""
import json, os, re, struct

WORK = os.environ.get("CASE_WORK_DIR", "/app/work")
OUT = os.environ.get("CASE_OUTPUT_DIR", "/app/output")
ANCHOR_RE = re.compile(r"\(anchor\s+(p\d+|fig\d+|tab\d+)\)")


def png_dims(path):
    with open(path, "rb") as f:
        head = f.read(26)
    if head[:8] == b"\x89PNG\r\n\x1a\n":
        return struct.unpack(">II", head[16:24])
    return (4, 3)


def layouts(prs):
    from pptx.enum.shapes import PP_PLACEHOLDER
    t = b = None
    for lay in prs.slide_layouts:
        ks = {ph.placeholder_format.type for ph in lay.placeholders}
        if b is None and (PP_PLACEHOLDER.TITLE in ks or PP_PLACEHOLDER.CENTER_TITLE in ks) and \
           (PP_PLACEHOLDER.BODY in ks or PP_PLACEHOLDER.OBJECT in ks):
            b = lay
        if t is None and PP_PLACEHOLDER.CENTER_TITLE in ks:
            t = lay
    ls = list(prs.slide_layouts)
    return t or ls[0], b or (ls[1] if len(ls) > 1 else ls[0])


def source_line(slide, prs, anchors, figcap):
    from pptx.util import Inches, Pt
    from pptx.dml.color import RGBColor
    bits = []
    if anchors:
        bits.append("、".join(dict.fromkeys(anchors)))
    if figcap:
        bits.append(figcap[:70])
    box = slide.shapes.add_textbox(Inches(0.35), prs.slide_height - Inches(0.42),
                                   prs.slide_width - Inches(0.7), Inches(0.32))
    r = box.text_frame.paragraphs[0].add_run()
    r.text = "来源：" + ("；".join(bits) or "任务材料")
    r.font.size = Pt(9)
    r.font.color.rgb = RGBColor(0x88, 0x88, 0x88)


def main():
    from pptx import Presentation
    brief = json.load(open(os.path.join(WORK, "stage_brief.json"), encoding="utf-8"))
    budget = {b["slide"]: b for b in json.load(open(os.path.join(WORK, "time_budget.json"), encoding="utf-8"))}
    caps = {c["id"]: c for c in json.load(open(os.path.join(WORK, "paper_caps.json"), encoding="utf-8"))}
    import lint_track
    slides = lint_track.parse(os.path.join(WORK, "talktrack.md"))
    if not slides:
        print("talktrack.md 为空或不可解析")
        return

    base = brief.get("deck_base")
    prs = Presentation(base) if base and os.path.exists(base) else Presentation()
    t_lay, b_lay = layouts(prs)
    existing = len(prs.slides._sldIdLst)
    edit = brief.get("mode") == "edit" and existing > 0

    derived = []
    for spec in slides:
        sn = spec["slide"]
        if edit and sn <= existing:
            slide = prs.slides[sn - 1]
        else:
            lay = t_lay if budget.get(sn, {}).get("role") == "title" else b_lay
            slide = prs.slides.add_slide(lay)
        # title
        ttl = slide.shapes.title
        if ttl is None:
            for ph in slide.placeholders:
                if ph.placeholder_format.type in (13, 15):
                    ttl = ph
                    break
        if ttl is not None:
            ttl.text = spec["title"]
        # bullets (strip anchor suffix from slide text; collect for source line)
        anchors = []
        texts = []
        for bl in spec["bullets"]:
            m = ANCHOR_RE.search(bl)
            if m:
                anchors.append(m.group(1))
            texts.append(ANCHOR_RE.sub("", bl).strip())
        body = None
        for ph in slide.placeholders:
            if ph.placeholder_format.type in (2, 7):
                body = ph
                break
        if body is not None and texts:
            tf = body.text_frame
            tf.clear()
            for i, t in enumerate(texts):
                p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
                p.text = t
        # figure
        figcap = None
        if spec["fig"]:
            c = caps.get(spec["fig"])
            img = os.path.join(OUT, c["crop"]) if c and c.get("crop") else None
            if img and os.path.exists(img):
                pw, ph = png_dims(img)
                W, H = prs.slide_width, prs.slide_height
                has_tx = bool(texts)
                bw = int(W * (0.44 if has_tx else 0.7)); bh = int(H * 0.55)
                bl = int(W * (0.53 if has_tx else 0.15)); bt = int(H * 0.22)
                sc = min(bw / pw, bh / ph)
                w, h = int(pw * sc), int(ph * sc)
                slide.shapes.add_picture(img, bl + (bw - w) // 2, bt + (bh - h) // 2, w, h)
                figcap = f"{spec['fig']}: {c['caption']}"
        source_line(slide, prs, anchors, figcap)
        slide.notes_slide.notes_text_frame.text = " ".join(spec["paras"])
        derived.append({"slide": sn, "seconds": spec["seconds"],
                        "budget_seconds": budget.get(sn, {}).get("seconds"),
                        "role": budget.get(sn, {}).get("role"),
                        "title": spec["title"], "anchors": sorted(set(anchors)),
                        "figure": spec["fig"], "notes_chars": sum(len(p) for p in spec["paras"])})

    os.makedirs(OUT, exist_ok=True)
    prs.save(os.path.join(OUT, "presentation.pptx"))
    json.dump(derived, open(os.path.join(WORK, "derived_map.json"), "w"),
              ensure_ascii=False, indent=1)
    print(json.dumps({"slides": len(prs.slides._sldIdLst), "edit": edit},
                     ensure_ascii=False))


if __name__ == "__main__":
    import sys
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    main()
