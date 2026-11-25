#!/usr/bin/env python3
"""Bind the declared output contract, strictly or as an honest partial result."""

import argparse
import copy
import math
import re
import sys

from score_engine import InputError, canonical_hash, dump_json, load_json


EXPORT_KEY = "rubric_mutation_lab"
DEFAULT_UNCERTAINTY = [
    "Rule execution is not semantic-entailment certification; manual review remains necessary."
]
HUMAN_AGREEMENT_NOTE = "Not measured; no DSH or human agreement score is claimed."
_TYPE_ALIASES = {
    "str": "string", "string": "string",
    "list": "array", "array": "array",
    "dict": "object", "object": "object",
    "bool": "boolean", "boolean": "boolean",
    "int": "integer", "integer": "integer",
    "float": "number", "number": "number",
    "null": "null", "none": "null",
    "any": "any", "unspecified": "any",
}
_CONTROL_KEYS = {
    "fields", "properties", "required", "required_fields",
    "required_top_level_fields", "optional_fields", "description", "title",
    "schema_version", "$schema", "additionalProperties",
}


def _gate(gates, name, passed, detail):
    gates.append({"gate": name, "passed": bool(passed), "detail": detail})


def _name_list(value, label):
    if value is None:
        return []
    if not isinstance(value, list) or any(
            not isinstance(entry, str) or not entry for entry in value):
        raise InputError(label + " must be an array of nonempty field names")
    if len(set(value)) != len(value):
        raise InputError(label + " contains duplicate field names")
    return list(value)


def _declared_types(descriptor, label):
    if isinstance(descriptor, str):
        raw_types = [descriptor]
        metadata = {}
    elif descriptor is None:
        raw_types = []
        metadata = {}
    elif isinstance(descriptor, dict):
        metadata = descriptor
        raw = descriptor.get("type", descriptor.get(
            "field_type", descriptor.get("data_type")))
        if raw is None:
            raw_types = []
        elif isinstance(raw, str):
            raw_types = [raw]
        elif isinstance(raw, list) and raw and all(
                isinstance(entry, str) for entry in raw):
            raw_types = raw
        else:
            raise InputError(label + ".type must be a string or nonempty string array")
    else:
        raise InputError(label + " must be a type string or metadata object")
    types = []
    for raw_type in raw_types:
        normalized = _TYPE_ALIASES.get(raw_type.strip().lower())
        if normalized is None:
            raise InputError(label + " declares unsupported type " + raw_type)
        if normalized not in types:
            types.append(normalized)
    if metadata.get("nullable") is True and "null" not in types:
        types.append("null")
    if metadata.get("nullable") not in (None, True, False):
        raise InputError(label + ".nullable must be Boolean")
    return types, metadata


def _required(metadata, default, label):
    required = default
    if "required" in metadata:
        if not isinstance(metadata["required"], bool):
            raise InputError(label + ".required must be Boolean")
        required = metadata["required"]
    if "optional" in metadata:
        if not isinstance(metadata["optional"], bool):
            raise InputError(label + ".optional must be Boolean")
        if metadata["optional"]:
            required = False
        elif "required" not in metadata:
            required = True
    return required


def _field_spec(name, descriptor, required_default, label):
    if not isinstance(name, str) or not name:
        raise InputError(label + " has an empty or non-string field name")
    types, metadata = _declared_types(descriptor, label)
    return {
        "name": name,
        "types": types,
        "required": _required(metadata, required_default, label),
        "metadata": copy.deepcopy(metadata),
    }


