#!/usr/bin/env python3
"""Canonical entity registry, mention resolution, SVG rendering, and exports.

No biological identities are inferred. Only the input registry is normalized.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import html
import json
import re
import shutil
import subprocess
import sys
import unicodedata
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
import xml.etree.ElementTree as ET

BUNDLE = Path(__file__).resolve().parent.parent
KINDS = {"gene", "protein", "complex", "family", "receptor", "cell_type", "small_molecule"}
SPECIES = {
    "Homo sapiens", "Mus musculus", "Rattus norvegicus", "Danio rerio",
    "Drosophila melanogaster", "Saccharomyces cerevisiae", "not_applicable",
}
STANDARD_FIELDS = [
    "case_id", "status", "editable_source", "export_artifact", "content_map",
    "compliance_checks", "exceptions", "sources", "uncertainty", "change_records",
]
STYLE = {
    "gene": ("#e7f1ff", "#205d9c", "GENE"),
    "protein": ("#e4f5ef", "#176b55", "PROTEIN"),
    "complex": ("#f1e9fa", "#704297", "COMPLEX"),
    "family": ("#f4eafd", "#833e9e", "FAMILY"),
    "receptor": ("#fff0de", "#a35416", "RECEPTOR"),
    "cell_type": ("#e8f6e3", "#477c32", "CELL TYPE"),
    "small_molecule": ("#fff8d8", "#866b08", "SMALL MOLECULE"),
}


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def dump(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def norm(value: object) -> str:
    return " ".join(unicodedata.normalize("NFKC", str(value)).strip().split()).casefold()


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
                if isinstance(item, str):
                    names.append(item)
                elif isinstance(item, dict):
                    value = item.get("name") or item.get("key") or item.get("field")
                    if isinstance(value, str):
                        names.append(value)
        else:
            # A direct field-to-description contract is also accepted.
            names = [str(k) for k in contract]
    return list(dict.fromkeys(names + STANDARD_FIELDS))


class Result:
    def __init__(self, output: Path, case: dict):
        self.path = output / "result.json"
        self.case_id = str(case.get("case_id", "unknown"))
        self.fields = contract_fields(case)
        self.values = {
            "case_id": self.case_id, "status": "partial", "editable_source": None,
            "export_artifact": None, "content_map": None,
            "compliance_checks": {"passed": False, "checks": [{"name": "run", "status": "started"}]},
            "exceptions": [], "sources": [], "uncertainty": [],
            "change_records": [{"at": now(), "action": "initialized_partial_result"}],
        }
        self.write()

    def write(self) -> None:
        payload = {key: copy.deepcopy(self.values.get(key)) for key in self.fields}
        # The supplemental provenance keys are unconditional, even for a minimal custom contract.
        for key in ("sources", "uncertainty", "change_records"):
            payload[key] = copy.deepcopy(self.values[key])
        dump(self.path, payload)

    def error(self, code: str, message: str, fatal: bool = False) -> None:
        self.values["exceptions"].append({"code": code, "message": message, "fatal": fatal})
        self.values["status"] = "failed" if fatal else "partial"
        self.write()


def issue(code: str, message: str, severity: str = "error", **extra: object) -> dict:
    return {"code": code, "severity": severity, "message": message, **extra}


def validate_registry(registry: dict) -> tuple[list[dict], list[dict], list[dict], list[dict]]:
    issues: list[dict] = []
    collisions: list[dict] = []
    unknown: list[dict] = []
    entities = registry.get("entities")
    if not isinstance(entities, list):
        return [issue("REGISTRY_SHAPE", "registry.entities must be a list")], [], [], []
    by_id: dict[str, dict] = {}
    aliases: dict[str, list[tuple[dict, str]]] = defaultdict(list)
    for index, entity in enumerate(entities):
        where = f"entities[{index}]"
        if not isinstance(entity, dict):
            issues.append(issue("ENTITY_SHAPE", f"{where} must be an object"))
            continue
        cid = entity.get("canonical_id")
        kind = entity.get("entity_kind")
        species = entity.get("species")
        if not isinstance(cid, str) or not re.fullmatch(r"[A-Za-z][A-Za-z0-9_.:-]*", cid):
            issues.append(issue("CANONICAL_ID", f"{where}.canonical_id is missing or unsafe"))
            continue
        if cid in by_id:
            issues.append(issue("DUPLICATE_CANONICAL_ID", f"Duplicate canonical_id {cid}", canonical_id=cid))
            continue
        by_id[cid] = entity
        if kind not in KINDS:
            issues.append(issue("ENTITY_KIND", f"{cid} has unsupported entity_kind {kind!r}", canonical_id=cid))
        if species not in SPECIES:
            issues.append(issue("SPECIES", f"{cid} has unsupported or missing species {species!r}", canonical_id=cid))
        if species == "not_applicable" and kind != "small_molecule":
            issues.append(issue("SPECIES_KIND", f"{cid}: not_applicable is restricted to small molecules", canonical_id=cid))
        if kind == "gene":
            symbol = entity.get("gene_symbol")
            if not isinstance(symbol, str) or not symbol.strip():
                issues.append(issue("GENE_SYMBOL", f"{cid} requires gene_symbol", canonical_id=cid))
            elif species == "Homo sapiens" and symbol != symbol.upper():
                issues.append(issue("HUMAN_GENE_CASE", f"{cid}: human gene symbols use uppercase", canonical_id=cid))
            elif species == "Mus musculus" and symbol != symbol[:1].upper() + symbol[1:].lower():
                issues.append(issue("MOUSE_GENE_CASE", f"{cid}: mouse gene symbols use sentence case", canonical_id=cid))
            if entity.get("protein_name"):
                issues.append(issue("GENE_PROTEIN_CONFLATION", f"{cid}: a gene record cannot carry protein_name", canonical_id=cid))
        if kind in {"protein", "receptor"}:
            if not isinstance(entity.get("protein_name"), str) or not entity.get("protein_name", "").strip():
                issues.append(issue("PROTEIN_NAME", f"{cid} requires a nonempty protein_name", canonical_id=cid))
            if entity.get("gene_symbol"):
                issues.append(issue("GENE_PROTEIN_CONFLATION", f"{cid}: protein/receptor uses protein_name, not gene_symbol", canonical_id=cid))
        if kind in {"complex", "family"}:
            members = entity.get("members")
            if not isinstance(members, list) or len(members) < 2 or any(not isinstance(x, str) for x in members):
                issues.append(issue("MEMBERS", f"{cid}: {kind} requires at least two canonical member IDs", canonical_id=cid))
            if isinstance(members, list) and len(set(members)) != len(members):
                issues.append(issue("DUPLICATE_MEMBER", f"{cid} repeats a member", canonical_id=cid))
        elif entity.get("members"):
            issues.append(issue("MEMBERS_KIND", f"{cid}: only complex/family records may declare members", canonical_id=cid))
        locator = entity.get("source_locator")
        if not isinstance(locator, dict) or not isinstance(locator.get("document"), str) or not isinstance(locator.get("locator"), str):
            issues.append(issue("SOURCE_LOCATOR", f"{cid} requires source_locator.document and .locator", canonical_id=cid))
        entity_aliases = entity.get("aliases")
        if not isinstance(entity_aliases, list) or any(not isinstance(a, str) or not a.strip() for a in entity_aliases):
            issues.append(issue("ALIASES", f"{cid}.aliases must be a list of nonempty strings", canonical_id=cid))
            entity_aliases = []
        local_seen: set[str] = set()
        for alias in entity_aliases:
            key = norm(alias)
            if key in local_seen:
                issues.append(issue("DUPLICATE_ALIAS", f"{cid} repeats normalized alias {alias!r}", "warning", canonical_id=cid))
            else:
                aliases[key].append((entity, alias))
                local_seen.add(key)
    for entity in by_id.values():
        if entity.get("entity_kind") in {"complex", "family"}:
            for member in entity.get("members", []):
                if member not in by_id:
                    record = {"owner": entity["canonical_id"], "endpoint": member, "role": "member"}
                    unknown.append(record)
                    issues.append(issue("UNKNOWN_ENDPOINT", f"{member!r} is not a registry member of {entity['canonical_id']}", **record))
    for key, records in sorted(aliases.items()):
        unique: dict[str, tuple[dict, str]] = {r[0]["canonical_id"]: r for r in records}
        if len(unique) < 2:
            continue
        policies = []
        for entity, alias in unique.values():
            raw = entity.get("alias_policies", {})
            policies.append(raw.get(alias) or raw.get(key))
        permitted = all(p == "context_required" for p in policies)
        collision = {
            "normalized_alias": key,
            "canonical_ids": sorted(unique),
            "resolution_policy": "context_required" if permitted else "reject",
            "contexts": [
                {"canonical_id": e["canonical_id"], "species": e.get("species"), "entity_kind": e.get("entity_kind")}
                for e, _ in unique.values()
            ],
        }
        collisions.append(collision)
        if permitted:
            issues.append(issue("CONTEXT_REQUIRED_ALIAS", f"Shared alias {key!r} requires species/kind context", "warning", **collision))
        else:
            issues.append(issue("ALIAS_COLLISION", f"Shared alias {key!r} is not explicitly context-resolvable", **collision))
    interactions = registry.get("interactions", [])
    if not isinstance(interactions, list):
        issues.append(issue("INTERACTIONS", "registry.interactions must be a list when present"))
    else:
        for index, interaction in enumerate(interactions):
            if not isinstance(interaction, dict):
                issues.append(issue("INTERACTION_SHAPE", f"interactions[{index}] must be an object"))
                continue
            for role in ("source", "target"):
                endpoint = interaction.get(role)
                if not isinstance(endpoint, str) or endpoint not in by_id:
                    record = {"interaction_index": index, "endpoint": endpoint, "role": role}
                    unknown.append(record)
                    issues.append(issue("UNKNOWN_ENDPOINT", f"Unknown {role} endpoint {endpoint!r}", **record))
    return issues, collisions, unknown, list(by_id.values())


def resolve_mentions(mentions: object, registry: dict, issues: list[dict]) -> list[dict]:
    if not isinstance(mentions, list):
        issues.append(issue("MENTIONS", "case.mentions must be a list"))
        return []
    index: dict[str, list[dict]] = defaultdict(list)
    for entity in registry.get("entities", []):
        if isinstance(entity, dict):
            for alias in entity.get("aliases", []):
                if isinstance(alias, str):
                    index[norm(alias)].append(entity)
    resolved = []
    for i, mention in enumerate(mentions):
        if not isinstance(mention, dict) or not isinstance(mention.get("surface"), str):
            issues.append(issue("MENTION_SHAPE", f"mentions[{i}] requires surface"))
            continue
        candidates = index.get(norm(mention["surface"]), [])
        if mention.get("species") is not None:
            candidates = [e for e in candidates if e.get("species") == mention["species"]]
        if mention.get("entity_kind") is not None:
            candidates = [e for e in candidates if e.get("entity_kind") == mention["entity_kind"]]
        ids = sorted({e.get("canonical_id") for e in candidates})
        record = {
            "mention_index": i, "surface": mention["surface"],
            "normalized_alias": norm(mention["surface"]),
            "supplied_species": mention.get("species"), "supplied_entity_kind": mention.get("entity_kind"),
            "candidate_canonical_ids": ids,
            "status": "resolved" if len(ids) == 1 else "unresolved",
            "canonical_id": ids[0] if len(ids) == 1 else None,
        }
        if len(ids) != 1:
            issues.append(issue("AMBIGUOUS_MENTION" if ids else "UNKNOWN_MENTION",
                                f"Mention {mention['surface']!r} has {len(ids)} candidates; supply species/kind context",
                                mention_index=i, candidate_canonical_ids=ids))
        resolved.append(record)
    return resolved


def get_pymupdf():
    try:
        import pymupdf
        return pymupdf
    except ImportError:
        import fitz
        return fitz


def inventory_sources(input_dir: Path, work: Path, case: dict) -> tuple[list[dict], list[str], str | None, Path | None]:
    sources: list[dict] = []
    uncertainties: list[str] = []
    caption = None
    original = None
    for name in case.get("source_files", []):
        if not isinstance(name, str) or not (input_dir / name).is_file():
            raise ValueError(f"case.source_files entry is missing or invalid: {name!r}")
    files = sorted((p for p in input_dir.rglob("*") if p.is_file()), key=lambda p: str(p))
    pdf = None
    for path in files:
        relative = path.relative_to(input_dir).as_posix()
        lower = relative.lower()
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
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(caption, encoding="utf-8")
        if path.suffix.lower() == ".svg" and path.stem.lower() == "figure03" and original is None:
            original = path
            dest = work / "original" / "figure03.original.svg"
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(path, dest)
        if path.suffix.lower() == ".pdf":
            if pdf is None: pdf = get_pymupdf()
            try:
                document = pdf.open(path)
                text = "\n\n".join(f"<!-- page {i+1} -->\n" + page.get_text() for i, page in enumerate(document))
                target = work / "source_text" / (path.stem + ".pdf.txt")
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text(text, encoding="utf-8")
                record["text_extraction"] = "plain text only; no claims inferred"
                document.close()
            except Exception as exc:
                raise ValueError(f"Unable to read paper PDF {relative}: {exc}") from exc
    if original is None:
        uncertainties.append("No figure03.svg was supplied; generated a new SVG instead of source-preserving editing.")
    if not sources:
        uncertainties.append("No supporting sources were present.")
    if case.get("synthetic"):
        uncertainties.append("SYNTHETIC fixture: labels, locators, data, and relations are not scientific evidence.")
    return sources, uncertainties, caption, original


def entity_label(entity: dict) -> tuple[str, str]:
    kind = entity.get("entity_kind")
    if kind == "gene":
        return str(entity.get("gene_symbol", entity["canonical_id"])), "italic"
    if kind in {"protein", "receptor"}:
        return str(entity.get("protein_name", entity["canonical_id"])), "normal"
    return str(entity.get("display_name") or entity.get("protein_name") or entity["canonical_id"]), "normal"


def generated_layer(registry: dict, synthetic: bool, case_id: str) -> str:
    entities = registry.get("entities", [])
    out = ['<g xmlns="http://www.w3.org/2000/svg" id="entity-registry-generated">']
    out.append('<rect x="0" y="0" width="1200" height="760" fill="#fcfdff" fill-opacity="0.94"/>')
    out.append('<text x="44" y="50" font-family="Arial,Helvetica,sans-serif" font-size="28" font-weight="700" fill="#18283b">Canonical entity registry</text>')
    badge = "SYNTHETIC — NOT A SCIENTIFIC CLAIM" if synthetic else "REGISTRY-DERIVED — CURATED INPUT"
    out.append(f'<text x="44" y="80" font-family="Arial,Helvetica,sans-serif" font-size="14" fill="#a12a38">{html.escape(badge)}</text>')
    out.append(f'<text x="1150" y="50" text-anchor="end" font-family="monospace" font-size="13" fill="#566577">{html.escape(case_id)}</text>')
    cols = 3
    cell_w, cell_h = 370, 190
    for i, entity in enumerate(entities):
        layout = entity.get("layout", {}) if isinstance(entity.get("layout", {}), dict) else {}
        x = float(layout.get("x", 44 + (i % cols) * cell_w))
        y = float(layout.get("y", 115 + (i // cols) * cell_h))
        w = float(layout.get("w", 335)); h = float(layout.get("h", 158))
        kind = entity.get("entity_kind")
        fill, stroke, kind_label = STYLE.get(kind, ("#f1f3f5", "#6b7785", "UNKNOWN"))
        label, font_style = entity_label(entity)
        out.append(f'<g id="entity-{html.escape(entity["canonical_id"])}">')
        out.append(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="18" fill="{fill}" stroke="{stroke}" stroke-width="2"/>')
        out.append(f'<rect x="{x}" y="{y}" width="{w}" height="27" rx="13" fill="{stroke}"/>')
        out.append(f'<text x="{x+14}" y="{y+19}" font-family="Arial,Helvetica,sans-serif" font-size="12" font-weight="700" fill="white">{kind_label}</text>')
        out.append(f'<text x="{x+w/2}" y="{y+67}" text-anchor="middle" font-family="Arial,Helvetica,sans-serif" font-size="25" font-style="{font_style}" font-weight="600" fill="#172536">{html.escape(label)}</text>')
        out.append(f'<text x="{x+14}" y="{y+99}" font-family="monospace" font-size="12" fill="#344457">id: {html.escape(entity["canonical_id"])}</text>')
        out.append(f'<text x="{x+14}" y="{y+120}" font-family="Arial,Helvetica,sans-serif" font-size="12" fill="#536174">species: {html.escape(str(entity.get("species")))}</text>')
        members = entity.get("members", [])
        if members:
            full = ", ".join(members)
            shown = full if len(full) <= 38 else full[:35] + "…"
            out.append(f'<text x="{x+14}" y="{y+143}" font-family="Arial,Helvetica,sans-serif" font-size="11" fill="#64467a">members ({len(members)}): {html.escape(shown)}<title>{html.escape(full)}</title></text>')
        else:
            out.append(f'<text x="{x+14}" y="{y+143}" font-family="Arial,Helvetica,sans-serif" font-size="11" fill="#657285">typography: {font_style}; type-driven glyph</text>')
        out.append('</g>')
    out.append('<text x="44" y="738" font-family="Arial,Helvetica,sans-serif" font-size="12" fill="#617083">Genes italic • proteins upright • complex/family members remain independent canonical entities</text>')
    out.append('</g>')
    return "".join(out)


def render_svg(registry: dict, synthetic: bool, case_id: str, original: Path | None) -> str:
    ET.register_namespace("", "http://www.w3.org/2000/svg")
    layer = ET.fromstring(generated_layer(registry, synthetic, case_id))
    if original is not None:
        root = ET.fromstring(original.read_text(encoding="utf-8"))
        if not root.tag.endswith("svg"):
            raise ValueError("figure03.svg root is not SVG")
        view = root.get("viewBox", "0 0 1200 760").split()
        if len(view) != 4:
            raise ValueError("figure03.svg has an invalid viewBox")
        width, height = max(1200.0, float(view[2])), max(760.0, float(view[3]))
        root.set("viewBox", f"{view[0]} {view[1]} {width:g} {height:g}")
        root.set("width", f"{width:g}"); root.set("height", f"{height:g}")
        root.append(layer)
        root.set("data-entity-registry-layer", "appended; original XML children retained")
        return ET.tostring(root, encoding="unicode", xml_declaration=True)
    return ('<?xml version="1.0" encoding="UTF-8"?><svg xmlns="http://www.w3.org/2000/svg" '
            'width="1200" height="760" viewBox="0 0 1200 760">' +
            ET.tostring(layer, encoding="unicode") + '</svg>')


def export(svg_path: Path, output: Path) -> None:
    pdf = get_pymupdf()
    document = pdf.open(svg_path)
    try:
        page = document[0]
        pixmap = page.get_pixmap(matrix=pdf.Matrix(2, 2), alpha=False)
        pixmap.save(output / "export.png")
        pdf_bytes = document.convert_to_pdf()
        (output / "export.pdf").write_bytes(pdf_bytes)
    finally:
        document.close()


def content_map(registry: dict, mentions: list[dict], collisions: list[dict]) -> dict:
    entities = []
    for e in registry.get("entities", []):
        if not isinstance(e, dict) or not e.get("canonical_id"): continue
        label, typography = entity_label(e)
        entities.append({
            "svg_element_id": "entity-" + e["canonical_id"], "canonical_id": e["canonical_id"],
            "entity_kind": e.get("entity_kind"), "species": e.get("species"),
            "display_label": label, "typography": typography, "aliases": e.get("aliases"),
            "members": e.get("members", []), "source_locator": e.get("source_locator"),
        })
    return {"mapping_authority": "canonical registry; no rendering inference", "entities": entities,
            "mentions": mentions, "alias_collisions": collisions}


def run(args: argparse.Namespace) -> int:
    input_dir, work, output = Path(args.input_dir), Path(args.work_dir), Path(args.output_dir)
    output.mkdir(parents=True, exist_ok=True); work.mkdir(parents=True, exist_ok=True)
    try:
        case = json.loads((input_dir / "case.json").read_text(encoding="utf-8"))
        if not isinstance(case, dict): raise ValueError("case.json root must be an object")
    except Exception as exc:
        result = Result(output, {})
        result.error("CASE_READ", str(exc), fatal=True)
        return 1
    result = Result(output, case)
    try:
        if case.get("synthetic") and not args.synthetic:
            raise ValueError("Synthetic case refused: use demo/--synthetic only for test fixtures")
        if not case.get("synthetic") and args.synthetic:
            raise ValueError("--synthetic cannot be used for a production case")
        task = (input_dir / "task.md").read_text(encoding="utf-8")
        workorder_path = input_dir / "figure-workorder.json"
        if not workorder_path.is_file(): workorder_path = input_dir / "artifacts" / "figure-workorder.json"
        workorder = json.loads(workorder_path.read_text(encoding="utf-8"))
        (work / "task.md").write_text(task, encoding="utf-8")
        dump(work / "figure-workorder.json", workorder)
        sources, uncertainties, caption, original = inventory_sources(input_dir, work, case)
        result.values["sources"] = sources
        result.values["uncertainty"] = uncertainties
        (work / "source_text" / "figure03.caption.review.txt").write_text(caption or "No figure03 caption supplied.\n", encoding="utf-8")
        result.values["change_records"].append({"at": now(), "action": "inventoried_sources_and_pdf_text", "source_count": len(sources)})
        registry = case.get("registry")
        if not isinstance(registry, dict): raise ValueError("case.registry must be an object")
        dump(output / "registry.json", registry)
        issues, collisions, unknown, entities = validate_registry(registry)
        mentions = resolve_mentions(case.get("mentions"), registry, issues)
        cmap = content_map(registry, mentions, collisions)
        dump(output / "content-map.json", cmap)
        result.values["content_map"] = "content-map.json"
        audit = {
            "case_id": result.case_id, "synthetic": bool(case.get("synthetic")),
            "status": "fail" if any(i["severity"] == "error" for i in issues) else "pass",
            "entity_count": len(entities), "allowed_entity_kinds": sorted(KINDS),
            "issues": issues, "alias_collisions": collisions, "unknown_endpoints": unknown,
            "mention_resolution": mentions,
            "normalization": "Unicode NFKC + whitespace collapse + casefold; canonical IDs never merged",
        }
        dump(output / "registry-audit.json", audit)
        result.values["audit_artifact"] = "registry-audit.json"
        result.values["exceptions"] = [i for i in issues if i["severity"] == "error"]
        result.values["compliance_checks"] = {"passed": audit["status"] == "pass", "checks": [
            {"name": "identity_schema_and_species_kind", "status": "pass" if not any(i["code"] in {"ENTITY_KIND", "SPECIES", "SPECIES_KIND", "GENE_SYMBOL", "PROTEIN_NAME", "GENE_PROTEIN_CONFLATION", "HUMAN_GENE_CASE", "MOUSE_GENE_CASE"} for i in issues) else "fail"},
            {"name": "alias_collision_policy", "status": "fail" if any(i["code"] == "ALIAS_COLLISION" for i in issues) else ("warn" if collisions else "pass")},
            {"name": "known_endpoints", "status": "pass" if not unknown else "fail"},
            {"name": "unambiguous_mentions", "status": "pass" if all(m["status"] == "resolved" for m in mentions) else "fail"},
            {"name": "source_svg_preserved", "status": "pass" if original else "not_applicable"},
        ]}
        result.values["change_records"].append({"at": now(), "action": "audited_registry_and_resolved_mentions", "issue_count": len(issues)})
        result.write()
        if audit["status"] == "fail":
            result.values["status"] = "partial"; result.write()
            return 2
        svg = render_svg(registry, bool(case.get("synthetic")), result.case_id, original)
        (output / "editable_source.svg").write_text(svg, encoding="utf-8")
        result.values["editable_source"] = "editable_source.svg"
        export(output / "editable_source.svg", output)
        result.values["export_artifact"] = {"png": "export.png", "pdf": "export.pdf"}
        result.values["compliance_checks"]["checks"].extend([
            {"name": "editable_svg_generated", "status": "pass"},
            {"name": "png_pdf_regenerated_with_pymupdf", "status": "pass"},
            {"name": "result_contract_fields", "status": "pass", "fields": result.fields},
        ])
        result.values["compliance_checks"]["passed"] = True
        result.values["status"] = "success"
        result.values["change_records"].append({"at": now(), "action": "rendered_and_exported", "source_preserving": original is not None})
        result.write()
        return 0
    except Exception as exc:
        result.error("RUN_FAILURE", str(exc))
        return 2


def demo(args: argparse.Namespace) -> int:
    destination = Path(args.destination).resolve()
    summary = {"bundle": "entity-registry", "synthetic": True, "runs": []}
    observed = []
    for fixture in ("synthetic", "synthetic-failure"):
        root = destination / ("success" if fixture == "synthetic" else "failure")
        inp = root / "input"
        if inp.exists(): shutil.rmtree(inp)
        inp.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(BUNDLE / "examples" / fixture / "input", inp)
        command = [sys.executable, str(Path(__file__).resolve()), "run", "--synthetic",
                   "--input-dir", str(inp), "--work-dir", str(root / "work"), "--output-dir", str(root / "output")]
        completed = subprocess.run(command, check=False)
        expected = 0 if fixture == "synthetic" else "nonzero"
        summary["runs"].append({"fixture": fixture, "command": command, "exit_code": completed.returncode,
                                "expected": expected, "output": str(root / "output")})
        observed.append(completed.returncode)
    dump(destination / "validation-summary.json", summary)
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0 if observed[0] == 0 and observed[1] != 0 else 1


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    runner = sub.add_parser("run")
    runner.add_argument("--input-dir", default="/input")
    runner.add_argument("--work-dir", default="/app/work")
    runner.add_argument("--output-dir", default="/app/output")
    runner.add_argument("--synthetic", action="store_true", help="Explicitly allow SYNTHETIC test fixtures only")
    runner.set_defaults(func=run)
    demonstration = sub.add_parser("demo")
    demonstration.add_argument("--destination", required=True)
    demonstration.set_defaults(func=demo)
    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
