#!/usr/bin/env python3
"""Deterministic source ledgers for discourse-local symbol grounding.

Stdlib only.  This program extracts evidence candidates; it never turns a candidate
into a definition and never reads formulae from images or OCR output.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import xml.etree.ElementTree as ET
from collections import Counter
from pathlib import Path
from typing import Any

CATEGORIES = [
    "direct_source_definition",
    "contextual_inference",
    "common_knowledge_external",
    "not_reported",
    "conflict",
]
DEFINITION_RE = re.compile(
    r"\bwhere\b|\bdenotes?\b|\bis\s+defined\s+as\b|\bare\s+defined\s+as\b|"
    r"\brepresents?\b|\brepresenting\b|\bstands\s+for\b|取值|表示|定义为",
    re.IGNORECASE,
)
UNIT_RE = re.compile(
    r"\bunits?\s+(?:of|is|are)\b|\bmeasured\s+in\b|\bin\s+"
    r"(?:nm|µm|um|mm|cm|km|m|kg|g|s|ms|K|Pa|kPa|MPa|GPa|Hz|V|A|Ω|ohm|ohms|J|eV|mol|K)\b|"
    r"(?:nm|µm|um|mm|cm|km|Pa|kPa|MPa|GPa|Hz|eV|Ω|ohm|ohms)\b|单位为|单位是|计量单位",
    re.IGNORECASE,
)
RANGE_RE = re.compile(
    r"\branges?\s+from\b|\bbetween\b|\bfrom\s+[-+]?\d|\bwithin\b|"
    r"[-+]?\d+(?:\.\d+)?\s*(?:–|—|\.\.|to)\s*[-+]?\d|"
    r"[≤≥<>]\s*[-+]?\d|范围为|取值范围|介于|至少|至多",
    re.IGNORECASE,
)
SOURCE_KEYS = (
    "source_xml", "publisher_xml", "xml_path", "document_path", "source_path",
    "source_text", "xml", "document", "documents", "source", "sources",
    "input_files", "files", "article", "articles", "input",
)


def norm_text(value: str) -> str:
    return " ".join(value.split())


def text_of(node: ET.Element) -> str:
    return norm_text("".join(node.itertext()))


def tag(node: ET.Element) -> str:
    return node.tag.rsplit("}", 1)[-1].lower()


def digest(data: str | bytes) -> str:
    if isinstance(data, str):
        data = data.encode("utf-8")
    return hashlib.sha256(data).hexdigest()


def resolve_file(value: str, case_dir: Path) -> Path | None:
    candidate = Path(value).expanduser()
    attempts = [candidate] if candidate.is_absolute() else [case_dir / candidate, Path("/input") / candidate]
    for attempt in attempts:
        if attempt.is_file():
            return attempt.resolve()
    return None


def discover_sources(case: dict[str, Any], case_path: Path) -> tuple[list[dict[str, str]], list[str]]:
    """Read declared XML/text only, with a conservative XML-file fallback."""
    case_dir = case_path.parent
    sources: list[dict[str, str]] = []
    warnings: list[str] = []
    seen: set[str] = set()

    def add_text(text: str, label: str, force_text: bool = False) -> None:
        stripped = text.lstrip()
        kind = "xml" if stripped.startswith("<") else "text"
        if kind != "xml" and not force_text:
            return
        key = digest(text)
        if key in seen:
            return
        seen.add(key)
        sources.append({"content": text, "label": label, "kind": kind, "origin": "embedded"})

    def add_file(path: Path, label: str, force_text: bool = False) -> None:
        key = str(path)
        if key in seen:
            return
        try:
            content = path.read_text(encoding="utf-8")
        except (OSError, UnicodeError) as exc:
            warnings.append(f"Cannot read {path}: {exc}")
            return
        kind = "xml" if path.suffix.lower() in (".xml", ".nxml", ".xhtml") or content.lstrip().startswith("<") else "text"
        if kind != "xml" and not force_text:
            return
        seen.add(key)
        sources.append({"content": content, "label": label, "kind": kind, "origin": str(path)})

    visited: set[int] = set()

    def visit(node: Any, hint: str, force_text: bool = False) -> None:
        if id(node) in visited:
            return
        if isinstance(node, (dict, list)):
            visited.add(id(node))
        if isinstance(node, str):
            path = resolve_file(node, case_dir)
            if path is not None:
                add_file(path, node, force_text or hint == "source_text")
            elif node.lstrip().startswith("<"):
                add_text(node, hint or "embedded source")
            elif force_text or hint == "source_text":
                add_text(node, hint or "source text", force_text=True)
            return
        if isinstance(node, list):
            for item in node:
                visit(item, hint, force_text)
            return
        if not isinstance(node, dict):
            return
        # Common wrapper forms: {path: ...}, {content: ..., format: ...}.
        fmt = str(node.get("format", node.get("type", ""))).lower()
        for key in ("path", "file", "file_path", "filename"):
            if isinstance(node.get(key), str):
                visit(node[key], hint or key, force_text or fmt in ("text", "txt", "plain"))
        for key in ("content", "text", "xml", "source_xml", "publisher_xml"):
            if isinstance(node.get(key), str):
                visit(node[key], hint or key, force_text or fmt in ("text", "txt", "plain") or key in ("text",))
        for key, value in node.items():
            if key in SOURCE_KEYS:
                visit(value, key, force_text or key == "source_text")
            elif key == "paper" and isinstance(value, (dict, list)):
                visit(value, "paper", force_text)

    visit(case, "case")
    if not sources:
        for path in sorted(case_dir.glob("*.xml"), key=lambda p: p.name):
            add_file(path, path.name)
    if not sources:
        warnings.append(
            "No readable publisher XML or declared source text was found. No formula representation or values are inferred."
        )
    for index, source in enumerate(sources, 1):
        source["document_id"] = f"doc-{index:04d}"
        source["sha256"] = digest(source["content"])
    return sources, warnings


def section_nodes(root: ET.Element) -> list[ET.Element]:
    return [n for n in root.iter() if tag(n) in ("sec", "section", "chapter")]


def node_paths(root: ET.Element) -> dict[int, str]:
    paths: dict[int, str] = {}

    def walk(node: ET.Element, path: str) -> None:
        paths[id(node)] = path
        counts: Counter[str] = Counter()
        for child in list(node):
            name = tag(child)
            counts[name] += 1
            walk(child, f"{path}/{name}[{counts[name]}]")

    walk(root, f"/{tag(root)}[1]")
    return paths


def split_sentences(text: str) -> list[tuple[int, int, str]]:
    """Return exact normalized substrings and offsets; deliberately deterministic."""
    if not text:
        return []
    spans: list[tuple[int, int]] = []
    start = 0
    i = 0
    while i < len(text):
        ch = text[i]
        terminal = ch in "。！？" or ch in ".!?"
        if terminal:
            if ch == "." and i > 0 and i + 1 < len(text) and text[i - 1].isdigit() and text[i + 1].isdigit():
                i += 1
                continue
            end = i + 1
            while end < len(text) and text[end] in "。！？.!?\"'”’)]}":
                end += 1
            # Latin punctuation ends a sentence at whitespace/end; CJK punctuation does so directly.
            if ch in "。！？" or end == len(text) or text[end].isspace():
                spans.append((start, end))
                start = end
                while start < len(text) and text[start].isspace():
                    start += 1
                i = start
                continue
        i += 1
    if start < len(text):
        spans.append((start, len(text)))
    result = []
    for left, right in spans:
        while left < right and text[left].isspace():
            left += 1
        while right > left and text[right - 1].isspace():
            right -= 1
        if right > left:
            result.append((left, right, text[left:right]))
    return result


def short_cue_quote(sentence: str, match: re.Match[str], radius: int = 120) -> str:
    if len(sentence) <= 240:
        return sentence
    left = max(0, match.start() - radius)
    right = min(len(sentence), match.end() + radius)
    # No ellipses: the result must remain a literal source substring.
    return sentence[left:right].strip()


def symbol_from_math(node: ET.Element) -> dict[str, Any] | None:
    """Canonicalize an mi or script-wrapper without discarding any script."""
    name = tag(node)
    if name == "mmultiscripts":
        children = [c for c in list(node) if tag(c) not in ("annotation", "annotation-xml")]
        if not children:
            return None
        base = symbol_from_math(children[0])
        if base is None:
            base_text = text_of(children[0])
            if not base_text:
                return None
            base = {"canonical": base_text, "base_glyph": base_text, "scripts": {}}
        script_parts = [{"role": "prescripts" if tag(child) == "mprescripts" else tag(child),
                         "text": text_of(child)} for child in children[1:]]
        scripts = dict(base["scripts"])
        scripts["multiscripts"] = script_parts
        signature = json.dumps(script_parts, ensure_ascii=False, sort_keys=True)
        return {"canonical": base["canonical"] + f"m{signature}",
                "base_glyph": base["base_glyph"], "scripts": scripts}
    if name == "mi":
        glyph = text_of(node)
        if not glyph:
            return None
        return {"canonical": glyph, "base_glyph": glyph, "scripts": {}}
    specs = {
        "msub": (("sub", 1),), "msup": (("sup", 1),),
        "msubsup": (("sub", 1), ("sup", 2)),
        "munder": (("under", 1),), "mover": (("over", 1),),
        "munderover": (("under", 1), ("over", 2)),
    }
    if name not in specs:
        return None
    children = [c for c in list(node) if tag(c) not in ("annotation", "annotation-xml")]
    if not children:
        return None
    base = symbol_from_math(children[0])
    if base is None:
        base_text = text_of(children[0])
        if not base_text:
            return None
        base = {"canonical": base_text, "base_glyph": base_text, "scripts": {}}
    scripts = dict(base["scripts"])
    pieces = base["canonical"]
    for script_name, position in specs[name]:
        value = text_of(children[position]) if len(children) > position else ""
        scripts[script_name] = value
        marker = {"sub": "_", "sup": "^", "under": "u", "over": "o"}[script_name]
        pieces += f"{marker}{{{value}}}"
    return {"canonical": pieces, "base_glyph": base["base_glyph"], "scripts": scripts}


def math_symbols(math: ET.Element) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []

    def walk(node: ET.Element) -> None:
        if tag(node) in ("annotation", "annotation-xml"):
            return
        record = symbol_from_math(node)
        if record is not None:
            record["mathml"] = ET.tostring(node, encoding="unicode")
            records.append(record)
            return
        for child in list(node):
            walk(child)

    walk(math)
    return records


def parse_document(source: dict[str, str], counters: dict[str, int]) -> dict[str, Any]:
    if source["kind"] != "xml":
        # Declared plain text is evidence prose, never a formula representation.
        pseudo = ET.Element("text-document")
        for block in re.split(r"\n\s*\n", source["content"]):
            if block.strip():
                p = ET.SubElement(pseudo, "p")
                p.text = block.strip()
        root = pseudo
    else:
        root = ET.fromstring(source["content"])
    doc_id = source["document_id"]
    paths = node_paths(root)
    sections_found = section_nodes(root)
    section_by_node: dict[int, dict[str, Any]] = {}
    sections: list[dict[str, Any]] = []
    root_scope = {"section_id": f"{doc_id}-sec-root", "document_id": doc_id,
                  "title": "Document scope", "source_pointer": paths[id(root)]}
    for node in [root] if not sections_found else []:
        section_by_node[id(node)] = root_scope
        sections.append(root_scope)
    if sections_found:
        # Root scope is retained only if paragraphs/formulae occur outside explicit sections.
        for node in sections_found:
            counters["section"] += 1
            title_node = next((c for c in list(node) if tag(c) == "title"), None)
            scope = {"section_id": f"{doc_id}-sec-{counters['section']:04d}", "document_id": doc_id,
                     "title": text_of(title_node) if title_node is not None else "",
                     "source_pointer": paths[id(node)]}
            section_by_node[id(node)] = scope
            sections.append(scope)
    else:
        section_by_node[id(root)] = root_scope

    parents = {id(child): node for node in root.iter() for child in list(node)}
    node_section: dict[int, dict[str, Any]] = {}

    def assign_scope(node: ET.Element, current: dict[str, Any]) -> None:
        own = section_by_node.get(id(node), current)
        node_section[id(node)] = own
        for child in list(node):
            assign_scope(child, own)

    fallback = root_scope
    assign_scope(root, fallback)
    paragraphs: list[dict[str, Any]] = []
    sentences: list[dict[str, Any]] = []
    paragraph_by_node: dict[int, dict[str, Any]] = {}
    used_root_scope = False
    for node in root.iter():
        if tag(node) == "p":
            counters["paragraph"] += 1
            scope = node_section[id(node)]
            if scope is root_scope:
                used_root_scope = True
            paragraph = {"paragraph_id": f"p-{counters['paragraph']:06d}", "document_id": doc_id,
                         "section_id": scope["section_id"], "source_pointer": paths[id(node)],
                         "text": text_of(node)}
            paragraphs.append(paragraph)
            paragraph_by_node[id(node)] = paragraph
            for number, (left, right, sentence_text) in enumerate(split_sentences(paragraph["text"]), 1):
                counters["sentence"] += 1
                sentences.append({"sentence_id": f"s-{counters['sentence']:06d}", "document_id": doc_id,
                                  "section_id": scope["section_id"], "paragraph_id": paragraph["paragraph_id"],
                                  "sentence_in_paragraph": number, "char_start": left, "char_end": right,
                                  "source_pointer": paths[id(node)], "text": sentence_text})

    def ancestor(node: ET.Element, targets: set[str]) -> ET.Element | None:
        current = parents.get(id(node))
        while current is not None:
            if tag(current) in targets:
                return current
            current = parents.get(id(current))
        return None

    formulas: list[dict[str, Any]] = []
    symbol_instances: list[dict[str, Any]] = []
    instance_lookup: dict[tuple[str, str, str], dict[str, Any]] = {}
    for node in root.iter():
        name = tag(node)
        is_math = name == "math" and ancestor(node, {"math"}) is None
        is_non_math_formula = name in ("disp-formula", "inline-formula", "formula")
        if is_non_math_formula:
            if any(tag(n) == "math" for n in node.iter()):
                continue
            if ancestor(node, {"disp-formula", "inline-formula", "formula"}) is not None:
                continue
        if not (is_math or is_non_math_formula):
            continue
        counters["formula"] += 1
        formula_id = f"f-{counters['formula']:06d}"
        p_node = ancestor(node, {"p"})
        paragraph = paragraph_by_node.get(id(p_node)) if p_node is not None else None
        scope = node_section[id(node)]
        if scope is root_scope:
            used_root_scope = True
        in_sentences = [s for s in sentences if paragraph and s["paragraph_id"] == paragraph["paragraph_id"]]
        symbols = math_symbols(node) if is_math else []
        formula_symbol_instance_ids: list[str] = []
        occurrence_symbols: list[dict[str, Any]] = []
        for index, symbol in enumerate(symbols, 1):
            signature = json.dumps(symbol["scripts"], ensure_ascii=False, sort_keys=True)
            key = (scope["section_id"], symbol["canonical"], signature)
            instance = instance_lookup.get(key)
            if instance is None:
                counters["symbol_instance"] += 1
                instance = {"symbol_instance_id": f"sym-{counters['symbol_instance']:06d}",
                            "document_id": doc_id, "section_id": scope["section_id"],
                            "canonical": symbol["canonical"], "base_glyph": symbol["base_glyph"],
                            "scripts": symbol["scripts"], "first_formula_id": formula_id,
                            "formula_ids": []}
                instance_lookup[key] = instance
                symbol_instances.append(instance)
            if formula_id not in instance["formula_ids"]:
                instance["formula_ids"].append(formula_id)
            if instance["symbol_instance_id"] not in formula_symbol_instance_ids:
                formula_symbol_instance_ids.append(instance["symbol_instance_id"])
            occurrence_symbols.append({**symbol, "symbol_occurrence_id": f"{formula_id}-symbol-{index:03d}",
                                       "symbol_instance_id": instance["symbol_instance_id"]})
        formula = {"formula_id": formula_id, "document_id": doc_id, "section_id": scope["section_id"],
                   "section_title": scope["title"], "paragraph_id": paragraph["paragraph_id"] if paragraph else None,
                   "source_pointer": paths[id(node)], "representation": "mathml" if is_math else "xml_text_only",
                   "mathml": ET.tostring(node, encoding="unicode") if is_math else None,
                   "formula_text": text_of(node), "symbol_occurrences": occurrence_symbols,
                   "symbol_instance_ids": formula_symbol_instance_ids,
                   "context": {"paragraph_text": paragraph["text"] if paragraph else "",
                               "sentence_text": in_sentences[0]["text"] if len(in_sentences) == 1 else "",
                               "sentence_ids": [s["sentence_id"] for s in in_sentences]}}
        formulas.append(formula)

    candidates: list[dict[str, Any]] = []
    for sentence in sentences:
        matches = [(kind, regex.search(sentence["text"])) for kind, regex in
                   (("definition", DEFINITION_RE), ("unit", UNIT_RE), ("range", RANGE_RE))]
        kinds = [kind for kind, match in matches if match]
        if not kinds:
            continue
        cue_match = next(match for _, match in matches if match)
        assert cue_match is not None
        counters["candidate"] += 1
        candidates.append({"candidate_id": f"cand-{counters['candidate']:06d}", "document_id": doc_id,
                           "section_id": sentence["section_id"], "paragraph_id": sentence["paragraph_id"],
                           "sentence_id": sentence["sentence_id"], "kinds": kinds,
                           "quote": short_cue_quote(sentence["text"], cue_match),
                           "locator": {"document_id": doc_id, "section_id": sentence["section_id"],
                                       "paragraph_id": sentence["paragraph_id"], "sentence_id": sentence["sentence_id"],
                                       "source_pointer": sentence["source_pointer"]},
                           "candidate_only": True, "confirmation_required": True})
    if sections_found and used_root_scope and root_scope not in sections:
        sections.insert(0, root_scope)
    return {"sections": sections, "paragraphs": paragraphs, "sentences": sentences,
            "formulas": formulas, "symbol_instances": symbol_instances, "candidates": candidates}


def build_ledger(case_path: Path, task_path: Path | None) -> dict[str, Any]:
    case = json.loads(case_path.read_text(encoding="utf-8"))
    if not isinstance(case, dict) or "case_id" not in case:
        raise ValueError("case.json must be an object containing case_id")
    sources, warnings = discover_sources(case, case_path)
    counters: Counter[str] = Counter()
    merged: dict[str, Any] = {"sections": [], "paragraphs": [], "sentences": [], "formulas": [],
                              "symbol_instances": [], "candidates": []}
    for source in sources:
        try:
            parsed = parse_document(source, counters)
            for key in merged:
                merged[key].extend(parsed[key])
        except (ET.ParseError, ValueError) as exc:
            warnings.append(f"Cannot parse {source['document_id']} ({source['label']}): {exc}")
    mathml_count = sum(f["representation"] == "mathml" for f in merged["formulas"])
    non_mathml_count = len(merged["formulas"]) - mathml_count
    if mathml_count:
        representation_status = "mathml_present"
    elif non_mathml_count:
        representation_status = "xml_formula_without_mathml"
        warnings.append("Formula containers lack MathML; symbols were not reconstructed from formula text.")
    else:
        representation_status = "no_formula_representation"
        warnings.append("No formula representation is available. Use partial or insufficient_evidence; do not invent formula values.")
    task_hash = None
    if task_path and task_path.is_file():
        task_hash = digest(task_path.read_bytes())
    contract = case.get("output_contract", {})
    ledger: dict[str, Any] = {
        "schema_version": "symbol-scope-ledger-1",
        "case_id": case["case_id"],
        "task_sha256": task_hash,
        "source_policy": "Publisher XML/source MathML and declared prose only; never formula OCR.",
        "source_summary": {
            "formula_representation_status": representation_status,
            "mathml_formula_count": mathml_count,
            "xml_text_only_formula_count": non_mathml_count,
            "documents": [{k: source[k] for k in ("document_id", "label", "kind", "origin", "sha256")} for source in sources],
        },
        "output_contract": contract,
        "warnings": warnings,
        **merged,
    }
    ledger["ledger_sha256"] = digest(json.dumps(ledger, ensure_ascii=False, sort_keys=True))
    return ledger


def write_markdown(ledger: dict[str, Any], path: Path) -> None:
    lines = ["# Extraction ledger", "", f"Case: `{ledger['case_id']}`", "",
             f"Formula representation: **{ledger['source_summary']['formula_representation_status']}**", "",
             "Candidates are unconfirmed evidence leads, not definitions.", "",
             "## Scoped symbol instances", "",
             "| Instance | Section | Canonical symbol | Base | Full scripts | Formula occurrences |",
             "|---|---|---|---|---|---|"]
    for symbol in ledger["symbol_instances"]:
        scripts = json.dumps(symbol["scripts"], ensure_ascii=False, sort_keys=True)
        lines.append(f"| {symbol['symbol_instance_id']} | {symbol['section_id']} | `{symbol['canonical']}` | "
                     f"`{symbol['base_glyph']}` | `{scripts}` | {', '.join(symbol['formula_ids'])} |")
    lines += ["", "## Evidence candidates", "", "| Candidate | Kinds | Locator | Exact quote |", "|---|---|---|---|"]
    for candidate in ledger["candidates"]:
        lines.append(f"| {candidate['candidate_id']} | {', '.join(candidate['kinds'])} | {candidate['sentence_id']} | "
                     f"{candidate['quote'].replace('|', '\\|')} |")
    lines += ["", "## Formula occurrences", ""]
    for formula in ledger["formulas"]:
        lines += [f"### {formula['formula_id']} — {formula['section_id']}", "",
                  f"Locator: `{formula['source_pointer']}`", "",
                  f"Symbols: {', '.join(formula['symbol_instance_ids']) or '(none extracted)'}", "",
                  f"Context: {formula['context']['paragraph_text']}", ""]
    if ledger["warnings"]:
        lines += ["## Warnings", ""] + [f"- {warning}" for warning in ledger["warnings"]] + [""]
    path.write_text("\n".join(lines), encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--case", default="/input/case.json")
    parser.add_argument("--task", default="/input/task.md")
    parser.add_argument("--work", default="/app/work")
    args = parser.parse_args(argv)
    case_path = Path(args.case).resolve()
    work = Path(args.work).resolve()
    work.mkdir(parents=True, exist_ok=True)
    try:
        ledger = build_ledger(case_path, Path(args.task).resolve() if args.task else None)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"ledger: fatal: {exc}", file=sys.stderr)
        return 1
    (work / "ledger.json").write_text(json.dumps(ledger, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    write_markdown(ledger, work / "ledger.md")
    template = {
        "schema_version": "symbol-scope-bindings-1",
        "case_id": ledger["case_id"],
        "requested_status": "partial" if not ledger["formulas"] else None,
        "symbol_bindings": [],
        "symbol_instance_checklist": [
            {"symbol_instance_id": s["symbol_instance_id"], "canonical": s["canonical"],
             "section_id": s["section_id"], "scripts": s["scripts"],
             "instruction": "Author a scope-specific evidence binding or explain why it remains unbound."}
            for s in ledger["symbol_instances"]
        ],
        "formula_coverage": [
            {"formula_id": f["formula_id"], "covered": None, "excluded": False,
             "symbol_instance_ids": f["symbol_instance_ids"], "reason": "Agent review required"}
            for f in ledger["formulas"]
        ],
        "limitations": list(ledger["warnings"]),
        "evidence_categories": CATEGORIES,
        "output_fields": {},
    }
    (work / "bindings.template.json").write_text(json.dumps(template, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"case_id": ledger["case_id"], "formulas": len(ledger["formulas"]),
                      "symbol_instances": len(ledger["symbol_instances"]), "candidates": len(ledger["candidates"]),
                      "work": str(work), "warnings": len(ledger["warnings"])}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
