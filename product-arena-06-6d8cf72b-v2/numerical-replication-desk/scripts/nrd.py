#!/usr/bin/env python3
"""Numerical Replication Desk: anchored Decimal verification, Python 3.9+ stdlib."""

import argparse
import copy
import json
import math
import re
import shutil
import sys
from decimal import Decimal, InvalidOperation, ROUND_DOWN, ROUND_HALF_EVEN, ROUND_HALF_UP, ROUND_UP, localcontext
from pathlib import Path
from xml.sax.saxutils import escape as xml_escape

SCHEMA_VERSION = "1.0"
OPERATIONS = {
    "percent_relative_change", "percentage_point_difference", "ratio",
    "difference", "product", "sum", "division",
}
ROUNDING = {
    "ROUND_HALF_UP": ROUND_HALF_UP,
    "ROUND_HALF_EVEN": ROUND_HALF_EVEN,
    "ROUND_DOWN": ROUND_DOWN,
    "ROUND_UP": ROUND_UP,
}
PROVENANCE = {
    "author_reported", "independently_calculated", "reader_inference", "not_reported", "missing"
}
PERCENT_UNITS = {"percent", "percentage"}
SCHEMA_ANNOTATIONS = {"$schema", "$id", "$comment", "title", "description", "default", "examples"}
SCHEMA_KEYWORDS = SCHEMA_ANNOTATIONS | {
    "$defs", "definitions", "$ref", "type", "properties", "required", "additionalProperties",
    "items", "const", "enum", "anyOf", "oneOf", "pattern", "uniqueItems",
    "minItems", "maxItems", "minLength", "maxLength", "minimum", "maximum",
    "exclusiveMinimum", "exclusiveMaximum", "multipleOf",
}


class LedgerError(Exception):
    pass


class ContractError(Exception):
    pass


