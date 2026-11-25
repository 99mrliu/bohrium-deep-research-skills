#!/usr/bin/env python3
"""Visual-evidence receipts, calibrated graph readback, and adaptive results.

Standard library only. This program never claims that an Agent saw an image.
"""

import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import shutil
import struct
import subprocess
import sys


class EvidenceError(Exception):
    """A deliberate, user-actionable evidence or contract failure."""


def load_json(path):
    try:
        with Path(path).open("r", encoding="utf-8") as handle:
            return json.load(handle)
    except (OSError, json.JSONDecodeError) as exc:
        raise EvidenceError(f"cannot load JSON {path}: {exc}") from exc


def write_json(path, value):
    target = Path(path)
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        temporary = target.with_name(target.name + ".tmp")
        with temporary.open("w", encoding="utf-8", newline="\n") as handle:
            json.dump(value, handle, ensure_ascii=False, indent=2, allow_nan=False)
            handle.write("\n")
        os.replace(temporary, target)
    except OSError as exc:
        raise EvidenceError(f"cannot write JSON {path}: {exc}") from exc


def file_hash(path):
    digest = hashlib.sha256()
    total = 0
    try:
        with Path(path).open("rb") as handle:
            while True:
                chunk = handle.read(1024 * 1024)
                if not chunk:
                    break
                total += len(chunk)
                digest.update(chunk)
    except OSError as exc:
        raise EvidenceError(f"cannot read evidence file {path}: {exc}") from exc
    if total == 0:
        raise EvidenceError(f"evidence file is empty: {path}")
    return digest.hexdigest(), total


def png_dimensions(path):
    try:
        with Path(path).open("rb") as handle:
            header = handle.read(24)
    except OSError as exc:
        raise EvidenceError(f"cannot open rendered PNG {path}: {exc}") from exc
    if len(header) != 24 or header[:8] != b"\x89PNG\r\n\x1a\n" or header[12:16] != b"IHDR":
        raise EvidenceError(f"not a valid PNG header: {path}")
    width, height = struct.unpack(">II", header[16:24])
    if width < 1 or height < 1:
        raise EvidenceError(f"PNG has empty dimensions: {path}")
    return width, height


def make_receipt(image, receipt, renderer, synthetic, source_pdf=None, page=None, dpi=None, command=None):
    image_path = Path(image).resolve()
    digest, size = file_hash(image_path)
    width, height = png_dimensions(image_path)
    value = {
        "schema_version": "1.0",
        "rendered": True,
        "renderer": renderer,
        "synthetic": bool(synthetic),
        "agent_image_opened": False,
        "observation_note": "Receipt verifies file integrity only; it is not an Agent visual observation.",
        "image": {
            "path": str(image_path),
            "sha256": digest,
            "bytes": size,
            "width_pixels": width,
            "height_pixels": height,
            "non_empty": True,
        },
    }
    if source_pdf is not None:
        pdf_hash, pdf_bytes = file_hash(source_pdf)
        value["source_pdf"] = {"path": str(Path(source_pdf).resolve()), "sha256": pdf_hash, "bytes": pdf_bytes}
        value["page"] = page
        value["dpi"] = dpi
        value["command"] = command
    write_json(receipt, value)
    return value


def verify_receipt(path):
    receipt = load_json(path)
    if receipt.get("rendered") is not True or receipt.get("image", {}).get("non_empty") is not True:
        raise EvidenceError("receipt does not certify rendered, non-empty image output")
    image = receipt.get("image", {})
    image_path = image.get("path")
    if not image_path:
        raise EvidenceError("receipt has no rendered image path")
    digest, size = file_hash(image_path)
    if digest != image.get("sha256") or size != image.get("bytes"):
        raise EvidenceError("rendered image hash/size differs from receipt")
    width, height = png_dimensions(image_path)
    if [width, height] != [image.get("width_pixels"), image.get("height_pixels")]:
        raise EvidenceError("rendered image dimensions differ from receipt")
    return receipt


