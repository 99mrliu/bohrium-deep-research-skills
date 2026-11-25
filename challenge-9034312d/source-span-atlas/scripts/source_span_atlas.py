#!/usr/bin/env python3
"""Validate a source-span atlas, render or audit an SVG, and emit result/report artifacts."""
from __future__ import annotations

import argparse
import importlib.util
import json
import os
from pathlib import Path
import re
import shutil
import struct
import subprocess
import sys

sys.dont_write_bytecode = True
SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))
from atlas_lib import (AtlasError, Reporter, canonical_json, coverage_for_svg, read_utf8,
                       render_svg, sha256_bytes, validate_spec)


def script_path(value):
    path = Path(value)
    return path.resolve() if path.is_absolute() else (SCRIPT_DIR / path).resolve()


def write_text(path, content):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8", newline="\n")


def markdown_report(atlas):
    lines = [
        "# Source-span atlas report", "",
        "**%s — SYNTHETIC example only; not scientific evidence.**" % atlas.get("case_id")
        if atlas.get("synthetic") else "**Case: %s**" % atlas.get("case_id"),
        "", "Verdict: **%s**" % atlas.get("verdict", "failed"), "",
        "> A normalized quote hit establishes only a source span. Scientific meaning requires the separately recorded semantic comparison and, for original figures, direct visual inspection. This report does not automate scientific judgement.", "",
        "## Sources", "",
        "| Source | Kind | SHA-256 | Declared path | Version |", "|---|---|---|---|---|",
    ]
    for source in atlas.get("sources", []):
        lines.append("| %s | %s | `%s` | %s | %s |" % (source.get("source_id"), source.get("kind"), source.get("sha256"), source.get("declared_path"), source.get("version")))
    lines.extend(["", "## Assertion-to-source-to-visual coverage", ""])
    for assertion in atlas.get("assertions", []):
        lines.append("### %s — %s" % (assertion.get("id"), assertion.get("label")))
        lines.append("")
        lines.append("- Category/status: `%s` / `%s`; visual: `%s`." % (assertion.get("category"), assertion.get("evidence_status"), assertion.get("visual_id")))
        semantic = assertion.get("semantic_review") or {}
        lines.append("- Separate semantic review: `%s`. %s" % (semantic.get("result", "unreviewed"), semantic.get("comparison", "No comparison recorded.")))
        for evidence in assertion.get("evidence", []):
            locator = evidence.get("locator", {})
            place = locator.get("section") or locator.get("figure") or "unspecified"
            if locator.get("panel"):
                place += ", panel " + str(locator["panel"])
            lines.append("- `%s`, page %s, lines %s–%s, %s; original offsets `%s`; normalized offsets `%s`." % (
                evidence.get("source_id"), evidence.get("page"), evidence.get("line_start"),
                evidence.get("line_end"), place, evidence.get("source_span_code_points"), evidence.get("normalized_span")))
            lines.append("  - Exact source excerpt: “%s”" % evidence.get("original_source_excerpt", "").replace("\n", " "))
    lines.extend(["", "## Direct original-figure reviews", ""])
    if not atlas.get("figure_reviews"):
        lines.append("None declared. Figure-backed assertions cannot pass without one.")
    for review in atlas.get("figure_reviews", []):
        lines.append("- `%s`: %s; panels %s; reviewed SHA-256 `%s`. %s" % (
            review.get("figure_review_id"), review.get("inspection_mode"),
            review.get("inspected_panels"), review.get("reviewed_sha256"), review.get("comparison")))
    lines.extend(["", "## Actual CSV mappings", ""])
    if not atlas.get("charts"):
        lines.append("No charts declared.")
    for chart in atlas.get("charts", []):
        lines.append("- `%s` binds **case-sensitive columns** `%s` and `%s` from `%s`; no imputation." % (chart.get("id"), chart.get("x_column"), chart.get("y_column"), chart.get("source_id")))
        for row in chart.get("row_mappings", []):
            lines.append("  - CSV row %s: `%s`=%s, `%s`=%s → `%s`." % (row["source_row"], row["x_column"], row["x_raw"], row["y_column"], row["y_raw"], row["visual_element_id"]))
    lines.extend(["", "## Conflicts", ""])
    if not atlas.get("conflicts"):
        lines.append("No conflicts declared. Absence here is not a claim that none exist; unresolved discovered conflicts block the gate.")
    for conflict in atlas.get("conflicts", []):
        lines.append("- `%s` (%s): %s Resolution: %s Visual treatment: %s" % (conflict.get("id"), conflict.get("status"), conflict.get("description"), conflict.get("resolution"), conflict.get("visual_treatment")))
    coverage = atlas.get("coverage")
    lines.extend(["", "## Source-to-visual coverage", ""])
    if coverage:
        lines.append("Bidirectional coverage passed: **%s**. Expected/scientific visuals: %s/%s." % (coverage.get("passed"), coverage.get("expected_visual_count"), coverage.get("scientific_visual_count")))
        for source_id, visual_ids in coverage.get("source_to_visual", {}).items():
            lines.append("- `%s` → %s" % (source_id, ", ".join("`%s`" % item for item in visual_ids)))
    lines.extend(["", "## Gate findings", ""])
    if not atlas.get("errors"):
        lines.append("No gate errors. This is not a scientific correctness certificate.")
    for error in atlas.get("errors", []):
        lines.append("- **%s** `%s`: %s" % (error.get("assertion_id", "atlas"), error.get("code"), error.get("message")))
    for warning in atlas.get("warnings", []):
        lines.append("- Warning `%s`: %s" % (warning.get("code"), warning.get("message")))
    lines.append("")
    return "\n".join(lines)