def read_json(path):
    path = Path(path)
    try:
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        raise LedgerError("missing JSON file: %s" % path)
    except (OSError, UnicodeError) as exc:
        raise LedgerError("unreadable JSON file %s: %s" % (path, exc))

    def unique_pairs(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise LedgerError("duplicate JSON key %r in %s" % (key, path))
            result[key] = value
        return result

    def bad_constant(value):
        raise LedgerError("non-finite JSON constant %s in %s" % (value, path))

    try:
        return json.loads(text, object_pairs_hook=unique_pairs, parse_constant=bad_constant)
    except json.JSONDecodeError as exc:
        raise LedgerError("malformed JSON %s at line %d column %d: %s" % (path, exc.lineno, exc.colno, exc.msg))


def write_json(path, value):
    Path(path).write_text(
        json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n",
        encoding="utf-8",
    )


def require(condition, message):
    if not condition:
        raise LedgerError(message)


def as_decimal(value, label):
    require(isinstance(value, str) and value.strip() != "", "%s must be a nonempty decimal string" % label)
    require(not re.search(r"[eE]", value), "%s must use plain decimal notation, not exponent notation" % label)
    try:
        result = Decimal(value)
    except InvalidOperation:
        raise LedgerError("%s is not a decimal: %r" % (label, value))
    require(result.is_finite(), "%s must be finite" % label)
    return result


def plain(value):
    text = format(value, "f")
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return "0" if text in ("-0", "") else text


def fixed(value, places):
    return format(value, ".%df" % places)


def canonical_unit(unit):
    require(isinstance(unit, str) and unit.strip(), "value unit must be a nonempty string")
    return "percent" if unit.strip().lower() in PERCENT_UNITS else unit.strip()


def source_records(ledger, ledger_dir):
    records = []
    by_id = {}
    texts = {}
    seen = set()
    sources = ledger.get("sources")
    require(isinstance(sources, list) and sources, "ledger.sources must be a nonempty array")
    for index, source in enumerate(sources):
        require(isinstance(source, dict), "sources[%d] must be an object" % index)
        source_id = source.get("source_id")
        require(isinstance(source_id, str) and source_id, "sources[%d].source_id is required" % index)
        require(source_id not in seen, "duplicate source_id %s" % source_id)
        seen.add(source_id)
        raw_path = source.get("path")
        require(isinstance(raw_path, str) and raw_path, "source %s needs a path" % source_id)
        path = Path(raw_path)
        if not path.is_absolute():
            path = ledger_dir / path
        item = {
            "source_id": source_id,
            "path": raw_path,
            "status": "readable",
            "uncertainty": source.get("uncertainty", "none recorded"),
        }
        try:
            texts[source_id] = path.read_text(encoding="utf-8")
        except FileNotFoundError:
            item["status"] = "missing"
            item["uncertainty"] = "Source file is missing; associated values cannot be quote-checked."
            texts[source_id] = None
        except (OSError, UnicodeError) as exc:
            item["status"] = "unreadable"
            item["uncertainty"] = "Source is unreadable: %s" % exc
            texts[source_id] = None
        records.append(item)
        by_id[source_id] = item
    return records, by_id, texts


def verify_values(ledger, source_by_id, source_texts):
    values = ledger.get("values")
    require(isinstance(values, list) and values, "ledger.values must be a nonempty array")
    value_by_id = {}
    records = []
    seen = set()
    for index, value in enumerate(values):
        require(isinstance(value, dict), "values[%d] must be an object" % index)
        value_id = value.get("value_id")
        require(isinstance(value_id, str) and value_id, "values[%d].value_id is required" % index)
        require(value_id not in seen, "duplicate value_id %s" % value_id)
        seen.add(value_id)
        provenance = value.get("provenance")
        require(provenance in PROVENANCE, "value %s has invalid provenance" % value_id)
        anchor = value.get("anchor")
        require(isinstance(anchor, dict), "value %s needs an anchor object" % value_id)
        for field in ("source_id", "locator", "row", "column", "condition", "unit"):
            require(isinstance(anchor.get(field), str) and anchor[field], "value %s anchor.%s is required" % (value_id, field))
        require(anchor["unit"] == value.get("unit"), "value %s top-level and anchor units differ" % value_id)
        source_id = anchor["source_id"]
        require(source_id in source_by_id, "value %s references unknown source %s" % (value_id, source_id))
        source_status = source_by_id[source_id]["status"]
        number = value.get("number")
        if provenance in ("not_reported", "missing"):
            require(number is None, "%s value %s must have number null" % (provenance, value_id))
            decimal_value = None
        else:
            decimal_value = as_decimal(number, "value %s.number" % value_id)
        quote = anchor.get("quote")
        quote_status = "not_applicable"
        locator_status = "not_applicable"
        method = "no quote required for a missing or not_reported value"
        char_start = anchor.get("char_start")
        char_end = anchor.get("char_end")
        if provenance not in ("not_reported", "missing"):
            require(isinstance(quote, str) and 0 < len(quote) <= 240, "value %s needs a short verbatim quote (1-240 characters)" % value_id)
            method = "exact Python Unicode code-point slice at anchor.char_start:char_end; no global substring fallback"
            if source_status != "readable":
                quote_status = "source_" + source_status
                locator_status = "locator_not_checked"
            elif char_start is None and char_end is None:
                quote_status = "locator_not_checked"
                locator_status = "locator_not_checked"
                method = "legacy locator has no verified quote region; char_start and char_end are required for an anchor pass"
            else:
                text = source_texts[source_id]
                valid_offsets = (
                    isinstance(char_start, int) and not isinstance(char_start, bool)
                    and isinstance(char_end, int) and not isinstance(char_end, bool)
                    and 0 <= char_start < char_end <= len(text)
                )
                if not valid_offsets:
                    quote_status = "invalid_region"
                    locator_status = "invalid_region"
                elif text[char_start:char_end] != quote:
                    quote_status = "region_not_matched"
                    locator_status = "region_not_matched"
                else:
                    quote_status = "matched"
                    locator_status = "region_verified"
        item = copy.deepcopy(value)
        item["canonical_unit"] = canonical_unit(value["unit"])
        item["quote_check"] = {
            "status": quote_status,
            "locator_status": locator_status,
            "quote": quote,
            "char_start": char_start,
            "char_end": char_end,
            "method": method,
        }
        item["source_status"] = source_status
        records.append(item)
        value_by_id[value_id] = item
    return records, value_by_id


def unit_compatible(operands):
    units = {item["canonical_unit"] for item in operands}
    return len(units) == 1


def operand_records(operand_spec, value_by_id):
    require(isinstance(operand_spec, dict) and operand_spec, "calculation operands must be a nonempty object")
    ordered = []
    for role, value_id in operand_spec.items():
        require(isinstance(role, str) and isinstance(value_id, str), "operand roles and IDs must be strings")
        require(value_id in value_by_id, "unknown operand value_id %s" % value_id)
        value = value_by_id[value_id]
        record = {
            "role": role,
            "value_id": value_id,
            "number": value.get("number"),
            "unit": value["unit"],
            "provenance": value["provenance"],
            "anchor": value["anchor"],
            "quote_check": value["quote_check"]["status"],
            "locator_check": value["quote_check"]["locator_status"],
        }
        ordered.append((role, value, record))
    return ordered


def compute(calc, value_by_id):
    calculation_id = calc.get("calculation_id")
    require(isinstance(calculation_id, str) and calculation_id, "calculation_id is required")
    operation = calc.get("operation")
    require(operation in OPERATIONS, "%s uses unsupported operation %r" % (calculation_id, operation))
    require(calc.get("provenance", "independently_calculated") == "independently_calculated", "%s provenance must be independently_calculated" % calculation_id)
    direction = calc.get("direction", "signed")
    require(direction in ("signed", "reduction"), "%s has invalid direction" % calculation_id)
    ordered = operand_records(calc.get("operands"), value_by_id)
    roles = [entry[0] for entry in ordered]
    if operation in ("sum", "product"):
        require(len(ordered) >= 1, "%s needs at least one operand" % calculation_id)
    else:
        require(len(ordered) == 2, "%s needs exactly two operands" % calculation_id)
        if operation == "division":
            require(set(roles) == {"numerator", "denominator"}, "%s needs numerator/denominator roles" % calculation_id)
        else:
            require(set(roles) == {"initial", "final"}, "%s needs initial/final roles" % calculation_id)
    expected = as_decimal(calc.get("expected"), "%s.expected" % calculation_id)
    tolerance = calc.get("tolerance")
    require(isinstance(tolerance, dict) and tolerance.get("type") in ("absolute", "relative"), "%s needs absolute/relative tolerance" % calculation_id)
    tolerance_value = as_decimal(tolerance.get("value"), "%s.tolerance.value" % calculation_id)
    require(tolerance_value >= 0, "%s tolerance cannot be negative" % calculation_id)
    rounding = calc.get("rounding")
    require(isinstance(rounding, dict), "%s needs rounding" % calculation_id)
    places = rounding.get("places")
    require(isinstance(places, int) and not isinstance(places, bool) and 0 <= places <= 12, "%s rounding.places must be an integer 0..12" % calculation_id)
    require(rounding.get("mode") in ROUNDING, "%s has unsupported rounding mode" % calculation_id)

    base = {
        "calculation_id": calculation_id,
        "operation": operation,
        "direction": direction,
        "provenance": "independently_calculated",
        "input_operands": [entry[2] for entry in ordered],
        "expected": plain(expected),
        "tolerance": copy.deepcopy(tolerance),
        "rounding": copy.deepcopy(rounding),
        "expected_basis": calc.get("expected_basis", "reader-supplied independent check"),
        "note": calc.get("note", ""),
    }
    unavailable = [entry[1] for entry in ordered if entry[1].get("number") is None]
    if unavailable:
        operand_ids = [entry["value_id"] for entry in unavailable]
        unavailable_status = "missing" if any(entry["provenance"] == "missing" for entry in unavailable) else "not_reported"
        base.update({
            "status": unavailable_status,
            "match": False,
            "formula": "not computed: operand value(s) %s: %s" % (unavailable_status, ", ".join(operand_ids)),
            "actual_raw": None,
            "actual_rounded": None,
            "discrepancy": None,
        })
        return base
    with localcontext() as context:
        context.prec = 50
        decimals = {role: as_decimal(value["number"], value["value_id"]) for role, value, _record in ordered}
        try:
            if operation in ("percent_relative_change", "percentage_point_difference", "ratio", "difference"):
                a = decimals["initial"]
                b = decimals["final"]
                pair = [entry[1] for entry in ordered]
                require(unit_compatible(pair), "%s operands must have the same unit" % calculation_id)
                if operation == "percent_relative_change":
                    require(a != 0, "%s initial value cannot be zero" % calculation_id)
                    numerator = (a - b) if direction == "reduction" else (b - a)
                    actual = Decimal(100) * numerator / abs(a)
                    unit = "percent"
                    formula = "100 * (%s %s %s) / abs(%s)" % (plain(a), "-" if direction == "reduction" else "-", plain(b), plain(a))
                    if direction == "signed":
                        formula = "100 * (%s - %s) / abs(%s)" % (plain(b), plain(a), plain(a))
                elif operation == "percentage_point_difference":
                    require(all(entry[1]["canonical_unit"] == "percent" for entry in ordered), "%s operands must be percentages" % calculation_id)
                    actual = (a - b) if direction == "reduction" else (b - a)
                    unit = "percentage_points"
                    formula = "%s - %s" % (plain(a), plain(b)) if direction == "reduction" else "%s - %s" % (plain(b), plain(a))
                elif operation == "difference":
                    actual = (a - b) if direction == "reduction" else (b - a)
                    unit = pair[0]["unit"]
                    formula = "%s - %s" % (plain(a), plain(b)) if direction == "reduction" else "%s - %s" % (plain(b), plain(a))
                else:
                    order = calc.get("ratio_order", "final_over_initial")
                    require(order in ("final_over_initial", "initial_over_final"), "%s has invalid ratio_order" % calculation_id)
                    numerator, denominator = (b, a) if order == "final_over_initial" else (a, b)
                    require(denominator != 0, "%s ratio denominator cannot be zero" % calculation_id)
                    actual = numerator / denominator
                    unit = "dimensionless"
                    formula = "%s / %s" % (plain(numerator), plain(denominator))
                    base["ratio_order"] = order
            elif operation == "division":
                a = decimals["numerator"]
                b = decimals["denominator"]
                require(b != 0, "%s denominator cannot be zero" % calculation_id)
                actual = a / b
                unit = calc.get("output_unit", "dimensionless")
                formula = "%s / %s" % (plain(a), plain(b))
            elif operation == "sum":
                require(unit_compatible([entry[1] for entry in ordered]), "%s operands must share units" % calculation_id)
                actual = sum(decimals.values(), Decimal(0))
                unit = ordered[0][1]["unit"]
                formula = " + ".join(plain(value) for value in decimals.values())
            else:
                actual = Decimal(1)
                for value in decimals.values():
                    actual *= value
                unit = calc.get("output_unit", " * ".join(entry[1]["unit"] for entry in ordered))
                formula = " * ".join(plain(value) for value in decimals.values())
        except InvalidOperation as exc:
            raise LedgerError("%s decimal operation failed: %s" % (calculation_id, exc))
        quantum = Decimal(1).scaleb(-places)
        rounded = actual.quantize(quantum, rounding=ROUNDING[rounding["mode"]])
        discrepancy = rounded - expected
        allowed = tolerance_value if tolerance["type"] == "absolute" else tolerance_value * abs(expected)
        match = abs(discrepancy) <= allowed
        anchor_failures = [
            entry[1]["value_id"] for entry in ordered
            if entry[1]["quote_check"]["status"] not in ("matched", "not_applicable")
        ]
        base.update({
            "status": "matched" if match else "mismatch",
            "match": match,
            "arithmetic_match": match,
            "formula": formula + " = " + plain(actual),
            "actual_raw": plain(actual),
            "actual_rounded": fixed(rounded, places),
            "output_unit": unit,
            "discrepancy": plain(discrepancy),
            "allowed_discrepancy": plain(allowed),
            "comparison": "abs(%s) <= %s" % (plain(discrepancy), plain(allowed)),
            "anchor_failures": anchor_failures,
        })
        if anchor_failures:
            base["status"] = "anchor_failed"
            base["match"] = False
        return base


def verify_calculations(ledger, value_by_id):
    calculations = ledger.get("calculations")
    require(isinstance(calculations, list) and calculations, "ledger.calculations must be a nonempty array")
    records = []
    seen = set()
    for calc in calculations:
        require(isinstance(calc, dict), "each calculation must be an object")
        calc_id = calc.get("calculation_id")
        require(calc_id not in seen, "duplicate calculation_id %s" % calc_id)
        seen.add(calc_id)
        records.append(compute(calc, value_by_id))
    return records


def reconcile(ledger, value_by_id):
    results = []
    conflicts = []
    for item in ledger.get("reconciliations", []):
        require(isinstance(item, dict), "reconciliation records must be objects")
        record = copy.deepcopy(item)
        ids = item.get("value_ids")
        require(isinstance(ids, list) and len(ids) >= 2, "reconciliation needs at least two value_ids")
        require(all(value_id in value_by_id for value_id in ids), "reconciliation references unknown value")
        declared = item.get("status")
        require(declared in ("consistent", "conflict", "not_checked", "unreadable"), "invalid reconciliation status")
        numeric = [value_by_id[value_id].get("number") for value_id in ids]
        units = [value_by_id[value_id]["canonical_unit"] for value_id in ids]
        equal = None
        if all(number is not None for number in numeric) and len(set(units)) == 1:
            equal = len({Decimal(number) for number in numeric}) == 1
        record["numbers"] = numeric
        record["units"] = units
        record["numeric_equality_after_unit_alignment"] = equal
        if declared == "consistent" and equal is False:
            record["status"] = "conflict"
            record["audit_note"] = "Declared consistent, but aligned numbers differ."
        if record["status"] == "conflict":
            conflicts.append(record)
        results.append(record)
    return results, conflicts


def should_make_visual(ledger, task_text, standalone):
    visual = ledger.get("visual_comparison", {})
    if not isinstance(visual, dict) or not visual.get("enabled", False):
        return False
    if standalone or ledger.get("numbers_matter", False):
        return True
    return bool(re.search(r"\b(figure|plot|chart|visual|comparison|compare)\b|图|绘图|比较", task_text or "", re.I))


def svg_document(visual, value_by_id, synthetic):
    series = visual.get("series")
    require(isinstance(series, list) and series, "enabled visual_comparison needs nonempty series")
    colors = ["#465f78", "#d06b4f", "#6a8b60", "#8b6a9e"]
    bars = []
    group_labels = []
    canonical_units = set()
    for group_index, group in enumerate(series):
        require(isinstance(group, dict), "visual series entries must be objects")
        label = group.get("label")
        require(isinstance(label, str) and label, "visual series label is required")
        group_labels.append(label)
        entries = group.get("bars")
        require(isinstance(entries, list) and 1 <= len(entries) <= 4, "each visual series needs 1..4 bars")
        for bar_index, bar in enumerate(entries):
            require(isinstance(bar, dict), "visual bars must be objects")
            value_id = bar.get("value_id")
            require(value_id in value_by_id, "visual references unknown value %s" % value_id)
            value = value_by_id[value_id]
            require(value.get("number") is not None, "visual cannot plot unavailable value %s" % value_id)
            decimal_value = as_decimal(value["number"], value_id)
            bar_label = bar.get("label", "series %d" % (bar_index + 1))
            require(isinstance(bar_label, str) and bar_label, "visual bar labels must be nonempty strings")
            canonical_units.add(value["canonical_unit"])
            bars.append({
                "group": group_index, "index": bar_index, "count": len(entries),
                "label": bar_label, "value_id": value_id, "number": plain(decimal_value),
                "unit": value["unit"], "value": decimal_value,
                "color": colors[bar_index % len(colors)],
            })
    require(len(canonical_units) == 1, "visual refuses mixed canonical units: %s" % sorted(canonical_units))
    axis_unit = next(iter(canonical_units))
    axis_label = visual.get("axis_label")
    if axis_label is None:
        axis_label = "Value (%%)" if axis_unit == "percent" else "Value (%s)" % axis_unit
    require(isinstance(axis_label, str) and 0 < len(axis_label) <= 80, "axis_label must be a nonempty string of at most 80 characters")
    if axis_unit == "percent":
        require(re.search(r"%|percent|percentage", axis_label, re.I), "percent axis_label must mention %, percent, or percentage")
    else:
        require(axis_unit.lower() in axis_label.lower(), "axis_label must mention the common canonical unit %s" % axis_unit)

    decimals = [bar["value"] for bar in bars]
    minimum = min(Decimal(0), min(decimals))
    maximum = max(Decimal(0), max(decimals))
    if minimum == maximum:
        axis_min, axis_max = Decimal(-1), Decimal(1)
    else:
        axis_min = minimum * Decimal("1.12") if minimum < 0 else minimum
        axis_max = maximum * Decimal("1.12") if maximum > 0 else maximum
    span = axis_max - axis_min
    require(span > 0, "visual axis span must be positive")

    left, right, top, bottom = 90, 950, 130, 440
    plot_height = bottom - top

    def y_position(number):
        fraction = float((number - axis_min) / span)
        return bottom - fraction * plot_height

    zero_y = y_position(Decimal(0))
    group_width = (right - left) / len(series)
    parts = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<svg xmlns="http://www.w3.org/2000/svg" width="1000" height="620" viewBox="0 0 1000 620" role="img" aria-labelledby="title desc">',
        '<title id="title">%sDerived numerical comparison</title>' % ("SYNTHETIC — " if synthetic else ""),
        '<desc id="desc">Signed bar chart generated solely from anchored ledger values. It is not an original figure and does not validate the source.</desc>',
        '<rect width="1000" height="620" fill="#fbfcfe"/>',
        '<style>text{font-family:Arial,Helvetica,sans-serif;fill:#172436}.small{font-size:14px}.label{font-size:16px}.value{font-size:15px;font-weight:bold}.tick{font-size:13px;fill:#526174}</style>',
        '<text x="50" y="42" font-size="24" font-weight="bold">%sNumerical comparison from extracted values</text>' % ("SYNTHETIC — " if synthetic else ""),
        '<text x="50" y="72" class="label" fill="#9b3b2e">DERIVED COMPARISON — NOT ORIGINAL; NOT PROOF OF SOURCE CORRECTNESS</text>',
        '<text x="50" y="101" class="small">Conditions and values are anchored in verification.json; inspect original page/crops separately.</text>',
    ]
    for tick in range(6):
        fraction = Decimal(tick) / Decimal(5)
        y = bottom - float(fraction) * plot_height
        tick_value = axis_min + span * fraction
        tick_text = "0.0" if tick_value == 0 else fixed(tick_value, 1)
        parts.append('<line x1="90" y1="%.2f" x2="950" y2="%.2f" stroke="#dce2ea" stroke-width="1"/>' % (y, y))
        parts.append('<text x="80" y="%.2f" text-anchor="end" class="tick">%s</text>' % (y + 4, tick_text))
    parts.extend([
        '<line x1="90" y1="130" x2="90" y2="440" stroke="#607085"/>',
        '<line x1="90" y1="%.2f" x2="950" y2="%.2f" stroke="#607085"/>' % (zero_y, zero_y),
        '<text x="28" y="285" transform="rotate(-90 28 285)" text-anchor="middle" class="label">%s</text>' % xml_escape(axis_label),
    ])
    for bar in bars:
        group = bar["group"]
        count = bar["count"]
        slot = group_width / (count + 0.65)
        bar_width = min(70.0, slot * 0.68)
        x = left + group * group_width + slot * (bar["index"] + 0.4)
        value = bar["value"]
        value_y = y_position(value)
        y = min(zero_y, value_y)
        bar_height = abs(value_y - zero_y)
        parts.append('<rect data-value-id="%s" data-unit="%s" x="%.2f" y="%.2f" width="%.2f" height="%.2f" rx="3" fill="%s"><title>%s: %s %s</title></rect>' % (
            xml_escape(bar["value_id"]), xml_escape(axis_unit), x, y, bar_width, bar_height, bar["color"],
            xml_escape(bar["label"]), xml_escape(bar["number"]), xml_escape(bar["unit"]),
        ))
        if value < 0:
            label_y = min(bottom - 4, value_y + 17)
        else:
            label_y = max(top + 14, value_y - 8)
        parts.append('<text x="%.2f" y="%.2f" text-anchor="middle" class="value">%s</text>' % (x + bar_width / 2, label_y, xml_escape(bar["number"])))
    for index, label in enumerate(group_labels):
        x = left + (index + 0.5) * group_width
        parts.append('<text x="%.2f" y="468" text-anchor="middle" class="label">%s</text>' % (x, xml_escape(label)))
    legend_labels = []
    for group in series:
        for bar in group["bars"]:
            label = bar.get("label", "series")
            if label not in legend_labels:
                legend_labels.append(label)
    for index, label in enumerate(legend_labels[:4]):
        x = 100 + index * 210
        parts.append('<rect x="%d" y="512" width="20" height="20" fill="%s"/>' % (x, colors[index]))
        parts.append('<text x="%d" y="528" class="label">%s</text>' % (x + 30, xml_escape(label)))
    parts.extend([
        '<text x="50" y="574" class="small">Arithmetic verification is independent; repeated measurements are not independent replicates.</text>',
        '<text x="50" y="598" class="small">No confidence intervals or statistical significance are inferred.</text>',
        '</svg>',
    ])
    return "\n".join(parts) + "\n"


