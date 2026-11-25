"""Input discovery, source-ledger extraction, caption candidates, and task parsing."""
from __future__ import annotations

import json
import re
import zipfile
from pathlib import Path
from typing import Any
from xml.etree import ElementTree

import fitz
from pptx import Presentation

from common import atomic_json, flatten_strings, normalize_text, sha256

CAPTION_RE = re.compile(r"^\s*(?:Figure|Fig\.?|Table)\s+[A-Za-z]?\d+", re.IGNORECASE)
PATH_KEY_RE = re.compile(r"(?:material|artifact|workorder|template|source|document|input|pdf|pptx)", re.I)
MISSING_INPUT_KEY_RE = re.compile(r"(?:material|workorder|template|source|document|input|pdf|pptx)", re.I)


def is_pdf(path: Path) -> bool:
    try:
        with path.open("rb") as stream:
            if stream.read(5) != b"%PDF-":
                return False
        with fitz.open(path) as document:
            return document.page_count > 0
    except Exception:
        return False


def is_pptx(path: Path) -> bool:
    try:
        if not zipfile.is_zipfile(path):
            return False
        with zipfile.ZipFile(path) as archive:
            if "ppt/presentation.xml" not in archive.namelist():
                return False
        presentation = Presentation(path)
        return len(presentation.slide_masters) > 0 and any(
            len(master.slide_layouts) > 0 for master in presentation.slide_masters)
    except Exception:
        return False


def discover_inputs(input_dir: Path, case: Any) -> tuple[list[Path], list[str]]:
    found = {path.resolve() for path in input_dir.rglob("*") if path.is_file()}
    uncertainties: list[str] = []
    if isinstance(case, dict):
        for key_path, value in flatten_strings(case):
            if not PATH_KEY_RE.search(key_path):
                continue
            expanded = Path(value).expanduser()
            candidates = [expanded] if expanded.is_absolute() else [input_dir / expanded, Path(value)]
            resolved = next((candidate.resolve() for candidate in candidates if candidate.exists()), None)
            if resolved and resolved.is_file():
                found.add(resolved)
            elif MISSING_INPUT_KEY_RE.search(key_path) and any(token in value.lower() for token in (".pdf", ".pptx", ".md", ".txt", "/")):
                uncertainties.append(f"Declared input path at {key_path or '<root>'} was not found: {value}")
    return sorted(found, key=lambda path: str(path)), uncertainties


def parse_task(text: str) -> dict[str, Any]:
    parameters: dict[str, Any] = {"slide_count": None, "time_minutes": None, "audience": None}
    slide = re.search(r"(?<!\d)(\d{1,3})\s*(?:slides?|页)(?!\w)", text, re.I)
    duration = re.search(r"(?<!\d)(\d{1,3}(?:\.\d+)?)\s*(?:minutes?|mins?|分钟)(?!\w)", text, re.I)
    audience = re.search(r"(?:audience|听众|受众)\s*[:：\-]\s*([^\n\r;]+)", text, re.I)
    if slide:
        parameters["slide_count"] = int(slide.group(1))
    if duration:
        raw = duration.group(1)
        parameters["time_minutes"] = float(raw) if "." in raw else int(raw)
    if audience:
        parameters["audience"] = audience.group(1).strip()
    parameters["missing"] = [key for key in ("slide_count", "time_minutes", "audience") if parameters[key] is None]
    return parameters


def parse_mode(case: Any, task_text: str) -> str:
    """Read an explicit generation/adaptation mode without guessing from a domain label."""
    if isinstance(case, dict):
        stack = [case]
        while stack:
            node = stack.pop()
            if isinstance(node, dict):
                for key, value in node.items():
                    if key.lower() in {"mode", "operation_mode"} and isinstance(value, str):
                        candidate = value.lower()
                        if candidate in {"edit", "adapt", "generate"}:
                            return "adapt" if candidate == "edit" else candidate
                    elif isinstance(value, (dict, list)):
                        stack.append(value)
            elif isinstance(node, list):
                stack.extend(item for item in node if isinstance(item, (dict, list)))
    match = re.search(r"\b(generate|generation|adapt|adaptation|edit)\b", task_text, re.I)
    if match:
        return "generate" if match.group(1).lower().startswith("generat") else "adapt"
    if isinstance(case, dict) and re.search(r"starting[-_ ]deck", json.dumps(case), re.I):
        return "adapt"
    return "generate"


