"""Shared I/O, normalization, contract, and rendering utilities."""
from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
import unicodedata
from pathlib import Path
from typing import Any, Iterable

import fitz

REQUIRED_RESULT_FIELDS = ("status", "sources", "uncertainty", "change_log", "artifacts")
LIGATURES = str.maketrans({
    "\ufb00": "ff", "\ufb01": "fi", "\ufb02": "fl", "\ufb03": "ffi",
    "\ufb04": "ffl", "\ufb05": "st", "\ufb06": "st", "\u00ad": "",
})


def atomic_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.replace(temporary, path)


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def normalize_text(text: str) -> str:
    """Normalize only for matching; raw extracted and quoted text is retained."""
    return re.sub(r"\s+", " ", unicodedata.normalize("NFKC", text).translate(LIGATURES)).strip()


def case_identifier(case: Any) -> str:
    if isinstance(case, dict):
        for key in ("case_id", "id", "caseId"):
            if key in case:
                return str(case[key])
    return "unknown_case"


def contract_fields(contract: Any) -> list[str]:
    """Return contracted field names without treating schema metadata as fields.

    Accepted shapes include ``fields: [name, ...]``, ``fields: {name: spec}``,
    lists of ``{name: ...}`` descriptors, and a direct ``{name: spec}`` map.
    Descriptor keys such as ``type`` and ``description`` are deliberately not
    traversed: they describe a field and are not output fields themselves.
    """
    names: list[str] = []

    def add(name: Any) -> None:
        if name is not None and str(name) and str(name) not in names:
            names.append(str(name))

    def walk(node: Any) -> None:
        if isinstance(node, str):
            add(node)
        elif isinstance(node, list):
            for item in node:
                if isinstance(item, dict):
                    descriptor = next((item[key] for key in ("name", "field", "key", "id")
                                       if key in item and isinstance(item[key], (str, int))), None)
                    if descriptor is not None:
                        add(descriptor)
                    else:
                        walk(item)
                else:
                    walk(item)
        elif isinstance(node, dict):
            if "fields" in node:
                walk(node["fields"])
                return
            descriptor = next((node[key] for key in ("name", "field", "key", "id")
                               if key in node and isinstance(node[key], (str, int))), None)
            if descriptor is not None:
                add(descriptor)
                return
            for field_name in node:
                add(field_name)

    walk(contract)
    return names


def semantic_contract_value(name: str, context: dict[str, Any]) -> Any:
    """Populate recognizable contract fields; unknown fields remain honestly null."""
    key = re.sub(r"[^a-z0-9]", "", name.lower())
    if "editable" in key and ("source" in key or "ppt" in key):
        return context.get("pptx")
    if key in {"exportartifact", "exportartifacts", "rendereddeck", "pdfartifact"} or (
        "export" in key and "artifact" in key
    ):
        return context.get("pdf")
    if "contentmap" in key or "evidencemap" in key:
        return context.get("evidence_map")
    if "compliance" in key or "validation" in key:
        return context.get("compliance")
    if "exception" in key or "error" in key:
        return context.get("exceptions")
    if key == "status":
        return context.get("status")
    if key == "sources":
        return context.get("sources")
    if "uncertaint" in key:
        return context.get("uncertainty")
    if "changelog" in key:
        return context.get("change_log")
    if key == "artifacts":
        return context.get("artifacts")
    return None


