#!/usr/bin/env python3
"""Exact quantitative claim ledger; Python 3.9+, standard library only."""

import argparse
from decimal import Decimal, InvalidOperation, ROUND_HALF_EVEN, ROUND_HALF_UP, localcontext
from fractions import Fraction
import json
import os
from pathlib import Path
import re
import sys
import time

VERSION = "1.0.0"
RESULT_FIELDS = {
    "case_id", "status", "assertion_results", "summary", "sources",
    "uncertainty", "change_records", "run_metadata", "artifacts",
}
CALCULATION_FIELDS = {
    "case_id", "status", "calculations", "direct_assertions",
    "qualitative_assertions", "unresolved", "summary",
}
OPERATIONS = {
    "share", "ratio_percent_change", "relative_cpu_time_change",
    "sum_reconciliation", "residual",
}


class DataError(Exception):
    """An expected input, evidence, semantic, or reconciliation error."""


def load_json(path):
    def invalid_constant(token):
        raise DataError("non-finite JSON number is forbidden: " + token)
    try:
        with open(path, "r", encoding="utf-8") as handle:
            return json.load(
                handle, parse_float=Decimal, parse_int=Decimal,
                parse_constant=invalid_constant,
            )
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise DataError("cannot read JSON {}: {}".format(path, exc)) from exc


def require_dict(value, label):
    if not isinstance(value, dict):
        raise DataError(label + " must be an object")
    return value


def require_list(value, label):
    if not isinstance(value, list):
        raise DataError(label + " must be an array")
    return value


def nonempty(value, label):
    if not isinstance(value, str) or not value.strip():
        raise DataError(label + " must be a non-empty string")
    return value.strip()


def decimal_value(value, label):
    if isinstance(value, bool) or value is None:
        raise DataError(label + " is missing or is not numeric")
    if not isinstance(value, (str, Decimal)):
        raise DataError(label + " must be a decimal string")
    try:
        number = Decimal(str(value).strip())
    except (InvalidOperation, ValueError) as exc:
        raise DataError(label + " is not a valid decimal") from exc
    if not number.is_finite():
        raise DataError(label + " must be finite")
    return number


def fraction_value(value, label):
    return Fraction(decimal_value(value, label))


def fraction_text(value):
    return "{}/{}".format(value.numerator, value.denominator)


def atomic_write(path, payload):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    with open(temporary, "w", encoding="utf-8", newline="\n") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2, sort_keys=True)
        handle.write("\n")
    os.replace(str(temporary), str(path))


def parse_contract(path):
    try:
        text = Path(path).read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        raise DataError("cannot read task.md: " + str(exc)) from exc
    match = re.search(
        r"<!--\s*OUTPUT_CONTRACT_START\s*-->(.*?)<!--\s*OUTPUT_CONTRACT_END\s*-->",
        text, re.DOTALL,
    )
    if not match:
        raise DataError("task.md lacks output_contract markers")
    block = re.search(r"```json\s*(\{.*?\})\s*```", match.group(1), re.DOTALL)
    if not block:
        raise DataError("output_contract must contain one JSON fenced object")
    try:
        contract = json.loads(block.group(1))
    except json.JSONDecodeError as exc:
        raise DataError("invalid output_contract JSON: " + str(exc)) from exc
    require_dict(contract, "output_contract")
    result = contract.get("required_result_fields")
    calculations = contract.get("required_calculation_fields")
    require_list(result, "required_result_fields")
    require_list(calculations, "required_calculation_fields")
    for field in result:
        if field not in RESULT_FIELDS:
            raise DataError("unsupported required result field: " + str(field))
    for field in calculations:
        if field not in CALCULATION_FIELDS:
            raise DataError("unsupported required calculations field: " + str(field))
    if "case_id" not in result or "case_id" not in calculations:
        raise DataError("both output contracts must require case_id")
    if len(set(result)) != len(result) or len(set(calculations)) != len(calculations):
        raise DataError("output_contract fields must be unique")
    return {"result": result, "calculations": calculations}


