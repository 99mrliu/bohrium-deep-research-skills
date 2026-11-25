#!/usr/bin/env python3
"""Structural SVG/PNG/PDF export validity checks; no scientific judgement."""
from __future__ import annotations

import argparse
import binascii
import hashlib
import json
import struct
import sys
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any

PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"


def file_record(path: Path) -> dict[str, Any]:
    data = path.read_bytes()
    return {"path": path.name, "bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()}


def svg_audit(path: Path, required_layers: list[str]) -> tuple[dict[str, Any], list[dict[str, str]], list[str]]:
    record = file_record(path)
    errors: list[dict[str, str]] = []
    warnings: list[str] = []
    try:
        root = ET.parse(path).getroot()
        if root.tag.rsplit("}", 1)[-1] != "svg":
            errors.append({"code": "SVG_ROOT_INVALID", "message": "Root is not svg."})
        view_box = root.attrib.get("viewBox")
        if view_box:
            parts = view_box.replace(",", " ").split()
            if len(parts) != 4 or float(parts[2]) <= 0 or float(parts[3]) <= 0:
                errors.append({"code": "SVG_VIEWBOX_INVALID", "message": view_box})
            record["view_box"] = [float(item) for item in parts]
        texts = [e for e in root.iter() if e.tag.rsplit("}", 1)[-1] == "text" and "".join(e.itertext()).strip()]
        layers = sorted({e.attrib["data-qc-layer"] for e in root.iter() if e.attrib.get("data-qc-layer")})
        record["editable_text_count"] = len(texts)
        record["layers"] = layers
        if not texts:
            warnings.append("No visible text nodes were structurally observed; text may be outlines or missing.")
        for layer in required_layers:
            if layer not in layers:
                errors.append({"code": "LAYER_MISSING", "message": layer})
    except (ET.ParseError, ValueError, OSError) as exc:
        errors.append({"code": "SVG_PARSE_ERROR", "message": str(exc)})
    return record, errors, warnings


def png_audit(path: Path) -> tuple[dict[str, Any], list[dict[str, str]], list[str]]:
    record = file_record(path)
    errors: list[dict[str, str]] = []
    warnings: list[str] = []
    data = path.read_bytes()
    if not data.startswith(PNG_SIGNATURE):
        return record, [{"code": "PNG_SIGNATURE_INVALID", "message": "Missing PNG signature."}], warnings
    offset = len(PNG_SIGNATURE)
    chunks = []
    seen_iend = False
    try:
        while offset < len(data):
            if offset + 12 > len(data):
                raise ValueError("Truncated PNG chunk header.")
            length = struct.unpack(">I", data[offset:offset + 4])[0]
            kind = data[offset + 4:offset + 8]
            end = offset + 12 + length
            if end > len(data):
                raise ValueError("Truncated PNG chunk body.")
            payload = data[offset + 8:offset + 8 + length]
            crc = struct.unpack(">I", data[end - 4:end])[0]
            if crc != binascii.crc32(kind + payload) & 0xFFFFFFFF:
                raise ValueError(f"CRC mismatch in {kind.decode('ascii', 'replace')} chunk.")
            chunk_name = kind.decode("ascii")
            chunks.append(chunk_name)
            if kind == b"IHDR":
                width, height, depth, color, compression, filtering, interlace = struct.unpack(">IIBBBBB", payload)
                if width <= 0 or height <= 0:
                    errors.append({"code": "PNG_DIMENSION_INVALID", "message": f"{width}x{height}"})
                record.update({"width": width, "height": height, "bit_depth": depth,
                               "color_type": color, "interlace": interlace})
            if kind == b"IEND":
                seen_iend = True
                if end != len(data):
                    warnings.append("Bytes follow PNG IEND.")
                break
            offset = end
        if not chunks or chunks[0] != "IHDR":
            errors.append({"code": "PNG_IHDR_INVALID", "message": "IHDR is not first or is absent."})
        if not seen_iend:
            errors.append({"code": "PNG_IEND_MISSING", "message": "No IEND chunk."})
        record["chunks"] = chunks
    except (ValueError, UnicodeError, struct.error) as exc:
        errors.append({"code": "PNG_STRUCTURE_INVALID", "message": str(exc)})
    return record, errors, warnings


def pdf_audit(path: Path) -> tuple[dict[str, Any], list[dict[str, str]], list[str]]:
    record = file_record(path)
    errors: list[dict[str, str]] = []
    warnings: list[str] = []
    data = path.read_bytes()
    if not data.startswith(b"%PDF-"):
        errors.append({"code": "PDF_HEADER_INVALID", "message": "No PDF header at byte zero."})
    else:
        record["version"] = data[5:8].decode("ascii", "replace")
    if b"%%EOF" not in data[-2048:]:
        errors.append({"code": "PDF_EOF_MISSING", "message": "No EOF marker near file end."})
    if b"startxref" not in data[-4096:]:
        warnings.append("No startxref near PDF end; full parser validation is still required.")
    return record, errors, warnings


def build_report(svg: Path | None, png: Path | None, pdf: Path | None,
                 required_layers: list[str]) -> dict[str, Any]:
    records: dict[str, Any] = {}
    errors: list[dict[str, str]] = []
    warnings: list[str] = []
    for kind, path, function in (("svg", svg, svg_audit), ("png", png, png_audit), ("pdf", pdf, pdf_audit)):
        if path is None:
            continue
        try:
            if kind == "svg":
                record, found_errors, found_warnings = function(path, required_layers)
            else:
                record, found_errors, found_warnings = function(path)
            records[kind] = record
            errors.extend({**error, "artifact": kind} for error in found_errors)
            warnings.extend(f"{kind}: {warning}" for warning in found_warnings)
        except OSError as exc:
            errors.append({"code": "EXPORT_MISSING", "artifact": kind, "message": str(exc)})
    if not records and not errors:
        errors.append({"code": "NO_EXPORT_SUPPLIED", "message": "At least one actual export path is required."})
    return {
        "schema": "dual-artifact-quality-gate/export-audit-v1",
        "scientific_correctness": "not evaluated; signatures/XML/chunks only",
        "visual_validation_required": True,
        "artifacts": records,
        "errors": errors,
        "warnings": warnings,
        "status": "pass" if not errors else "fail",
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--svg", type=Path)
    parser.add_argument("--png", type=Path)
    parser.add_argument("--pdf", type=Path)
    parser.add_argument("--require-layer", action="append", default=[])
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args(argv)
    report = build_report(args.svg, args.png, args.pdf, args.require_layer)
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, indent=2, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8")
    return 2 if report["errors"] else 0


if __name__ == "__main__":
    sys.exit(main())