def render_pdf(args):
    if args.page < 1 or args.dpi < 20 or args.dpi > 1200:
        raise EvidenceError("page must be >= 1 and DPI must be between 20 and 1200")
    pdf = Path(args.pdf)
    if not pdf.is_file() or pdf.stat().st_size == 0:
        raise EvidenceError(f"PDF is missing or empty: {pdf}")
    executable = shutil.which("pdftoppm")
    if not executable:
        raise EvidenceError("existing pdftoppm executable was not found")
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    base = output_dir / f"page-{args.page:04d}"
    image = base.with_suffix(".png")
    command = [executable, "-f", str(args.page), "-l", str(args.page), "-singlefile", "-r", str(args.dpi), "-png", str(pdf), str(base)]
    try:
        completed = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=300, check=False)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise EvidenceError(f"pdftoppm failed to execute: {exc}") from exc
    if completed.returncode != 0:
        raise EvidenceError(f"pdftoppm exit {completed.returncode}: {completed.stderr.strip()}")
    make_receipt(image, args.receipt, "pdftoppm", False, pdf, args.page, args.dpi, command)
    print(json.dumps({"status": "ok", "receipt": str(args.receipt), "image": str(image)}, ensure_ascii=False))


def mark_opened(args):
    receipt = verify_receipt(args.receipt)
    if receipt.get("synthetic"):
        raise EvidenceError("SYNTHETIC example receipts cannot be marked as real-case Agent observations")
    if not args.actually_opened:
        raise EvidenceError("mark-opened requires --actually-opened only after the Agent really opened the rendered image")
    if not args.observer.strip():
        raise EvidenceError("mark-opened requires a non-empty observer note")
    receipt["agent_image_opened"] = True
    receipt["observation_attestation"] = {
        "observer": args.observer,
        "statement": "Agent attests that it opened the exact hash-matched rendered image; this flag is not set by rendering.",
    }
    receipt["observation_note"] = "Explicit Agent observation attestation after image opening; retain actual visual-tool use in the run record."
    write_json(args.receipt, receipt)
    print(json.dumps({"status": "ok", "agent_image_opened": True, "image_sha256": receipt["image"]["sha256"]}))


def register_image(args):
    if not args.synthetic:
        raise EvidenceError("register-image is restricted to explicitly SYNTHETIC examples; use render-pdf for case evidence")
    receipt = make_receipt(args.image, args.receipt, "existing synthetic PNG; no PDF rendering", True)
    print(json.dumps({"status": "ok", "synthetic": True, "sha256": receipt["image"]["sha256"]}))


def finite_number(value, label):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise EvidenceError(f"{label} must be a finite number")
    return float(value)


def residual_threshold(calibration):
    if "max_residual_data_units" not in calibration:
        raise EvidenceError("calibration requires max_residual_data_units")
    threshold = finite_number(calibration["max_residual_data_units"], "max_residual_data_units")
    if threshold < 0:
        raise EvidenceError("max_residual_data_units must be non-negative")
    return threshold


def fit_axis(name, axis):
    scale = axis.get("scale", "linear")
    if scale not in ("linear", "log"):
        raise EvidenceError(f"{name}: scale must be linear or log")
    points = axis.get("points")
    if not isinstance(points, list) or len(points) < 2:
        raise EvidenceError(f"{name}: at least two calibration points are required")
    base = finite_number(axis.get("base", 10), f"{name}.base")
    if scale == "log" and base <= 1:
        raise EvidenceError(f"{name}: logarithm base must be > 1")
    pixels, values = [], []
    for index, point in enumerate(points):
        if not isinstance(point, dict):
            raise EvidenceError(f"{name}: calibration point {index} is not an object")
        pixels.append(finite_number(point.get("pixel"), f"{name}.points[{index}].pixel"))
        value = finite_number(point.get("value"), f"{name}.points[{index}].value")
        if scale == "log" and value <= 0:
            raise EvidenceError(f"{name}: log calibration values must be positive")
        values.append(value)
    mean_pixel = sum(pixels) / len(pixels)
    denominator = sum((pixel - mean_pixel) ** 2 for pixel in pixels)
    if denominator <= 1e-12:
        raise EvidenceError(f"{name}: degenerate calibration; pixels are duplicate or collinear in 1D")
    transformed = [math.log(value, base) for value in values] if scale == "log" else values
    mean_transformed = sum(transformed) / len(transformed)
    slope = sum((p - mean_pixel) * (v - mean_transformed) for p, v in zip(pixels, transformed)) / denominator
    intercept = mean_transformed - slope * mean_pixel

    def forward(pixel):
        transformed_value = slope * pixel + intercept
        return base ** transformed_value if scale == "log" else transformed_value

    fitted = [forward(pixel) for pixel in pixels]
    residuals = [actual - prediction for actual, prediction in zip(values, fitted)]
    transformed_fitted = [slope * pixel + intercept for pixel in pixels]
    transformed_residuals = [actual - prediction for actual, prediction in zip(transformed, transformed_fitted)]
    max_residual = max(abs(value) for value in residuals)
    threshold = residual_threshold(axis)
    if max_residual > threshold:
        raise EvidenceError(f"{name}: calibration residual {max_residual:.8g} exceeds {threshold:.8g} data units")
    return {
        "axis": name,
        "scale": scale,
        "base": base if scale == "log" else None,
        "units": axis.get("units"),
        "model": "value = base ** (a * pixel + b)" if scale == "log" else "value = a * pixel + b",
        "a_transformed": slope,
        "b_transformed": intercept,
        "points": [
            {"pixel": p, "value": v, "fitted_value": f, "residual_data_units": r}
            for p, v, f, r in zip(pixels, values, fitted, residuals)
        ],
        "max_abs_residual_data_units": max_residual,
        "rms_residual_data_units": math.sqrt(sum(r * r for r in residuals) / len(residuals)),
        "max_abs_residual_transformed": max(abs(r) for r in transformed_residuals),
        "max_allowed_residual_data_units": threshold,
    }, forward, slope


