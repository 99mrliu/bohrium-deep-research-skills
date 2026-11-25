"""Evidence-bound plan validation and numeric provenance checks."""
from __future__ import annotations

import math
import re
from collections import Counter
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

from common import case_identifier, normalize_text, sha256

# Numbers are tokenized, never searched as arbitrary substrings. Units are retained.
NUMBER_RE = re.compile(
    r"(?<![\w.])[-+\u2212]?(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?"
    r"(?:[eE][-+]?\d+)?(?:\s*(?:%|percent|percentage|ppm|ppb|ms|s|min|h|Hz|kHz|MHz|GPa|MPa|kPa|Pa|mV|V|nM|µM|μM|mM|M|mg|kg|g|mL|L|nm|µm|μm|mm|cm|km|m|K))?(?!\w)",
    re.IGNORECASE,
)
SLIDE_KINDS = {"title", "content", "section", "figure", "table", "summary", "closing"}
MAX_BULLETS = 6


def numeric_tokens(text: str) -> list[str]:
    return [match.group(0).strip() for match in NUMBER_RE.finditer(normalize_text(text))]


def numeric_signature(token: str) -> tuple[Decimal, str] | None:
    normalized = normalize_text(token).replace("\u2212", "-").replace(",", "")
    match = re.match(r"^([-+]?(?:\d+(?:\.\d+)?|\.\d+)(?:e[-+]?\d+)?)\s*(.*)$", normalized, re.I)
    if not match:
        return None
    try:
        number = Decimal(match.group(1))
    except InvalidOperation:
        return None
    unit = re.sub(r"\s+", "", match.group(2)).lower().replace("μ", "µ")
    if unit in {"percent", "percentage"}:
        unit = "%"
    return number, unit


def numeric_supported(token: str, evidence_text: str) -> bool:
    signature = numeric_signature(token)
    if signature is None:
        return False
    number, unit = signature
    for candidate in numeric_tokens(evidence_text):
        other = numeric_signature(candidate)
        if other is not None and other[0] == number and other[1] == unit:
            return True
    return False


def bullet_text(bullet: Any) -> str:
    return str(bullet.get("text", "")) if isinstance(bullet, dict) else str(bullet)


