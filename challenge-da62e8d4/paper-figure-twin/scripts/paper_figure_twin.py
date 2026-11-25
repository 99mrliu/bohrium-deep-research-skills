#!/usr/bin/env python3
"""Traceable manual paper-pixel digitization and candidate-series comparison.

No OCR, PDF extraction, curve recognition, unit guessing, or extrapolation.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import html
import json
import math
import os
from importlib import metadata
from pathlib import Path
import platform
import shlex
import subprocess
import sys
import time
from typing import Any

VERSION = "1.1.0"
BASE_FIELDS = ("case_id", "status", "sources", "uncertainty", "change_records")
EXTRA_FIELDS = ("artifacts", "comparison", "mapping", "report", "errors", "reproduction_verdict")


class PartialError(RuntimeError):
    pass


def parse_field_list(items: Any, label: str) -> list[str]:
    """Read a field list/mapping, retaining every field unless explicitly optional."""
    if isinstance(items, dict):
        entries = []
        for name, declaration in items.items():
            if isinstance(declaration, dict) and declaration.get("required") is False:
                continue
            entries.append(name)
        return entries
    if not isinstance(items, list):
        raise PartialError(f"{label} must be a list or mapping")
    fields = []
    for item in items:
        if isinstance(item, str):
            name = item
        elif isinstance(item, dict):
            if item.get("required") is False:
                continue
            name = next((item[key] for key in ("name", "field", "key", "id") if key in item), None)
        else:
            name = None
        if not isinstance(name, str) or not name.strip():
            raise PartialError(f"{label} contains an invalid field entry: {item!r}")
        fields.append(name.strip())
    return fields


def extract_contract_fields(contract: Any) -> list[str]:
    """Extract declared top-level fields from common output_contract shapes.

    JSON Schema uses its required array when present; without one, all declared
    properties are delivery requirements. Base result names are legal fields.
    """
    if contract is None:
        return []
    if isinstance(contract, list):
        fields = parse_field_list(contract, "output_contract")
    elif isinstance(contract, dict):
        if set(contract) == {"output_contract"}:
            return extract_contract_fields(contract["output_contract"])
        if set(contract) == {"schema"}:
            return extract_contract_fields(contract["schema"])
        if "properties" in contract:
            properties = contract["properties"]
            if not isinstance(properties, dict):
                raise PartialError("JSON Schema output_contract.properties must be an object")
            if "required" in contract:
                required = contract["required"]
                if not isinstance(required, list) or any(not isinstance(name, str) or not name.strip() for name in required):
                    raise PartialError("JSON Schema output_contract.required must be a string list")
                fields = [name for name in properties if name in required]
                fields += [name for name in required if name not in fields]
            else:
                fields = list(properties)
        elif "fields" in contract or "required_fields" in contract:
            fields = []
            if "fields" in contract:
                fields += parse_field_list(contract["fields"], "output_contract.fields")
            if "required_fields" in contract:
                fields += parse_field_list(contract["required_fields"], "output_contract.required_fields")
            fields = list(dict.fromkeys(fields))
        elif "required" in contract and isinstance(contract["required"], list):
            fields = parse_field_list(contract["required"], "output_contract.required")
        else:
            fields = parse_field_list(contract, "output_contract mapping")
    else:
        raise PartialError("output_contract must be a list, mapping, or JSON Schema object")
    if any(not isinstance(name, str) or not name.strip() for name in fields):
        raise PartialError("every output_contract field must be a nonempty string")
    duplicates = sorted({name for name in fields if fields.count(name) > 1})
    if duplicates:
        raise PartialError(f"duplicate output_contract fields: {duplicates}")
    return fields


def contract_values(spec: dict) -> dict:
    values = spec.get("contract_values", {})
    if not isinstance(values, dict):
        raise PartialError("spec.contract_values must be an object")
    return values


def output_relative(path: Path, output: Path) -> str:
    return Path(os.path.relpath(path.resolve(), output.resolve())).as_posix()


def unavailable_contract_value(field: str) -> dict:
    return {
        "status": "unavailable",
        "reason": f"No evidence-backed value for output_contract field {field!r} was supplied in spec.contract_values.",
        "evidence_required": True,
    }


def assemble_result(case: dict, spec: dict, *, complete: bool, reproduction_verdict: str,
                    sources: Any, uncertainty: list, change_records: list,
                    values: dict, fields: list[str] | None = None,
                    forced_status: str | None = None) -> tuple[dict, list[str]]:
    """Flatten intrinsic and case-specific values into the dynamic result contract."""
    fields = extract_contract_fields(case.get("output_contract")) if fields is None else fields
    supplied = contract_values(spec)
    result = {
        "case_id": case.get("case_id", "unknown"),
        "status": "success" if complete else "partial",
        "sources": sources,
        "uncertainty": uncertainty,
        "change_records": change_records,
    }
    missing = []
    for field in fields:
        if field in result:
            continue
        if field in values:
            result[field] = values[field]
        elif field in supplied and supplied[field] is not None:
            result[field] = supplied[field]
        else:
            result[field] = unavailable_contract_value(field)
            missing.append(field)
    for field in EXTRA_FIELDS:
        if field in values and field not in result:
            result[field] = values[field]
    if forced_status is not None:
        result["status"] = forced_status
    elif missing:
        result["status"] = "partial"
    return result, missing


def load_json(path: Path) -> Any:
    try:
        with path.open("r", encoding="utf-8") as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError) as exc:
        raise PartialError(f"cannot read JSON {path}: {exc}") from exc


def dump_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def finite(value: Any, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise PartialError(f"{label} must be a finite number")
    return float(value)


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def resolve(base: Path, value: str) -> Path:
    p = Path(value).expanduser()
    return (base / p).resolve() if not p.is_absolute() else p.resolve()


def fit_axis(axis: dict, name: str) -> dict:
    anchors = axis.get("anchors")
    if not isinstance(anchors, list) or len(anchors) < 2:
        raise PartialError(f"{name} axis needs at least two anchors; comparison is impossible")
    scale = axis.get("pixel_scale", "linear")
    if scale not in ("linear", "log"):
        raise PartialError(f"{name} pixel_scale must be linear or log")
    rows = []
    for i, anchor in enumerate(anchors):
        pixel = finite(anchor.get("pixel"), f"{name}.anchors[{i}].pixel")
        value = finite(anchor.get("value"), f"{name}.anchors[{i}].value")
        if scale == "log" and value <= 0:
            raise PartialError(f"{name} log anchor values must be positive")
        q = math.log(value) if scale == "log" else value
        rows.append((pixel, value, q))
    if len({r[0] for r in rows}) < 2 or len({r[2] for r in rows}) < 2:
        raise PartialError(f"{name} anchors have degenerate pixels or values")
    n = len(rows)
    mean_p = sum(r[0] for r in rows) / n
    mean_q = sum(r[2] for r in rows) / n
    denom = sum((r[0] - mean_p) ** 2 for r in rows)
    slope = sum((r[0] - mean_p) * (r[2] - mean_q) for r in rows) / denom
    intercept = mean_q - slope * mean_p
    residuals = []
    for i, (pixel, value, q) in enumerate(rows):
        predicted = math.exp(slope * pixel + intercept) if scale == "log" else slope * pixel + intercept
        residuals.append({"anchor_index": i, "pixel": pixel, "paper_value": value,
                          "fitted_value": predicted, "residual": value - predicted})
    return {"name": axis.get("name", name), "paper_unit": axis.get("paper_unit"),
            "pixel_scale": scale, "slope_q_per_pixel": slope, "intercept_q": intercept,
            "anchors": anchors, "anchor_residuals": residuals}


def pixel_to_value(pixel: float, fit: dict) -> float:
    q = fit["slope_q_per_pixel"] * pixel + fit["intercept_q"]
    if fit["pixel_scale"] == "log":
        if q > 709:
            raise PartialError("log-axis conversion overflow")
        return math.exp(q)
    return q


def pixel_uncertainty(value: float, fit: dict, pixels: float) -> dict:
    if fit["pixel_scale"] == "log":
        converted = abs(value * fit["slope_q_per_pixel"]) * pixels
        method = "first_order_log_propagation"
    else:
        converted = abs(fit["slope_q_per_pixel"]) * pixels
        method = "linear_propagation"
    return {"pixel": pixels, "converted": converted, "method": method}


def load_paper(spec: dict, spec_dir: Path, figure: dict) -> tuple[dict, dict]:
    xfit = fit_axis(spec.get("axes", {}).get("x", {}), "x")
    yfit = fit_axis(spec.get("axes", {}).get("y", {}), "y")
    fits = {"x": xfit, "y": yfit}
    converted: dict[str, list] = {}
    ledger_points: dict[str, list] = {}
    wanted = {s["id"]: s for s in spec.get("series", [])}
    for spec_series in spec.get("series", []):
        sid = spec_series.get("id")
        if not sid or "points_file" not in spec_series:
            raise PartialError("each paper series needs id and points_file")
        source_path = resolve(spec_dir, spec_series["points_file"])
        data = load_json(source_path)
        records = data.get("series") if isinstance(data, dict) else data
        match = [s for s in records or [] if s.get("id") == sid]
        if len(match) != 1:
            raise PartialError(f"paper series {sid} missing or duplicated in {source_path}")
        out, ledger = [], []
        for i, point in enumerate(match[0].get("points", [])):
            label = f"{sid}.points[{i}]"
            if point.get("value_status") != "digitized":
                raise PartialError(f"{label} must explicitly be digitized, not paper-reported")
            source = point.get("source") or {}
            uncertainty = point.get("uncertainty") or {}
            for key in ("figure", "page", "panel", "source_file", "locator"):
                if key not in source:
                    raise PartialError(f"{label} source lacks {key}")
            for key in ("figure", "page", "panel"):
                if source[key] != figure.get(key):
                    raise PartialError(f"{label} source {key} disagrees with figure metadata")
            if Path(str(source["source_file"])).name != Path(str(figure["source_file"])).name:
                raise PartialError(f"{label} source_file disagrees with figure")
            ux = finite(uncertainty.get("pixel_x"), f"{label}.uncertainty.pixel_x")
            uy = finite(uncertainty.get("pixel_y"), f"{label}.uncertainty.pixel_y")
            if ux < 0 or uy < 0 or uncertainty.get("method") != "manual_pixel_click":
                raise PartialError(f"{label} uncertainty must be nonnegative and manual_pixel_click")
            px = finite(point.get("pixel_x"), f"{label}.pixel_x")
            py = finite(point.get("pixel_y"), f"{label}.pixel_y")
            x = pixel_to_value(px, xfit)
            y = pixel_to_value(py, yfit)
            if not math.isfinite(x) or not math.isfinite(y) or (xfit["pixel_scale"] == "log" and x <= 0) or (yfit["pixel_scale"] == "log" and y <= 0):
                raise PartialError(f"{label} converts outside the finite axis domain")
            out.append({"x": x, "y": y, "pixel_x": px, "pixel_y": py})
            ledger.append({"point_index": i, "pixel": {"x": px, "y": py}, "value": {"x": x, "y": y},
                           "source": source, "value_status": "digitized",
                           "uncertainty": {"x": pixel_uncertainty(x, xfit, ux),
                                           "y": pixel_uncertainty(y, yfit, uy)}})
        if len(out) < 2:
            raise PartialError(f"paper series {sid} needs at least two points")
        out.sort(key=lambda p: p["x"])
        if any(b["x"] <= a["x"] for a, b in zip(out, out[1:])):
            raise PartialError(f"paper series {sid} has duplicate/non-increasing converted x values")
        converted[sid] = out
        ledger_points[sid] = ledger
    if not converted:
        raise PartialError("no paper series supplied; cannot invent points")
    return converted, {"axes": fits, "paper_series": ledger_points, "definitions": wanted}


def candidate_json(path: Path) -> list[dict]:
    data = load_json(path)
    raw = data.get("series") if isinstance(data, dict) else data
    if not isinstance(raw, list):
        raise PartialError(f"candidate JSON {path} needs a series array")
    result = []
    for series in raw:
        points = [{"x": finite(p.get("x"), "candidate x"), "y": finite(p.get("y"), "candidate y")}
                  for p in series.get("points", [])]
        result.append({"id": series.get("id"), "unit": series.get("unit"),
                       "x_definition": series.get("x_definition"), "points": points,
                       "source": series.get("source", {})})
    return result


def candidate_csv(path: Path) -> list[dict]:
    grouped: dict[str, dict] = {}
    try:
        with path.open("r", encoding="utf-8", newline="") as f:
            for i, row in enumerate(csv.DictReader(f), start=2):
                sid = row.get("series_id")
                if not sid:
                    raise PartialError(f"{path}:{i} lacks series_id")
                item = grouped.setdefault(sid, {"id": sid, "unit": row.get("unit"),
                                                "x_definition": row.get("x_definition"), "points": [],
                                                "source": {"file_row_first": i}})
                if item["unit"] != row.get("unit") or item["x_definition"] != row.get("x_definition"):
                    raise PartialError(f"{path}:{i} inconsistent unit or x_definition")
                item["points"].append({"x": finite(float(row["x"]), f"{path}:{i} x"),
                                       "y": finite(float(row["y"]), f"{path}:{i} y")})
    except (OSError, KeyError, ValueError) as exc:
        raise PartialError(f"invalid candidate CSV {path}: {exc}") from exc
    return list(grouped.values())


def load_candidate(path: Path) -> dict[str, dict]:
    series = candidate_csv(path) if path.suffix.lower() == ".csv" else candidate_json(path)
    result = {}
    for item in series:
        sid = item.get("id")
        if not sid or sid in result:
            raise PartialError(f"candidate {path} has missing/duplicate series id {sid}")
        item["points"].sort(key=lambda p: p["x"])
        xs = [p["x"] for p in item["points"]]
        if len(xs) < 2 or any(b <= a for a, b in zip(xs, xs[1:])):
            raise PartialError(f"candidate series {sid} x values must be unique; duplicates cannot be ordered")
        if not item.get("unit") or not item.get("x_definition"):
            raise PartialError(f"candidate series {sid} lacks unit/x_definition")
        result[sid] = item
    return result


def interpolate(points: list[dict], x: float) -> float:
    if x == points[-1]["x"]:
        return points[-1]["y"]
    lo, hi = 0, len(points) - 1
    while hi - lo > 1:
        mid = (lo + hi) // 2
        if points[mid]["x"] <= x:
            lo = mid
        else:
            hi = mid
    a, b = points[lo], points[hi]
    return a["y"] + (b["y"] - a["y"]) * (x - a["x"]) / (b["x"] - a["x"])


def compare_series(paper: list[dict], candidate: dict) -> dict:
    cpoints = candidate["points"]
    lo, hi = cpoints[0]["x"], cpoints[-1]["x"]
    overlap_lo = max(lo, min(p["x"] for p in paper))
    overlap_hi = min(hi, max(p["x"] for p in paper))
    if overlap_hi <= overlap_lo:
        raise PartialError(f"candidate {candidate['id']} and paper have no positive-width x overlap; no comparison")
    aligned = []
    for p in paper:
        if lo <= p["x"] <= hi:
            estimate = interpolate(cpoints, p["x"])
            aligned.append({"x": p["x"], "paper_y": p["y"], "candidate_y": estimate,
                            "error": estimate - p["y"], "paper_pixel": [p["pixel_x"], p["pixel_y"]]})
    if len(aligned) < 2:
        raise PartialError(f"candidate {candidate['id']} has fewer than two paper x locations in overlap")
    errors = [p["error"] for p in aligned]
    return {"overlap": {"x_min": overlap_lo, "x_max": overlap_hi, "n": len(aligned),
                        "candidate_x_min": lo, "candidate_x_max": hi, "interpolation": "linear", "extrapolation": False},
            "aligned_points": aligned,
            "metrics": {"rmse": math.sqrt(sum(e * e for e in errors) / len(errors)),
                        "mae": sum(abs(e) for e in errors) / len(errors),
                        "max_error": max(abs(e) for e in errors),
                        "signed_mean_error": sum(errors) / len(errors)}}


def esc(value: Any) -> str:
    return html.escape(str(value), quote=True)


def ticks(lo: float, hi: float, count: int = 5) -> list[float]:
    if hi <= lo:
        hi = lo + 1.0
    return [lo + (hi - lo) * i / count for i in range(count + 1)]


def bounds(series: list[tuple[list[float], list[float]]]) -> tuple[float, float, float, float]:
    xs = [x for s in series for x in s[0]]
    ys = [y for s in series for y in s[1]]
    xmin, xmax, ymin, ymax = min(xs), max(xs), min(ys), max(ys)
    if xmax == xmin:
        xmax = xmin + 1
    if ymax == ymin:
        ymax = ymin + 1
    pad = (ymax - ymin) * 0.08
    return xmin, xmax, ymin - pad, ymax + pad


def svg_line_chart(title: str, xlabel: str, ylabel: str,
                   curves: list[dict], error_mode: bool = False) -> str:
    width, height = 900, 520
    left, right, top, bottom = 80, 860, 78, 435
    series = [(c["xs"], c["ys"]) for c in curves]
    xmin, xmax, ymin, ymax = bounds(series)
    if error_mode:
        extent = max(abs(ymin), abs(ymax), 1e-12) * 1.1
        ymin, ymax = -extent, extent
    def sx(x: float) -> float:
        return left + (x - xmin) / (xmax - xmin) * (right - left)
    def sy(y: float) -> float:
        return bottom - (y - ymin) / (ymax - ymin) * (bottom - top)
    out = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">',
           '<rect width="100%" height="100%" fill="white"/>',
           f'<text x="450" y="27" text-anchor="middle" font-family="Arial,sans-serif" font-size="19" font-weight="bold">{esc(title)}</text>']
    # Legend lives in a dedicated band above the axes, never over data.
    for i, curve in enumerate(curves):
        lx = 85 + i * 390
        out.append(f'<line x1="{lx}" y1="52" x2="{lx+35}" y2="52" stroke="{curve["color"]}" stroke-width="3"/>')
        out.append(f'<text x="{lx+43}" y="57" font-family="Arial,sans-serif" font-size="14">{esc(curve["label"])}</text>')
    for value in ticks(xmin, xmax):
        x = sx(value)
        out.append(f'<line x1="{x:.2f}" y1="{top}" x2="{x:.2f}" y2="{bottom}" stroke="#e5e7eb"/>')
        out.append(f'<text x="{x:.2f}" y="{bottom+22}" text-anchor="middle" font-family="Arial,sans-serif" font-size="12">{value:.3g}</text>')
    for value in ticks(ymin, ymax):
        y = sy(value)
        out.append(f'<line x1="{left}" y1="{y:.2f}" x2="{right}" y2="{y:.2f}" stroke="#e5e7eb"/>')
        out.append(f'<text x="{left-10}" y="{y+4:.2f}" text-anchor="end" font-family="Arial,sans-serif" font-size="12">{value:.3g}</text>')
    out.append(f'<rect x="{left}" y="{top}" width="{right-left}" height="{bottom-top}" fill="none" stroke="#111827"/>')
    if error_mode and ymin < 0 < ymax:
        out.append(f'<line x1="{left}" y1="{sy(0):.2f}" x2="{right}" y2="{sy(0):.2f}" stroke="#6b7280" stroke-dasharray="5,4"/>')
    for curve in curves:
        pts = " ".join(f"{sx(x):.2f},{sy(y):.2f}" for x, y in zip(curve["xs"], curve["ys"]))
        out.append(f'<polyline points="{pts}" fill="none" stroke="{curve["color"]}" stroke-width="2.5"/>')
        if curve.get("markers"):
            for x, y in zip(curve["xs"], curve["ys"]):
                out.append(f'<circle cx="{sx(x):.2f}" cy="{sy(y):.2f}" r="4" fill="white" stroke="{curve["color"]}" stroke-width="2"/>')
    out.append(f'<text x="{(left+right)/2}" y="488" text-anchor="middle" font-family="Arial,sans-serif" font-size="15">{esc(xlabel)}</text>')
    out.append(f'<text x="20" y="{(top+bottom)/2}" text-anchor="middle" transform="rotate(-90 20 {(top+bottom)/2})" font-family="Arial,sans-serif" font-size="15">{esc(ylabel)}</text>')
    out.append('</svg>')
    return "\n".join(out) + "\n"


def safe_id(value: str) -> str:
    cleaned = "".join(c if c.isalnum() or c in "-_" else "_" for c in value)
    if not cleaned:
        raise PartialError("empty series id")
    return cleaned


def render_svgs(output: Path, comparisons: list[dict], figure_file: Path) -> list[str]:
    made = []
    overlays = []
    for comp in comparisons:
        pair = comp["pair_id"]
        paper = comp["aligned_points"]
        pxs = [p["x"] for p in paper]
        pys = [p["paper_y"] for p in paper]
        cys = [p["candidate_y"] for p in paper]
        errors = [p["error"] for p in paper]
        xlabel = f'{comp["x_definition"]} ({comp.get("x_unit") or "paper x unit"})'
        ylabel = f'y ({comp["unit"]}); signed error = candidate - paper'
        overlay = svg_line_chart(f'Overlay: {comp["candidate_id"]} vs {comp["paper_series_id"]}', xlabel,
                                 f'y ({comp["unit"]})', [
            {"label": "Paper (manual pixels)", "xs": pxs, "ys": pys, "color": "#111827", "markers": True},
            {"label": comp["candidate_id"] + " (interpolated)", "xs": pxs, "ys": cys, "color": "#2563eb"}])
        error = svg_line_chart(f'Error curve: {comp["candidate_id"]}', xlabel, ylabel,
                               [{"label": "candidate - paper", "xs": pxs, "ys": errors,
                                 "color": "#dc2626", "markers": True}], error_mode=True)
        for suffix, text in (("overlay.svg", overlay), ("error.svg", error)):
            name = f"{pair}_{suffix}"
            (output / name).write_text(text, encoding="utf-8")
            made.append(name)
        overlays.append(f"{pair}_overlay.svg")
    # Both images are links: no base64 and no copied binary in the Skill.
    left_href = figure_file.as_uri()
    cards = []
    for i, overlay in enumerate(overlays):
        y = 45 + i * 520
        cards.append(f'<text x="25" y="{y-15}" font-family="Arial,sans-serif" font-size="17">Source figure (linked, not auto-recognized)</text>')
        cards.append(f'<image x="20" y="{y}" width="760" height="475" preserveAspectRatio="xMidYMid meet" href="{esc(left_href)}"/>')
        cards.append(f'<image x="810" y="{y}" width="780" height="475" href="{esc(overlay)}"/>')
    height = max(565, 45 + len(overlays) * 520)
    side = [f'<svg xmlns="http://www.w3.org/2000/svg" width="1600" height="{height}" viewBox="0 0 1600 {height}">',
            '<rect width="100%" height="100%" fill="white"/>',
            '<text x="800" y="23" text-anchor="middle" font-family="Arial,sans-serif" font-size="20" font-weight="bold">Side-by-side audit view</text>'] + cards + ['</svg>']
    (output / "side_by_side.svg").write_text("\n".join(side) + "\n", encoding="utf-8")
    made.append("side_by_side.svg")
    return made


def render_pngs(output: Path, comparisons: list[dict]) -> list[str]:
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError as exc:
        raise PartialError(f"matplotlib is required for real PNG rendering: {exc}") from exc
    made = []
    for comp in comparisons:
        pair = comp["pair_id"]
        points = comp["aligned_points"]
        xs = [p["x"] for p in points]
        paper = [p["paper_y"] for p in points]
        candidate = [p["candidate_y"] for p in points]
        errors = [p["error"] for p in points]
        fig, ax = plt.subplots(figsize=(9, 5.2), constrained_layout=True)
        ax.plot(xs, paper, "ko-", label="Paper (manual pixels)", markersize=4)
        ax.plot(xs, candidate, "-", color="#2563eb", linewidth=2, label=comp["candidate_id"] + " (interpolated)")
        ax.set(title=f'Overlay: {comp["candidate_id"]} vs paper', xlabel=comp["x_definition"], ylabel=f'y ({comp["unit"]})')
        ax.grid(alpha=0.25)
        ax.legend(loc="best")
        fig.savefig(output / f"{pair}_overlay.png", dpi=150)
        plt.close(fig)
        made.append(f"{pair}_overlay.png")
        fig, ax = plt.subplots(figsize=(9, 5.2), constrained_layout=True)
        ax.axhline(0, color="#6b7280", linestyle="--", linewidth=1)
        ax.plot(xs, errors, "o-", color="#dc2626", label="candidate - paper")
        ax.set(title=f'Error curve: {comp["candidate_id"]}', xlabel=comp["x_definition"],
               ylabel=f'signed error ({comp["unit"]})')
        ax.grid(alpha=0.25)
        ax.legend(loc="best")
        fig.savefig(output / f"{pair}_error.png", dpi=150)
        plt.close(fig)
        made.append(f"{pair}_error.png")
    n = len(comparisons)
    fig, axes = plt.subplots(n, 2, figsize=(15, 4.5 * n), squeeze=False, constrained_layout=True)
    for row, comp in enumerate(comparisons):
        points = comp["aligned_points"]
        xs = [p["x"] for p in points]
        paper = [p["paper_y"] for p in points]
        candidate = [p["candidate_y"] for p in points]
        # Left is the calibrated paper sample, not a claimed rasterization of an SVG/PDF.
        axes[row][0].plot(xs, paper, "ko-", label="manual digitized points")
        axes[row][0].set(title="Paper series after anchor calibration", xlabel=comp["x_definition"], ylabel=f'y ({comp["unit"]})')
        axes[row][0].grid(alpha=0.25)
        axes[row][0].legend(loc="best")
        axes[row][1].plot(xs, paper, "ko-", label="paper")
        axes[row][1].plot(xs, candidate, color="#2563eb", label=comp["candidate_id"])
        axes[row][1].set(title="Numeric candidate overlay", xlabel=comp["x_definition"], ylabel=f'y ({comp["unit"]})')
        axes[row][1].grid(alpha=0.25)
        axes[row][1].legend(loc="best")
    fig.savefig(output / "side_by_side.png", dpi=150)
    plt.close(fig)
    made.append("side_by_side.png")
    return made


def require_output_file(output: Path, relative: Any, label: str) -> Path:
    if not isinstance(relative, str) or not relative or Path(relative).is_absolute():
        raise PartialError(f"{label} must be a nonempty path relative to output")
    path = (output / relative).resolve()
    try:
        path.relative_to(output.resolve())
    except ValueError as exc:
        raise PartialError(f"{label} escapes output: {relative}") from exc
    if not path.is_file() or path.stat().st_size == 0:
        raise PartialError(f"declared delivery is missing or empty: {relative}")
    return path


def audit_delivery(output: Path, result: dict, figures: list[str]) -> None:
    for field in BASE_FIELDS:
        if field not in result:
            raise PartialError(f"result lacks base field {field}")
    for field in ("comparison", "mapping", "report"):
        require_output_file(output, result.get(field), f"result.{field}")
    for name in figures:
        path = require_output_file(output, name, "figure artifact")
        if path.suffix.lower() == ".png":
            with path.open("rb") as handle:
                if handle.read(8) != b"\x89PNG\r\n\x1a\n":
                    raise PartialError(f"not a real PNG: {name}")
    load_json(output / "comparison.json")
    load_json(output / "mapping.json")
    if not (output / "report.md").read_text(encoding="utf-8").strip():
        raise PartialError("report.md is empty")


def compare(args: argparse.Namespace) -> int:
    started = time.monotonic()
    case_path = args.case.resolve()
    output = args.output.resolve()
    work = args.work.resolve()
    output.mkdir(parents=True, exist_ok=True)
    work.mkdir(parents=True, exist_ok=True)
    case = load_json(case_path)
    if not isinstance(case, dict):
        raise PartialError("case.json must be a JSON object")
    case_id = case.get("case_id")
    if not case_id:
        raise PartialError("case.json lacks case_id")
    fields = extract_contract_fields(case.get("output_contract"))
    if not args.spec and not case.get("spec"):
        raise PartialError("case.json lacks spec and --spec was not supplied")
    spec_path = args.spec.resolve() if args.spec else resolve(case_path.parent, case["spec"])
    spec = load_json(spec_path)
    if not isinstance(spec, dict):
        raise PartialError("comparison spec must be a JSON object")
    contract_values(spec)
    spec_dir = spec_path.parent
    tolerances = spec.get("tolerances", {})
    if tolerances.get("declared_before_comparison") is not True:
        raise PartialError("tolerances must be declared before comparison")
    for metric in ("rmse", "mae", "max_error"):
        finite(tolerances.get(metric), f"tolerance {metric}")
        if tolerances[metric] < 0:
            raise PartialError("tolerances cannot be negative")
    figure = spec.get("figure", {})
    for key in ("source_file", "source_locator", "figure", "page", "panel"):
        if key not in figure:
            raise PartialError(f"figure metadata lacks {key}")
    figure_file = resolve(spec_dir, figure["source_file"])
    if not figure_file.is_file():
        raise PartialError(f"source figure missing: {figure_file}; no points may be invented")
    paper, mapping = load_paper(spec, spec_dir, figure)
    candidate_data: dict[str, dict] = {}
    run_records = []
    for candidate in case.get("candidates", []):
        cid = candidate.get("id")
        raw_command = candidate.get("command")
        if not cid or not isinstance(raw_command, list) or not raw_command:
            raise PartialError("every candidate needs id and argv command")
        replacements = {"work": str(work), "output": str(output), "case_dir": str(case_path.parent),
                        "spec_dir": str(spec_dir)}
        command = []
        for part in raw_command:
            expanded = str(part)
            for key, value in replacements.items():
                expanded = expanded.replace("{" + key + "}", value)
            command.append(expanded)
        output_value = str(candidate.get("output", ""))
        for key, value in replacements.items():
            output_value = output_value.replace("{" + key + "}", value)
        cwd = resolve(case_path.parent, candidate.get("cwd", "."))
        run_started = time.monotonic()
        requested_timeout = finite(candidate.get("timeout_seconds", case.get("timeout_seconds", 120)), f"{cid} timeout")
        remaining = 900.0 - (run_started - started)
        if requested_timeout <= 0 or remaining <= 0:
            raise PartialError(f"candidate {cid} has no positive execution budget")
        try:
            proc = subprocess.run(command, cwd=cwd, capture_output=True, text=True,
                                  timeout=min(requested_timeout, remaining), check=False)
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise PartialError(f"candidate {cid} could not run: {exc}") from exc
        run_record = {"candidate_id": cid, "label": candidate.get("label", cid), "argv": command,
                      "shell_command_for_audit": shlex.join(command), "cwd": output_relative(cwd, output), "exit_code": proc.returncode,
                      "elapsed_seconds": time.monotonic() - run_started, "stdout": proc.stdout[-8000:],
                      "stderr": proc.stderr[-8000:],
                      "implementation_provenance": candidate.get("implementation_provenance", "unspecified")}
        run_records.append(run_record)
        (work / f"{safe_id(cid)}.stdout.txt").write_text(proc.stdout, encoding="utf-8")
        (work / f"{safe_id(cid)}.stderr.txt").write_text(proc.stderr, encoding="utf-8")
        if proc.returncode != 0:
            raise PartialError(f"candidate {cid} exited {proc.returncode}")
        candidate_path = resolve(case_path.parent, output_value)
        if not candidate_path.is_file():
            raise PartialError(f"candidate {cid} produced no {candidate_path}")
        candidate_hash = sha256(candidate_path)
        run_record["output_path"] = output_relative(candidate_path, output)
        run_record["output_sha256"] = candidate_hash
        candidate_data[cid] = {"path": candidate_path, "sha256": candidate_hash,
                               "series": load_candidate(candidate_path)}
    comparisons = []
    for paper_spec in spec.get("series", []):
        sid = paper_spec["id"]
        for link in paper_spec.get("candidate_series", []):
            cid, csid = link.get("candidate_id"), link.get("series_id")
            if cid not in candidate_data:
                raise PartialError(f"no candidate run for {cid}")
            cseries = candidate_data[cid]["series"].get(csid)
            if cseries is None:
                raise PartialError(f"candidate series missing: {cid}/{csid}")
            unit, xdef = paper_spec.get("unit"), paper_spec.get("x_definition")
            if not unit or unit != spec["axes"]["y"].get("paper_unit") or tolerances.get("unit") != unit:
                raise PartialError(f"paper/y-axis/tolerance units disagree for {sid}; refusing implicit conversion")
            if link.get("unit") != unit or link.get("x_definition") != xdef:
                raise PartialError(f"spec unit/x_definition mismatch for {sid}/{cid}")
            if cseries["unit"] != unit or cseries["x_definition"] != xdef:
                raise PartialError(f"candidate unit/x_definition mismatch for {sid}/{cid}; refusing implicit conversion")
            result = compare_series(paper[sid], cseries)
            passed = all(result["metrics"][m] <= tolerances[m] for m in ("rmse", "mae", "max_error"))
            comp = {"pair_id": safe_id(f"{cid}__{sid}"), "candidate_id": cid, "paper_series_id": sid,
                    "candidate_series_id": csid, "unit": unit, "x_definition": xdef,
                    "x_unit": spec["axes"]["x"].get("paper_unit"), "comparison_y": "candidate_linear_interpolation_minus_manual_digitized_paper",
                    "tolerances": {m: tolerances[m] for m in ("rmse", "mae", "max_error")},
                    "within_tolerance": passed, **result}
            comp["figure_files"] = {kind: f"{comp['pair_id']}_{kind}.svg" for kind in ("overlay", "error")}
            comparisons.append(comp)
    if not comparisons:
        raise PartialError("no candidate-paper comparisons were declared")
    figures = render_svgs(output, comparisons, figure_file)
    figures += render_pngs(output, comparisons)
    elapsed = time.monotonic() - started
    if elapsed > 900.0:
        raise PartialError(f"900-second overall budget exceeded ({elapsed:.3f}s)")
    reproduction_verdict = "pass" if all(c["within_tolerance"] for c in comparisons) else "fail"
    source_record = {"figure": {**figure, "source_file": output_relative(figure_file, output),
                                "resolved_file": output_relative(figure_file, output), "sha256": sha256(figure_file)},
                     "spec": {"path": output_relative(spec_path, output), "sha256": sha256(spec_path)},
                     "paper_digitization": "manual pixel clicks; no OCR or automatic curve detection",
                     "candidates": run_records}
    task_path = case.get("task")
    if task_path:
        task_file = resolve(case_path.parent, task_path)
        source_record["task"] = {"path": output_relative(task_file, output), "sha256": sha256(task_file)}
    for ledger_points in mapping["paper_series"].values():
        for point in ledger_points:
            declared_source = point["source"]["source_file"]
            point["source"]["source_file"] = output_relative(resolve(spec_dir, str(declared_source)), output)
    mapping.update({"version": VERSION, "case_id": case_id, "figure": source_record["figure"],
                    "candidate_series": {cid: {"path": output_relative(data["path"], output), "sha256": data["sha256"],
                                               "series": data["series"]} for cid, data in candidate_data.items()},
                    "units_and_x_definitions_checked_exactly": True, "automatic_ocr_or_curve_detection": False})
    comparison_doc = {"case_id": case_id, "status": "success", "reproduction_verdict": reproduction_verdict,
                      "tolerance_unit": tolerances.get("unit"),
                      "tolerance_source": tolerances.get("source"), "comparisons": comparisons,
                      "elapsed_seconds": elapsed}
    # Files are linked in report entries rather than substituted for numeric tables.
    table = ["| Candidate | Paper series | n | RMSE | MAE | max abs error | x overlap | Verdict |",
             "|---|---|---:|---:|---:|---:|---|---|"]
    for c in comparisons:
        m, o = c["metrics"], c["overlap"]
        table.append(f'| {c["candidate_id"]} | {c["paper_series_id"]} | {o["n"]} | {m["rmse"]:.8g} | {m["mae"]:.8g} | {m["max_error"]:.8g} | [{o["x_min"]:.6g}, {o["x_max"]:.6g}] | {"PASS" if c["within_tolerance"] else "FAIL"} |')
    runs = [f'- `{r["candidate_id"]}`: `{r["shell_command_for_audit"]}`; exit={r["exit_code"]}; {r["elapsed_seconds"]:.3f}s; provenance={r["implementation_provenance"]}' for r in run_records]
    versions = {}
    for package in ("numpy", "matplotlib"):
        try:
            versions[package] = metadata.version(package)
        except metadata.PackageNotFoundError:
            versions[package] = "not installed"
    environment = f'Python {platform.python_version()} on {platform.platform()}; numpy {versions["numpy"]}; matplotlib {versions["matplotlib"]}'
    artifacts = {"comparison": "comparison.json", "mapping": "mapping.json", "report": "report.md", "figures": figures}
    uncertainties = [{"type": "manual_digitization", "paper_series": mapping["paper_series"]},
                     {"type": "scope", "statement": "Pixel uncertainty propagation and interpolation only; not total scientific uncertainty."}]
    created = ["comparison.json", "mapping.json", "report.md", "result.json"] + figures
    values = {
        "summary": f"{len(comparisons)} pairs compared; {sum(not c['within_tolerance'] for c in comparisons)} outside tolerance",
        "artifacts": artifacts, "comparison": "comparison.json", "mapping": "mapping.json", "report": "report.md",
        "errors": [], "reproduction_verdict": reproduction_verdict,
    }
    records = [{"action": "created", "files": created}]
    result, missing_fields = assemble_result(
        case, spec, complete=True, reproduction_verdict=reproduction_verdict,
        sources=source_record, uncertainty=uncertainties,
        change_records=records, values=values, fields=fields)
    if missing_fields:
        result["errors"].append({"type": "incomplete_output_contract", "fields": missing_fields,
                                 "message": "Required contract values lack case-specific evidence in spec.contract_values."})
        result["change_records"].append({"action": "delivery_incomplete", "missing_contract_values": missing_fields})
    comparison_doc["status"] = result["status"]
    report = f'''# Paper-figure twin comparison: {case_id}

## Verdict

**Scientific reproduction verdict: {reproduction_verdict.upper()}**. **Task delivery status: {result["status"].upper()}**.
Tolerances ({tolerances.get("unit")}) were declared before comparison from: {tolerances.get("source")}.
A numeric `fail` does not make a complete run a task failure; missing materials, execution, or required delivery does.
A synthetic figure within tolerance is only numerical agreement with manual samples, **not paper reproduction** and not author-code reproduction.

## Materials and environment

- Source: `{figure["source_locator"]}`; figure/page/panel = `{figure["figure"]}` / `{figure["page"]}` / `{figure["panel"]}`.
- Linked figure: [{figure_file.name}]({figure_file.as_uri()}); SHA-256 `{sha256(figure_file)}`. Source SVG images remain links, not base64.
- Digitization: manual pixel points with per-point locator and uncertainty; no OCR, PDF pre-extracted layer, or automatic curve detection.
- {environment}; SVG generated with stdlib, PNG generated with matplotlib Agg.
- Runtime {elapsed:.3f}s; formal overall budget 900s. JSON specs and commands are authoritative parameters.

## Candidate runs (actually executed)

{chr(10).join(runs)}

## Numeric results

{chr(10).join(table)}

Errors are `linear_interpolation(candidate at paper x) - manual_digitized_paper`; no extrapolation. Full aligned values are in `comparison.json`. Anchor residuals and every pixel conversion are in `mapping.json`.

## Figures for visual inspection (not a substitute for metrics)

''' + "\n".join(f'- [{name}]({name})' for name in figures) + f'''

## Attribution and limitations

Candidate provenance is recorded per run above. Organizer-supplied runners or synthetic inputs, when present, are not paper-author code. Agreement is conditional on manual clicks, axis anchors, interpolation, overlapping x domains, identical units and identical x definitions. Uncertainty estimates convert only declared pixel uncertainty; they do not prove total experimental uncertainty. Missing figures/anchors or zero-width overlap are non-comparable, never licenses to invent data. Figures aid visual audit only and cannot replace the numerical table, commands, run records, or attributable error analysis.

Signed mean errors, where nonzero, indicate systematic offset; large max/RMSE relative to MAE suggests localized deviation or interpolation sensitivity. These are diagnostics, not proof of a causal modeling defect.
'''
    (output / "report.md").write_text(report, encoding="utf-8")
    dump_json(output / "comparison.json", comparison_doc)
    dump_json(output / "mapping.json", mapping)
    dump_json(output / "result.json", result)
    if result["status"] == "success":
        audit_delivery(output, result, figures)
        load_json(output / "result.json")
    print(json.dumps({"case_id": case_id, "status": result["status"],
                      "reproduction_verdict": reproduction_verdict, "output": "."}, ensure_ascii=False))
    if result["status"] == "partial":
        return 1
    return 0 if reproduction_verdict == "pass" else 2


def emit_synthetic_candidate(args: argparse.Namespace) -> int:
    """Example-only analytic candidate emitter; never a paper curve recognizer."""
    method_id = "a_s1" if args.method == "near" else "b_s1"
    points = []
    for i in range(17):
        x = i * 0.5
        truth = 1.0 + 0.65 * math.sin(math.pi * x / 4.0)
        y = truth + 0.03 * math.cos(math.pi * x / 2.0) if args.method == "near" else truth + 0.18 + 0.04 * x
        points.append({"x": x, "y": y})
    path = args.output.resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.suffix.lower() == ".csv":
        with path.open("w", encoding="utf-8", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(["series_id", "x", "y", "unit", "x_definition"])
            for p in points:
                writer.writerow([method_id, p["x"], p["y"], "mV", "time_since_start_s"])
    else:
        dump_json(path, {"series": [{"id": method_id, "unit": "mV", "x_definition": "time_since_start_s",
                                    "source": {"method": args.method, "provenance": "organizer synthetic analytic candidate"},
                                    "points": points}]})
    return 0


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__)
    sub = p.add_subparsers(dest="command", required=True)
    run = sub.add_parser("compare", help="run candidates and compare with explicit manual digitization")
    run.add_argument("--case", required=True, type=Path)
    run.add_argument("--spec", type=Path, help="override case.json spec path")
    run.add_argument("--work", required=True, type=Path)
    run.add_argument("--output", required=True, type=Path)
    run.set_defaults(func=compare)
    emit = sub.add_parser("emit-synthetic-candidate", help="example-only analytic method, not curve recognition")
    emit.add_argument("--method", required=True, choices=("near", "biased"))
    emit.add_argument("--output", required=True, type=Path)
    emit.set_defaults(func=emit_synthetic_candidate)
    return p


def write_failure_result(args: argparse.Namespace, message: str) -> str:
    """Best-effort dynamic result for partial/unable runs, without fabricated outputs."""
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    case_path = args.case.resolve()
    case: dict = {}
    case_readable = False
    try:
        loaded = load_json(case_path)
        if not isinstance(loaded, dict):
            raise PartialError("case.json must be a JSON object")
        case = loaded
        case_readable = True
    except Exception as case_exc:
        message = f"{message}; case is unreadable: {case_exc}"
    spec: dict = {}
    if case_readable:
        try:
            spec_value = str(args.spec) if args.spec else case.get("spec")
            if spec_value:
                spec_path = args.spec.resolve() if args.spec else resolve(case_path.parent, spec_value)
                loaded_spec = load_json(spec_path)
                if isinstance(loaded_spec, dict):
                    spec = loaded_spec
        except Exception:
            spec = {}
    errors = [{"type": "partial" if case_readable else "unable", "message": message}]
    try:
        fields = extract_contract_fields(case.get("output_contract")) if case_readable else []
    except Exception as contract_exc:
        fields = []
        errors.append({"type": "invalid_output_contract", "message": str(contract_exc)})
    try:
        contract_values(spec)
    except Exception as values_exc:
        spec = {}
        errors.append({"type": "invalid_contract_values", "message": str(values_exc)})
    sources = {"case": {"path": output_relative(case_path, output), "readable": case_readable},
               "candidates": [{"id": item.get("id"),
                               "implementation_provenance": item.get("implementation_provenance", "unspecified")}
                              for item in case.get("candidates", []) if isinstance(item, dict)]}
    values = {
        "summary": message, "artifacts": {}, "comparison": None, "mapping": None, "report": None,
        "errors": errors, "reproduction_verdict": "not_comparable",
    }
    result, _ = assemble_result(
        case, spec, complete=False, reproduction_verdict="not_comparable", sources=sources,
        uncertainty=[{"type": "incomplete_evidence", "statement": message}],
        change_records=[{"action": "withheld_complete_outputs", "reason": message}],
        values=values, fields=fields, forced_status=None if case_readable else "unable")
    dump_json(output / "result.json", result)
    return result["status"]


def main() -> int:
    args = parser().parse_args()
    try:
        return args.func(args)
    except PartialError as exc:
        status = "partial"
        if args.command == "compare":
            try:
                status = write_failure_result(args, str(exc))
            except OSError as write_exc:
                print(f"could not write partial/unable result: {write_exc}", file=sys.stderr)
        print(f"{status.upper()}: {exc}", file=sys.stderr)
        return 1
    except Exception as exc:
        message = f"Unexpected {type(exc).__name__}: {exc}"
        status = "partial"
        if args.command == "compare":
            try:
                status = write_failure_result(args, message)
            except OSError as write_exc:
                print(f"could not write partial/unable result: {write_exc}", file=sys.stderr)
        print(f"{status.upper()}: {message}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
