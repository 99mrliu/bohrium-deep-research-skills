#!/usr/bin/env python3
"""Validate dynamic output_contract, stale evidence verdicts, and export honestly."""

import argparse
import copy
import json
import re
import sys

from source_map import atomic_json, sha256_bytes


class FinalizeInputError(Exception):
    pass


def load_json(path, label):
    try:
        with open(path, "rb") as handle:
            raw = handle.read()
        if not raw:
            raise FinalizeInputError(label + " is empty: " + path)
        return json.loads(raw.decode("utf-8")), raw
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise FinalizeInputError("cannot read %s %s: %s" % (label, path, error)) from error


def named_spec(name, metadata=None):
    if not isinstance(name, str) or not name.strip():
        raise FinalizeInputError("output contract contains an empty or non-string field name")
    if metadata is None:
        metadata = {}
    if isinstance(metadata, str):
        metadata = {"type": metadata}
    if not isinstance(metadata, dict):
        # Direct field -> non-string metadata is still retained as metadata, with unknown type.
        metadata = {"metadata": metadata}
    result = copy.deepcopy(metadata)
    result["name"] = name
    return result


def extract_contract(contract):
    """Return ordered specs for all four organizer contract shapes without dropping fields."""
    specs = []
    if isinstance(contract, list):
        if not all(isinstance(name, str) for name in contract):
            raise FinalizeInputError("list output_contract must be list[str]")
        specs = [named_spec(name) for name in contract]
    elif isinstance(contract, dict) and "fields" in contract:
        fields = contract["fields"]
        if isinstance(fields, list):
            for entry in fields:
                if isinstance(entry, str):
                    specs.append(named_spec(entry))
                elif isinstance(entry, dict) and isinstance(entry.get("name"), str):
                    specs.append(named_spec(entry["name"], entry))
                else:
                    raise FinalizeInputError("fields list entries must be strings or objects with name")
        elif isinstance(fields, dict):
            specs = [named_spec(name, metadata) for name, metadata in fields.items()]
        else:
            raise FinalizeInputError("output_contract.fields must be a list or direct mapping")
    elif isinstance(contract, dict):
        # Direct mapping: every key is a submitted field, regardless of metadata shape.
        specs = [named_spec(name, metadata) for name, metadata in contract.items()]
    else:
        raise FinalizeInputError("unsupported output_contract shape")
    if not specs:
        raise FinalizeInputError("output_contract declares no fields")
    names = [spec["name"] for spec in specs]
    if len(set(names)) != len(names):
        raise FinalizeInputError("output_contract contains duplicate field names")
    return specs


def expected_kind(spec):
    if not isinstance(spec, dict):
        return None
    value = spec.get("type", spec.get("field_type"))
    if isinstance(value, dict) and "name" in value:
        value = value["name"]
    if value is None:
        return None
    if not isinstance(value, str):
        return "unknown"
    label = value.strip().lower().replace(" ", "")
    aliases = {
        "str": "string", "text": "string", "markdown": "string", "string": "string",
        "list": "array", "array": "array", "list[str]": "array", "array[string]": "array",
        "list[dict]": "array", "array[object]": "array",
        "dict": "object", "map": "object", "object": "object",
        "bool": "boolean", "boolean": "boolean",
        "int": "integer", "integer": "integer",
        "float": "number", "number": "number", "numeric": "number",
        "any": "any", "json": "any", "unknown": "any",
    }
    return aliases.get(label, "unknown")


def matches_kind(value, kind):
    if kind == "any":
        return True
    if kind == "string":
        return isinstance(value, str)
    if kind == "array":
        return isinstance(value, list)
    if kind == "object":
        return isinstance(value, dict)
    if kind == "boolean":
        return isinstance(value, bool)
    if kind == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    if kind == "number":
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    return False


