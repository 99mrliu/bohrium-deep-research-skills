#!/usr/bin/env python3
"""Quantitative entailment evidence, never an automatic claim verdict.

All calculated numbers are role=derived and retain formula/source_ids. Source
observations remain role=reported. Standard-library only; no network access.
"""
from __future__ import annotations

import html
import json
import math
from pathlib import Path

Z95 = 1.959963984540054
DEFAULT_ABSOLUTE_TOLERANCE = 1e-9
DEFAULT_RELATIVE_TOLERANCE = 1e-9
METRICS = {
    "proportion_difference", "percentage_point_difference", "relative_change",
    "proportion_ratio", "mean_difference", "relative_mean_change", "mean_ratio",
    "unit_conversion", "two_proportion_p_value",
}


class InputError(ValueError):
    """Invalid observations, claims, units, sample sizes, or intervals."""


def read_json(path):
    def bad_constant(value):
        raise InputError("non-finite JSON number: " + value)
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"), parse_constant=bad_constant)
    except json.JSONDecodeError as exc:
        raise InputError("invalid JSON in %s: %s" % (Path(path).name, exc)) from exc


def write_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n",
                    encoding="utf-8")


def number(value, label):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise InputError(label + " must be a finite number")
    return float(value)


def positive_integer(value, label):
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise InputError(label + " must be a positive integer")
    return value


def validate_confidence(value):
    value = number(value, "confidence")
    if not 0 < value < 1:
        raise InputError("confidence must be strictly between 0 and 1")
    if value < 0.5:
        raise InputError("confidence below 0.5 is not supported for these intervals")
    return value


def normal_quantile(probability):
    """Inverse standard normal CDF by bisection; deterministic and stdlib-only."""
    probability = number(probability, "normal probability")
    if not 0 < probability < 1:
        raise InputError("normal probability must be strictly between 0 and 1")
    low, high = -12.0, 12.0
    for _ in range(120):
        middle = (low + high) / 2
        cdf = 0.5 * math.erfc(-middle / math.sqrt(2))
        if cdf < probability:
            low = middle
        else:
            high = middle
    return (low + high) / 2


def wilson_interval(events, n, confidence=0.95):
    """Wilson score interval for one binomial proportion, with continuity no correction."""
    positive_integer(n, "n")
    if isinstance(events, bool) or not isinstance(events, int) or not 0 <= events <= n:
        raise InputError("events must be an integer between 0 and n")
    confidence = validate_confidence(confidence)
    z = Z95 if abs(confidence - 0.95) < 1e-15 else normal_quantile((1 + confidence) / 2)
    p = events / n
    denominator = 1 + z * z / n
    center = (p + z * z / (2 * n)) / denominator
    half_width = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / denominator
    return {
        "role": "derived", "method": "Wilson score interval (no continuity correction)",
        "confidence": confidence, "z_critical": z, "lower": max(0.0, center - half_width),
        "upper": min(1.0, center + half_width),
        "formula": "center=(p+z^2/(2n))/(1+z^2/n); halfwidth=z*sqrt(p(1-p)/n+z^2/(4n^2))/(1+z^2/n)",
        "source_ids": [],
    }