def solve_three(matrix, vector):
    augmented = [list(map(float, row)) + [float(value)] for row, value in zip(matrix, vector)]
    for column in range(3):
        pivot = max(range(column, 3), key=lambda row: abs(augmented[row][column]))
        if abs(augmented[pivot][column]) <= 1e-10:
            raise EvidenceError("affine2d: degenerate/collinear calibration controls")
        augmented[column], augmented[pivot] = augmented[pivot], augmented[column]
        divisor = augmented[column][column]
        augmented[column] = [value / divisor for value in augmented[column]]
        for row in range(3):
            if row == column:
                continue
            factor = augmented[row][column]
            augmented[row] = [a - factor * b for a, b in zip(augmented[row], augmented[column])]
    return [augmented[row][3] for row in range(3)]


def fit_affine2d(calibration):
    controls = calibration.get("points")
    if not isinstance(controls, list) or len(controls) < 3:
        raise EvidenceError("affine2d: at least three non-collinear controls are required")
    pixels, values = [], []
    for index, control in enumerate(controls):
        pixel, value = control.get("pixel"), control.get("value")
        if not isinstance(pixel, list) or len(pixel) != 2 or not isinstance(value, list) or len(value) != 2:
            raise EvidenceError(f"affine2d control {index} needs two pixel and two value coordinates")
        pixels.append([finite_number(pixel[0], "pixel.x"), finite_number(pixel[1], "pixel.y")])
        values.append([finite_number(value[0], "value.x"), finite_number(value[1], "value.y")])
    rows = [[pixel[0], pixel[1], 1.0] for pixel in pixels]
    normal = [[sum(row[i] * row[j] for row in rows) for j in range(3)] for i in range(3)]
    coefficients = []
    for dimension in range(2):
        rhs = [sum(row[i] * value[dimension] for row, value in zip(rows, values)) for i in range(3)]
        coefficients.append(solve_three(normal, rhs))

    def forward(pixel):
        return [coefficients[d][0] * pixel[0] + coefficients[d][1] * pixel[1] + coefficients[d][2] for d in range(2)]

    fitted = [forward(pixel) for pixel in pixels]
    residuals = [[actual[d] - prediction[d] for d in range(2)] for actual, prediction in zip(values, fitted)]
    maxima = [max(abs(residual[d]) for residual in residuals) for d in range(2)]
    threshold = residual_threshold(calibration)
    if max(maxima) > threshold:
        raise EvidenceError(f"affine2d calibration residual {max(maxima):.8g} exceeds {threshold:.8g}")
    model = {
        "mode": "affine2d",
        "coefficients": coefficients,
        "points": [
            {"pixel": p, "value": v, "fitted_value": f, "residual_data_units": r}
            for p, v, f, r in zip(pixels, values, fitted, residuals)
        ],
        "max_abs_residual_data_units": maxima,
        "max_allowed_residual_data_units": threshold,
    }
    return model, forward


