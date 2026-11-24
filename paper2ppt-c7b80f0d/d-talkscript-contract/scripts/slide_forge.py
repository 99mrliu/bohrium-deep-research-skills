#!/usr/bin/env python3
"""slide_forge.py -- 幂等 upsert 第 i 页幻灯片（逐拍打造）。

用法：
    python3 slide_forge.py deck.pptx --beat beats.json#2 \
        [--template target-template.pptx] [--evidence evidence.json] \
        [--paper paper.pdf] --log forge_log.json

行为：
  * deck.pptx 不存在时：以 --template 的母版/版式新建（模板自带示例页会被清空并记录），
    无模板则用 python-pptx 默认母版；
  * 页数不足 i+1 时按"标题+内容"版式补页；
  * 自建元素统一 forge_ 前缀；重跑先删旧 forge_ 元素再重建 => 幂等，不堆积；
  * 备注 = 该拍讲稿原文 + [TRANSITION] 过渡句 + [IF-ASKED] 备询补充；
  * 页脚小字放证据引用（ref + 页码 + 逐字 quote 摘要）；
  * 图：--paper + pymupdf 可用时把 caption 上方的页面区域渲染成 PNG 插入；
    取不到图就放带引用文字的占位框，并在 log 中记 figure_placeholder=true。

python-pptx 缺失时明确报错并以退出码 2 退出（诚实 partial，不静默失败）。
"""
import argparse
import json
import os
import re
import sys

try:
    from pptx import Presentation
    from pptx.util import Inches, Pt, Emu
    from pptx.dml.color import RGBColor
    from pptx.enum.shapes import PP_PLACEHOLDER
    BODY_PH_TYPES = frozenset(
        {PP_PLACEHOLDER.BODY, PP_PLACEHOLDER.OBJECT, PP_PLACEHOLDER.VERTICAL_BODY}
    )
except ImportError:
    print(
        "ERROR: python-pptx is required for slide_forge.py. "
        "Install it (pip install python-pptx) or build the deck manually and "
        "record status=partial with exceptions=[tool_missing:python-pptx].",
        file=sys.stderr,
    )
    sys.exit(2)

FORGE_PREFIX = "forge_"
FOOTER_COLOR = RGBColor(0x59, 0x59, 0x59)


def parse_beat_selector(sel):
    m = re.match(r"^(?P<path>.+?)#(?P<idx>\d+)$", sel)
    if not m:
        print(f"ERROR: --beat must look like beats.json#<index>, got '{sel}'", file=sys.stderr)
        sys.exit(2)
    with open(m.group("path"), encoding="utf-8") as f:
        data = json.load(f)
    beats = data.get("beats") if isinstance(data, dict) else data
    idx = int(m.group("idx"))
    if not isinstance(beats, list) or idx >= len(beats):
        print(f"ERROR: beat index {idx} out of range (n={len(beats) if isinstance(beats, list) else '?'})",
              file=sys.stderr)
        sys.exit(2)
    return beats[idx], idx, m.group("path")


def drop_all_slides(prs):
    xml_slides = prs.slides._sldIdLst  # noqa: SLF001 (python-pptx 无公开 API)
    for sld in list(xml_slides):
        rId = sld.get("{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id")
        prs.part.drop_rel(rId)
        xml_slides.remove(sld)


def pick_body_layout(prs):
    """优先选带正文占位符（BODY/OBJECT）且带标题的版式，如 'Title and Content'。"""
    for layout in prs.slide_layouts:
        types = {ph.placeholder_format.type for ph in layout.placeholders}
        if BODY_PH_TYPES & types and PP_PLACEHOLDER.TITLE in types:
            return layout
    for layout in prs.slide_layouts:
        types = {ph.placeholder_format.type for ph in layout.placeholders}
        if BODY_PH_TYPES & types:
            return layout
    return prs.slide_layouts[min(1, len(prs.slide_layouts) - 1)]


def remove_forge_shapes(slide):
    """只删 forge_ 前缀的"游离"元素（textbox/picture）。

    占位符（title/body）不删：覆盖其文本天然幂等，删掉反而永久丢失版式占位符。
    """
    for shape in list(slide.shapes):
        if shape.name and shape.name.startswith(FORGE_PREFIX) and not shape.is_placeholder:
            shape._element.getparent().remove(shape._element)  # noqa: SLF001


def remove_empty_placeholders(slide):
    for ph in list(slide.placeholders):
        if ph.has_text_frame and not ph.text_frame.text.strip():
            ph._element.getparent().remove(ph._element)  # noqa: SLF001