def copy_original(raw_path, output_dir, stem):
    if raw_path is None:
        return {"status": "missing", "path": None}
    require(isinstance(raw_path, str) and raw_path, "original image path must be a string or null")
    source = Path(raw_path)
    if not source.is_file():
        return {"status": "missing", "path": str(source)}
    suffix = source.suffix if source.suffix else ".bin"
    destination = output_dir / (stem + suffix)
    if source.resolve() != destination.resolve():
        shutil.copyfile(str(source), str(destination))
    return {"status": "copied", "path": destination.name}


def make_visual(ledger, ledger_dir, value_by_id, output_dir, task_text, standalone):
    visual = ledger.get("visual_comparison", {})
    if not should_make_visual(ledger, task_text, standalone):
        return {"status": "not_run", "reason": "Task did not request a plot and numbers were not marked decision-critical."}, []
    derived_name = visual.get("derived_output", "comparison.svg")
    require(isinstance(derived_name, str) and Path(derived_name).name == derived_name and derived_name.endswith(".svg"), "derived_output must be a simple .svg filename")
    derived_path = output_dir / derived_name
    derived_path.write_text(svg_document(visual, value_by_id, bool(ledger.get("synthetic"))), encoding="utf-8")
    original_render = copy_original(visual.get("original_render"), output_dir, "original_page")
    original_crop = copy_original(visual.get("original_crop"), output_dir, "original_crop")
    review = copy.deepcopy(visual.get("original_review", {
        "status": "missing",
        "note": "No original-page visual review was supplied.",
    }))
    require(isinstance(review, dict), "original_review must be an object")
    review_status = review.get("status", "missing")
    require(review_status in ("consistent", "conflict", "partial", "unreadable", "not_reported", "missing"), "invalid original_review status")
    if review_status in ("consistent", "conflict", "partial"):
        require(original_render["status"] == "copied" or original_crop["status"] == "copied", "original visual agreement/conflict cannot be claimed without an original render or crop")
    result = {
        "status": "derived_created",
        "derived_path": derived_name,
        "original_render": original_render,
        "original_crop": original_crop,
        "original_review": review,
        "claim": "Derived plot of extracted values only; no correctness claim follows without original-render review.",
    }
    artifacts = [derived_name]
    for item in (original_render, original_crop):
        if item["status"] == "copied":
            artifacts.append(item["path"])
    return result, artifacts