def two_proportion_z_test(first, second, confidence=0.95):
    """Two-sided pooled z test plus per-group Wilson intervals.

    This is a normal approximation, not an exact test. Sparse expected cells are
    flagged and never converted into a hard semantic verdict.
    """
    x1, n1 = first["events"], first["n"]
    x0, n0 = second["events"], second["n"]
    p1, p0 = x1 / n1, x0 / n0
    pooled = (x1 + x0) / (n1 + n0)
    standard_error = math.sqrt(pooled * (1 - pooled) * (1 / n1 + 1 / n0))
    warnings = []
    if standard_error == 0:
        z_value, p_value = None, None
        warnings.append("degenerate pooled proportion: two-sided z and p are undefined")
    else:
        z_value = (p1 - p0) / standard_error
        p_value = math.erfc(abs(z_value) / math.sqrt(2))
    expected = [n1 * pooled, n1 * (1 - pooled), n0 * pooled, n0 * (1 - pooled)]
    sparse = any(cell < 5 for cell in expected)
    if sparse:
        warnings.append("at least one pooled expected cell is below 5; normal-approximation p-value is unstable")
    intervals = []
    for group, obs, p in (("first", first, p1), ("second", second, p0)):
        interval = wilson_interval(obs["events"], obs["n"], confidence)
        interval.update(source_ids=[obs["id"]], group=group, observed_proportion=p)
        intervals.append(interval)
    test_id = "ztest_%s_%s" % (first["id"], second["id"])
    return {
        "id": test_id, "role": "derived", "method": "two-sided pooled two-proportion z test",
        "source_ids": [first["id"], second["id"]],
        "formula": "pooled=(x1+x0)/(n1+n0); z=(p1-p0)/sqrt(pooled*(1-pooled)*(1/n1+1/n0)); p_two_sided=erfc(abs(z)/sqrt(2))",
        "substitution": "pooled=(%d+%d)/(%d+%d)" % (x1, x0, n1, n0),
        "pooled_proportion": pooled, "standard_error_null": standard_error,
        "z": z_value, "p_two_sided_normal_approximation": p_value,
        "alternative": "two_sided", "exact_test": False, "sparse_expected_cells": sparse,
        "expected_cells_under_null": {"n1_success": expected[0], "n1_failure": expected[1],
                                      "n0_success": expected[2], "n0_failure": expected[3]},
        "wilson_intervals": intervals, "confidence": confidence, "warnings": warnings,
        "interpretation_limit": "A non-significant result is not evidence that the effect is zero; a derived p-value does not prove the source reported it.",
    }


def validate_observations(document):
    if not isinstance(document, dict) or not isinstance(document.get("observations"), list):
        raise InputError("observations input must be an object with an observations list")
    observations = document["observations"]
    if not observations:
        raise InputError("observations list is empty")
    output, identifiers = [], set()
    for index, original in enumerate(observations):
        if not isinstance(original, dict):
            raise InputError("observation %d must be an object" % index)
        obs = dict(original)
        identifier = obs.get("id")
        if not isinstance(identifier, str) or not identifier.strip() or identifier in identifiers:
            raise InputError("observation ids must be nonempty and unique")
        identifiers.add(identifier)
        if not isinstance(obs.get("quote"), str) or not obs["quote"].strip():
            raise InputError(identifier + " requires a verbatim source quote")
        if not obs.get("source_id") or not obs.get("location"):
            raise InputError(identifier + " requires source_id and location")
        obs["role"] = "reported"
        kind = obs.get("kind")
        if kind == "proportion":
            obs["n"] = positive_integer(obs.get("n"), identifier + ".n")
            events = obs.get("events")
            if isinstance(events, bool) or not isinstance(events, int) or not 0 <= events <= obs["n"]:
                raise InputError(identifier + ".events must be an integer between 0 and n")
        elif kind == "mean":
            obs["n"] = positive_integer(obs.get("n"), identifier + ".n")
            obs["mean"] = number(obs.get("mean"), identifier + ".mean")
            obs["sd"] = number(obs.get("sd"), identifier + ".sd")
            if obs["sd"] < 0:
                raise InputError(identifier + ".sd must be nonnegative")
            if not isinstance(obs.get("unit"), str) or not obs["unit"]:
                raise InputError(identifier + ".unit is required")
        else:
            raise InputError(identifier + ".kind must be proportion or mean")
        display = obs.get("reported_display")
        if display is not None:
            if not isinstance(display, dict) or not isinstance(display.get("quote"), str) or not display["quote"].strip():
                raise InputError(identifier + ".reported_display requires its own quote")
            display["value"] = number(display.get("value"), identifier + ".reported_display.value")
            if display.get("unit") not in ("percent", "proportion"):
                raise InputError(identifier + ".reported_display.unit must be percent or proportion")
        output.append(obs)
    return output


_UNIT_TABLE = {
    "s": ("time", 1.0), "ms": ("time", 1e-3), "us": ("time", 1e-6),
    "min": ("time", 60.0), "h": ("time", 3600.0),
    "m": ("length", 1.0), "cm": ("length", 1e-2), "mm": ("length", 1e-3),
    "um": ("length", 1e-6), "km": ("length", 1000.0),
    "kg": ("mass", 1.0), "g": ("mass", 1e-3), "mg": ("mass", 1e-6), "ug": ("mass", 1e-9),
    "L": ("volume", 1.0), "mL": ("volume", 1e-3), "uL": ("volume", 1e-6),
}