def parse_output_contract(contract):
    """Return normalized field specs for all supported contract spellings.

    Arbitrary original case keys are deliberately not consulted here. Only this
    declaration determines which generated values the runtime contract requires.
    """
    if isinstance(contract, list):
        names = _name_list(contract, "output_contract")
        return [_field_spec(name, None, True, "output_contract[]") for name in names]
    if not isinstance(contract, dict):
        raise InputError("case.json output_contract must be an array or object")

    explicit_required = []
    for key in ("required_fields", "required_top_level_fields", "required"):
        if key in contract:
            # In a direct field map a Boolean required belongs to field metadata,
            # not to the object-level parser; object-level required is always a list.
            explicit_required.extend(_name_list(contract[key], "output_contract." + key))
    explicit_required = list(dict.fromkeys(explicit_required))
    optional = _name_list(contract.get("optional_fields"), "output_contract.optional_fields")
    default_required = not bool(explicit_required)
    specs = []
    by_name = {}

    def add(name, descriptor, label):
        if name in by_name:
            raise InputError("output_contract declares duplicate field " + name)
        spec = _field_spec(name, descriptor, default_required, label)
        specs.append(spec)
        by_name[name] = spec

    if "fields" in contract:
        fields = contract["fields"]
        if not isinstance(fields, list):
            raise InputError("output_contract.fields must be an array")
        for index, entry in enumerate(fields):
            label = "output_contract.fields[%d]" % index
            if isinstance(entry, str):
                if not entry:
                    raise InputError(label + " must not be empty")
                add(entry, None, label)
            elif isinstance(entry, dict):
                name = entry.get("name", entry.get("field", entry.get("key")))
                if not isinstance(name, str) or not name:
                    raise InputError(label + " requires a nonempty name")
                add(name, entry, label)
            else:
                raise InputError(label + " must be a field name or metadata object")
    elif "properties" in contract:
        properties = contract["properties"]
        if not isinstance(properties, dict):
            raise InputError("output_contract.properties must be an object")
        for name, descriptor in properties.items():
            add(name, descriptor, "output_contract.properties." + str(name))
    else:
        # Direct field -> type/metadata map. required*_fields may accompany it.
        for name, descriptor in contract.items():
            if name not in _CONTROL_KEYS:
                add(name, descriptor, "output_contract." + str(name))

    for name in explicit_required:
        if name not in by_name:
            add(name, None, "output_contract.required_fields")
        by_name[name]["required"] = True
    for name in optional:
        if name in by_name and name not in explicit_required:
            by_name[name]["required"] = False
    if any(spec["name"] == EXPORT_KEY for spec in specs):
        raise InputError("output_contract uses reserved top-level key " + EXPORT_KEY)
    return specs


def _compatible(value, types):
    if not types or "any" in types:
        return True
    for declared in types:
        if declared == "null" and value is None:
            return True
        if declared == "string" and isinstance(value, str):
            return True
        if declared == "array" and isinstance(value, list):
            return True
        if declared == "object" and isinstance(value, dict):
            return True
        if declared == "boolean" and isinstance(value, bool):
            return True
        if declared == "integer" and isinstance(value, int) and not isinstance(value, bool):
            return True
        if declared == "number" and isinstance(value, (int, float)) and \
                not isinstance(value, bool) and math.isfinite(float(value)):
            return True
    return False


def _placeholder(spec, force_null=False):
    if force_null or not spec["types"] or "null" in spec["types"] or \
            "any" in spec["types"]:
        return None
    # A missing/incompatible value gets a typed empty placeholder, never a fake
    # report or score. The corresponding field gate remains failed.
    for declared in spec["types"]:
        if declared == "array":
            return []
        if declared == "object":
            return {}
        if declared == "string":
            return ""
        if declared == "boolean":
            return False
        if declared in ("integer", "number"):
            # Numeric zero would be indistinguishable from a real measurement.
            return None
    return None


def _kind(name):
    normalized = re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")
    aliases = {
        "case_id": "case_id",
        "status": "status", "state": "status", "completion_status": "status",
        "success": "success", "ok": "success", "complete": "success",
        "completed": "success", "is_complete": "success",
        "item_bank": "item_bank", "benchmark_draft": "item_bank",
        "draft_item_bank": "item_bank", "bank": "item_bank",
        "items": "items", "questions": "items", "benchmark_items": "items",
        "draft_items": "items",
        "score_report": "score_report", "scoring_report": "score_report",
        "actual_score_records": "records", "score_records": "records",
        "scores": "records", "actual_scores": "records",
        "mutation_report": "mutation_report", "mutation_results": "mutation_report",
        "rollup": "rollup", "score_rollup": "rollup", "scoring_rollup": "rollup",
        "sources": "sources", "source_records": "sources",
        "uncertainty": "uncertainty", "uncertainties": "uncertainty",
        "limitations": "uncertainty",
        "change_records": "change_records", "changes": "change_records",
        "change_log": "change_records", "changelog": "change_records",
        "summary": "summary", "diagnostics": "diagnostics",
        "diagnostic": "diagnostics", "strict_gates": "gates", "gates": "gates",
        "score": "score_total", "score_total": "score_total",
        "total_score": "score_total", "normalized_score": "normalized_score",
        "item_count": "item_count",
    }
    if normalized in aliases:
        return aliases[normalized]
    if ("human" in normalized and ("agreement" in normalized or "score" in normalized)) \
            or "dsh" in normalized:
        return "human_agreement"
    return "unknown"