def markdown_report(verification):
    lines = [
        "# Numerical verification" + (" — SYNTHETIC" if verification.get("synthetic") else ""),
        "",
        "**Status:** `%s`" % verification["status"],
        "**Ledger:** `%s`" % verification["ledger_id"],
        "",
        "Calculated values are `independently_calculated`; source values retain their own provenance. A derived comparison does not authenticate the original source.",
        "",
        "## Source values and anchors",
        "",
        "| Value | Number | Unit | Provenance | Row / column / condition | Quote check |",
        "|---|---:|---|---|---|---|",
    ]
    for value in verification["source_values"]:
        anchor = value["anchor"]
        location = "%s / %s / %s" % (anchor["row"], anchor["column"], anchor["condition"])
        number = value["provenance"] if value.get("number") is None else value["number"]
        lines.append("| %s | %s | %s | %s | %s | %s |" % (
            value["value_id"], number, value["unit"], value["provenance"], location,
            "%s/%s" % (value["quote_check"]["status"], value["quote_check"]["locator_status"]),
        ))
    lines.extend([
        "",
        "## Decimal calculations",
        "",
        "| Check | Operation | Raw → rounded | Expected | Tolerance | Result | Formula |",
        "|---|---|---:|---:|---|---|---|",
    ])
    for calc in verification["calculations"]:
        actual = calc.get("actual_raw")
        rounded = calc.get("actual_rounded")
        displayed = calc["status"] if actual is None else "%s → %s %s" % (actual, rounded, calc.get("output_unit", ""))
        tolerance = "%s %s" % (calc["tolerance"]["type"], calc["tolerance"]["value"])
        formula = calc["formula"].replace("|", "\\|")
        lines.append("| %s | %s (%s) | %s | %s | %s | %s | %s |" % (
            calc["calculation_id"], calc["operation"], calc["direction"], displayed,
            calc["expected"], tolerance, calc["status"], formula,
        ))
    lines.extend(["", "## Input anchors", ""])
    for calc in verification["calculations"]:
        lines.append("### %s" % calc["calculation_id"])
        for operand in calc["input_operands"]:
            anchor = operand["anchor"]
            lines.append("- `%s` (%s): %s; row `%s`; column `%s`; condition `%s`; unit `%s`; region `[%s:%s]`; quote: “%s”; quote/locator check `%s/%s`." % (
                operand["role"], operand["value_id"], anchor["locator"], anchor["row"],
                anchor["column"], anchor["condition"], anchor["unit"], anchor.get("char_start"), anchor.get("char_end"),
                anchor.get("quote") or operand["provenance"], operand["quote_check"], operand["locator_check"],
            ))
    lines.extend(["", "## Reconciliation", ""])
    if verification["reconciliations"]:
        for item in verification["reconciliations"]:
            lines.append("- `%s`: **%s** — %s Values: %s." % (
                item.get("reconciliation_id", "reconciliation"), item["status"], item.get("note", ""), item.get("numbers"),
            ))
    else:
        lines.append("- `not_reported`: no body/table/figure reconciliation records were supplied.")
    lines.extend(["", "## Visual comparison", "", "```json", json.dumps(verification["visual_comparison"], ensure_ascii=False, indent=2), "```", "", "## Limitations and uncertainty", ""])
    for item in verification.get("uncertainties", []):
        lines.append("- %s" % item)
    lines.extend([
        "- Decimal arithmetic checks formulas, not measurement quality or statistical independence.",
        "- OCR, source rounding, significant figures, unit conversion, and original-image legibility can limit extraction.",
        "- No confidence intervals, significance tests, or independence assumptions are generated.",
        "",
    ])
    return "\n".join(lines)


