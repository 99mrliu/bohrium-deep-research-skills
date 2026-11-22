#!/usr/bin/env python3
"""apply.py — opjournal-deck-surgeon step 3: replay the journal.

Replays work/journal.jsonl onto the frozen v000 base and writes
output/presentation.pptx. Snapshots are taken after every milestone batch
(work/versions/vNNN.pptx) so any earlier state can be restored by
re-applying a truncated journal. Also writes output/change_journal.md —
the human-readable change record (what changed, why, with anchors).

Determinism rule: replay is pure — same v000 + same journal => same deck.
"""
import json, os, struct

WORK = os.environ.get("CASE_WORK_DIR", "/app/work")
OUT = os.environ.get("CASE_OUTPUT_DIR", "/app/output")


def png_dims(path):
    with open(path, "rb") as f:
        head = f.read(26)
    if head[:8] == b"\x89PNG\r\n\x1a\n":
        return struct.unpack(">II", head[16:24])
    return (4, 3)


def layout_pair(prs):
    from pptx.enum.shapes import PP_PLACEHOLDER
    t_lay = b_lay = None
    for lay in prs.slide_layouts:
        kinds = {ph.placeholder_format.type for ph in lay.placeholders}
        has_t = PP_PLACEHOLDER.TITLE in kinds or PP_PLACEHOLDER.CENTER_TITLE in kinds
        has_b = PP_PLACEHOLDER.BODY in kinds or PP_PLACEHOLDER.OBJECT in kinds
        if b_lay is None and has_t and has_b:
            b_lay = lay
        if t_lay is None and PP_PLACEHOLDER.CENTER_TITLE in kinds:
            t_lay = lay
    lays = list(prs.slide_layouts)
    return t_lay or lays[0], b_lay or (lays[1] if len(lays) > 1 else lays[0])


def slide_ref(prs, n, t_lay, b_lay):
    """Slide by 1-based logical index; create trailing slides if needed."""
    while len(prs.slides._sldIdLst) < n:
        prs.slides.add_slide(b_lay)
    return prs.slides[n - 1]


def add_source_stamp(slide, prs, anchors, figcap=None):
    from pptx.util import Inches, Pt
    from pptx.dml.color import RGBColor
    bits = []
    if anchors:
        bits.append("、".join(dict.fromkeys(anchors)))
    if figcap:
        bits.append(figcap[:70])
    box = slide.shapes.add_textbox(Inches(0.35), prs.slide_height - Inches(0.42),
                                   prs.slide_width - Inches(0.7), Inches(0.32))
    run = box.text_frame.paragraphs[0].add_run()
    run.text = "来源：" + ("；".join(bits) or "任务材料")
    run.font.size = Pt(9)
    run.font.color.rgb = RGBColor(0x88, 0x88, 0x88)


def drop_shape(sp):
    sp._element.getparent().remove(sp._element)