def point_pixel(point, label):
    pixel = point.get("pixel")
    if not isinstance(pixel, list) or len(pixel) != 2:
        raise EvidenceError(f"{label}: pixel must be [x, y]")
    return [finite_number(pixel[0], f"{label}.pixel.x"), finite_number(pixel[1], f"{label}.pixel.y")]


def point_sigma(point, label):
    sigma = point.get("pixel_sigma", [0.5, 0.5])
    if not isinstance(sigma, list) or len(sigma) != 2:
        raise EvidenceError(f"{label}: pixel_sigma must be [x, y]")
    result = [finite_number(sigma[0], "sigma.x"), finite_number(sigma[1], "sigma.y")]
    if min(result) < 0:
        raise EvidenceError(f"{label}: pixel_sigma cannot be negative")
    return result


def compute_readback(receipt, measurement):
    if not isinstance(measurement, dict) or measurement.get("schema_version") != "1.0":
        raise EvidenceError("measurement requires schema_version 1.0")
    origin = measurement.get("measurement_origin")
    if origin not in ("agent_visual_measurement", "synthetic_programmatic_measurement"):
        raise EvidenceError("measurement_origin must disclose Agent visual or synthetic programmatic origin")
    if origin == "synthetic_programmatic_measurement" and receipt.get("synthetic") is not True:
        raise EvidenceError("synthetic measurements cannot be attached to non-synthetic evidence")
    if origin == "agent_visual_measurement":
        if receipt.get("synthetic"):
            raise EvidenceError("synthetic receipt cannot be labeled Agent visual measurement")
        if receipt.get("agent_image_opened") is not True:
            raise EvidenceError("Agent visual measurement refused: receipt does not record that the rendered image was opened")
        if not measurement.get("observer"):
            raise EvidenceError("Agent visual measurement requires an observer note")
    pixel_space = measurement.get("pixel_space", {})
    if pixel_space.get("origin") != "top_left" or pixel_space.get("units") != "pixel":
        raise EvidenceError("pixel_space must explicitly declare top_left origin and pixel units")
    points = measurement.get("points")
    if not isinstance(points, list) or not points:
        raise EvidenceError("at least one measurement point is required")
    calibration = measurement.get("calibration")
    if not isinstance(calibration, dict):
        raise EvidenceError("calibration object is required")
    results = []
    if calibration.get("mode") == "affine2d":
        calibration_result, forward = fit_affine2d(calibration)
        for index, point in enumerate(points):
            label = point.get("label", f"point-{index}")
            pixel = point_pixel(point, label)
            sigma = point_sigma(point, label)
            values = forward(pixel)
            coefficients = calibration_result["coefficients"]
            uncertainties = [math.sqrt(sum((coefficients[d][j] * sigma[j]) ** 2 for j in range(2))) for d in range(2)]
            quantization = [math.sqrt(sum((coefficients[d][j] * 0.5) ** 2 for j in range(2))) for d in range(2)]
            results.append(readback_point(point, label, pixel, values, uncertainties, quantization, ["x", "y"]))
    else:
        x_result, x_forward, x_slope = fit_axis("x", calibration.get("x", {}))
        y_result, y_forward, y_slope = fit_axis("y", calibration.get("y", {}))
        calibration_result = {"mode": "separate_axes", "x": x_result, "y": y_result}
        for index, point in enumerate(points):
            label = point.get("label", f"point-{index}")
            pixel = point_pixel(point, label)
            sigma = point_sigma(point, label)
            values = [x_forward(pixel[0]), y_forward(pixel[1])]
            x_uncertainty = abs(x_slope) * sigma[0]
            if x_result["scale"] == "log":
                x_uncertainty = abs(math.log(x_result["base"]) * values[0] * x_slope) * sigma[0]
            y_uncertainty = abs(y_slope) * sigma[1]
            if y_result["scale"] == "log":
                y_uncertainty = abs(math.log(y_result["base"]) * values[1] * y_slope) * sigma[1]
            x_quantum = abs(math.log(x_result["base"]) * values[0] * x_slope) * 0.5 if x_result["scale"] == "log" else abs(x_slope) * 0.5
            y_quantum = abs(math.log(y_result["base"]) * values[1] * y_slope) * 0.5 if y_result["scale"] == "log" else abs(y_slope) * 0.5
            results.append(readback_point(point, label, pixel, values, [x_uncertainty, y_uncertainty], [x_quantum, y_quantum], [x_result["units"] or "x", y_result["units"] or "y"]))
    return {
        "schema_version": "1.0",
        "measurement_origin": origin,
        "observer": measurement.get("observer"),
        "synthetic": receipt.get("synthetic", False),
        "image_sha256": receipt["image"]["sha256"],
        "figure": measurement.get("figure"),
        "pixel_space": pixel_space,
        "calibration": calibration_result,
        "points": results,
        "warning": "Calibrated graphical readback is an estimate, not an exact source table value.",
    }