def _diagnostic_summary(context, complete, gates):
    return {
        "status": "complete" if complete else "partial",
        "success": bool(complete),
        "item_count": len(context["items"]),
        "actual_score_record_count": len(context["records"]),
        "rollup": copy.deepcopy(context["rollup"]),
        "failed_gates": [gate["gate"] for gate in gates if not gate["passed"]],
        "strict_gates": copy.deepcopy(gates),
    }


def _semantic_value(spec, context, complete, gates):
    """Return (known, available, value) without fabricating measured content."""
    name = spec["name"]
    kind = _kind(name)
    types = spec["types"]
    if kind == "case_id":
        return True, True, context["case_id"]
    if kind == "status":
        status = "complete" if complete else "partial"
        if types and "object" in types and "string" not in types:
            return True, True, {"status": status, "success": bool(complete)}
        if types and "boolean" in types and "string" not in types:
            return True, True, bool(complete)
        return True, True, status
    if kind == "success":
        if types and "string" in types and "boolean" not in types:
            return True, True, "complete" if complete else "partial"
        return True, True, bool(complete)
    if kind == "item_bank":
        return True, isinstance(context["bank"], dict), copy.deepcopy(context["bank"])
    if kind == "items":
        available = isinstance(context["bank"], dict) and isinstance(
            context["bank"].get("items"), list)
        return True, available, copy.deepcopy(context["items"]) if available else None
    if kind == "score_report":
        return True, isinstance(context["score_report"], dict), copy.deepcopy(
            context["score_report"])
    if kind == "records":
        available = isinstance(context["score_report"], dict) and isinstance(
            context["score_report"].get("records"), list)
        return True, available, copy.deepcopy(context["records"]) if available else None
    if kind == "mutation_report":
        return True, isinstance(context["mutation_report"], dict), copy.deepcopy(
            context["mutation_report"])
    if kind == "rollup":
        available = isinstance(context["score_report"], dict) and isinstance(
            context["score_report"].get("rollup"), dict)
        return True, available, copy.deepcopy(context["rollup"]) if available else None
    if kind == "sources":
        return True, True, copy.deepcopy(context["case"].get("sources", []))
    if kind == "uncertainty":
        return True, True, copy.deepcopy(context["case"].get(
            "uncertainty", DEFAULT_UNCERTAINTY))
    if kind == "change_records":
        return True, True, copy.deepcopy(context["case"].get("change_records", []))
    if kind in ("summary", "diagnostics"):
        summary = _diagnostic_summary(context, complete, gates)
        if kind == "diagnostics":
            summary["input_errors"] = list(context["errors"])
            summary["contract_fields"] = [field["name"] for field in context["specs"]]
        if types and "string" in types and not ({"object", "array", "any"} & set(types)):
            failed = summary["failed_gates"]
            return True, True, "%s; failed gates: %s" % (
                summary["status"], ", ".join(failed) if failed else "none")
        if types and "array" in types and not ({"object", "string", "any"} & set(types)):
            return True, True, copy.deepcopy(summary["strict_gates"])
        return True, True, summary
    if kind == "gates":
        return True, True, copy.deepcopy(gates)
    if kind in ("score_total", "normalized_score"):
        value = context["rollup"].get(kind)
        return True, value is not None, copy.deepcopy(value)
    if kind == "item_count":
        available = isinstance(context["bank"], dict) and isinstance(
            context["bank"].get("items"), list)
        return True, available, len(context["items"]) if available else None
    if kind == "human_agreement":
        normalized = re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")
        measured_object = {"measured": False, "score": None, "note": HUMAN_AGREEMENT_NOTE}
        if "measured" in normalized and (not types or "boolean" in types):
            return True, True, False
        if "note" in normalized or (types and set(types) <= {"string", "null"}):
            return True, True, HUMAN_AGREEMENT_NOTE
        if not types or "any" in types or "object" in types:
            return True, True, measured_object
        if "array" in types:
            return True, True, [HUMAN_AGREEMENT_NOTE]
        if "string" in types:
            return True, True, HUMAN_AGREEMENT_NOTE
        # A numeric/null-only human score cannot be manufactured. It is null only
        # where an optional/nullable declaration can represent that absence.
        return True, False, None
    return False, False, None


