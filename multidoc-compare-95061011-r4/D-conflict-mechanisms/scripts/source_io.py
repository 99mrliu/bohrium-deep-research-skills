#!/usr/bin/env python3
"""Local text/PDF preparation with stable paragraph identifiers; stdlib only."""
from __future__ import annotations

import hashlib
import re
import shutil
import subprocess
from pathlib import Path

MARKER = re.compile(r"^\[([A-Za-z0-9][A-Za-z0-9_.:-]*)\]\s*$")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def parse_marked_text(text: str) -> dict[str, str]:
    paragraphs: dict[str, str] = {}
    current = None
    lines: list[str] = []
    for line in text.splitlines():
        match = MARKER.match(line)
        if match:
            if current is not None:
                paragraphs[current] = "\n".join(lines).strip()
            current = match.group(1)
            if current in paragraphs:
                raise ValueError(f"duplicate paragraph marker: {current}")
            lines = []
        elif current is not None:
            lines.append(line)
    if current is not None:
        paragraphs[current] = "\n".join(lines).strip()
    if not paragraphs:
        raise ValueError("text source has no [paragraph-id] marker lines")
    empty = [key for key, value in paragraphs.items() if not value]
    if empty:
        raise ValueError(f"empty source paragraphs: {', '.join(empty)}")
    return paragraphs


def generated_pdf_paragraphs(text: str, document_id: str) -> dict[str, str]:
    paragraphs: dict[str, str] = {}
    for page_number, page in enumerate(text.split("\f"), start=1):
        blocks = re.split(r"\n\s*\n", page)
        block_number = 0
        for block in blocks:
            cleaned = "\n".join(line.rstrip() for line in block.splitlines()).strip()
            if cleaned:
                block_number += 1
                key = f"{document_id}-p{page_number:04d}-{block_number:03d}"
                paragraphs[key] = cleaned
    if not paragraphs:
        raise ValueError(f"PDF produced no non-empty text blocks: {document_id}")
    return paragraphs


def _inside_input(path: Path, input_dir: Path) -> None:
    try:
        path.relative_to(input_dir)
    except ValueError as exc:
        raise ValueError(f"document path escapes input directory: {path}") from exc


def prepare_documents(workorder: dict, input_dir: Path, work_dir: Path) -> tuple[dict, dict[str, dict[str, str]]]:
    """Return serializable registry and in-memory exact paragraph maps."""
    input_dir = input_dir.resolve()
    work_dir = work_dir.resolve()
    extracted_dir = work_dir / "sources"
    extracted_dir.mkdir(parents=True, exist_ok=True)
    documents = workorder.get("documents")
    if not isinstance(documents, list) or not documents:
        raise ValueError("workorder.documents must be a non-empty list")
    registry: dict[str, dict] = {}
    paragraphs_by_document: dict[str, dict[str, str]] = {}
    for document in documents:
        if not isinstance(document, dict):
            raise ValueError("each document must be an object")
        document_id = document.get("source_document_id")
        if not isinstance(document_id, str) or not document_id:
            raise ValueError("document source_document_id must be a non-empty string")
        if document_id in registry:
            raise ValueError(f"duplicate source_document_id: {document_id}")
        source_path = (input_dir / str(document.get("path", ""))).resolve()
        _inside_input(source_path, input_dir)
        if not source_path.is_file():
            raise ValueError(f"missing source document: {source_path}")
        suffix = source_path.suffix.lower()
        if suffix in {".txt", ".text", ".md"}:
            text = source_path.read_text(encoding="utf-8")
            paragraphs = parse_marked_text(text)
            extracted_text_path = source_path
            extraction = "explicit_paragraph_markers"
        elif suffix == ".pdf":
            executable = shutil.which("pdftotext")
            if executable is None:
                raise RuntimeError(
                    f"cannot extract {source_path.name}: local pdftotext is unavailable; "
                    "no installation is attempted and no citations are invented"
                )
            output_path = extracted_dir / f"{document_id}.txt"
            completed = subprocess.run(
                [executable, "-layout", str(source_path), str(output_path)],
                check=False, capture_output=True, text=True, timeout=120
            )
            if completed.returncode != 0 or not output_path.is_file():
                raise RuntimeError(f"pdftotext failed for {source_path.name}: {completed.stderr.strip()}")
            text = output_path.read_text(encoding="utf-8", errors="replace")
            paragraphs = generated_pdf_paragraphs(text, document_id)
            extracted_text_path = output_path
            extraction = "local_pdftotext_generated_page_paragraph_ids"
        else:
            raise ValueError(f"unsupported source type {suffix!r}; use PDF or UTF-8 marked text")
        registry[document_id] = {
            "source_document_id": document_id,
            "title": document.get("title", document_id),
            "source_path": str(source_path),
            "extracted_text_path": str(extracted_text_path),
            "sha256": sha256_file(source_path),
            "extraction": extraction,
            "paragraph_ids": list(paragraphs),
        }
        paragraphs_by_document[document_id] = paragraphs
    return {"documents": list(registry.values())}, paragraphs_by_document
