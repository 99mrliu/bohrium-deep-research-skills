#!/usr/bin/env python3
"""Native PPTX edit transactions, OOXML auditing, source evidence, and render QA.

Only python-pptx, PyMuPDF, Pillow, and the Python standard library are used.
The base deck is an immutable input: all writes target a copy or new artifacts.
"""
from __future__ import annotations

import copy
import hashlib
import json
import os
import posixpath
import re
import shutil
import subprocess
import sys
import tempfile
import unicodedata
import zipfile
from pathlib import Path
from typing import Any
from urllib.parse import unquote

import fitz
from PIL import Image
from pptx import Presentation
from pptx.enum.shapes import MSO_SHAPE_TYPE, PP_PLACEHOLDER
from lxml import etree

NS = {
    "a": "http://schemas.openxmlformats.org/drawingml/2006/main",
    "p": "http://schemas.openxmlformats.org/presentationml/2006/main",
    "r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships",
    "pr": "http://schemas.openxmlformats.org/package/2006/relationships",
}
SLIDE_REL = "{" + NS["r"] + "}id"


class TransactionError(RuntimeError):
    """A plan, source, native transaction, or audit cannot be accepted."""


def dump_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def file_sha(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def norm_text(text: str) -> str:
    text = unicodedata.normalize("NFKC", text or "")
    text = text.replace("ﬁ", "fi").replace("ﬂ", "fl")
    return re.sub(r"\s+", " ", text).strip()


def compact_text(text: str) -> str:
    text = norm_text(text)
    return re.sub(r"[\s•▪◦·]+", "", text)


def rels_name(part: str) -> str:
    return posixpath.join(posixpath.dirname(part), "_rels", posixpath.basename(part) + ".rels")


def resolve_part(source_part: str, target: str) -> str:
    target = unquote(target)
    if target.startswith("/"):
        return posixpath.normpath(target.lstrip("/"))
    return posixpath.normpath(posixpath.join(posixpath.dirname(source_part), target))


def xml(data: bytes) -> etree._Element:
    return etree.fromstring(data)


def package_parts(path: Path) -> dict[str, str]:
    with zipfile.ZipFile(path) as zf:
        return {name: sha(zf.read(name)) for name in zf.namelist() if not name.endswith("/")}


def related_parts(zf: zipfile.ZipFile, source_part: str, suffix: str) -> list[str]:
    rn = rels_name(source_part)
    if rn not in zf.namelist():
        return []
    root = xml(zf.read(rn))
    answer = []
    for rel in root.findall("pr:Relationship", NS):
        if rel.get("TargetMode") == "External":
            continue
        if rel.get("Type", "").endswith(suffix):
            answer.append(resolve_part(source_part, rel.get("Target", "")))
    return answer


def layout_inventory(prs: Presentation) -> list[dict[str, Any]]:
    records = []
    for mi, master in enumerate(prs.slide_masters):
        for li, layout in enumerate(master.slide_layouts):
            records.append({
                "idx": len(records),
                "master_index": mi,
                "layout_index": li,
                "name": layout.name,
                "part": str(layout.part.partname).lstrip("/"),
                "placeholders": [{
                    "idx": ph.placeholder_format.idx,
                    "type": str(ph.placeholder_format.type),
                    "name": ph.name,
                    "left": ph.left, "top": ph.top, "width": ph.width, "height": ph.height,
                } for ph in layout.placeholders],
            })
    return records


def audit_package(path: Path) -> dict[str, Any]:
    """Audit slide inheritance and membership directly from OOXML relationships."""
    with zipfile.ZipFile(path) as zf:
        names = set(zf.namelist())
        pres = xml(zf.read("ppt/presentation.xml"))
        prels = xml(zf.read("ppt/_rels/presentation.xml.rels"))
        relmap = {r.get("Id"): r for r in prels.findall("pr:Relationship", NS)}
        master_members = {
            e.get(SLIDE_REL) for e in pres.findall("p:sldMasterIdLst/p:sldMasterId", NS)
        }
        slides = []
        for pos, sid in enumerate(pres.findall("p:sldIdLst/p:sldId", NS), 1):
            rid = sid.get(SLIDE_REL)
            rel = relmap.get(rid)
            if rel is None:
                raise TransactionError(f"Slide relationship {rid} is absent in {path}")
            part = resolve_part("ppt/presentation.xml", rel.get("Target", ""))
            layouts = related_parts(zf, part, "/slideLayout")
            layout = layouts[0] if layouts else None
            masters = related_parts(zf, layout, "/slideMaster") if layout else []
            master = masters[0] if masters else None
            themes = related_parts(zf, master, "/theme") if master else []
            theme = themes[0] if themes else None
            chain = [part, layout, master, theme]
            hashes = {p: sha(zf.read(p)) if p in names else None for p in chain if p}
            slides.append({
                "position": pos,
                "slide_id": int(sid.get("id")),
                "relationship_id": rid,
                "part": part,
                "layout_part": layout,
                "master_part": master,
                "theme_part": theme,
                "hashes": hashes,
                "slide_relationships_hash": sha(zf.read(rels_name(part))) if rels_name(part) in names else None,
                "membership": {
                    "slide_in_presentation": True,
                    "layout_part_exists": layout in names,
                    "master_part_exists": master in names,
                    "theme_part_exists": theme in names,
                    "master_in_presentation": bool(master and any(
                        m.get(SLIDE_REL) in master_members and
                        resolve_part("ppt/presentation.xml", relmap[m.get(SLIDE_REL)].get("Target", "")) == master
                        for m in pres.findall("p:sldMasterIdLst/p:sldMasterId", NS)
                        if m.get(SLIDE_REL) in relmap
                    )),
                },
            })
        sldsz = pres.find("p:sldSz", NS)
        dimensions = {"cx": int(sldsz.get("cx")), "cy": int(sldsz.get("cy"))} if sldsz is not None else None
        layouts = sorted(n for n in names if re.fullmatch(r"ppt/slideLayouts/slideLayout\d+\.xml", n))
        masters = sorted(n for n in names if re.fullmatch(r"ppt/slideMasters/slideMaster\d+\.xml", n))
        notes_masters = sorted(n for n in names if re.fullmatch(r"ppt/notesMasters/notesMaster\d+\.xml", n))
        themes = sorted(n for n in names if re.fullmatch(r"ppt/theme/theme\d+\.xml", n))
        return {
            "path": str(path),
            "dimensions": dimensions,
            "slides": slides,
            "layout_hashes": {n: sha(zf.read(n)) for n in layouts},
            "master_hashes": {n: sha(zf.read(n)) for n in masters},
            "notes_master_hashes": {n: sha(zf.read(n)) for n in notes_masters},
            "theme_hashes": {n: sha(zf.read(n)) for n in themes},
            "part_hashes": {n: sha(zf.read(n)) for n in sorted(names) if not n.endswith("/")},
        }


def inspect_deck(path: Path) -> dict[str, Any]:
    prs = Presentation(str(path))
    auditor = audit_package(path)
    layouts = layout_inventory(prs)
    by_part = {x["part"]: x for x in layouts}
    slides = []
    for idx, slide in enumerate(prs.slides):
        base = auditor["slides"][idx]
        shape_records = []
        for shape in slide.shapes:
            rec = {
                "name": shape.name,
                "shape_type": str(shape.shape_type),
                "left": shape.left, "top": shape.top, "width": shape.width, "height": shape.height,
            }
            if shape.is_placeholder:
                rec["placeholder"] = {"idx": shape.placeholder_format.idx, "type": str(shape.placeholder_format.type)}
            if getattr(shape, "has_text_frame", False):
                rec["text"] = shape.text
            shape_records.append(rec)
        slides.append({
            "id": f"original-{idx + 1:04d}",
            "source_slide_id": base["slide_id"],
            "part": base["part"],
            "layout_name": slide.slide_layout.name,
            "layout_idx": by_part.get(str(slide.slide_layout.part.partname).lstrip("/"), {}).get("idx"),
            "text": "\n".join(s.text for s in slide.shapes if getattr(s, "has_text_frame", False) and s.text),
            "placeholders": [{
                "idx": s.placeholder_format.idx, "type": str(s.placeholder_format.type), "name": s.name,
            } for s in slide.placeholders],
            "shapes": shape_records,
            "identity_hash": kept_identity(auditor, idx),
        })
    return {
        "path": str(path),
        "sha256": file_sha(path),
        "slide_count": len(prs.slides),
        "dimensions": auditor["dimensions"],
        "masters": len(prs.slide_masters),
        "layouts": layouts,
        "slides": slides,
        "native_audit": auditor,
    }


def kept_identity(audit: dict[str, Any], slide_index: int) -> str:
    s = audit["slides"][slide_index]
    payload = s["hashes"].get(s["part"], "") + ":" + (s["slide_relationships_hash"] or "")
    return sha(payload.encode("ascii"))


def looks_like_path(value: str) -> bool:
    return bool(re.search(r"\.(?:pdf|pptx|md|json)$", value, re.I)) or "/" in value or "\\" in value


def explicit_materials(case: Any, root: Path) -> list[dict[str, str]]:
    found: list[dict[str, str]] = []

    def add(raw: str, context: str, role: str = "") -> None:
        candidate = Path(raw).expanduser()
        if not candidate.is_absolute():
            candidate = root / candidate
        try:
            candidate = candidate.resolve()
        except OSError:
            return
        if candidate.is_file() and candidate.suffix.lower() in {".pdf", ".pptx", ".md", ".json"}:
            found.append({"path": str(candidate), "context": context, "role": role})
        elif candidate.is_dir():
            for p in sorted(candidate.rglob("*")):
                if p.is_file() and p.suffix.lower() in {".pdf", ".pptx"}:
                    found.append({"path": str(p.resolve()), "context": context + "/recursive", "role": role})

    def walk(obj: Any, context: str, inherited_role: str = "") -> None:
        if isinstance(obj, dict):
            role = str(obj.get("role", inherited_role) or "")
            for key, value in obj.items():
                walk(value, f"{context}/{key}", role)
        elif isinstance(obj, list):
            for i, value in enumerate(obj):
                walk(value, f"{context}/{i}", inherited_role)
        elif isinstance(obj, str) and looks_like_path(obj):
            add(obj, context, inherited_role)

    walk(case, "case")
    return found


def discover_inputs(input_dir: Path) -> tuple[dict[str, Any], list[str]]:
    uncertainties: list[str] = []
    case_path = input_dir / "case.json"
    case = load_json(case_path) if case_path.exists() else {}
    task_path = input_dir / "task.md"
    task = task_path.read_text(encoding="utf-8") if task_path.exists() else ""
    records = explicit_materials(case, input_dir)
    known = {r["path"] for r in records}
    if task_path.exists() and str(task_path.resolve()) not in known:
        records.append({"path": str(task_path.resolve()), "context": "input/task.md", "role": "workorder"})
    for p in sorted(input_dir.rglob("*")):
        if p.is_file() and p.suffix.lower() in {".pdf", ".pptx"} and str(p.resolve()) not in known:
            records.append({"path": str(p.resolve()), "context": "input/recursive", "role": ""})
            known.add(str(p.resolve()))
    # Multiple mentions retain role evidence but only one actual path is inventoried.
    grouped: dict[str, list[dict[str, str]]] = {}
    for rec in records:
        grouped.setdefault(rec["path"], []).append(rec)
    pdfs, decks = [], []
    for path, mentions in sorted(grouped.items()):
        p = Path(path)
        if not p.exists():
            continue
        roles = sorted({m["role"] for m in mentions if m["role"]})
        contexts = sorted({m["context"] for m in mentions})
        if p.suffix.lower() == ".pdf":
            pdfs.append({"path": path, "roles": roles, "contexts": contexts})
        elif p.suffix.lower() == ".pptx":
            try:
                deck = inspect_deck(p)
                deck.update({"roles": roles, "contexts": contexts})
                decks.append(deck)
            except Exception as exc:
                uncertainties.append(f"PPTX inspection failed for {path}: {exc}")
    if not decks:
        raise TransactionError("No inspectable PPTX starting deck or template was discovered")
    case_text = json.dumps(case, ensure_ascii=False) + "\n" + task
    mode_match = re.search(r"\b(generate|generation|adapt|edit)\b", case_text, re.I)
    mode = mode_match.group(1).lower() if mode_match else "adapt"
    if mode == "generation":
        mode = "generate"

    def has_role(deck: dict[str, Any], words: tuple[str, ...]) -> bool:
        role_text = " ".join(deck["roles"] + deck["contexts"]).lower()
        return any(word in role_text for word in words)

    starting = [d for d in decks if has_role(d, ("starting_deck", "starting-deck", "start_deck", "source_deck"))]
    templates = [d for d in decks if has_role(d, ("template", "template_deck"))]
    if mode == "generate":
        candidates = templates or starting
        role_reason = "explicit template role" if templates else "explicit starting-deck role used as generation template"
    else:
        candidates = starting or templates
        role_reason = "explicit starting-deck role" if starting else "explicit template role used as adaptation base"
    if candidates:
        base = candidates[0]
        if len(candidates) > 1:
            uncertainties.append("Multiple decks shared the selected role; the first explicit material was selected.")
    elif len(decks) == 1:
        base = decks[0]
        role_reason = "only actual PPTX; role selected by transaction mode"
    else:
        # Role-independent fallback uses actual deck structure, never filename/domain labels.
        base = max(decks, key=lambda d: (d["slide_count"], len(d["layouts"]), d["masters"]))
        role_reason = "no explicit role; greatest actual slide/layout/master structure selected"
        uncertainties.append("Deck roles were not explicit; structural selection is uncertain. Declare roles in case materials.")
    explicit_examples = case.get("example_slide_ids", []) if isinstance(case, dict) else []
    valid_ids = {s["id"] for s in base["slides"]}
    example_ids = [x for x in explicit_examples if x in valid_ids]
    if mode == "generate" and not example_ids:
        example_ids = [s["id"] for s in base["slides"]]
        example_reason = "all pre-existing slides in the selected generation template are recorded examples"
    else:
        example_reason = "explicit case.example_slide_ids"
    constraints = parse_constraints(case, task)
    inventory = {
        "schema_version": "1.0",
        "input_dir": str(input_dir),
        "case_id": case.get("case_id", case.get("id", "unknown")) if isinstance(case, dict) else "unknown",
        "case": case,
        "task_path": str(task_path) if task_path.exists() else None,
        "task_text": task,
        "mode": mode,
        "constraints": constraints,
        "pdf_paths": [p["path"] for p in pdfs],
        "pptx_paths": [d["path"] for d in decks],
        "decks": decks,
        "base_path": base["path"],
        "base_role": "template" if mode == "generate" else "starting_deck",
        "base_selection_reason": role_reason,
        "base_slide_ids": [s["id"] for s in base["slides"]],
        "base": base,
        "example_slide_ids": example_ids,
        "example_slide_reason": example_reason,
    }
    return inventory, uncertainties


def parse_constraints(case: Any, task: str) -> dict[str, Any]:
    result: dict[str, Any] = {"slide_count": None, "audience": None, "minutes": None}
    count_keys = {"slide_count", "slides", "num_slides", "n_slides", "slidecount"}
    minute_keys = {"minutes", "time_minutes", "duration_minutes", "presentation_minutes"}
    audience_keys = {"audience", "target_audience"}

    def walk(obj: Any) -> None:
        if isinstance(obj, dict):
            for key, value in obj.items():
                k = key.lower()
                if k in count_keys and isinstance(value, int) and value > 0:
                    result["slide_count"] = value
                elif k in minute_keys and isinstance(value, (int, float)) and value > 0:
                    result["minutes"] = value
                elif k in audience_keys and isinstance(value, str) and value.strip():
                    result["audience"] = value.strip()
                else:
                    walk(value)
        elif isinstance(obj, list):
            for value in obj:
                walk(value)
    walk(case)
    if result["slide_count"] is None:
        m = re.search(r"\b(\d+)\s*(?:slides?|页(?:幻灯片)?)\b", task, re.I)
        if m:
            result["slide_count"] = int(m.group(1))
    if result["minutes"] is None:
        m = re.search(r"\b(\d+(?:\.\d+)?)\s*(?:minutes?|mins?|分钟)\b", task, re.I)
        if m:
            result["minutes"] = float(m.group(1)) if "." in m.group(1) else int(m.group(1))
    if result["audience"] is None:
        m = re.search(r"(?:audience|听众|受众)\s*[:：]\s*([^\n;.]+)", task, re.I)
        if m:
            result["audience"] = m.group(1).strip()
    return result


def extract_sources(inventory: dict[str, Any], work: Path) -> dict[str, Any]:
    assets = work / "assets"
    assets.mkdir(parents=True, exist_ok=True)
    documents = []
    for di, pdf_path in enumerate(inventory["pdf_paths"], 1):
        source_id = f"pdf-{di:04d}"
        doc = fitz.open(pdf_path)
        record = {"source_id": source_id, "path": pdf_path, "sha256": file_sha(Path(pdf_path)),
                  "extractor": "PyMuPDF", "page_count": len(doc), "pages": []}
        for pi, page in enumerate(doc, 1):
            page_id = f"{source_id}-p{pi:04d}"
            lines = []
            data = page.get_text("dict")
            line_no = 0
            for block in data.get("blocks", []):
                if block.get("type") != 0:
                    continue
                for line in block.get("lines", []):
                    spans = line.get("spans", [])
                    text = "".join(s.get("text", "") for s in spans)
                    if not norm_text(text):
                        continue
                    line_no += 1
                    lines.append({
                        "quote_id": f"{page_id}-l{line_no:04d}",
                        "text": text,
                        "bbox": list(line.get("bbox", ())),
                        "spans": [{"text": s.get("text", ""), "bbox": list(s.get("bbox", ())), "font": s.get("font"), "size": s.get("size")} for s in spans],
                    })
            render_path = assets / f"{page_id}.png"
            pix = page.get_pixmap(matrix=fitz.Matrix(1.6, 1.6), alpha=False)
            pix.save(str(render_path))
            images = []
            for ii, info in enumerate(page.get_images(full=True), 1):
                xref = info[0]
                try:
                    extracted = doc.extract_image(xref)
                    ext = extracted.get("ext", "bin")
                    image_path = assets / f"{page_id}-image{ii:03d}.{ext}"
                    image_path.write_bytes(extracted["image"])
                    with Image.open(image_path) as im:
                        im.verify()
                    images.append(str(image_path))
                except Exception:
                    if 'image_path' in locals() and image_path.exists():
                        image_path.unlink()
            record["pages"].append({
                "page": pi,
                "text": page.get_text("text"),
                "lines": lines,
                "rendered_page": str(render_path),
                "extracted_images": images,
            })
        documents.append(record)
        doc.close()
    return {"schema_version": "1.0", "documents": documents}


def contract_fields(case: Any) -> list[str]:
    """Extract field names, never schema descriptor keys such as type/description."""
    if not isinstance(case, dict):
        return []
    contract = case.get("output_contract", case.get("fields", []))
    names: list[str] = []

    def add(value: Any) -> None:
        if value is not None and str(value) and str(value) not in names:
            names.append(str(value))

    def walk(node: Any) -> None:
        if isinstance(node, str):
            add(node)
        elif isinstance(node, list):
            for item in node:
                if isinstance(item, dict):
                    descriptor = next((item[key] for key in ("name", "field", "key", "id", "path")
                                       if key in item and isinstance(item[key], (str, int))), None)
                    add(descriptor) if descriptor is not None else walk(item)
                else:
                    walk(item)
        elif isinstance(node, dict):
            if "fields" in node:
                walk(node["fields"])
                return
            descriptor = next((node[key] for key in ("name", "field", "key", "id", "path")
                               if key in node and isinstance(node[key], (str, int))), None)
            if descriptor is not None:
                add(descriptor)
            else:
                for field_name in node:
                    add(field_name)

    walk(contract)
    return names


def input_source_paths(inventory: dict[str, Any]) -> list[str]:
    paths = list(inventory.get("pdf_paths", [])) + list(inventory.get("pptx_paths", []))
    if inventory.get("task_path"):
        paths.append(inventory["task_path"])
    return list(dict.fromkeys(paths))


def base_result(inventory: dict[str, Any], status: str, uncertainties: list[str]) -> dict[str, Any]:
    case = inventory.get("case") if isinstance(inventory.get("case"), dict) else {}
    result = {
        "case_id": inventory["case_id"],
        "status": status,
        "sources": input_source_paths(inventory),
        "uncertainty": uncertainties,
        "change_log": [],
        "artifacts": [],
        "output_contract": case.get("output_contract", case.get("fields", [])),
    }
    for field in contract_fields(case):
        if field not in result:
            result[field] = None
    return result


def prepare(input_dir: Path, work: Path, output: Path) -> dict[str, Any]:
    work.mkdir(parents=True, exist_ok=True)
    output.mkdir(parents=True, exist_ok=True)
    inventory, uncertainties = discover_inputs(input_dir)
    dump_json(work / "native_inventory.json", inventory)
    dump_json(output / "native_inventory.json", inventory)
    sources = extract_sources(inventory, work)
    dump_json(work / "source_index.json", sources)
    dump_json(output / "source_index.json", sources)
    ids = inventory["base_slide_ids"]
    meta = {
        "title": "Native deck transaction",
        "audience": inventory["constraints"]["audience"],
        "minutes": inventory["constraints"]["minutes"],
        "slide_count": inventory["constraints"]["slide_count"],
        "visual_review": {"status": "pending", "pages": [], "corrections": []},
    }
    plan = {
        "schema_version": "1.0",
        "mode": inventory["mode"],
        "base_path": inventory["base_path"],
        "base_slide_ids": ids,
        "meta": meta,
        "operations": [{"op": "keep", "id": x} for x in ids] + [{"op": "reorder", "final_order": ids}],
    }
    dump_json(work / "transaction_plan.json", plan)
    result = base_result(inventory, "partial", uncertainties + ["Preparation only: transaction operations and rendering are not complete."])
    result["change_log"] = [{"event": "prepare", "detail": "Inventoried actual inputs, PDF evidence spans, native layouts, and original slide IDs."}]
    result["artifacts"] = [str(output / n) for n in ("native_inventory.json", "source_index.json")] + [str(work / "transaction_plan.json")]
    dump_json(output / "result.json", result)
    return {"inventory": inventory, "sources": sources, "plan": plan, "result": result}


def source_maps(sources: dict[str, Any]) -> tuple[dict[str, dict[str, Any]], dict[str, dict[str, Any]]]:
    docs = {d["source_id"]: d for d in sources["documents"]}
    quotes = {line["quote_id"]: line for d in sources["documents"] for p in d["pages"] for line in p["lines"]}
    return docs, quotes


def validate_evidence(spec: dict[str, Any], sources: dict[str, Any], label: str) -> list[str]:
    if spec.get("presentation_metadata"):
        return []
    errors = []
    evidence = spec.get("evidence", [])
    if not evidence:
        return [f"{label}: edited/new scientific content requires source evidence"]
    docs, quotes = source_maps(sources)
    supported_text = []
    for ei, ev in enumerate(evidence):
        elabel = f"{label}.evidence[{ei}]"
        sid, page, quote = ev.get("source_id"), ev.get("page"), ev.get("quote")
        doc = docs.get(sid)
        if not doc:
            errors.append(f"{elabel}: unknown source_id {sid!r}")
            continue
        source_path = Path(doc["path"])
        if not source_path.is_file() or file_sha(source_path) != doc.get("sha256"):
            errors.append(f"{elabel}: source is missing or changed since prepare; rerun prepare: {source_path}")
            continue
        pages = [p for p in doc["pages"] if p["page"] == page]
        if not pages:
            errors.append(f"{elabel}: source page {page!r} does not exist")
            continue
        if not isinstance(quote, str) or not norm_text(quote):
            errors.append(f"{elabel}: an exact nonempty quote is required")
            continue
        if compact_text(quote) not in compact_text(pages[0]["text"]):
            errors.append(f"{elabel}: quote is not exact text on the cited page")
        qid = ev.get("quote_id")
        if qid:
            line = quotes.get(qid)
            if not line or compact_text(line["text"]) != compact_text(quote) or not qid.startswith(f"{sid}-p{int(page):04d}-"):
                errors.append(f"{elabel}: quote_id does not match source/page/quote")
        if not (ev.get("section") or ev.get("figure") or page):
            errors.append(f"{elabel}: page, section, or figure reference is required")
        supported_text.append(quote)
    text = "\n".join([str(spec.get("title", ""))] + [b.get("text", "") if isinstance(b, dict) else str(b) for b in spec.get("bullets", [])])
    numbers = re.findall(r"(?<![A-Za-z])\d+(?:\.\d+)?%?", text)
    evidence_compact = compact_text(" ".join(supported_text))
    for token in numbers:
        if compact_text(token) not in evidence_compact:
            errors.append(f"{label}: numerical token {token!r} is absent from attached evidence; support it or mark presentation_metadata")
    return errors


def all_layouts(prs: Presentation) -> list[Any]:
    return [layout for master in prs.slide_masters for layout in master.slide_layouts]


def choose_layout(prs: Presentation, spec: dict[str, Any], current: Any = None) -> Any:
    if spec.get("layout_idx") is None and spec.get("layout") is None:
        if current is not None:
            return current
        raise TransactionError(f"{spec.get('id')}: append requires layout or layout_idx")
    layouts = all_layouts(prs)
    if spec.get("layout_idx") is not None:
        idx = spec["layout_idx"]
        if not isinstance(idx, int) or isinstance(idx, bool) or not 0 <= idx < len(layouts):
            raise TransactionError(f"{spec.get('id')}: dangling layout_idx {idx!r}")
        return layouts[idx]
    name = spec.get("layout")
    matches = [layout for layout in layouts if layout.name == name]
    if len(matches) != 1:
        raise TransactionError(f"{spec.get('id')}: layout name {name!r} has {len(matches)} matches; use a valid global layout_idx")
    return matches[0]


def validate_plan(plan: dict[str, Any], inventory: dict[str, Any], sources: dict[str, Any]) -> list[str]:
    errors = []
    base_ids = inventory["base_slide_ids"]
    if plan.get("base_slide_ids") != base_ids:
        errors.append("base_slide_ids must exactly match inventory order")
    if Path(plan.get("base_path", "")).resolve() != Path(inventory["base_path"]).resolve():
        errors.append("base_path does not match the inventoried immutable base")
    if plan.get("mode") != inventory["mode"]:
        errors.append("plan mode differs from inventoried mode")
    operations = plan.get("operations")
    if not isinstance(operations, list):
        return errors + ["operations must be a list"]
    original_ops: dict[str, str] = {}
    final_ids, seen = [], set()
    reorders = [op for op in operations if isinstance(op, dict) and op.get("op") == "reorder"]
    for oi, op in enumerate(operations):
        if not isinstance(op, dict):
            errors.append(f"operations[{oi}] must be an object")
            continue
        kind, oid = op.get("op"), op.get("id")
        if kind == "reorder":
            if op is not operations[-1]:
                errors.append("reorder must be the final operation")
            order = op.get("final_order")
            if not isinstance(order, list):
                errors.append("reorder.final_order must be a list")
            continue
        if kind not in {"keep", "edit", "append", "remove"}:
            errors.append(f"operations[{oi}]: unsupported op {kind!r}")
            continue
        if not isinstance(oid, str) or not oid or oid in seen:
            errors.append(f"operations[{oi}]: missing or duplicate id {oid!r}")
            continue
        seen.add(oid)
        if kind == "append":
            if oid in base_ids:
                errors.append(f"{oid}: append id collides with an original slide")
            final_ids.append(oid)
        else:
            if oid not in base_ids:
                errors.append(f"{oid}: unknown original slide ID")
                continue
            if oid in original_ops:
                errors.append(f"{oid}: original slide has multiple accounting operations")
            original_ops[oid] = kind
            if kind != "remove":
                final_ids.append(oid)
        if kind in {"edit", "append"}:
            if kind == "edit" and op.get("source_slide_id") != oid:
                errors.append(f"{oid}: edit.source_slide_id must equal the targeted original ID")
            errors.extend(validate_evidence(op, sources, oid))
            for key in ("title_placeholder_idx", "body_placeholder_idx"):
                if key in op and (not isinstance(op[key], int) or isinstance(op[key], bool) or op[key] < 0):
                    errors.append(f"{oid}: {key} must be a nonnegative placeholder idx")
            for fi, figure in enumerate(op.get("figures", [])):
                if not isinstance(figure, dict):
                    errors.append(f"{oid}.figures[{fi}]: must be an object")
                    continue
                path = figure.get("path")
                sid, page = figure.get("source_id"), figure.get("page")
                if path and not Path(path).is_file():
                    errors.append(f"{oid}.figures[{fi}]: image path does not exist: {path}")
                elif not path:
                    docs, _ = source_maps(sources)
                    doc = docs.get(sid)
                    if not doc or not any(p["page"] == page for p in doc["pages"]):
                        errors.append(f"{oid}.figures[{fi}]: figure requires an existing path or valid source_id/page")
    for oid in base_ids:
        if oid not in original_ops:
            errors.append(f"missing original slide accounting: {oid}")
    if len(reorders) != 1:
        errors.append("exactly one reorder operation with explicit final order is required")
    else:
        order = reorders[0].get("final_order", [])
        if len(order) != len(set(order)):
            errors.append("reorder.final_order contains duplicates")
        if set(order) != set(final_ids) or len(order) != len(final_ids):
            errors.append("reorder.final_order must contain every retained/appended ID exactly once and no removed IDs")
    constraints = inventory["constraints"]
    expected = constraints.get("slide_count")
    if expected is not None and len(final_ids) != expected:
        errors.append(f"fixed slide count {expected} is not met: final deck has {len(final_ids)}")
    meta = plan.get("meta", {})
    if constraints.get("audience") and meta.get("audience") != constraints["audience"]:
        errors.append("plan meta.audience does not match the fixed audience")
    if constraints.get("minutes") is not None and meta.get("minutes") != constraints["minutes"]:
        errors.append("plan meta.minutes does not match the fixed presentation time")
    if inventory["mode"] == "generate":
        allowed = set(inventory["example_slide_ids"])
        for oid, kind in original_ops.items():
            if kind == "remove" and oid not in allowed:
                errors.append(f"generate mode may remove only recorded example slides: {oid}")
    # Resolve layouts and placeholder membership against the actual base.
    try:
        prs = Presentation(inventory["base_path"])
        layouts = all_layouts(prs)
        slide_by_id = {f"original-{i + 1:04d}": slide for i, slide in enumerate(prs.slides)}
        for op in operations:
            if not isinstance(op, dict) or op.get("op") not in {"edit", "append"}:
                continue
            oid = op.get("id")
            try:
                current = slide_by_id[oid].slide_layout if op["op"] == "edit" else None
                layout = choose_layout(prs, op, current)
                valid_layout_idx = {ph.placeholder_format.idx for ph in layout.placeholders}
                valid_slide_idx = {ph.placeholder_format.idx for ph in current.placeholders} if current is not None else set()
                for key in ("title_placeholder_idx", "body_placeholder_idx"):
                    if key in op:
                        valid = valid_slide_idx if op["op"] == "edit" else valid_layout_idx
                        if op[key] not in valid:
                            errors.append(f"{oid}: {key} {op[key]} is not a valid placeholder idx on the target")
                for fig in op.get("figures", []):
                    if "placeholder_idx" in fig and fig["placeholder_idx"] not in valid_layout_idx:
                        errors.append(f"{oid}: figure placeholder_idx {fig['placeholder_idx']} is absent from layout")
            except TransactionError as exc:
                errors.append(str(exc))
    except Exception as exc:
        errors.append(f"could not validate native layouts/placeholders: {exc}")
    return errors


def set_text(shape: Any, text: str) -> None:
    if not getattr(shape, "has_text_frame", False):
        raise TransactionError(f"Placeholder {shape.name} does not contain a text frame")
    # Clearing runs is deliberately local to this authorized placeholder. Theme,
    # layout inheritance, paragraph properties, and every other shape stay intact.
    shape.text_frame.clear()
    shape.text_frame.paragraphs[0].text = text


def placeholder_by_idx(slide: Any, idx: int) -> Any:
    for ph in slide.placeholders:
        if ph.placeholder_format.idx == idx:
            return ph
    raise TransactionError(f"Placeholder idx {idx} is absent on slide")


def title_shape(slide: Any, spec: dict[str, Any]) -> Any:
    if "title_placeholder_idx" in spec:
        return placeholder_by_idx(slide, spec["title_placeholder_idx"])
    shape = slide.shapes.title
    if shape is None:
        raise TransactionError(f"{spec.get('id')}: title edit requested but no title placeholder exists")
    return shape


def body_shape(slide: Any, spec: dict[str, Any]) -> Any:
    if "body_placeholder_idx" in spec:
        return placeholder_by_idx(slide, spec["body_placeholder_idx"])
    candidates = []
    for ph in slide.placeholders:
        pht = ph.placeholder_format.type
        if pht in (PP_PLACEHOLDER.TITLE, PP_PLACEHOLDER.CENTER_TITLE, PP_PLACEHOLDER.SUBTITLE,
                   PP_PLACEHOLDER.FOOTER, PP_PLACEHOLDER.SLIDE_NUMBER, PP_PLACEHOLDER.DATE):
            continue
        if getattr(ph, "has_text_frame", False):
            candidates.append(ph)
    if not candidates:
        raise TransactionError(f"{spec.get('id')}: bullets requested but no native body placeholder exists")
    return max(candidates, key=lambda s: s.width * s.height)


def set_bullets(shape: Any, bullets: list[Any]) -> None:
    tf = shape.text_frame
    tf.clear()
    for i, item in enumerate(bullets):
        data = {"text": str(item), "level": 0} if not isinstance(item, dict) else item
        p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
        p.text = str(data.get("text", ""))
        p.level = int(data.get("level", 0))


def evidence_notes(spec: dict[str, Any], inherited_notes: str = "") -> str:
    # An omitted notes property preserves the original speaker notes; evidence
    # is appended rather than becoming an implicit erase operation.
    notes = str(spec["notes"]) if "notes" in spec else inherited_notes
    lines = []
    for ev in spec.get("evidence", []):
        ref = f"{ev.get('source_id')} p.{ev.get('page')}"
        if ev.get("section"):
            ref += f" section {ev['section']}"
        if ev.get("figure"):
            ref += f" {ev['figure']}"
        if ev.get("quote_id"):
            ref += f" {ev['quote_id']}"
        lines.append(f"{ref}: {ev.get('quote', '')}")
    if lines:
        notes += ("\n\n" if notes else "") + "Sources:\n" + "\n".join(lines)
    return notes


def figure_path(figure: dict[str, Any], sources: dict[str, Any]) -> str:
    if figure.get("path"):
        return figure["path"]
    docs, _ = source_maps(sources)
    doc = docs[figure["source_id"]]
    page = next(p for p in doc["pages"] if p["page"] == figure["page"])
    if figure.get("extracted_image_index") is not None:
        return page["extracted_images"][figure["extracted_image_index"]]
    return page["rendered_page"]


def add_aspect_fit_picture(slide: Any, image_path: str, box: tuple[int, int, int, int]) -> Any:
    left, top, width, height = box
    with Image.open(image_path) as im:
        iw, ih = im.size
    if iw <= 0 or ih <= 0 or width <= 0 or height <= 0:
        raise TransactionError(f"Invalid image or placement dimensions for {image_path}")
    scale = min(width / iw, height / ih)
    w, h = int(iw * scale), int(ih * scale)
    x, y = int(left + (width - w) / 2), int(top + (height - h) / 2)
    return slide.shapes.add_picture(image_path, x, y, w, h)


def add_figures(slide: Any, spec: dict[str, Any], sources: dict[str, Any]) -> None:
    figures = spec.get("figures", [])
    if not figures:
        return
    body = None
    try:
        body = body_shape(slide, spec)
    except TransactionError:
        pass
    auto_figures = [figure for figure in figures if "placeholder_idx" not in figure]
    auto_index = 0
    for figure in figures:
        if "placeholder_idx" in figure:
            target = placeholder_by_idx(slide, figure["placeholder_idx"])
            box = (target.left, target.top, target.width, target.height)
        else:
            if body is not None:
                # Reserve the upper portion for explicitly supplied bullets.
                top = body.top + (body.height // 2 if spec.get("bullets") else 0)
                container = (body.left, top, body.width, max(1, body.top + body.height - top))
            else:
                title = slide.shapes.title
                top = title.top + title.height if title is not None else 0
                sldsz = slide.part.package.presentation_part._element.sldSz
                container = (0, top, sldsz.cx, sldsz.cy - top)
            # Multiple automatic figures receive nonoverlapping vertical slots;
            # explicit placeholder targets retain their native geometry.
            left, top, width, height = container
            slot = max(1, height // len(auto_figures))
            figure_top = top + auto_index * slot
            figure_height = height - auto_index * slot if auto_index == len(auto_figures) - 1 else slot
            box = (left, figure_top, width, figure_height)
            auto_index += 1
        add_aspect_fit_picture(slide, figure_path(figure, sources), box)


def restore_kept_parts(base_path: Path, output_path: Path, base_audit: dict[str, Any], keep_indexes: list[int], work: Path) -> None:
    replacements: dict[str, bytes] = {}
    with zipfile.ZipFile(base_path) as base:
        for idx in keep_indexes:
            slide = base_audit["slides"][idx]
            for part in (slide["part"], rels_name(slide["part"])):
                if part in base.namelist():
                    replacements[part] = base.read(part)
    temp = work / "presentation-restored.pptx"
    with zipfile.ZipFile(output_path) as src, zipfile.ZipFile(temp, "w") as dst:
        for info in src.infolist():
            dst.writestr(info, replacements.get(info.filename, src.read(info.filename)))
    temp.replace(output_path)


def direct_dependencies(base_path: Path, slide_part: str) -> set[str]:
    protected = {slide_part, rels_name(slide_part)}
    with zipfile.ZipFile(base_path) as zf:
        rn = rels_name(slide_part)
        if rn not in zf.namelist():
            return protected
        root = xml(zf.read(rn))
        for rel in root.findall("pr:Relationship", NS):
            if rel.get("TargetMode") == "External" or rel.get("Type", "").endswith("/slideLayout"):
                continue
            part = resolve_part(slide_part, rel.get("Target", ""))
            protected.add(part)
            protected.add(rels_name(part))
    return protected


def native_diff(base_path: Path, final_path: Path, plan: dict[str, Any]) -> dict[str, Any]:
    before, after = audit_package(base_path), audit_package(final_path)
    base_parts, final_parts = before["part_hashes"], after["part_hashes"]
    changed = sorted(p for p in base_parts.keys() & final_parts.keys() if base_parts[p] != final_parts[p])
    added = sorted(final_parts.keys() - base_parts.keys())
    removed = sorted(base_parts.keys() - final_parts.keys())
    opmap = {op["id"]: op for op in plan["operations"] if op.get("op") in {"keep", "edit", "remove"}}
    keep_indexes = [i for i, oid in enumerate(plan["base_slide_ids"]) if opmap.get(oid, {}).get("op") == "keep"]
    edit_indexes = [i for i, oid in enumerate(plan["base_slide_ids"]) if opmap.get(oid, {}).get("op") == "edit"]
    remove_indexes = [i for i, oid in enumerate(plan["base_slide_ids"]) if opmap.get(oid, {}).get("op") == "remove"]
    kept = []
    for idx in keep_indexes:
        oid = plan["base_slide_ids"][idx]
        old = before["slides"][idx]
        matches = [s for s in after["slides"] if s["slide_id"] == old["slide_id"]]
        current = matches[0] if matches else None
        kept.append({
            "id": oid,
            "original_slide_id": old["slide_id"],
            "original_identity_hash": kept_identity(before, idx),
            "final_identity_hash": sha((current["hashes"].get(current["part"], "") + ":" + (current["slide_relationships_hash"] or "")).encode("ascii")) if current else None,
            "byte_identical_slide_and_relationships": bool(current and kept_identity(before, idx) == sha((current["hashes"].get(current["part"], "") + ":" + (current["slide_relationships_hash"] or "")).encode("ascii"))),
            "inheritance_chain_unchanged": bool(current and all(current[k] == old[k] for k in ("layout_part", "master_part", "theme_part"))),
        })
    protected_keep = set()
    for idx in keep_indexes:
        protected_keep |= direct_dependencies(base_path, before["slides"][idx]["part"])
    allowed = {
        "[Content_Types].xml", "_rels/.rels", "ppt/presentation.xml", "ppt/_rels/presentation.xml.rels",
        "ppt/presProps.xml", "ppt/viewProps.xml", "ppt/tableStyles.xml",
    }
    for idx in edit_indexes:
        part = before["slides"][idx]["part"]
        allowed |= {part, rels_name(part)}
    for idx in remove_indexes:
        part = before["slides"][idx]["part"]
        allowed |= {part, rels_name(part)}
        allowed |= direct_dependencies(base_path, part)
    with zipfile.ZipFile(final_path) as final_zip:
        notes_themes = {
            theme
            for notes_master in after["notes_master_hashes"]
            for theme in related_parts(final_zip, notes_master, "/theme")
        }
    unauthorized = []
    for part in changed + added + removed:
        if part in allowed or part.startswith("docProps/"):
            continue
        if part in protected_keep:
            unauthorized.append(part)
            continue
        if part in added and re.fullmatch(r"ppt/slides/(?:_rels/)?slide\d+\.xml(?:\.rels)?", part):
            continue
        if part.startswith(("ppt/notesSlides/", "ppt/notesMasters/")):
            continue
        if part in added and part in notes_themes:
            continue
        if part.startswith(("ppt/media/", "ppt/embeddings/")) and part not in removed:
            continue
        unauthorized.append(part)
    chain_failures = []
    for slide in after["slides"]:
        if not all(slide["membership"].values()):
            chain_failures.append({"slide_id": slide["slide_id"], "membership": slide["membership"]})
    dimensions_same = before["dimensions"] == after["dimensions"]
    themes_untouched = all(after["theme_hashes"].get(p) == h for p, h in before["theme_hashes"].items())
    layouts_untouched = before["layout_hashes"] == after["layout_hashes"]
    masters_untouched = before["master_hashes"] == after["master_hashes"]
    notes_masters_untouched = all(after["notes_master_hashes"].get(p) == h for p, h in before["notes_master_hashes"].items())
    added_notes_themes = sorted(p for p in notes_themes if p in added)
    notes_changed = [p for p in changed if p.startswith("ppt/notesSlides/")]
    notes_added = [p for p in added if p.startswith("ppt/notesSlides/")]
    media_added = [p for p in added if p.startswith("ppt/media/")]
    passed = (not unauthorized and not chain_failures and dimensions_same and themes_untouched and
              layouts_untouched and masters_untouched and notes_masters_untouched and
              all(k["byte_identical_slide_and_relationships"] and k["inheritance_chain_unchanged"] for k in kept))
    return {
        "schema_version": "1.0",
        "passed": passed,
        "deterministic_zip_required": False,
        "dimensions_same": dimensions_same,
        "theme_untouched": themes_untouched,
        "layouts_untouched": layouts_untouched,
        "masters_untouched": masters_untouched,
        "notes_masters_untouched": notes_masters_untouched,
        "added_notes_themes": added_notes_themes,
        "kept_slides": kept,
        "changed_parts": changed,
        "added_parts": added,
        "removed_parts": removed,
        "allowed_changed_parts": sorted(allowed),
        "unauthorized_changed_parts": unauthorized,
        "inheritance_chain_failures": chain_failures,
        "new_media": media_added,
        "notes_changes": {"changed": notes_changed, "added": notes_added},
        "final_native_audit": {k: v for k, v in after.items() if k != "part_hashes"},
    }


def apply_plan(plan: dict[str, Any], inventory: dict[str, Any], sources: dict[str, Any], work: Path, output: Path) -> tuple[Path, dict[str, Any]]:
    errors = validate_plan(plan, inventory, sources)
    if errors:
        raise TransactionError("Transaction plan rejected:\n - " + "\n - ".join(errors))
    base_path = Path(inventory["base_path"])
    copied_base = work / "immutable-base-copy.pptx"
    shutil.copy2(base_path, copied_base)
    prs = Presentation(str(copied_base))
    base_audit = audit_package(copied_base)
    initial = {f"original-{i + 1:04d}": slide for i, slide in enumerate(prs.slides)}
    final_slides = dict(initial)
    keep_indexes = []
    for op in plan["operations"]:
        kind = op.get("op")
        if kind == "reorder":
            continue
        oid = op["id"]
        if kind == "keep":
            keep_indexes.append(plan["base_slide_ids"].index(oid))
            continue
        if kind == "remove":
            slide = final_slides[oid]
            # Resolve the relationship from python-pptx's current presentation part.
            for sldId in list(prs.slides._sldIdLst):
                if prs.part.related_part(sldId.rId) is slide.part:
                    prs.part.drop_rel(sldId.rId)
                    prs.slides._sldIdLst.remove(sldId)
                    break
            del final_slides[oid]
            continue
        if kind == "append":
            layout = choose_layout(prs, op)
            slide = prs.slides.add_slide(layout)
            final_slides[oid] = slide
        else:
            slide = final_slides[oid]
            if op.get("layout") is not None or op.get("layout_idx") is not None:
                desired = choose_layout(prs, op, slide.slide_layout)
                if desired.part != slide.slide_layout.part:
                    raise TransactionError(f"{oid}: changing an existing slide's layout is not supported; omit layout to preserve inheritance")
        if "title" in op:
            set_text(title_shape(slide, op), str(op["title"]))
        if "bullets" in op:
            set_bullets(body_shape(slide, op), op["bullets"])
        add_figures(slide, op, sources)
        if "notes" in op or op.get("evidence"):
            inherited = slide.notes_slide.notes_text_frame.text if kind == "edit" else ""
            slide.notes_slide.notes_text_frame.text = evidence_notes(op, inherited)
    reorder = plan["operations"][-1]
    by_part = {slide.part: oid for oid, slide in final_slides.items()}
    elements = list(prs.slides._sldIdLst)
    elem_by_oid = {}
    for element in elements:
        part = prs.part.related_part(element.rId)
        if part in by_part:
            elem_by_oid[by_part[part]] = element
    for element in elements:
        prs.slides._sldIdLst.remove(element)
    for oid in reorder["final_order"]:
        prs.slides._sldIdLst.append(elem_by_oid[oid])
    output_path = output / "presentation.pptx"
    prs.save(str(output_path))
    restore_kept_parts(base_path, output_path, base_audit, keep_indexes, work)
    diff = native_diff(base_path, output_path, plan)
    dump_json(output / "native_diff.json", diff)
    if not diff["passed"]:
        problems = []
        if diff["unauthorized_changed_parts"]:
            problems.append("unauthorized parts: " + ", ".join(diff["unauthorized_changed_parts"]))
        if diff["inheritance_chain_failures"]:
            problems.append("slide-layout-master-theme membership failure")
        if not diff["themes_untouched"]:
            problems.append("theme changed")
        if not diff["layouts_untouched"] or not diff["masters_untouched"]:
            problems.append("layout/master bytes changed")
        if not diff["notes_masters_untouched"]:
            problems.append("existing notes master bytes changed")
        if not all(k["byte_identical_slide_and_relationships"] for k in diff["kept_slides"]):
            problems.append("kept slide identity changed")
        raise TransactionError("Native diff failed: " + "; ".join(problems))
    return output_path, diff


def shape_texts(slide: Any) -> list[str]:
    texts = []

    def collect(shape: Any) -> None:
        if getattr(shape, "has_text_frame", False):
            for p in shape.text_frame.paragraphs:
                if norm_text(p.text):
                    texts.append(p.text)
        if getattr(shape, "has_table", False):
            for row in shape.table.rows:
                for cell in row.cells:
                    for p in cell.text_frame.paragraphs:
                        if norm_text(p.text):
                            texts.append(p.text)
        if shape.shape_type == MSO_SHAPE_TYPE.GROUP:
            for child in shape.shapes:
                collect(child)

    for shape in slide.shapes:
        collect(shape)
    return texts


def find_soffice() -> str | None:
    configured = os.environ.get("SOFFICE")
    candidates = [configured, shutil.which("soffice"), shutil.which("libreoffice"),
                  "/Applications/LibreOffice.app/Contents/MacOS/soffice",
                  "/usr/bin/soffice", "/usr/local/bin/soffice"]
    return next((p for p in candidates if p and Path(p).is_file() and os.access(p, os.X_OK)), None)


def render_pdf(pptx: Path, work: Path, output: Path) -> tuple[Path | None, dict[str, Any]]:
    soffice = find_soffice()
    if not soffice:
        return None, {"renderer_available": False, "status": "unavailable", "uncertainty": "No soffice renderer was found; real PDF/PNG QA was not possible."}
    render_dir = work / "render"
    render_dir.mkdir(parents=True, exist_ok=True)
    profile = work / "lo-profile"
    profile.mkdir(parents=True, exist_ok=True)
    cmd = [soffice, "--headless", f"-env:UserInstallation={profile.resolve().as_uri()}", "--convert-to", "pdf", "--outdir", str(render_dir), str(pptx)]
    pdf = render_dir / (pptx.stem + ".pdf")
    if pdf.exists():
        pdf.unlink()
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=180)
        if proc.returncode != 0 or not pdf.exists():
            return None, {"renderer_available": True, "status": "failed", "command": cmd, "stdout": proc.stdout, "stderr": proc.stderr}
        destination = output / "presentation.pdf"
        shutil.copy2(pdf, destination)
        return destination, {"renderer_available": True, "status": "rendered", "command": cmd, "stdout": proc.stdout, "stderr": proc.stderr}
    except Exception as exc:
        return None, {"renderer_available": True, "status": "failed", "command": cmd, "error": str(exc)}


def make_previews(pdf: Path, work: Path, output: Path) -> tuple[list[Path], dict[str, Any]]:
    preview_dir = output / "previews"
    preview_dir.mkdir(parents=True, exist_ok=True)
    for old in preview_dir.glob("preview-*.png"):
        old.unlink()
    pdftoppm = shutil.which("pdftoppm")
    try:
        if pdftoppm:
            prefix = preview_dir / "preview"
            proc = subprocess.run([pdftoppm, "-png", "-r", "110", str(pdf), str(prefix)], capture_output=True, text=True, timeout=180)
            if proc.returncode:
                raise TransactionError(proc.stderr)
            def page_number(path: Path) -> int:
                match = re.search(r"(\d+)$", path.stem)
                return int(match.group(1)) if match else 0
            raw = sorted(preview_dir.glob("preview-*.png"), key=page_number)
            method = "pdftoppm"
        else:
            doc = fitz.open(pdf)
            raw = []
            for i, page in enumerate(doc, 1):
                p = preview_dir / f"preview-{i:03d}.png"
                page.get_pixmap(matrix=fitz.Matrix(1.5, 1.5), alpha=False).save(str(p))
                raw.append(p)
            doc.close()
            method = "PyMuPDF"
        normalized = []
        for i, p in enumerate(raw, 1):
            target = preview_dir / f"preview-{i:03d}.png"
            if p != target:
                p.replace(target)
            normalized.append(target)
        return normalized, {"status": "rendered", "method": method}
    except Exception as exc:
        return [], {"status": "failed", "error": str(exc)}


def font_report(pptx: Path, renderer_log: str) -> dict[str, Any]:
    fonts = set()
    sizes = []
    with zipfile.ZipFile(pptx) as zf:
        for name in zf.namelist():
            if re.fullmatch(r"ppt/slides/slide\d+\.xml", name):
                root = xml(zf.read(name))
                for node in root.xpath("//*[@typeface]"):
                    if node.get("typeface") and not node.get("typeface").startswith("+"):
                        fonts.add(node.get("typeface"))
                for node in root.xpath("//*[@sz]"):
                    if node.tag.startswith("{" + NS["a"] + "}") and node.get("sz", "").isdigit():
                        sizes.append({"part": name, "tag": etree.QName(node).localname, "points": int(node.get("sz")) / 100})
    fc = shutil.which("fc-list")
    families = set()
    fc_error = None
    if fc:
        try:
            proc = subprocess.run([fc, ":", "family"], capture_output=True, text=True, timeout=30)
            if proc.returncode == 0:
                for line in proc.stdout.splitlines():
                    for family in line.split(","):
                        families.add(family.strip().lower())
            else:
                fc_error = proc.stderr
        except Exception as exc:
            fc_error = str(exc)
    potential_missing = sorted(f for f in fonts if families and f.lower() not in families)
    log_signals = [line for line in renderer_log.splitlines() if re.search(r"font.*(?:fallback|not.?found|missing)", line, re.I)]
    if not fc and not log_signals:
        status = "unavailable"
    elif potential_missing or log_signals:
        status = "potential_fallback"
    else:
        status = "no_signal_best_effort"
    return {
        "status": status,
        "detection_is_not_confirmation": True,
        "explicit_typefaces": sorted(fonts),
        "fc_list_available": bool(fc),
        "fc_list_error": fc_error,
        "potential_missing_explicit_fonts": potential_missing,
        "renderer_log_signals": log_signals,
        "explicit_font_sizes": sizes,
        "inherited_sizes_not_inferred": True,
    }


def render_qa(pptx: Path, pdf: Path | None, previews: list[Path], renderer: dict[str, Any], preview_info: dict[str, Any], plan: dict[str, Any]) -> dict[str, Any]:
    prs = Presentation(str(pptx))
    width, height = prs.slide_width, prs.slide_height
    expected = [shape_texts(slide) for slide in prs.slides]
    expected_images = {op["id"]: len(op.get("figures", [])) for op in plan["operations"] if op.get("op") in {"edit", "append"}}
    ordered_ids = plan["operations"][-1]["final_order"]
    geometry, intersections, image_checks = [], [], []
    for i, slide in enumerate(prs.slides):
        oid = ordered_ids[i]
        title_footer = []
        for shape in slide.shapes:
            if shape.is_placeholder and shape.placeholder_format.type in (
                PP_PLACEHOLDER.TITLE, PP_PLACEHOLDER.CENTER_TITLE, PP_PLACEHOLDER.FOOTER,
                PP_PLACEHOLDER.SLIDE_NUMBER, PP_PLACEHOLDER.DATE,
            ):
                title_footer.append(shape)
        for shape in slide.shapes:
            outside = shape.left < 0 or shape.top < 0 or shape.left + shape.width > width or shape.top + shape.height > height
            if outside:
                geometry.append({"slide": i + 1, "id": oid, "shape": shape.name, "bounds": [shape.left, shape.top, shape.width, shape.height], "warning": "OOXML geometry outside slide; decorative bleed may be intentional"})
            if shape in title_footer:
                continue
            for protected in title_footer:
                ix = max(0, min(shape.left + shape.width, protected.left + protected.width) - max(shape.left, protected.left))
                iy = max(0, min(shape.top + shape.height, protected.top + protected.height) - max(shape.top, protected.top))
                if ix * iy > 0.1 * min(shape.width * shape.height, protected.width * protected.height):
                    intersections.append({"slide": i + 1, "shape": shape.name, "intersects": protected.name})
        actual_pictures = sum(1 for shape in slide.shapes if shape.shape_type == MSO_SHAPE_TYPE.PICTURE)
        wanted = expected_images.get(oid, 0)
        image_checks.append({"slide": i + 1, "id": oid, "expected_new_images": wanted, "pptx_picture_count": actual_pictures, "present": actual_pictures >= wanted})
    minimum = plan.get("meta", {}).get("minimum_explicit_font_pt", 12)
    fonts = font_report(pptx, (renderer.get("stdout", "") + "\n" + renderer.get("stderr", "")))
    small_fonts = [x for x in fonts["explicit_font_sizes"] if x["points"] < minimum]
    report = {
        "schema_version": "1.0",
        "renderer": renderer,
        "preview_renderer": preview_info,
        "pdf_path": str(pdf) if pdf else None,
        "preview_paths": [str(p) for p in previews],
        "slide_count": len(prs.slides),
        "pdf_page_count": None,
        "page_count_matches": None,
        "lost_or_clipped_text": [],
        "geometry_outside_slide": geometry,
        "title_footer_intersections": intersections,
        "minimum_explicit_font_pt": minimum,
        "below_minimum_explicit_fonts": small_fonts,
        "inherited_font_sizes": "not inferred or shrunk blindly",
        "image_checks": image_checks,
        "font_fallback": fonts,
        "page_edge_ink_overflow_test": "not used",
        "visual_inspection": plan.get("meta", {}).get("visual_review", {"status": "pending"}),
        "passed": False,
    }
    if not pdf:
        report["uncertainty"] = "PDF was unavailable; text, page count, preview, and visual QA remain incomplete."
        return report
    try:
        doc = fitz.open(pdf)
        report["pdf_page_count"] = len(doc)
        report["page_count_matches"] = len(doc) == len(prs.slides)
        for i, page in enumerate(doc):
            actual = compact_text(page.get_text("text"))
            for text in expected[i] if i < len(expected) else []:
                needle = compact_text(text)
                if needle and needle not in actual:
                    report["lost_or_clipped_text"].append({"slide": i + 1, "expected_text": text, "pdf_text": page.get_text("text")})
            if i < len(image_checks) and image_checks[i]["expected_new_images"]:
                image_checks[i]["pdf_image_count_best_effort"] = len(page.get_images(full=True))
        page_dims = [{"page": i + 1, "width_pt": p.rect.width, "height_pt": p.rect.height} for i, p in enumerate(doc)]
        report["pdf_page_dimensions"] = page_dims
        doc.close()
        dims = []
        for i, p in enumerate(previews, 1):
            with Image.open(p) as im:
                dims.append({"page": i, "width_px": im.width, "height_px": im.height})
        report["preview_dimensions"] = dims
        previews_ok = len(previews) == len(prs.slides) and all(p.exists() for p in previews)
        report["passed"] = bool(report["page_count_matches"] and previews_ok and not report["lost_or_clipped_text"] and all(x["present"] for x in image_checks))
    except Exception as exc:
        report["qa_error"] = str(exc)
        report["uncertainty"] = "Rendered PDF could not be completely analyzed."
    return report


def semantic_result(result: dict[str, Any], inventory: dict[str, Any], output: Path, pptx: Path | None, pdf: Path | None, previews: list[Path], status: str) -> None:
    result["status"] = status
    artifacts = [str(p) for p in (pptx, pdf) if p] + [str(p) for p in previews]
    for name in ("native_inventory.json", "source_index.json", "transaction_plan.json", "evidence_map.json",
                 "native_diff.json", "render_report.json", "result.json"):
        p = output / name
        if p.exists() or name == "result.json":
            artifacts.append(str(p))
    result["artifacts"] = list(dict.fromkeys(artifacts))
    result["sources"] = input_source_paths(inventory)
    actual_slide_count = len(previews) if previews else None
    if pptx and pptx.exists():
        try:
            actual_slide_count = len(Presentation(str(pptx)).slides)
        except Exception:
            pass
    values = {
        "case_id": inventory["case_id"], "status": status, "success": status == "success",
        "pptx": str(pptx) if pptx else None, "pptx_path": str(pptx) if pptx else None,
        "presentation": str(pptx) if pptx else None, "presentation_path": str(pptx) if pptx else None,
        "editable_pptx": str(pptx) if pptx else None,
        "pdf": str(pdf) if pdf else None, "pdf_path": str(pdf) if pdf else None,
        "previews": [str(p) for p in previews], "preview_images": [str(p) for p in previews],
        "preview_paths": [str(p) for p in previews],
        "sources": result["sources"], "uncertainty": result["uncertainty"], "change_log": result["change_log"],
        "artifacts": result["artifacts"], "slide_count": actual_slide_count,
        "audience": inventory["constraints"].get("audience"), "minutes": inventory["constraints"].get("minutes"),
        "editable_source": str(pptx) if pptx else None,
        "export_artifact": str(pdf) if pdf else None,
        "content_map": str(output / "evidence_map.json") if (output / "evidence_map.json").exists() else None,
        "compliance_checks": {
            "native_diff": str(output / "native_diff.json") if (output / "native_diff.json").exists() else None,
            "render_report": str(output / "render_report.json") if (output / "render_report.json").exists() else None,
        },
        "exceptions": result["uncertainty"],
    }
    for field in contract_fields(inventory.get("case")):
        key = field.lower()
        normalized_key = re.sub(r"[^a-z0-9]", "", key)
        if normalized_key in {"editablesource", "editablepptx"}:
            result[field] = values["editable_source"]
        elif normalized_key in {"exportartifact", "pdfartifact", "rendereddeck"}:
            result[field] = values["export_artifact"]
        elif normalized_key in {"contentmap", "evidencemap"}:
            result[field] = values["content_map"]
        elif "compliance" in normalized_key or "validation" in normalized_key:
            result[field] = values["compliance_checks"]
        elif "exception" in normalized_key:
            result[field] = values["exceptions"]
        elif field in values:
            result[field] = values[field]
        elif key in values:
            result[field] = values[key]
        elif any(token in key for token in ("pptx", "presentation")) and not any(token in key for token in ("count", "theme")):
            result[field] = values["pptx"]
        elif "pdf" in key:
            result[field] = values["pdf"]
        elif "preview" in key or "png" in key:
            result[field] = values["previews"]
        elif "source" in key or "citation" in key:
            result[field] = values["sources"]
        elif "artifact" in key or "file" in key:
            result[field] = values["artifacts"]
        elif "uncertain" in key or "limitation" in key:
            result[field] = values["uncertainty"]
        elif "change" in key or "log" in key:
            result[field] = values["change_log"]
        elif "status" in key:
            result[field] = status


def finish(input_dir: Path, work: Path, output: Path, plan_path: Path | None = None) -> dict[str, Any]:
    output.mkdir(parents=True, exist_ok=True)
    inventory_path = work / "native_inventory.json"
    sources_path = work / "source_index.json"
    if not inventory_path.exists() or not sources_path.exists():
        prepared = prepare(input_dir, work, output)
        inventory, sources = prepared["inventory"], prepared["sources"]
    else:
        inventory, sources = load_json(inventory_path), load_json(sources_path)
    plan_path = plan_path or work / "transaction_plan.json"
    plan = load_json(plan_path)
    dump_json(output / "transaction_plan.json", plan)
    plan_operations = plan.get("operations", []) if isinstance(plan.get("operations"), list) else []
    reorders = [op for op in plan_operations if isinstance(op, dict) and op.get("op") == "reorder"]
    evidence_map = {
        "case_id": inventory["case_id"],
        "final_order": reorders[-1].get("final_order", []) if reorders else [],
        "slides": [{"id": op.get("id"), "op": op.get("op"), "source_slide_id": op.get("source_slide_id"),
                    "evidence": op.get("evidence", [])}
                   for op in plan_operations if isinstance(op, dict) and op.get("op") in {"edit", "append"}],
    }
    dump_json(output / "evidence_map.json", evidence_map)
    result = base_result(inventory, "failed", [])
    pptx = pdf = None
    previews: list[Path] = []
    candidate = output / "presentation.pptx"
    # Do not let artifacts from a previous plan masquerade as products of this
    # transaction. Only known generated outputs are cleared, never input files.
    for stale in (candidate, output / "presentation.pdf", output / "native_diff.json", output / "render_report.json"):
        if stale.exists():
            stale.unlink()
    preview_dir = output / "previews"
    if preview_dir.exists():
        for stale in preview_dir.glob("preview-*.png"):
            stale.unlink()
    try:
        pptx, diff = apply_plan(plan, inventory, sources, work, output)
        result["change_log"].append({"event": "native_transaction", "detail": "Applied authorized keep/edit/append/remove/reorder operations to a copy of the base deck; kept slide parts restored and audited."})
        result["status"] = "partial"
        pdf, renderer = render_pdf(pptx, work, output)
        if pdf:
            previews, preview_info = make_previews(pdf, work, output)
        else:
            preview_info = {"status": "unavailable"}
        qa = render_qa(pptx, pdf, previews, renderer, preview_info, plan)
        dump_json(output / "render_report.json", qa)
        if qa["passed"]:
            result["status"] = "success"
            result["change_log"].append({"event": "render_qa", "detail": "Real PDF/PNG rendering passed page count, text retention, preview, and expected-image checks."})
        else:
            result["uncertainty"].append("Native PPTX was produced, but render QA did not fully pass; inspect render_report.json.")
        if qa.get("geometry_outside_slide") or qa.get("title_footer_intersections") or qa.get("below_minimum_explicit_fonts"):
            result["uncertainty"].append("Render QA contains geometry, intersection, or explicit-font warnings requiring visual review; page-edge ink was not used as overflow evidence.")
        if qa.get("font_fallback", {}).get("status") in {"unavailable", "potential_fallback"}:
            result["uncertainty"].append("Font fallback is unavailable or only best-effort; see render_report.json.")
        if qa.get("visual_inspection", {}).get("status") != "complete":
            result["uncertainty"].append("Agent every-page visual inspection is pending or not marked complete in meta.visual_review.")
    except TransactionError as exc:
        pptx = candidate if candidate.is_file() else None
        pdf = output / "presentation.pdf" if (output / "presentation.pdf").is_file() else None
        result["status"] = "partial" if pptx else "failed"
        result["uncertainty"].append(str(exc))
        result["change_log"].append({"event": "failure", "detail": str(exc)})
    except Exception as exc:
        pptx = candidate if candidate.is_file() else None
        pdf = output / "presentation.pdf" if (output / "presentation.pdf").is_file() else None
        result["status"] = "partial" if pptx else "failed"
        result["uncertainty"].append(f"Unexpected transaction/render failure: {type(exc).__name__}: {exc}")
        result["change_log"].append({"event": "failure", "detail": str(exc)})
    semantic_result(result, inventory, output, pptx, pdf, previews, result["status"])
    dump_json(output / "result.json", result)
    return result
