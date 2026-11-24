#!/usr/bin/env python3
"""build_deck.py — 从（修复后的）deck.json 简洁构建 presentation.pptx。

python-pptx 优先；可选 --template 复用模板版式与主题；--fig-dir 按
"Figure_1.png" 之类的净化命名查找图片并嵌入。空占位符一律移除，
保证 placeholder_free 可测。备注写入 notes_slide。

缺 python-pptx：不写半成品，build_report 记 engine=unavailable，
stderr 明确说明，退出码 3（诚实 partial，由调用方决定降级）。

用法：build_deck.py deck.json [--template t.pptx] --fig-dir figs/ \
        --out presentation.pptx --report build_report.json
退出码：0 成功；2 输入错误；3 python-pptx 缺失。
"""
import argparse
import json
import os
import re
import sys


def load_json(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def fig_filename(label: str):
    base = re.sub(r"[^A-Za-z0-9]+", "_", label).strip("_")
    return base


def find_fig(fig_dir, label):
    base = fig_filename(label)
    for ext in (".png", ".jpg", ".jpeg"):
        p = os.path.join(fig_dir, base + ext)
        if os.path.isfile(p):
            return p
    return None


def remove_placeholder(shape):
    el = shape._element
    el.getparent().remove(el)


def pick_layout(prs, names):
    for layout in prs.slide_layouts:
        if layout.name in names:
            return layout
    return None


def main(argv=None):
    ap = argparse.ArgumentParser(description="deck.json -> presentation.pptx")
    ap.add_argument("deck", help="deck.json 路径")
    ap.add_argument("--template", help="可选模板 pptx")
    ap.add_argument("--fig-dir", default="figs", help="图片目录（默认 figs/）")
    ap.add_argument("--out", required=True)
    ap.add_argument("--report", required=True)
    args = ap.parse_args(argv)

    try:
        deck = load_json(args.deck)
    except (OSError, json.JSONDecodeError) as e:
        print(f"ERROR: 无法读取 deck: {e}", file=sys.stderr)
        return 2

    try:
        from pptx import Presentation
        from pptx.util import Inches, Pt
    except ImportError:
        msg = ("python-pptx 不可用（tool_missing）：无法构建 pptx。"
               "请安装 python-pptx 或按诚实 partial 流程处理。")
        print(f"ERROR: {msg}", file=sys.stderr)
        with open(args.report, "w", encoding="utf-8") as f:
            json.dump({"out": None, "engine": "unavailable",
                       "error": msg, "slides": 0}, f, ensure_ascii=False, indent=2)
            f.write("\n")
        return 3

    if args.template and os.path.isfile(args.template):
        prs = Presentation(args.template)
        template_used = args.template
    else:
        prs = Presentation()
        template_used = None

    warnings = []
    figures_embedded, figures_missing = [], []
    title_layout = pick_layout(prs, ("Title Slide",))
    content_layout = pick_layout(prs, ("Title and Content", "Title, Content"))
    if content_layout is None:
        content_layout = prs.slide_layouts[1] if len(prs.slide_layouts) > 1 else prs.slide_layouts[0]
        warnings.append("未找到 Title and Content 版式，回退到 slide_layouts[1]")
    if title_layout is None:
        title_layout = prs.slide_layouts[0]
        warnings.append("未找到 Title Slide 版式，回退到 slide_layouts[0]")

    for spec in deck.get("slides", []):
        is_title = spec.get("role") == "title"
        slide = prs.slides.add_slide(title_layout if is_title else content_layout)

        # 先记录占位符，后统一清理空占位符
        body = None
        subtitle = None
        for ph in slide.placeholders:
            idx = ph.placeholder_format.idx
            if idx == 0:
                ph.text = spec.get("title", "")
            elif is_title:
                subtitle = ph
            elif body is None:
                body = ph

        if is_title:
            if subtitle is not None:
                subs = spec.get("bullets", [])
                if subs:
                    subtitle.text = subs[0]
                else:
                    remove_placeholder(subtitle)
        else:
            bullets = spec.get("bullets", [])
            if body is not None and bullets:
                tf = body.text_frame
                tf.clear()
                for i, b in enumerate(bullets):
                    para = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
                    para.text = b
                    para.font.size = Pt(16)
            elif body is not None:
                remove_placeholder(body)

        # 嵌图（非标题页）
        if not is_title:
            imgs = []
            for label in spec.get("figures", []) or []:
                p = find_fig(args.fig_dir, label)
                if p:
                    imgs.append((label, p))
                    figures_embedded.append({"slide": spec.get("slide"), "label": label, "file": p})
                else:
                    figures_missing.append({"slide": spec.get("slide"), "label": label})
                    warnings.append(f"slide {spec.get('slide')}: 未找到 {label} 的图片文件")
            if imgs:
                sw, sh = prs.slide_width, prs.slide_height
                if body is not None and body in [s for s in slide.shapes]:
                    body.width = int(sw * 0.52)
                top = Inches(1.6)
                for label, p in imgs[:2]:
                    slide.shapes.add_picture(
                        p, int(sw * 0.56), top, width=int(sw * 0.40))
                    top += int(sh * 0.45)

        # 表格（deck 提供 rows 时）
        tbl = spec.get("table")
        if tbl and tbl.get("rows"):
            rows, cols = len(tbl["rows"]), len(tbl["rows"][0])
            gframe = slide.shapes.add_table(
                rows, cols, Inches(0.6), Inches(4.2), Inches(5.0), Inches(0.4 * rows))
            for r, row in enumerate(tbl["rows"]):
                for c, val in enumerate(row):
                    gframe.table.cell(r, c).text = str(val)

        notes = spec.get("notes", "")
        if notes:
            slide.notes_slide.notes_text_frame.text = notes

        # 清理残留空占位符（保证 placeholder_free）
        for ph in list(slide.placeholders):
            try:
                if ph.has_text_frame and not ph.text_frame.text.strip():
                    remove_placeholder(ph)
            except Exception:
                pass

    prs.save(args.out)
    report = {
        "out": args.out,
        "engine": "python-pptx",
        "template": template_used,
        "slides": len(deck.get("slides", [])),
        "figures_embedded": figures_embedded,
        "figures_missing": figures_missing,
        "warnings": warnings,
    }
    with open(args.report, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
        f.write("\n")
    print(f"built {args.out} slides={report['slides']} engine=python-pptx "
          f"template={template_used} figs={len(figures_embedded)} "
          f"missing_figs={len(figures_missing)} warnings={len(warnings)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