def declared_deck_roles(case: Any, input_dir: Path) -> dict[str, str]:
    """Map explicitly declared material paths to roles, including sibling role keys."""
    roles: dict[str, str] = {}

    def walk(node: Any, inherited_role: str = "") -> None:
        if isinstance(node, dict):
            role = str(node.get("role", inherited_role) or "").lower()
            for key, value in node.items():
                if key in {"path", "file"} and isinstance(value, str):
                    candidate = Path(value).expanduser()
                    if not candidate.is_absolute():
                        candidate = input_dir / candidate
                    if candidate.exists():
                        roles[str(candidate.resolve())] = role
                elif isinstance(value, (dict, list)):
                    walk(value, role)
        elif isinstance(node, list):
            for value in node:
                walk(value, inherited_role)

    walk(case)
    return roles


def template_details(path: Path) -> dict[str, Any]:
    presentation = Presentation(path)
    details: dict[str, Any] = {
        "path": str(path), "sha256": sha256(path), "slide_count": len(presentation.slides),
        "slide_width": presentation.slide_width, "slide_height": presentation.slide_height,
        "master_count": len(presentation.slide_masters), "layouts": [], "theme_colors": {},
        "slides": [],
    }
    for index, slide in enumerate(presentation.slides, 1):
        details["slides"].append({
            "source_slide_id": f"original-{index:04d}", "layout_name": slide.slide_layout.name,
            "text": "\n".join(shape.text for shape in slide.shapes
                              if getattr(shape, "has_text_frame", False) and shape.text),
        })
    for master_index, master in enumerate(presentation.slide_masters):
        for layout in master.slide_layouts:
            details["layouts"].append({
                "index": len(details["layouts"]), "master_index": master_index, "name": layout.name,
                "placeholders": [{"idx": shape.placeholder_format.idx,
                                  "type": str(shape.placeholder_format.type), "name": shape.name}
                                 for shape in layout.placeholders],
            })
    try:
        with zipfile.ZipFile(path) as archive:
            theme_names = sorted(name for name in archive.namelist() if name.startswith("ppt/theme/theme") and name.endswith(".xml"))
            if theme_names:
                root = ElementTree.fromstring(archive.read(theme_names[0]))
                ns = {"a": "http://schemas.openxmlformats.org/drawingml/2006/main"}
                scheme = root.find(".//a:clrScheme", ns)
                if scheme is not None:
                    for child in scheme:
                        color = next(iter(child), None)
                        if color is not None:
                            details["theme_colors"][child.tag.rsplit("}", 1)[-1]] = color.attrib.get("val") or color.attrib.get("lastClr")
    except Exception as exc:
        details["theme_read_error"] = str(exc)
    return details


def _crop_above_caption(page: fitz.Page, caption: fitz.Rect) -> fitz.Rect:
    """Propose a conservative crop; users may replace it with an explicit PDF-points bbox."""
    rectangles: list[fitz.Rect] = []
    try:
        rectangles.extend(fitz.Rect(item["bbox"]) for item in page.get_image_info())
    except Exception:
        pass
    try:
        rectangles.extend(fitz.Rect(item["rect"]) for item in page.get_drawings() if item.get("rect"))
    except Exception:
        pass
    page_rect = page.rect
    nearby = []
    for rect in rectangles:
        if rect.is_empty or rect.width < 3 or rect.height < 3:
            continue
        if rect.width * rect.height > page_rect.width * page_rect.height * 0.9:
            continue
        vertical = rect.y1 <= caption.y0 + 3 and rect.y0 >= caption.y0 - 450
        horizontal = rect.x1 >= caption.x0 - 100 and rect.x0 <= caption.x1 + 100
        if vertical and horizontal:
            nearby.append(rect)
    if nearby:
        crop = nearby[0]
        for rect in nearby[1:]:
            crop |= rect
        # Vector table rules alone do not contain table text. Include neighboring text
        # within the drawing band, while excluding distant page headings/narrative.
        try:
            for text_block in page.get_text("blocks"):
                if len(text_block) < 5 or int(text_block[6]) != 0:
                    continue
                rect = fitz.Rect(text_block[:4])
                if (rect.y1 <= caption.y0 + 2 and rect.y0 >= crop.y0 - 80
                        and rect.x1 >= crop.x0 - 10 and rect.x0 <= crop.x1 + 10):
                    crop |= rect
        except Exception:
            pass
        crop = fitz.Rect(crop.x0 - 5, crop.y0 - 5, crop.x1 + 5, min(crop.y1 + 5, caption.y0 - 3))
    else:
        # Text-only tables have no usable drawing rectangles. Their neighboring
        # blocks provide the true column extent; exclude distant page headings.
        nearby_text = []
        try:
            for text_block in page.get_text("blocks"):
                if len(text_block) < 7 or int(text_block[6]) != 0:
                    continue
                rect = fitz.Rect(text_block[:4])
                if rect.y1 <= caption.y0 - 2 and rect.y0 >= caption.y0 - 240:
                    nearby_text.append(rect)
        except Exception:
            pass
        if nearby_text:
            crop = nearby_text[0]
            for rect in nearby_text[1:]:
                crop |= rect
            crop = fitz.Rect(crop.x0 - 6, crop.y0 - 6, crop.x1 + 6, caption.y0 - 4)
        else:
            crop = fitz.Rect(max(page_rect.x0 + 36, caption.x0 - 40), max(page_rect.y0 + 36, caption.y0 - 260),
                             min(page_rect.x1 - 36, caption.x1 + 40), caption.y0 - 4)
    return crop & page_rect