def json_equal(left, right):
    """JSON Schema equality: booleans are not numbers; numeric 1 equals 1.0."""
    if isinstance(left, bool) or isinstance(right, bool):
        return type(left) is type(right) and left == right
    if isinstance(left, (int, float)) and isinstance(right, (int, float)):
        return left == right
    if type(left) is not type(right):
        return False
    if isinstance(left, list):
        return len(left) == len(right) and all(json_equal(a, b) for a, b in zip(left, right))
    if isinstance(left, dict):
        return set(left) == set(right) and all(json_equal(left[key], right[key]) for key in left)
    return left == right


def resolve_ref(schema, root):
    seen = set()
    current = schema
    while isinstance(current, dict) and "$ref" in current:
        ref = current["$ref"]
        if not isinstance(ref, str) or not ref.startswith("#"):
            raise ContractError("only local JSON Pointer $ref values are supported: %r" % ref)
        if ref in seen:
            raise ContractError("circular $ref is not supported: %s" % ref)
        seen.add(ref)
        target = root
        pointer = ref[1:]
        if pointer:
            if not pointer.startswith("/"):
                raise ContractError("invalid local JSON Pointer $ref: %s" % ref)
            for raw_part in pointer[1:].split("/"):
                part = raw_part.replace("~1", "/").replace("~0", "~")
                try:
                    if isinstance(target, list):
                        target = target[int(part)]
                    else:
                        target = target[part]
                except (KeyError, IndexError, ValueError, TypeError):
                    raise ContractError("unresolved $ref: %s" % ref)
        if not isinstance(target, dict):
            raise ContractError("$ref must resolve to an object schema: %s" % ref)
        current = target
    return current


def audit_contract(schema):
    checks = []
    errors = []

    def check(condition, path, message):
        checks.append({"path": path, "check": message, "passed": bool(condition)})
        if not condition:
            errors.append("%s: %s" % (path, message))

    check(isinstance(schema, dict), "$", "contract must be an object schema")
    if not isinstance(schema, dict):
        raise ContractError("; ".join(errors))
    try:
        root_object = resolve_ref(schema, schema)
    except ContractError as exc:
        check(False, "$.$ref", str(exc))
        root_object = {}
    check(root_object.get("type") == "object", "$", "root type must be object")
    check(root_object.get("additionalProperties") is False, "$", "root additionalProperties must be false")
    properties = root_object.get("properties")
    check(isinstance(properties, dict) and bool(properties), "$", "root properties must be a nonempty object")
    required = root_object.get("required")
    check(isinstance(required, list) and all(isinstance(item, str) for item in required), "$.required", "required must be an array of strings")
    if isinstance(properties, dict) and isinstance(required, list) and all(isinstance(item, str) for item in required):
        check("case_id" in properties and "case_id" in required, "$", "case_id must be declared and required")
        if isinstance(properties.get("case_id"), dict):
            try:
                case_id_schema = resolve_ref(properties["case_id"], schema)
                check(case_id_schema.get("type") == "string", "$.properties.case_id", "case_id must be a string")
            except ContractError as exc:
                check(False, "$.properties.case_id", str(exc))
        check(set(required).issubset(properties), "$.required", "required keys must be declared properties")

    allowed_types = {"object", "array", "string", "number", "integer", "boolean", "null"}
    active = set()
    visited = set()

    def walk(node, path):
        if not isinstance(node, dict):
            check(False, path, "schema node must be an object")
            return
        identity = id(node)
        if identity in active:
            check(False, path, "circular schema references are not supported")
            return
        if identity in visited:
            return
        active.add(identity)
        unknown = sorted(set(node) - SCHEMA_KEYWORDS)
        check(not unknown, path, "unsupported schema keywords are rejected: %s" % unknown)
        for keyword, value in node.items():
            if keyword not in SCHEMA_KEYWORDS:
                continue
            if keyword in ("exclusiveMinimum", "exclusiveMaximum", "multipleOf", "minimum", "maximum"):
                check(isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value), path + "." + keyword, "numeric constraint must be a finite JSON number")
            elif keyword in ("minItems", "maxItems", "minLength", "maxLength"):
                check(isinstance(value, int) and not isinstance(value, bool) and value >= 0, path + "." + keyword, "size constraint must be a nonnegative integer")
        if "multipleOf" in node and isinstance(node["multipleOf"], (int, float)) and not isinstance(node["multipleOf"], bool):
            check(node["multipleOf"] > 0, path + ".multipleOf", "multipleOf must be greater than zero")
        for lower, upper in (("minItems", "maxItems"), ("minLength", "maxLength")):
            if lower in node and upper in node and isinstance(node[lower], int) and isinstance(node[upper], int):
                check(node[lower] <= node[upper], path, "%s cannot exceed %s" % (lower, upper))
        if "uniqueItems" in node:
            check(isinstance(node["uniqueItems"], bool), path + ".uniqueItems", "uniqueItems must be boolean")
        if "pattern" in node:
            check(isinstance(node["pattern"], str), path + ".pattern", "pattern must be a string")
            if isinstance(node["pattern"], str):
                try:
                    re.compile(node["pattern"])
                except re.error as exc:
                    check(False, path + ".pattern", "invalid stdlib regular expression: %s" % exc)
        if "enum" in node:
            enum = node["enum"]
            check(isinstance(enum, list) and bool(enum), path + ".enum", "enum must be a nonempty array")
            if isinstance(enum, list):
                duplicates = any(json_equal(enum[i], enum[j]) for i in range(len(enum)) for j in range(i))
                check(not duplicates, path + ".enum", "enum values must be unique using JSON-aware equality")
        if "$ref" in node:
            check(set(node).issubset(SCHEMA_ANNOTATIONS | {"$ref"}), path, "$ref siblings other than annotations are not supported")
            try:
                target = resolve_ref(node, schema)
                if target is not node:
                    walk(target, path + ".$ref")
            except ContractError as exc:
                check(False, path + ".$ref", str(exc))
        combinators = [key for key in ("anyOf", "oneOf") if key in node]
        if combinators:
            check(len(combinators) == 1, path, "anyOf and oneOf cannot be combined at one schema node")
            check(set(node).issubset(SCHEMA_ANNOTATIONS | set(combinators)), path, "combinator siblings other than annotations are not supported")
            for keyword in combinators:
                branches = node[keyword]
                check(isinstance(branches, list) and bool(branches), path + "." + keyword, "combinator must be a nonempty schema array")
                if isinstance(branches, list):
                    for index, branch in enumerate(branches):
                        walk(branch, "%s.%s[%d]" % (path, keyword, index))
        node_type = node.get("type")
        types = node_type if isinstance(node_type, list) else [node_type]
        if "$ref" not in node and not combinators:
            check(bool(types) and all(isinstance(item, str) and item in allowed_types for item in types), path + ".type", "unsupported or missing schema type")
        if isinstance(node_type, list):
            check(all(isinstance(item, str) for item in node_type) and len(node_type) == len(set(node_type)) and bool(node_type), path + ".type", "type array must be nonempty, unique strings")
        if "object" in types:
            props = node.get("properties")
            req = node.get("required", [])
            check(isinstance(props, dict), path + ".properties", "object properties are required")
            check(node.get("additionalProperties") is False, path + ".additionalProperties", "object additionalProperties must be false")
            req_valid = (
                isinstance(req, list) and all(isinstance(item, str) for item in req)
                and len(req) == len(set(req))
            )
            check(req_valid, path + ".required", "required must be a unique string array")
            if isinstance(props, dict):
                check(set(req).issubset(props) if req_valid else False, path + ".required", "required keys must be declared")
                for key, child in props.items():
                    check(isinstance(key, str), path + ".properties", "property names must be strings")
                    walk(child, path + ".properties." + str(key))
        if "array" in types:
            check(isinstance(node.get("items"), dict), path + ".items", "array item schema is required")
            if isinstance(node.get("items"), dict):
                walk(node["items"], path + ".items")
        for definitions_key in ("$defs", "definitions"):
            if definitions_key in node:
                definitions = node[definitions_key]
                check(isinstance(definitions, dict), path + "." + definitions_key, "definitions must be an object")
                if isinstance(definitions, dict):
                    for name, child in definitions.items():
                        walk(child, "%s.%s.%s" % (path, definitions_key, name))
        active.remove(identity)
        visited.add(identity)

    walk(schema, "$")
    if errors:
        raise ContractError("invalid output_contract: " + "; ".join(errors))
    return {"status": "passed", "checks": checks}


