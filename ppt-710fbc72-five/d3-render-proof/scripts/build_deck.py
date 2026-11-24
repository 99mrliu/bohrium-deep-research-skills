#!/usr/bin/env python3
"""build_deck.py — 从 slide_plan.json + template.pptx 构建 deck.pptx。

刻意保持简单：本 bundle 的智能在下游（render_pipeline + fix_loop）。
- 按模板真实版式填占位符；占位符缺失时用 textbox 兜底并记录。
- 图片等比缩放放入内容区，绝不拉伸。
- 每页写讲稿备注。
- 输出 build_log.json：逐页记录版式、字号、图片期望位置（页面分数坐标），
  供 render_pipeline 的像素级 QA 与 fix_loop 的定点修复使用。
"""
import argparse
import json
import os

from pptx import Presentation
from pptx.util import Emu, Inches, Pt

DEFAULT_BODY_PT = 18
TITLE_PT = 28
FONT_LADDER = [20, 18, 16, 14, 12]  # 文档化阶梯；硬下限 10pt（见 references/render-qa.md）
FLOOR_PT = 10

KIND_TO_LAYOUT = {
    "title": ["Title Slide", "Title"],
    "background": ["Title and Content"],
    "method": ["Title and Content"],
    "results": ["Title and Content"],
    "discussion": ["Title and Content"],
    "conclusion": ["Title and Content"],
    "section": ["Section Header"],
}


def find_layout(prs, kind):
    names = KIND_TO_LAYOUT.get(kind, ["Title and Content"])
    for name in names:
        for lay in prs.slide_layouts:
            if lay.name == name:
                return lay
    # 兜底：任何带正文占位符的版式
    for lay in prs.slide_layouts:
        if any(ph.placeholder_format.idx not in (0, None) for ph in lay.placeholders):
            return lay
    return prs.slide_layouts[0]


def _set_text_frame(tf, bullets, body_pt):
    tf.word_wrap = True
    for i, b in enumerate(bullets):
        p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
        p.text = str(b)
        for run in p.runs:
            run.font.size = Pt(body_pt)


def _fit_image_box(img_w_px, img_h_px, box):
    """等比缩放图片到 box（EMU 四元组），返回 (left, top, width, height)。"""
    bl, bt, bw, bh = box
    if img_w_px <= 0 or img_h_px <= 0:
        return bl, bt, bw, bh
    scale = min(bw / img_w_px, bh / img_h_px)
    w, h = int(img_w_px * scale), int(img_h_px * scale)
    return bl + (bw - w) // 2, bt + (bh - h) // 2, w, h


def _image_size(path):
    try:
        from PIL import Image
        with Image.open(path) as im:
            return im.size
    except Exception:
        return 1280, 720  # 无法读取时按 16:9 假设，QA 会兜底校验


def build(plan_path, template_path, out_pptx, log_path):
    with open(plan_path, encoding="utf-8") as f:
        plan = json.load(f)
    prs = Presentation(template_path)
    sw, sh = prs.slide_width, prs.slide_height

    # 模板自带示例页：移除，只保留母版/版式（继承关系真实保留）。
    sldIdLst = prs.slides._sldIdLst
    for sldId in list(sldIdLst):
        prs.part.drop_rel(sldId.rId)
        sldIdLst.remove(sldId)

    log = {"plan_path": plan_path, "template": template_path,
           "slide_size_emu": [int(sw), int(sh)], "pages": []}

    for idx, sl in enumerate(plan.get("slides", [])):
        kind = sl.get("kind", "background")
        layout = find_layout(prs, kind)
        slide = prs.slides.add_slide(layout)
        body_pt = int(sl.get("body_font_override", DEFAULT_BODY_PT))
        if body_pt < FLOOR_PT:
            body_pt = FLOOR_PT
        page_log = {"page": idx + 1, "plan_index": idx, "kind": kind,
                    "title": sl.get("title", ""), "layout": layout.name,
                    "body_font_pt": body_pt, "fallback_textbox": False,
                    "images": []}

        # 标题
        if slide.shapes.title is not None:
            slide.shapes.title.text = sl.get("title", "")
            for p in slide.shapes.title.text_frame.paragraphs:
                for run in p.runs:
                    run.font.size = Pt(TITLE_PT)
        # 正文占位符
        body_ph = None
        for ph in slide.placeholders:
            if ph.placeholder_format.idx != 0:
                body_ph = ph
                break
        bullets = sl.get("bullets", [])
        figures = sl.get("figures", [])
        if body_ph is not None:
            tf = body_ph.text_frame
            if bullets:
                _set_text_frame(tf, bullets, body_pt)
            elif not figures:
                tf.text = sl.get("claim", "")
            box = (body_ph.left, body_ph.top, body_ph.width, body_ph.height)
        else:
            # 占位符缺失 → textbox 兜底并记录
            page_log["fallback_textbox"] = True
            l, t = Inches(0.7), Inches(1.4)
            w, h = Emu(int(sw) - int(Inches(1.4))), Emu(int(sh) - int(Inches(2.0)))
            tb = slide.shapes.add_textbox(l, t, w, h)
            _set_text_frame(tb.text_frame, bullets or [sl.get("claim", "")], body_pt)
            box = (l, t, w, h)

        # 图片：等比缩放放入内容区（有正文时用内容区下 55%）
        if figures:
            bl, bt, bw, bh = (int(box[0]), int(box[1]), int(box[2]), int(box[3]))
            if bullets:
                bt = bl_top = bt + int(bh * 0.45)
                bh = int(bh * 0.55)
            n = len(figures)
            cell_w = bw // n
            for k, fig in enumerate(figures):
                path = fig.get("path", "")
                cell = (bl + k * cell_w, bt, cell_w, bh)
                iw, ih = _image_size(path)
                il, it, iw2, ih2 = _fit_image_box(iw, ih, cell)
                entry = {"ref": fig.get("ref", ""), "path": path,
                         "caption": fig.get("caption", ""),
                         "left_frac": il / int(sw), "top_frac": it / int(sh),
                         "width_frac": iw2 / int(sw), "height_frac": ih2 / int(sh),
                         "embedded": False}
                if path and os.path.exists(path):
                    slide.shapes.add_picture(path, il, it, iw2, ih2)
                    entry["embedded"] = True
                page_log["images"].append(entry)

        # 备注（讲稿 + 证据锚点）
        notes = slide.notes_slide.notes_text_frame
        ev = "; ".join(f"{e.get('type','?')}:{e.get('ref','')}" for e in sl.get("evidence", []))
        notes.text = (sl.get("notes", "") or "").strip()
        if ev:
            notes.text += ("\n\n[evidence] " + ev).strip()

        log["pages"].append(page_log)

    os.makedirs(os.path.dirname(os.path.abspath(out_pptx)), exist_ok=True)
    prs.save(out_pptx)
    with open(log_path, "w", encoding="utf-8") as f:
        json.dump(log, f, ensure_ascii=False, indent=2)
    return log


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--plan", required=True)
    ap.add_argument("--template", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--log", required=True)
    a = ap.parse_args()
    log = build(a.plan, a.template, a.out, a.log)
    print(f"[build_deck] {len(log['pages'])} slides -> {a.out}")


if __name__ == "__main__":
    main()