def validate_plan(plan: dict[str, Any], ledger: dict[str, Any], assets_document: dict[str, Any],
                  case: Any, ledger_path: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    errors: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []

    def error(code: str, message: str, **location: Any) -> None:
        errors.append({"code": code, "message": message, **location})

    if not isinstance(plan, dict):
        error("plan_type", "deck_plan.json must contain a JSON object.")
        return {"valid": False, "errors": errors, "warnings": warnings}, {}
    if case_identifier(case) != "unknown_case" and plan.get("case_id") != case_identifier(case):
        error("case_id", "Plan case_id must match the original case.json.", expected=case_identifier(case), actual=plan.get("case_id"))
    spans = {item.get("span_id"): item for item in ledger.get("spans", [])}
    assets = {item.get("asset_id"): item for item in assets_document.get("assets", [])}
    evidence_list = plan.get("evidence")
    if not isinstance(evidence_list, list):
        error("evidence_list", "Plan evidence must be a list.")
        evidence_list = []
    evidence: dict[str, dict[str, Any]] = {}
    for index, anchor in enumerate(evidence_list):
        eid = anchor.get("id") if isinstance(anchor, dict) else None
        if not isinstance(anchor, dict) or not eid:
            error("evidence_schema", "Each evidence anchor needs id, span_id, and quote.", evidence_index=index)
            continue
        if eid in evidence:
            error("duplicate_evidence", f"Duplicate evidence ID: {eid}", evidence_id=eid)
            continue
        evidence[eid] = anchor
        span_id = anchor.get("span_id")
        quote = anchor.get("quote")
        if span_id not in spans:
            error("missing_span", f"Evidence {eid} references unknown span {span_id!r}; copy span_id from source_ledger.json.", evidence_id=eid)
            continue
        if not isinstance(quote, str) or not normalize_text(quote):
            error("empty_quote", f"Evidence {eid} needs a nonempty raw quote.", evidence_id=eid)
            continue
        span = spans[span_id]
        if normalize_text(quote) not in span["normalized_text"]:
            error("quote_mismatch", f"Evidence {eid} quote is not an exact normalized substring of {span_id}; copy raw text without paraphrasing.", evidence_id=eid, span_id=span_id, quote=quote)
        source = next((item for item in ledger.get("sources", []) if item.get("source_id") == span.get("source_id")), None)
        if not source:
            error("missing_source", f"Span {span_id} has no ledger source.", evidence_id=eid)
            continue
        source_path = Path(source["path"])
        if not source_path.is_file():
            error("source_unavailable", f"Source file is unavailable: {source_path}", evidence_id=eid)
        else:
            actual_hash = sha256(source_path)
            if actual_hash != span.get("source_sha256") or actual_hash != source.get("sha256"):
                error("source_hash", f"Source hash changed for {source_path}; rerun prepare and update evidence IDs.", evidence_id=eid, expected=span.get("source_sha256"), actual=actual_hash)
    slides = plan.get("slides")
    if not isinstance(slides, list) or not slides:
        error("slides", "Plan must contain at least one slide with actual narrative content.")
        slides = []
    expected_count = (plan.get("task_parameters") or {}).get("slide_count")
    if expected_count is not None and len(slides) != expected_count:
        error("slide_count", f"Task requests {expected_count} slides but plan has {len(slides)}.", expected=expected_count, actual=len(slides))
    mode = plan.get("mode", "generate")
    if mode not in {"generate", "adapt"}:
        error("mode", "Plan mode must be generate or adapt.", mode=mode)
    removed_ids = plan.get("remove_slide_ids", [])
    if not isinstance(removed_ids, list) or len(removed_ids) != len(set(removed_ids)):
        error("remove_slide_ids", "remove_slide_ids must be a list of unique original slide IDs.")
        removed_ids = []
    source_refs = [slide.get("source_slide_id") for slide in slides
                   if isinstance(slide, dict) and slide.get("source_slide_id")]
    if len(source_refs) != len(set(source_refs)):
        error("source_slide_id", "Each original slide may be targeted by at most one final slide.")
    if mode == "adapt":
        try:
            from pptx import Presentation
            base_path = Path(plan.get("template_path") or "")
            original_ids = [f"original-{index:04d}" for index in range(1, len(Presentation(base_path).slides) + 1)]
            known = set(original_ids)
            for ref in source_refs + removed_ids:
                if ref not in known:
                    error("source_slide_id", f"Unknown original slide ID {ref!r}; inspect template_inventory.json.", source_slide_id=ref)
            accounted = source_refs + removed_ids
            for original in original_ids:
                if original not in accounted:
                    error("original_accounting", f"Original slide {original} is not targeted or explicitly removed.", source_slide_id=original)
            for slide in slides:
                if isinstance(slide, dict) and slide.get("source_slide_id") and (
                    "layout_name" in slide or "layout_index" in slide
                ):
                    error("layout_replacement", "Adapt edits preserve an existing slide's native layout; omit layout overrides.", slide_id=slide.get("id"))
        except Exception as exc:
            error("adapt_base", f"Cannot inspect adaptation base: {exc}")
    elif source_refs or removed_ids:
        error("generation_accounting", "source_slide_id/remove_slide_ids are adapt-only; generation removes recorded template example slides.")
    seen_slide_ids: Counter = Counter(str(slide.get("id")) for slide in slides if isinstance(slide, dict))
    slide_maps = []
    numeric_checks = 0
    for index, slide in enumerate(slides):
        slide_id = str(slide.get("id", f"index-{index + 1}")) if isinstance(slide, dict) else f"index-{index + 1}"
        if not isinstance(slide, dict):
            error("slide_schema", "Slide must be an object.", slide_index=index)
            continue
        if not slide.get("id") or seen_slide_ids[slide_id] > 1:
            error("slide_id", f"Slide ID missing or duplicated: {slide_id}", slide_id=slide_id)
        if slide.get("kind") not in SLIDE_KINDS:
            error("slide_kind", f"Unsupported kind {slide.get('kind')!r}; use {sorted(SLIDE_KINDS)}.", slide_id=slide_id)
        for field in ("title", "takeaway", "notes", "evidence", "figures"):
            if field not in slide:
                error("slide_field", f"Slide is missing required field {field!r}.", slide_id=slide_id)
        title = str(slide.get("title", ""))
        takeaway = str(slide.get("takeaway", ""))
        if not title.strip():
            error("title", "Slide title cannot be blank.", slide_id=slide_id)
        if len(title) > 90:
            error("text_budget", f"Title is {len(title)} characters; maximum is 90 to avoid overflow.", slide_id=slide_id, field="title")
        if len(takeaway) > 220:
            error("text_budget", f"Takeaway is {len(takeaway)} characters; maximum is 220.", slide_id=slide_id, field="takeaway")
        slide_eids = slide.get("evidence") if isinstance(slide.get("evidence"), list) else []
        if not slide_eids:
            error("slide_evidence", "Every slide needs source evidence, including title/section slides with factual framing.", slide_id=slide_id)
        for eid in slide_eids:
            if eid not in evidence:
                error("unknown_evidence_ref", f"Slide references undefined evidence {eid!r}.", slide_id=slide_id, evidence_id=eid)
        bullets = slide.get("bullets", [])
        if not isinstance(bullets, list):
            error("bullets", "Slide bullets must be a list.", slide_id=slide_id)
            bullets = []
        if len(bullets) > MAX_BULLETS:
            error("text_budget", f"Slide has {len(bullets)} bullets; maximum is {MAX_BULLETS}.", slide_id=slide_id)
        total_characters = len(title) + len(takeaway)
        units: list[tuple[str, str, list[str]]] = [("title", title, slide_eids), ("takeaway", takeaway, slide_eids)]
        for bullet_index, bullet in enumerate(bullets):
            text = bullet_text(bullet)
            own_eids = bullet.get("evidence", []) if isinstance(bullet, dict) else slide_eids
            if not isinstance(bullet, dict):
                warnings.append({"code": "implicit_bullet_binding", "message": "String bullet inherits slide evidence; prefer {text,evidence:[...]} for precise binding.", "slide_id": slide_id, "bullet_index": bullet_index})
            if not text.strip():
                error("bullet_text", "Bullet text cannot be empty.", slide_id=slide_id, bullet_index=bullet_index)
            if len(text) > 170:
                error("text_budget", f"Bullet is {len(text)} characters; maximum is 170.", slide_id=slide_id, bullet_index=bullet_index)
            total_characters += len(text)
            if not own_eids:
                error("bullet_evidence", "Bullet has no evidence binding; bind it explicitly rather than deleting factual content.", slide_id=slide_id, bullet_index=bullet_index)
            for eid in own_eids:
                if eid not in evidence:
                    error("unknown_evidence_ref", f"Bullet references undefined evidence {eid!r}.", slide_id=slide_id, bullet_index=bullet_index, evidence_id=eid)
                if eid not in slide_eids:
                    error("slide_evidence_closure", f"Bullet evidence {eid!r} must also appear in the slide evidence list.", slide_id=slide_id, evidence_id=eid)
            units.append((f"bullet[{bullet_index}]", text, own_eids))
        if total_characters > 900:
            error("text_budget", f"Slide text totals {total_characters} characters; maximum is 900.", slide_id=slide_id)
        figures = slide.get("figures", [])
        if not isinstance(figures, list):
            error("figures", "Slide figures must be a list.", slide_id=slide_id)
            figures = []
        if len(figures) > 2:
            error("figure_budget", "At most two source assets per slide are supported.", slide_id=slide_id)
        figure_map = []
        anchored_caption_text = ""
        for figure_index, figure in enumerate(figures):
            if not isinstance(figure, dict) or figure.get("asset_id") not in assets:
                error("asset", f"Unknown asset_id {figure.get('asset_id') if isinstance(figure, dict) else None!r}; select an ID from asset_candidates.json.", slide_id=slide_id, figure_index=figure_index)
                continue
            asset = assets[figure["asset_id"]]
            figure_eids = figure.get("evidence", [])
            if not figure_eids:
                error("figure_evidence", "Selected source asset needs evidence for its caption/interpretation.", slide_id=slide_id, asset_id=asset["asset_id"])
            for eid in figure_eids:
                if eid not in evidence:
                    error("unknown_evidence_ref", f"Figure references undefined evidence {eid!r}.", slide_id=slide_id, evidence_id=eid)
                if eid not in slide_eids:
                    error("slide_evidence_closure", f"Figure evidence {eid!r} must also appear in slide evidence.", slide_id=slide_id, evidence_id=eid)
            bbox = figure.get("bbox", asset["bbox"])
            if not isinstance(bbox, list) or len(bbox) != 4 or not all(isinstance(value, (int, float)) and math.isfinite(value) for value in bbox):
                error("bbox", "Explicit crop bbox must be four finite PDF-point coordinates [x0,y0,x1,y1].", slide_id=slide_id, asset_id=asset["asset_id"])
            elif bbox[2] <= bbox[0] or bbox[3] <= bbox[1]:
                error("bbox", "Crop bbox must have positive width and height.", slide_id=slide_id, asset_id=asset["asset_id"])
            source = next((item for item in ledger.get("sources", []) if item.get("source_id") == asset.get("source_id")), None)
            if not source or not Path(source["path"]).is_file() or sha256(Path(source["path"])) != asset.get("source_sha256"):
                error("source_hash", "Selected asset source is missing or changed; rerun prepare.", slide_id=slide_id, asset_id=asset["asset_id"])
            anchored_caption_text += " " + asset["caption"]
            figure_map.append({"asset_id": asset["asset_id"], "source_id": asset["source_id"],
                               "page_number": asset["page_number"], "source_caption": asset["caption"],
                               "bbox": bbox, "evidence": figure_eids})
        for unit, text, eids in units:
            for token in numeric_tokens(text):
                numeric_checks += 1
                supporting = [eid for eid in eids if eid in evidence]
                quote_text = "\n".join(str(evidence[eid].get("quote", "")) for eid in supporting)
                # Source captions are metadata anchors for Figure/Table references, not relabeled results.
                combined = quote_text + ("\n" + anchored_caption_text if re.search(r"(?:Figure|Fig\.?|Table)\s*" + re.escape(token) + r"\b", text, re.I) else "")
                if not numeric_supported(token, combined):
                    error("unsupported_numeric", f"Numeric token {token!r} in {unit} is not supported by its bound evidence. Bind the exact source span or revise the text; do not drop the token automatically.", slide_id=slide_id, unit=unit, token=token, bound_evidence=eids)
        resolved = []
        for eid in slide_eids:
            if eid not in evidence:
                continue
            anchor = evidence[eid]
            span = spans.get(anchor.get("span_id"), {})
            resolved.append({"evidence_id": eid, "span_id": anchor.get("span_id"),
                             "source_id": span.get("source_id"), "page_number": span.get("page_number"),
                             "raw_quote": anchor.get("quote"), "qualifier": anchor.get("qualifier"),
                             "context": span.get("block_text"), "span_bbox": span.get("bbox")})
        slide_maps.append({"slide_id": slide_id, "source_slide_id": slide.get("source_slide_id"),
                           "preserve": bool(slide.get("preserve")), "title": title,
                           "evidence": resolved, "figures": figure_map})
    report = {"valid": not errors, "error_count": len(errors), "warning_count": len(warnings),
              "numeric_token_count": numeric_checks, "evidence_count": len(evidence), "slide_count": len(slides),
              "errors": errors, "warnings": warnings, "ledger": str(ledger_path),
              "normalization": "NFKC + whitespace/ligature normalization for matching; raw quote and context retained"}
    evidence_map = {"case_id": case_identifier(case), "slides": slide_maps}
    return report, evidence_map