def inspect_pdf(path):
    """Check the actual bytes of a simple exported PDF, without third-party libraries."""
    path = Path(path)
    if not path.is_file():
        return {"valid": False, "checks": {"file_exists": False}, "errors": ["PDF does not exist"]}
    try:
        data = path.read_bytes()
    except OSError as exc:
        return {"valid": False, "checks": {"file_exists": True, "readable": False}, "errors": [str(exc)]}
    objects = re.findall(rb"\d+\s+\d+\s+obj\b(.*?)\bendobj", data, re.DOTALL)
    page_objects = [item for item in objects if re.search(rb"/Type\s*/Page\b", item)]
    page_trees = [item for item in objects if re.search(rb"/Type\s*/Pages\b", item)]
    counts = []
    for item in page_trees:
        match = re.search(rb"/Count\s+(\d+)", item)
        if match:
            counts.append(int(match.group(1)))
    number = rb"[+-]?(?:\d+(?:\.\d*)?|\.\d+)"
    boxes = re.findall(rb"/MediaBox\s*\[\s*(" + number + rb")\s+(" + number +
                       rb")\s+(" + number + rb")\s+(" + number + rb")\s*\]", data)
    dimensions = []
    for box in boxes:
        try:
            x0, y0, x1, y1 = [float(value) for value in box]
            dimensions.append([abs(x1 - x0), abs(y1 - y0)])
        except ValueError:
            pass
    startxref = list(re.finditer(rb"startxref\s+(\d+)", data))
    xref_target = False
    if startxref:
        offset = int(startxref[-1].group(1))
        if 0 <= offset < len(data):
            target = data[offset:offset + 128].lstrip()
            xref_target = target.startswith(b"xref") or re.match(rb"\d+\s+\d+\s+obj\b", target) is not None
    checks = {
        "file_exists": True,
        "readable": True,
        "pdf_header": data.startswith(b"%PDF-"),
        "eof_marker": re.search(rb"%%EOF\s*$", data[-4096:]) is not None,
        "page_object": bool(page_objects),
        "page_tree_with_positive_count": bool(counts) and max(counts) > 0,
        "page_count_consistent": bool(page_objects) and bool(counts) and len(page_objects) == max(counts),
        "positive_media_box": bool(dimensions) and all(width > 0 and height > 0 for width, height in dimensions),
        "startxref_target": xref_target,
    }
    result = {
        "valid": all(checks.values()),
        "checks": checks,
        "bytes": len(data),
        "sha256": sha256_bytes(data),
        "page_count": max(counts) if counts else None,
        "page_dimensions_points": dimensions,
        "errors": [name for name, passed in checks.items() if not passed],
    }
    return result