def readback_point(point, label, pixel, values, uncertainties, quantization, units):
    return {
        "label": label,
        "pixel": pixel,
        "figure_coordinate": point.get("figure_coordinate"),
        "pixel_sigma": point.get("pixel_sigma", [0.5, 0.5]),
        "series": point.get("series"),
        "legend_label": point.get("legend_label"),
        "group": point.get("group"),
        "error_bar": point.get("error_bar"),
        "estimated_values": {unit: value for unit, value in zip(units, values)},
        "estimated_uncertainty_1sigma": {unit: value for unit, value in zip(units, uncertainties)},
        "half_pixel_quantization_equivalent": {unit: value for unit, value in zip(units, quantization)},
        "estimate_interval_1sigma": {unit: [value - error, value + error] for unit, value, error in zip(units, values, uncertainties)},
    }


def default_for_spec(spec):
    if isinstance(spec, str):
        normalized = spec.lower()
        if normalized in ("array", "list"):
            return []
        if normalized in ("object", "dict", "dictionary"):
            return {}
        if normalized in ("string", "str"):
            return ""
        if normalized in ("number", "integer", "float"):
            return None
        if normalized in ("boolean", "bool"):
            return False
        return None
    if isinstance(spec, list):
        return []
    if not isinstance(spec, dict):
        return None
    if "type" in spec:
        return default_for_spec(spec["type"])
    if "properties" in spec or "fields" in spec:
        return {}
    return {}


def contract_fields(contract):
    fields = {}
    if isinstance(contract, dict):
        for key, spec in contract.items():
            if not isinstance(key, str) or not key:
                raise EvidenceError("output_contract dictionary keys must be non-empty strings")
            fields[key] = default_for_spec(spec)
    elif isinstance(contract, list):
        for entry in contract:
            spec = None
            if isinstance(entry, str):
                key = entry
            elif isinstance(entry, dict):
                key = next((entry[name] for name in ("name", "key", "field") if isinstance(entry.get(name), str)), None)
                spec = entry
            else:
                raise EvidenceError("output_contract list entries must be strings or objects")
            if not key:
                raise EvidenceError("output_contract list object requires name, key, or field")
            fields[key] = default_for_spec(spec)
    else:
        raise EvidenceError("case.output_contract must be a dictionary or list")
    return fields


def scaffold(args):
    case = load_json(args.case)
    if not isinstance(case, dict) or not isinstance(case.get("case_id"), str) or not case["case_id"]:
        raise EvidenceError("case.json requires a non-empty case_id")
    if "output_contract" not in case:
        raise EvidenceError("case.json requires output_contract")
    target = Path(args.output)
    if target.exists() and not args.force:
        raise EvidenceError(f"refusing to overwrite existing result without --force: {target}")
    result = {"case_id": case["case_id"]}
    reserved = {"case_id", "status", "sources", "uncertainty", "change_records"}
    for key, value in contract_fields(case["output_contract"]).items():
        if key not in reserved:
            result[key] = value
    result.update({
        "status": "partial",
        "sources": [],
        "uncertainty": ["Initial skeleton: evidence review is incomplete and all claims remain unverified."],
        "change_records": [{"sequence": 0, "change": "Created adaptive partial-result skeleton before evidence review."}],
    })
    write_json(target, result)
    print(json.dumps({"status": "partial", "result": str(target), "contract_fields": list(contract_fields(case["output_contract"]))}, ensure_ascii=False))


def walk_verdicts(value, path="result"):
    if isinstance(value, dict):
        for key, child in value.items():
            child_path = f"{path}.{key}"
            if key == "verdict":
                yield child_path, child
            yield from walk_verdicts(child, child_path)
    elif isinstance(value, list):
        for index, child in enumerate(value):
            yield from walk_verdicts(child, f"{path}[{index}]")