def set_title(slide, title):
    if slide.shapes.title is not None:
        slide.shapes.title.text_frame.text = title
        return
    box = slide.shapes.add_textbox(Inches(0.5), Inches(0.3), Inches(9), Inches(1.0))
    box.name = FORGE_PREFIX + "title"
    box.text_frame.text = title
    box.text_frame.paragraphs[0].font.size = Pt(28)
    box.text_frame.paragraphs[0].font.bold = True


def set_bullets(slide, bullets):
    body_ph = None
    for ph in slide.placeholders:
        if ph.placeholder_format.type in BODY_PH_TYPES:
            body_ph = ph
            break
    if body_ph is not None:
        tf = body_ph.text_frame
        tf.clear()
        for i, b in enumerate(bullets):
            p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
            p.text = str(b)
            p.font.size = Pt(18)
        return
    box = slide.shapes.add_textbox(Inches(0.6), Inches(1.4), Inches(8.8), Inches(4.2))
    box.name = FORGE_PREFIX + "body"
    tf = box.text_frame
    tf.word_wrap = True
    for i, b in enumerate(bullets):
        p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
        p.text = str(b)
        p.font.size = Pt(18)


def resolve_refs(refs, evidence):
    """把 evidence_refs 解析为 (kind, ref, page, quote) 列表。"""
    out = []
    if not evidence:
        return out
    figs = {f["ref"]: f for f in evidence.get("figures", [])}
    tabs = {t["ref"]: t for t in evidence.get("tables", [])}
    anchors = {a["id"]: a for a in evidence.get("anchors", [])}
    for ref in refs:
        kind, _, key = str(ref).partition(":")
        if kind == "fig" and key in figs:
            e = figs[key]
            out.append(("fig", key, e["page"], e["caption"]))
        elif kind == "tab" and key in tabs:
            e = tabs[key]
            out.append(("tab", key, e["page"], e["caption"]))
        elif kind == "anchor":
            e = anchors.get(int(key)) if key.isdigit() else None
            if e:
                out.append(("anchor", f"{e['value']} {e['unit']}", e["page"], e["context"]))
        elif kind == "page" and key.isdigit():
            out.append(("page", f"page {key}", int(key), ""))
    return out


def add_footer(slide, citations, prs):
    if not citations:
        return
    parts = [f"{ref} (p.{page})" for _k, ref, page, _q in citations]
    text = "Evidence: " + "; ".join(parts)
    box = slide.shapes.add_textbox(
        Inches(0.4), prs.slide_height - Inches(0.45),
        prs.slide_width - Inches(0.8), Inches(0.35),
    )
    box.name = FORGE_PREFIX + "footer"
    tf = box.text_frame
    tf.word_wrap = True
    tf.text = text
    p = tf.paragraphs[0]
    p.font.size = Pt(10)
    p.font.color.rgb = FOOTER_COLOR


def render_figure_region(paper, page_no, caption, out_png):
    """用 pymupdf 把 caption 上方的页面区域渲染为 PNG。失败返回 None。"""
    try:
        import fitz
    except ImportError:
        return None
    try:
        doc = fitz.open(paper)
        page = doc[page_no - 1]
        rects = page.search_for(caption[:40])
        top_of_caption = min(r.y0 for r in rects) if rects else page.rect.height * 0.75
        clip = fitz.Rect(0, 0, page.rect.width, max(top_of_caption - 6, page.rect.height * 0.2))
        pix = page.get_pixmap(matrix=fitz.Matrix(2, 2), clip=clip)
        pix.save(out_png)
        doc.close()
        return out_png
    except Exception as e:
        print(f"WARN: figure render failed ({e}); using placeholder", file=sys.stderr)
        return None


def place_figure_or_placeholder(slide, prs, fig_citations, paper, deck_dir, log_entry):
    if not fig_citations:
        return
    _kind, ref, page, quote = fig_citations[0]
    img_path = None
    if paper:
        safe = re.sub(r"\W+", "_", ref)
        img_path = render_figure_region(
            paper, page, quote, os.path.join(deck_dir, f"forge_{safe}_p{page}.png")
        )
    if img_path:
        top = Inches(3.2)  # 避开标题与前两条 bullet 的常规区域
        height = prs.slide_height - top - Inches(0.6)  # 给页脚留空
        pic = slide.shapes.add_picture(img_path, Inches(3.8), top, height=height)
        pic.name = FORGE_PREFIX + "figure"
        log_entry["figure_placeholder"] = False
        log_entry["figure_image"] = img_path
    else:
        box = slide.shapes.add_textbox(Inches(3.8), Inches(2.8), Inches(5.2), Inches(2.6))
        box.name = FORGE_PREFIX + "fig_placeholder"
        tf = box.text_frame
        tf.word_wrap = True
        tf.text = f"[Figure placeholder] {ref} (paper p.{page})\n{quote}"
        tf.paragraphs[0].font.size = Pt(12)
        tf.paragraphs[0].font.italic = True
        log_entry["figure_placeholder"] = True


