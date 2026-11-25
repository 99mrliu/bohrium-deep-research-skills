#!/usr/bin/env python3
"""Audit and export a dynamic top-level contract as success or explicit partial."""

from __future__ import annotations

import argparse
import copy
import json
import sys
from typing import Any, Dict, List, Tuple

from blueprint import audit_blueprint
from common import (
    canonical_bytes, empty_for_descriptor, fail_message, load_json,
    normalized_text, parse_output_contract, write_json,
)
from item_audit import audit_items

STANDARD_FIELDS = ("case_id", "items", "status", "sources", "uncertainty", "change_records", "defects")


def _defect(code: str, path: str, message: str) -> Dict[str, str]:
    return {"code": code, "path": path, "message": message}


def _extend_unique(target: List[Any], values: Any) -> None:
    if not isinstance(values, list):
        return
    seen = {canonical_bytes(value) for value in target}
    for value in values:
        marker = canonical_bytes(value)
        if marker not in seen:
            target.append(copy.deepcopy(value))
            seen.add(marker)


def _case_sources(case: Dict[str, Any]) -> List[Dict[str, Any]]:
    materials = case.get("materials", case.get("sources", []))
    output: List[Dict[str, Any]] = []
    if isinstance(materials, list):
        for entry in materials:
            if isinstance(entry, dict):
                output.append(copy.deepcopy(entry))
            elif isinstance(entry, str):
                output.append({"source_id": entry, "path": entry})
    elif isinstance(materials, dict):
        for source_id, entry in materials.items():
            if isinstance(entry, dict):
                record = copy.deepcopy(entry)
                record.setdefault("source_id", source_id)
            else:
                record = {"source_id": source_id, "path": entry}
            output.append(record)
    return output


def _field_semantic(descriptor: Dict[str, Any]) -> str:
    declared = descriptor.get("semantic", descriptor.get("role"))
    name = declared if isinstance(declared, str) else descriptor.get("name", "")
    key = normalized_text(name)
    aliases = {
        "caseid": "case_id", "id": "case_id",
        "items": "items", "itembank": "items", "questions": "items",
        "benchmarkitems": "items", "benchmarkdraft": "items", "draftitems": "items",
        "status": "status", "resultstatus": "status",
        "sources": "sources", "sourcemanifest": "sources", "materials": "sources",
        "uncertainty": "uncertainty", "uncertainties": "uncertainty",
        "changerecords": "change_records", "changes": "change_records", "changelog": "change_records",
        "defects": "defects", "errors": "defects", "auditdefects": "defects",
        "blueprint": "blueprint", "constructblueprint": "blueprint",
        "audits": "audits", "auditreports": "audits",
    }
    return aliases.get(key, key)


def export_result(
    case: Dict[str, Any], blueprint: Any, bank: Any,
    blueprint_audit: Dict[str, Any], item_audit: Dict[str, Any],
    load_defects: List[Dict[str, str]], contract_problems: List[str],
) -> Dict[str, Any]:
    defects = copy.deepcopy(load_defects)
    defects.extend(_defect("OUTPUT_CONTRACT", "$.output_contract", problem) for problem in contract_problems)
    for audit_name, audit in (("blueprint", blueprint_audit), ("items", item_audit)):
        for error in audit.get("errors", []):
            defect = copy.deepcopy(error)
            defect["path"] = "$.%s_audit%s" % (audit_name, str(error.get("path", "$")))
            defects.append(defect)
    items = bank.get("items", []) if isinstance(bank, dict) and isinstance(bank.get("items"), list) else []
    if len(items) != 4:
        defects.append(_defect("ITEM_COUNT", "$.items", "Strict success requires exactly four items; found %d." % len(items)))
    status = "success" if not defects else "partial"

    sources = _case_sources(case)
    uncertainties: List[Any] = []
    _extend_unique(uncertainties, case.get("uncertainty"))
    if isinstance(bank, dict):
        _extend_unique(uncertainties, bank.get("uncertainty"))
    for index, item in enumerate(items):
        if isinstance(item, dict):
            _extend_unique(uncertainties, item.get("uncertainty"))
    if status == "partial":
        uncertainties.append({
            "status": "incomplete",
            "statement": "The exported bank is partial; listed defects must be resolved before treating all four items as a complete draft.",
        })
    changes: List[Any] = []
    _extend_unique(changes, case.get("change_records"))
    if isinstance(bank, dict):
        _extend_unique(changes, bank.get("change_records"))

    available = {
        "case_id": case.get("case_id"),
        "items": copy.deepcopy(items),
        "status": status,
        "sources": sources,
        "uncertainty": uncertainties,
        "change_records": changes,
        "defects": defects,
        "blueprint": copy.deepcopy(blueprint) if isinstance(blueprint, dict) else {},
        "audits": {"blueprint": blueprint_audit, "items": item_audit},
    }
    descriptors, _ = parse_output_contract(case.get("output_contract"))
    by_name = {descriptor["name"]: descriptor for descriptor in descriptors}
    ordered_names = list(STANDARD_FIELDS)
    ordered_names.extend(name for name in by_name if name not in ordered_names)
    result: Dict[str, Any] = {}
    for name in ordered_names:
        descriptor = by_name.get(name, {"name": name})
        semantic = _field_semantic(descriptor)
        if semantic in available:
            value = copy.deepcopy(available[semantic])
            if semantic == "items" and descriptor.get("type") in {"object", "map"}:
                value = {
                    str(entry.get("item_id", "index-%d" % index)): entry
                    for index, entry in enumerate(value) if isinstance(entry, dict)
                }
            result[name] = value
        else:
            result[name] = empty_for_descriptor(descriptor)
            if "default" not in descriptor:
                result["defects"].append(_defect(
                    "UNMAPPED_CONTRACT_FIELD", "$." + name,
                    "No safe runtime source maps this contract field; exported its type-appropriate empty value and forced partial status.",
                ))
    # An unmapped field discovered during export must never leave status as success.
    if result["defects"]:
        for name in ordered_names:
            descriptor = by_name.get(name, {"name": name})
            if _field_semantic(descriptor) == "status":
                result[name] = "partial"
    return result