def extract_pdf(source_id: str, path: Path, digest: str, preview_dir: Path) -> tuple[list[dict], list[dict], list[dict]]:
    preview_dir.mkdir(parents=True, exist_ok=True)
    spans: list[dict[str, Any]] = []
    assets: list[dict[str, Any]] = []
    pages: list[dict[str, Any]] = []
    with fitz.open(path) as document:
        for page_index, page in enumerate(document):
            page_number = page_index + 1
            page_id = f"{source_id}.p{page_number:04d}"
            zoom = min(2.0, 1600.0 / max(page.rect.width, page.rect.height))
            preview = preview_dir / f"{page_id}.png"
            page.get_pixmap(matrix=fitz.Matrix(zoom, zoom), alpha=False).save(preview)
            pages.append({"page_id": page_id, "page_number": page_number, "width": page.rect.width,
                          "height": page.rect.height, "preview": str(preview)})
            data = page.get_text("dict", flags=fitz.TEXTFLAGS_TEXT)
            for block_index, block in enumerate(data.get("blocks", [])):
                if block.get("type") != 0:
                    continue
                block_id = f"{page_id}.b{block_index:03d}"
                block_lines = []
                for line in block.get("lines", []):
                    line_text = "".join(item.get("text", "") for item in line.get("spans", []))
                    if line_text:
                        block_lines.append(line_text)
                block_text = "\n".join(block_lines)
                for line_index, line in enumerate(block.get("lines", [])):
                    for span_index, span in enumerate(line.get("spans", [])):
                        raw = span.get("text", "")
                        if not normalize_text(raw):
                            continue
                        span_id = f"{block_id}.l{line_index:02d}s{span_index:02d}"
                        spans.append({
                            "span_id": span_id, "source_id": source_id, "source_sha256": digest,
                            "page_id": page_id, "page_number": page_number, "block_id": block_id,
                            "bbox": [round(value, 3) for value in span["bbox"]], "text": raw,
                            "normalized_text": normalize_text(raw), "block_text": block_text,
                            "block_bbox": [round(value, 3) for value in block["bbox"]],
                        })
                if CAPTION_RE.match(normalize_text(block_text)):
                    caption = normalize_text(block_text)
                    bbox = fitz.Rect(block["bbox"])
                    crop = _crop_above_caption(page, bbox)
                    kind = "table" if caption.lower().startswith("table") else "figure"
                    asset_id = f"{block_id}.asset"
                    assets.append({"asset_id": asset_id, "source_id": source_id, "source_sha256": digest,
                                   "page_number": page_number, "kind": kind, "caption": caption,
                                   "caption_bbox": [round(v, 3) for v in bbox],
                                   "bbox": [round(v, 3) for v in crop], "coordinate_system": "PDF points, top-left origin",
                                   "page_preview": str(preview), "requires_visual_check": True})
    return spans, assets, pages


def extract_text(source_id: str, path: Path, digest: str) -> list[dict[str, Any]]:
    text = path.read_text(encoding="utf-8", errors="replace")
    spans = []
    for index, line in enumerate(text.splitlines()):
        if not normalize_text(line):
            continue
        span_id = f"{source_id}.p0001.b000.l{index:03d}s00"
        spans.append({"span_id": span_id, "source_id": source_id, "source_sha256": digest,
                      "page_id": f"{source_id}.p0001", "page_number": 1, "block_id": f"{source_id}.p0001.b000",
                      "bbox": None, "text": line, "normalized_text": normalize_text(line),
                      "block_text": line, "block_bbox": None})
    return spans