def compose_notes(beat):
    parts = [str(beat.get("beat_text", "")).strip()]
    if str(beat.get("transition", "")).strip():
        parts.append(f"[TRANSITION] {beat['transition'].strip()}")
    if str(beat.get("if_asked", "")).strip():
        parts.append(f"[IF-ASKED] {beat['if_asked'].strip()}")
    return "\n\n".join(p for p in parts if p)


def upsert_slide(deck_path, beat, idx, template, evidence, paper, log_path):
    created_from = None
    if os.path.exists(deck_path):
        prs = Presentation(deck_path)
    elif template and os.path.exists(template):
        prs = Presentation(template)
        n_dropped = len(prs.slides._sldIdLst)  # noqa: SLF001
        drop_all_slides(prs)
        created_from = f"template:{template} (dropped {n_dropped} demo slides)"
    else:
        prs = Presentation()
        created_from = "python-pptx default master"

    layout = pick_body_layout(prs)
    while len(prs.slides) <= idx:
        prs.slides.add_slide(layout)
    slide = prs.slides[idx]

    remove_forge_shapes(slide)
    title = str(beat.get("title") or str(beat.get("claim", ""))[:60])
    set_title(slide, title)
    bullets = beat.get("bullets") or [beat.get("claim", "")]
    set_bullets(slide, bullets[:6])
    remove_empty_placeholders(slide)

    refs = beat.get("evidence_refs") or []
    citations = resolve_refs(refs, evidence)
    add_footer(slide, citations, prs)

    log_entry = {
        "slide": idx + 1,
        "beat_id": beat.get("id", f"beat-{idx}"),
        "deck_created_from": created_from,
        "title": title,
        "n_bullets": len(bullets[:6]),
        "citations": [
            {"kind": k, "ref": r, "page": p, "quote": q} for k, r, p, q in citations
        ],
        "figure_placeholder": None,
        "notes_chars": 0,
    }
    fig_citations = [c for c in citations if c[0] == "fig"]
    place_figure_or_placeholder(
        slide, prs, fig_citations, paper,
        os.path.dirname(os.path.abspath(deck_path)), log_entry,
    )

    notes = compose_notes(beat)
    slide.notes_slide.notes_text_frame.text = notes
    log_entry["notes_chars"] = len(notes)

    prs.save(deck_path)

    # log：按 slide 索引覆盖，幂等
    log = {"runs": []}
    if os.path.exists(log_path):
        try:
            with open(log_path, encoding="utf-8") as f:
                log = json.load(f)
        except (OSError, json.JSONDecodeError):
            log = {"runs": []}
    log["runs"] = [r for r in log.get("runs", []) if r.get("slide") != idx + 1]
    log["runs"].append(log_entry)
    log["runs"].sort(key=lambda r: r["slide"])
    with open(log_path, "w", encoding="utf-8") as f:
        json.dump(log, f, ensure_ascii=False, indent=2)
    return log_entry


def main() -> int:
    ap = argparse.ArgumentParser(description="Idempotently upsert slide #i from beats.json.")
    ap.add_argument("deck", help="deck.pptx path (created if missing)")
    ap.add_argument("--beat", required=True, help="beats.json#<index>")
    ap.add_argument("--template", help="template pptx (theme/layouts source)")
    ap.add_argument("--evidence", help="evidence.json from evidence_scan.py")
    ap.add_argument("--paper", help="paper.pdf for figure region rendering (needs pymupdf)")
    ap.add_argument("--log", required=True, help="forge_log.json path")
    args = ap.parse_args()

    beat, idx, _ = parse_beat_selector(args.beat)
    evidence = None
    if args.evidence:
        try:
            with open(args.evidence, encoding="utf-8") as f:
                evidence = json.load(f)
        except (OSError, json.JSONDecodeError) as e:
            print(f"WARN: evidence.json unreadable ({e}); citations skipped", file=sys.stderr)

    entry = upsert_slide(args.deck, beat, idx, args.template, evidence, args.paper, args.log)
    fig_state = entry["figure_placeholder"]
    fig_msg = "n/a" if fig_state is None else ("placeholder" if fig_state else "rendered")
    print(
        f"slide_forge: slide {entry['slide']} upserted "
        f"(bullets={entry['n_bullets']}, citations={len(entry['citations'])}, "
        f"figure={fig_msg}, notes_chars={entry['notes_chars']}) -> {args.deck}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