def convert_units(value, source, target):
    value = number(value, "unit conversion value")
    if source == target:
        return value
    if source not in _UNIT_TABLE or target not in _UNIT_TABLE:
        raise InputError("unsupported unit conversion: %s to %s" % (source, target))
    source_dimension, source_factor = _UNIT_TABLE[source]
    target_dimension, target_factor = _UNIT_TABLE[target]
    if source_dimension != target_dimension:
        raise InputError("incompatible unit dimensions: %s to %s" % (source, target))
    return value * source_factor / target_factor


def _target_in_output_units(target, output_unit):
    target = number(target, "claim target")
    return target


def _component_rate(obs, basis):
    if basis == "raw_counts":
        return obs["events"] / obs["n"], "%d/%d" % (obs["events"], obs["n"]), obs["id"]
    if basis == "reported_display":
        display = obs.get("reported_display")
        if not display:
            raise InputError(obs["id"] + " has no reported_display for requested basis")
        value = display["value"] / 100 if display["unit"] == "percent" else display["value"]
        expression = "%g%%" % display["value"] if display["unit"] == "percent" else repr(display["value"])
        return value, expression, obs["id"] + ".reported_display"
    raise InputError("basis must be raw_counts or reported_display")


def _tolerance(component, target):
    specification = component.get("tolerance", {})
    if not isinstance(specification, dict):
        raise InputError("tolerance must be an object")
    absolute = number(specification.get("absolute", DEFAULT_ABSOLUTE_TOLERANCE), "absolute tolerance")
    relative = number(specification.get("relative", DEFAULT_RELATIVE_TOLERANCE), "relative tolerance")
    if absolute < 0 or relative < 0:
        raise InputError("tolerances must be nonnegative")
    return {
        "absolute": absolute, "relative": relative,
        "rule": "abs(calculated-target) <= max(absolute, relative*abs(target))",
        "maximum_allowed_absolute_difference": max(absolute, relative * abs(target)),
    }


def _compare(value, component, target, output_unit):
    tolerance = _tolerance(component, target)
    difference = value - target
    comparison = {
        "target": target, "target_unit": output_unit,
        "calculated_minus_target": difference, "tolerance": tolerance,
        "within_tolerance": abs(difference) <= tolerance["maximum_allowed_absolute_difference"],
    }
    if component.get("target_origin") == "source_reported":
        comparison["entailment_comparison"] = "not_applicable_source_reporting_question"
        comparison["warning"] = "A recomputation cannot prove that the source printed an exact target; absence of a reported value is not a contradiction."
    else:
        comparison["entailment_comparison"] = "within_tolerance" if comparison["within_tolerance"] else "outside_tolerance"
    return comparison


def _get_pair(component, by_id):
    source_ids = component.get("source_ids")
    if not isinstance(source_ids, list) or len(source_ids) != 2 or not all(isinstance(x, str) for x in source_ids):
        raise InputError("comparison source_ids must contain exactly two observation ids")
    try:
        return by_id[source_ids[0]], by_id[source_ids[1]]
    except KeyError as exc:
        raise InputError("unknown observation id: " + str(exc)) from exc