def remove_output(path):
    """Remove a requested export target so stale bytes cannot become a false success."""
    try:
        if Path(path).is_file() or Path(path).is_symlink():
            Path(path).unlink()
        return None
    except OSError as exc:
        return str(exc)


def detect_browser():
    """Return an existing Chrome/Chromium executable and how it was found."""
    problems = []
    configured = os.environ.get("SOURCE_SPAN_ATLAS_BROWSER")
    if configured:
        configured_path = Path(configured).expanduser()
        executable = None
        if configured_path.is_file() and os.access(str(configured_path), os.X_OK):
            executable = str(configured_path.resolve())
        else:
            executable = shutil.which(configured)
        if executable:
            return executable, "SOURCE_SPAN_ATLAS_BROWSER", problems
        problems.append("SOURCE_SPAN_ATLAS_BROWSER is not an executable existing browser: %s" % configured)
    for name in ("chromium", "chromium-browser", "google-chrome", "google-chrome-stable", "chrome"):
        executable = shutil.which(name)
        if executable:
            return executable, name + " on PATH", problems
    for candidate in (
        "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
        "/Applications/Chromium.app/Contents/MacOS/Chromium",
    ):
        if Path(candidate).is_file() and os.access(candidate, os.X_OK):
            return candidate, "standard installed application", problems
    problems.append("no Chrome/Chromium executable found on PATH or in standard application locations")
    return None, None, problems


def export_pdf(svg_path, pdf_path, report_path):
    """Export PDF using installed tools only, then validate its physical PDF structure."""
    attempts = []
    structure = {"valid": False, "checks": {"file_exists": False}, "errors": ["PDF export not attempted"]}
    success = False
    try:
        pdf_path.parent.mkdir(parents=True, exist_ok=True)
        if pdf_path.resolve() == svg_path.resolve():
            raise OSError("PDF output must differ from the editable SVG input")
        preparation_error = remove_output(pdf_path)
        if preparation_error:
            raise OSError("Cannot remove previous PDF target: " + preparation_error)
    except OSError as exc:
        attempts.append({"tool": "output preparation", "success": False, "error": str(exc)})
        report = {"success": False, "format": "pdf", "svg": str(svg_path.resolve()), "pdf": None,
                  "attempts": attempts, "structure": structure}
        write_text(report_path, canonical_json(report))
        return report

    def validate_attempt(attempt):
        nonlocal structure, success
        if pdf_path.is_file():
            structure = inspect_pdf(pdf_path)
            attempt["pdf_structure"] = structure
        attempt["success"] = bool(attempt.get("returncode", 0) == 0 and structure["valid"])
        if attempt["success"]:
            success = True
        elif pdf_path.exists():
            error = remove_output(pdf_path)
            if error:
                attempt["cleanup_error"] = error
        return success

    if importlib.util.find_spec("cairosvg") is not None:
        attempt = {"tool": "cairosvg"}
        try:
            import cairosvg
            cairosvg.svg2pdf(url=str(svg_path), write_to=str(pdf_path))
            attempt["returncode"] = 0
        except Exception as exc:
            attempt["error"] = str(exc)
            attempt["returncode"] = 1
        attempts.append(attempt)
        validate_attempt(attempt)
    else:
        attempts.append({"tool": "cairosvg", "success": False, "error": "not installed; no installation attempted"})

    native_tools = (
        ("rsvg-convert", lambda executable: [executable, "-f", "pdf", "-o", str(pdf_path), str(svg_path)]),
        ("inkscape", lambda executable: [executable, str(svg_path), "--export-type=pdf",
                                         "--export-filename=" + str(pdf_path)]),
    )
    for name, command_for in native_tools:
        if success:
            break
        executable = shutil.which(name)
        if not executable:
            attempts.append({"tool": name, "success": False, "error": "not installed; no installation attempted"})
            continue
        command = command_for(executable)
        attempt = {"tool": name, "command": command}
        try:
            proc = subprocess.run(command, capture_output=True, text=True, timeout=60)
            attempt.update({"returncode": proc.returncode, "stderr": proc.stderr[-1000:]})
        except (OSError, subprocess.TimeoutExpired) as exc:
            attempt.update({"returncode": 1, "error": str(exc)})
        attempts.append(attempt)
        validate_attempt(attempt)

    if not success:
        executable, origin, detection_problems = detect_browser()
        if executable:
            command = [executable, "--headless", "--disable-gpu", "--no-sandbox", "--no-pdf-header-footer",
                       "--print-to-pdf-no-header", "--print-to-pdf=" + str(pdf_path), svg_path.resolve().as_uri()]
            attempt = {"tool": "headless Chrome/Chromium", "detected_by": origin,
                       "detection_notes": detection_problems, "command": command}
            try:
                proc = subprocess.run(command, capture_output=True, text=True, timeout=60)
                attempt.update({"returncode": proc.returncode, "stderr": proc.stderr[-1000:]})
            except (OSError, subprocess.TimeoutExpired) as exc:
                attempt.update({"returncode": 1, "error": str(exc)})
            attempts.append(attempt)
            validate_attempt(attempt)
        else:
            attempts.append({"tool": "headless Chrome/Chromium", "success": False,
                             "error": "; ".join(detection_problems) + "; no installation attempted"})

    if not success:
        structure = inspect_pdf(pdf_path)
    report = {
        "success": success, "format": "pdf", "svg": str(svg_path.resolve()),
        "pdf": str(pdf_path.resolve()) if success else None, "attempts": attempts,
        "structure": structure,
        "font_note": "Editable text remains in SVG. PDF font embedding and substitution are tool-dependent and not preflighted; inspect the actual PDF.",
        "color_note": "RGB SVG; no CMYK conversion or journal preflight is claimed.",
        "inspection_note": "Structural PDF checks do not prove scientific correctness or visual fidelity; inspect the actual PDF.",
    }
    write_text(report_path, canonical_json(report))
    return report


