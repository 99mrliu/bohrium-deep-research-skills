#!/usr/bin/env python3
"""Inventory runtime material, save a partial result early, and index source text.

Only mechanical text extraction/paragraph registration is performed. The reading
agent must curate discourse classes and target-field mappings from the actual paper.
PDF text uses the optional system `pdftotext`; failure is reported, never hidden.
"""
from __future__ import annotations

import argparse
import csv
import json
import re
import shutil
import subprocess
import sys
from html.parser import HTMLParser
from pathlib import Path

from common import ContractError, atomic_json, load_json, normalize_target_fields, pending_result, sha256_file

SUFFIXES = {".pdf", ".txt", ".md", ".html", ".htm", ".xml", ".json", ".jsonl", ".csv"}
CONTROL_INPUTS = {"case.json", "target-fields.json", "task.md"}
WHITESPACE = re.compile(r"\s+")


def clean_text(text):
    return WHITESPACE.sub(" ", text.replace("\u00ad", "")).strip()


def paragraphs_from_text(text, source_id, pages=False):
    output = []
    page_chunks = text.split("\f") if pages else [text]
    for page_index, page_text in enumerate(page_chunks, 1):
        if pages and page_index == len(page_chunks) and not page_text.strip():
            continue
        chunks = re.split(r"(?:\r?\n)[ \t]*(?:\r?\n)+", page_text)
        if len(chunks) == 1 and page_text.strip():
            # Preserve line-level audit ability even in single-newline extracts.
            nonempty = [line for line in page_text.splitlines() if line.strip()]
            chunks = nonempty if len(nonempty) > 1 else chunks
        for chunk in chunks:
            cleaned = clean_text(chunk)
            if cleaned:
                output.append({
                    "paragraph_id": f"{source_id}-P{len(output) + 1:04d}",
                    "page": page_index if pages else None,
                    "text": cleaned,
                })
    return output


class TextHTMLParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.parts = []
        self.ignored = 0

    def handle_starttag(self, tag, attrs):
        if tag in {"script", "style"}:
            self.ignored += 1
        if tag in {"p", "div", "section", "article", "tr", "h1", "h2", "h3", "li", "br"}:
            self.parts.append("\n\n")

    def handle_endtag(self, tag):
        if tag in {"script", "style"} and self.ignored:
            self.ignored -= 1
        if tag in {"p", "div", "section", "article", "tr", "h1", "h2", "h3", "li"}:
            self.parts.append("\n\n")

    def handle_data(self, data):
        if not self.ignored:
            self.parts.append(data)


def json_paragraph_records(document):
    """Use only explicitly structured paragraph records, not arbitrary JSON values."""
    records = []
    if isinstance(document, dict) and isinstance(document.get("paragraphs"), list):
        candidates = document["paragraphs"]
    elif isinstance(document, list):
        candidates = document
    else:
        candidates = []
    for index, item in enumerate(candidates, 1):
        if not isinstance(item, dict) or not isinstance(item.get("text"), str):
            continue
        records.append({
            "paragraph_id": str(item.get("paragraph_id") or item.get("id") or f"P{index:04d}"),
            "page": item.get("page"),
            "text": clean_text(item["text"]),
        })
    return records