def make_result(case: Any, status: str, sources: Any, uncertainty: list[str],
                change_log: list[str], artifacts: list[str], work: Path, output: Path,
                exceptions: list[dict[str, Any]] | None = None,
                pptx: Path | None = None, pdf: Path | None = None) -> dict[str, Any]:
    evidence_map = output / "evidence_map.json"
    compliance = {
        "evidence_report": str(output / "evidence_report.json") if (output / "evidence_report.json").exists() else None,
        "render_report": str(output / "render_report.json") if (output / "render_report.json").exists() else None,
        "exceptions": exceptions or [],
    }
    context = {
        "status": status, "sources": sources, "uncertainty": uncertainty,
        "change_log": change_log, "artifacts": artifacts,
        "exceptions": exceptions or [],
        "pptx": str(pptx) if pptx and pptx.exists() else None,
        "pdf": str(pdf) if pdf and pdf.exists() else None,
        "evidence_map": str(evidence_map) if evidence_map.exists() else None,
        "compliance": compliance,
    }
    result: dict[str, Any] = {"case_id": case_identifier(case), "status": status}
    contract = case.get("output_contract", {}) if isinstance(case, dict) else {}
    for field in contract_fields(contract):
        result[field] = semantic_contract_value(field, context)
    for field in REQUIRED_RESULT_FIELDS:
        result[field] = context[field]
    return result


def discover_soffice() -> str | None:
    configured = os.environ.get("SOFFICE")
    candidates = [configured, shutil.which("soffice"), shutil.which("libreoffice"),
                  "/Applications/LibreOffice.app/Contents/MacOS/soffice",
                  "/usr/bin/soffice", "/usr/local/bin/soffice"]
    for candidate in candidates:
        if candidate and Path(candidate).is_file() and os.access(candidate, os.X_OK):
            return str(candidate)
    return None


def export_pdf(pptx: Path, output: Path, timeout: int = 180) -> tuple[Path | None, dict[str, Any]]:
    executable = discover_soffice()
    if not executable:
        return None, {"renderer": None, "status": "unavailable", "message": "LibreOffice/soffice not found; set SOFFICE."}
    export_dir = output / "export"
    export_dir.mkdir(parents=True, exist_ok=True)
    profile = export_dir / "lo-profile"
    profile.mkdir(parents=True, exist_ok=True)
    command = [executable, "--headless", f"-env:UserInstallation={profile.resolve().as_uri()}",
               "--convert-to", "pdf", "--outdir", str(export_dir), str(pptx)]
    try:
        completed = subprocess.run(command, capture_output=True, text=True, timeout=timeout, check=False)
    except (OSError, subprocess.TimeoutExpired) as exc:
        return None, {"renderer": executable, "status": "failed", "message": str(exc), "command": command}
    generated = export_dir / f"{pptx.stem}.pdf"
    destination = output / f"{pptx.stem}.pdf"
    if completed.returncode == 0 and generated.exists():
        shutil.copy2(generated, destination)
        return destination, {"renderer": executable, "status": "success", "command": command,
                             "returncode": completed.returncode, "stdout": completed.stdout,
                             "stderr": completed.stderr, "pdf": str(destination)}
    return None, {"renderer": executable, "status": "failed", "command": command,
                  "returncode": completed.returncode, "stdout": completed.stdout,
                  "stderr": completed.stderr}


def pdf_to_pngs(pdf: Path, output: Path) -> tuple[list[str], list[str]]:
    preview_dir = output / "previews"
    preview_dir.mkdir(parents=True, exist_ok=True)
    paths: list[str] = []
    errors: list[str] = []
    with fitz.open(pdf) as document:
        for index, page in enumerate(document):
            target = preview_dir / f"slide-{index + 1:02d}.png"
            try:
                page.get_pixmap(matrix=fitz.Matrix(1.5, 1.5), alpha=False).save(target)
                paths.append(str(target))
            except Exception as exc:  # renderer-specific errors belong in the report
                errors.append(f"Page {index + 1}: {exc}")
    return paths, errors


def flatten_strings(value: Any, prefix: str = "") -> Iterable[tuple[str, str]]:
    if isinstance(value, dict):
        for key, item in value.items():
            yield from flatten_strings(item, f"{prefix}.{key}" if prefix else str(key))
    elif isinstance(value, list):
        for index, item in enumerate(value):
            yield from flatten_strings(item, f"{prefix}[{index}]")
    elif isinstance(value, str):
        yield prefix, value