def schema_types(schema, root=None):
    node = resolve_ref(schema, root) if root is not None else schema
    value = node.get("type")
    return value if isinstance(value, list) else [value]


def select_schema(schema, value, root, key=""):
    node = resolve_ref(schema, root)
    combinators = [name for name in ("anyOf", "oneOf") if name in node]
    if not combinators:
        return node
    branches = node[combinators[0]]
    for branch in branches:
        candidate = resolve_ref(branch, root)
        if not validate_instance(value, candidate, root=root):
            return candidate
    # If the response does not validate yet, choose a branch with a compatible shape
    # so fitting can produce useful, contract-checked output rather than guessing freely.
    for branch in branches:
        candidate = resolve_ref(branch, root)
        types = schema_types(candidate, root)
        if ((isinstance(value, dict) and "object" in types)
                or (isinstance(value, list) and "array" in types)
                or (isinstance(value, str) and "string" in types)
                or (isinstance(value, bool) and "boolean" in types)
                or (value is None and "null" in types)
                or (isinstance(value, (int, float)) and not isinstance(value, bool) and ("number" in types or "integer" in types))):
            return candidate
    return resolve_ref(branches[0], root)


def skeleton(schema, key="", root=None):
    if root is None:
        root = schema
    node = resolve_ref(schema, root)
    if "const" in node:
        return copy.deepcopy(node["const"])
    if "enum" in node and node["enum"]:
        for candidate in ("partial", "not_reported", "missing"):
            if any(json_equal(candidate, option) for option in node["enum"]):
                return copy.deepcopy(candidate)
        return copy.deepcopy(node["enum"][0])
    if "anyOf" in node or "oneOf" in node:
        branches = node.get("anyOf", node.get("oneOf"))
        candidates = [skeleton(branch, key, root) for branch in branches]
        for candidate in candidates:
            if not validate_instance(candidate, node, root=root):
                return candidate
        return candidates[0]
    types = schema_types(node, root)
    if "null" in types and len(types) > 1:
        return None
    kind = types[0]
    if kind == "object":
        return {name: skeleton(child, name, root) for name, child in node.get("properties", {}).items()}
    if kind == "array":
        count = node.get("minItems", 0)
        return [skeleton(node["items"], key, root) for _ in range(count)]
    if kind == "string":
        if key == "status":
            return "partial"
        if key in ("answer", "summary", "detail", "note", "visual_comparison"):
            return "not_reported: no direct response content was supplied"
        return "not_reported"
    if kind == "null":
        return None
    return None


def status_value(schema, desired, root):
    node = resolve_ref(schema, root)
    choices = []
    if "const" in node:
        choices = [node["const"]]
    elif "enum" in node:
        choices = node["enum"]
    else:
        for combinator in ("anyOf", "oneOf"):
            for branch in node.get(combinator, []):
                branch_node = resolve_ref(branch, root)
                if "const" in branch_node:
                    choices.append(branch_node["const"])
                else:
                    choices.extend(branch_node.get("enum", []))
    if not choices:
        return desired
    if desired == "complete":
        preference = ("complete", "success", "partial")
    elif desired == "failed":
        preference = ("failed", "partial")
    else:
        preference = ("partial",)
    for candidate in preference:
        if any(isinstance(option, str) and option == candidate for option in choices):
            return candidate
    raise ContractError("status schema does not permit honest %s status; declared values are %r" % (desired, choices))


def deep_overlay(base, overlay):
    if isinstance(base, dict) and isinstance(overlay, dict):
        result = copy.deepcopy(base)
        for key, value in overlay.items():
            result[key] = deep_overlay(result[key], value) if key in result else copy.deepcopy(value)
        return result
    return copy.deepcopy(overlay)


def fit_value(value, schema, key="", root=None):
    if root is None:
        root = schema
    if value is None:
        return None
    node = select_schema(schema, value, root, key)
    types = schema_types(node, root)
    kind = next((item for item in types if item != "null"), types[0])
    if kind == "object" and isinstance(value, dict):
        return {
            name: fit_value(value.get(name, skeleton(child, name, root)), child, name, root)
            for name, child in node.get("properties", {}).items()
        }
    if kind == "array":
        values = value if isinstance(value, list) else [value]
        return [fit_value(item, node["items"], key, root) for item in values]
    if kind == "string":
        if isinstance(value, str):
            return value
        if isinstance(value, bool):
            return "true" if value else "false"
        if isinstance(value, (dict, list)):
            return json.dumps(value, ensure_ascii=False, sort_keys=True)
        return str(value)
    if kind == "boolean" and isinstance(value, bool):
        return value
    if kind in ("number", "integer") and isinstance(value, (int, float)) and not isinstance(value, bool):
        return value
    if kind in ("number", "integer") and isinstance(value, str):
        try:
            decimal_value = Decimal(value)
            if kind == "integer" and decimal_value == decimal_value.to_integral_value():
                return int(decimal_value)
            if kind == "number":
                number = float(decimal_value)
                return number if math.isfinite(number) else None
        except InvalidOperation:
            pass
    return value


def calculation_projection(calc):
    projected = copy.deepcopy(calc)
    projected.update({
        "finding_id": calc["calculation_id"],
        "actual": calc.get("actual_rounded") if calc.get("actual_rounded") is not None else calc["status"],
        "calculation_match": calc.get("match"),
        "input_anchors": [
            "%s | row=%s | column=%s | condition=%s | unit=%s | char_start=%s | char_end=%s | quote_check=%s | quote=%s" % (
                entry["anchor"]["locator"], entry["anchor"]["row"], entry["anchor"]["column"],
                entry["anchor"]["condition"], entry["anchor"]["unit"], entry["anchor"].get("char_start"),
                entry["anchor"].get("char_end"), entry["quote_check"], entry["anchor"].get("quote") or entry["provenance"],
            ) for entry in calc["input_operands"]
        ],
    })
    return projected