def main(argv: List[str] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--case", required=True, help="Actual /input/case.json or example case")
    parser.add_argument("--blueprint", help="Authored blueprint.json")
    parser.add_argument("--items", help="Authored item_bank.json")
    parser.add_argument("--output", required=True, help="Contract-shaped result.json destination")
    parser.add_argument("--partial-only", action="store_true", help="Export an honest early partial without reading blueprint/items")
    parser.add_argument("--allow-partial", action="store_true", help="Return 0 for a written partial; status remains partial and defects remain visible")
    args = parser.parse_args(argv)
    try:
        case = load_json(args.case)
        if not isinstance(case, dict):
            raise ValueError("case.json root must be an object")
        if "case_id" not in case:
            raise ValueError("case.json must contain case_id so it can be preserved")
        descriptors, contract_problems = parse_output_contract(case.get("output_contract"))
        del descriptors
        load_defects: List[Dict[str, str]] = []
        blueprint: Any = {}
        bank: Any = {}
        if args.partial_only:
            if args.blueprint or args.items:
                parser.error("--partial-only cannot be combined with --blueprint or --items")
            load_defects.extend([
                _defect("BLUEPRINT_NOT_SUPPLIED", "$.blueprint", "Early partial export: no authored blueprint supplied."),
                _defect("ITEMS_NOT_SUPPLIED", "$.items", "Early partial export: no scientific items supplied."),
            ])
            blueprint_audit = {"status": "fail", "errors": [_defect("NOT_RUN", "$", "Blueprint audit not run in partial-only mode.")]}
            item_audit = {"status": "fail", "errors": [_defect("NOT_RUN", "$", "Item audit not run in partial-only mode.")]}
        else:
            if not args.blueprint or not args.items:
                parser.error("--blueprint and --items are required unless --partial-only is used")
            try:
                blueprint = load_json(args.blueprint)
            except ValueError as exc:
                load_defects.append(_defect("BLUEPRINT_LOAD", "$.blueprint", str(exc)))
            try:
                bank = load_json(args.items)
            except ValueError as exc:
                load_defects.append(_defect("ITEMS_LOAD", "$.items", str(exc)))
            blueprint_audit = audit_blueprint(blueprint, case)
            item_audit = audit_items(bank, blueprint, case)
        result = export_result(case, blueprint, bank, blueprint_audit, item_audit, load_defects, contract_problems)
        write_json(args.output, result)
        sys.stdout.write("Wrote %s with status=%s, items=%d, defects=%d\n" % (
            args.output, result.get("status"),
            len(result.get("items", [])) if isinstance(result.get("items"), list) else len(result.get("items", {})),
            len(result.get("defects", [])),
        ))
        if result["status"] == "partial" and not args.allow_partial:
            return 2
        return 0
    except (ValueError, OSError) as exc:
        fail_message(exc)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