def prepare(input_dir: Path, work: Path) -> dict[str, Any]:
    work.mkdir(parents=True, exist_ok=True)
    case_path = input_dir / "case.json"
    if not case_path.is_file():
        raise FileNotFoundError(f"Required case file not found: {case_path}")
    case = json.loads(case_path.read_text(encoding="utf-8"))
    atomic_json(work / "case_snapshot.json", case)
    paths, uncertainties = discover_inputs(input_dir, case)
    inventory = []
    pdfs: list[Path] = []
    templates: list[Path] = []
    text_sources: list[Path] = []
    for path in paths:
        item: dict[str, Any] = {"path": str(path), "size": path.stat().st_size, "sha256": sha256(path)}
        try:
            relative = path.relative_to(input_dir.resolve())
            item["relative_path"] = str(relative)
        except ValueError:
            item["relative_path"] = None
        if is_pdf(path):
            item["kind"] = "pdf"
            pdfs.append(path)
        elif is_pptx(path):
            item["kind"] = "pptx_template"
            templates.append(path)
        elif path.suffix.lower() in {".md", ".txt"}:
            item["kind"] = "text_source"
            text_sources.append(path)
        else:
            item["kind"] = "other"
        inventory.append(item)
    sources, spans, assets, pages = [], [], [], []
    source_paths = sorted(pdfs + text_sources, key=lambda path: str(path))
    for index, path in enumerate(source_paths, 1):
        source_id = f"S{index:03d}"
        digest = sha256(path)
        kind = "pdf" if path in pdfs else "task_text"
        source = {"source_id": source_id, "path": str(path), "sha256": digest, "kind": kind}
        if kind == "pdf":
            extracted_spans, extracted_assets, extracted_pages = extract_pdf(source_id, path, digest, work / "page_previews")
            spans.extend(extracted_spans)
            assets.extend(extracted_assets)
            pages.extend(extracted_pages)
            source["page_count"] = len(extracted_pages)
        else:
            spans.extend(extract_text(source_id, path, digest))
        sources.append(source)
    ledger = {"schema_version": "1.0", "sources": sources, "spans": spans, "pages": pages,
              "input_files": inventory}
    atomic_json(work / "source_ledger.json", ledger)
    atomic_json(work / "asset_candidates.json", {"assets": assets,
             "usage": "Select asset_id and optionally replace bbox with [x0,y0,x1,y1] in PDF points after inspecting page_preview."})
    atomic_json(work / "input_inventory.json", {"files": inventory})
    template_inventory = [template_details(path) for path in templates]
    task_text = "\n".join(path.read_text(encoding="utf-8", errors="replace") for path in text_sources)
    mode = parse_mode(case, task_text)
    roles = declared_deck_roles(case, input_dir)
    if mode == "adapt":
        role_matches = [item for item in template_inventory
                        if re.search(r"starting|source[-_ ]deck", roles.get(item["path"], ""))]
    else:
        role_matches = [item for item in template_inventory if "template" in roles.get(item["path"], "")]
    candidates = role_matches or template_inventory
    selected_template = candidates[0]["path"] if len(candidates) == 1 else None
    if len(candidates) > 1:
        uncertainties.append(f"Multiple valid PPTX bases match mode={mode}; set template_path explicitly in deck_plan.json.")
    if not template_inventory:
        uncertainties.append("No valid PPTX template/starting deck was discovered.")
    atomic_json(work / "template_inventory.json", {"templates": template_inventory,
             "selected_template": selected_template, "mode": mode, "declared_roles": roles})
    parameters = parse_task(task_text)
    uncertainties.extend(f"Task parameter not stated; not guessed: {key}" for key in parameters["missing"])
    if not pdfs:
        uncertainties.append("No valid source PDF was discovered; text sources may still be used.")
    plan = {
        "schema_version": "1.0", "case_id": case.get("case_id") if isinstance(case, dict) else None,
        "mode": mode, "task_parameters": parameters, "template_path": selected_template,
        "remove_slide_ids": [], "evidence": [], "slides": [],
        "_instructions": "Replace with the concise audience-specific narrative. Copy this file to deck_plan.json; each slide needs id/kind/title/takeaway/bullets/notes/evidence/figures. Bullets may be strings only when non-factual, otherwise {text,evidence:[E...]}. Define E anchors as {id,span_id,quote,qualifier}. In adapt mode account for every original slide once with slide.source_slide_id or remove_slide_ids; preserve:true keeps original slide content. No content is authored by prepare.",
    }
    atomic_json(work / "deck_plan.skeleton.json", plan)
    return {"case": case, "sources": sources, "uncertainties": uncertainties,
            "span_count": len(spans), "asset_count": len(assets), "task_parameters": parameters,
            "mode": mode, "input_files": inventory}
