#!/usr/bin/env python3
""" specification-driven independent numeric oracle checks using stdlib only. """
from __future__ import annotations

import argparse
import datetime as dt
import decimal
import hashlib
import hmac
import json
import math
import os
from pathlib import Path
import platform
import re
import signal
import subprocess
import sys
import time
from typing import Any

from decimal import Decimal, localcontext

VERSION = "1.1.0"
HASH_RE = re.compile(r"^[0-9a-f]{64}$")
PLACEHOLDER_RE = re.compile(r"\{([A-Za-z_][A-Za-z0-9_]*)\}")
RESULT_STATUSES = frozenset({"success", "partial", "unable", "refused"})
REQUIRED_RESULT_FIELDS = frozenset({"case_id", "status", "sources", "uncertainty", "change_records"})


class SpecError(ValueError):
    pass


def utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat()


def decimal_text(value: Decimal) -> str:
    return format(value, "g")


def json_default(value: Any) -> Any:
    if isinstance(value, Decimal):
        return decimal_text(value)
    if isinstance(value, Path):
        return str(value)
    raise TypeError(f"not JSON serializable: {type(value).__name__}")


def load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle, parse_float=Decimal)


def dump_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    with temporary.open("w", encoding="utf-8", newline="\n") as handle:
        json.dump(value, handle, ensure_ascii=False, indent=2, sort_keys=True, default=json_default)
        handle.write("\n")
    os.replace(temporary, path)


def canonical_spec(spec: dict[str, Any]) -> bytes:
    return json.dumps(
        spec, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=json_default
    ).encode("utf-8")


def spec_digest(spec: dict[str, Any]) -> str:
    return hashlib.sha256(canonical_spec(spec)).hexdigest()


def dec(value: Any, label: str) -> Decimal:
    if isinstance(value, bool) or value is None:
        raise SpecError(f"{label} must be a finite number")
    try:
        result = value if isinstance(value, Decimal) else Decimal(str(value))
    except (decimal.InvalidOperation, ValueError) as exc:
        raise SpecError(f"{label} must be a finite number") from exc
    if not result.is_finite():
        raise SpecError(f"{label} must be finite")
    return result


def require_num(value: Any, label: str) -> Decimal:
    if isinstance(value, (int, float, Decimal, str)) and not isinstance(value, bool):
        return dec(value, label)
    if isinstance(value, dict) and set(value) == {"value"}:
        return dec(value["value"], label)
    raise SpecError(f"{label} must be a number or numeric string")