def parse_resources(path):
    values = {
        "limits": {"max_requests": 64, "max_seconds": 900},
        "paths": {"work_dir": "/app/work", "output_dir": "/app/output"},
    }
    if path is None:
        return values
    try:
        lines = Path(path).read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeError) as exc:
        raise DataError("cannot read resources.yaml: " + str(exc)) from exc
    section = None
    for line_number, raw in enumerate(lines, 1):
        if not raw.strip() or raw.lstrip().startswith("#"):
            continue
        if "\t" in raw:
            raise DataError("resources.yaml tabs are unsupported")
        indent = len(raw) - len(raw.lstrip(" "))
        stripped = raw.strip()
        if indent == 0:
            if stripped == "version: 1":
                section = None
                continue
            if not stripped.endswith(":"):
                raise DataError("resources.yaml line {} must start a section or be version: 1".format(line_number))
            section = stripped[:-1]
            if section not in values:
                raise DataError("unsupported resources section: " + section)
        elif indent == 2 and section and ":" in stripped:
            key, raw_value = stripped.split(":", 1)
            key, raw_value = key.strip(), raw_value.strip()
            if key not in values[section] or not raw_value:
                raise DataError("unsupported resources key at line {}".format(line_number))
            values[section][key] = raw_value
        else:
            raise DataError("resources.yaml supports only two indentation levels")
    try:
        values["limits"]["max_requests"] = int(values["limits"]["max_requests"])
        values["limits"]["max_seconds"] = int(values["limits"]["max_seconds"])
    except (TypeError, ValueError) as exc:
        raise DataError("resource limits must be integers") from exc
    if not 0 <= values["limits"]["max_requests"] <= 64:
        raise DataError("max_requests must be between 0 and 64")
    if not 0 < values["limits"]["max_seconds"] <= 900:
        raise DataError("max_seconds must be between 1 and 900")
    return values