def _bind_contract(specs, context, complete, diagnostic_gates):
    values = {}
    gates = []
    for spec in specs:
        name = spec["name"]
        known, available, candidate = _semantic_value(
            spec, context, complete, diagnostic_gates)
        compatible = known and available and _compatible(candidate, spec["types"])
        bound = compatible and candidate is not None
        if bound:
            value = candidate
            detail = "bound generated value with compatible declared type"
        else:
            value = _placeholder(
                spec, force_null=not known or _kind(name) == "human_agreement")
            if not known:
                requirement = "required" if spec["required"] else "declared"
                detail = "unknown %s contract field has no honest generated binding; null emitted" % requirement
            elif not available:
                detail = "no non-null measured/generated value is available; typed placeholder emitted"
            elif not compatible:
                detail = "generated value is incompatible with declared type %s; typed placeholder emitted" % (
                    spec["types"] or ["any"])
            else:
                detail = "contract field is null; strict completion requires a non-null value"
        values[name] = copy.deepcopy(value)
        _gate(gates, "contract_field:" + name, bound, detail)
    return values, gates


def _core_gates(bank, score_report, mutation_report, errors):
    gates = []
    items = bank.get("items", []) if isinstance(bank, dict) else []
    if not isinstance(items, list):
        items = []
    bank_ids = [item.get("item_id") for item in items if isinstance(item, dict)]
    valid_bank_ids = [item_id for item_id in bank_ids if isinstance(item_id, str)]
    bank_ok = len(items) == 4 and len(bank_ids) == 4 and \
        len(valid_bank_ids) == 4 and len(set(valid_bank_ids)) == 4 and all(valid_bank_ids)
    _gate(gates, "exact_four_unique_items", bank_ok, "bank item IDs: %s" % bank_ids)

    mutation_summary = mutation_report.get("summary", {}) \
        if isinstance(mutation_report, dict) else {}
    if not isinstance(mutation_summary, dict):
        mutation_summary = {}
    mutation_ok = isinstance(mutation_report, dict) and \
        mutation_report.get("status") == "passed" and \
        mutation_summary.get("passed") is True and \
        mutation_summary.get("item_count") == 4
    _gate(gates, "mutation_suite_passed", mutation_ok,
          "all independent probe classifications and required classes must pass")

    records = score_report.get("records", []) if isinstance(score_report, dict) else []
    if not isinstance(records, list):
        records = []
    record_ids = [record.get("item_id") for record in records if isinstance(record, dict)]
    scores = [record.get("score") for record in records if isinstance(record, dict)]
    valid_record_ids = [item_id for item_id in record_ids if isinstance(item_id, str)]
    records_ok = len(records) == 4 and len(record_ids) == 4 and \
        len(valid_record_ids) == 4 and len(set(valid_record_ids)) == 4 and \
        set(valid_record_ids) == set(valid_bank_ids) and all(
            isinstance(score, int) and not isinstance(score, bool) and score in (0, 1, 2)
            for score in scores) and len(scores) == 4
    _gate(gates, "four_valid_score_records", records_ok,
          "exactly four required IDs with integer 0/1/2 scores")

    hash_ok = records_ok
    by_id = {item["item_id"]: item for item in items if isinstance(item, dict) and
             isinstance(item.get("item_id"), str)}
    for record in records:
        if not isinstance(record, dict):
            hash_ok = False
            continue
        item = by_id.get(record.get("item_id"))
        if item is None or record.get("rubric_hash") != canonical_hash(item.get("rubric")):
            hash_ok = False
    _gate(gates, "rubric_hashes_match", hash_ok,
          "each score record must bind to its current item rubric")

    rollup = score_report.get("rollup", {}) if isinstance(score_report, dict) else {}
    if not isinstance(rollup, dict):
        rollup = {}
    expected_total = sum(scores) if records_ok else None
    normalized = rollup.get("normalized_score")
    normalized_ok = isinstance(normalized, (int, float)) and \
        not isinstance(normalized, bool) and math.isfinite(float(normalized))
    rollup_ok = records_ok and rollup.get("score_total") == expected_total and \
        rollup.get("scored_required_count") == 4 and \
        rollup.get("required_denominator") == 4 and \
        rollup.get("max_score") == 8 and \
        rollup.get("normalization_denominator") == 8 and normalized_ok and \
        math.isclose(normalized, expected_total / 8, rel_tol=0, abs_tol=1e-12)
    _gate(gates, "rollup_consistent", rollup_ok,
          "sum of four scored required items; denominator is exactly 2*4")

    candidate_hashes_ok = records_ok and all(
        isinstance(record, dict) and
        isinstance(record.get("raw_output_ref"), str) and
        record["raw_output_ref"].startswith("sha256:") and
        isinstance(record.get("checks"), list) and record["checks"]
        for record in records)
    _gate(gates, "raw_output_trace_present", candidate_hashes_ok,
          "each score must retain a SHA-256 raw-output reference and explicit checks")

    for error in errors:
        _gate(gates, "input_error", False, error)
    return gates, items, records, rollup


