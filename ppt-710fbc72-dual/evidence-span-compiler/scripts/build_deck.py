"""Build an editable PPTX from the actual template and evidence-linked plan."""
from __future__ import annotations

from pathlib import Path
from typing import Any

import fitz
from PIL import Image
from pptx import Presentation
from pptx.dml.color import RGBColor
from pptx.enum.shapes import PP_PLACEHOLDER
from pptx.enum.text import MSO_ANCHOR, PP_ALIGN
from pptx.util import Inches, Pt

from common import atomic_json
from validate_plan import bullet_text

BODY_TYPES = {PP_PLACEHOLDER.BODY, PP_PLACEHOLDER.OBJECT, PP_PLACEHOLDER.SUBTITLE,
              PP_PLACEHOLDER.VERTICAL_BODY, PP_PLACEHOLDER.VERTICAL_OBJECT}
TITLE_TYPES = {PP_PLACEHOLDER.TITLE, PP_PLACEHOLDER.CENTER_TITLE}


def remove_template_slides(presentation: Presentation) -> int:
    slide_ids = list(presentation.slides._sldIdLst)
    for slide_id in slide_ids:
        relationship = slide_id.rId
        presentation.part.drop_rel(relationship)
        presentation.slides._sldIdLst.remove(slide_id)
    return len(slide_ids)


def choose_layout(presentation: Presentation, slide: dict[str, Any]):
    layouts = [layout for master in presentation.slide_masters for layout in master.slide_layouts]
    if "layout_index" in slide:
        index = slide["layout_index"]
        if not isinstance(index, int) or not 0 <= index < len(layouts):
            raise ValueError(f"Slide {slide.get('id')}: invalid layout_index {index!r}")
        return layouts[index], index
    if slide.get("layout_name"):
        matches = [(index, layout) for index, layout in enumerate(layouts) if layout.name == slide["layout_name"]]
        if not matches:
            raise ValueError(f"Slide {slide.get('id')}: layout_name {slide['layout_name']!r} not found")
        return matches[0][1], matches[0][0]
    preferred = "Title Slide" if slide.get("kind") == "title" else "Section Header" if slide.get("kind") == "section" else "Title and Content"
    for index, layout in enumerate(layouts):
        if layout.name.lower() == preferred.lower():
            return layout, index
    # Fall back by actual placeholder capabilities, never by a hard-coded package path.
    for index, layout in enumerate(layouts):
        placeholders = list(layout.placeholders)
        has_title = any(item.placeholder_format.type in TITLE_TYPES for item in placeholders)
        has_body = any(item.placeholder_format.type in BODY_TYPES for item in placeholders)
        if has_title and (slide.get("kind") == "title" or has_body):
            return layout, index
    raise ValueError(f"Slide {slide.get('id')}: no usable native layout with a title placeholder")


def style_run(run, size: int, bold: bool = False, color: RGBColor | None = None) -> None:
    run.font.size = Pt(max(14, size))
    run.font.bold = bold
    if color is not None:
        run.font.color.rgb = color


def set_title(shape, text: str, title_slide: bool) -> None:
    # Title size, typeface, and color remain native to the layout/master.
    frame = shape.text_frame
    frame.clear()
    frame.word_wrap = True
    paragraph = frame.paragraphs[0]
    paragraph.add_run().text = text


def set_body(shape, slide: dict[str, Any], title_slide: bool) -> None:
    frame = shape.text_frame
    frame.clear()
    frame.word_wrap = True
    frame.vertical_anchor = MSO_ANCHOR.TOP
    margin = Inches(0.06)
    frame.margin_left = margin
    frame.margin_right = margin
    frame.margin_top = margin
    frame.margin_bottom = margin
    first = True
    if slide.get("takeaway"):
        paragraph = frame.paragraphs[0]
        run = paragraph.add_run()
        run.text = str(slide["takeaway"])
        style_run(run, 20 if title_slide else 18, not title_slide)
        first = False
    for bullet in slide.get("bullets", []):
        paragraph = frame.paragraphs[0] if first else frame.add_paragraph()
        first = False
        paragraph.text = bullet_text(bullet)
        paragraph.level = 0
        paragraph.space_before = Pt(8)
        paragraph.space_after = Pt(4)
        paragraph.font.size = Pt(18)
        # Native body placeholders supply real bullet formatting through the layout.
    if first:
        frame.paragraphs[0].text = ""


def add_textbox(slide, left, top, width, height, text: str, size: int = 18, bold: bool = False):
    shape = slide.shapes.add_textbox(left, top, width, height)
    frame = shape.text_frame
    frame.word_wrap = True
    frame.margin_left = frame.margin_right = Inches(0.04)
    paragraph = frame.paragraphs[0]
    run = paragraph.add_run()
    run.text = text
    style_run(run, size, bold)
    return shape