def derive_component(claim_id, component, index, by_id, confidence):
    if not isinstance(component, dict):
        raise InputError("claim component must be an object")
    metric = component.get("metric")
    if metric not in METRICS:
        raise InputError("unsupported metric: " + str(metric))
    basis = component.get("basis", "raw_counts")
    role_source_ids = list(component.get("source_ids", []))
    first = second = None
    if metric == "unit_conversion":
        source_ids = component.get("source_ids")
        if not isinstance(source_ids, list) or len(source_ids) != 1 or source_ids[0] not in by_id:
            raise InputError("unit_conversion requires one valid source id")
        first = by_id[source_ids[0]]
        if first["kind"] != "mean" or "unit" not in component.get("target", {}):
            raise InputError("unit_conversion requires a mean observation and target.unit")
        target_unit = component["target"]["unit"]
        converted = convert_units(first["mean"], first["unit"], target_unit)
        value, output_unit = converted, target_unit
        formula = "value_in_%s = value_in_%s * unit_factor(%s/%s)" % (target_unit, first["unit"], first["unit"], target_unit)
        substitution = "%g %s -> %.12g %s" % (first["mean"], first["unit"], value, target_unit)
    else:
        first, second = _get_pair(component, by_id)
        if metric.startswith("mean") or metric in ("relative_mean_change",):
            if first["kind"] != "mean" or second["kind"] != "mean" or first["unit"] != second["unit"]:
                raise InputError("mean comparisons require two mean observations with the same unit")
            m1, m0 = first["mean"], second["mean"]
            unit = first["unit"]
            if metric == "mean_difference":
                value, output_unit = m1 - m0, unit
                formula, substitution = "mean1-mean0", "%g - %g" % (m1, m0)
            elif metric == "mean_ratio":
                if m0 == 0:
                    raise InputError("mean ratio is undefined for a zero denominator")
                value, output_unit = m1 / m0, "ratio"
                formula, substitution = "mean1/mean0", "%g/%g" % (m1, m0)
            else:
                if m0 == 0:
                    raise InputError("relative mean change is undefined for a zero denominator")
                value, output_unit = (m1 - m0) / m0, "relative_fraction"
                formula, substitution = "(mean1-mean0)/mean0", "(%g-%g)/%g" % (m1, m0, m0)
        else:
            if first["kind"] != "proportion" or second["kind"] != "proportion":
                raise InputError("proportion comparisons require two proportion observations")
            p1, e1, id1 = _component_rate(first, basis)
            p0, e0, id0 = _component_rate(second, basis)
            role_source_ids = [id1, id0]
            if metric == "proportion_difference":
                value, output_unit = p1 - p0, "proportion"
                formula, substitution = "p1-p0", "%s - %s" % (e1, e0)
            elif metric == "percentage_point_difference":
                value, output_unit = 100 * (p1 - p0), "percentage_point"
                formula, substitution = "100*(p1-p0)", "100*(%s - %s)" % (e1, e0)
            elif metric == "relative_change":
                if p0 == 0:
                    raise InputError("relative change is undefined for a zero baseline")
                value, output_unit = (p1 - p0) / p0, "relative_fraction"
                formula, substitution = "(p1-p0)/p0", "(%s - %s)/(%s)" % (e1, e0, e0)
            elif metric == "proportion_ratio":
                if p0 == 0:
                    raise InputError("proportion ratio is undefined for a zero baseline")
                value, output_unit = p1 / p0, "ratio"
                formula, substitution = "p1/p0", "(%s)/(%s)" % (e1, e0)
            else:
                value, output_unit = None, "probability"
                formula, substitution = "see linked two-sided pooled z test", "raw counts only; display values are never used for the z test"
    record = {
        "id": "derived_%s_%d" % (claim_id, index), "claim_id": claim_id,
        "role": "derived", "data_label": "SYNTHETIC" if by_id[first["id"]].get("synthetic", False) else None,
        "metric": metric, "basis": basis if metric != "unit_conversion" else None,
        "source_ids": role_source_ids, "formula": formula, "substitution": substitution,
        "value": value, "unit": output_unit,
        "display_percentage": 100 * value if output_unit == "relative_fraction" and value is not None else None,
        "warnings": [], "verdict": None,
        "verdict_policy": "Agent semantic adjudication required; numeric matching alone is not entailment.",
    }
    if record["data_label"] is None:
        del record["data_label"]
    if record["basis"] is None:
        del record["basis"]
    if metric == "two_proportion_p_value":
        test = two_proportion_z_test(first, second, confidence)
        value = test["p_two_sided_normal_approximation"]
        record["value"] = value
        record["statistical_test_id"] = test["id"]
        record["source_ids"] = [first["id"], second["id"]]
        record["warnings"].append("normal-approximation derived p-value is not a source-reported exact p-value")
    target_spec = component.get("target")
    if target_spec is not None:
        if not isinstance(target_spec, dict) or "value" not in target_spec:
            raise InputError("target must be an object with value")
        target = number(target_spec["value"], "target.value")
        target_unit = target_spec.get("unit", output_unit)
        if metric == "unit_conversion":
            if target_unit != output_unit:
                raise InputError("unit_conversion target unit mismatch")
        elif output_unit in (first.get("unit") if first else None, "s", "ms", "us", "min", "h", "m", "cm", "mm", "um", "km", "kg", "g", "mg", "ug", "L", "mL", "uL") and target_unit != output_unit:
            value = convert_units(value, output_unit, target_unit)
            record["value"], record["unit"], output_unit = value, target_unit, target_unit
        elif output_unit == "relative_fraction" and target_unit == "relative_percent":
            target /= 100
        elif output_unit == "proportion" and target_unit == "percent":
            target /= 100
        elif target_unit not in (output_unit, "probability" if output_unit == "probability" else output_unit):
            raise InputError("target unit %s does not match calculated unit %s" % (target_unit, output_unit))
        record["comparison"] = _compare(value, component, target, output_unit) if value is not None else {
            "entailment_comparison": "not_computable", "warning": "derived value is undefined"
        }
    return record, (test if metric == "two_proportion_p_value" else None)