class Ledger:
    def __init__(self, case, contract, resources, work_root, output_root):
        self.case = require_dict(case, "case")
        self.case_id = nonempty(self.case.get("case_id"), "case_id")
        self.contract = contract
        self.resources = resources
        self.work_root = Path(work_root)
        self.output_root = Path(output_root)
        self.deadline = time.monotonic() + resources["limits"]["max_seconds"]
        self.sources = require_list(self.case.get("sources"), "sources")
        self.evidence = require_list(self.case.get("evidence"), "evidence")
        self.assertions = require_list(self.case.get("assertions"), "assertions")
        self.source_by_id = {}
        self.evidence_by_id = {}
        self.calculations = []
        self.direct_assertions = []
        self.qualitative_assertions = []
        self.assertion_results = []
        self.unresolved = []
        self.change_records = []
        self.uncertainty = [{
            "code": "semantic_scope_review",
            "message": "Scope compatibility is explicit and source-bound; no missing value is inferred.",
        }]
        self.status = "partial"

    def source_summary(self):
        used = {item["evidence_id"]: [] for item in self.evidence if isinstance(item, dict) and "evidence_id" in item}
        for result in self.assertion_results:
            for evidence_id in result.get("evidence_ids", []):
                if evidence_id in used:
                    used[evidence_id].append(result["assertion_id"])
        output = []
        for source in self.sources:
            if not isinstance(source, dict):
                continue
            source_id = source.get("source_id")
            evidence_ids = [
                item.get("evidence_id") for item in self.evidence
                if isinstance(item, dict) and item.get("source_id") == source_id
            ]
            output.append({
                "source_id": source_id,
                "source_type": source.get("source_type"),
                "evidence_ids": evidence_ids,
                "used_by": sorted({a for eid in evidence_ids for a in used.get(eid, [])}),
            })
        return output

    def summary(self):
        kinds = {"direct": 0, "calculated": 0, "qualitative": 0}
        complete = 0
        for result in self.assertion_results:
            if result["status"] == "complete":
                complete += 1
                kinds[result["kind"]] += 1
        return {
            "total_assertions": len(self.assertions),
            "completed_assertions": complete,
            "direct_assertions": kinds["direct"],
            "calculated_assertions": kinds["calculated"],
            "qualitative_assertions": kinds["qualitative"],
            "pending_assertions": len(self.assertions) - complete,
        }

    def result_payload(self):
        registered = {
            "case_id": self.case_id,
            "status": self.status,
            "assertion_results": self.assertion_results,
            "summary": self.summary(),
            "sources": self.source_summary(),
            "uncertainty": self.uncertainty,
            "change_records": self.change_records,
            "run_metadata": {
                "calculator_version": VERSION,
                "python_requirement": "3.9+",
                "stdlib_only": True,
                "external_requests_used": 0,
                "request_limit": self.resources["limits"]["max_requests"],
                "time_limit_seconds": self.resources["limits"]["max_seconds"],
                "numeric_engine": "Decimal input; Fraction exact arithmetic; Decimal final rounding",
            },
            "artifacts": {"calculations": "calculations.json", "result": "result.json"},
        }
        return {key: registered[key] for key in self.contract["result"]}

    def calculations_payload(self):
        registered = {
            "case_id": self.case_id,
            "status": self.status,
            "calculations": self.calculations,
            "direct_assertions": self.direct_assertions,
            "qualitative_assertions": self.qualitative_assertions,
            "unresolved": self.unresolved,
            "summary": self.summary(),
        }
        return {key: registered[key] for key in self.contract["calculations"]}

    def save(self):
        result = self.result_payload()
        calculations = self.calculations_payload()
        atomic_write(self.work_root / "work_ledger.json", {
            "case_id": self.case_id, "status": self.status,
            "next_assertion_index": len(self.assertion_results),
            "result": result, "calculations": calculations,
        })
        atomic_write(self.output_root / "calculations.json", calculations)
        atomic_write(self.output_root / "result.json", result)

    def validate_sources(self):
        if not self.assertions:
            raise DataError("case has no assertions")
        for source in self.sources:
            require_dict(source, "source")
            source_id = nonempty(source.get("source_id"), "source_id")
            if source_id in self.source_by_id:
                raise DataError("duplicate source_id: " + source_id)
            self.source_by_id[source_id] = source
            source_type = source.get("source_type")
            if source_type == "table":
                header = require_dict(source.get("row_header"), source_id + ".row_header")
                nonempty(header.get("label"), source_id + " row header label")
                nonempty(header.get("unit"), source_id + " row header unit")
                columns = require_list(source.get("columns"), source_id + ".columns")
                rows = require_list(source.get("rows"), source_id + ".rows")
                column_ids = []
                for column in columns:
                    require_dict(column, "column")
                    cid = nonempty(column.get("column_id"), "column_id")
                    nonempty(column.get("label"), cid + " label")
                    nonempty(column.get("unit"), cid + " unit")
                    column_ids.append(cid)
                if len(column_ids) != len(set(column_ids)) or not column_ids:
                    raise DataError(source_id + " column IDs must be non-empty and unique")
                row_ids = set()
                for row in rows:
                    require_dict(row, "row")
                    rid = nonempty(row.get("row_id"), "row_id")
                    nonempty(row.get("label"), rid + " label")
                    if rid in row_ids:
                        raise DataError("duplicate row_id: " + rid)
                    row_ids.add(rid)
                    cells = require_dict(row.get("cells"), rid + ".cells")
                    if set(cells) != set(column_ids):
                        raise DataError(rid + " cells do not exactly match columns")
                    for cid, value in cells.items():
                        decimal_value(value, rid + "." + cid)
            elif source_type == "figure_caption":
                nonempty(source.get("text"), source_id + ".text")
                panels = require_list(source.get("panels"), source_id + ".panels")
                panel_ids = set()
                for panel in panels:
                    require_dict(panel, "panel")
                    pid = nonempty(panel.get("panel_id"), "panel_id")
                    nonempty(panel.get("label"), pid + " label")
                    nonempty(panel.get("unit"), pid + " unit")
                    nonempty(panel.get("text"), pid + " text")
                    panel_ids.add(pid)
                if len(panel_ids) != len(panels):
                    raise DataError(source_id + " panel IDs must be unique")
            else:
                raise DataError("unsupported source_type for " + source_id)
        for evidence in self.evidence:
            require_dict(evidence, "evidence")
            eid = nonempty(evidence.get("evidence_id"), "evidence_id")
            if eid in self.evidence_by_id:
                raise DataError("duplicate evidence_id: " + eid)
            source_id = nonempty(evidence.get("source_id"), eid + ".source_id")
            if source_id not in self.source_by_id:
                raise DataError(eid + " references missing source " + source_id)
            nonempty(evidence.get("unit"), eid + ".unit")
            nonempty(evidence.get("quantity_kind"), eid + ".quantity_kind")
            nonempty(evidence.get("statistical_unit"), eid + ".statistical_unit")
            nonempty(evidence.get("population_scope"), eid + ".population_scope")
            locator = require_dict(evidence.get("locator"), eid + ".locator")
            source = self.source_by_id[source_id]
            if source["source_type"] == "table" and "row_id" in locator:
                row = next((r for r in source["rows"] if r["row_id"] == locator["row_id"]), None)
                column = next((c for c in source["columns"] if c["column_id"] == locator.get("column_id")), None)
                if row is None or column is None:
                    raise DataError(eid + " has invalid table locator")
                if decimal_value(evidence.get("value"), eid + ".value") != decimal_value(row["cells"][column["column_id"]], eid + " cell"):
                    raise DataError(eid + " value differs from table cell")
                if evidence["unit"] != column["unit"]:
                    raise DataError(eid + " unit differs from column unit")
            elif source["source_type"] == "figure_caption" and "panel_id" in locator:
                panel = next((p for p in source["panels"] if p["panel_id"] == locator["panel_id"]), None)
                if panel is None:
                    raise DataError(eid + " has invalid panel locator")
                if evidence["unit"] != panel["unit"]:
                    raise DataError(eid + " unit differs from panel unit")
                if evidence.get("value") is not None:
                    decimal_value(evidence["value"], eid + ".value")
            elif evidence.get("value") is not None:
                decimal_value(evidence["value"], eid + ".value")
            self.evidence_by_id[eid] = evidence

    def evidence_for(self, ids, label):
        ids = require_list(ids, label)
        if not ids:
            raise DataError(label + " cannot be empty")
        resolved = []
        for eid in ids:
            if not isinstance(eid, str) or eid not in self.evidence_by_id:
                raise DataError(label + " references missing evidence ID: " + str(eid))
            resolved.append(self.evidence_by_id[eid])
        return resolved

    def process_direct(self, assertion):
        evidence_ids = assertion.get("evidence_ids")
        evidence = self.evidence_for(evidence_ids, assertion["assertion_id"] + ".evidence_ids")
        if len(evidence) != 1:
            raise DataError("direct quantity requires exactly one evidence ID")
        item = evidence[0]
        if decimal_value(assertion.get("value"), "direct value") != decimal_value(item.get("value"), "evidence value"):
            raise DataError("direct value differs from its evidence")
        if assertion.get("unit") != item["unit"]:
            raise DataError("direct unit differs from its evidence")
        record = {
            "assertion_id": assertion["assertion_id"],
            "direct_vs_calculated": "direct",
            "value": str(assertion["value"]), "unit": assertion["unit"],
            "evidence_ids": evidence_ids,
        }
        self.direct_assertions.append(record)
        return "direct", record["value"], record["unit"], evidence_ids

    def scalar_operand(self, assertion, name):
        aid = assertion["assertion_id"]
        operands = require_dict(assertion.get("operands"), aid + ".operands")
        if name not in operands:
            raise DataError(aid + " lacks operand " + name)
        value_text = nonempty(str(operands[name]), aid + ".operands." + name) if operands[name] is not None else None
        if value_text is None:
            raise DataError(aid + " has unknown operand " + name)
        value = fraction_value(operands[name], aid + "." + name)
        units = require_dict(assertion.get("operand_units"), aid + ".operand_units")
        kinds = require_dict(assertion.get("operand_kinds"), aid + ".operand_kinds")
        unit = nonempty(units.get(name), aid + " unit for " + name)
        kind = nonempty(kinds.get(name), aid + " kind for " + name)
        evidence_map = require_dict(assertion.get("operand_evidence_ids"), aid + ".operand_evidence_ids")
        ids = self.evidence_for(evidence_map.get(name), aid + " evidence for " + name)
        if len(ids) != 1:
            raise DataError(aid + " operand " + name + " requires exactly one evidence ID")
        item = ids[0]
        if value != fraction_value(item.get("value"), aid + " evidence value for " + name):
            raise DataError(aid + " operand " + name + " differs from source evidence")
        if unit != item["unit"] or kind != item["quantity_kind"]:
            raise DataError(aid + " operand " + name + " unit/kind differs from source evidence")
        return {"name": name, "text": value_text, "value": value, "unit": unit, "kind": kind, "evidence_ids": evidence_map[name]}

    def validate_scope(self, assertion, names):
        scope = require_dict(assertion.get("scope"), assertion["assertion_id"] + ".scope")
        if scope.get("compatible") is not True:
            raise DataError(assertion["assertion_id"] + " denominator/scope compatibility is not established")
        for name in names:
            nonempty(scope.get(name), assertion["assertion_id"] + ".scope." + name)

    def process_calculation(self, assertion):
        aid = assertion["assertion_id"]
        operation = assertion.get("operation")
        if operation not in OPERATIONS:
            raise DataError(aid + " has unsupported operation")
        rounding = require_dict(assertion.get("rounding"), aid + ".rounding")
        places = rounding.get("places")
        if isinstance(places, Decimal):
            places = int(places) if places == int(places) else -1
        if not isinstance(places, int) or isinstance(places, bool) or not 0 <= places <= 12:
            raise DataError(aid + " rounding.places must be an integer from 0 to 12")
        if rounding.get("mode") not in ("half_up", "half_even"):
            raise DataError(aid + " rounding.mode must be half_up or half_even")
        part_ids = []
        if operation == "sum_reconciliation":
            operands = require_dict(assertion.get("operands"), aid + ".operands")
            raw_parts = require_list(operands.get("parts"), aid + ".operands.parts")
            if not raw_parts:
                raise DataError(aid + " parts cannot be empty")
            raw_part_ids = require_list(assertion.get("part_evidence_ids"), aid + ".part_evidence_ids")
            if len(raw_part_ids) != len(raw_parts):
                raise DataError(aid + " part_evidence_ids length differs from parts")
            parts = []
            units = require_dict(assertion.get("operand_units"), aid + ".operand_units")
            kinds = require_dict(assertion.get("operand_kinds"), aid + ".operand_kinds")
            common_unit = nonempty(units.get("parts"), aid + " parts unit")
            common_kind = nonempty(kinds.get("parts"), aid + " parts kind")
            for index, raw in enumerate(raw_parts):
                value = fraction_value(raw, aid + " part " + str(index))
                ids = self.evidence_for(raw_part_ids[index], aid + " part evidence " + str(index))
                if len(ids) != 1:
                    raise DataError(aid + " each part requires exactly one evidence ID")
                item = ids[0]
                if value != fraction_value(item.get("value"), aid + " part evidence"):
                    raise DataError(aid + " part differs from evidence")
                if common_unit != item["unit"] or common_kind != item["quantity_kind"]:
                    raise DataError(aid + " part unit/kind differs from evidence")
                parts.append(value)
                part_ids.extend(raw_part_ids[index])
            total = self.scalar_operand(assertion, "total")
            if total["unit"] != common_unit or total["kind"] != common_kind:
                raise DataError(aid + " total and parts have incompatible units/kinds")
            self.validate_scope(assertion, ["parts", "total"])
            values = {"parts": parts, "total": total["value"]}
            exact = sum(parts, Fraction(0)) - total["value"]
            output_unit = common_unit
            formula = "sum(parts) - total"
            scalar_ids = total["evidence_ids"]
            all_ids = part_ids + scalar_ids
            names_for_units = [common_unit]
        else:
            names = {
                "share": ["numerator", "denominator"],
                "ratio_percent_change": ["baseline", "new"],
                "relative_cpu_time_change": ["baseline_cpu_time", "candidate_cpu_time"],
                "residual": ["left", "right"],
            }[operation]
            items = {name: self.scalar_operand(assertion, name) for name in names}
            self.validate_scope(assertion, names)
            first = items[names[0]]
            for item in items.values():
                if item["unit"] != first["unit"] or item["kind"] != first["kind"]:
                    raise DataError(aid + " operand units/kinds are incompatible or denominators are confused")
            values = {name: item["value"] for name, item in items.items()}
            all_ids = [eid for name in names for eid in items[name]["evidence_ids"]]
            if operation == "share":
                if values["denominator"] == 0:
                    raise DataError(aid + " division by zero: share denominator")
                exact = values["numerator"] / values["denominator"] * 100
                formula = "numerator / denominator * 100"
                output_unit = "percent"
            elif operation == "ratio_percent_change":
                if values["baseline"] == 0:
                    raise DataError(aid + " division by zero: baseline")
                exact = (values["new"] - values["baseline"]) / values["baseline"] * 100
                formula = "(new - baseline) / baseline * 100"
                output_unit = "percent"
            elif operation == "relative_cpu_time_change":
                if values["baseline_cpu_time"] == 0:
                    raise DataError(aid + " division by zero: baseline_cpu_time")
                exact = (values["candidate_cpu_time"] - values["baseline_cpu_time"]) / values["baseline_cpu_time"] * 100
                formula = "(candidate_cpu_time - baseline_cpu_time) / baseline_cpu_time * 100"
                output_unit = "percent"
            else:
                exact = values["left"] - values["right"]
                formula = "left - right"
                output_unit = first["unit"]
            names_for_units = [first["unit"]]
        if operation == "sum_reconciliation" and exact != 0:
            raise DataError(aid + " sum reconciliation is unbalanced; residual=" + fraction_text(exact) + " " + output_unit)
        declared_ids = self.evidence_for(assertion.get("evidence_ids"), aid + ".evidence_ids")
        declared_id_values = [item["evidence_id"] for item in declared_ids]
        if set(declared_id_values) != set(all_ids) or len(declared_id_values) != len(all_ids):
            raise DataError(aid + " evidence_ids must exactly cover all operand evidence IDs")
        quantum = Decimal(1).scaleb(-places)
        mode = ROUND_HALF_UP if rounding["mode"] == "half_up" else ROUND_HALF_EVEN
        with localcontext() as context:
            context.prec = 60
            decimal_exact = Decimal(exact.numerator) / Decimal(exact.denominator)
            rounded = decimal_exact.quantize(quantum, rounding=mode)
        normalized_operands = {}
        for key, value in require_dict(assertion.get("operands"), aid + ".operands").items():
            normalized_operands[key] = [str(v) for v in value] if isinstance(value, list) else str(value)
        record = {
            "assertion_id": aid, "operation": operation,
            "direct_vs_calculated": "calculated",
            "operands": normalized_operands,
            "operand_units": assertion["operand_units"],
            "operand_kinds": assertion["operand_kinds"],
            "operand_evidence_ids": assertion.get("operand_evidence_ids", {}),
            "scope": assertion["scope"], "formula": formula,
            "exact_result": {"fraction": fraction_text(exact), "unit": output_unit},
            "rounded_value": format(rounded, "." + str(places) + "f"),
            "rounding": {"places": places, "mode": rounding["mode"], "applied_at": "presentation_only"},
            "evidence_validation": {"status": "valid", "evidence_ids": sorted(set(all_ids))},
        }
        if part_ids:
            record["part_evidence_ids"] = assertion["part_evidence_ids"]
        if operation == "sum_reconciliation":
            record["reconciliation"] = {"status": "balanced", "residual": "0", "unit": output_unit}
        self.calculations.append(record)
        return "calculated", record["rounded_value"], output_unit, declared_id_values

    def process_qualitative(self, assertion):
        ids = assertion.get("evidence_ids")
        self.evidence_for(ids, assertion["assertion_id"] + ".evidence_ids")
        if assertion.get("value") is not None:
            raise DataError("qualitative assertion cannot carry a numeric value")
        record = {
            "assertion_id": assertion["assertion_id"],
            "direct_vs_calculated": "not_applicable",
            "conclusion": nonempty(assertion.get("conclusion"), "qualitative conclusion"),
            "evidence_ids": ids,
        }
        self.qualitative_assertions.append(record)
        return "qualitative", None, None, ids

    def run(self):
        self.save()
        self.validate_sources()
        seen = set()
        for assertion in self.assertions:
            if time.monotonic() > self.deadline:
                raise DataError("900-second resource budget exceeded")
            require_dict(assertion, "assertion")
            aid = nonempty(assertion.get("assertion_id"), "assertion_id")
            if aid in seen:
                raise DataError("duplicate assertion_id: " + aid)
            seen.add(aid)
            try:
                kind = assertion.get("kind")
                if kind == "direct":
                    result_kind, value, unit, ids = self.process_direct(assertion)
                elif kind == "calculated":
                    result_kind, value, unit, ids = self.process_calculation(assertion)
                elif kind == "qualitative":
                    result_kind, value, unit, ids = self.process_qualitative(assertion)
                else:
                    raise DataError(aid + " has unsupported kind")
                result = {
                    "assertion_id": aid, "kind": result_kind, "status": "complete",
                    "direct_vs_calculated": "not_applicable" if kind == "qualitative" else kind,
                    "value": value, "unit": unit, "evidence_ids": ids,
                }
                self.assertion_results.append(result)
                self.change_records.append({"assertion_id": aid, "from": "pending", "to": "complete"})
                self.save()
            except DataError as exc:
                self.status = "failed"
                result = {
                    "assertion_id": aid, "kind": assertion.get("kind", "unknown"),
                    "status": "pending", "direct_vs_calculated": assertion.get("kind", "unknown"),
                    "value": None, "unit": None, "evidence_ids": assertion.get("evidence_ids", []),
                    "error": str(exc),
                }
                self.assertion_results.append(result)
                self.unresolved.append({"assertion_id": aid, "reason": str(exc), "value": None})
                self.uncertainty.append({"assertion_id": aid, "code": "unresolved", "message": str(exc)})
                self.change_records.append({"assertion_id": aid, "from": "pending", "to": "unresolved"})
                self.save()
                raise
        self.status = "complete"
        self.save()
        return 0


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--case", default="/input/case.json")
    parser.add_argument("--task", default="/input/task.md")
    parser.add_argument("--resources", default="environment/resources.yaml")
    parser.add_argument("--work-root")
    parser.add_argument("--output-root")
    args = parser.parse_args(argv)
    ledger = None
    try:
        case = load_json(args.case)
        contract = parse_contract(args.task)
        resources = parse_resources(args.resources)
        work_root = args.work_root or resources["paths"]["work_dir"]
        output_root = args.output_root or resources["paths"]["output_dir"]
        ledger = Ledger(case, contract, resources, work_root, output_root)
        return ledger.run()
    except DataError as exc:
        if ledger is not None and ledger.status != "failed":
            ledger.status = "failed"
            ledger.uncertainty.append({"code": "run_failed", "message": str(exc)})
            ledger.change_records.append({"assertion_id": None, "from": "partial", "to": "failed"})
            ledger.save()
        print("quant_ledger: " + str(exc), file=sys.stderr)
        return 2
    except Exception as exc:  # Preserve a clear nonzero exit without inventing values.
        if ledger is not None:
            ledger.status = "failed"
            ledger.uncertainty.append({"code": "internal_error", "message": str(exc)})
            ledger.save()
        print("quant_ledger internal error: " + str(exc), file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
