#!/usr/bin/env python3
"""Validate agent-authored symbol bindings and emit contract-preserving results.

A non-zero exit (2) means validation errors. Normal mode still writes an honest
partial/invalid result and both variable tables so failures are never silent.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

CATEGORIES = {
    "direct_source_definition", "contextual_inference", "common_knowledge_external",
    "not_reported", "conflict",
}
STANDARD_ALIASES = {
    "variable_table": "variables", "variabletable": "variables", "symbols": "variables",
    "symbol_table": "variables", "formula_table": "formula_occurrences",
    "formulae": "formula_occurrences", "formulas": "formula_occurrences",
    "coverage": "formula_coverage", "evidence_records": "evidence",
    "conflict_records": "conflicts", "caveats": "limitations",
}


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def canonical_key(value: str) -> str:
    return re.sub(r"[^a-z0-9_]+", "_", value.lower()).strip("_")


def contract_fields(contract: dict[str, Any]) -> tuple[list[str], dict[str, Any], list[str]]:
    raw_required = contract.get("required_fields", [])
    required: list[str] = []
    if isinstance(raw_required, dict):
        required = [str(key) for key, enabled in raw_required.items() if enabled is not False]
    elif isinstance(raw_required, list):
        for item in raw_required:
            if isinstance(item, str):
                required.append(item)
            elif isinstance(item, dict) and isinstance(item.get("name"), str):
                required.append(item["name"])
    raw_types = contract.get("field_types", {})
    field_types = dict(raw_types) if isinstance(raw_types, dict) else {}
    properties = contract.get("properties", {})
    if isinstance(properties, dict):
        for key, spec in properties.items():
            field_types.setdefault(key, spec)
            if isinstance(spec, dict) and spec.get("required") is True and key not in required:
                required.append(key)
    optional = contract.get("optional_fields", [])
    if isinstance(optional, list):
        for item in optional:
            if isinstance(item, str):
                field_types.setdefault(item, {})
    raw_status = contract.get("status_enum", [])
    if not raw_status and isinstance(field_types.get("status"), dict):
        raw_status = field_types["status"].get("enum", [])
    if not raw_status and isinstance(properties.get("status"), dict):
        raw_status = properties["status"].get("enum", [])
    status_enum = [str(item) for item in raw_status] if isinstance(raw_status, list) else []
    # Emit every named contract field, including typed fields omitted from required_fields.
    ordered = list(required)
    for key in field_types:
        if key not in ordered:
            ordered.append(key)
    return ordered, field_types, status_enum


def choose_status(enum: list[str], priorities: list[str], fallback: str) -> str:
    if not enum:
        return fallback
    lookup = {re.sub(r"[-\s]+", "_", item.lower()): item for item in enum}
    for desired in priorities:
        key = re.sub(r"[-\s]+", "_", desired.lower())
        if key in lookup:
            return lookup[key]
    return enum[0]


def source_text_for_locator(locator: Any, ledger: dict[str, Any], indexes: dict[str, Any]) -> tuple[str, str | None]:
    if not isinstance(locator, dict):
        return "", "locator must be an object"
    sentence_id = locator.get("sentence_id")
    paragraph_id = locator.get("paragraph_id")
    if sentence_id:
        sentence = indexes["sentences"].get(sentence_id)
        if sentence is None:
            return "", f"unknown sentence_id {sentence_id!r}"
        for key in ("document_id", "section_id", "paragraph_id"):
            if locator.get(key) is not None and locator.get(key) != sentence.get(key):
                return "", f"locator {key} does not match {sentence_id}"
        return sentence["text"], None
    if paragraph_id:
        paragraph = indexes["paragraphs"].get(paragraph_id)
        if paragraph is None:
            return "", f"unknown paragraph_id {paragraph_id!r}"
        for key in ("document_id", "section_id"):
            if locator.get(key) is not None and locator.get(key) != paragraph.get(key):
                return "", f"locator {key} does not match {paragraph_id}"
        return paragraph["text"], None
    return "", "locator needs sentence_id or paragraph_id"


def check_quote(quote: Any, locator: Any, scope_id: str, ledger: dict[str, Any],
                indexes: dict[str, Any], errors: list[str], label: str) -> None:
    if not isinstance(quote, str) or not quote.strip():
        errors.append(f"{label}: exact non-empty evidence quote is required")
        return
    text, error = source_text_for_locator(locator, ledger, indexes)
    if error:
        errors.append(f"{label}: {error}")
        return
    if quote not in text:
        errors.append(f"{label}: quote is not an exact substring of the located source sentence/paragraph")
    if isinstance(locator, dict) and locator.get("section_id") != scope_id:
        errors.append(f"{label}: evidence section does not match binding scope {scope_id}")


def check_quantity(value: Any, field: str, scope_id: str, ledger: dict[str, Any],
                   indexes: dict[str, Any], errors: list[str], label: str) -> None:
    if value is None:
        return
    if not isinstance(value, dict):
        errors.append(f"{label}.{field}: must be null or a provenance object")
        return
    provenance = value.get("provenance")
    if provenance not in CATEGORIES - {"conflict"}:
        errors.append(f"{label}.{field}: unsupported or missing provenance {provenance!r}")
        return
    has_value = value.get("value") is not None
    if field == "range":
        has_value = any(value.get(key) is not None for key in ("value", "lower", "upper", "text"))
    if provenance == "not_reported":
        if has_value:
            errors.append(f"{label}.{field}: not_reported cannot carry a value")
        return
    if not has_value:
        errors.append(f"{label}.{field}: reported provenance has no value")
    if provenance == "direct_source_definition":
        check_quote(value.get("evidence_quote"), value.get("locator"), scope_id,
                    ledger, indexes, errors, f"{label}.{field}")
    elif provenance == "contextual_inference":
        if not isinstance(value.get("inference_reason"), str) or not value["inference_reason"].strip():
            errors.append(f"{label}.{field}: contextual_inference requires inference_reason")
        if value.get("evidence_quote") is not None:
            check_quote(value.get("evidence_quote"), value.get("locator"), scope_id,
                        ledger, indexes, errors, f"{label}.{field} inference")
    elif provenance == "common_knowledge_external":
        if not isinstance(value.get("external_basis"), str) or not value["external_basis"].strip():
            errors.append(f"{label}.{field}: common_knowledge_external requires external_basis")
        if value.get("attribution") != "external_not_paper":
            errors.append(f"{label}.{field}: external knowledge must set attribution=external_not_paper")
        if value.get("evidence_quote") is not None or value.get("candidate_id") is not None:
            errors.append(f"{label}.{field}: external knowledge cannot be attributed to paper evidence")


def validate(ledger: dict[str, Any], bindings: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    errors: list[str] = []
    warnings: list[str] = []
    indexes = {
        "sentences": {x["sentence_id"]: x for x in ledger.get("sentences", [])},
        "paragraphs": {x["paragraph_id"]: x for x in ledger.get("paragraphs", [])},
        "candidates": {x["candidate_id"]: x for x in ledger.get("candidates", [])},
        "symbols": {x["symbol_instance_id"]: x for x in ledger.get("symbol_instances", [])},
        "formulas": {x["formula_id"]: x for x in ledger.get("formulas", [])},
    }
    case_id = ledger.get("case_id")
    if not isinstance(bindings, dict):
        return {"valid": False, "errors": ["bindings.json must be an object"], "warnings": [], "case_id": case_id}, indexes
    if bindings.get("case_id") != case_id:
        errors.append(f"bindings case_id {bindings.get('case_id')!r} does not equal source case_id {case_id!r}")
    raw_bindings = bindings.get("symbol_bindings", [])
    if not isinstance(raw_bindings, list):
        errors.append("symbol_bindings must be an array")
        raw_bindings = []
    bound_ids: set[str] = set()
    normalized_bindings: list[dict[str, Any]] = []
    for index, binding in enumerate(raw_bindings):
        label = f"symbol_bindings[{index}]"
        if not isinstance(binding, dict):
            errors.append(f"{label}: must be an object")
            continue
        sid = binding.get("symbol_instance_id")
        label = f"{label}({sid})"
        instance = indexes["symbols"].get(sid)
        if instance is None:
            errors.append(f"{label}: unknown symbol_instance_id")
            continue
        if sid in bound_ids:
            errors.append(f"{label}: duplicate binding for {sid}")
        bound_ids.add(sid)
        scope_id = instance["section_id"]
        if binding.get("section_id") != scope_id:
            errors.append(f"{label}: binding must name its local section_id {scope_id}; global bindings are forbidden")
        if binding.get("canonical") != instance["canonical"] or binding.get("base_glyph") != instance["base_glyph"]:
            errors.append(f"{label}: base glyph/full symbol identity does not match ledger")
        if binding.get("scripts") != instance["scripts"]:
            errors.append(f"{label}: full scripts do not match ledger; scripted and unscripted glyphs are distinct")
        category = binding.get("category")
        if category not in CATEGORIES:
            errors.append(f"{label}: invalid category {category!r}")
        elif category == "direct_source_definition":
            if not isinstance(binding.get("meaning"), str) or not binding["meaning"].strip():
                errors.append(f"{label}: direct definition needs meaning")
            candidate_id = binding.get("selected_candidate_id")
            candidate = indexes["candidates"].get(candidate_id)
            if candidate is None:
                errors.append(f"{label}: direct definition must select an existing definition candidate")
            else:
                if "definition" not in candidate.get("kinds", []):
                    errors.append(f"{label}: selected candidate is not a definition candidate")
                if candidate["section_id"] != scope_id:
                    errors.append(f"{label}: selected candidate comes from a different scope")
                evidence = binding.get("evidence", {})
                if not isinstance(evidence, dict):
                    errors.append(f"{label}: evidence must be an object")
                else:
                    if evidence.get("quote") != candidate["quote"]:
                        errors.append(f"{label}: evidence.quote must exactly equal selected candidate.quote")
                    if evidence.get("locator") != candidate["locator"]:
                        errors.append(f"{label}: evidence.locator must exactly equal selected candidate.locator")
                    check_quote(evidence.get("quote"), evidence.get("locator"), scope_id,
                                ledger, indexes, errors, label)
        elif category == "contextual_inference":
            if not isinstance(binding.get("inference_reason"), str) or not binding["inference_reason"].strip():
                errors.append(f"{label}: contextual_inference must state inference_reason")
            evidence = binding.get("evidence")
            if evidence is not None and isinstance(evidence, dict) and evidence.get("quote") is not None:
                check_quote(evidence.get("quote"), evidence.get("locator"), scope_id,
                            ledger, indexes, errors, f"{label} inference")
        elif category == "common_knowledge_external":
            if not isinstance(binding.get("external_basis"), str) or not binding["external_basis"].strip():
                errors.append(f"{label}: common_knowledge_external must state external_basis")
            if binding.get("attribution") != "external_not_paper":
                errors.append(f"{label}: external knowledge must set attribution=external_not_paper")
            if binding.get("selected_candidate_id") is not None or binding.get("evidence") is not None:
                errors.append(f"{label}: external common knowledge cannot be attributed to the paper")
        elif category == "not_reported":
            if not isinstance(binding.get("reason"), str) or not binding["reason"].strip():
                errors.append(f"{label}: not_reported requires reason")
        elif category == "conflict":
            conflicts = binding.get("conflicts")
            if not isinstance(conflicts, list) or len(conflicts) < 2:
                errors.append(f"{label}: conflict must retain at least two competing claims")
            else:
                for c_index, conflict in enumerate(conflicts):
                    clabel = f"{label}.conflicts[{c_index}]"
                    if not isinstance(conflict, dict):
                        errors.append(f"{clabel}: must be an object")
                        continue
                    if not isinstance(conflict.get("claim"), str) or not conflict["claim"].strip():
                        errors.append(f"{clabel}: competing claim text is required")
                    candidate = indexes["candidates"].get(conflict.get("candidate_id"))
                    if candidate is None:
                        errors.append(f"{clabel}: unknown candidate_id")
                        continue
                    if candidate["section_id"] != scope_id:
                        errors.append(f"{clabel}: conflict evidence crosses local scopes")
                    if conflict.get("quote") != candidate["quote"] or conflict.get("locator") != candidate["locator"]:
                        errors.append(f"{clabel}: conflict must preserve selected candidate's exact quote and locator")
                    check_quote(conflict.get("quote"), conflict.get("locator"), scope_id,
                                ledger, indexes, errors, clabel)
        check_quantity(binding.get("unit"), "unit", scope_id, ledger, indexes, errors, label)
        check_quantity(binding.get("range"), "range", scope_id, ledger, indexes, errors, label)
        normalized_bindings.append(binding)

    coverage_entries = bindings.get("formula_coverage", [])
    if not isinstance(coverage_entries, list):
        errors.append("formula_coverage must be an array")
        coverage_entries = []
    seen_formulas: set[str] = set()
    normalized_coverage: list[dict[str, Any]] = []
    for index, coverage in enumerate(coverage_entries):
        label = f"formula_coverage[{index}]"
        if not isinstance(coverage, dict):
            errors.append(f"{label}: must be an object")
            continue
        fid = coverage.get("formula_id")
        formula = indexes["formulas"].get(fid)
        if formula is None:
            errors.append(f"{label}: unknown formula_id {fid!r}")
            continue
        if fid in seen_formulas:
            errors.append(f"{label}: duplicate coverage for {fid}")
        seen_formulas.add(fid)
        covered = coverage.get("covered")
        excluded = coverage.get("excluded")
        if covered is True and excluded is True:
            errors.append(f"{label}: covered and excluded are mutually exclusive")
        elif covered is not True and excluded is not True:
            errors.append(f"{label}: every formula occurrence must be covered=true or excluded=true")
        if excluded is True and (not isinstance(coverage.get("reason"), str) or not coverage["reason"].strip()):
            errors.append(f"{label}: excluded formula requires an explicit reason")
        listed = coverage.get("symbol_instance_ids", [])
        if not isinstance(listed, list):
            errors.append(f"{label}: symbol_instance_ids must be an array")
            listed = []
        unknown = [sid for sid in listed if sid not in indexes["symbols"]]
        if unknown:
            errors.append(f"{label}: unknown symbol instances {unknown}")
        if covered is True:
            missing = [sid for sid in formula["symbol_instance_ids"] if sid not in listed]
            if missing:
                errors.append(f"{label}: covered formula omits scoped symbol instances {missing}")
        normalized_coverage.append(coverage)
    missing_formulas = [fid for fid in indexes["formulas"] if fid not in seen_formulas]
    if missing_formulas:
        errors.append(f"formula occurrences without coverage/exclusion entries: {missing_formulas}")
    unbound = [sid for sid in indexes["symbols"] if sid not in bound_ids]
    if unbound:
        warnings.append(f"Unbound scoped symbol instances remain: {unbound}")
    if not raw_bindings and indexes["symbols"]:
        warnings.append("No symbol bindings were authored; result cannot be complete.")
    # Coverage can point only to symbols occurring in that formula.
    for coverage in normalized_coverage:
        formula = indexes["formulas"].get(coverage.get("formula_id"))
        if formula:
            extra = [sid for sid in coverage.get("symbol_instance_ids", [])
                     if sid in indexes["symbols"] and sid not in formula["symbol_instance_ids"]]
            if extra:
                errors.append(f"{coverage.get('formula_id')}: coverage lists symbols from another formula/scope: {extra}")
    conflicts = [{"symbol_instance_id": b.get("symbol_instance_id"), "section_id": b.get("section_id"),
                  "canonical": b.get("canonical"), "claims": b.get("conflicts", [])}
                 for b in normalized_bindings if b.get("category") == "conflict"]
    derived = {"bindings": normalized_bindings, "coverage": normalized_coverage, "unbound": unbound,
               "conflicts": conflicts}
    report = {"valid": not errors, "errors": errors, "warnings": warnings, "case_id": case_id,
              "formula_count": len(indexes["formulas"]), "covered_formula_count": sum(
                  c.get("covered") is True or c.get("excluded") is True for c in normalized_coverage),
              "symbol_instance_count": len(indexes["symbols"]), "bound_symbol_instance_count": len(bound_ids)}
    return report, {**indexes, **derived}


def make_evidence(bindings: list[dict[str, Any]]) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for binding in bindings:
        sid = binding.get("symbol_instance_id")
        category = binding.get("category")
        if isinstance(binding.get("evidence"), dict):
            records.append({"symbol_instance_id": sid, "aspect": "meaning", "category": category,
                            **binding["evidence"]})
        if category == "conflict":
            for claim in binding.get("conflicts", []):
                if isinstance(claim, dict):
                    records.append({"symbol_instance_id": sid, "aspect": "conflict", "category": category, **claim})
        if category == "common_knowledge_external":
            records.append({"symbol_instance_id": sid, "aspect": "meaning", "category": category,
                            "external_basis": binding.get("external_basis"),
                            "attribution": binding.get("attribution")})
        for field in ("unit", "range"):
            quantity = binding.get(field)
            if isinstance(quantity, dict):
                record = {"symbol_instance_id": sid, "aspect": field, **quantity}
                if "evidence_quote" in record:
                    record["quote"] = record["evidence_quote"]
                records.append(record)
    return records


def variable_rows(ledger: dict[str, Any], derived: dict[str, Any]) -> list[dict[str, Any]]:
    by_id = {b.get("symbol_instance_id"): b for b in derived["bindings"]}
    rows = []
    for symbol in ledger.get("symbol_instances", []):
        binding = by_id.get(symbol["symbol_instance_id"])
        rows.append({**symbol, "binding": binding, "binding_state": "bound" if binding else "unbound"})
    return rows


def markdown_table(rows: list[dict[str, Any]], coverage: list[dict[str, Any]],
                   report: dict[str, Any], limitations: list[str]) -> str:
    def cell(value: Any) -> str:
        if value is None:
            return "not reported"
        if isinstance(value, (dict, list)):
            value = json.dumps(value, ensure_ascii=False, sort_keys=True)
        return str(value).replace("|", "\\|").replace("\n", " ")

    lines = ["# Discourse-local variable table", "",
             "Meanings and quantities below are agent-authored claims checked against the extraction ledger. "
             "Candidates alone never confirm a definition.", "",
             "| Instance | Scope | Full symbol | Base glyph | Scripts | Meaning | Evidence category | Unit | Range | Evidence quote |",
             "|---|---|---|---|---|---|---|---|---|---|"]
    for row in rows:
        binding = row.get("binding") or {}
        evidence = binding.get("evidence") if isinstance(binding.get("evidence"), dict) else {}
        unit = binding.get("unit")
        range_value = binding.get("range")
        unit_value = cell(unit) if unit is not None else "not reported"
        range_text = cell(range_value) if range_value is not None else "not reported"
        lines.append("| " + " | ".join(cell(v) for v in [
            row["symbol_instance_id"], row["section_id"], f"`{row['canonical']}`", f"`{row['base_glyph']}`",
            row["scripts"], binding.get("meaning"), binding.get("category", "unbound"),
        ]) + f" | {unit_value} | {range_text} | {cell(evidence.get('quote'))} |")
    lines += ["", "## Formula occurrence coverage", "", "| Formula | Covered | Explicitly excluded | Reason | Scoped symbols |",
              "|---|---|---|---|---|"]
    for item in coverage:
        lines.append(f"| {cell(item.get('formula_id'))} | {cell(item.get('covered'))} | {cell(item.get('excluded'))} | "
                     f"{cell(item.get('reason'))} | {cell(item.get('symbol_instance_ids'))} |")
    lines += ["", "## Validation", "", f"- Valid: **{report['valid']}**"]
    lines += [f"- Error: {error}" for error in report["errors"]]
    lines += [f"- Warning: {warning}" for warning in report["warnings"]]
    if limitations:
        lines += ["", "## Limitations", ""] + [f"- {item}" for item in limitations]
    return "\n".join(lines) + "\n"


def type_name(spec: Any) -> str:
    if isinstance(spec, dict):
        spec = spec.get("type", "")
    if isinstance(spec, list):
        return "union"
    return str(spec or "").lower().replace("json.", "")


def default_for_unknown(spec: Any) -> Any:
    kind = type_name(spec)
    if kind in ("string", "str", "text"):
        return "not reported"
    if kind in ("array", "list") or kind.startswith("array<"):
        return []
    if kind in ("object", "dict", "map") or kind.startswith("object<"):
        return {}
    # In particular, absent numbers/booleans stay null: never substitute zero/false.
    return None


def check_type(value: Any, spec: Any) -> bool:
    kind = type_name(spec)
    if not kind or kind in ("any", "union", "null"):
        return True
    if value is None:
        return True  # Missing evidence is nullable even for a typed numeric field; this is reported, not zero-filled.
    if kind in ("string", "str", "text"):
        return isinstance(value, str)
    if kind in ("array", "list") or kind.startswith("array<"):
        return isinstance(value, list)
    if kind in ("object", "dict", "map") or kind.startswith("object<"):
        return isinstance(value, dict)
    if kind in ("integer", "int"):
        return isinstance(value, int) and not isinstance(value, bool)
    if kind in ("number", "numeric", "float", "double"):
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    if kind in ("boolean", "bool"):
        return isinstance(value, bool)
    return True


def assemble_result(case: dict[str, Any], ledger: dict[str, Any], bindings: dict[str, Any],
                    report: dict[str, Any], derived: dict[str, Any]) -> dict[str, Any]:
    contract = case.get("output_contract", {})
    if not isinstance(contract, dict):
        contract = {}
    fields, field_types, status_enum = contract_fields(contract)
    no_formula = not ledger.get("formulas")
    requested = str(bindings.get("requested_status") or "").lower().replace("-", "_")
    incomplete = bool(report["errors"] or report["warnings"] or derived["unbound"])
    if report["errors"]:
        # Early termination and invalid analysis both remain explicitly non-successful;
        # prefer partial when offered so time-limited runs yield an honest early result.
        priorities = ["partial", "invalid", "insufficient_evidence", "failed"]
        fallback = "partial"
    elif no_formula or requested in ("partial", "insufficient_evidence", "incomplete"):
        priorities = (["insufficient_evidence", "partial", "incomplete"] if no_formula
                      else ["partial", "incomplete", "insufficient_evidence"])
        fallback = "insufficient_evidence" if no_formula else "partial"
    elif incomplete:
        priorities = ["partial", "incomplete", "insufficient_evidence"]
        fallback = "partial"
    else:
        priorities = ["complete", "completed", "success", "ok"]
        fallback = "complete"
    status = choose_status(status_enum, priorities, fallback)
    rows = variable_rows(ledger, derived)
    evidence = make_evidence(derived["bindings"])
    limitations = []
    for item in list(ledger.get("warnings", [])) + list(bindings.get("limitations", [])):
        if isinstance(item, str) and item and item not in limitations:
            limitations.append(item)
    if derived["unbound"]:
        item = "Not all scoped symbol instances have evidence bindings."
        if item not in limitations:
            limitations.append(item)
    if no_formula:
        item = "No formula representation or source values are available; quantities are null, not zero."
        if item not in limitations:
            limitations.append(item)
    coverage = derived["coverage"]
    base: dict[str, Any] = {
        "case_id": case["case_id"], "status": status, "variables": rows,
        "formula_occurrences": ledger.get("formulas", []), "formula_coverage": coverage,
        "evidence": evidence, "limitations": limitations, "conflicts": derived["conflicts"],
        "validation": {"valid": report["valid"], "errors": report["errors"], "warnings": report["warnings"],
                       "contract_fields": fields},
        "source_summary": ledger["source_summary"],
        "scope_resolution": "Symbols are keyed by base glyph + full scripts + local section; no global definition is imposed.",
        "notes": bindings.get("notes", ""),
    }
    authored = bindings.get("output_fields", {})
    if authored is None:
        authored = {}
    if not isinstance(authored, dict):
        authored = {}
        report["warnings"].append("output_fields was not an object and was ignored")
    # Common alias semantics preserve the exact contract's spelling.
    for field in fields:
        key = canonical_key(field)
        if field in base:
            continue
        if field in authored:
            base[field] = authored[field]
            continue
        target = STANDARD_ALIASES.get(key)
        if target in base:
            base[field] = base[target]
        elif key in base:
            base[field] = base[key]
        else:
            base[field] = default_for_unknown(field_types.get(field))
            report["warnings"].append(f"Contract field {field!r} had no derivable evidence-backed value; used a null/empty placeholder.")
    for field, spec in field_types.items():
        if field in base and not check_type(base[field], spec):
            report["warnings"].append(f"Contract field {field!r} does not match declared type {type_name(spec)!r}.")
    if status_enum and status not in status_enum:
        report["errors"].append(f"Selected status {status!r} is outside status_enum")
    base["status"] = status
    base["validation"] = {"valid": not report["errors"], "errors": report["errors"], "warnings": report["warnings"],
                          "contract_fields": fields}
    # Additional agent-authored fields are permitted, but contract fields cannot be overwritten late.
    for field, value in authored.items():
        base.setdefault(field, value)
    return base


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--case", default="/input/case.json")
    parser.add_argument("--work", default="/app/work")
    parser.add_argument("--output", default="/app/output")
    parser.add_argument("--bindings", default=None)
    parser.add_argument("--validate-only", action="store_true")
    parser.add_argument("--report", default=None, help="Optional validation report path")
    args = parser.parse_args(argv)
    case_path = Path(args.case).resolve()
    work = Path(args.work).resolve()
    output = Path(args.output).resolve()
    try:
        case = load_json(case_path)
        ledger = load_json(work / "ledger.json")
        if not isinstance(case, dict) or ledger.get("case_id") != case.get("case_id"):
            raise ValueError("case and ledger case_id differ")
        bindings_path = Path(args.bindings).resolve() if args.bindings else work / "bindings.json"
        if not bindings_path.is_file() and not args.bindings and (work / "bindings.template.json").is_file():
            bindings_path = work / "bindings.template.json"
        bindings = load_json(bindings_path)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"finalize: fatal: {exc}", file=sys.stderr)
        return 1
    report, derived = validate(ledger, bindings)
    result = assemble_result(case, ledger, bindings, report, derived)
    # Assembly can discover contract errors; synchronize the top-level report.
    report["valid"] = not report["errors"]
    report["warnings"] = result["validation"]["warnings"]
    report_path = Path(args.report).resolve() if args.report else work / "validation.json"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if args.validate_only:
        print(json.dumps(report, ensure_ascii=False, indent=2))
        if report["errors"]:
            print(f"finalize: validation failed with {len(report['errors'])} error(s)", file=sys.stderr)
            return 2
        return 0
    output.mkdir(parents=True, exist_ok=True)
    rows = variable_rows(ledger, derived)
    limitations = result.get("limitations", [])
    if not isinstance(limitations, list):
        limitations = []
    (output / "variable_table.json").write_text(json.dumps({
        "case_id": case["case_id"], "status": result["status"], "variables": rows,
        "formula_occurrences": ledger.get("formulas", []), "formula_coverage": derived["coverage"],
        "evidence": make_evidence(derived["bindings"]), "conflicts": derived["conflicts"],
        "limitations": limitations, "source_summary": ledger["source_summary"], "validation": report,
    }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (output / "variable_table.md").write_text(
        markdown_table(rows, derived["coverage"], report, limitations), encoding="utf-8")
    (output / "result.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"case_id": case["case_id"], "status": result["status"],
                      "valid": report["valid"], "errors": len(report["errors"]),
                      "output": str(output)}, ensure_ascii=False))
    if report["errors"]:
        print(f"finalize: validation failed with {len(report['errors'])} error(s); partial/invalid outputs retained", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