def extract_file(path, source_id):
    suffix = path.suffix.lower()
    warnings = []
    if suffix == ".pdf":
        executable = shutil.which("pdftotext")
        if not executable:
            return [], ["No pdftotext executable is available; PDF text was not extracted. Use an available PDF reader/OCR manually, then register the actual paragraphs."]
        try:
            completed = subprocess.run(
                [executable, "-layout", "-enc", "UTF-8", str(path), "-"],
                check=False, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=120,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            return [], [f"pdftotext failed for {path.name}: {exc}"]
        if completed.returncode != 0:
            return [], [f"pdftotext exited {completed.returncode} for {path.name}: {completed.stderr.decode('utf-8', errors='replace').strip()}"]
        text = completed.stdout.decode("utf-8", errors="replace")
        paragraphs = paragraphs_from_text(text, source_id, pages=True)
        if not paragraphs:
            warnings.append("PDF yielded no text; it may be scanned/image-only. OCR and visual inspection are required.")
        return paragraphs, warnings
    raw = path.read_text(encoding="utf-8", errors="replace")
    if suffix == ".json":
        try:
            document = json.loads(raw)
        except json.JSONDecodeError as exc:
            return [], [f"Invalid source JSON {path.name}: {exc}"]
        # A complete source registry can be merged by the caller.
        if isinstance(document, dict) and isinstance(document.get("sources"), list):
            return document["sources"], warnings
        records = json_paragraph_records(document)
        if records:
            for record in records:
                if not str(record["paragraph_id"]).startswith(source_id + "-"):
                    record["paragraph_id"] = source_id + "-" + record["paragraph_id"]
            return records, warnings
        return [], ["JSON had no explicit paragraphs list with text; no arbitrary values were treated as paper prose."]
    if suffix == ".jsonl":
        candidates = []
        for line in raw.splitlines():
            if line.strip():
                candidates.append(json.loads(line))
        records = json_paragraph_records(candidates)
        return records, warnings
    if suffix in {".html", ".htm", ".xml"}:
        parser = TextHTMLParser()
        parser.feed(raw)
        return paragraphs_from_text("".join(parser.parts), source_id), warnings
    if suffix == ".csv":
        rows = list(csv.reader(raw.splitlines()))
        return paragraphs_from_text("\n\n".join(" | ".join(row) for row in rows if any(row)), source_id), warnings
    return paragraphs_from_text(raw, source_id), warnings


def normalize_adopted_sources(adopted):
    sources = []
    for source in adopted:
        if not isinstance(source, dict) or not isinstance(source.get("paragraphs"), list):
            raise ContractError("Adopted source registry is malformed")
        copied = dict(source)
        copied["source_id"] = str(source.get("source_id") or f"S{len(sources) + 1}")
        copied["paragraphs"] = []
        for index, paragraph in enumerate(source["paragraphs"], 1):
            if not isinstance(paragraph, dict) or not isinstance(paragraph.get("text"), str):
                raise ContractError("Adopted paragraph must contain text")
            copied["paragraphs"].append({
                "paragraph_id": str(paragraph.get("paragraph_id") or f"{copied['source_id']}-P{index:04d}"),
                "page": paragraph.get("page"),
                "text": clean_text(paragraph["text"]),
            })
        sources.append(copied)
    return sources


def make_template(targets):
    fields = []
    for target in targets:
        fields.append({
            "field_id": target["field_id"],
            "status": "extraction_failed",
            "scalar": None,
            "units": None,
            "statistic": None,
            "experimental_condition": None,
            "condition": None,
            "comparator": None,
            "evidence": [],
            "observation_ids": [],
            "claim_ids": [],
            "notes": "Pending actual-paper reading; do not submit this placeholder as an extracted value.",
        })
    return {
        "schema_version": "claim-evidence-curation/1.0",
        "conditions": [],
        "observations": [],
        "claims": [],
        "field_results": fields,
        "uncertainties": [{"kind": "pending_curation", "detail": "Read the registered source paragraphs and replace placeholders with sourced curation."}],
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=Path("/input"))
    parser.add_argument("--work", type=Path, default=Path("/app/work"))
    parser.add_argument("--output", type=Path, default=Path("/app/output"))
    parser.add_argument("--reset", action="store_true", help="Replace an existing early result; otherwise preserve it")
    args = parser.parse_args(argv)
    args.work.mkdir(parents=True, exist_ok=True)
    args.output.mkdir(parents=True, exist_ok=True)
    result_path = args.output / "result.json"
    case = {}
    try:
        case = load_json(args.input / "case.json")
        targets = normalize_target_fields(load_json(args.input / "target-fields.json"))
        case_id = case.get("case_id") if isinstance(case, dict) else None
        if not isinstance(case_id, str) or not case_id:
            raise ContractError("case.json has no valid case_id")
    except ContractError as exc:
        failure_id = case.get("case_id") if isinstance(case, dict) and isinstance(case.get("case_id"), str) and case.get("case_id") else "UNKNOWN_CASE_ID"
        failure = pending_result(failure_id, [], str(exc), status="input_error")
        failure["result"] = {"fields": [], "field_results": []}
        atomic_json(result_path, failure)
        print(f"INPUT_ERROR: {exc}", file=sys.stderr)
        return 2

    note = "Inputs indexed; field-level reading and discourse curation are pending. Nulls are placeholders, not extracted values."
    if args.reset or not result_path.exists():
        atomic_json(result_path, pending_result(case_id, targets, note))
    atomic_json(args.work / "curation-template.json", make_template(targets))
    if not (args.work / "curated.json").exists():
        atomic_json(args.work / "curated.json", make_template(targets))
    task_path = args.input / "task.md"
    if task_path.exists():
        (args.work / "task.md").write_text(task_path.read_text(encoding="utf-8"), encoding="utf-8")

    warnings = []
    if not task_path.exists():
        warnings.append({"kind": "missing_task", "detail": "task.md was not supplied; only case/target instructions can be used."})
    material = [path for path in sorted(args.input.rglob("*")) if path.is_file() and path.suffix.lower() in SUFFIXES and path.name not in CONTROL_INPUTS]
    source_doc = {"schema_version": "registered-source-paragraphs/1.0", "sources": []}
    text_dir = args.work / "source-text"
    text_dir.mkdir(parents=True, exist_ok=True)
    try:
        for path in material:
            relative = path.relative_to(args.input).as_posix()
            source_id = f"S{len(source_doc['sources']) + 1}"
            extracted, source_warnings = extract_file(path, source_id)
            warnings.extend({"source_path": relative, "detail": warning} for warning in source_warnings)
            adopted = normalize_adopted_sources(extracted) if isinstance(extracted, dict) or (isinstance(extracted, list) and extracted and isinstance(extracted[0], dict) and "paragraphs" in extracted[0]) else []
            candidates = adopted if adopted else [{
                "source_id": source_id,
                "title": path.stem,
                "input_relative_path": relative,
                "media_type": path.suffix.lower().lstrip("."),
                "sha256": sha256_file(path),
                "paragraphs": extracted,
            }]
            for source in candidates:
                if not source.get("input_relative_path"):
                    source["input_relative_path"] = relative
                source_doc["sources"].append(source)
                text_lines = []
                for paragraph in source["paragraphs"]:
                    page = f" page={paragraph['page']}" if paragraph.get("page") is not None else ""
                    text_lines.append(f"[{source['source_id']}/{paragraph['paragraph_id']}{page}]\n{paragraph['text']}\n")
                (text_dir / f"{source['source_id']}.txt").write_text("\n".join(text_lines), encoding="utf-8")
        atomic_json(args.work / "sources.json", source_doc)
        if not material:
            warnings.append({"kind": "no_material", "detail": "No supported paper/artifact files were found under the input directory."})
        (args.work / "ingestion-warnings.json").write_text(json.dumps(warnings, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        # Upgrade only source inventory/uncertainties in the early partial; keep pending fields.
        if result_path.exists():
            early = load_json(result_path)
            if early.get("status") == "partial" and all(field.get("status") == "extraction_failed" for field in early.get("result", {}).get("fields", [])):
                early["sources"] = [{k: v for k, v in source.items() if k != "paragraphs"} for source in source_doc["sources"]]
                early["uncertainties"] = [{"kind": "pending_curation", "detail": note}] + warnings
                early.setdefault("change_records", []).append({"action": "register_sources", "detail": f"Registered {len(source_doc['sources'])} sources; semantics remain uncurated."})
                atomic_json(result_path, early)
    except (OSError, ContractError, json.JSONDecodeError) as exc:
        early = pending_result(case_id, targets, f"Source ingestion failed: {exc}", status="partial")
        atomic_json(result_path, early)
        print(f"INGESTION_ERROR: {exc}", file=sys.stderr)
        return 3
    print(f"Early partial: {result_path}")
    print(f"Registered sources: {len(source_doc['sources'])}; warnings: {len(warnings)}")
    print(f"Next: read {text_dir}, curate {args.work / 'curated.json'}, then run build_graph.py and validate_result.py")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