def build_report(observation_document, claim_document, case_id, confidence=0.95):
    confidence = validate_confidence(confidence)
    observations = validate_observations(observation_document)
    by_id = {obs["id"]: obs for obs in observations}
    claims = claim_document.get("claims") if isinstance(claim_document, dict) else claim_document
    if not isinstance(claims, list) or not claims:
        raise InputError("claims must be a nonempty list or an object with claims list")
    derived, tests, claim_ids = [], {}, set()
    for claim in claims:
        if not isinstance(claim, dict) or not isinstance(claim.get("id"), str) or not claim["id"]:
            raise InputError("each claim requires a nonempty id")
        claim_id = claim["id"]
        if claim_id in claim_ids or not isinstance(claim.get("question"), str) or not claim["question"].strip():
            raise InputError("claim ids must be unique and each claim requires a question")
        claim_ids.add(claim_id)
        components = claim.get("components", [claim])
        if not isinstance(components, list) or not components:
            raise InputError(claim_id + ".components must be a nonempty list")
        for index, component in enumerate(components, 1):
            record, test = derive_component(claim_id, component, index, by_id, confidence)
            derived.append(record)
            if test is not None:
                tests[test["id"]] = test
    # Every raw proportion pair used in a proportion claim receives test evidence,
    # including effect-size claims that do not themselves target a p-value.
    seen_pairs = {tuple(test["source_ids"]) for test in tests.values()}
    for claim in claims:
        for component in claim.get("components", [claim]):
            if component.get("metric", "") in ("proportion_difference", "percentage_point_difference", "relative_change", "proportion_ratio"):
                first, second = _get_pair(component, by_id)
                if component.get("basis", "raw_counts") != "raw_counts":
                    continue
                pair = (first["id"], second["id"])
                if pair in seen_pairs:
                    continue
                seen_pairs.add(pair)
                test = two_proportion_z_test(first, second, confidence)
                tests[test["id"]] = test
    tests = list(tests.values())
    if observation_document.get("synthetic", False):
        for test in tests:
            test["data_label"] = "SYNTHETIC"
            for interval in test["wilson_intervals"]:
                interval["data_label"] = "SYNTHETIC"
    for record in derived:
        if record["metric"] in ("proportion_difference", "percentage_point_difference", "relative_change", "proportion_ratio") and record.get("basis", "raw_counts") == "raw_counts":
            pair = tuple(record["source_ids"])
            for test in tests:
                if tuple(test["source_ids"]) == pair:
                    record["statistical_test_id"] = test["id"]
    warnings = []
    for obs in observations:
        display = obs.get("reported_display")
        if obs["kind"] == "proportion" and display:
            reported = display["value"] / 100 if display["unit"] == "percent" else display["value"]
            calculated = obs["events"] / obs["n"]
            if not math.isclose(reported, calculated, rel_tol=1e-12, abs_tol=1e-12):
                warnings.append({"observation_id": obs["id"], "type": "reported_display_conflicts_with_raw_counts",
                                 "reported_display_proportion": reported, "derived_proportion": calculated,
                                 "action": "retain both; do not silently overwrite either"})
    return {
        "schema_version": "1.0", "case_id": case_id,
        "synthetic": bool(observation_document.get("synthetic", False)),
        "data_label": "SYNTHETIC" if observation_document.get("synthetic", False) else "SOURCE_EXTRACTED",
        "status": "success", "role": "quantitative_entailment_evidence_only",
        "policy": {
            "verdicts": "Agent-only: supported/partially_supported/contradicted/insufficient_evidence",
            "topic_relevance_is_not_support": True, "unreported_is_not_contradiction": True,
            "conflicts_are_retained_in_parallel": True,
            "statistical_non_significance_is_not_zero_effect": True,
            "no_raw_data_no_fabricated_exact_p_value": True,
        },
        "confidence": confidence, "observations": observations, "derived": derived,
        "statistical_tests": tests, "warnings": warnings,
        "method_boundary": "Two-proportion p-values use a pooled normal approximation; Wilson intervals are per group. Neither is an exact small-sample test or an automatic semantic verdict.",
    }


