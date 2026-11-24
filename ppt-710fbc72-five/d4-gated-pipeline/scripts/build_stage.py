#!/usr/bin/env python3
"""build_stage.py — S6 构建 deck.pptx。

从模板真实继承：以模板文件为底打开 Presentation，按 plan 逐页 add_slide(模板版式)，
填充标题/正文占位符；占位符缺失时以 textbox 兜底并如实记录；图片等比缩放
（contain-fit 到右栏）；讲稿写入 notes。产出：
  /app/output/deck.pptx
  /app/work/build_report.json （每页版式/占位符命中/兜底/字号阶梯记录）
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from stage_machine import StageFailure, now_iso, read_json, write_json, sha256_file

KIND_TO_LAYOUT = {
    "title": "Title Slide",
    "background": "Title and Content",
    "method": "Title and Content",
    "results": "Title and Content",
    "discussion": "Title and Content",
    "conclusion": "Title and Content",
}


def _body_font_size(total_chars: int) -> int:
    """可解释的字号阶梯：内容越多字号越小，但下限 14pt 保证可读。"""
    if total_chars <= 300:
        return 18
    if total_chars <= 600:
        return 16
    return 14


def _find_placeholder(slide, idx=0, want_body=False):
    for ph in slide.placeholders:
        fmt = ph.placeholder_format
        if want_body and fmt.idx != 0:
            return ph
        if not want_body and fmt.idx == 0:
            return ph
    return None


def run(ctx) -> list:
    plan_path = os.path.join(ctx.work, "slide_plan.json")
    tpl_report_path = os.path.join(ctx.work, "template_report.json")
    plan = read_json(plan_path)
    tpl_report = read_json(tpl_report_path)
    if not plan or not tpl_report:
        raise StageFailure("缺少 slide_plan.json 或 template_report.json",
                           hint=ctx.default_resume_cmd())
    template = tpl_report["template"]
    if not os.path.isfile(template):
        raise StageFailure(f"模板文件已不存在: {template}",
                           hint=f"恢复模板到原路径后 {ctx.default_resume_cmd()}")
    try:
        from pptx import Presentation
        from pptx.util import Pt, Emu
    except ImportError:
        raise StageFailure("缺少 python-pptx", hint="pip install python-pptx 后重跑")
    try:
        from PIL import Image
    except ImportError:
        Image = None

    prs = Presentation(template)
    W, H = int(prs.slide_width), int(prs.slide_height)
    # 模板若自带旧页，移除（如实记录数量），保证成册页页出自本流水线
    existing = list(prs.slides._sldIdLst)
    n_removed = len(existing)
    for sld in existing:
        prs.slides._sldIdLst.remove(sld)

    layout_by_name = {lo.name: lo for lo in prs.slide_layouts}
    layout_names = list(layout_by_name.keys())

    def resolve_layout(slide_spec):
        hint = slide_spec.get("layout_hint")
        if hint in layout_by_name:
            return layout_by_name[hint], hint, "hint"
        mapped = KIND_TO_LAYOUT.get(slide_spec.get("kind"))
        if mapped in layout_by_name:
            return layout_by_name[mapped], mapped, "kind-map"
        # 兜底：第一个带正文占位符的版式；再不行用第一个版式
        for lo in prs.slide_layouts:
            if any(ph.placeholder_format.idx != 0 for ph in lo.placeholders):
                return lo, lo.name, "fallback-body-layout"
        return prs.slide_layouts[0], prs.slide_layouts[0].name, "fallback-first-layout"

    slides_report, fallbacks = [], []
    for i, spec in enumerate(plan.get("slides", [])):
        n = i + 1
        lo, lname, how = resolve_layout(spec)
        slide = prs.slides.add_slide(lo)
        rep = {"slide": n, "kind": spec.get("kind"), "title": spec.get("title"),
               "layout": lname, "layout_resolved_by": how,
               "n_evidence": len(spec.get("evidence") or []),
               "n_figures": len(spec.get("figures") or [])}

        title_text = str(spec.get("title") or "")
        title_ph = _find_placeholder(slide, idx=0)
        if title_ph is not None:
            title_ph.text = title_text
            if len(title_text) > 44:
                for para in title_ph.text_frame.paragraphs:
                    for r in para.runs:
                        r.font.size = Pt(24)
                rep["title_shrunk"] = True
            rep["title_via"] = "placeholder"
        else:
            tb = slide.shapes.add_textbox(Emu(int(0.06 * W)), Emu(int(0.05 * H)),
                                          Emu(int(0.88 * W)), Emu(int(0.12 * H)))
            tb.text_frame.text = title_text
            rep["title_via"] = "textbox-fallback"
            fallbacks.append({"slide": n, "what": "title placeholder", "action": "added textbox"})

        bullets = [str(b) for b in (spec.get("bullets") or [])]
        total_chars = sum(len(b) for b in bullets)
        figures = spec.get("figures") or []
        if spec.get("kind") == "title":
            sub = _find_placeholder(slide, want_body=True)
            subtitle = "；".join(x for x in [spec.get("claim") or "",
                                             f"听众: {plan.get('audience', '')}",
                                             f"时长: {plan.get('duration_min', '')} 分钟"] if x)
            if sub is not None:
                sub.text = subtitle
                rep["body_via"] = "subtitle-placeholder"
            elif subtitle:
                tb = slide.shapes.add_textbox(Emu(int(0.10 * W)), Emu(int(0.55 * H)),
                                              Emu(int(0.80 * W)), Emu(int(0.20 * H)))
                tb.text_frame.text = subtitle
                rep["body_via"] = "textbox-fallback"
                fallbacks.append({"slide": n, "what": "subtitle placeholder", "action": "added textbox"})
            else:
                rep["body_via"] = "none"
        else:
            body = _find_placeholder(slide, want_body=True)
            size = _body_font_size(total_chars)
            rep["body_font_pt"] = size
            if body is not None:
                tf = body.text_frame
                tf.word_wrap = True
                tf.clear()
                for k, b in enumerate(bullets):
                    p = tf.paragraphs[0] if k == 0 else tf.add_paragraph()
                    p.text = b
                    p.level = 0
                    for r in p.runs:
                        r.font.size = Pt(size)
                if figures:
                    body.width = Emu(int(0.52 * W))  # 给右栏图留位
                rep["body_via"] = "placeholder"
            elif bullets:
                tb = slide.shapes.add_textbox(Emu(int(0.06 * W)), Emu(int(0.18 * H)),
                                              Emu(int((0.52 if figures else 0.88) * W)),
                                              Emu(int(0.72 * H)))
                tf = tb.text_frame
                tf.word_wrap = True
                for k, b in enumerate(bullets):
                    p = tf.paragraphs[0] if k == 0 else tf.add_paragraph()
                    p.text = b
                    for r in p.runs:
                        r.font.size = Pt(size)
                rep["body_via"] = "textbox-fallback"
                fallbacks.append({"slide": n, "what": "body placeholder", "action": "added textbox"})
            else:
                rep["body_via"] = "none"

        # 图片：等比 contain-fit 到右栏
        placed = []
        if figures:
            n_fig = len(figures)
            for k, fg in enumerate(figures):
                path = fg.get("path")
                entry = {"ref": fg.get("ref"), "path": path, "placed": False}
                if not path or not os.path.isfile(path):
                    entry["reason"] = "file-missing"
                    fallbacks.append({"slide": n, "what": f"figure {fg.get('ref')}",
                                      "action": "skipped (file missing)"})
                    placed.append(entry)
                    continue
                box_l = int(0.56 * W)
                box_t = int(0.18 * H) + k * int(0.66 * H / max(n_fig, 1))
                box_w = int(0.40 * W)
                box_h = int(0.62 * H / max(n_fig, 1))
                try:
                    if Image is not None:
                        with Image.open(path) as im:
                            iw, ih = im.size
                        aspect = iw / max(ih, 1)
                    else:
                        aspect = 4 / 3
                    w = box_w
                    h = int(w / aspect)
                    if h > box_h:
                        h = box_h
                        w = int(h * aspect)
                    left = box_l + (box_w - w) // 2
                    top = box_t + (box_h - h) // 2
                    slide.shapes.add_picture(path, Emu(left), Emu(top), Emu(w), Emu(h))
                    entry["placed"] = True
                    entry["aspect_preserved"] = True
                    entry["scale_pct"] = round(100 * w / max(iw, 1), 1) if Image is not None and iw else None
                except Exception as e:  # 图片损坏等：跳过并记录
                    entry["reason"] = f"{type(e).__name__}: {e}"
                    fallbacks.append({"slide": n, "what": f"figure {fg.get('ref')}",
                                      "action": f"skipped ({entry['reason']})"})
                placed.append(entry)
        rep["figures"] = placed

        notes = str(spec.get("notes") or "")
        if notes:
            slide.notes_slide.notes_text_frame.text = notes
        rep["notes_chars"] = len(notes)
        slides_report.append(rep)

    out_pptx = os.path.join(ctx.output, "deck.pptx")
    prs.save(out_pptx)
    report = {
        "template": template,
        "template_layout_names": layout_names,
        "template_had_slides_removed": n_removed,
        "slides": slides_report,
        "fallbacks": fallbacks,
        "deck": out_pptx,
        "deck_sha256": sha256_file(out_pptx),
        "built_at": now_iso(),
    }
    rp = os.path.join(ctx.work, "build_report.json")
    write_json(rp, report)
    print(f"[S6] deck.pptx 构建完成：{len(slides_report)} 页，兜底 {len(fallbacks)} 处", flush=True)
    return [out_pptx, rp]
