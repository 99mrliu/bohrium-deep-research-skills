#!/usr/bin/env python3
"""build_deck.py — 只从「已通过 plan_lint 的计划」构建 /app/output/deck.pptx。

- 模板真实套用：打开 template.pptx，按页型选版式（title→Title Slide，其余→Title and Content，
  找不到则退回含 title/body 占位符的版式，再退 prs.slide_layouts[1]）。
- 占位符填充；缺占位符时用文本框兜底并记录到 build_report.json（不静默）。
- 图片按容器等比缩放（PIL 读真实宽高比），图下加图注，绝不拉伸变形。
- 备注 = [claim_id] 主张 + 讲稿 + "⏱ ~Ns" 计时行（含累计/预算）+ 证据锚点；
  封面备注额外写入 storyline 主线四句话。
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common  # noqa: E402

from pptx import Presentation  # noqa: E402
from pptx.util import Emu, Inches, Pt  # noqa: E402
from PIL import Image  # noqa: E402

KIND_LAYOUT_CANDIDATES = {
    "title": ["Title Slide", "Title Only"],
    "_default": ["Title and Content", "Title Only", "Blank"],
}


def find_layout(prs, kind, report_entry):
    names = {lay.name: lay for lay in prs.slide_layouts}
    candidates = KIND_LAYOUT_CANDIDATES.get(kind, KIND_LAYOUT_CANDIDATES["_default"])
    for cand in candidates:
        if cand in names:
            if cand != candidates[0]:
                report_entry["layout_fallback"] = cand
            return names[cand]
    # 找同时含 title+body 占位符的版式
    for lay in prs.slide_layouts:
        types = {ph.placeholder_format.idx for ph in lay.placeholders}
        if 0 in types and any(i >= 1 for i in types):
            report_entry["layout_fallback"] = lay.name
            return lay
    report_entry["layout_fallback"] = prs.slide_layouts[min(1, len(prs.slide_layouts) - 1)].name
    return prs.slide_layouts[min(1, len(prs.slide_layouts) - 1)]


def _body_placeholder(slide):
    for ph in slide.placeholders:
        if ph.placeholder_format.idx == 0:
            continue
        t = str(ph.placeholder_format.type)
        if "BODY" in t or "OBJECT" in t or "CONTENT" in t or "SUBTITLE" in t:
            return ph
    return slide.placeholders[1] if len(slide.placeholders) > 1 else None


def fill_bullets(tf, claim_text, bullets):
    tf.clear()
    p0 = tf.paragraphs[0]
    r = p0.add_run()
    r.text = f"主张：{claim_text}"
    r.font.bold = True
    r.font.size = Pt(15)
    for b in bullets:
        p = tf.add_paragraph()
        p.text = str(b)
        p.font.size = Pt(14)
        p.space_after = Pt(4)


def add_figure(slide, fig_path, caption, box, report_entry):
    """box=(left,top,width,height) EMU；等比缩放放入，图注置于图下。"""
    left, top, width, height = box
    try:
        with Image.open(fig_path) as im:
            iw, ih = im.size
    except Exception as e:  # noqa: BLE001
        report_entry.setdefault("figure_issues", []).append(f"{fig_path}: 无法读取图片 {e}")
        return
    cap_h = Inches(0.32)
    avail_h = max(height - cap_h, Inches(0.5))
    scale = min(width / iw, avail_h / ih)
    w, h = int(iw * scale), int(ih * scale)
    x = int(left + (width - w) / 2)
    y = int(top + (avail_h - h) / 2)
    slide.shapes.add_picture(str(fig_path), Emu(x), Emu(y), Emu(w), Emu(h))
    if caption:
        tb = slide.shapes.add_textbox(Emu(left), Emu(y + h + Emu(Inches(0.03))),
                                    Emu(width), Emu(cap_h))
        para = tb.text_frame.paragraphs[0]
        para.text = caption
        para.font.size = Pt(10)
        para.font.italic = True


def fmt_mmss(sec):
    sec = int(round(sec))
    return f"{sec // 60}:{sec % 60:02d}"


def build(work, output):
    work, output = Path(work), Path(output)
    cfg = common.read_json(work / "config.json", {}) or {}
    plan = common.read_json(work / "slide_plan.json", {}) or {}
    storyline = common.read_json(work / "storyline.json", {}) or {}
    lint = common.read_json(output / "plan_lint_report.json", {}) or {}
    if lint.get("overall") == "fail":
        print("[build_deck] plan_lint 未通过，拒绝构建（先修 storyline/slide_plan）")
        return 2

    template = cfg.get("materials", {}).get("template_pptx")
    if template and Path(template).exists():
        prs = Presentation(template)
        template_used = template
    else:
        prs = Presentation()  # python-pptx 默认模板，仍含真实母版/版式
        template_used = "python-pptx 默认模板（未发现/无法打开 template.pptx）"

    claims = {c.get("id"): c for c in storyline.get("claims", [])}
    timing = {t["slide"]: t for r in lint.get("rules", []) if r["rule"] == "R6_time_budget"
              for t in r["details"].get("timeline", [])}
    budget = next((r["details"] for r in lint.get("rules", []) if r["rule"] == "R6_time_budget"), {})
    dur = budget.get("duration_min", "?")

    SW, SH = prs.slide_width, prs.slide_height
    report = {"template_used": template_used, "built_at": common.now_iso(), "slides": []}

    for i, spec in enumerate(plan.get("slides", []), 1):
        entry = {"slide": i, "kind": spec.get("kind"), "title": spec.get("title", "")}
        layout = find_layout(prs, spec.get("kind", ""), entry)
        slide = prs.slides.add_slide(layout)
        entry["layout"] = layout.name

        # 标题
        if slide.shapes.title is not None:
            slide.shapes.title.text = spec.get("title", "") or spec.get("kind", "")
        else:
            tb = slide.shapes.add_textbox(Inches(0.5), Inches(0.3), SW - Inches(1.0), Inches(0.9))
            tb.text_frame.text = spec.get("title", "")
            entry["title_fallback"] = "textbox（版式无 title 占位符）"

        cid = spec.get("claim_id", "")
        claim = claims.get(cid, {})
        claim_text = spec.get("claim") or claim.get("text", "")

        if spec.get("kind") == "title":
            sub = _body_placeholder(slide)
            line = (f"{storyline.get('audience') or cfg.get('constraints', {}).get('audience') or ''}"
                    f" · {dur} min · narrative-first-deck").strip(" ·")
            if sub is not None:
                sub.text_frame.text = line
        else:
            body = _body_placeholder(slide)
            figs = [f for f in spec.get("figures", []) if f.get("path") and Path(f["path"]).exists()]
            if body is not None:
                fill_bullets(body.text_frame, claim_text, spec.get("bullets", []))
                if figs:
                    body.width = int(SW * 0.52)  # 左文右图
            else:
                tb = slide.shapes.add_textbox(Inches(0.5), Inches(1.5),
                                              int(SW * 0.52) if figs else SW - Inches(1.0),
                                              SH - Inches(2.1))
                fill_bullets(tb.text_frame, claim_text, spec.get("bullets", []))
                entry["body_fallback"] = "textbox（版式无 body 占位符）"

            missing_figs = [f.get("ref") for f in spec.get("figures", [])
                            if not (f.get("path") and Path(f["path"]).exists())]
            if missing_figs:
                entry.setdefault("figure_issues", []).append(f"图文件缺失未上页: {missing_figs}")
            if figs:
                area_l, area_t = int(SW * 0.55), Inches(1.4)
                area_w, area_h = int(SW * 0.42), SH - Inches(2.0)
                slot_h = int(area_h / len(figs))
                for k, f in enumerate(figs):
                    cap = f.get("caption") or f.get("ref", "")
                    add_figure(slide, f["path"], cap,
                               (area_l, int(area_t + k * slot_h), area_w, slot_h), entry)

        # 备注：主张 + 讲稿 + 计时行 + 证据
        lines = []
        if i == 1:
            ml = storyline.get("mainline", {})
            lines += ["[storyline 主线（先主线后页面）]",
                      f"问题: {ml.get('problem', '')}",
                      f"方法: {ml.get('method', '')}",
                      f"结果: {ml.get('results', '')}",
                      f"限制: {ml.get('limitations', '')}", ""]
        lines.append(f"[{cid}] {claim_text}")
        if spec.get("notes"):
            lines += ["", spec["notes"]]
        t = timing.get(i, {})
        lines += ["", f"⏱ ~{t.get('seconds', 0)}s"
                      f"（语速估计：中文≈4字/秒，英文≈2.2词/秒；累计 {fmt_mmss(t.get('cumulative_s', 0))}"
                      f" / 预算 {dur}min±15%）"]
        anchors = []
        for ev in claim.get("evidence_refs", []) or []:
            a = f"{ev.get('type')}:{ev.get('ref')}"
            if ev.get("quote"):
                a += f" \"{str(ev['quote'])[:80]}\""
            anchors.append(a)
        for ev in spec.get("evidence", []) or []:
            anchors.append(f"{ev.get('type')}:{ev.get('ref')}")
        if anchors:
            lines.append("证据: " + "; ".join(anchors))
        slide.notes_slide.notes_text_frame.text = "\n".join(lines)
        report["slides"].append(entry)

    output.mkdir(parents=True, exist_ok=True)
    deck = output / "deck.pptx"
    prs.save(str(deck))
    report["deck"] = str(deck)
    report["n_slides"] = len(report["slides"])
    common.write_json(output / "build_report.json", report)
    print(f"[build_deck] deck.pptx: {report['n_slides']} 页，模板={template_used}")
    for e in report["slides"]:
        fb = [k for k in e if k.endswith("fallback")] + (["figure_issues"] if e.get("figure_issues") else [])
        print(f"  slide {e['slide']:>2} [{e['kind']:<10}] layout={e['layout']}"
              + (f"  ⚠ {fb}" if fb else ""))
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(description="从已校验计划构建 deck.pptx")
    ap.add_argument("--work", required=True)
    ap.add_argument("--output", required=True)
    args = ap.parse_args(argv)
    return build(args.work, args.output)


if __name__ == "__main__":
    sys.exit(main())