def crop_asset(asset: dict[str, Any], bbox: list[float], source_path: Path,
               slide_id: str, figure_index: int, target_dir: Path) -> Path:
    target_dir.mkdir(parents=True, exist_ok=True)
    with fitz.open(source_path) as document:
        page = document[asset["page_number"] - 1]
        requested = fitz.Rect(*bbox)
        clipped = requested & page.rect
        if clipped.is_empty or clipped.width < 4 or clipped.height < 4:
            raise ValueError(f"Slide {slide_id}: crop {bbox} lies outside source page {asset['page_number']}")
        zoom = min(3.0, 2200.0 / max(clipped.width, clipped.height))
        target = target_dir / f"{slide_id}-asset-{figure_index + 1}.png"
        page.get_pixmap(matrix=fitz.Matrix(zoom, zoom), clip=clipped, alpha=False).save(target)
    return target


def add_picture_contain(slide, image_path: Path, left: int, top: int, width: int, height: int):
    with Image.open(image_path) as image:
        image_width, image_height = image.size
    scale = min(width / image_width, height / image_height)
    placed_width = max(1, int(image_width * scale))
    placed_height = max(1, int(image_height * scale))
    x = int(left + (width - placed_width) / 2)
    y = int(top + (height - placed_height) / 2)
    return slide.shapes.add_picture(str(image_path), x, y, width=placed_width, height=placed_height)


def speaker_notes(slide: dict[str, Any], evidence: dict[str, Any], spans: dict[str, Any]) -> str:
    lines = [str(slide.get("notes", "")).strip(), "", "Evidence anchors:"]
    for evidence_id in slide.get("evidence", []):
        anchor = evidence[evidence_id]
        span = spans[anchor["span_id"]]
        qualifier = anchor.get("qualifier")
        qualifier_text = f" Qualifier: {qualifier}" if qualifier else ""
        lines.append(f"[{evidence_id}] {anchor['span_id']} — {anchor['quote']}{qualifier_text}")
    lines.extend(["", "References:"])
    seen = set()
    for evidence_id in slide.get("evidence", []):
        anchor = evidence[evidence_id]
        span = spans[anchor["span_id"]]
        reference = f"{span['source_id']}, page {span['page_number']}, {span['span_id']}"
        if reference not in seen:
            lines.append(reference)
            seen.add(reference)
    return "\n".join(lines).strip()


def _remove_slide(presentation: Presentation, target: Any) -> None:
    for slide_id in list(presentation.slides._sldIdLst):
        if presentation.part.related_part(slide_id.rId) is target.part:
            presentation.part.drop_rel(slide_id.rId)
            presentation.slides._sldIdLst.remove(slide_id)
            return
    raise ValueError("Cannot resolve slide relationship for authorized removal")


def _reorder(presentation: Presentation, ordered_slides: list[Any]) -> None:
    by_part = {slide.part: slide for slide in ordered_slides}
    elements = list(presentation.slides._sldIdLst)
    selected = {}
    for element in elements:
        part = presentation.part.related_part(element.rId)
        if part in by_part:
            selected[part] = element
    for element in elements:
        presentation.slides._sldIdLst.remove(element)
    for slide in ordered_slides:
        presentation.slides._sldIdLst.append(selected[slide.part])


def _body_box(presentation: Presentation, body: Any) -> tuple[int, int, int, int]:
    if body is not None and all(value is not None for value in (body.left, body.top, body.width, body.height)):
        return int(body.left), int(body.top), int(body.width), int(body.height)
    return (int(presentation.slide_width * 0.05), int(presentation.slide_height * 0.21),
            int(presentation.slide_width * 0.90), int(presentation.slide_height * 0.70))