def check_contract(draft, specs):
    errors = []
    for spec in specs:
        name = spec["name"]
        if name not in draft:
            errors.append("missing original output_contract field at top level: " + name)
            continue
        value = draft[name]
        if value is None:
            errors.append("field is null and cannot be a final success value: " + name)
            continue
        kind = expected_kind(spec)
        if kind == "unknown":
            errors.append("unknown declared type for field %s: %r" % (name, spec.get("type", spec.get("field_type"))))
        elif kind is not None and not matches_kind(value, kind):
            errors.append("type mismatch for field %s: expected %s, found %s" % (name, kind, type(value).__name__))
        enum = spec.get("enum")
        if isinstance(enum, list) and value not in enum:
            errors.append("value outside declared enum for field: " + name)
        if isinstance(value, list):
            minimum = spec.get("minItems", spec.get("min_items"))
            maximum = spec.get("maxItems", spec.get("max_items"))
            if isinstance(minimum, int) and not isinstance(minimum, bool) and len(value) < minimum:
                errors.append("array below minItems for field: " + name)
            if isinstance(maximum, int) and not isinstance(maximum, bool) and len(value) > maximum:
                errors.append("array above maxItems for field: " + name)
    return errors


def public_sources(source_map):
    return [
        {
            "source_id": source.get("source_id"),
            "source_file": source.get("source_file"),
            "format": source.get("format"),
            "sha256": source.get("sha256"),
            "byte_count": source.get("byte_count"),
            "node_count": source.get("node_count"),
        }
        for source in source_map.get("sources", [])
        if isinstance(source, dict)
    ]


def check_source_bytes(source_map):
    """Re-read actual bytes at export time; a prior gate pass is not enough after mutation."""
    if not isinstance(source_map, dict):
        return ["source map top level is not an object"]
    sources = source_map.get("sources")
    if not isinstance(sources, list) or not sources:
        return ["source map has no sources for final byte verification"]
    if not isinstance(source_map.get("nodes"), list) or not source_map["nodes"]:
        return ["source map has no nodes for final evidence verification"]
    errors = []
    for source in sources:
        if not isinstance(source, dict):
            errors.append("source map contains a non-object source record")
            continue
        label = str(source.get("source_file", "<unknown>"))
        digest = source.get("sha256")
        path = source.get("file_path")
        if not isinstance(digest, str) or not re.fullmatch(r"[0-9a-f]{64}", digest) or not isinstance(path, str) or not path:
            errors.append("source map lacks valid path/SHA256 identity: " + label)
            continue
        try:
            with open(path, "rb") as handle:
                actual = sha256_bytes(handle.read())
        except OSError as error:
            errors.append("cannot re-read source at export: %s: %s" % (label, error))
            continue
        if actual != digest:
            errors.append("source bytes changed before export: " + label)
    return errors


def load_optional(path, label, failures):
    if not path:
        failures.append(label + " was not supplied")
        return None, None
    try:
        return load_json(path, label)
    except FinalizeInputError as error:
        failures.append(str(error))
        return None, None


def append_change(result, record):
    existing = result.get("change_records", [])
    if isinstance(existing, list):
        result["change_records"] = existing + [record]
    else:
        # Preserve the submitted value verbatim rather than coercing or discarding it.
        result["change_records_original"] = existing
        result["change_records"] = [record]