def finalize(case, bank, score_report, mutation_report, errors):
    if not isinstance(case, dict) or not isinstance(case.get("case_id"), str) or not case["case_id"]:
        raise InputError("case.json must contain a nonempty top-level case_id")
    if EXPORT_KEY in case:
        raise InputError("original case already uses reserved top-level key " + EXPORT_KEY)
    if "output_contract" not in case:
        raise InputError("case.json must contain an explicit top-level output_contract")
    specs = parse_output_contract(case["output_contract"])
    errors = list(errors or [])
    core_gates, items, records, rollup = _core_gates(
        bank, score_report, mutation_report, errors)
    context = {
        "case": case, "case_id": case["case_id"], "bank": bank,
        "score_report": score_report, "mutation_report": mutation_report,
        "items": items, "records": records, "rollup": rollup,
        "errors": errors, "specs": specs,
    }
    core_complete = all(gate["passed"] for gate in core_gates)

    # Status/success values depend on contract binding itself. Rebinding after the
    # first decision makes them truthful even when an unknown/incompatible field
    # is the only failed gate. Gate compatibility is stable across these passes.
    complete = core_complete
    diagnostic_gates = core_gates
    for _ in range(3):
        values, contract_gates = _bind_contract(
            specs, context, complete, diagnostic_gates)
        updated = core_complete and all(gate["passed"] for gate in contract_gates)
        diagnostic_gates = core_gates + contract_gates
        if updated == complete:
            break
        complete = updated
    values, contract_gates = _bind_contract(
        specs, context, complete, diagnostic_gates)
    complete = core_complete and all(gate["passed"] for gate in contract_gates)
    if not complete:
        # This also covers the theoretically unstable case of a status-only type
        # failure; normal contracts converge in the loop above.
        values, contract_gates = _bind_contract(
            specs, context, False, core_gates + contract_gates)
        complete = False
    gates = core_gates + contract_gates
    status = "complete" if complete else "partial"

    # Original fields are metadata extras only; they never satisfy an output field
    # unless the semantic binder above recognizes that declared field.
    result = {key: copy.deepcopy(value) for key, value in case.items()
              if key not in (EXPORT_KEY, "status", "success")}
    for name, value in values.items():
        result[name] = value
    result["case_id"] = case["case_id"]
    if "status" not in values:
        result["status"] = status
    if "success" not in values:
        result["success"] = complete

    result[EXPORT_KEY] = {
        "schema_version": "1.0",
        "status": status,
        "success": complete,
        "synthetic_only": bank.get("synthetic_only", False) if isinstance(bank, dict) else False,
        "strict_gates": gates,
        "item_bank": copy.deepcopy(bank) if bank is not None else None,
        "actual_score_records": copy.deepcopy(records),
        "rollup": copy.deepcopy(rollup),
        "mutation_report": copy.deepcopy(mutation_report),
        "sources": copy.deepcopy(case.get("sources", [])),
        "uncertainty": copy.deepcopy(case.get("uncertainty", DEFAULT_UNCERTAINTY)),
        "change_records": copy.deepcopy(case.get("change_records", [])),
        "human_agreement_score": None,
        "human_agreement_note": HUMAN_AGREEMENT_NOTE,
        "contract_fields": [spec["name"] for spec in specs],
    }
    return result, complete