def validate_result(args):
    case = load_json(args.case)
    result = load_json(args.result)
    if not isinstance(result, dict):
        raise EvidenceError("result must be a JSON object")
    if result.get("case_id") != case.get("case_id"):
        raise EvidenceError("result.case_id does not exactly match case.case_id")
    required = set(contract_fields(case.get("output_contract"))) | {"case_id", "status", "sources", "uncertainty", "change_records"}
    missing = sorted(required - set(result))
    if missing:
        raise EvidenceError(f"result misses required fields: {', '.join(missing)}")
    if result.get("status") not in ("partial", "complete", "failed"):
        raise EvidenceError("result.status must be partial, complete, or failed")
    for field in ("sources", "uncertainty", "change_records"):
        if not isinstance(result.get(field), list):
            raise EvidenceError(f"result.{field} must be a list")
    allowed = {"supported", "partially_supported", "contradicted", "insufficient_evidence"}
    for path, verdict in walk_verdicts(result):
        if verdict not in allowed:
            raise EvidenceError(f"invalid verdict at {path}: {verdict!r}")
    assessments = result.get("claim_assessments")
    if isinstance(assessments, list):
        identifiers = set()
        for index, item in enumerate(assessments):
            if not isinstance(item, dict) or not item.get("claim_id") or "verdict" not in item:
                raise EvidenceError(f"claim_assessments[{index}] requires claim_id and verdict")
            if item["claim_id"] in identifiers:
                raise EvidenceError(f"duplicate claim assessment: {item['claim_id']}")
            identifiers.add(item["claim_id"])
            if item.get("verification_complete") is False and result.get("status") == "complete":
                raise EvidenceError("complete status conflicts with an incomplete claim assessment")
    output = {"valid": True, "case_id": result["case_id"], "status": result["status"], "required_fields": sorted(required)}
    if args.output:
        write_json(args.output, output)
    print(json.dumps(output, ensure_ascii=False))


def build_parser():
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    render = subparsers.add_parser("render-pdf", help="really render one PDF page using existing pdftoppm")
    render.add_argument("--pdf", required=True)
    render.add_argument("--page", type=int, required=True)
    render.add_argument("--dpi", type=int, default=250)
    render.add_argument("--output-dir", required=True)
    render.add_argument("--receipt", required=True)
    render.set_defaults(function=render_pdf)
    opened = subparsers.add_parser("mark-opened", help="attest actual Agent image opening after visual-tool use")
    opened.add_argument("--receipt", required=True)
    opened.add_argument("--observer", required=True)
    opened.add_argument("--actually-opened", action="store_true")
    opened.set_defaults(function=mark_opened)
    register = subparsers.add_parser("register-image", help="hash an explicitly SYNTHETIC generated PNG")
    register.add_argument("--image", required=True)
    register.add_argument("--receipt", required=True)
    register.add_argument("--synthetic", action="store_true")
    register.set_defaults(function=register_image)
    readback_parser = subparsers.add_parser("readback", help="recompute graphical values from calibration controls")
    readback_parser.add_argument("--receipt", required=True)
    readback_parser.add_argument("--measurement", required=True)
    readback_parser.add_argument("--output", required=True)
    readback_parser.set_defaults(function=lambda args: (write_json(args.output, compute_readback(verify_receipt(args.receipt), load_json(args.measurement))), print(json.dumps({"status": "ok", "output": args.output}))))
    scaffold_parser = subparsers.add_parser("scaffold", help="create an early adaptive partial result")
    scaffold_parser.add_argument("--case", required=True)
    scaffold_parser.add_argument("--output", required=True)
    scaffold_parser.add_argument("--force", action="store_true")
    scaffold_parser.set_defaults(function=scaffold)
    validate = subparsers.add_parser("validate-result", help="validate the adaptive output contract")
    validate.add_argument("--case", required=True)
    validate.add_argument("--result", required=True)
    validate.add_argument("--output")
    validate.set_defaults(function=validate_result)
    return parser


def main(argv=None):
    args = build_parser().parse_args(argv)
    try:
        args.function(args)
    except EvidenceError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    except (OSError, KeyError, TypeError, ValueError, OverflowError) as exc:
        print(f"ERROR: evidence processing failed: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