def build(plan: dict[str, Any], ledger: dict[str, Any], assets_document: dict[str, Any],
          work: Path, output: Path) -> tuple[Path, dict[str, Any]]:
    template_path = Path(plan.get("template_path") or "")
    if not template_path.is_file():
        raise ValueError("template_path must identify a valid PPTX; inspect template_inventory.json and set it explicitly.")
    presentation = Presentation(template_path)
    if not presentation.slide_masters or not any(master.slide_layouts for master in presentation.slide_masters):
        raise ValueError("Template has no usable masters/layouts.")
    mode = plan.get("mode", "generate")
    if mode == "generate":
        removed = remove_template_slides(presentation)
        originals: dict[str, Any] = {}
    else:
        removed = 0
        originals = {f"original-{index:04d}": slide
                     for index, slide in enumerate(presentation.slides, 1)}
        for source_id in plan.get("remove_slide_ids", []):
            _remove_slide(presentation, originals[source_id])
            removed += 1
    evidence = {item["id"]: item for item in plan["evidence"]}
    spans = {item["span_id"]: item for item in ledger["spans"]}
    sources = {item["source_id"]: item for item in ledger["sources"]}
    assets = {item["asset_id"]: item for item in assets_document["assets"]}
    build_slides = []
    ordered_slides = []
    output.mkdir(parents=True, exist_ok=True)
    for slide_spec in plan["slides"]:
        slide_id = slide_spec["id"]
        source_slide_id = slide_spec.get("source_slide_id")
        preserving = bool(slide_spec.get("preserve"))
        if preserving and slide_spec.get("figures"):
            raise ValueError(f"Slide {slide_id}: preserve:true cannot add figures; use an explicit edit instead")
        if source_slide_id:
            slide = originals[source_slide_id]
            layout = slide.slide_layout
            all_layouts = [candidate for master in presentation.slide_masters for candidate in master.slide_layouts]
            layout_index = next((index for index, candidate in enumerate(all_layouts)
                                 if candidate.part == layout.part), None)
        else:
            layout, layout_index = choose_layout(presentation, slide_spec)
            slide = presentation.slides.add_slide(layout)
        ordered_slides.append(slide)
        title_slide = slide_spec.get("kind") == "title"
        title_shape = slide.shapes.title
        if title_shape is None:
            title_shape = next((shape for shape in slide.placeholders if shape.placeholder_format.type in TITLE_TYPES), None)
        if title_shape is None and not preserving:
            raise ValueError(f"Slide {slide_id}: selected layout has no native title placeholder")
        bodies = sorted((shape for shape in slide.placeholders if shape.placeholder_format.type in BODY_TYPES),
                        key=lambda shape: shape.placeholder_format.idx)
        body = bodies[0] if bodies else None
        figures = slide_spec.get("figures", [])
        used = {"layout_index": layout_index, "layout_name": layout.name,
                "source_slide_id": source_slide_id, "preserved": preserving,
                "title_placeholder_idx": title_shape.placeholder_format.idx if title_shape is not None else None,
                "body_placeholder_idx": body.placeholder_format.idx if body is not None and body.is_placeholder else None,
                "assets": []}
        if not preserving:
            set_title(title_shape, slide_spec["title"], title_slide)
            if body is None:
                x, y, width, height = _body_box(presentation, None)
                body = add_textbox(slide, x, y, width, height, "", 18)
            set_body(body, slide_spec, title_slide)
            if figures:
                x, y, width, height = _body_box(presentation, body)
                text_width = int(width * 0.46)
                gap = int(width * 0.03)
                figure_x = x + text_width + gap
                figure_width = width - text_width - gap
                body.left, body.top, body.width, body.height = x, y, text_width, height
                slot_height = height / len(figures)
                for figure_index, figure in enumerate(figures):
                    asset = assets[figure["asset_id"]]
                    source = sources[asset["source_id"]]
                    image = crop_asset(asset, figure.get("bbox", asset["bbox"]), Path(source["path"]),
                                       slide_id, figure_index, work / "generated_assets")
                    slot_top = y + int(figure_index * slot_height)
                    caption_height = min(int(Inches(0.48)), max(int(Inches(0.30)), int(slot_height * 0.18)))
                    image_height = max(1, int(slot_height) - caption_height - int(Inches(0.06)))
                    add_picture_contain(slide, image, figure_x, slot_top, figure_width, image_height)
                    caption = add_textbox(slide, figure_x, slot_top + image_height, figure_width,
                                          caption_height, asset["caption"], 14)
                    caption.text_frame.paragraphs[0].alignment = PP_ALIGN.CENTER
                    used["assets"].append({"asset_id": asset["asset_id"], "crop_image": str(image),
                                           "bbox": figure.get("bbox", asset["bbox"]), "source_caption": asset["caption"]})
        evidence_text = speaker_notes(slide_spec, evidence, spans)
        if source_slide_id and preserving:
            previous_notes = slide.notes_slide.notes_text_frame.text.strip()
            slide.notes_slide.notes_text_frame.text = (previous_notes + "\n\n" if previous_notes else "") + evidence_text
        else:
            slide.notes_slide.notes_text_frame.text = evidence_text
        build_slides.append(used)
    _reorder(presentation, ordered_slides)
    presentation.core_properties.title = f"Evidence-bound presentation: {plan.get('case_id', '')}"
    destination = output / "presentation.pptx"
    presentation.save(destination)
    report = {"template": str(template_path), "mode": mode, "removed_template_slide_count": removed,
              "slide_count": len(build_slides), "slides": build_slides,
              "minimum_explicit_font_pt": 14, "title_style": "native layout/master inheritance",
              "image_placement": "aspect-fit within native body geometry; explicit or candidate PDF-point crop"}
    atomic_json(output / "build_report.json", report)
    return destination, report