def effect_svg(report):
    """Create a text-only SVG directly from computed proportions/Wilson limits."""
    test = report.get("statistical_tests", [None])[0] if report.get("statistical_tests") else None
    if not test:
        return None
    observations = {obs["id"]: obs for obs in report["observations"]}
    width, height = 760, 330
    left, right, top = 190, 40, 105
    axis_width = width - left - right
    rows = test["wilson_intervals"]
    parts = [
        '<svg xmlns="http://www.w3.org/2000/svg" width="760" height="330" viewBox="0 0 760 330" role="img" aria-labelledby="title desc">',
        '<title id="title">SYNTHETIC proportions and Wilson 95 percent intervals</title>' if report["synthetic"] else '<title id="title">Derived proportions and Wilson intervals</title>',
        '<desc id="desc">Effect plot generated from quantitative report; dots are derived proportions and bars are Wilson score confidence intervals.</desc>',
        '<rect width="100%" height="100%" fill="white"/>',
        '<text x="24" y="32" font-family="sans-serif" font-size="20" font-weight="bold">%s proportions with Wilson %g%% CI</text>' % ("SYNTHETIC" if report["synthetic"] else "Derived", 100 * test["confidence"]),
        '<text x="24" y="56" font-family="sans-serif" font-size="12" fill="#555">Derived from source-linked counts; interval is uncertainty, not a semantic verdict.</text>',
    ]
    axis_y = 250
    parts.append('<line x1="%d" y1="%d" x2="%d" y2="%d" stroke="#333"/>' % (left, axis_y, left + axis_width, axis_y))
    for tick in range(0, 101, 20):
        x = left + axis_width * tick / 100
        parts.append('<line x1="%.2f" y1="%d" x2="%.2f" y2="%d" stroke="#333"/>' % (x, axis_y, x, axis_y + 6))
        parts.append('<text x="%.2f" y="%d" text-anchor="middle" font-family="sans-serif" font-size="12">%d%%</text>' % (x, axis_y + 23, tick))
    for row, interval in zip((140, 205), rows):
        obs = observations[interval["source_ids"][0]]
        p, low, high = interval["observed_proportion"], interval["lower"], interval["upper"]
        x, xl, xh = (left + axis_width * value for value in (p, low, high))
        label = "%s (%d/%d)" % (obs["id"], obs["events"], obs["n"])
        parts.extend([
            '<text x="%d" y="%d" text-anchor="end" font-family="sans-serif" font-size="13">%s</text>' % (left - 12, row + 4, html.escape(label)),
            '<line x1="%.2f" y1="%d" x2="%.2f" y2="%d" stroke="#1769aa" stroke-width="4"/>' % (xl, row, xh, row),
            '<line x1="%.2f" y1="%d" x2="%.2f" y2="%d" stroke="#1769aa" stroke-width="2"/>' % (xl, row - 7, xl, row + 7),
            '<line x1="%.2f" y1="%d" x2="%.2f" y2="%d" stroke="#1769aa" stroke-width="2"/>' % (xh, row - 7, xh, row + 7),
            '<circle cx="%.2f" cy="%d" r="7" fill="#d1495b"/>' % (x, row),
            '<text x="%.2f" y="%d" font-family="sans-serif" font-size="12" fill="#333"> %.1f%% [%.1f, %.1f]</text>' % (min(xh + 8, width - 190), row - 10, 100*p, 100*low, 100*high),
        ])
    parts.append('<text x="24" y="305" font-family="sans-serif" font-size="12" fill="#555">All values are derived; formulas and source ids are in quantitative-report.json.</text>')
    parts.append('</svg>')
    return "\n".join(parts) + "\n"