def _catastrophic_partial(case, bank, score_report, mutation_report, detail):
    """Best-effort partial for an unreadable/invalid contract or other InputError."""
    result = {key: copy.deepcopy(value) for key, value in case.items()
              if key not in (EXPORT_KEY, "status", "success")}
    if isinstance(case.get("case_id"), str) and case["case_id"]:
        result["case_id"] = case["case_id"]
    result["status"] = "partial"
    result["success"] = False
    result[EXPORT_KEY] = {
        "schema_version": "1.0", "status": "partial", "success": False,
        "synthetic_only": bank.get("synthetic_only", False) if isinstance(bank, dict) else False,
        "strict_gates": [{"gate": "finalization", "passed": False, "detail": detail}],
        "item_bank": bank, "actual_score_records": [], "rollup": {},
        "mutation_report": mutation_report,
        "sources": copy.deepcopy(case.get("sources", [])),
        "uncertainty": copy.deepcopy(case.get("uncertainty", [detail])),
        "change_records": copy.deepcopy(case.get("change_records", [])),
        "human_agreement_score": None,
        "human_agreement_note": HUMAN_AGREEMENT_NOTE,
    }
    if isinstance(score_report, dict) and isinstance(score_report.get("records"), list):
        result[EXPORT_KEY]["actual_score_records"] = copy.deepcopy(score_report["records"])
    if isinstance(score_report, dict) and isinstance(score_report.get("rollup"), dict):
        result[EXPORT_KEY]["rollup"] = copy.deepcopy(score_report["rollup"])
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--case", required=True, help="original case.json")
    parser.add_argument("--items", required=True)
    parser.add_argument("--score-report")
    parser.add_argument("--mutation-report")
    parser.add_argument("--output", required=True)
    parser.add_argument("--strict", action="store_true",
                        help="return nonzero unless every gate passes; still write honest partial")
    args = parser.parse_args(argv)
    case = None
    bank = None
    errors = []
    score_report = None
    mutation_report = None
    try:
        case = load_json(args.case)
        for label, path in (("items", args.items),
                            ("score report", args.score_report),
                            ("mutation report", args.mutation_report)):
            if path is None:
                if label != "items":
                    errors.append(label + " was not supplied")
                continue
            try:
                value = load_json(path)
            except InputError as exc:
                errors.append(str(exc))
                value = None
            if label == "items":
                bank = value
            elif label == "score report":
                score_report = value
            else:
                mutation_report = value
        result, complete = finalize(case, bank, score_report, mutation_report, errors)
        dump_json(result, args.output)
    except InputError as exc:
        # Keep the case identity and explicit failure diagnostics when possible.
        if case is not None and isinstance(case, dict) and EXPORT_KEY not in case:
            result = _catastrophic_partial(case, bank, score_report, mutation_report, str(exc))
            try:
                dump_json(result, args.output)
            except InputError as write_exc:
                sys.stderr.write("finalize: %s\n" % write_exc)
        sys.stderr.write("finalize: %s\n" % exc)
        return 2
    if args.strict and not complete:
        sys.stderr.write("finalize: strict gates failed; honest partial was written\n")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