def adapt_records(records, schema, kind="", root=None):
    if root is None:
        root = schema
    node = select_schema(schema, records, root, kind)
    if node.get("type") != "array":
        return records
    item_schema = node["items"]
    sample = records[0] if records else skeleton(item_schema, kind, root)
    item_node = select_schema(item_schema, sample, root, kind)
    if item_node.get("type") == "string":
        if kind == "sources":
            return [record["source_id"] for record in records]
        if kind == "numerical_findings":
            return [record["calculation_id"] for record in records]
        if kind == "artifacts":
            return [str(record) for record in records]
        return [json.dumps(record, ensure_ascii=False, sort_keys=True) if isinstance(record, dict) else str(record) for record in records]
    if item_node.get("type") == "object":
        return [fit_value(record, item_schema, kind, root) for record in records]
    return records


def inject_known(result, schema, context, key="", root=None):
    if root is None:
        root = schema
    node = select_schema(schema, result, root, key)
    if not isinstance(result, dict) or node.get("type") != "object":
        return result
    for name, child_schema in node.get("properties", {}).items():
        value = result.get(name)
        child_node = select_schema(child_schema, value, root, name)
        if name == "case_id":
            result[name] = context["case_id"]
        elif name == "status" and "string" in schema_types(child_node, root):
            result[name] = status_value(child_schema, context["run_status"], root)
        elif name == "numerical_findings":
            records = [calculation_projection(item) for item in context["verification"]["calculations"]]
            result[name] = fit_value(adapt_records(records, child_schema, name, root), child_schema, name, root)
        elif name == "sources":
            result[name] = fit_value(adapt_records(context["verification"]["sources"], child_schema, name, root), child_schema, name, root)
        elif name in ("uncertainty", "uncertainties"):
            result[name] = fit_value(context["verification"]["uncertainties"], child_schema, name, root)
        elif name == "change_records":
            result[name] = fit_value(adapt_records(context["verification"]["change_records"], child_schema, name, root), child_schema, name, root)
        elif name == "artifacts":
            result[name] = fit_value(context["artifacts"], child_schema, name, root)
        elif name == "verification" and isinstance(value, dict):
            merged = deep_overlay(context["verification"]["summary"], value)
            result[name] = fit_value(merged, child_schema, name, root)
        elif child_node.get("type") == "object":
            result[name] = inject_known(value, child_schema, context, name, root)
    return result


def validate_instance(value, schema, path="$", errors=None, root=None):
    if errors is None:
        errors = []
    if root is None:
        root = schema
    try:
        node = resolve_ref(schema, root)
    except ContractError as exc:
        errors.append("%s %s" % (path, exc))
        return errors
    # References are resolved above; siblings are annotations by contract audit.
    for combinator in ("anyOf", "oneOf"):
        if combinator in node:
            matches = 0
            branch_errors = []
            for index, branch in enumerate(node[combinator]):
                candidate_errors = validate_instance(value, branch, "%s.%s[%d]" % (path, combinator, index), [], root)
                if not candidate_errors:
                    matches += 1
                else:
                    branch_errors.extend(candidate_errors)
            valid = matches >= 1 if combinator == "anyOf" else matches == 1
            if not valid:
                errors.append("%s %s matched %d branches" % (path, combinator, matches))
                if matches == 0:
                    errors.extend(branch_errors)
            return errors
    types = schema_types(node, root)
    actual_ok = False
    for kind in types:
        if kind == "object" and isinstance(value, dict):
            actual_ok = True
        elif kind == "array" and isinstance(value, list):
            actual_ok = True
        elif kind == "string" and isinstance(value, str):
            actual_ok = True
        elif kind == "boolean" and isinstance(value, bool):
            actual_ok = True
        elif kind == "integer" and isinstance(value, int) and not isinstance(value, bool):
            actual_ok = True
        elif kind == "number" and isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value):
            actual_ok = True
        elif kind == "null" and value is None:
            actual_ok = True
    if not actual_ok:
        errors.append("%s expected type %s, got %s" % (path, types, type(value).__name__))
        return errors
    if "const" in node and not json_equal(value, node["const"]):
        errors.append("%s does not equal const %r" % (path, node["const"]))
    if "enum" in node and not any(json_equal(value, option) for option in node["enum"]):
        errors.append("%s value %r is outside enum" % (path, value))
    if "object" in types and isinstance(value, dict):
        properties = node.get("properties", {})
        required = node.get("required", [])
        for key in required:
            if key not in value:
                errors.append("%s missing required key %s" % (path, key))
        if set(value) != set(properties):
            extras = sorted(set(value) - set(properties))
            missing = sorted(set(properties) - set(value))
            if extras:
                errors.append("%s has additional properties %s" % (path, extras))
            if missing:
                errors.append("%s does not contain all declared contract fields %s" % (path, missing))
        if node.get("additionalProperties") is not False:
            errors.append("%s lacks additionalProperties false" % path)
        for key, child in properties.items():
            if key in value:
                validate_instance(value[key], child, path + "." + key, errors, root)
    if "array" in types and isinstance(value, list):
        if len(value) < node.get("minItems", 0):
            errors.append("%s has fewer than minItems" % path)
        if "maxItems" in node and len(value) > node["maxItems"]:
            errors.append("%s exceeds maxItems" % path)
        if node.get("uniqueItems"):
            for index, item in enumerate(value):
                for earlier in range(index):
                    if json_equal(item, value[earlier]):
                        errors.append("%s items %d and %d are not unique using JSON-aware equality" % (path, earlier, index))
        for index, item in enumerate(value):
            validate_instance(item, node["items"], "%s[%d]" % (path, index), errors, root)
    if "string" in types and isinstance(value, str):
        if len(value) < node.get("minLength", 0):
            errors.append("%s is shorter than minLength" % path)
        if "maxLength" in node and len(value) > node["maxLength"]:
            errors.append("%s exceeds maxLength" % path)
        if "pattern" in node and re.search(node["pattern"], value) is None:
            errors.append("%s does not match pattern %r" % (path, node["pattern"]))
    if ("number" in types or "integer" in types) and isinstance(value, (int, float)) and not isinstance(value, bool):
        if "minimum" in node and value < node["minimum"]:
            errors.append("%s is below minimum" % path)
        if "maximum" in node and value > node["maximum"]:
            errors.append("%s exceeds maximum" % path)
        if "exclusiveMinimum" in node and value <= node["exclusiveMinimum"]:
            errors.append("%s is not above exclusiveMinimum" % path)
        if "exclusiveMaximum" in node and value >= node["exclusiveMaximum"]:
            errors.append("%s is not below exclusiveMaximum" % path)
        if "multipleOf" in node:
            try:
                remainder = Decimal(str(value)) % Decimal(str(node["multipleOf"]))
                if remainder != 0:
                    errors.append("%s is not a multiple of %s" % (path, node["multipleOf"]))
            except InvalidOperation:
                errors.append("%s multipleOf comparison failed" % path)
    return errors


def make_changes(verification):
    records = []
    sequence = 1
    for source in verification["sources"]:
        records.append({"sequence": sequence, "action": "source_read", "detail": "%s: %s" % (source["source_id"], source["status"])})
        sequence += 1
    for calc in verification["calculations"]:
        records.append({"sequence": sequence, "action": "decimal_calculation", "detail": "%s: %s" % (calc["calculation_id"], calc["status"])})
        sequence += 1
    for conflict in verification["conflicts"]:
        records.append({"sequence": sequence, "action": "conflict_retained", "detail": conflict.get("reconciliation_id", "reconciliation conflict")})
        sequence += 1
    if verification["visual_comparison"].get("status") == "derived_created":
        records.append({"sequence": sequence, "action": "derived_visual_created", "detail": "comparison.svg is derived only; original review=%s" % verification["visual_comparison"]["original_review"].get("status", "missing")})
    return records