def replay():
    from pptx import Presentation
    from pptx.util import Emu
    journal = []
    jp = os.path.join(WORK, "journal.jsonl")
    if os.path.exists(jp):
        for line in open(jp, encoding="utf-8"):
            line = line.strip()
            if line:
                journal.append(json.loads(line))
    caps = {}
    try:
        for c in json.load(open(os.path.join(WORK, "captions.json"), encoding="utf-8")):
            caps[c["id"]] = c
    except Exception:
        pass
    base = os.path.join(WORK, "versions", "v000_base.pptx")
    prs = Presentation(base)
    t_lay, b_lay = layout_pair(prs)

    src_anchors = {}   # slide -> anchors collected for the source stamp
    src_figcap = {}
    errors = []
    applied = 0
    for op in journal:
        kind = op.get("op")
        if kind == "init":
            continue
        try:
            if kind == "add_slide":
                lay = t_lay if op.get("layout") == "title" else b_lay
                slide = prs.slides.add_slide(lay)
                applied += 1
            elif kind == "remove_slide":
                n = op["slide"]
                lst = prs.slides._sldIdLst
                if n > len(lst):
                    raise IndexError(f"slide {n} 不存在")
                el = list(lst)[n - 1]
                lst.remove(el)
                applied += 1
            elif kind == "set_title":
                slide = slide_ref(prs, op["slide"], t_lay, b_lay)
                ttl = slide.shapes.title
                if ttl is None:
                    for ph in slide.placeholders:
                        if ph.placeholder_format.type in (13, 15):
                            ttl = ph
                            break
                if ttl is None:
                    raise ValueError("该页无标题占位符")
                ttl.text = op.get("text", "")
                applied += 1
            elif kind == "set_bullets":
                slide = slide_ref(prs, op["slide"], t_lay, b_lay)
                body = None
                for ph in slide.placeholders:
                    if ph.placeholder_format.type in (2, 7):
                        body = ph
                        break
                if body is None:
                    raise ValueError("该页无正文占位符")
                tf = body.text_frame
                tf.clear()
                for i, it in enumerate(op["items"]):
                    p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
                    p.text = it.get("text", "")
                src_anchors[op["slide"]] = [it.get("anchor") for it in op["items"] if it.get("anchor")]
                applied += 1
            elif kind == "set_notes":
                slide = slide_ref(prs, op["slide"], t_lay, b_lay)
                slide.notes_slide.notes_text_frame.text = op.get("text", "")
                applied += 1
            elif kind == "insert_figure":
                slide = slide_ref(prs, op["slide"], t_lay, b_lay)
                c = caps.get(op["fig"])
                img = os.path.join(OUT, c["crop"]) if c and c.get("crop") else None
                if not img or not os.path.exists(img):
                    raise ValueError(f"图 {op['fig']} 裁剪缺失")
                pw, ph = png_dims(img)
                W, H = prs.slide_width, prs.slide_height
                has_text = any(sh.has_text_frame and sh.text_frame.text.strip()
                               for sh in slide.shapes)
                bw = int(W * (0.44 if has_text else 0.7))
                bh = int(H * 0.55)
                bl = int(W * (0.53 if has_text else 0.15))
                bt = int(H * 0.22)
                sc = min(bw / pw, bh / ph)
                w, h = int(pw * sc), int(ph * sc)
                slide.shapes.add_picture(img, bl + (bw - w) // 2, bt + (bh - h) // 2, w, h)
                src_figcap[op["slide"]] = f"{op['fig']}: {c['caption']}"
                applied += 1
            elif kind == "replace_text":
                slide = slide_ref(prs, op["slide"], t_lay, b_lay)
                hit = False
                for sh in slide.shapes:
                    if not sh.has_text_frame:
                        continue
                    for p in sh.text_frame.paragraphs:
                        for r in p.runs:
                            if op["find"] in r.text:
                                r.text = r.text.replace(op["find"], op.get("by", ""))
                                hit = True
                if not hit:
                    raise ValueError(f"未找到文本 '{op['find'][:30]}'")
                applied += 1
        except Exception as e:
            errors.append({"seq": op.get("_seq"), "op": kind, "error": str(e)})

    # source stamps on every slide (contract: per-page source line)
    for n in range(1, len(prs.slides._sldIdLst) + 1):
        add_source_stamp(prs.slides[n - 1], prs, src_anchors.get(n, []),
                         src_figcap.get(n))

    os.makedirs(OUT, exist_ok=True)
    out_pptx = os.path.join(OUT, "presentation.pptx")
    prs.save(out_pptx)
    # milestone snapshot
    snaps = sorted(f for f in os.listdir(os.path.join(WORK, "versions")) if f.endswith(".pptx"))
    next_v = f"v{len(snaps):03d}.pptx"
    prs.save(os.path.join(WORK, "versions", next_v))

    # human-readable change journal
    lines = ["# 修改记录（change journal）",
             f"底稿: v000_base.pptx → 成稿: presentation.pptx",
             f"应用操作 {applied} 项，失败 {len(errors)} 项\n",
             "| # | 操作 | 页 | 理由 |", "|-|-|-|-|"]
    for op in journal:
        if op["op"] == "init":
            continue
        detail = op.get("text") or op.get("fig") or \
            "; ".join(i.get("text", "")[:24] for i in op.get("items", [])) or ""
        lines.append(f"| {op.get('_seq','-')} | {op['op']} | {op.get('slide','-')} | "
                     f"{op.get('why','')}（{str(detail)[:40]}） |")
    if errors:
        lines.append("\n## 应用失败（未入稿）")
        for e in errors:
            lines.append(f"- #{e['seq']} {e['op']}: {e['error']}")
    open(os.path.join(OUT, "change_journal.md"), "w", encoding="utf-8").write("\n".join(lines))
    print(json.dumps({"applied": applied, "errors": errors,
                      "slides": len(prs.slides._sldIdLst), "snapshot": next_v},
                     ensure_ascii=False))


if __name__ == "__main__":
    replay()