def export_png(svg_path, png_path, report_path):
    attempts = []
    png_path.parent.mkdir(parents=True, exist_ok=True)
    if importlib.util.find_spec("cairosvg") is not None:
        try:
            import cairosvg
            cairosvg.svg2png(url=str(svg_path), write_to=str(png_path), scale=2.0)
            attempts.append({"tool": "cairosvg", "success": True, "scale": 2.0})
        except Exception as exc:
            attempts.append({"tool": "cairosvg", "success": False, "error": str(exc)})
    else:
        attempts.append({"tool": "cairosvg", "success": False, "error": "not installed; no installation attempted"})
    if not png_path.exists():
        executable = shutil.which("rsvg-convert")
        if executable:
            proc = subprocess.run([executable, "-w", "2400", "-o", str(png_path), str(svg_path)], capture_output=True, text=True)
            attempts.append({"tool": "rsvg-convert", "success": proc.returncode == 0, "returncode": proc.returncode, "stderr": proc.stderr[-1000:]})
        else:
            attempts.append({"tool": "rsvg-convert", "success": False, "error": "not installed; no installation attempted"})
    if not png_path.exists():
        executable = shutil.which("inkscape")
        if executable:
            proc = subprocess.run([executable, str(svg_path), "--export-type=png", "--export-width=2400", "--export-filename=" + str(png_path)], capture_output=True, text=True)
            attempts.append({"tool": "inkscape", "success": proc.returncode == 0, "returncode": proc.returncode, "stderr": proc.stderr[-1000:]})
        else:
            attempts.append({"tool": "inkscape", "success": False, "error": "not installed; no installation attempted"})
    if not png_path.exists():
        executable, origin, detection_problems = detect_browser()
        if executable:
            try:
                import xml.etree.ElementTree as ET
                root = ET.parse(str(svg_path)).getroot()
                width = max(1, min(4000, int(float(root.attrib.get("width", "1200")))))
                height = max(1, min(4000, int(float(root.attrib.get("height", "800")))))
                proc = subprocess.run([executable, "--headless", "--disable-gpu", "--no-sandbox", "--hide-scrollbars",
                                       "--window-size=%d,%d" % (width, height),
                                       "--screenshot=" + str(png_path), Path(svg_path).resolve().as_uri()],
                                      capture_output=True, text=True, timeout=60)
                attempts.append({"tool": "headless Chrome/Chromium", "detected_by": origin,
                                 "detection_notes": detection_problems,
                                 "success": proc.returncode == 0 and png_path.exists(),
                                 "returncode": proc.returncode, "stderr": proc.stderr[-1000:], "pixel_scale": 1})
            except (OSError, ValueError, ET.ParseError, subprocess.TimeoutExpired) as exc:
                attempts.append({"tool": "headless Chrome/Chromium", "success": False, "error": str(exc)})
        else:
            attempts.append({"tool": "headless Chrome/Chromium", "success": False,
                             "error": "; ".join(detection_problems) + "; no installation attempted"})
    success = png_path.is_file() and png_path.stat().st_size > 24
    dimensions = None
    if success:
        data = png_path.read_bytes()[:24]
        if data[:8] != b"\x89PNG\r\n\x1a\n":
            success = False
            attempts.append({"tool": "PNG signature check", "success": False})
        else:
            dimensions = list(struct.unpack(">II", data[16:24]))
    report = {"success": success, "svg": str(svg_path.resolve()), "png": str(png_path.resolve()) if success else None,
              "attempts": attempts, "pixel_dimensions": dimensions,
              "font_note": "SVG text remains editable and uses a fallback family stack. Fonts are not embedded by this exporter; inspect preview for substitution/tofu.",
              "color_note": "RGB SVG; no CMYK conversion or journal preflight is claimed."}
    write_text(report_path, canonical_json(report))
    return report