def require_int(value: Any, label: str, low: int, high: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or not low <= value <= high:
        raise SpecError(f"{label} must be an integer in [{low}, {high}]")
    return value


def resolve_spec_path(spec_dir: Path, raw: str) -> Path:
    path = Path(raw)
    return path.resolve() if path.is_absolute() else (spec_dir / path).resolve()


def parse_envelope(path: Path) -> tuple[dict[str, Any], dict[str, Any], str]:
    try:
        envelope = load_json(path)
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise SpecError(f"cannot read spec {path}: {exc}") from exc
    if not isinstance(envelope, dict) or set(envelope) != {"spec_sha256", "spec"}:
        raise SpecError("spec envelope must contain exactly spec_sha256 and spec")
    digest = envelope["spec_sha256"]
    spec = envelope["spec"]
    if not isinstance(digest, str) or not HASH_RE.fullmatch(digest):
        raise SpecError("spec_sha256 must be 64 lowercase hexadecimal characters")
    if not isinstance(spec, dict):
        raise SpecError("spec must be an object")
    actual = spec_digest(spec)
    if not hmac.compare_digest(actual, digest):
        raise SpecError(f"spec hash mismatch: declared {digest}, actual {actual}")
    return envelope, spec, actual


def validate_spec(envelope_path: Path) -> tuple[dict[str, Any], str, Path]:
    _, spec, digest = parse_envelope(envelope_path)
    spec_dir = envelope_path.resolve().parent
    if spec.get("spec_version") != "1.0":
        raise SpecError("spec_version must be '1.0'")
    oracle = spec.get("oracle")
    if not isinstance(oracle, dict):
        raise SpecError("oracle must be an object")
    kind = oracle.get("type")
    if kind not in {"quadratic_roots", "brute_force_minimizer_1d"}:
        raise SpecError("oracle.type must be quadratic_roots or brute_force_minimizer_1d")
    parameters = oracle.get("parameters")
    tolerances = oracle.get("tolerances")
    if not isinstance(parameters, dict) or not isinstance(tolerances, dict):
        raise SpecError("oracle.parameters and oracle.tolerances must be objects")
    if not tolerances:
        raise SpecError("at least one pre-run tolerance is required")
    for key, value in tolerances.items():
        if key not in {
            "abs", "rel", "residual_abs", "residual_scaled",
            "objective_abs", "objective_rel", "x_abs", "x_rel",
        }:
            raise SpecError(f"unsupported tolerance {key!r}")
        if dec(value, f"tolerances.{key}") < 0:
            raise SpecError(f"tolerances.{key} cannot be negative")
    precision = require_int(parameters.get("precision"), "oracle.parameters.precision", 16, 250)
    if kind == "quadratic_roots":
        for key in ("a", "b", "c"):
            require_num(parameters.get(key), f"parameters.{key}")
        if require_num(parameters.get("a"), "parameters.a") == 0:
            raise SpecError("quadratic roots requires nonzero a")
        for key in ("abs", "rel", "residual_abs", "residual_scaled"):
            if key not in tolerances:
                raise SpecError(f"quadratic_roots requires tolerances.{key}")
        factors = oracle.get("scaling_factors")
        if not isinstance(factors, list) or not factors or len(factors) > 20:
            raise SpecError("scaling_factors must contain 1 to 20 factors")
        for index, factor in enumerate(factors):
            if require_num(factor, f"scaling_factors[{index}]") == 0:
                raise SpecError("scaling factors must be nonzero")
    else:
        coefficients = parameters.get("coefficients")
        if not isinstance(coefficients, list) or not coefficients or len(coefficients) > 30:
            raise SpecError("polynomial coefficients must contain 1 to 30 entries")
        for index, value in enumerate(coefficients):
            require_num(value, f"coefficients[{index}]")
        lower = require_num(parameters.get("lower"), "parameters.lower")
        upper = require_num(parameters.get("upper"), "parameters.upper")
        if lower >= upper:
            raise SpecError("lower must be less than upper")
        require_int(parameters.get("initial_grid_points"), "initial_grid_points", 2, 100001)
        require_int(parameters.get("refinement_rounds"), "refinement_rounds", 0, 14)
        require_int(parameters.get("local_grid_points"), "local_grid_points", 3, 1001)
        for key in ("objective_abs", "objective_rel"):
            if key not in tolerances:
                raise SpecError(f"brute_force_minimizer_1d requires tolerances.{key}")
        for key in ("initial_grid_points", "refinement_rounds", "local_grid_points"):
            require_int(parameters[key], key, 0 if key == "refinement_rounds" else 2, 100001)
    candidates = spec.get("candidates")
    if not isinstance(candidates, list) or len(candidates) < 2:
        raise SpecError("at least two candidates are required; each is independently isolated")
    identifiers: set[str] = set()
    allowed = {"spec_dir", "work_dir", "output_dir", "json_out", "a", "b", "c", "scale"}
    for index, candidate in enumerate(candidates):
        prefix = f"candidates[{index}]"
        if not isinstance(candidate, dict):
            raise SpecError(f"{prefix} must be an object")
        identifier = candidate.get("id")
        if not isinstance(identifier, str) or not re.fullmatch(r"[A-Za-z0-9_.-]+", identifier):
            raise SpecError(f"{prefix}.id has invalid characters")
        if identifier in identifiers:
            raise SpecError(f"duplicate candidate id {identifier}")
        identifiers.add(identifier)
        argv = candidate.get("argv")
        if not isinstance(argv, list) or not argv or not all(isinstance(x, str) and x for x in argv):
            raise SpecError(f"{prefix}.argv must be an explicit nonempty string array; no shell")
        for argument in argv:
            for field in PLACEHOLDER_RE.findall(argument):
                if field not in allowed:
                    raise SpecError(f"{prefix}.argv uses unknown placeholder {{{field}}}")
        timeout = candidate.get("timeout_seconds")
        if isinstance(timeout, bool) or not isinstance(timeout, (int, float, Decimal)):
            raise SpecError(f"{prefix}.timeout_seconds must be positive")
        if dec(timeout, f"{prefix}.timeout_seconds") <= 0:
            raise SpecError(f"{prefix}.timeout_seconds must be positive")
        output = candidate.get("output")
        if not isinstance(output, dict) or output.get("mode") not in {"last_json_line", "json_file"}:
            raise SpecError(f"{prefix}.output.mode must be last_json_line or json_file")
        if output["mode"] == "json_file" and not isinstance(output.get("path"), str):
            raise SpecError(f"{prefix}.output.path is required for json_file mode")
        if output["mode"] == "json_file":
            for field in PLACEHOLDER_RE.findall(output["path"]):
                if field not in allowed:
                    raise SpecError(f"{prefix}.output.path uses unknown placeholder {{{field}}}")
        if not isinstance(candidate.get("cwd", "{spec_dir}"), str):
            raise SpecError(f"{prefix}.cwd must be a string")
        if "author_code" in candidate and not isinstance(candidate["author_code"], bool):
            raise SpecError(f"{prefix}.author_code must be true or false, never a truthy string")
        if "source_path" in candidate and not isinstance(candidate["source_path"], str):
            raise SpecError(f"{prefix}.source_path must be a path string")
    for key in ("case_file", "task_file"):
        value = spec.get(key)
        if value is not None and not isinstance(value, str):
            raise SpecError(f"{key} must be a path string or null")
    materials = spec.get("paper_materials", [])
    if not isinstance(materials, list) or not all(isinstance(item, str) for item in materials):
        raise SpecError("paper_materials must be an array of paths")
    contract_values = spec.get("contract_values", {})
    if not isinstance(contract_values, dict):
        raise SpecError("contract_values must be an object")
    return spec, digest, spec_dir


def render(template: str, values: dict[str, str]) -> str:
    def replace(match: re.Match[str]) -> str:
        key = match.group(1)
        if key not in values:
            raise SpecError(f"unresolved placeholder {{{key}}}")
        return values[key]
    return PLACEHOLDER_RE.sub(replace, template)


def decimal_payload(value: Any) -> Any:
    if isinstance(value, Decimal):
        return decimal_text(value)
    if isinstance(value, list):
        return [decimal_payload(item) for item in value]
    if isinstance(value, dict):
        return {key: decimal_payload(item) for key, item in value.items()}
    return value


def close_enough(actual: Decimal, expected: Decimal, abs_tol: Decimal, rel_tol: Decimal) -> tuple[bool, Decimal, Decimal]:
    error = abs(actual - expected)
    bound = abs_tol + rel_tol * max(abs(actual), abs(expected))
    return error <= bound, error, bound


def quadratic_expected(parameters: dict[str, Any]) -> dict[str, Any]:
    precision = parameters["precision"]
    with localcontext() as context:
        context.prec = precision
        a = dec(parameters["a"], "a")
        b = dec(parameters["b"], "b")
        c = dec(parameters["c"], "c")
        discriminant = b * b - Decimal(4) * a * c
        if discriminant < 0:
            raise SpecError("this oracle supports only a nonnegative real discriminant")
        root_discriminant = discriminant.sqrt()
        if root_discriminant == 0:
            roots = [-b / (Decimal(2) * a)] * 2
        else:
            q = -(b + (root_discriminant if b >= 0 else -root_discriminant)) / Decimal(2)
            if q == 0:
                roots = [(-b + root_discriminant) / (2 * a), (-b - root_discriminant) / (2 * a)]
            else:
                roots = sorted([q / a, c / q])
        roots = [+root for root in sorted(roots)]
        return {
            "mathematical_definition": "sorted real roots of a*x^2+b*x+c=0; stable q-form in Decimal",
            "roots": roots,
            "discriminant": +discriminant,
            "precision": precision,
        }


def quadratic_residuals(root: Decimal, a: Decimal, b: Decimal, c: Decimal, precision: int) -> dict[str, Decimal]:
    with localcontext() as context:
        context.prec = precision
        absolute = abs(a * root * root + b * root + c)
        scale = abs(a) * root * root + abs(b) * abs(root) + abs(c) + Decimal(1)
        return {"absolute": +absolute, "scaled": +(absolute / scale)}


def poly_value(coefficients: list[Decimal], x: Decimal, precision: int) -> Decimal:
    with localcontext() as context:
        context.prec = precision
        value = Decimal(0)
        for coefficient in reversed(coefficients):
            value = value * x + coefficient
        return +value


def brute_force_expected(parameters: dict[str, Any]) -> dict[str, Any]:
    precision = parameters["precision"]
    coefficients = [dec(value, "coefficient") for value in parameters["coefficients"]]
    lower = dec(parameters["lower"], "lower")
    upper = dec(parameters["upper"], "upper")
    initial_n = parameters["initial_grid_points"]
    rounds = parameters["refinement_rounds"]
    local_n = parameters["local_grid_points"]
    evaluations = 0
    trajectory: list[dict[str, Any]] = []
    with localcontext() as context:
        context.prec = precision
        best_x: Decimal | None = None
        best_value: Decimal | None = None

        def scan(left: Decimal, right: Decimal, count: int, label: str) -> None:
            nonlocal best_x, best_value, evaluations
            step = (right - left) / Decimal(count - 1)
            for index in range(count):
                x = left if index == count - 1 else left + step * index
                value = poly_value(coefficients, x, precision)
                evaluations += 1
                if best_value is None or value < best_value:
                    best_x, best_value = x, value
            trajectory.append({
                "stage": label, "left": +left, "right": +right, "points": count,
                "best_x": best_x, "best_value": best_value,
            })

        scan(lower, upper, initial_n, "initial_uniform_grid")
        width = upper - lower
        for round_index in range(rounds):
            # Fixed symmetric refinement around the incumbent, never candidate code/output.
            radius = width / Decimal(max(initial_n - 1, 1) * (local_n - 1) ** round_index)
            left = max(lower, best_x - radius)
            right = min(upper, best_x + radius)
            scan(left, right, local_n, f"refinement_{round_index + 1}")
        return {
            "mathematical_definition": "best value visited by the specified deterministic polynomial grid/refinement search; not a general global-optimality proof",
            "coefficients_low_to_high": coefficients,
            "x": best_x,
            "value": best_value,
            "evaluations": evaluations,
            "precision": precision,
            "search_trajectory": trajectory,
        }


def _root_comparison_at_current_precision(payload: Any, expected_roots: list[Decimal], tolerances: dict[str, Any], precision: int,
                                          a: Decimal, b: Decimal, c: Decimal) -> dict[str, Any]:
    result: dict[str, Any] = {"passed": False, "metrics": {}, "errors": [], "residuals": [], "vieta": {}}
    if not isinstance(payload, dict) or not isinstance(payload.get("roots"), list):
        result["errors"].append("output must be an object with a roots array")
        return result
    try:
        actual = [require_num(value, f"roots[{index}]") for index, value in enumerate(payload["roots"])]
    except SpecError as exc:
        result["errors"].append(str(exc))
        return result
    result["parsed_roots"] = actual
    if len(actual) != 2:
        result["errors"].append(f"expected exactly two roots, got {len(actual)}")
        return result
    actual.sort()
    abs_tol = dec(tolerances["abs"], "abs")
    rel_tol = dec(tolerances["rel"], "rel")
    residual_abs_tol = dec(tolerances["residual_abs"], "residual_abs")
    residual_scaled_tol = dec(tolerances["residual_scaled"], "residual_scaled")
    errors: list[Decimal] = []
    bounds: list[Decimal] = []
    root_pass = True
    residual_pass = True
    for index, (observed, expected) in enumerate(zip(actual, expected_roots)):
        passed, error, bound = close_enough(observed, expected, abs_tol, rel_tol)
        errors.append(error)
        bounds.append(bound)
        root_pass = root_pass and passed
        residual = quadratic_residuals(observed, a, b, c, precision)
        residual_ok = residual["absolute"] <= residual_abs_tol and residual["scaled"] <= residual_scaled_tol
        residual_pass = residual_pass and residual_ok
        result["residuals"].append({
            "root_index": index, **residual, "passed": residual_ok,
            "absolute_bound": residual_abs_tol, "scaled_bound": residual_scaled_tol,
        })
    vieta_sum = actual[0] + actual[1]
    vieta_product = actual[0] * actual[1]
    sum_error = abs(vieta_sum + b / a)
    product_error = abs(vieta_product - c / a)
    vieta_bound = abs_tol + rel_tol * max(abs(b / a), abs(c / a), Decimal(1))
    vieta_pass = sum_error <= vieta_bound and product_error <= vieta_bound
    result["vieta"] = {
        "sum_minus_expected": sum_error, "product_minus_expected": product_error,
        "shared_bound": vieta_bound, "passed": vieta_pass,
    }
    result["metrics"] = {
        "max_root_absolute_error": max(errors), "root_error_bounds": bounds,
        "max_residual_absolute": max(item["absolute"] for item in result["residuals"]),
        "max_residual_scaled": max(item["scaled"] for item in result["residuals"]),
    }
    if not root_pass:
        result["errors"].append("at least one root exceeds the pre-run absolute/relative tolerance")
    if not residual_pass:
        result["errors"].append("at least one root residual exceeds the pre-run tolerance")
    if not vieta_pass:
        result["errors"].append("Vieta sum/product identity exceeds the pre-run tolerance")
    result["passed"] = root_pass and residual_pass and vieta_pass
    return result


def root_comparison(payload: Any, expected_roots: list[Decimal], tolerances: dict[str, Any], precision: int,
                    a: Decimal, b: Decimal, c: Decimal) -> dict[str, Any]:
    with localcontext() as context:
        context.prec = precision
        return _root_comparison_at_current_precision(payload, expected_roots, tolerances, precision, a, b, c)


def candidate_json_number(payload: dict[str, Any], key: str) -> Decimal | None:
    if key not in payload:
        return None
    try:
        return require_num(payload[key], key)
    except SpecError:
        return None


def _minimizer_comparison_at_current_precision(payload: Any, expected: dict[str, Any], parameters: dict[str, Any],
                                               tolerances: dict[str, Any]) -> dict[str, Any]:
    result: dict[str, Any] = {"passed": False, "status": "failed", "metrics": {}, "errors": []}
    if not isinstance(payload, dict) or "x" not in payload:
        result["errors"].append("output must be an object containing numeric x; optional value is rechecked, never trusted")
        return result
    try:
        x = require_num(payload["x"], "x")
    except SpecError as exc:
        result["errors"].append(str(exc))
        return result
    precision = parameters["precision"]
    coefficients = [dec(value, "coefficient") for value in parameters["coefficients"]]
    lower = dec(parameters["lower"], "lower")
    upper = dec(parameters["upper"], "upper")
    if x < lower or x > upper:
        result["errors"].append("candidate x is outside the pre-specified search interval")
        return result
    value = poly_value(coefficients, x, precision)
    expected_x = expected["x"]
    expected_value = expected["value"]
    abs_tol = dec(tolerances["objective_abs"], "objective_abs")
    rel_tol = dec(tolerances["objective_rel"], "objective_rel")
    objective_ok, objective_gap, objective_bound = close_enough(value, expected_value, abs_tol, rel_tol)
    # A lower candidate value is better, and close_enough alone must not treat it as failure.
    objective_ok = value <= expected_value + objective_bound
    x_check: dict[str, Any] = {"performed": False}
    if "x_abs" in tolerances or "x_rel" in tolerances:
        x_pass, x_error, x_bound = close_enough(
            x, expected_x, dec(tolerances.get("x_abs", 0), "x_abs"),
            dec(tolerances.get("x_rel", 0), "x_rel"),
        )
        x_check = {"performed": True, "passed": x_pass, "absolute_error": x_error, "bound": x_bound}
        objective_ok = objective_ok and x_pass
    reported_value = candidate_json_number(payload, "value")
    report_difference = None if reported_value is None else abs(reported_value - value)
    result.update({
        "actual": {"x": x, "recomputed_value": value, "reported_value": reported_value},
        "expected": {"x": expected_x, "best_sampled_value": expected_value},
        "metrics": {
            "candidate_minus_best_sampled_objective": value - expected_value,
            "objective_absolute_difference": objective_gap,
            "objective_upper_bound_for_excess": objective_bound,
            "reported_value_minus_recomputed_absolute": report_difference,
        },
        "x_check": x_check,
    })
    if value + objective_bound < expected_value:
        result["status"] = "oracle_inconclusive"
        result["errors"].append("candidate beat the sampled oracle beyond tolerance: grid missed a better point; do not label candidate wrong")
    else:
        result["passed"] = objective_ok
        if not objective_ok:
            result["errors"].append("objective and/or pre-specified x tolerance failed")
    return result


def minimizer_comparison(payload: Any, expected: dict[str, Any], parameters: dict[str, Any],
                         tolerances: dict[str, Any]) -> dict[str, Any]:
    with localcontext() as context:
        context.prec = parameters["precision"]
        return _minimizer_comparison_at_current_precision(payload, expected, parameters, tolerances)


def candidate_paper_comparison(kind: str, paper_target: Any, payload: Any, parameters: dict[str, Any],
                               tolerances: dict[str, Any]) -> dict[str, Any]:
    """Compare candidate directly with paper-like values, never substituting them for Oracle truth."""
    if paper_target is None:
        return {"status": "not_provided", "paper_target": None}
    try:
        if kind == "quadratic_roots":
            if not isinstance(paper_target, dict) or not isinstance(paper_target.get("roots"), list) or len(paper_target["roots"]) != 2:
                raise SpecError("quadratic paper target must contain exactly two roots")
            paper_roots = sorted(require_num(value, "paper root") for value in paper_target["roots"])
            a, b, c = (dec(parameters[key], key) for key in ("a", "b", "c"))
            comparison = root_comparison(payload, paper_roots, tolerances, parameters["precision"], a, b, c)
        else:
            if not isinstance(paper_target, dict) or "x" not in paper_target:
                raise SpecError("minimizer paper target must contain x and may contain value")
            paper_x = require_num(paper_target["x"], "paper x")
            if "value" in paper_target:
                paper_value = require_num(paper_target["value"], "paper value")
            else:
                coefficients = [dec(value, "coefficient") for value in parameters["coefficients"]]
                paper_value = poly_value(coefficients, paper_x, parameters["precision"])
            comparison = minimizer_comparison(payload, {"x": paper_x, "value": paper_value}, parameters, tolerances)
        return {"status": "matched" if comparison.get("passed") else "mismatched",
                "paper_target": paper_target, "comparison": comparison,
                "note": "This is candidate versus paper, separate from candidate versus independent Oracle truth."}
    except (SpecError, ArithmeticError) as exc:
        return {"status": "invalid_paper_target", "paper_target": paper_target, "error": str(exc)}


def paper_comparison(kind: str, paper_target: Any, expected: dict[str, Any], spec: dict[str, Any]) -> dict[str, Any]:
    if paper_target is None:
        return {"status": "not_provided", "paper_target": None, "oracle_mathematical_result": expected,
                "note": "No paper target is not evidence that paper and mathematics agree or disagree."}
    tolerances = spec["oracle"]["tolerances"]
    parameters = spec["oracle"]["parameters"]
    if kind == "quadratic_roots":
        a, b, c = (dec(parameters[key], key) for key in ("a", "b", "c"))
        comparison = root_comparison(paper_target, expected["roots"], tolerances, parameters["precision"], a, b, c)
        return {"status": "matched" if comparison["passed"] else "mismatched", "paper_target": paper_target,
                "oracle_mathematical_result": expected, "comparison": comparison,
                "note": "Paper agreement/disagreement is separate from either candidate's mathematical correctness."}
    synthetic_parameters = dict(parameters)
    comparison = minimizer_comparison(paper_target, expected, synthetic_parameters, tolerances)
    matched = comparison.get("passed", False)
    return {"status": "matched" if matched else "mismatched", "paper_target": paper_target,
            "oracle_mathematical_result": expected, "comparison": comparison,
            "note": "A grid-target mismatch is reported, not silently repaired to the paper value."}


def run_process(argv: list[str], cwd: Path, timeout_seconds: float, deadline: float) -> dict[str, Any]:
    started = time.monotonic()
    record: dict[str, Any] = {
        "argv": argv, "cwd": str(cwd), "started_at": utc_now(),
        "timeout_seconds_requested": timeout_seconds, "timed_out": False,
    }
    remaining = deadline - started
    if remaining <= 0:
        record.update({"exit_code": None, "stdout": "", "stderr": "", "launch_error": "900-second run budget exhausted before launch"})
        return record
    effective_timeout = min(timeout_seconds, max(remaining - 0.05, 0.001))
    record["timeout_seconds_effective"] = effective_timeout
    process: subprocess.Popen[bytes] | None = None
    try:
        process = subprocess.Popen(
            argv, cwd=str(cwd), stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            start_new_session=(os.name == "posix"), env={**os.environ, "PYTHONHASHSEED": "0"},
        )
        stdout, stderr = process.communicate(timeout=effective_timeout)
        record.update({
            "exit_code": process.returncode,
            "stdout": stdout.decode("utf-8", errors="replace"),
            "stderr": stderr.decode("utf-8", errors="replace"),
        })
    except subprocess.TimeoutExpired:
        record["timed_out"] = True
        try:
            if os.name == "posix" and process is not None:
                os.killpg(process.pid, signal.SIGKILL)
            elif process is not None:
                process.kill()
        except ProcessLookupError:
            pass
        stdout, stderr = process.communicate() if process is not None else (b"", b"")
        record.update({
            "exit_code": process.returncode if process is not None else None,
            "stdout": stdout.decode("utf-8", errors="replace"),
            "stderr": stderr.decode("utf-8", errors="replace"),
            "launch_error": "timeout; process and its process group were terminated",
        })
    except (OSError, ValueError) as exc:
        record.update({"exit_code": None, "stdout": "", "stderr": "", "launch_error": f"{type(exc).__name__}: {exc}"})
    record["duration_seconds"] = time.monotonic() - started
    record["finished_at"] = utc_now()
    return record


def parse_candidate_output(candidate: dict[str, Any], execution: dict[str, Any], values: dict[str, str], cwd: Path) -> tuple[str, Any, str | None, str | None]:
    mode = candidate["output"]["mode"]
    if mode == "last_json_line":
        lines = [line for line in execution["stdout"].splitlines() if line.strip()]
        location = "last non-empty stdout line"
        if not lines:
            return "failed", None, "stdout has no non-empty JSON line", location
        text = lines[-1]
    else:
        rendered = render(candidate["output"]["path"], values)
        output_path = Path(rendered)
        if not output_path.is_absolute():
            output_path = cwd / output_path
        output_path = output_path.resolve()
        location = str(output_path)
        try:
            text = output_path.read_text(encoding="utf-8")
        except (OSError, UnicodeError) as exc:
            return "failed", None, f"cannot read JSON output: {exc}", location
    try:
        return "parsed", json.loads(text, parse_float=Decimal), None, location
    except json.JSONDecodeError as exc:
        return "failed", None, f"JSON parse failure: {exc}", location


def expected_for_trial(spec: dict[str, Any], scale: Decimal) -> tuple[dict[str, Any], dict[str, Any]]:
    oracle = spec["oracle"]
    parameters = dict(oracle["parameters"])
    if oracle["type"] == "quadratic_roots":
        with localcontext() as context:
            context.prec = parameters["precision"]
            for key in ("a", "b", "c"):
                parameters[key] = dec(parameters[key], key) * scale
            return quadratic_expected(parameters), parameters
    return brute_force_expected(parameters), parameters


def _extend_contract_items(fields: list[str], value: Any) -> None:
    """Read field arrays or field-name -> definition mappings without adding container keys."""
    if isinstance(value, str):
        if value:
            fields.append(value)
        return
    if isinstance(value, list):
        for item in value:
            if isinstance(item, str) and item:
                fields.append(item)
            elif isinstance(item, dict):
                name = item.get("name", item.get("key"))
                if isinstance(name, str) and name:
                    fields.append(name)
        return
    if isinstance(value, dict):
        fields.extend(key for key in value if isinstance(key, str) and key)


def extract_contract_fields(case: dict[str, Any]) -> list[str]:
    """Support flat lists/mappings, fields containers, and JSON Schema object contracts."""
    contract = case.get("output_contract", {})
    fields: list[str] = []
    if isinstance(contract, list) or isinstance(contract, str):
        _extend_contract_items(fields, contract)
    elif isinstance(contract, dict):
        has_container = False
        if isinstance(contract.get("fields"), (list, dict, str)):
            has_container = True
            _extend_contract_items(fields, contract["fields"])
        if isinstance(contract.get("required_fields"), (list, dict, str)):
            has_container = True
            _extend_contract_items(fields, contract["required_fields"])
        if isinstance(contract.get("properties"), dict):
            has_container = True
            _extend_contract_items(fields, contract["properties"])
        if isinstance(contract.get("required"), (list, dict, str)):
            has_container = True
            _extend_contract_items(fields, contract["required"])
        if not has_container:
            # A plain object is itself a field-name -> description/schema mapping.
            _extend_contract_items(fields, contract)
    return list(dict.fromkeys(fields))


def read_case(spec: dict[str, Any], spec_dir: Path, override: str | None) -> tuple[dict[str, Any], Path | None, str | None]:
    raw = override or spec.get("case_file")
    if not raw:
        return {}, None, "case.json was not configured; contract fields cannot be inferred and case_id must come from spec"
    path = resolve_spec_path(spec_dir, raw)
    try:
        case = load_json(path)
        if not isinstance(case, dict):
            raise ValueError("case JSON is not an object")
        return case, path, None
    except (OSError, UnicodeError, json.JSONDecodeError, ValueError) as exc:
        return {}, path, f"case load failed: {exc}"


def formal_witness_complete(spec: dict[str, Any]) -> bool:
    witness = spec.get("_witness")
    if not isinstance(witness, dict):
        return False
    required = {
        "materials_environment_parameters", "two_candidate_materials_reviewed",
        "paper_table_figure_comparisons", "difference_attribution", "raw_data_repository_status",
    }
    return all(isinstance(witness.get(key), (dict, list)) and bool(witness[key]) for key in required)


def usable_case_id(case: dict[str, Any], spec: dict[str, Any]) -> str | int | None:
    value = case["case_id"] if "case_id" in case else spec.get("case_id")
    if isinstance(value, str) and value.strip():
        return value
    if isinstance(value, int) and not isinstance(value, bool):
        return value
    return None


def determine_result_status(report: dict[str, Any], case: dict[str, Any], case_error: str | None,
                            spec: dict[str, Any], missing_contract_fields: list[str]) -> str:
    """Apply task-result semantics, independently of execution completion and paper agreement."""
    if usable_case_id(case, spec) is None or report.get("run_error"):
        return "unable"
    expected_candidate_count = len(spec.get("candidates", []))
    candidates = report.get("candidates", [])
    oracle = spec.get("oracle", {})
    expected_trial_count = (
        len(oracle.get("scaling_factors", [])) if oracle.get("type") == "quadratic_roots" else 1
    )
    executions_complete = (
        report.get("completion_status") == "complete"
        and expected_candidate_count >= 2
        and len(candidates) == expected_candidate_count
        and all(
            item.get("status") == "passed"
            and item.get("passed") is True
            and len(item.get("trials", [])) == expected_trial_count
            for item in candidates
        )
    )
    missing_sources = any(not source.get("loaded", True) for source in report.get("sources", []))
    if (
        not executions_complete
        or spec.get("evaluation_mode", "formal") == "synthetic"
        or case_error
        or missing_sources
        or missing_contract_fields
        or not formal_witness_complete(spec)
    ):
        return "partial"
    return "success"


def make_result(report: dict[str, Any], case: dict[str, Any], case_path: Path | None,
                case_error: str | None, spec: dict[str, Any], output_dir: Path,
                cert_path: Path, md_path: Path) -> dict[str, Any]:
    candidates = report["candidates"]
    any_failure = any(item["status"] != "passed" for item in candidates)
    paper_vs = report.get("paper_vs_oracle", {})
    concise = []
    for candidate in candidates:
        concise.append({"candidate_id": candidate["id"], "status": candidate["status"],
                        "mathematical_oracle_passed": candidate.get("passed"),
                        "paper_target_comparison_statuses": [trial.get("candidate_vs_paper", {}).get("status", "not_run")
                                                              for trial in candidate.get("trials", [])],
                        "trials_completed": len(candidate.get("trials", []))})
    difference = []
    for candidate in candidates:
        if candidate["status"] != "passed":
            messages = []
            for trial in candidate.get("trials", []):
                if trial.get("process", {}).get("launch_error"):
                    messages.append(trial["process"]["launch_error"])
                if trial.get("parse_error"):
                    messages.append(trial["parse_error"])
                comparison = trial.get("candidate_vs_oracle") or {}
                messages.extend(comparison.get("errors") or [])
            difference.append({"candidate_id": candidate["id"], "observed_differences": list(dict.fromkeys(messages)),
                               "attribution": "Observed execution/output/oracle differences only; causal code attribution requires source inspection."})
    defaults: dict[str, Any] = {
        "reproduction_summary": {
            "statement": "Independent mathematical oracle and metamorphic checks completed; this is not by itself paper reproduction.",
            "paper_vs_oracle_status": paper_vs.get("status"),
        },
        "candidate_comparison": concise,
        "paper_comparison": paper_vs,
        "difference_attribution": difference,
        "formal_task_completion": {
            "materials_and_environment_parameters": "agent must inventory and report; runner does not infer missing parameters",
            "two_candidates_executed": len(candidates) >= 2,
            "paper_tables_and_figures_compared": "not established by numeric oracle alone",
            "causal_difference_attribution": "source/data/environment attribution still required when applicable",
        },
    }
    for key, value in spec.get("contract_values", {}).items():
        if isinstance(defaults.get(key), dict) and isinstance(value, dict):
            defaults[key] = {**defaults[key], **value}
        else:
            defaults[key] = value
    runtime_fields = {
        "oracle_tool", "oracle_report_path", "overall_oracle_status",
        "candidate_failures_do_not_stop_other_candidates",
    }
    contract_fields = extract_contract_fields(case)
    known_fields = set(defaults) | REQUIRED_RESULT_FIELDS | runtime_fields
    missing_contract_fields = [field for field in contract_fields if field not in known_fields]
    status = determine_result_status(report, case, case_error, spec, missing_contract_fields)
    if status not in RESULT_STATUSES:
        raise AssertionError(f"internal error: illegal result status {status!r}")
    report["status"] = status
    if isinstance(defaults.get("reproduction_summary"), dict):
        defaults["reproduction_summary"]["status"] = status
    result: dict[str, Any] = {}
    for field in contract_fields:
        result[field] = defaults.get(field, {
            "status": "not_populated_by_oracle_runner",
            "reason": "This declared output_contract field requires case-specific evidence; see oracle_report and uncertainty.",
        })
    uncertainties = list(dict.fromkeys(report["uncertainties"] + ([case_error] if case_error else [])))
    if usable_case_id(case, spec) is None:
        uncertainties.append("case_id is unavailable; task result status is unable.")
    if report.get("run_error"):
        uncertainties.append(f"Task execution could not complete: {report['run_error']}")
    if missing_contract_fields:
        uncertainties.append(
            "Declared contract fields lack populated case-specific evidence: " + ", ".join(missing_contract_fields)
        )
    result.update({
        "case_id": usable_case_id(case, spec),
        "status": status,
        "sources": report["sources"],
        "uncertainty": list(dict.fromkeys(uncertainties)),
        "change_records": [
            {"action": "executed_candidate_argv", "detail": "Commands, stdout, stderr, exit codes and parse outcomes are in oracle_report.json."},
            {"action": "generated", "paths": [str(cert_path), str(md_path), str(output_dir / "result.json")]},
            {"action": "candidate_sources_modified", "value": False},
        ],
        "oracle_tool": {"name": "independent-oracle-lab", "version": VERSION, "spec_sha256": report["spec_sha256"]},
        "oracle_report_path": str(cert_path),
        "overall_oracle_status": "passed" if not any_failure else "partial",
        "candidate_failures_do_not_stop_other_candidates": True,
    })
    if missing_contract_fields:
        result["missing_required_evidence"] = missing_contract_fields
    return result


def render_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# Independent Oracle Report", "",
        f"- Result status: **{report['status']}**",
        f"- Execution completion: **{report.get('completion_status', 'partial')}**",
        f"- Spec SHA-256: `{report['spec_sha256']}`",
        f"- Oracle: `{report['oracle_type']}`",
        f"- Started: {report['started_at']}",
        f"- Finished: {report.get('finished_at', 'not finished')}", "",
        "> Mathematical truth, candidate agreement, and paper agreement are distinct. Passing this oracle is not paper reproduction.", "",
        "## Frozen spec and tolerances", "",
        "```json", json.dumps(report["frozen_tolerances"], ensure_ascii=False, indent=2, default=json_default), "```", "",
        "## Paper target versus Oracle mathematical result", "",
        f"Status: **{report.get('paper_vs_oracle', {}).get('status', 'not_available')}**", "",
        "The paper target is not used as Oracle expected output. Any mismatch remains separately visible in oracle_report.json.", "",
        "## Candidates", "",
    ]
    for candidate in report["candidates"]:
        lines += [f"### {candidate['id']}: {candidate['status']}", ""]
        for trial in candidate.get("trials", []):
            process = trial["process"]
            lines += [
                f"#### Trial `{trial['trial_id']}`", "",
                f"- argv: `{json.dumps(process['argv'], ensure_ascii=False)}`",
                f"- exit code: `{process.get('exit_code')}`; timed out: `{process.get('timed_out')}`",
                f"- parse status: **{trial['parse_status']}**; parse error: {trial.get('parse_error')}",
                f"- candidate vs Oracle passed: `{trial.get('candidate_vs_oracle', {}).get('passed')}`",
                f"- candidate vs paper target: **{trial.get('candidate_vs_paper', {}).get('status', 'not_run')}**", "",
                "stdout:", "", "```text", process.get("stdout", ""), "```", "",
                "stderr:", "", "```text", process.get("stderr", ""), "```", "",
            ]
        if not candidate.get("trials"):
            lines += ["No trial was launched; see failure reason in JSON.", ""]
    lines += ["## Uncertainty", ""]
    lines += [f"- {item}" for item in report["uncertainties"]]
    lines += ["", "## Limitations", "", report["oracle_limitations"], ""]
    return "\n".join(lines)


