#!/usr/bin/env python3
"""Deterministic, checkpointed case delivery with honest degradation.

Core Python standard library only. External programs are used only for optional
SVG -> PNG/PDF export; this program never installs software.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import importlib.util
import json
import math
import os
import re
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
from typing import Any
from xml.sax.saxutils import escape

RUNNER_VERSION = "resilient-case-delivery/1.1.0"
ERROR_KINDS = {"missing_material", "unreadable", "ambiguous", "tool_unavailable", "semantic_defect"}
STAGE_ORDER = ["intake", "validate", "render", "export", "report", "project_result"]
RESERVED_RESULT_KEYS = {
    "case_id", "status", "sources", "uncertainties", "change_records", "artifacts",
    "stages", "errors", "runner", "output_contract", "synthetic", "resume",
}


def issue(kind: str, message: str, path: str | None = None, hint: str | None = None) -> dict[str, Any]:
    if kind not in ERROR_KINDS:
        raise ValueError(f"unknown error kind: {kind}")
    item: dict[str, Any] = {"kind": kind, "message": message}
    if path is not None:
        item["path"] = str(path)
    if hint:
        item["hint"] = hint
    return item


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def atomic_write_bytes(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=str(path.parent))
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def atomic_write_json(path: Path, value: Any) -> None:
    payload = json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    atomic_write_bytes(path, payload.encode("utf-8"))


def read_json(path: Path) -> tuple[Any | None, bytes | None, dict[str, Any] | None]:
    try:
        raw = path.read_bytes()
    except FileNotFoundError:
        return None, None, issue("missing_material", "Required file does not exist.", str(path))
    except (PermissionError, OSError) as exc:
        return None, None, issue("unreadable", f"Cannot read file: {exc}", str(path))
    try:
        return json.loads(raw.decode("utf-8")), raw, None
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        return None, raw, issue("semantic_defect", f"Malformed UTF-8 JSON: {exc}", str(path))


def infer_kind(path: str) -> str:
    suffix = Path(path).suffix.lower()
    return {".svg": "svg", ".png": "png", ".pdf": "pdf", ".json": "json", ".md": "report"}.get(suffix, "file")


def validate_pdf_bytes(raw: bytes) -> tuple[bool, dict[str, Any]]:
    """Validate the physical PDF structure needed for a readable one-page preview.

    This is deliberately a structural check, not a claim about visual/scientific
    fidelity. It accepts classic xref tables and cross-reference stream objects.
    """
    details: dict[str, Any] = {"valid": False, "bytes": len(raw)}
    header = re.match(rb"%PDF-([0-9]+\.[0-9]+)", raw)
    if not header:
        details["reason"] = "missing PDF header at byte zero"
        return False, details
    details["version"] = header.group(1).decode("ascii")
    final = re.search(rb"startxref\s+([0-9]+)\s+%%EOF\s*$", raw)
    if not final:
        details["reason"] = "missing final startxref/%%EOF marker"
        return False, details
    startxref = int(final.group(1))
    details["startxref"] = startxref
    if startxref >= len(raw):
        details["reason"] = "startxref offset is outside the file"
        return False, details
    target = raw[startxref:startxref + 128]
    if not (re.match(rb"xref(?:\r|\n|\s)", target) or re.match(rb"[0-9]+\s+[0-9]+\s+obj\b", target)):
        details["reason"] = "startxref does not point to an xref table or stream object"
        return False, details
    if not re.search(rb"/Root\s+[0-9]+\s+[0-9]+\s+R\b", raw):
        details["reason"] = "document catalog Root reference is absent"
        return False, details
    if not re.search(rb"/Type\s*/Page\b", raw):
        details["reason"] = "no structural page object was found"
        return False, details
    details["valid"] = True
    details["page_object"] = True
    return True, details


def validate_png_bytes(raw: bytes) -> tuple[bool, dict[str, Any]]:
    """Check PNG signature, IHDR dimensions, and the final IEND chunk."""
    details: dict[str, Any] = {"valid": False, "bytes": len(raw)}
    if len(raw) < 45 or not raw.startswith(b"\x89PNG\r\n\x1a\n") or raw[12:16] != b"IHDR":
        details["reason"] = "missing PNG signature or initial IHDR"
        return False, details
    width = int.from_bytes(raw[16:20], "big")
    height = int.from_bytes(raw[20:24], "big")
    details.update({"width": width, "height": height})
    if width < 1 or height < 1:
        details["reason"] = "PNG dimensions are zero"
        return False, details
    if not raw.endswith(b"\x00\x00\x00\x00IEND\xaeB`\x82"):
        details["reason"] = "PNG final IEND chunk is absent"
        return False, details
    details["valid"] = True
    return True, details


def fmt(value: float) -> str:
    if abs(value) < 0.0000000005:
        value = 0.0
    return f"{value:.6f}".rstrip("0").rstrip(".")


class Runner:
    def __init__(self, args: argparse.Namespace) -> None:
        self.case_path = Path(args.case).expanduser().resolve()
        self.spec_path = Path(args.spec).expanduser().resolve()
        self.output_dir = Path(args.output_dir).expanduser().resolve()
        self.work_dir = Path(args.work_dir).expanduser().resolve()
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.work_dir.mkdir(parents=True, exist_ok=True)
        self.result_path = self.output_dir / "result.json"
        self.checkpoint_path = self.output_dir / "checkpoint.json"
        self.manifest_path = self.output_dir / "manifest.json"
        self.preview_requested_by_cli = bool(args.preview_png)
        self.preview_pdf_requested_by_cli = bool(getattr(args, "preview_pdf", False))
        self.resume_requested = bool(args.resume)
        self.task_path = self._task_path(args.task)

        self.case: dict[str, Any] = {}
        self.spec: dict[str, Any] = {}
        self.case_id: str | None = None
        self.synthetic = False
        self.contract: dict[str, dict[str, Any]] = {}
        self.artifact_defs: dict[str, dict[str, Any]] = {}
        self.bootstrap_errors: list[dict[str, Any]] = []
        self.fatal_bootstrap = False
        self.stage_records: dict[str, dict[str, Any]] = {}
        self.artifact_errors: dict[str, dict[str, Any]] = {}
        self.changes: list[dict[str, Any]] = []
        self.manifest: dict[str, Any] = {"schema_version": 1, "inputs": []}
        self.fingerprint = ""
        self.previous: dict[str, Any] = {}
        self.same_inputs = False
        self.data_mapping: dict[str, Any] | None = None
        self.export_details: dict[str, Any] = {"requested": False, "exporter": None, "available": False}
        self.svg_key: str | None = None
        self.data_key: str | None = None
        self.report_key: str | None = None
        self.preview_key: str | None = None
        self.pdf_key: str | None = None
        self._aux_counter = 0

    def _task_path(self, explicit: str | None) -> Path | None:
        if explicit:
            return Path(explicit).expanduser().resolve()
        candidates = [self.case_path.parent / "task.md", Path("/input/task.md"), Path("/task.md")]
        for candidate in candidates:
            if candidate.is_file():
                return candidate.resolve()
        return candidates[0].resolve()

    def _load_previous(self) -> None:
        if not self.resume_requested or not self.checkpoint_path.is_file():
            return
        value, _, error = read_json(self.checkpoint_path)
        if error or not isinstance(value, dict):
            self.previous = {}
            return
        self.previous = value

    def _bootstrap_case(self) -> None:
        value, raw, error = read_json(self.case_path)
        if error:
            self.bootstrap_errors.append(error)
            self.fatal_bootstrap = True
            return
        if not isinstance(value, dict):
            self.bootstrap_errors.append(issue("semantic_defect", "case.json must be a JSON object.", str(self.case_path)))
            self.fatal_bootstrap = True
            return
        self.case = value
        case_id = value.get("case_id")
        if not isinstance(case_id, str) or not case_id.strip():
            self.bootstrap_errors.append(issue("semantic_defect", "case_id must be a non-empty string.", str(self.case_path)))
            self.fatal_bootstrap = True
        else:
            self.case_id = case_id
        self.synthetic = value.get("synthetic") is True or value.get("label") == "SYNTHETIC"
        raw_contract = value.get("output_contract")
        if not isinstance(raw_contract, dict) or not raw_contract:
            self.bootstrap_errors.append(issue("semantic_defect", "output_contract must be a non-empty object.", str(self.case_path)))
            self.fatal_bootstrap = True
            return
        seen_paths: dict[str, str] = {}
        for key, descriptor in raw_contract.items():
            if not isinstance(key, str) or not key or key in RESERVED_RESULT_KEYS:
                self.bootstrap_errors.append(issue("semantic_defect", f"Contract key is empty or reserved: {key!r}", str(self.case_path)))
                self.fatal_bootstrap = True
                continue
            if isinstance(descriptor, str):
                descriptor = {"path": descriptor}
            if not isinstance(descriptor, dict) or not isinstance(descriptor.get("path"), str):
                self.bootstrap_errors.append(issue("semantic_defect", f"Contract entry {key!r} must be a path or an object with path.", str(self.case_path)))
                self.fatal_bootstrap = True
                continue
            rel = descriptor["path"]
            candidate = Path(rel)
            if candidate.is_absolute() or not rel or ".." in candidate.parts or rel == "result.json":
                self.bootstrap_errors.append(issue("semantic_defect", f"Unsafe or reserved output path for {key!r}: {rel!r}", str(self.case_path)))
                self.fatal_bootstrap = True
                continue
            kind = descriptor.get("kind", infer_kind(rel))
            if kind not in {"svg", "png", "pdf", "json", "report", "file"}:
                self.bootstrap_errors.append(issue("semantic_defect", f"Unsupported artifact kind for {key!r}: {kind!r}"))
                self.fatal_bootstrap = True
                continue
            normalized = str(candidate)
            if normalized in seen_paths:
                self.bootstrap_errors.append(issue("ambiguous", f"Contract keys {seen_paths[normalized]!r} and {key!r} share one output path.", normalized))
                self.fatal_bootstrap = True
                continue
            seen_paths[normalized] = key
            self.contract[key] = {
                "path": normalized,
                "kind": kind,
                "required": bool(descriptor.get("required", kind not in {"png", "pdf"})),
            }
        self.artifact_defs = {key: dict(value) for key, value in self.contract.items()}
        self._discover_roles()
        self._ensure_aux_artifacts()

    def _discover_roles(self) -> None:
        def first(kind: str) -> str | None:
            return next((key for key, value in self.contract.items() if value["kind"] == kind), None)

        self.svg_key = first("svg")
        self.data_key = first("json")
        self.report_key = first("report")
        self.preview_key = first("png")
        self.pdf_key = first("pdf")

    def _aux_key(self, stem: str) -> str:
        while True:
            self._aux_counter += 1
            key = f"__{stem}_{self._aux_counter}"
            if key not in self.artifact_defs:
                return key

    def _ensure_aux_artifacts(self) -> None:
        if self.report_key is None:
            self.report_key = self._aux_key("report")
            self.artifact_defs[self.report_key] = {"path": "report.md", "kind": "report", "required": True, "auxiliary": True}
        if self.preview_key is None:
            self.preview_key = self._aux_key("preview")
            self.artifact_defs[self.preview_key] = {"path": "preview.png", "kind": "png", "required": False, "auxiliary": True}
        if self.pdf_key is None and self.preview_pdf_requested_by_cli:
            self.pdf_key = self._aux_key("preview_pdf")
            self.artifact_defs[self.pdf_key] = {"path": "preview.pdf", "kind": "pdf", "required": False, "auxiliary": True}
        if self.data_key is None:
            self.data_key = self._aux_key("data")
            self.artifact_defs[self.data_key] = {"path": "data_mapping.json", "kind": "json", "required": False, "auxiliary": True}

    def _configure_roles_from_spec(self) -> None:
        if not self.spec:
            return
        for field, kind, current in (
            ("artifact_key", "svg", self.svg_key),
            ("data_artifact_key", "json", self.data_key),
            ("report_artifact_key", "report", self.report_key),
            ("preview_artifact_key", "png", self.preview_key),
            ("pdf_artifact_key", "pdf", self.pdf_key),
        ):
            key = self.spec.get(field)
            if isinstance(key, str) and key in self.contract and self.contract[key]["kind"] == kind:
                if field == "artifact_key":
                    self.svg_key = key
                elif field == "data_artifact_key":
                    self.data_key = key
                elif field == "report_artifact_key":
                    self.report_key = key
                elif field == "preview_artifact_key":
                    self.preview_key = key
                else:
                    self.pdf_key = key

    @property
    def preview_requested(self) -> bool:
        return self.preview_requested_by_cli or any(
            item["kind"] == "png" and item["required"] for item in self.contract.values()
        )

    @property
    def preview_pdf_requested(self) -> bool:
        return self.preview_pdf_requested_by_cli or any(
            item["kind"] == "pdf" and item["required"] for item in self.contract.values()
        )

    @property
    def exports_requested(self) -> bool:
        return self.preview_requested or self.preview_pdf_requested

    def _export_targets(self) -> list[tuple[str, str]]:
        targets = []
        if self.preview_requested and self.preview_key:
            targets.append(("png", self.preview_key))
        if self.preview_pdf_requested and self.pdf_key:
            targets.append(("pdf", self.pdf_key))
        return targets

    def _artifact_path(self, key: str) -> Path:
        return self.output_dir / self.artifact_defs[key]["path"]

    def _invalidate_outputs(self, keys: list[str] | None = None) -> None:
        for key in list(keys if keys is not None else self.artifact_defs.keys()):
            if key not in self.artifact_defs:
                continue
            path = self._artifact_path(key).resolve()
            try:
                path.relative_to(self.output_dir)
            except ValueError:
                continue
            if path in {self.result_path.resolve(), self.checkpoint_path.resolve(), self.manifest_path.resolve()}:
                continue
            if path.is_file() or path.is_symlink():
                path.unlink()
        self.changes.append({"action": "invalidated_stale_outputs", "keys": list(keys) if keys is not None else list(self.artifact_defs)})

    def _scan_input(self, identifier: str, path: Path, kind: str, role: str, version: Any = None, locator: Any = None) -> dict[str, Any]:
        item: dict[str, Any] = {
            "id": identifier, "path": str(path), "kind": kind, "role": role,
            "version": version if version is not None else "unversioned",
            "available": False, "bytes": None, "sha256": None,
        }
        if locator is not None:
            item["locator"] = locator
        try:
            raw = path.read_bytes()
        except FileNotFoundError:
            item["error"] = issue("missing_material", "Input material does not exist.", str(path))
            return item
        except (PermissionError, OSError) as exc:
            item["error"] = issue("unreadable", f"Cannot read input material: {exc}", str(path))
            return item
        item.update({"available": True, "bytes": len(raw), "sha256": sha256_bytes(raw)})
        return item

    def _intake(self) -> list[dict[str, Any]]:
        errors: list[dict[str, Any]] = list(self.bootstrap_errors)
        inputs: list[dict[str, Any]] = []
        case_scan = self._scan_input("case", self.case_path, "json", "case_contract")
        inputs.append(case_scan)
        if self.task_path is not None:
            task_scan = self._scan_input("task", self.task_path, "text", "task_instruction")
            inputs.append(task_scan)
            if not task_scan["available"]:
                errors.append(task_scan["error"])
        spec_value, spec_raw, spec_error = read_json(self.spec_path)
        spec_scan = self._scan_input("case_spec", self.spec_path, "json", "agent_created_specification")
        inputs.append(spec_scan)
        if spec_error:
            errors.append(spec_error)
        elif not isinstance(spec_value, dict):
            errors.append(issue("semantic_defect", "Case specification must be a JSON object.", str(self.spec_path)))
        else:
            self.spec = spec_value
            self.synthetic = self.synthetic or self.spec.get("synthetic") is True
        self._configure_roles_from_spec()
        materials = self.spec.get("materials", []) if self.spec else []
        if isinstance(materials, list):
            for index, material in enumerate(materials):
                if not isinstance(material, dict) or not isinstance(material.get("path"), str):
                    continue
                raw_path = Path(material["path"]).expanduser()
                path = raw_path.resolve() if raw_path.is_absolute() else (self.spec_path.parent / raw_path).resolve()
                identifier = material.get("id", f"material_{index + 1}")
                inputs.append(self._scan_input(
                    str(identifier), path, str(material.get("kind", "file")),
                    str(material.get("role", "source")), material.get("version"), material.get("locator"),
                ))
        self.manifest = {
            "schema_version": 1,
            "case_id": self.case_id,
            "synthetic": self.synthetic,
            "runner": RUNNER_VERSION,
            "inputs": inputs,
            "note": "Hashes and sizes are read from actual files; missing inputs have no fabricated hash.",
        }
        atomic_write_json(self.manifest_path, self.manifest)
        fingerprint_payload = {
            "runner": RUNNER_VERSION,
            "inputs": [{key: item.get(key) for key in ("id", "path", "sha256", "available", "error")} for item in inputs],
            "preview_requested": self.preview_requested,
            "png_preview_requested": self.preview_requested,
            "pdf_preview_requested": self.preview_pdf_requested,
            "exporter_override": os.environ.get("RESILIENT_CASE_PREVIEW_EXPORTER"),
        }
        self.fingerprint = sha256_bytes(json.dumps(fingerprint_payload, ensure_ascii=False, sort_keys=True).encode("utf-8"))
        return errors

    def _materials(self) -> list[dict[str, Any]]:
        materials = self.spec.get("materials", [])
        return materials if isinstance(materials, list) else []

    def _material(self, identifier: Any) -> tuple[dict[str, Any] | None, dict[str, Any] | None, Path | None]:
        for item in self._materials():
            if isinstance(item, dict) and item.get("id") == identifier:
                raw = item.get("path")
                if not isinstance(raw, str):
                    return item, issue("semantic_defect", f"Material {identifier!r} has no valid path."), None
                candidate = Path(raw).expanduser()
                path = candidate.resolve() if candidate.is_absolute() else (self.spec_path.parent / candidate).resolve()
                return item, None, path
        return None, issue("missing_material", f"Referenced material {identifier!r} is not declared."), None

    def _read_text(self, path: Path) -> tuple[str | None, dict[str, Any] | None]:
        try:
            return path.read_text(encoding="utf-8"), None
        except FileNotFoundError:
            return None, issue("missing_material", "Required source text is missing.", str(path))
        except (PermissionError, OSError, UnicodeDecodeError) as exc:
            return None, issue("unreadable", f"Cannot decode/read UTF-8 source: {exc}", str(path))

    def _validate_chart(self, errors: list[dict[str, Any]]) -> None:
        chart = self.spec.get("chart")
        if not isinstance(chart, dict):
            errors.append(issue("semantic_defect", "Chart mode requires a chart object.", str(self.spec_path)))
            return
        material, material_error, path = self._material(chart.get("source_id"))
        if material_error:
            errors.append(material_error)
            return
        assert material is not None and path is not None
        if material.get("kind") != "csv":
            errors.append(issue("semantic_defect", "Chart source_id must reference a CSV material.", str(path)))
            return
        try:
            handle = path.open("r", encoding="utf-8-sig", newline="")
        except FileNotFoundError:
            errors.append(issue("missing_material", "Chart source CSV is missing; no values were invented.", str(path)))
            return
        except (PermissionError, OSError) as exc:
            errors.append(issue("unreadable", f"Cannot open chart CSV: {exc}", str(path)))
            return
        rows: list[dict[str, Any]] = []
        try:
            with handle:
                reader = csv.DictReader(handle)
                headers = reader.fieldnames
                if not headers:
                    errors.append(issue("semantic_defect", "CSV has no header row.", str(path)))
                    return
                duplicates = sorted({name for name in headers if headers.count(name) > 1})
                if duplicates:
                    errors.append(issue("ambiguous", f"Duplicate CSV column names: {duplicates}", str(path)))
                    return
                x_column, y_column = chart.get("x_column"), chart.get("y_column")
                series_column = chart.get("series_column")
                required = [x_column, y_column] + ([series_column] if series_column else [])
                missing = [column for column in required if not isinstance(column, str) or column not in headers]
                if missing:
                    errors.append(issue("semantic_defect", f"Specified CSV columns are absent: {missing}", str(path), "Use exact header names; do not rename data silently."))
                    return
                for row_number, row in enumerate(reader, start=2):
                    if None in row:
                        errors.append(issue("ambiguous", f"CSV row {row_number} has more fields than the header.", str(path)))
                        continue
                    try:
                        x = float(row[x_column])
                        y = float(row[y_column])
                        if not math.isfinite(x) or not math.isfinite(y):
                            raise ValueError("non-finite number")
                    except (TypeError, ValueError) as exc:
                        errors.append(issue("semantic_defect", f"CSV row {row_number} has invalid numeric data: {exc}", str(path)))
                        continue
                    rows.append({
                        "csv_row": row_number,
                        "series": str(row[series_column]) if series_column else "series",
                        "raw_x": row[x_column], "raw_y": row[y_column],
                        "x": x, "y": y,
                    })
        except (UnicodeDecodeError, csv.Error, OSError) as exc:
            errors.append(issue("unreadable", f"Cannot parse chart CSV: {exc}", str(path)))
            return
        if not rows:
            errors.append(issue("missing_material", "No usable CSV rows remain; chart was not fabricated.", str(path)))
            return
        comparison_rows = [{
            "csv_row": row["csv_row"], "series": row["series"], "raw_x": row["raw_x"], "raw_y": row["raw_y"],
            "plotted_x": row["x"], "plotted_y": row["y"],
            "matches": float(row["raw_x"]) == row["x"] and float(row["raw_y"]) == row["y"],
        } for row in rows]
        self.data_mapping = {
            "case_id": self.case_id,
            "synthetic": self.synthetic,
            "source": {"id": material.get("id"), "path": str(path), "version": material.get("version", "unversioned")},
            "columns": list(headers),
            "mapping": {"x": x_column, "y": y_column, "series": series_column, "row_order": "source CSV order"},
            "rows": rows,
            "primary_source_comparison": {
                "method": "Each plotted numeric value is compared directly with the same parsed CSV cell; CSV row numbers include the header.",
                "all_match": all(item["matches"] for item in comparison_rows),
                "rows": comparison_rows,
            },
        }

    def _validate_diagram(self, errors: list[dict[str, Any]]) -> None:
        diagram = self.spec.get("diagram")
        if not isinstance(diagram, dict) or not isinstance(diagram.get("entities"), list) or not diagram["entities"]:
            errors.append(issue("semantic_defect", "Diagram mode requires a non-empty diagram.entities list.", str(self.spec_path)))
            return
        identifiers: set[str] = set()
        for entity in diagram["entities"]:
            identifier = entity.get("id") if isinstance(entity, dict) else None
            if not isinstance(identifier, str) or not identifier:
                errors.append(issue("semantic_defect", "Every diagram entity needs a non-empty id.", str(self.spec_path)))
            elif identifier in identifiers:
                errors.append(issue("ambiguous", f"Duplicate diagram entity id: {identifier}", str(self.spec_path)))
            else:
                identifiers.add(identifier)
        edges = diagram.get("edges", [])
        if not isinstance(edges, list):
            errors.append(issue("semantic_defect", "diagram.edges must be a list.", str(self.spec_path)))
            edges = []
        for edge in edges:
            if not isinstance(edge, dict) or edge.get("from") not in identifiers or edge.get("to") not in identifiers:
                errors.append(issue("semantic_defect", f"Edge has missing or unknown endpoints: {edge}", str(self.spec_path)))
        inspection = self.spec.get("figure_inspection")
        if inspection is not None:
            if not isinstance(inspection, dict) or not inspection.get("figure_id") or not inspection.get("source_id"):
                errors.append(issue("semantic_defect", "figure_inspection needs figure_id and source_id.", str(self.spec_path)))
            else:
                _, source_error, _ = self._material(inspection.get("source_id"))
                if source_error:
                    errors.append(source_error)
                observations = inspection.get("observations")
                if not isinstance(observations, list) or not observations:
                    kind = "missing_material" if str(inspection.get("figure_id")).lower() == "figure03" else "ambiguous"
                    errors.append(issue(kind, "Figure inspection has no recorded observations; the agent must inspect the actual figure.", str(self.spec_path)))

    def _validate_edit(self, errors: list[dict[str, Any]]) -> None:
        edit = self.spec.get("svg_edit")
        if not isinstance(edit, dict):
            errors.append(issue("semantic_defect", "svg_edit mode requires an svg_edit object.", str(self.spec_path)))
            return
        material, material_error, path = self._material(edit.get("source_id"))
        if material_error:
            errors.append(material_error)
            return
        assert material is not None and path is not None
        text, read_error = self._read_text(path)
        if read_error:
            errors.append(read_error)
            return
        assert text is not None
        replacements = edit.get("replacements")
        if not isinstance(replacements, list) or not replacements:
            errors.append(issue("missing_material", "No targeted SVG replacements were specified; source was not rebuilt.", str(path)))
            return
        for index, replacement in enumerate(replacements):
            if not isinstance(replacement, dict) or not isinstance(replacement.get("old"), str) or not isinstance(replacement.get("new"), str):
                errors.append(issue("semantic_defect", f"Replacement {index} needs literal old and new strings.", str(self.spec_path)))
                continue
            if replacement["old"] == "":
                errors.append(issue("ambiguous", f"Replacement {index} has an empty target.", str(self.spec_path)))
                continue
            expected = replacement.get("expected_count", 1)
            count = text.count(replacement["old"])
            if not isinstance(expected, int) or expected < 1:
                errors.append(issue("semantic_defect", f"Replacement {index} expected_count must be a positive integer."))
            elif count == 0:
                errors.append(issue("semantic_defect", f"Replacement {index} target is absent; no broad SVG rebuild was attempted.", str(path)))
            elif count != expected:
                errors.append(issue("ambiguous", f"Replacement {index} matched {count} times, expected {expected}.", str(path)))

    def _validate(self, intake_errors: list[dict[str, Any]]) -> list[dict[str, Any]]:
        errors: list[dict[str, Any]] = []
        if intake_errors or not self.spec:
            return errors
        if self.spec.get("schema_version") != 1:
            errors.append(issue("semantic_defect", "Case specification schema_version must be 1.", str(self.spec_path)))
        if self.spec.get("case_id") != self.case_id:
            errors.append(issue("semantic_defect", "Specification case_id does not match case.json.", str(self.spec_path)))
        identifiers: set[str] = set()
        for index, material in enumerate(self._materials()):
            if not isinstance(material, dict) or not isinstance(material.get("id"), str) or not isinstance(material.get("path"), str):
                errors.append(issue("semantic_defect", f"Material {index} needs id and path.", str(self.spec_path)))
                continue
            if material["id"] in identifiers:
                errors.append(issue("ambiguous", f"Duplicate material id: {material['id']}", str(self.spec_path)))
            identifiers.add(material["id"])
            scan = next((item for item in self.manifest["inputs"] if item.get("id") == material["id"]), None)
            if scan and not scan["available"]:
                errors.append(scan["error"])
        for field, key, kind in (
            ("artifact_key", self.svg_key, "svg"),
            ("data_artifact_key", self.data_key, "json"),
            ("report_artifact_key", self.report_key, "report"),
            ("preview_artifact_key", self.preview_key, "png"),
            ("pdf_artifact_key", self.pdf_key, "pdf"),
        ):
            requested = self.spec.get(field)
            if requested is not None and (not isinstance(requested, str) or requested not in self.contract):
                errors.append(issue("semantic_defect", f"{field} must name an output_contract key.", str(self.spec_path)))
            if key is not None and key in self.artifact_defs and self.artifact_defs[key]["kind"] != kind:
                errors.append(issue("semantic_defect", f"Artifact role {field} does not have kind {kind}."))
        if self.svg_key is None or self.svg_key not in self.contract:
            errors.append(issue("semantic_defect", "An SVG output_contract artifact is required.", str(self.case_path)))
        mode = self.spec.get("mode")
        if mode == "chart":
            self._validate_chart(errors)
            if self.data_key is None:
                errors.append(issue("semantic_defect", "Chart mode needs a data mapping artifact."))
        elif mode == "diagram":
            self._validate_diagram(errors)
        elif mode == "svg_edit":
            self._validate_edit(errors)
        else:
            errors.append(issue("semantic_defect", f"Unsupported specification mode: {mode!r}", str(self.spec_path)))
        return errors

    def _chart_svg(self) -> str:
        assert self.data_mapping is not None
        chart = self.spec["chart"]
        rows = self.data_mapping["rows"]
        width, height = 1200, 760
        left, right, top, bottom = 120, 70, 120, 125
        plot_w, plot_h = width - left - right, height - top - bottom
        xs = [float(row["x"]) for row in rows]
        ys = [float(row["y"]) for row in rows]
        x_min, x_max = min(xs), max(xs)
        y_min, y_max = min(0.0, min(ys)), max(ys)
        if x_min == x_max:
            x_min, x_max = x_min - 0.5, x_max + 0.5
        if y_min == y_max:
            y_min, y_max = y_min - 0.5, y_max + 0.5
        y_pad = (y_max - y_min) * 0.08
        y_max += y_pad

        def px(value: float) -> float:
            return left + (value - x_min) / (x_max - x_min) * plot_w

        def py(value: float) -> float:
            return top + plot_h - (value - y_min) / (y_max - y_min) * plot_h

        series: list[str] = []
        for row in rows:
            if row["series"] not in series:
                series.append(row["series"])
        colors = ["#1768aa", "#c65b21", "#26856b", "#8256a3", "#8a6d1f", "#a23b5d"]
        parts = [
            '<svg xmlns="http://www.w3.org/2000/svg" width="1200" height="760" viewBox="0 0 1200 760" role="img">',
            f"<title>{escape(str(chart.get('title', self.spec.get('title', 'Source-bound chart'))))}</title>",
            "<desc>Editable chart generated from the declared CSV rows. No values are inferred beyond numeric parsing.</desc>",
            "<metadata>" + escape(json.dumps({"runner": RUNNER_VERSION, "case_id": self.case_id, "synthetic": self.synthetic, "source": self.data_mapping["source"]}, ensure_ascii=False)) + "</metadata>",
            '<rect width="1200" height="760" fill="#ffffff"/>',
            '<g id="layer-title" font-family="Arial, Helvetica, sans-serif" fill="#17232d">',
            f'<text x="600" y="46" text-anchor="middle" font-size="26" font-weight="700">{escape(str(chart.get("title", self.spec.get("title", "Source-bound chart"))))}</text>',
        ]
        if self.synthetic:
            parts.append('<text x="600" y="79" text-anchor="middle" font-size="17" fill="#9b2c2c">SYNTHETIC EXAMPLE — NOT SCIENTIFIC EVIDENCE</text>')
        parts.append("</g>")
        parts.append('<g id="layer-axes" stroke="#344550" stroke-width="1.2" fill="none">')
        parts.append(f'<path d="M {left} {top} V {top + plot_h} H {left + plot_w}"/>')
        parts.append("</g>")
        parts.append('<g id="layer-grid" stroke="#dbe3e8" stroke-width="1">')
        for index in range(6):
            y_value = y_min + (y_max - y_min) * index / 5
            y_coord = py(y_value)
            parts.append(f'<line x1="{left}" y1="{fmt(y_coord)}" x2="{left + plot_w}" y2="{fmt(y_coord)}"/>')
        parts.append("</g>")
        parts.append('<g id="layer-tick-labels" font-family="Arial, Helvetica, sans-serif" font-size="14" fill="#344550">')
        for index in range(6):
            y_value = y_min + (y_max - y_min) * index / 5
            y_coord = py(y_value)
            parts.append(f'<text x="{left - 12}" y="{fmt(y_coord + 5)}" text-anchor="end">{fmt(y_value)}</text>')
        for index in range(6):
            x_value = x_min + (x_max - x_min) * index / 5
            x_coord = px(x_value)
            parts.append(f'<text x="{fmt(x_coord)}" y="{top + plot_h + 28}" text-anchor="middle">{fmt(x_value)}</text>')
        parts.append(f'<text x="{left + plot_w / 2}" y="{height - 35}" text-anchor="middle" font-size="17">{escape(str(chart.get("x_label", chart["x_column"])))}</text>')
        parts.append(f'<text x="28" y="{top + plot_h / 2}" text-anchor="middle" font-size="17" transform="rotate(-90 28 {top + plot_h / 2})">{escape(str(chart.get("y_label", chart["y_column"])))}</text>')
        parts.append("</g>")
        parts.append('<g id="layer-data" fill="none" stroke-width="3">')
        for series_index, name in enumerate(series):
            color = colors[series_index % len(colors)]
            points = [row for row in rows if row["series"] == name]
            coordinates = " ".join(f"{fmt(px(row['x']))},{fmt(py(row['y']))}" for row in points)
            parts.append(f'<polyline id="series-{series_index}" stroke="{color}" points="{coordinates}"/>')
            for row in points:
                parts.append(f'<circle cx="{fmt(px(row["x"]))}" cy="{fmt(py(row["y"]))}" r="5" fill="{color}" stroke="#ffffff" stroke-width="1.5"><title>{escape(str(name))}; CSV row {row["csv_row"]}; x={escape(str(row["raw_x"]))}; y={escape(str(row["raw_y"]))}</title></circle>')
        parts.append("</g>")
        parts.append('<g id="layer-legend" font-family="Arial, Helvetica, sans-serif" font-size="15" fill="#17232d">')
        for series_index, name in enumerate(series):
            color = colors[series_index % len(colors)]
            x = left + series_index * 250
            parts.append(f'<line x1="{x}" y1="{top - 25}" x2="{x + 30}" y2="{top - 25}" stroke="{color}" stroke-width="3"/>')
            parts.append(f'<text x="{x + 40}" y="{top - 20}">{escape(str(name))}</text>')
        parts.append("</g>")
        source = self.data_mapping["source"]
        parts.append(f'<g id="layer-source" font-family="Arial, Helvetica, sans-serif" font-size="12" fill="#53636e"><text x="{left}" y="{height - 12}">Source: {escape(str(source["id"]))}; {len(rows)} actual CSV rows; row locators in data_mapping.json.</text></g>')
        parts.append("</svg>")
        return "\n".join(parts) + "\n"

    def _diagram_svg(self) -> str:
        diagram = self.spec["diagram"]
        entities = diagram["entities"]
        columns = min(3, max(1, len(entities)))
        rows_count = math.ceil(len(entities) / columns)
        width, height = 1200, max(620, 210 + rows_count * 190)
        positions: dict[str, tuple[float, float]] = {}
        for index, entity in enumerate(entities):
            row, column = divmod(index, columns)
            positions[entity["id"]] = (180 + column * (840 / max(1, columns - 1)) if columns > 1 else 600, 180 + row * 190)
        parts = [
            f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">',
            '<defs><marker id="arrow" markerWidth="10" markerHeight="10" refX="8" refY="3" orient="auto"><path d="M0,0 L0,6 L9,3 z" fill="#385666"/></marker></defs>',
            '<rect width="100%" height="100%" fill="#ffffff"/>',
            f'<g id="layer-title" font-family="Arial, Helvetica, sans-serif"><text x="600" y="48" text-anchor="middle" font-size="27" font-weight="700">{escape(str(self.spec.get("title", "Source-bound diagram")))}</text>',
        ]
        if self.synthetic:
            parts.append('<text x="600" y="78" text-anchor="middle" font-size="17" fill="#9b2c2c">SYNTHETIC EXAMPLE — NOT SCIENTIFIC EVIDENCE</text>')
        parts.append("</g>")
        parts.append('<g id="layer-relationships" stroke="#385666" stroke-width="2.2" fill="none" marker-end="url(#arrow)">')
        for edge in diagram.get("edges", []):
            x1, y1 = positions[edge["from"]]
            x2, y2 = positions[edge["to"]]
            parts.append(f'<line x1="{fmt(x1)}" y1="{fmt(y1 + 42)}" x2="{fmt(x2)}" y2="{fmt(y2 - 48)}"><title>{escape(str(edge.get("label", "")))}</title></line>')
        parts.append("</g>")
        parts.append('<g id="layer-entities" font-family="Arial, Helvetica, sans-serif">')
        for index, entity in enumerate(entities):
            x, y = positions[entity["id"]]
            label = str(entity.get("label", entity["id"]))
            parts.append(f'<g id="entity-{escape(str(entity["id"]))}"><rect x="{fmt(x - 120)}" y="{fmt(y - 42)}" width="240" height="84" rx="10" fill="#edf5f8" stroke="#28728a" stroke-width="2"/><text x="{fmt(x)}" y="{fmt(y + 6)}" text-anchor="middle" font-size="17" fill="#173b47">{escape(label)}</text></g>')
        parts.append("</g>")
        inspection = self.spec.get("figure_inspection")
        if inspection:
            note = f"Inspected {inspection.get('figure_id')}; source {inspection.get('source_id')}; agent observations retained in result sources/report."
            parts.append(f'<g id="layer-provenance" font-family="Arial, Helvetica, sans-serif" font-size="13" fill="#53636e"><text x="40" y="{height - 28}">{escape(note)}</text></g>')
        parts.append("</svg>")
        return "\n".join(parts) + "\n"

    def _edit_svg(self) -> tuple[str, list[dict[str, Any]]]:
        edit = self.spec["svg_edit"]
        _, _, path = self._material(edit["source_id"])
        assert path is not None
        text = path.read_text(encoding="utf-8")
        records: list[dict[str, Any]] = []
        for index, replacement in enumerate(edit["replacements"]):
            old, new = replacement["old"], replacement["new"]
            expected = replacement.get("expected_count", 1)
            text = text.replace(old, new, expected)
            records.append({"index": index, "old": old, "new": new, "expected_count": expected, "target_id": replacement.get("target_id")})
        return text, records

    def _render(self) -> list[dict[str, Any]]:
        assert self.svg_key is not None
        svg_path = self._artifact_path(self.svg_key)
        source_hashes = {item["id"]: item.get("sha256") for item in self.manifest["inputs"] if item.get("available")}
        if self.spec["mode"] == "chart":
            svg = self._chart_svg()
            atomic_write_json(self._artifact_path(self.data_key), self.data_mapping)
            self.changes.append({
                "action": "created_chart_from_actual_csv", "artifact": self.artifact_defs[self.svg_key]["path"],
                "source_id": self.data_mapping["source"]["id"], "source_sha256": source_hashes.get(self.data_mapping["source"]["id"]),
                "rows_used": [row["csv_row"] for row in self.data_mapping["rows"]],
                "primary_source_all_match": self.data_mapping["primary_source_comparison"]["all_match"],
            })
        elif self.spec["mode"] == "diagram":
            svg = self._diagram_svg()
            self.changes.append({
                "action": "created_diagram_from_agent_inspection", "artifact": self.artifact_defs[self.svg_key]["path"],
                "source_ids": [item.get("id") for item in self._materials()],
                "source_hashes": source_hashes,
                "note": "Scientific observations are agent-recorded from actual inputs; renderer does not invent missing entities.",
            })
        else:
            svg, replacements = self._edit_svg()
            edit = self.spec["svg_edit"]
            source_path = self._material(edit["source_id"])[2]
            assert source_path is not None
            self.changes.append({
                "action": "targeted_source_preserving_svg_edit", "artifact": self.artifact_defs[self.svg_key]["path"],
                "source_path": str(source_path), "source_sha256": sha256_bytes(source_path.read_bytes()),
                "output_sha256": sha256_bytes(svg.encode("utf-8")), "replacements": replacements,
                "preservation": "Literal counted substring patches only; no XML serialization, restyling, or whole-document rebuild.",
            })
        atomic_write_bytes(svg_path, svg.encode("utf-8"))
        return []

    @staticmethod
    def _exporter_kind(name: str) -> str:
        tool = Path(name).name.lower()
        if tool in {"google chrome", "google-chrome", "google-chrome-stable", "chrome"}:
            return "chrome"
        if tool in {"chromium", "chromium-browser"}:
            return "chromium"
        return tool

    def _resolve_exporter(self, name: str) -> tuple[str, str] | None:
        kind = self._exporter_kind(name)
        if kind == "cairosvg":
            executable = shutil.which(name)
            if executable:
                return name, executable
            if importlib.util.find_spec("cairosvg") is not None:
                return "cairosvg", sys.executable
            return None
        executable = shutil.which(name)
        if executable:
            return name, executable
        if kind in {"chrome", "chromium"} and sys.platform == "darwin":
            mac_path = {
                "chrome": "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
                "chromium": "/Applications/Chromium.app/Contents/MacOS/Chromium",
            }[kind]
            if os.path.isfile(mac_path) and os.access(mac_path, os.X_OK):
                return kind, mac_path
        return None

    def _candidate_exporters(self, output_format: str) -> list[tuple[str, str]]:
        override = os.environ.get("RESILIENT_CASE_PREVIEW_EXPORTER")
        if override is not None:
            if override.strip().lower() in {"", "none", "disabled"}:
                return []
            resolved = self._resolve_exporter(override.strip())
            return [resolved] if resolved else []
        names = {
            "png": ("rsvg-convert", "inkscape", "magick", "sips", "cairosvg"),
            "pdf": ("rsvg-convert", "inkscape", "google-chrome", "chrome", "chromium", "chromium-browser", "cairosvg"),
        }[output_format]
        candidates: list[tuple[str, str]] = []
        seen: set[tuple[str, str]] = set()
        for name in names:
            resolved = self._resolve_exporter(name)
            if resolved:
                identity = (self._exporter_kind(resolved[0]), resolved[1])
                if identity not in seen:
                    candidates.append(resolved)
                    seen.add(identity)
        return candidates

    @staticmethod
    def _validate_export(path: Path, output_format: str) -> tuple[bool, dict[str, Any]]:
        try:
            raw = path.read_bytes()
        except OSError as exc:
            return False, {"valid": False, "reason": f"cannot read exported file: {exc}"}
        return validate_pdf_bytes(raw) if output_format == "pdf" else validate_png_bytes(raw)

    def _export_command(self, name: str, executable: str, output_format: str, svg_path: Path, target: Path) -> list[str] | None:
        tool = self._exporter_kind(name)
        if tool == "rsvg-convert":
            return [executable, "--format", output_format, "--output", str(target), str(svg_path)]
        if tool == "inkscape":
            return [executable, str(svg_path), f"--export-type={output_format}", f"--export-filename={target}"]
        if tool == "cairosvg" and output_format in {"png", "pdf"}:
            command = [executable]
            if Path(executable).resolve() == Path(sys.executable).resolve():
                command += ["-m", "cairosvg"]
            return command + [str(svg_path), "--format", output_format, "--output", str(target)]
        if output_format == "png" and tool == "magick":
            return [executable, str(svg_path), str(target)]
        if output_format == "png" and tool == "sips":
            return [executable, "-s", "format", "png", str(svg_path), "--out", str(target)]
        if output_format == "pdf" and tool in {"chrome", "chromium"}:
            return [
                executable, "--headless=new", "--disable-gpu", "--no-sandbox", "--no-first-run",
                "--no-default-browser-check", "--disable-background-networking", "--no-pdf-header-footer",
                "--print-to-pdf-no-header", f"--print-to-pdf={target}", svg_path.resolve().as_uri(),
            ]
        return None

    def _export_one(self, name: str, executable: str, output_format: str, svg_path: Path, destination: Path) -> tuple[bool, str, dict[str, Any]]:
        tool = self._exporter_kind(name)
        destination.parent.mkdir(parents=True, exist_ok=True)
        fd, temporary_name = tempfile.mkstemp(prefix=f".{destination.stem}-export-", suffix=f".{output_format}", dir=str(destination.parent))
        os.close(fd)
        temporary = Path(temporary_name)
        temporary.unlink()
        validation: dict[str, Any] = {"valid": False}
        try:
            command = self._export_command(name, executable, output_format, svg_path, temporary)
            if command is None:
                return False, f"Unsupported {output_format} exporter {name!r}.", validation
            process = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=45, check=False)
            if process.returncode != 0:
                return False, f"{tool} exit {process.returncode}: {process.stderr.decode('utf-8', 'replace')[-400:]}", validation
            valid, validation = self._validate_export(temporary, output_format)
            if not valid:
                return False, f"{tool} produced structurally invalid {output_format.upper()}: {validation.get('reason', 'unknown defect')}", validation
            os.replace(temporary, destination)
            return True, f"{tool} produced a structurally valid {output_format.upper()}.", validation
        except (OSError, subprocess.SubprocessError) as exc:
            return False, f"{tool} failed: {exc}", validation
        finally:
            if temporary.exists():
                temporary.unlink()

    def _new_export_details(self) -> dict[str, Any]:
        formats: dict[str, Any] = {}
        for output_format, key in (("png", self.preview_key), ("pdf", self.pdf_key)):
            if key is None:
                continue
            requested = self.preview_requested if output_format == "png" else self.preview_pdf_requested
            formats[output_format] = {
                "requested": requested, "artifact_key": key, "path": self.artifact_defs[key]["path"],
                "exporter": None, "available": False, "attempts": [], "validation": None, "reused": False,
            }
        requested_formats = [output_format for output_format, _ in self._export_targets()]
        return {
            "requested": self.exports_requested, "requested_formats": requested_formats,
            "exporter": None, "available": False, "attempts": [], "formats": formats,
            "policy": "Only installed exporters are used; PNG and PDF are independently requested and structurally validated.",
        }

    def _export(self) -> list[dict[str, Any]]:
        self.export_details = self._new_export_details()
        errors: list[dict[str, Any]] = []
        assert self.svg_key is not None
        svg_path = self._artifact_path(self.svg_key)
        for output_format, key in self._export_targets():
            details = self.export_details["formats"][output_format]
            destination = self._artifact_path(key)
            if destination.is_file() or destination.is_symlink():
                destination.unlink()
            candidates = self._candidate_exporters(output_format)
            failures: list[str] = []
            for name, executable in candidates:
                ok, detail, validation = self._export_one(name, executable, output_format, svg_path, destination)
                attempt = {
                    "format": output_format, "artifact_key": key, "exporter": name,
                    "ok": ok, "detail": detail, "validation": validation,
                }
                details["attempts"].append(attempt)
                self.export_details["attempts"].append(attempt)
                if ok:
                    details.update({"exporter": name, "available": True, "validation": validation})
                    self.artifact_errors.pop(key, None)
                    self.changes.append({
                        "action": f"exported_{output_format}_preview", "exporter": name,
                        "source_svg": self.artifact_defs[self.svg_key]["path"], "preview": self.artifact_defs[key]["path"],
                        "validation": validation,
                    })
                    break
                failures.append(detail)
            if details["available"]:
                continue
            if candidates:
                message = f"Supported {output_format.upper()} exporter(s) failed or returned an invalid file; SVG was retained."
                hint = " | ".join(failures)[-1200:]
            else:
                message = f"{output_format.upper()} export was requested but no supported installed exporter is available."
                hint = (
                    "SVG and result.json remain valid. Install nothing automatically; provide an already installed "
                    + ("rsvg-convert, Inkscape, CairoSVG, ImageMagick, or sips, or omit PNG." if output_format == "png"
                       else "rsvg-convert, Inkscape, Chrome/Chromium, or CairoSVG, or omit PDF.")
                )
            self.artifact_errors[key] = issue("tool_unavailable", message, self.artifact_defs[key]["path"], hint)
            details["error"] = self.artifact_errors[key]
            errors.append(self.artifact_errors[key])
        requested = [self.export_details["formats"][output_format] for output_format, _ in self._export_targets()]
        self.export_details["available"] = bool(requested) and all(item["available"] for item in requested)
        successful = next((item["exporter"] for item in requested if item["available"]), None)
        self.export_details["exporter"] = successful
        if errors:
            self.export_details["error"] = errors[0]
        return errors

    def _all_errors(self) -> list[dict[str, Any]]:
        errors = [] if "intake" in self.stage_records else list(self.bootstrap_errors)
        for stage in STAGE_ORDER:
            record = self.stage_records.get(stage, {})
            errors.extend(record.get("errors", []))
        return errors

    def _requested_keys(self) -> set[str]:
        keys = {key for key, value in self.contract.items() if value["required"]}
        if self.report_key:
            keys.add(self.report_key)
        if self.svg_key:
            keys.add(self.svg_key)
        if self.spec.get("mode") == "chart" and self.data_key:
            keys.add(self.data_key)
        if self.preview_requested and self.preview_key:
            keys.add(self.preview_key)
        if self.preview_pdf_requested and self.pdf_key:
            keys.add(self.pdf_key)
        return keys

    def _artifact_records(self, assume_report: bool = False) -> list[dict[str, Any]]:
        records = []
        requested = self._requested_keys()
        for key, definition in self.artifact_defs.items():
            path = self._artifact_path(key)
            available = path.is_file()
            size = sha = None
            if available:
                try:
                    raw = path.read_bytes()
                    size, sha = len(raw), sha256_bytes(raw)
                except OSError:
                    available = False
            if assume_report and key == self.report_key:
                available = True
            error = None if available else self.artifact_errors.get(key)
            if not available and error is None and key in requested:
                error = issue("semantic_defect", "Requested artifact was not produced.", definition["path"])
            availability = "available" if available else ("not_requested" if key not in requested and error is None else "unavailable")
            records.append({
                "contract_key": key if key in self.contract else None,
                "artifact_id": key,
                "path": definition["path"], "kind": definition["kind"],
                "required": bool(definition.get("required")), "requested": key in requested,
                "available": available, "availability": availability,
                "bytes": size, "sha256": sha, "error": error,
            })
        return records

    def _status(self, assume_report: bool = False) -> str:
        if self.fatal_bootstrap:
            return "failed"
        records = self._artifact_records(assume_report=assume_report)
        requested = [item for item in records if item["requested"]]
        complete = bool(requested) and all(item["available"] for item in requested) and not self._all_errors()
        if complete:
            return "success"
        if any(item["available"] for item in requested) or self.report_path.is_file():
            return "partial"
        return "partial" if self.case_id else "failed"

    @property
    def report_path(self) -> Path:
        return self._artifact_path(self.report_key) if self.report_key else self.output_dir / "report.md"

    def _sources(self) -> list[dict[str, Any]]:
        sources = []
        for item in self.manifest.get("inputs", []):
            if not item.get("available"):
                continue
            source = {key: item.get(key) for key in ("id", "path", "kind", "role", "version", "bytes", "sha256", "locator") if key in item}
            sources.append(source)
        inspection = self.spec.get("figure_inspection") if self.spec else None
        if isinstance(inspection, dict):
            for source in sources:
                if source.get("id") == inspection.get("source_id"):
                    source["figure_inspection"] = inspection
        return sources

    def _uncertainties(self) -> list[str]:
        values = []
        if self.synthetic:
            values.append("SYNTHETIC example only: values and biological/scientific claims are not evidence for an official case.")
        if self.spec.get("figure_inspection"):
            values.append("Figure observations are supplied by the inspecting agent and source-bound; the fallback renderer does not independently adjudicate biological correctness.")
        for error in self._all_errors():
            text = f"{error['kind']}: {error['message']}"
            if text not in values:
                values.append(text)
        return values

    def _write_result(self, assume_report: bool = False) -> str:
        artifacts = self._artifact_records(assume_report=assume_report)
        by_id = {item["artifact_id"]: item for item in artifacts}
        result: dict[str, Any] = {
            "case_id": self.case_id,
            "status": self._status(assume_report=assume_report),
            "sources": self._sources(),
            "uncertainties": self._uncertainties(),
            "change_records": self.changes,
            "artifacts": artifacts,
            "stages": self.stage_records,
            "errors": self._all_errors(),
            "runner": RUNNER_VERSION,
            "resume": self.resume_requested,
            "synthetic": self.synthetic,
            "output_contract": self.contract,
        }
        for key in self.contract:
            record = by_id.get(key)
            result[key] = record["path"] if record and record["available"] else None
        atomic_write_json(self.result_path, result)
        return result["status"]

    def _write_checkpoint(self) -> None:
        value = {
            "schema_version": 1,
            "runner": RUNNER_VERSION,
            "case_id": self.case_id,
            "input_fingerprint": self.fingerprint,
            "resume": self.resume_requested,
            "stages": self.stage_records,
            "pending_stages": [stage for stage in STAGE_ORDER if stage not in self.stage_records],
            "change_records": self.changes,
            "export_details": self.export_details,
            "resume_semantics": "A matching fingerprint covers both preview requests and permits intact render/export reuse; validation always reruns and report/result are rebuilt. Cached PNG/PDF structure is revalidated. Changed inputs or preview requests invalidate stale contract artifacts.",
        }
        atomic_write_json(self.checkpoint_path, value)

    def _record_stage(self, name: str, status: str, errors: list[dict[str, Any]], action: str) -> None:
        assert status in {"succeeded", "partial", "failed", "skipped"}
        for error in errors:
            assert error["kind"] in ERROR_KINDS
        self.stage_records[name] = {
            "status": status,
            "error_taxonomy": sorted({error["kind"] for error in errors}),
            "errors": errors,
            "action": action,
        }
        self._write_checkpoint()
        self._write_result(assume_report=(name == "project_result"))

    def _render_reusable(self) -> bool:
        if not self.same_inputs or not self.previous.get("stages", {}).get("render", {}).get("status") == "succeeded":
            return False
        keys = [self.svg_key]
        if self.spec.get("mode") == "chart":
            keys.append(self.data_key)
        return all(key and self._artifact_path(key).is_file() for key in keys)

    def _export_reusable(self) -> bool:
        if not self.exports_requested:
            return True
        if not self.same_inputs or self.previous.get("stages", {}).get("export", {}).get("status") != "succeeded":
            return False
        for output_format, key in self._export_targets():
            path = self._artifact_path(key)
            if not path.is_file():
                return False
            valid, _ = self._validate_export(path, output_format)
            if not valid:
                return False
        return bool(self._export_targets())

    def _load_reused_mapping(self) -> None:
        if self.spec.get("mode") == "chart" and self.data_key:
            value, _, error = read_json(self._artifact_path(self.data_key))
            if not error and isinstance(value, dict):
                self.data_mapping = value

    def _report(self) -> str:
        status = self._status(assume_report=True)
        lines = ["# Case delivery report", ""]
        if self.synthetic:
            lines += ["> **SYNTHETIC EXAMPLE — NOT AN OFFICIAL CASE OR SCIENTIFIC EVIDENCE**", ""]
        lines += [f"- Case ID: `{self.case_id}`", f"- Final status: **{status}**", f"- Runner: `{RUNNER_VERSION}`", "- Delivery uses one deterministic runner pass. Agent review is bounded to at most two rounds; no automatic scientific correction is claimed.", "", "## Output contract projection", "", "| Contract key | Availability | Actual path | Error |", "|---|---|---|---|"]
        for artifact in self._artifact_records(assume_report=True):
            key = artifact["contract_key"] if artifact["contract_key"] is not None else f"(auxiliary) {artifact['artifact_id']}"
            error = artifact["error"]["kind"] if artifact["error"] else "—"
            lines.append(f"| `{key}` | {artifact['availability']} | `{artifact['path']}` | {error} |")
        lines += ["", "Every original output_contract key is projected as a top-level result.json key. Available values are relative paths; unavailable values are null.", "", "## Stage checkpoints", "", "| Stage | Status | Error taxonomy | Action |", "|---|---|---|---|"]
        for stage in STAGE_ORDER:
            record = self.stage_records.get(stage, {"status": "pending", "error_taxonomy": [], "action": "not reached"})
            lines.append(f"| {stage} | {record['status']} | {', '.join(record['error_taxonomy']) or '—'} | {record['action']} |")
        lines += ["", "## Actual input manifest", "", "| ID | Role | Available | Bytes | SHA-256 | Actual path |", "|---|---|---|---:|---|---|"]
        for item in self.manifest.get("inputs", []):
            lines.append(f"| {item['id']} | {item['role']} | {str(item['available']).lower()} | {item['bytes'] if item['bytes'] is not None else '—'} | `{item['sha256'] or '—'}` | `{item['path']}` |")
        lines += ["", "Manifest entries record bytes actually read. A missing or unreadable source never receives an invented hash.", ""]
        if self.data_mapping:
            comparison = self.data_mapping.get("primary_source_comparison", {})
            lines += ["## Chart data and primary-source comparison", "", f"Source: `{self.data_mapping['source']['path']}`", f"Columns read: `{', '.join(self.data_mapping['columns'])}`", f"All plotted values match their parsed source cells: **{comparison.get('all_match')}**", "", "| CSV row (header = 1) | Series | Raw x | Raw y | Plotted x | Plotted y | Match |", "|---:|---|---|---|---:|---:|---|"]
            for row in comparison.get("rows", []):
                lines.append(f"| {row['csv_row']} | {row['series']} | {row['raw_x']} | {row['raw_y']} | {fmt(row['plotted_x'])} | {fmt(row['plotted_y'])} | {row['matches']} |")
            lines.append("")
        inspection = self.spec.get("figure_inspection") if self.spec else None
        if isinstance(inspection, dict):
            lines += ["## Figure inspection record", "", "```json", json.dumps(inspection, ensure_ascii=False, indent=2, sort_keys=True), "```", "", "These observations are agent-created from the actual source figure. The runner does not replace biological review with an export check.", ""]
        lines += ["## PNG/PDF preview exports", "", "```json", json.dumps(self.export_details, ensure_ascii=False, indent=2, sort_keys=True), "```", "", "The built-in SVG renderer is intentionally modest. PNG/PDF exports are independently optional and externally detected; no package installation is attempted. PDF validation covers physical document structure, not visual or scientific fidelity.", "", "## Change records", "", "```json", json.dumps(self.changes, ensure_ascii=False, indent=2, sort_keys=True), "```", "", "## Uncertainties and limits", ""]
        uncertainties = self._uncertainties()
        lines += [(f"- {value}") for value in uncertainties] or ["- None recorded by the runner; scientific judgement remains external."]
        lines += ["", "## Resume", "", "Run again with `--resume`. The input fingerprint covers actual file hashes and independent PNG/PDF preview requests. Intake and validation rerun; intact render/export artifacts are structurally revalidated and reused only after a matching successful checkpoint. Changed inputs or preview requests invalidate stale outputs. The JSON result is atomically replaced after each stage.", ""]
        return "\n".join(lines)

    def run(self) -> int:
        self._load_previous()
        self._bootstrap_case()
        self._write_checkpoint()
        self._write_result()
        if self.fatal_bootstrap:
            self.manifest = {"schema_version": 1, "case_id": self.case_id, "inputs": [self._scan_input("case", self.case_path, "json", "case_contract")], "note": "Bootstrap failed; no scientific output was assumed."}
            atomic_write_json(self.manifest_path, self.manifest)
            self._record_stage("intake", "failed", self.bootstrap_errors, "case bootstrap failed; honest result.json retained")
            self._write_result()
            return 3

        intake_errors = self._intake()
        previous_fingerprint = self.previous.get("input_fingerprint")
        self.same_inputs = self.resume_requested and bool(previous_fingerprint) and previous_fingerprint == self.fingerprint
        if self.same_inputs:
            self.changes = list(self.previous.get("change_records", []))
            self.export_details = dict(self.previous.get("export_details", self.export_details))
        else:
            self._invalidate_outputs()
            self.artifact_errors = {}
        intake_status = "succeeded" if not intake_errors else "partial"
        self._record_stage("intake", intake_status, intake_errors, f"read actual inputs and wrote manifest; input fingerprint {'matched' if self.same_inputs else 'changed/new'}")

        validation_errors = self._validate(intake_errors)
        if intake_errors:
            self._record_stage("validate", "skipped", [], "validation cannot proceed until intake defects are resolved")
        else:
            if validation_errors:
                for key in (self.svg_key, self.data_key):
                    if key and key in self.artifact_defs:
                        self.artifact_errors[key] = validation_errors[0]
            self._record_stage("validate", "succeeded" if not validation_errors else "partial", validation_errors, "validated actual sources, agent specification, dynamic artifact roles, and source mappings")

        if intake_errors or validation_errors:
            self._record_stage("render", "skipped", [], "scientific artifact not fabricated after intake/validation defects")
        elif self._render_reusable():
            self._load_reused_mapping()
            self._record_stage("render", "succeeded", [], "reused intact source-bound SVG/data artifacts from matching checkpoint")
        else:
            try:
                render_errors = self._render()
            except (OSError, KeyError, AssertionError, ValueError) as exc:
                render_errors = [issue("semantic_defect", f"Renderer could not complete: {exc}", str(self.spec_path))]
            self._record_stage("render", "succeeded" if not render_errors else "failed", render_errors, "wrote editable SVG with deterministic built-in fallback; existing SVG edits are literal targeted patches")

        if not self.exports_requested:
            self.export_details = self._new_export_details()
            self._record_stage("export", "skipped", [], "PNG/PDF previews not requested; editable SVG is still delivered")
        elif self.svg_key is None or not self._artifact_path(self.svg_key).is_file():
            self.export_details = self._new_export_details()
            for output_format, key in self._export_targets():
                self.artifact_errors[key] = issue(
                    "missing_material", f"Cannot export {output_format.upper()} because the source SVG is unavailable.",
                    self.artifact_defs[key]["path"],
                )
                self.export_details["formats"][output_format]["error"] = self.artifact_errors[key]
            self._record_stage("export", "skipped", [], "previews not attempted without a valid SVG")
        elif self._export_reusable():
            for output_format, key in self._export_targets():
                valid, validation = self._validate_export(self._artifact_path(key), output_format)
                assert valid
                details = self.export_details["formats"][output_format]
                details.update({"available": True, "reused": True, "validation": validation})
            formats = "/".join(output_format.upper() for output_format, _ in self._export_targets())
            self._record_stage("export", "succeeded", [], f"reused structurally valid {formats} preview(s) from matching checkpoint")
        else:
            export_errors = self._export()
            self._record_stage("export", "succeeded" if not export_errors else "partial", export_errors, "detected optional PNG/PDF exporters without installing software; SVG survives exporter failure")

        report_text = self._report()
        atomic_write_bytes(self.report_path, report_text.encode("utf-8"))
        self.artifact_errors.pop(self.report_key, None)
        self._record_stage("report", "succeeded", [], "wrote source, availability, taxonomy, comparison, and resume report")
        self._record_stage("project_result", "succeeded", [], "atomically projected every output_contract key to result top level with per-artifact availability")
        atomic_write_bytes(self.report_path, self._report().encode("utf-8"))
        status = self._write_result(assume_report=True)
        return 0 if status == "success" else (2 if status == "partial" else 3)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--case", required=True, help="Actual case.json")
    parser.add_argument("--task", help="Actual task.md; auto-detects case sibling, /input/task.md, then /task.md")
    parser.add_argument("--spec", required=True, help="Agent-created source-bound case specification")
    parser.add_argument("--work-dir", required=True, help="Temporary/work directory, e.g. /app/work")
    parser.add_argument("--output-dir", required=True, help="Final artifact directory, e.g. /app/output")
    parser.add_argument("--preview-png", action="store_true", help="Request optional external SVG-to-PNG export")
    parser.add_argument("--preview-pdf", action="store_true", help="Request optional external SVG-to-PDF export")
    parser.add_argument("--resume", action="store_true", help="Reuse only intact stages with a matching input fingerprint")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    runner = Runner(args)
    return runner.run()


if __name__ == "__main__":
    sys.exit(main())
