#!/usr/bin/env python3
"""build_deck.py — 由 deck.json 构建可编辑 pptx。

- python-pptx 优先；缺失时 stderr 报 tool_missing，退出码 3（不伪造产物）。
- 可选 --template：沿用模板的前两个版式（title / title+content）。
- 每个 figure 下方加 provenance 小字（id · provenance · 论文页码 · caption 截断）。
- 每页备注写明图源与页码（来自 deck.json 的 notes 字段，自动追加 figure 出处行）。
- 构建后删除残留空占位符，保证渲染无 "Click to add" 提示文本。
- 幂等：同输入重建同结构 pptx（包内 zip 时间戳固定为 1980-01-01 由调用方不保证，
  但幻灯片内容结构确定）。

退出码：0 正常；2 输入错误；3 python-pptx 缺失。
"""
import argparse
import json
import os
import sys

try:
    from pptx import Presentation
    from pptx.util import Inches, Pt
    HAS_PPTX = True
except ImportError:
    HAS_PPTX = False

ROLE_LAYOUT = {"title": 0}  # 其余角色用 title+content 版式


def remove_empty_placeholders(slide):
    for ph in list(slide.placeholders):
        try:
            if ph.has_text_frame and not ph.text_frame.text.strip():
                ph._element.getparent().remove(ph._element)
        except Exception:
            pass


def add_text_body(slide, claims, sources, narrow):
    """把 claims 作为要点写入正文占位符；sources 追加为来源行。
    narrow=True 时收窄正文宽度，给右侧图让位。"""
    body = None
    for ph in slide.placeholders:
        if ph.placeholder_format.idx != 0 and ph.has_text_frame:
            body = ph
            break
    if body is None:
        return False
    if narrow:
        body.width = Inches(3.9)
    tf = body.text_frame
    tf.word_wrap = True
    tf.clear()
    first = True
    for c in claims:
        p = tf.paragraphs[0] if first else tf.add_paragraph()
        first = False
        p.text = c
        for run in p.runs:
            run.font.size = Pt(14)
    for s in sources:
        p = tf.add_paragraph()
        p.text = f"source: {s.get('ref', '')} {s.get('locator', '')}".strip()
        p.level = 1
        for run in p.runs:
            run.font.size = Pt(11)
    return True


def main():
    ap = argparse.ArgumentParser(
        description="Build an editable pptx from deck.json with provenance labels.")
    ap.add_argument("deck", help="deck.json (must pass fig_binding_lint.py first)")
    ap.add_argument("--template", default=None, help="optional template .pptx")
    ap.add_argument("--fig-dir", default="figs", help="base dir for relative figure paths")
    ap.add_argument("--manifest", default=None,
                    help="figure_manifest.json for page/caption in labels")
    ap.add_argument("--out", default="presentation.pptx")
    ap.add_argument("--report", default="build_report.json")
    args = ap.parse_args()

    try:
        with open(args.deck, encoding="utf-8") as fh:
            deck = json.load(fh)
    except (OSError, json.JSONDecodeError) as exc:
        sys.stderr.write(f"error: cannot read deck.json: {exc}\n")
        return 2

    fig_meta = {}
    if args.manifest and os.path.isfile(args.manifest):
        with open(args.manifest, encoding="utf-8") as fh:
            manifest = json.load(fh)
        fig_meta = {f["id"]: f for f in manifest.get("figures", [])}

    if not HAS_PPTX:
        sys.stderr.write("tool_missing: python-pptx not installed; cannot build "
                         "editable pptx; no artifact fabricated\n")
        return 3

    if args.template and os.path.isfile(args.template):
        prs = Presentation(args.template)
        # 模板里自带的示例幻灯片全部移除（连关系一起 drop，否则残留部件会
        # 与新幻灯片重名），仅保留版式与主题
        rns = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id"
        xml_slides = prs.slides._sldIdLst
        for sld in list(xml_slides):
            prs.part.drop_rel(sld.attrib[rns])
            xml_slides.remove(sld)
        template_used = os.path.abspath(args.template)
    else:
        prs = Presentation()
        template_used = None

    deck_dir = os.path.dirname(os.path.abspath(args.deck))
    images_embedded, images_missing = [], []

    for slide_spec in deck.get("slides", []):
        role = slide_spec.get("role", "content")
        layout_idx = ROLE_LAYOUT.get(role, 1)
        if layout_idx >= len(prs.slide_layouts):
            layout_idx = 1 if len(prs.slide_layouts) > 1 else 0
        slide = prs.slides.add_slide(prs.slide_layouts[layout_idx])
        if slide.shapes.title is not None:
            slide.shapes.title.text = slide_spec.get("title", "")

        claims = slide_spec.get("claims", [])
        sources = slide_spec.get("sources", [])
        has_figs = bool(slide_spec.get("figures"))
        body_ok = (add_text_body(slide, claims, sources, narrow=has_figs)
                   if (claims or sources) else False)

        # 图：有正文占位符时图放右侧/下方；无正文时居中
        figs = slide_spec.get("figures", [])
        y = Inches(1.6)
        for ref in figs:
            path = ref.get("path") or ""
            full = path if os.path.isabs(path) else os.path.join(deck_dir, path)
            if not os.path.isfile(full):
                alt = os.path.join(args.fig_dir, os.path.basename(path))
                full = alt if os.path.isfile(alt) else full
            meta = fig_meta.get(ref.get("id"), {})
            if os.path.isfile(full):
                pic_left = Inches(4.7) if body_ok else Inches(2.4)
                pic = slide.shapes.add_picture(full, pic_left, y, height=Inches(3.0))
                images_embedded.append({"slide": slide_spec.get("n"),
                                        "id": ref.get("id"), "file": full})
                # provenance 小字
                tb = slide.shapes.add_textbox(pic_left, y + Inches(3.25),
                                              Inches(5.2), Inches(0.5))
                page = meta.get("page", "?")
                cap = (meta.get("caption") or "")[:90]
                tb.text_frame.text = (f"{ref.get('id')} · {ref.get('provenance')} · "
                                      f"paper p.{page} · {cap}")
                tb.text_frame.paragraphs[0].runs[0].font.size = Pt(8)
                y += Inches(3.9)
                _ = pic
            else:
                images_missing.append({"slide": slide_spec.get("n"),
                                       "id": ref.get("id"), "path": path})

        # 备注：讲稿 + 图源与页码
        notes_lines = [slide_spec.get("notes", "")]
        for ref in figs:
            meta = fig_meta.get(ref.get("id"), {})
            notes_lines.append(
                f"figure {ref.get('id')}: {ref.get('provenance')}, "
                f"paper page {meta.get('page', '?')}, file {ref.get('path')}")
        if slide_spec.get("table"):
            notes_lines.append(f"table source: {slide_spec['table']}")
        notes_text = "\n".join(t for t in notes_lines if t)
        slide.notes_slide.notes_text_frame.text = notes_text

        remove_empty_placeholders(slide)

    os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
    prs.save(args.out)

    report = {
        "deck": os.path.abspath(args.deck),
        "out": os.path.abspath(args.out),
        "template_used": template_used,
        "generated_by": "build_deck.py",
        "slides_built": len(deck.get("slides", [])),
        "images_embedded": images_embedded,
        "images_missing": images_missing,
    }
    with open(args.report, "w", encoding="utf-8") as fh:
        json.dump(report, fh, ensure_ascii=False, indent=2)
    print(f"slides={report['slides_built']} images={len(images_embedded)} "
          f"missing={len(images_missing)} template={'yes' if template_used else 'no'} "
          f"-> {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
