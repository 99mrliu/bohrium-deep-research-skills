#!/usr/bin/env python3
"""Validate SBGN-inspired process semantics, render distinct arcs, and export.

Only explicit input model assertions are drawn. No relation is inferred.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import html
import json
import math
import re
import shutil
import subprocess
import sys
import unicodedata
from datetime import datetime, timezone
from pathlib import Path
import xml.etree.ElementTree as ET

BUNDLE = Path(__file__).resolve().parent.parent
PROCESS_TYPES = {"association", "dissociation", "phosphorylation", "ubiquitination", "transport", "transcription", "activation", "inhibition", "uncertain"}
EFFECTS = {"activation", "inhibition", "uncertain"}
STANDARD_FIELDS = ["case_id", "status", "editable_source", "export_artifact", "content_map", "compliance_checks", "exceptions", "sources", "uncertainty", "change_records"]
GLYPH = {"association": "ASSOC", "dissociation": "DISSOC", "phosphorylation": "P", "ubiquitination": "U", "transport": "T", "transcription": "Tx", "activation": "+", "inhibition": "INH", "uncertain": "?"}


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def norm(value: object) -> str:
    return " ".join(unicodedata.normalize("NFKC", str(value)).strip().split()).casefold()


def dump(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def contract_fields(case: dict) -> list[str]:
    contract = case.get("output_contract", STANDARD_FIELDS)
    names: list[str] = []
    if isinstance(contract, list):
        names = [x for x in contract if isinstance(x, str)]
    elif isinstance(contract, dict):
        candidate = None
        for key in ("result_fields", "required_result_fields", "fields", "required"):
            if isinstance(contract.get(key), list):
                candidate = contract[key]
                break
        if candidate is None and isinstance(contract.get("properties"), dict):
            candidate = list(contract["properties"])
        if candidate is not None:
            for item in candidate:
                if isinstance(item, str): names.append(item)
                elif isinstance(item, dict):
                    key = item.get("name") or item.get("key") or item.get("field")
                    if isinstance(key, str): names.append(key)
        else:
            names = [str(k) for k in contract]
    return list(dict.fromkeys(names + STANDARD_FIELDS))


class Result:
    def __init__(self, output: Path, case: dict):
        self.case_id = str(case.get("case_id", "unknown"))
        self.fields = contract_fields(case)
        self.values = {
            "case_id": self.case_id, "status": "partial", "editable_source": None,
            "export_artifact": None, "content_map": None,
            "compliance_checks": {"passed": False, "checks": [{"name": "run", "status": "started"}]},
            "exceptions": [], "sources": [], "uncertainty": [],
            "change_records": [{"at": now(), "action": "initialized_partial_result"}],
        }
        self.path = output / "result.json"
        self.write()

    def write(self) -> None:
        payload = {key: copy.deepcopy(self.values.get(key)) for key in self.fields}
        for key in ("sources", "uncertainty", "change_records"):
            payload[key] = copy.deepcopy(self.values[key])
        dump(self.path, payload)

    def error(self, code: str, message: str, fatal: bool = False) -> None:
        self.values["exceptions"].append({"code": code, "message": message, "fatal": fatal})
        self.values["status"] = "failed" if fatal else "partial"
        self.write()


def issue(code: str, message: str, **extra: object) -> dict:
    return {"code": code, "severity": "error", "message": message, **extra}


def validate_model(model: dict) -> tuple[list[dict], list[dict], list[dict]]:
    issues: list[dict] = []
    unknown: list[dict] = []
    arc_plan: list[dict] = []
    entities = model.get("entities")
    processes = model.get("processes")
    if not isinstance(entities, list) or not isinstance(processes, list):
        return [issue("MODEL_SHAPE", "model.entities and model.processes must be lists")], [], []
    by_entity: dict[str, dict] = {}
    for i, entity in enumerate(entities):
        if not isinstance(entity, dict):
            issues.append(issue("ENTITY_SHAPE", f"entities[{i}] must be an object")); continue
        cid = entity.get("canonical_id")
        if not isinstance(cid, str) or not re.fullmatch(r"[A-Za-z][A-Za-z0-9_.:-]*", cid):
            issues.append(issue("ENTITY_ID", f"entities[{i}] requires a safe canonical_id")); continue
        if cid in by_entity:
            issues.append(issue("DUPLICATE_ENTITY", f"Duplicate entity {cid}")); continue
        by_entity[cid] = entity
        if not isinstance(entity.get("label"), str) or not entity["label"].strip():
            issues.append(issue("ENTITY_LABEL", f"{cid} requires a nonempty label", canonical_id=cid))
        if "compartment" in entity and (not isinstance(entity["compartment"], str) or not entity["compartment"].strip()):
            issues.append(issue("COMPARTMENT", f"{cid}.compartment must be nonempty when present", canonical_id=cid))
    seen_processes: set[str] = set()
    for i, process in enumerate(processes):
        where = f"processes[{i}]"
        if not isinstance(process, dict):
            issues.append(issue("PROCESS_SHAPE", f"{where} must be an object")); continue
        pid = process.get("process_id")
        if not isinstance(pid, str) or not re.fullmatch(r"[A-Za-z][A-Za-z0-9_.:-]*", pid):
            issues.append(issue("PROCESS_ID", f"{where} requires a safe process_id")); continue
        if pid in seen_processes:
            issues.append(issue("DUPLICATE_PROCESS", f"Duplicate process_id {pid}")); continue
        seen_processes.add(pid)
        ptype = process.get("process_type")
        if ptype not in PROCESS_TYPES:
            issues.append(issue("PROCESS_TYPE", f"{pid} has unsupported process_type {ptype!r}", process_id=pid))
        inputs, outputs, modulators = process.get("inputs"), process.get("outputs"), process.get("modulators")
        if not isinstance(inputs, list) or not isinstance(outputs, list) or not isinstance(modulators, list):
            issues.append(issue("EXPLICIT_ARCS", f"{pid} requires explicit inputs, outputs, and modulators lists", process_id=pid))
            continue
        if not inputs and not outputs:
            issues.append(issue("EMPTY_PROCESS", f"{pid} requires at least one input or output", process_id=pid))
        for role, endpoints in (("input", inputs), ("output", outputs)):
            for j, endpoint in enumerate(endpoints):
                arc = {"arc_id": f"arc-{pid}-{role}-{j}", "process_id": pid, "arc_class": "consumption" if role == "input" else "production", "endpoint": endpoint, "endpoint_index": j}
                arc_plan.append(arc)
                if not isinstance(endpoint, str) or endpoint not in by_entity:
                    unknown.append(arc)
                    issues.append(issue("UNKNOWN_ENDPOINT", f"{pid} has unknown {role} endpoint {endpoint!r}", **arc))
        for j, modulator in enumerate(modulators):
            if not isinstance(modulator, dict):
                issues.append(issue("MODULATOR_SHAPE", f"{pid}.modulators[{j}] must be an object", process_id=pid)); continue
            endpoint, effect = modulator.get("entity_id"), modulator.get("effect")
            arc = {"arc_id": f"arc-{pid}-modulator-{j}", "process_id": pid, "arc_class": "modulation", "endpoint": endpoint, "endpoint_index": j, "effect": effect}
            arc_plan.append(arc)
            if not isinstance(endpoint, str) or endpoint not in by_entity:
                unknown.append(arc)
                issues.append(issue("UNKNOWN_ENDPOINT", f"{pid} has unknown modulator endpoint {endpoint!r}", **arc))
            if effect not in EFFECTS:
                issues.append(issue("MODULATOR_EFFECT", f"{pid} has invalid modulator effect {effect!r}", **arc))
        if ptype == "inhibition" and outputs:
            issues.append(issue("INHIBITION_PRODUCTION", f"{pid}: inhibition must not declare outputs or production arrows", process_id=pid, outputs=outputs))
        if ptype == "transport":
            source, target = process.get("from_compartment"), process.get("to_compartment")
            if not isinstance(source, str) or not source.strip() or not isinstance(target, str) or not target.strip():
                issues.append(issue("TRANSPORT_COMPARTMENTS", f"{pid}: transport requires from_compartment and to_compartment", process_id=pid))
            elif norm(source) == norm(target):
                issues.append(issue("TRANSPORT_SAME_COMPARTMENT", f"{pid}: transport compartments must differ", process_id=pid, from_compartment=source, to_compartment=target))
            if not inputs or not outputs:
                issues.append(issue("TRANSPORT_ARITY", f"{pid}: transport requires at least one input and one output", process_id=pid))
            if isinstance(source, str) and isinstance(target, str):
                for endpoint in inputs:
                    compartment = by_entity.get(endpoint, {}).get("compartment")
                    if compartment is not None and norm(compartment) != norm(source):
                        issues.append(issue("TRANSPORT_ORIGIN_MISMATCH", f"{pid}: input {endpoint} is not in {source}", process_id=pid, endpoint=endpoint))
                for endpoint in outputs:
                    compartment = by_entity.get(endpoint, {}).get("compartment")
                    if compartment is not None and norm(compartment) != norm(target):
                        issues.append(issue("TRANSPORT_DESTINATION_MISMATCH", f"{pid}: output {endpoint} is not in {target}", process_id=pid, endpoint=endpoint))
        locator = process.get("source_locator")
        if not isinstance(locator, dict) or not isinstance(locator.get("document"), str) or not isinstance(locator.get("locator"), str):
            issues.append(issue("SOURCE_LOCATOR", f"{pid} requires source_locator.document and .locator", process_id=pid))
    return issues, unknown, arc_plan


def get_pymupdf():
    try:
        import pymupdf
        return pymupdf
    except ImportError:
        import fitz
        return fitz


def inventory_sources(input_dir: Path, work: Path, case: dict) -> tuple[list[dict], list[str], str | None, Path | None]:
    sources, uncertainties = [], []
    caption, original = None, None
    for name in case.get("source_files", []):
        if not isinstance(name, str) or not (input_dir / name).is_file():
            raise ValueError(f"case.source_files entry is missing or invalid: {name!r}")
    pdf = None
    for path in sorted((p for p in input_dir.rglob("*") if p.is_file()), key=lambda p: str(p)):
        relative = path.relative_to(input_dir).as_posix(); lower = relative.lower()
        role = "supporting_source"
        if lower == "case.json": role = "case"
        elif lower == "task.md": role = "task"
        elif lower == "figure-workorder.json": role = "workorder"
        elif path.suffix.lower() == ".pdf": role = "paper_pdf"
        elif path.name.lower().startswith("figure03"): role = "figure03_original_or_caption"
        elif lower.startswith("data/"): role = "real_data" if not case.get("synthetic") else "synthetic_data"
        record = {"path": relative, "role": role, "bytes": path.stat().st_size,
                  "sha256": hashlib.sha256(path.read_bytes()).hexdigest(), "synthetic": bool(case.get("synthetic"))}
        sources.append(record)
        if path.name.lower().startswith("figure03") and path.suffix.lower() in {".txt", ".md"}:
            caption = path.read_text(encoding="utf-8")
            target = work / "source_text" / path.name
            target.parent.mkdir(parents=True, exist_ok=True); target.write_text(caption, encoding="utf-8")
        if path.suffix.lower() == ".svg" and path.stem.lower() == "figure03" and original is None:
            original = path
            target = work / "original" / "figure03.original.svg"
            target.parent.mkdir(parents=True, exist_ok=True); shutil.copyfile(path, target)
        if path.suffix.lower() == ".pdf":
            if pdf is None: pdf = get_pymupdf()
            try:
                document = pdf.open(path)
                text = "\n\n".join(f"<!-- page {i+1} -->\n" + page.get_text() for i, page in enumerate(document))
                target = work / "source_text" / (path.stem + ".pdf.txt")
                target.parent.mkdir(parents=True, exist_ok=True); target.write_text(text, encoding="utf-8")
                record["text_extraction"] = "plain text only; no claims inferred"
                document.close()
            except Exception as exc:
                raise ValueError(f"Unable to read paper PDF {relative}: {exc}") from exc
    if original is None:
        uncertainties.append("No figure03.svg was supplied; generated a new SVG instead of source-preserving editing.")
    if case.get("synthetic"):
        uncertainties.append("SYNTHETIC fixture: labels, locators, data, and relations are not scientific evidence.")
    return sources, uncertainties, caption, original


def geometry(entity: dict, index: int) -> tuple[float, float, float, float]:
    layout = entity.get("layout", {}) if isinstance(entity.get("layout"), dict) else {}
    return (float(layout.get("x", 40 + (index % 4) * 285)), float(layout.get("y", 140 + (index // 4) * 200)),
            float(layout.get("w", 210)), float(layout.get("h", 70)))


def process_center(process: dict, index: int) -> tuple[float, float]:
    layout = process.get("layout", {}) if isinstance(process.get("layout"), dict) else {}
    return float(layout.get("x", 320 + (index % 3) * 270)), float(layout.get("y", 300 + (index // 3) * 180))


def point_toward(sx: float, sy: float, tx: float, ty: float, inset: float) -> tuple[float, float]:
    """Point inset pixels before target, keeping terminal glyphs outside nodes."""
    length = math.hypot(tx - sx, ty - sy)
    if length == 0: return tx, ty
    return tx - (tx - sx) * inset / length, ty - (ty - sy) * inset / length


def entity_terminal(px: float, py: float, ex: float, ey: float, w: float, h: float, outset: float = 13) -> tuple[float, float]:
    """Endpoint just outside an entity rectangle in the process-to-entity direction."""
    dx, dy = ex - px, ey - py
    if dx == 0 and dy == 0: return ex, ey
    x_distance = (w / 2) / abs(dx) if dx else float("inf")
    y_distance = (h / 2) / abs(dy) if dy else float("inf")
    distance = min(x_distance, y_distance) + outset
    length = math.hypot(dx, dy)
    return ex - dx * distance / length, ey - dy * distance / length


def terminal_svg(aid: str, sx: float, sy: float, tx: float, ty: float, effect: str, color: str) -> str:
    """Explicit SVG geometry avoids renderer-dependent marker support/occlusion."""
    length = math.hypot(tx - sx, ty - sy)
    if length == 0: return ""
    ux, uy = (tx - sx) / length, (ty - sy) / length
    px, py = -uy, ux
    if effect == "inhibition":
        return (f'<line id="{html.escape(aid)}-terminal" data-terminal="inhibition-tbar" '
                f'x1="{tx+px*10:.2f}" y1="{ty+py*10:.2f}" x2="{tx-px*10:.2f}" y2="{ty-py*10:.2f}" '
                f'stroke="{color}" stroke-width="4"/>')
    if effect == "uncertain":
        return (f'<g id="{html.escape(aid)}-terminal" data-terminal="uncertain"><circle cx="{tx:.2f}" cy="{ty:.2f}" r="9" fill="white" stroke="{color}" stroke-width="2"/>'
                f'<text x="{tx:.2f}" y="{ty+4:.2f}" text-anchor="middle" font-family="Arial" font-size="12" fill="{color}">?</text></g>')
    bx, by = tx - ux * 16, ty - uy * 16
    points = f"{tx:.2f},{ty:.2f} {bx+px*7:.2f},{by+py*7:.2f} {bx-px*7:.2f},{by-py*7:.2f}"
    hollow = effect == "activation"
    return (f'<polygon id="{html.escape(aid)}-terminal" data-terminal="{effect}-arrow" points="{points}" '
            f'fill="{"white" if hollow else color}" stroke="{color}" stroke-width="2"/>')


def generated_layer(model: dict, synthetic: bool, case_id: str) -> str:
    out = ['<g xmlns="http://www.w3.org/2000/svg" id="process-semantics-generated">']
    out.append('''<defs>
      <marker id="consumption-arrow" markerWidth="12" markerHeight="12" refX="10" refY="6" orient="auto" markerUnits="userSpaceOnUse"><path d="M0,0 L11,6 L0,12 Z" fill="#34465b"/></marker>
      <marker id="production-arrow" markerWidth="12" markerHeight="12" refX="10" refY="6" orient="auto" markerUnits="userSpaceOnUse"><path d="M0,0 L11,6 L0,12 Z" fill="#1b668e"/></marker>
      <marker id="stimulation-arrow" markerWidth="14" markerHeight="14" refX="12" refY="7" orient="auto" markerUnits="userSpaceOnUse"><path d="M1,1 L12,7 L1,13 Z" fill="#f7fff9" stroke="#188150" stroke-width="2"/></marker>
      <marker id="inhibition-tbar" markerWidth="16" markerHeight="18" refX="12" refY="9" orient="auto" markerUnits="userSpaceOnUse"><path d="M12,1 L12,17" stroke="#b32b3d" stroke-width="4"/></marker>
      <marker id="uncertain-end" markerWidth="18" markerHeight="18" refX="13" refY="9" orient="auto" markerUnits="userSpaceOnUse"><circle cx="10" cy="9" r="7" fill="white" stroke="#78649b"/><text x="10" y="13" text-anchor="middle" font-size="12" fill="#78649b">?</text></marker>
    </defs>''')
    out.append('<rect x="0" y="0" width="1200" height="760" fill="#fcfdff" fill-opacity="0.95"/>')
    out.append('<text x="40" y="43" font-family="Arial,Helvetica,sans-serif" font-size="27" font-weight="700" fill="#192a3d">Process nodes and explicit semantic arcs</text>')
    badge = "SYNTHETIC — NOT A SCIENTIFIC CLAIM" if synthetic else "CURATED PROCESS MODEL"
    out.append(f'<text x="40" y="70" font-family="Arial,Helvetica,sans-serif" font-size="14" fill="#a12a38">{html.escape(badge)}</text>')
    out.append(f'<text x="1160" y="43" text-anchor="end" font-family="monospace" font-size="12" fill="#586a7e">{html.escape(case_id)}</text>')
    out.append('<g id="arc-legend" font-family="Arial,Helvetica,sans-serif" font-size="11" fill="#41546a"><text x="655" y="67">filled: consumption/production</text><text x="865" y="67">hollow: stimulation</text><text x="1000" y="67">T-bar: inhibition</text></g>')
    entities = model.get("entities", []); processes = model.get("processes", [])
    entity_geo = {e["canonical_id"]: geometry(e, i) for i, e in enumerate(entities) if isinstance(e, dict) and "canonical_id" in e}
    centers = {p["process_id"]: process_center(p, i) for i, p in enumerate(processes) if isinstance(p, dict) and "process_id" in p}
    # Lines and explicit terminal geometry stay outside node glyphs, including in PNG/PDF export.
    for i, process in enumerate(processes):
        if not isinstance(process, dict) or process.get("process_id") not in centers: continue
        pid = process["process_id"]; px, py = centers[pid]
        for role in ("inputs", "outputs"):
            for j, endpoint in enumerate(process.get(role, [])):
                if endpoint not in entity_geo: continue
                x, y, w, h = entity_geo[endpoint]; ex, ey = x+w/2, y+h/2
                aid = f"arc-{pid}-{'input' if role == 'inputs' else 'output'}-{j}"
                if role == "inputs":
                    x1, y1 = ex, ey; x2, y2 = point_toward(ex, ey, px, py, 47)
                    color, arc_class, effect = "#34465b", "consumption", "consumption"
                else:
                    x1, y1 = px, py; x2, y2 = entity_terminal(px, py, ex, ey, w, h)
                    color, arc_class, effect = "#1b668e", "production", "production"
                out.append(f'<line id="{html.escape(aid)}" data-arc-class="{arc_class}" x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" stroke="{color}" stroke-width="2.5"/>')
                out.append(terminal_svg(aid, x1, y1, x2, y2, effect, color))
        for j, modulator in enumerate(process.get("modulators", [])):
            if not isinstance(modulator, dict) or modulator.get("entity_id") not in entity_geo: continue
            endpoint, effect = modulator["entity_id"], modulator.get("effect")
            x, y, w, h = entity_geo[endpoint]; ex, ey = x+w/2, y+h/2
            color = {"activation": "#188150", "inhibition": "#b32b3d"}.get(effect, "#78649b")
            dash = ' stroke-dasharray="7 5"' if effect == "uncertain" else ""
            aid = f"arc-{pid}-modulator-{j}"; tx, ty = point_toward(ex, ey, px, py, 47)
            out.append(f'<line id="{html.escape(aid)}" data-arc-class="modulation" data-effect="{html.escape(str(effect))}" x1="{ex}" y1="{ey}" x2="{tx}" y2="{ty}" stroke="{color}" stroke-width="2.5"{dash}/>')
            out.append(terminal_svg(aid, ex, ey, tx, ty, str(effect), color))
    for cid, (x, y, w, h) in entity_geo.items():
        entity = next(e for e in entities if isinstance(e, dict) and e.get("canonical_id") == cid)
        compartment = entity.get("compartment")
        fill = "#eef6ff" if not compartment else ("#fff4dd" if norm(compartment) == "nucleus" else "#ecf8f0")
        out.append(f'<g id="entity-{html.escape(cid)}"><rect x="{x}" y="{y}" width="{w}" height="{h}" rx="15" fill="{fill}" stroke="#49627b" stroke-width="2"/>')
        out.append(f'<text x="{x+w/2}" y="{y+30}" text-anchor="middle" font-family="Arial,Helvetica,sans-serif" font-size="17" font-weight="600" fill="#213247">{html.escape(entity.get("label", cid))}</text>')
        sub = compartment or cid
        out.append(f'<text x="{x+w/2}" y="{y+52}" text-anchor="middle" font-family="Arial,Helvetica,sans-serif" font-size="11" fill="#607388">{html.escape(str(sub))}</text></g>')
    for i, process in enumerate(processes):
        if not isinstance(process, dict) or process.get("process_id") not in centers: continue
        pid = process["process_id"]; ptype = process.get("process_type"); px, py = centers[pid]
        color = "#b32b3d" if ptype == "inhibition" else ("#188150" if ptype == "activation" else "#5966a9")
        out.append(f'<g id="process-{html.escape(pid)}" data-process-type="{html.escape(str(ptype))}">')
        if ptype in {"activation", "uncertain", "phosphorylation", "ubiquitination", "transcription"}:
            out.append(f'<circle cx="{px}" cy="{py}" r="31" fill="white" stroke="{color}" stroke-width="3"/>')
        elif ptype == "inhibition":
            points = []
            for k in range(8):
                angle = math.pi / 8 + k * math.pi / 4
                points.append(f"{px+34*math.cos(angle):.2f},{py+34*math.sin(angle):.2f}")
            out.append(f'<polygon points="{" ".join(points)}" fill="#fff4f5" stroke="{color}" stroke-width="3"/>')
        else:
            out.append(f'<rect x="{px-43}" y="{py-31}" width="86" height="62" rx="12" fill="white" stroke="{color}" stroke-width="3"/>')
        out.append(f'<text x="{px}" y="{py+7}" text-anchor="middle" font-family="Arial,Helvetica,sans-serif" font-size="18" font-weight="700" fill="{color}">{GLYPH.get(ptype, "?")}</text>')
        if ptype == "transport":
            out.append(f'<text x="{px}" y="{py-44}" text-anchor="middle" font-family="Arial,Helvetica,sans-serif" font-size="11" fill="#485a75">{html.escape(str(process.get("from_compartment")))} → {html.escape(str(process.get("to_compartment")))}</text>')
        out.append(f'<text x="{px}" y="{py+53}" text-anchor="middle" font-family="monospace" font-size="11" fill="#57687e">{html.escape(pid)}</text></g>')
    out.append('<text x="40" y="740" font-family="Arial,Helvetica,sans-serif" font-size="12" fill="#617286">Arc class is explicit: association never implies activation; inhibition has no production output.</text></g>')
    return "".join(out)


def render_svg(model: dict, synthetic: bool, case_id: str, original: Path | None) -> str:
    ET.register_namespace("", "http://www.w3.org/2000/svg")
    layer = ET.fromstring(generated_layer(model, synthetic, case_id))
    if original is not None:
        root = ET.fromstring(original.read_text(encoding="utf-8"))
        if not root.tag.endswith("svg"): raise ValueError("figure03.svg root is not SVG")
        view = root.get("viewBox", "0 0 1200 760").split()
        if len(view) != 4: raise ValueError("figure03.svg has an invalid viewBox")
        width, height = max(1200.0, float(view[2])), max(760.0, float(view[3]))
        root.set("viewBox", f"{view[0]} {view[1]} {width:g} {height:g}")
        root.set("width", f"{width:g}"); root.set("height", f"{height:g}")
        root.append(layer); root.set("data-process-semantics-layer", "appended; original XML children retained")
        return ET.tostring(root, encoding="unicode", xml_declaration=True)
    return ('<?xml version="1.0" encoding="UTF-8"?><svg xmlns="http://www.w3.org/2000/svg" width="1200" height="760" viewBox="0 0 1200 760">' +
            ET.tostring(layer, encoding="unicode") + '</svg>')


def export(svg_path: Path, output: Path) -> None:
    pdf = get_pymupdf(); document = pdf.open(svg_path)
    try:
        document[0].get_pixmap(matrix=pdf.Matrix(2, 2), alpha=False).save(output / "export.png")
        (output / "export.pdf").write_bytes(document.convert_to_pdf())
    finally:
        document.close()


def content_map(model: dict, arc_plan: list[dict]) -> dict:
    entities = [{"svg_element_id": "entity-" + e["canonical_id"], "canonical_id": e["canonical_id"],
                 "label": e.get("label"), "compartment": e.get("compartment")}
                for e in model.get("entities", []) if isinstance(e, dict) and e.get("canonical_id")]
    processes = []
    for p in model.get("processes", []):
        if not isinstance(p, dict) or not p.get("process_id"): continue
        processes.append({"svg_element_id": "process-" + p["process_id"], "process_id": p["process_id"],
                          "process_type": p.get("process_type"), "inputs": p.get("inputs"), "outputs": p.get("outputs"),
                          "modulators": p.get("modulators"), "from_compartment": p.get("from_compartment"),
                          "to_compartment": p.get("to_compartment"), "source_locator": p.get("source_locator")})
    return {"mapping_authority": "explicit process model; no arc inference", "entities": entities, "processes": processes, "arcs": arc_plan}


def run(args: argparse.Namespace) -> int:
    input_dir, work, output = Path(args.input_dir), Path(args.work_dir), Path(args.output_dir)
    output.mkdir(parents=True, exist_ok=True); work.mkdir(parents=True, exist_ok=True)
    try:
        case = json.loads((input_dir / "case.json").read_text(encoding="utf-8"))
        if not isinstance(case, dict): raise ValueError("case.json root must be an object")
    except Exception as exc:
        result = Result(output, {}); result.error("CASE_READ", str(exc), fatal=True); return 1
    result = Result(output, case)
    try:
        if case.get("synthetic") and not args.synthetic: raise ValueError("Synthetic case refused: use demo/--synthetic only for test fixtures")
        if not case.get("synthetic") and args.synthetic: raise ValueError("--synthetic cannot be used for a production case")
        task = (input_dir / "task.md").read_text(encoding="utf-8")
        workorder_path = input_dir / "figure-workorder.json"
        if not workorder_path.is_file(): workorder_path = input_dir / "artifacts" / "figure-workorder.json"
        workorder = json.loads(workorder_path.read_text(encoding="utf-8"))
        (work / "task.md").write_text(task, encoding="utf-8"); dump(work / "figure-workorder.json", workorder)
        sources, uncertainties, caption, original = inventory_sources(input_dir, work, case)
        result.values["sources"] = sources; result.values["uncertainty"] = uncertainties
        (work / "source_text" / "figure03.caption.review.txt").write_text(caption or "No figure03 caption supplied.\n", encoding="utf-8")
        result.values["change_records"].append({"at": now(), "action": "inventoried_sources_and_pdf_text", "source_count": len(sources)})
        model = case.get("model")
        if not isinstance(model, dict): raise ValueError("case.model must be an object")
        dump(output / "process-model.json", model)
        issues, unknown, arc_plan = validate_model(model)
        cmap = content_map(model, arc_plan); dump(output / "content-map.json", cmap)
        result.values["content_map"] = "content-map.json"
        audit = {
            "case_id": result.case_id, "synthetic": bool(case.get("synthetic")),
            "status": "fail" if issues else "pass", "issues": issues, "unknown_endpoints": unknown,
            "allowed_process_types": sorted(PROCESS_TYPES), "allowed_modulator_effects": sorted(EFFECTS),
            "arc_counts": {
                "consumption": sum(a["arc_class"] == "consumption" for a in arc_plan),
                "production": sum(a["arc_class"] == "production" for a in arc_plan),
                "activation_modulation": sum(a.get("effect") == "activation" for a in arc_plan),
                "inhibition_modulation": sum(a.get("effect") == "inhibition" for a in arc_plan),
                "uncertain_modulation": sum(a.get("effect") == "uncertain" for a in arc_plan),
            },
            "rule": "inputs/outputs are consumption/production; modulator effects target process nodes; no relation inference",
        }
        dump(output / "semantic-audit.json", audit); result.values["audit_artifact"] = "semantic-audit.json"
        result.values["exceptions"] = issues
        result.values["compliance_checks"] = {"passed": not issues, "checks": [
            {"name": "process_has_input_or_output", "status": "fail" if any(i["code"] == "EMPTY_PROCESS" for i in issues) else "pass"},
            {"name": "all_endpoints_exist", "status": "pass" if not unknown else "fail"},
            {"name": "inhibition_has_no_production", "status": "fail" if any(i["code"] == "INHIBITION_PRODUCTION" for i in issues) else "pass"},
            {"name": "transport_compartments_distinct_and_consistent", "status": "fail" if any(i["code"].startswith("TRANSPORT_") for i in issues) else "pass"},
            {"name": "source_svg_preserved", "status": "pass" if original else "not_applicable"},
        ]}
        result.values["change_records"].append({"at": now(), "action": "audited_processes_and_arcs", "issue_count": len(issues)})
        result.write()
        if issues:
            result.values["status"] = "partial"; result.write(); return 2
        svg = render_svg(model, bool(case.get("synthetic")), result.case_id, original)
        (output / "editable_source.svg").write_text(svg, encoding="utf-8"); result.values["editable_source"] = "editable_source.svg"
        export(output / "editable_source.svg", output)
        result.values["export_artifact"] = {"png": "export.png", "pdf": "export.pdf"}
        result.values["compliance_checks"]["checks"].extend([
            {"name": "editable_svg_generated", "status": "pass"},
            {"name": "png_pdf_regenerated_with_pymupdf", "status": "pass"},
            {"name": "result_contract_fields", "status": "pass", "fields": result.fields},
        ])
        result.values["compliance_checks"]["passed"] = True; result.values["status"] = "success"
        result.values["change_records"].append({"at": now(), "action": "rendered_and_exported", "source_preserving": original is not None})
        result.write(); return 0
    except Exception as exc:
        result.error("RUN_FAILURE", str(exc)); return 2


def demo(args: argparse.Namespace) -> int:
    destination = Path(args.destination).resolve()
    summary = {"bundle": "process-semantics", "synthetic": True, "runs": []}
    observed = []
    for fixture in ("synthetic", "synthetic-failure"):
        root = destination / ("success" if fixture == "synthetic" else "failure")
        inp = root / "input"
        if inp.exists(): shutil.rmtree(inp)
        inp.parent.mkdir(parents=True, exist_ok=True); shutil.copytree(BUNDLE / "examples" / fixture / "input", inp)
        command = [sys.executable, str(Path(__file__).resolve()), "run", "--synthetic", "--input-dir", str(inp),
                   "--work-dir", str(root / "work"), "--output-dir", str(root / "output")]
        completed = subprocess.run(command, check=False)
        summary["runs"].append({"fixture": fixture, "command": command, "exit_code": completed.returncode,
                                "expected": 0 if fixture == "synthetic" else "nonzero", "output": str(root / "output")})
        observed.append(completed.returncode)
    dump(destination / "validation-summary.json", summary)
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0 if observed[0] == 0 and observed[1] != 0 else 1


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    runner = sub.add_parser("run")
    runner.add_argument("--input-dir", default="/input"); runner.add_argument("--work-dir", default="/app/work"); runner.add_argument("--output-dir", default="/app/output")
    runner.add_argument("--synthetic", action="store_true", help="Explicitly allow SYNTHETIC test fixtures only")
    runner.set_defaults(func=run)
    demonstration = sub.add_parser("demo"); demonstration.add_argument("--destination", required=True); demonstration.set_defaults(func=demo)
    args = parser.parse_args(); return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