def main():
    parser = argparse.ArgumentParser(description="Export a complete result only after fresh four-item gate success.")
    parser.add_argument("--case", required=True)
    parser.add_argument("--draft", required=True)
    parser.add_argument("--source-map")
    parser.add_argument("--evidence-verdict")
    parser.add_argument("--result", required=True)
    parser.add_argument("--allow-partial", action="store_true")
    parser.add_argument("--limits", action="append", default=[], help="explicit partial limitation; repeatable and required for partial export")
    args = parser.parse_args()

    failures = []
    try:
        case, _ = load_json(args.case, "case")
        draft, draft_raw = load_json(args.draft, "draft")
        if not isinstance(case, dict) or not isinstance(draft, dict):
            raise FinalizeInputError("case and draft top levels must be objects")
        if "case_id" not in case or case["case_id"] is None or isinstance(case["case_id"], bool):
            raise FinalizeInputError("original case.json lacks case_id")
        if "output_contract" not in case:
            raise FinalizeInputError("original case.json lacks output_contract")
        specs = extract_contract(case["output_contract"])
        if "case_id" in draft and draft["case_id"] != case["case_id"]:
            raise FinalizeInputError("draft case_id differs from original case.json")
        failures.extend(check_contract(draft, specs))
        source_map, source_map_raw = load_optional(args.source_map, "source map", failures)
        verdict, verdict_raw = load_optional(args.evidence_verdict, "evidence verdict", failures)
        gate_ok = False
        if verdict is not None:
            if not isinstance(verdict, dict):
                failures.append("evidence verdict top level is not an object")
            else:
                if verdict.get("draft_sha256") != sha256_bytes(draft_raw):
                    failures.append("evidence verdict is stale for the current draft")
                if source_map_raw is not None and verdict.get("source_map_sha256") != sha256_bytes(source_map_raw):
                    failures.append("evidence verdict is stale for the current source map")
                summary = verdict.get("summary", {})
                policy = verdict.get("policy", {})
                items = verdict.get("items", [])
                gate_ok = bool(
                    verdict.get("ok") is True
                    and isinstance(summary, dict)
                    and summary.get("item_count") == 4
                    and summary.get("passed_items") == 4
                    and not summary.get("failed_items")
                    and not summary.get("zero_atom_items")
                    and not summary.get("orphan_atom_ids")
                    and isinstance(policy, dict)
                    and policy.get("expected_items") == 4
                    and isinstance(items, list)
                    and len(items) == 4
                    and all(isinstance(item, dict) and item.get("status") == "pass" for item in items)
                )
                if not gate_ok:
                    failures.append("evidence gate is absent, failed, or not a trusted four-item pass")
        if source_map is not None:
            failures.extend(check_source_bytes(source_map))
        if not isinstance(draft.get("Bank"), list) or len(draft.get("Bank")) != 4:
            failures.append("current draft Bank does not contain exactly four items")

        if failures and not args.allow_partial:
            for failure in failures:
                print("FINALIZE_FAIL_CLOSED: " + failure, file=sys.stderr)
            return 1
        if args.allow_partial and not any(isinstance(limit, str) and limit.strip() for limit in args.limits):
            print("FINALIZE_INPUT_ERROR: --allow-partial requires at least one non-empty --limits", file=sys.stderr)
            return 2

        result = copy.deepcopy(draft)  # all submitted content fields, including extras, survive
        result["case_id"] = case["case_id"]
        result["success"] = not args.allow_partial and not failures
        result["status"] = "partial" if args.allow_partial or failures else "complete"
        if ("sources" not in result or result.get("sources") == []) and isinstance(source_map, dict):
            # An empty placeholder may be replaced; non-empty submitted sources are never discarded.
            result["sources"] = public_sources(source_map)
        elif "sources" not in result:
            result["sources"] = []
        result.setdefault("uncertainty", [])
        result.setdefault("change_records", [])
        limitation_records = [limit for limit in args.limits if isinstance(limit, str) and limit.strip()]
        limitation_records.extend(failures)
        if args.allow_partial:
            existing_limits = result.get("limits", [])
            if isinstance(existing_limits, list):
                result["limits"] = existing_limits + limitation_records
            else:
                result["limits"] = [{"submitted_limits_preserved": existing_limits}] + limitation_records
        if isinstance(verdict, dict):
            result["evidence_gate"] = {
                "ok": gate_ok,
                "summary": copy.deepcopy(verdict.get("summary")),
                "semantic_status": verdict.get("policy", {}).get("semantic_status")
                    if isinstance(verdict.get("policy"), dict) else None,
                "draft_sha256": verdict.get("draft_sha256"),
                "source_map_sha256": verdict.get("source_map_sha256"),
            }
        else:
            result["evidence_gate"] = {"ok": False, "summary": None, "limits": limitation_records}
        append_change(result, {
            "stage": "finalize",
            "status": result["status"],
            "note": "Exported with explicit limits; no gate failure converted to success."
                if result["status"] == "partial" else
                "Fresh source-byte check, four-item atom evidence gate, and dynamic contract check passed.",
        })
        if result["status"] == "complete" and (failures or not gate_ok):
            raise FinalizeInputError("internal fail-closed violation")
        atomic_json(args.result, result)
    except FinalizeInputError as error:
        print("FINALIZE_INPUT_ERROR: " + str(error), file=sys.stderr)
        return 2
    except OSError as error:
        print("FINALIZE_IO_ERROR: " + str(error), file=sys.stderr)
        return 2

    print("FINALIZE_%s case_id=%s output=%s" % (
        "PARTIAL" if args.allow_partial else "OK", result["case_id"], args.result))
    if args.allow_partial:
        for limit in result.get("limits", []):
            print("PARTIAL_LIMIT: " + str(limit), file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
