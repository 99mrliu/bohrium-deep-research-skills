#!/usr/bin/env python3
"""Shared stdlib helpers. No semantic or numeric extraction happens here."""
from __future__ import annotations

import hashlib
import json
import os
import tempfile
from pathlib import Path

FIELD_STATUSES = {"reported", "not_reported", "source_conflict", "extraction_failed"}
RUN_STATUSES = {"answered", "partial", "insufficient_evidence", "input_error"}
CLAIM_KINDS = {
    "author_conclusion",
    "limitation",
    "hypothesis_speculation",
    "method_observation",
    "prior_work_cited_claim",
}


class ContractError(ValueError):
    """A source-grounding or output-contract error."""


def load_json(path: Path):
    try:
        with path.open("r", encoding="utf-8") as handle:
            return json.load(handle)
    except FileNotFoundError as exc:
        raise ContractError(f"Missing JSON input: {path}") from exc
    except json.JSONDecodeError as exc:
        raise ContractError(f"Invalid JSON in {path}: line {exc.lineno}, column {exc.colno}: {exc.msg}") from exc


def atomic_json(path: Path, value) -> None:
    """Write deterministic, human-auditable UTF-8 JSON without partial files."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=path.name + ".", suffix=".tmp", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(value, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
        os.replace(temporary, path)
    except BaseException:
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            pass
        raise


def normalize_target_fields(document):
    """Accept common target-fields wrappers while preserving request order."""
    if isinstance(document, list):
        fields = document
    elif isinstance(document, dict):
        fields = None
        for key in ("fields", "target_fields", "requested_fields", "items"):
            if isinstance(document.get(key), list):
                fields = document[key]
                break
        if fields is None and isinstance(document.get("field_id"), str):
            fields = [document]
        if fields is None:
            raise ContractError("target-fields.json must contain a fields/target_fields/requested_fields list")
    else:
        raise ContractError("target-fields.json must be an object or list")
    normalized = []
    seen = set()
    for index, field in enumerate(fields):
        if not isinstance(field, dict) or not isinstance(field.get("field_id"), str) or not field["field_id"].strip():
            raise ContractError(f"Target field {index} lacks a nonempty field_id")
        field_id = field["field_id"]
        if field_id in seen:
            raise ContractError(f"Duplicate requested field_id: {field_id}")
        seen.add(field_id)
        normalized.append(field)
    return normalized


def source_paragraph_index(source_document):
    """Index only explicit source paragraphs; pages are never inferred."""
    index = {}
    seen_sources = set()
    sources = source_document.get("sources") if isinstance(source_document, dict) else None
    if not isinstance(sources, list):
        raise ContractError("Source registry must contain a sources list")
    for source in sources:
        source_id = source.get("source_id")
        paragraphs = source.get("paragraphs")
        if not isinstance(source_id, str) or not source_id or not isinstance(paragraphs, list):
            raise ContractError("Every source needs source_id and a paragraphs list")
        if source_id in seen_sources:
            raise ContractError(f"Duplicate source_id: {source_id}")
        seen_sources.add(source_id)
        for paragraph in paragraphs:
            paragraph_id = paragraph.get("paragraph_id")
            text = paragraph.get("text")
            if not isinstance(paragraph_id, str) or not paragraph_id or not isinstance(text, str):
                raise ContractError(f"Bad paragraph in source {source_id}")
            key = (source_id, paragraph_id)
            if key in index:
                raise ContractError(f"Duplicate source paragraph: {source_id}/{paragraph_id}")
            page = paragraph.get("page")
            if page is not None and (not isinstance(page, int) or isinstance(page, bool) or page < 1):
                raise ContractError(f"Invalid explicit page for {source_id}/{paragraph_id}")
            index[key] = {"text": text, "page": page}
    if not index:
        raise ContractError("Source registry has no paragraphs")
    return index


def verify_evidence(evidence, paragraph_index, context: str) -> None:
    """Require a verbatim substring and an existing explicit source location."""
    if not isinstance(evidence, dict):
        raise ContractError(f"{context}: evidence item must be an object")
    for key in ("source_id", "paragraph_id", "quote"):
        if not isinstance(evidence.get(key), str) or not evidence.get(key):
            raise ContractError(f"{context}: evidence requires nonempty {key}")
    key = (evidence["source_id"], evidence["paragraph_id"])
    if key not in paragraph_index:
        raise ContractError(f"{context}: unknown source location {key[0]}/{key[1]}")
    paragraph = paragraph_index[key]
    if evidence["quote"] not in paragraph["text"]:
        raise ContractError(f"{context}: quotation is not a verbatim substring at {key[0]}/{key[1]}")
    if "page" in evidence and evidence["page"] != paragraph["page"]:
        raise ContractError(f"{context}: evidence page does not match the registered source paragraph")


def evidence_key(item):
    return (item.get("source_id"), item.get("paragraph_id"), item.get("page"), item.get("quote"))


def dedupe_evidence(items):
    output = []
    seen = set()
    for item in items:
        key = evidence_key(item)
        if key not in seen:
            seen.add(key)
            output.append(item)
    return output


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def pending_result(case_id: str, targets, note: str, status: str = "partial"):
    fields = []
    for target in targets:
        field_id = target["field_id"]
        fields.append({
            "field_id": field_id,
            "status": "extraction_failed",
            "scalar": None,
            "units": None,
            "statistic": None,
            "experimental_condition": None,
            "condition": None,
            "comparator": None,
            "paragraph_id": None,
            "quote": "",
            "evidence": [],
            "notes": note,
        })
    return {
        "case_id": case_id,
        "status": status,
        "result": {"fields": fields, "field_results": fields},
        "claims": [],
        "uncertainties": [{"kind": "pending_curation", "detail": note}],
        "sources": [],
        "change_records": [{"action": "initialize_honest_partial", "detail": note}],
    }