def build_result(spec, atlas, output_dir, svg_path, artifacts, uncertainties):
    output_dir = Path(output_dir).resolve()

    def produced(desired):
        if not isinstance(desired, str) or not desired:
            return None
        candidate = Path(desired)
        candidate = candidate.resolve() if candidate.is_absolute() else (output_dir / candidate).resolve()
        if desired in {"result.json", "report.md"}:
            return str(candidate)
        return str(candidate) if candidate.is_file() else None

    result = {"case_id": atlas.get("case_id", spec.get("case_id", "unknown"))}
    for key, desired in (spec.get("output_contract") or {}).items():
        result[key] = produced(desired)
    if svg_path and svg_path.is_file():
        for key in result:
            if key == "editable_source" and not result[key]:
                result[key] = str(svg_path.resolve())
    errors = atlas.get("errors", [])
    status = "failed" if errors else "success"
    all_uncertainties = list(uncertainties)
    all_uncertainties.extend("%s: %s" % (item.get("code"), item.get("message")) for item in errors)
    result.update({
        "status": status, "verdict": atlas.get("verdict"),
        "sources": atlas.get("sources", []), "uncertainties": all_uncertainties,
        "change_records": spec.get("change_records", []),
        "artifacts": artifacts,
        "scientific_validation_note": "Gate success verifies source spans, locators, declared reviews, CSV mappings, and visual coverage. Scientific correctness still depends on independent comparison against the actual PDF and original figures.",
    })
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--atlas", required=True, help="Input atlas JSON; relative paths resolve beside this script")
    parser.add_argument("--output-dir", required=True, help="Output directory; relative paths resolve beside this script")
    parser.add_argument("--audit-svg", help="Audit an existing/patched SVG instead of rebuilding it")
    parser.add_argument("--preview-png", help="Optionally export PNG with detected installed tools")
    parser.add_argument("--preview-pdf", help="Optionally export structurally checked PDF with detected installed tools")
    args = parser.parse_args(argv)
    atlas_path = script_path(args.atlas)
    output_dir = script_path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    atlas_out = output_dir / "atlas.json"
    report_out = output_dir / "report.md"
    result_out = output_dir / "result.json"
    export_report_out = output_dir / "export_report.json"
    pdf_export_report_out = output_dir / "pdf_export_report.json"
    spec = {}
    artifacts = {}
    uncertainties = []
    svg_path = None
    exit_code = 0
    try:
        spec_text, _ = read_utf8(atlas_path)
        spec = json.loads(spec_text)
    except (OSError, AtlasError, json.JSONDecodeError) as exc:
        failed = {"schema_version": "source-span-atlas/1.0", "case_id": "unknown", "verdict": "failed",
                  "sources": [], "assertions": [], "conflicts": [], "charts": [],
                  "errors": [{"code": "ATLAS_READ", "message": str(exc)}], "warnings": []}
        write_text(atlas_out, canonical_json(failed))
        write_text(report_out, markdown_report(failed))
        result = {"case_id": "unknown", "status": "failed", "verdict": "failed", "sources": [],
                  "uncertainties": [str(exc)], "change_records": [],
                  "artifacts": {"atlas": str(atlas_out.resolve()), "report": str(report_out.resolve())}}
        write_text(result_out, canonical_json(result))
        print("Gate failed: %s" % exc, file=sys.stderr)
        return 2
    atlas, sources, by_id, charts = validate_spec(spec, atlas_path)
    uncertainties = list(spec.get("uncertainties", [])) if isinstance(spec.get("uncertainties", []), list) else ["uncertainties was not a list"]
    if not atlas["errors"]:
        coverage_reporter = Reporter()
        try:
            if args.audit_svg:
                svg_path = script_path(args.audit_svg)
                if not svg_path.is_file():
                    raise AtlasError("Audit SVG does not exist: %s" % svg_path)
                coverage = coverage_for_svg(svg_path, spec, atlas, coverage_reporter)
            else:
                svg_path = output_dir / "figure.svg"
                svg = render_svg(spec, atlas, charts)
                write_text(svg_path, svg)
                coverage = coverage_for_svg(svg_path, spec, atlas, coverage_reporter)
            atlas["coverage"] = coverage
            atlas["errors"].extend(coverage_reporter.errors)
            atlas["warnings"].extend(coverage_reporter.warnings)
            if coverage_reporter.errors:
                atlas["verdict"] = "failed"
        except (OSError, AtlasError) as exc:
            atlas["errors"].append({"code": "SVG_BUILD", "message": str(exc)})
            atlas["verdict"] = "failed"
    if not atlas["errors"]:
        atlas["verdict"] = "passed"
    write_text(atlas_out, canonical_json(atlas))
    artifacts.update({"atlas": str(atlas_out.resolve()), "report": str(report_out.resolve())})
    if svg_path and svg_path.is_file():
        artifacts["editable_svg"] = str(svg_path.resolve())
    exports = []
    if args.preview_png and atlas["verdict"] == "passed" and svg_path:
        png_path = script_path(args.preview_png)
        export = export_png(svg_path, png_path, export_report_out)
        exports.append(export)
        artifacts["export_report"] = str(export_report_out.resolve())
        if export["success"]:
            artifacts["preview_png"] = export["png"]
        else:
            uncertainties.append("PNG export unavailable or failed; editable SVG remains valid. See export_report.json. No installation was attempted.")
    if args.preview_pdf and atlas["verdict"] == "passed" and svg_path:
        pdf_path = script_path(args.preview_pdf)
        export = export_pdf(svg_path, pdf_path, pdf_export_report_out)
        exports.append(export)
        artifacts["pdf_export_report"] = str(pdf_export_report_out.resolve())
        if export["success"]:
            artifacts["preview_pdf"] = export["pdf"]
        else:
            uncertainties.append("PDF export unavailable or failed; editable SVG remains valid. See pdf_export_report.json. No PDF is claimed and no installation was attempted.")
    result = build_result(spec, atlas, output_dir, svg_path, artifacts, uncertainties)
    if exports:
        result["exports"] = exports
        if not all(item["success"] for item in exports) and result["status"] == "success":
            result["status"] = "partial"
    write_text(report_out, markdown_report(atlas))
    write_text(result_out, canonical_json(result))
    exit_code = 0 if atlas["verdict"] == "passed" else 2
    if exit_code:
        print("Gate failed with %d error(s); see %s" % (len(atlas["errors"]), atlas_out), file=sys.stderr)
    else:
        print("Gate passed: %s; %s; %s" % (svg_path, atlas_out, result_out))
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