def execute_ledger(ledger_path, output_dir, task_text="", standalone=True, supplied_ledger=None):
    ledger_path = Path(ledger_path)
    ledger = supplied_ledger if supplied_ledger is not None else read_json(ledger_path)
    require(isinstance(ledger, dict), "ledger root must be an object")
    require(isinstance(ledger.get("ledger_id"), str) and ledger["ledger_id"], "ledger_id is required")
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    sources, source_by_id, texts = source_records(ledger, ledger_path.parent)
    values, value_by_id = verify_values(ledger, source_by_id, texts)
    calculations = verify_calculations(ledger, value_by_id)
    reconciliations, conflicts = reconcile(ledger, value_by_id)
    visual, visual_artifacts = make_visual(ledger, ledger_path.parent, value_by_id, output_dir, task_text, standalone)
    if visual.get("original_review", {}).get("status") == "conflict":
        conflicts.append({
            "reconciliation_id": "original_visual_review",
            "status": "conflict",
            "value_ids": visual["original_review"].get("checked_values", []),
            "note": visual["original_review"].get("note", "Original visual review reported a conflict."),
        })
    quote_failures = [value["value_id"] for value in values if value["quote_check"]["status"] not in ("matched", "not_applicable")]
    mismatches = [calc["calculation_id"] for calc in calculations if calc["status"] == "mismatch"]
    failed_calcs = [calc["calculation_id"] for calc in calculations if calc["status"] not in ("matched", "mismatch")]
    source_failures = [source["source_id"] for source in sources if source["status"] != "readable"]
    if failed_calcs and not mismatches and len(failed_calcs) == len(calculations):
        status = "failed"
    else:
        status = "partial" if mismatches or failed_calcs or conflicts or quote_failures or source_failures else "passed"
    uncertainties = list(ledger.get("uncertainties", []))
    limitations = ledger.get("limitations", [])
    require(isinstance(uncertainties, list) and all(isinstance(item, str) for item in uncertainties), "uncertainties must be an array of strings")
    require(isinstance(limitations, list) and all(isinstance(item, str) for item in limitations), "limitations must be an array of strings")
    uncertainties.extend(item for item in limitations if item not in uncertainties)
    if quote_failures:
        uncertainties.append("Quote/source checks failed or remain unavailable for: " + ", ".join(quote_failures))
    inferences = ledger.get("inferences", [])
    require(isinstance(inferences, list), "inferences must be an array")
    for inference in inferences:
        require(isinstance(inference, dict) and inference.get("provenance") == "reader_inference", "every inference must be labelled reader_inference")
    verification = {
        "schema_version": SCHEMA_VERSION,
        "ledger_id": ledger["ledger_id"],
        "synthetic": bool(ledger.get("synthetic", False)),
        "status": status,
        "sources": sources,
        "source_values": values,
        "calculations": calculations,
        "reconciliations": reconciliations,
        "conflicts": conflicts,
        "reader_inferences": inferences,
        "visual_comparison": visual,
        "uncertainties": uncertainties,
        "change_records": [],
        "summary": {
            "calculations_total": len(calculations),
            "matched": len(calculations) - len(mismatches) - len(failed_calcs),
            "mismatches": mismatches,
            "not_computed": failed_calcs,
            "quote_failures": quote_failures,
            "source_failures": source_failures,
            "conflicts": [item.get("reconciliation_id", "conflict") for item in conflicts],
        },
        "contract_audit": None,
    }
    verification["change_records"] = make_changes(verification)
    write_json(output_dir / "verification.json", verification)
    (output_dir / "verification.md").write_text(markdown_report(verification), encoding="utf-8")
    return verification, ["verification.json", "verification.md"] + visual_artifacts


def run_case(args):
    case_path = Path(args.case)
    case = read_json(case_path)
    require(isinstance(case, dict), "case root must be an object")
    case_id = case.get("case_id")
    require(isinstance(case_id, str) and case_id, "case_id must be a nonempty string")
    contract = case.get("output_contract")
    contract_audit = audit_contract(contract)
    try:
        task_text = Path(args.task).read_text(encoding="utf-8")
    except FileNotFoundError:
        raise LedgerError("missing task file: %s" % args.task)
    except (OSError, UnicodeError) as exc:
        raise LedgerError("unreadable task file %s: %s" % (args.task, exc))
    materials = Path(args.materials)
    if not materials.is_dir():
        raise LedgerError("materials directory is missing or unreadable: %s" % materials)
    if "numeric_ledger" in case:
        ledger = case["numeric_ledger"]
        ledger_path = case_path
    else:
        ledger_ref = case.get("numeric_ledger_path")
        require(isinstance(ledger_ref, str) and ledger_ref, "case needs numeric_ledger or numeric_ledger_path")
        ledger_path = Path(ledger_ref)
        if not ledger_path.is_absolute():
            ledger_path = case_path.parent / ledger_path
        ledger = read_json(ledger_path)
    output_dir = Path(args.output_dir)
    verification, artifacts = execute_ledger(ledger_path, output_dir, task_text, standalone=False, supplied_ledger=ledger)
    verification["contract_audit"] = contract_audit
    response = case.get("response") if args.response is None else read_json(args.response)
    response_supplied = response is not None
    if response is not None:
        require(isinstance(response, dict), "response root must be an object")
    result = skeleton(contract, root=contract)
    if response is not None:
        result = deep_overlay(result, response)
    if verification["status"] == "failed":
        run_status = "failed"
    else:
        run_status = "complete" if response_supplied and verification["status"] == "passed" else "partial"
    context = {
        "case_id": case_id,
        "run_status": run_status,
        "verification": verification,
        "artifacts": artifacts + ["result.json"],
    }
    result = inject_known(result, contract, context, root=contract)
    errors = validate_instance(result, contract, root=contract)
    if errors:
        raise ContractError("result contract validation failed: " + "; ".join(errors))
    verification["change_records"].append({
        "sequence": len(verification["change_records"]) + 1,
        "action": "result_ready",
        "detail": "case_id %s; status %s; recursive contract validation passed" % (case_id, run_status),
    })
    write_json(output_dir / "verification.json", verification)
    (output_dir / "verification.md").write_text(markdown_report(verification), encoding="utf-8")
    write_json(output_dir / "result.json", result)
    if args.fail_on_mismatch and verification["status"] != "passed":
        return 1
    return 0


def parser():
    root = argparse.ArgumentParser(description="Verify anchored numerical tuples using Decimal and safe operations.")
    sub = root.add_subparsers(dest="command", required=True)
    verify = sub.add_parser("verify", help="Run a standalone numeric ledger")
    verify.add_argument("--ledger", required=True)
    verify.add_argument("--output-dir", required=True)
    verify.add_argument("--fail-on-mismatch", action="store_true")
    run = sub.add_parser("run", help="Run a case and emit a contract-validated result.json")
    run.add_argument("--case", default="/input/case.json")
    run.add_argument("--task", default="/input/task.md")
    run.add_argument("--materials", default="/input/materials")
    run.add_argument("--output-dir", default="/app/output")
    run.add_argument("--response", help="Optional contract-specific direct-answer response JSON")
    run.add_argument("--fail-on-mismatch", action="store_true")
    return root


def main(argv=None):
    args = parser().parse_args(argv)
    try:
        if args.command == "verify":
            verification, _ = execute_ledger(args.ledger, args.output_dir, standalone=True)
            if args.fail_on_mismatch and verification["status"] != "passed":
                return 1
            return 0
        return run_case(args)
    except (LedgerError, ContractError) as exc:
        sys.stderr.write("numerical-replication-desk: ERROR: %s\n" % exc)
        return 2


if __name__ == "__main__":
    sys.exit(main())