def write_outputs(output_dir: Path, report: dict[str, Any], result: dict[str, Any]) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    json_path = output_dir / "oracle_report.json"
    md_path = output_dir / "oracle_report.md"
    dump_json(json_path, report)
    md_path.write_text(render_markdown(report), encoding="utf-8", newline="\n")
    dump_json(output_dir / "result.json", result)


def run(args: argparse.Namespace) -> int:
    spec_path = Path(args.spec).resolve()
    spec, digest, spec_dir = validate_spec(spec_path)
    output_dir = Path(args.output_dir).resolve()
    work_dir = Path(args.work_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    work_dir.mkdir(parents=True, exist_ok=True)
    started_monotonic = time.monotonic()
    budget = min(float(args.budget_seconds), 900.0)
    if not math.isfinite(budget) or budget <= 0:
        raise SpecError("budget_seconds must be finite and positive")
    deadline = started_monotonic + budget
    case, case_path, case_error = read_case(spec, spec_dir, args.case)
    oracle = spec["oracle"]
    kind = oracle["type"]
    paper_vs = paper_comparison(kind, spec.get("paper_target"), expected_for_trial(spec, Decimal(1))[0], spec)
    sources: list[dict[str, Any]] = []
    if case_path:
        sources.append({"path": str(case_path), "role": "case.json", "loaded": case_error is None})
    if spec.get("task_file"):
        task_path = resolve_spec_path(spec_dir, spec["task_file"])
        sources.append({"path": str(task_path), "role": "task.md", "loaded": task_path.is_file()})
    for material in spec.get("paper_materials", []):
        path = resolve_spec_path(spec_dir, material)
        sources.append({"path": str(path), "role": "declared paper material", "loaded": path.is_file()})
    for candidate in spec["candidates"]:
        if candidate.get("source_path"):
            path = resolve_spec_path(spec_dir, candidate["source_path"])
            sources.append({"path": str(path), "role": "candidate source", "candidate_id": candidate["id"],
                            "author_code": bool(candidate.get("author_code", False)), "loaded": path.is_file()})
    report: dict[str, Any] = {
        "schema_version": "1.0", "tool_version": VERSION, "status": "partial", "completion_status": "partial",
        "spec_path": str(spec_path), "spec_sha256": digest, "started_at": utc_now(),
        "oracle_type": kind, "frozen_tolerances": oracle["tolerances"],
        "oracle_limitations": (
            "Only real quadratic roots (nonnegative discriminant) are supported. Decimal stable formulas, residuals, Vieta identities and explicit scaling tests are used."
            if kind == "quadratic_roots" else
            "Only a low-to-high-coefficient polynomial on one closed interval is supported. Expected is the best sampled grid/refinement point, not a universal continuous global minimum certificate; narrow missed minima can make results inconclusive."
        ),
        "paper_vs_oracle": paper_vs, "candidates": [], "sources": sources,
        "uncertainties": [
            "Oracle agreement is mathematical/metamorphic evidence only, not proof of paper reproduction.",
            "No same-code rerun, log-frequency vote, reproduction-count vote, or generator consensus is used as an expected value.",
        ],
        "environment": {"python": sys.version, "platform": platform.platform(), "decimal_module": "CPython stdlib decimal"},
        "budget_seconds_effective": budget,
    }
    if case_error:
        report["uncertainties"].append(case_error)
    for source in sources:
        if not source.get("loaded", True):
            report["uncertainties"].append(f"Declared source is missing or unreadable: {source['path']} ({source['role']})")
    if spec.get("evaluation_mode") == "synthetic":
        report["uncertainties"].append("Synthetic organizer-written example only: not author code and not a reproduction of an original paper.")
        report["uncertainties"].append("Original raw data and author repository are absent and were not fabricated.")
    base_parameters = oracle["parameters"]
    for candidate_index, candidate in enumerate(spec["candidates"]):
        record: dict[str, Any] = {"id": candidate["id"], "status": "running", "passed": False,
                                  "explicit_argv_template": candidate["argv"], "trials": []}
        report["candidates"].append(record)
        scales = ([Decimal(1)] if kind == "brute_force_minimizer_1d" else
                  [dec(value, "scaling factor") for value in oracle["scaling_factors"]])
        for trial_index, scale in enumerate(scales):
            if time.monotonic() >= deadline - 0.05:
                record["trials"].append({"trial_id": f"budget_{trial_index}", "parse_status": "not_run",
                                         "parse_error": "run budget exhausted", "process": {"argv": [], "stdout": "", "stderr": ""}})
                continue
            expected, parameters = expected_for_trial(spec, scale)
            trial_work = work_dir / candidate["id"] / f"trial_{trial_index:03d}"
            trial_work.mkdir(parents=True, exist_ok=True)
            json_out = trial_work / "candidate_output.json"
            # This runner-owned path must never provide stale output from an earlier run.
            json_out.unlink(missing_ok=True)
            values = {
                "spec_dir": str(spec_dir), "work_dir": str(trial_work), "output_dir": str(output_dir),
                "json_out": str(json_out), "scale": decimal_text(scale),
            }
            for key in ("a", "b", "c"):
                value = parameters.get(key, base_parameters.get(key, ""))
                values[key] = decimal_text(dec(value, key)) if value != "" else ""
            argv = [render(argument, values) for argument in candidate["argv"]]
            cwd = Path(render(candidate.get("cwd", "{spec_dir}"), values)).resolve()
            execution = run_process(argv, cwd, float(candidate["timeout_seconds"]), deadline)
            parse_status, payload, parse_error, output_location = parse_candidate_output(candidate, execution, values, cwd)
            try:
                if kind == "quadratic_roots":
                    comparison = (root_comparison(payload, expected["roots"], oracle["tolerances"], parameters["precision"],
                                                  dec(parameters["a"], "a"), dec(parameters["b"], "b"), dec(parameters["c"], "c"))
                                  if parse_status == "parsed" else {"passed": False, "errors": [parse_error or "no parsed output"]})
                else:
                    comparison = (minimizer_comparison(payload, expected, parameters, oracle["tolerances"])
                                  if parse_status == "parsed" else {"passed": False, "errors": [parse_error or "no parsed output"]})
                paper_direct = (candidate_paper_comparison(kind, spec.get("paper_target"), payload, parameters, oracle["tolerances"])
                                if parse_status == "parsed" else {"status": "not_available", "reason": parse_error or "no parsed output"})
            except Exception as exc:
                # Candidate-controlled extreme numbers must not stop the other candidate.
                comparison = {"passed": False, "status": "failed",
                              "errors": [f"oracle evaluation error isolated to this trial: {type(exc).__name__}: {exc}"]}
                paper_direct = {"status": "not_available", "reason": "Oracle evaluation error; see candidate_vs_oracle"}
            trial = {
                "trial_id": f"trial_{trial_index:03d}", "scale": scale,
                "independent_expected": expected, "candidate_parsed_output": payload,
                "candidate_vs_oracle": comparison, "candidate_vs_paper": paper_direct, "process": execution,
                "parse_status": parse_status, "parse_error": parse_error, "output_location": output_location,
            }
            record["trials"].append(trial)
        execution_failures = [trial for trial in record["trials"]
                              if trial["process"].get("exit_code") != 0 or trial["process"].get("timed_out")
                              or trial["parse_status"] != "parsed"]
        numeric_failures = [trial for trial in record["trials"] if not trial.get("candidate_vs_oracle", {}).get("passed", False)]
        inconclusive = any(trial.get("candidate_vs_oracle", {}).get("status") == "oracle_inconclusive" for trial in record["trials"])
        record["passed"] = not execution_failures and not numeric_failures and bool(record["trials"])
        record["status"] = "passed" if record["passed"] else ("inconclusive" if inconclusive and not execution_failures else "failed")
        record["scaling_metamorphic"] = {
            "performed": kind == "quadratic_roots" and len(scales) > 1,
            "factors": scales,
            "definition": "nonzero a,b,c common scaling leaves roots invariant; each trial independently recomputes stable Decimal expected roots and residuals",
            "passed": record["passed"] if kind == "quadratic_roots" else None,
        }
        # Persist partial evidence immediately after every candidate, independent of later failures.
        case_fields_result = make_result(report, case, case_path, case_error, spec, output_dir,
                                         output_dir / "oracle_report.json", output_dir / "oracle_report.md")
        write_outputs(output_dir, report, case_fields_result)
    report["finished_at"] = utc_now()
    report["duration_seconds"] = time.monotonic() - started_monotonic
    report["completion_status"] = "complete"
    result = make_result(report, case, case_path, case_error, spec, output_dir,
                         output_dir / "oracle_report.json", output_dir / "oracle_report.md")
    # Execution can be complete while task evidence is only partial or the task is unable.
    report["uncertainties"] = result["uncertainty"]
    write_outputs(output_dir, report, result)
    print(json.dumps({"status": result["status"], "completion_status": report["completion_status"], "spec_sha256": digest,
                      "candidates": [{"id": c["id"], "status": c["status"]} for c in report["candidates"]],
                      "output_dir": str(output_dir)}, ensure_ascii=False))
    return 0


def self_test() -> int:
    q_parameters = {"a": "1", "b": "-100000000", "c": "1", "precision": 100}
    q = quadratic_expected(q_parameters)
    small = q["roots"][0]
    residual = quadratic_residuals(small, Decimal(1), Decimal(-100000000), Decimal(1), 100)
    small_expected = Decimal("0.00000001")
    # The exact small root is 1.0000000000000001...e-8, not merely 1e-8.
    if abs(small - small_expected) > Decimal("1.01e-24") or residual["scaled"] > Decimal("1e-90"):
        raise AssertionError("stable quadratic self-test failed")
    b_parameters = {
        "coefficients": ["3.5625", "-2.5", "1"], "lower": "-3", "upper": "4",
        "initial_grid_points": 33, "refinement_rounds": 8, "local_grid_points": 101, "precision": 80,
    }
    b = brute_force_expected(b_parameters)
    if abs(b["x"] - Decimal("1.25")) > Decimal("1e-12") or abs(b["value"] - 2) > Decimal("1e-20"):
        raise AssertionError(f"brute force self-test failed: x={b['x']} value={b['value']}")
    print(json.dumps({"status": "passed", "quadratic_small_root": decimal_text(small),
                      "quadratic_scaled_residual": decimal_text(residual["scaled"]),
                      "brute_force_x": decimal_text(b["x"]), "brute_force_evaluations": b["evaluations"]}))
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    run_parser = subparsers.add_parser("run", help="verify frozen spec hash, run candidates, emit reports")
    run_parser.add_argument("--spec", required=True)
    run_parser.add_argument("--case", help="optional case.json override")
    run_parser.add_argument("--work-dir", default="/app/work", help="intermediate outputs; formal platform default /app/work")
    run_parser.add_argument("--output-dir", default="/app/output", help="final outputs; formal platform default /app/output")
    run_parser.add_argument("--budget-seconds", type=float, default=900.0, help="capped at 900 seconds; partial evidence persisted per candidate")
    validate_parser = subparsers.add_parser("validate", help="validate spec and hash without running candidates")
    validate_parser.add_argument("--spec", required=True)
    subparsers.add_parser("self-test", help="test high-precision quadratic and brute-force minimizer")
    args = parser.parse_args()
    try:
        if args.command == "self-test":
            return self_test()
        if args.command == "validate":
            spec, digest, _ = validate_spec(Path(args.spec).resolve())
            print(json.dumps({"status": "valid", "spec_sha256": digest, "oracle_type": spec["oracle"]["type"]}))
            return 0
        return run(args)
    except SpecError as exc:
        print(json.dumps({"status": "invalid_spec", "error": str(exc)}), file=sys.stderr)
        return 2
    except Exception as exc:  # honest top-level failure; per-candidate failures are caught in their records
        print(json.dumps({"status": "runner_error", "error": f"{type(exc).__name__}: {exc}"}), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
