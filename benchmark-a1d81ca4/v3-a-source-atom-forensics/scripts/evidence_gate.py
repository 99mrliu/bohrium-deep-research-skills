#!/usr/bin/env python3
"""Structural, lexical, and numeric evidence gate for a four-item draft."""

import argparse
import hashlib
import json
import re
import sys
import unicodedata

from source_map import SCHEMA_VERSION as MAP_SCHEMA_VERSION, atomic_json, normalized, sha256_bytes

EXPECTED_ITEMS = 4
VERDICT_SCHEMA_VERSION = "evidence-verdict/v1"
NUMERIC = re.compile(
    r"(?<![A-Za-z0-9_])[+\-\u2212]?(?:\d+(?:,\d{3})*(?:\.\d+)?|\.\d+)(?:[eE][+\-]?\d+)?%?"
)


class GateInputError(Exception):
    pass


def load_json(path, label):
    try:
        with open(path, "rb") as handle:
            raw = handle.read()
        return json.loads(raw.decode("utf-8")), raw
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise GateInputError("cannot read %s %s: %s" % (label, path, error)) from error


def error(code, message):
    return {"code": code, "message": message}


def nonempty_text(value):
    return isinstance(value, str) and bool(value.strip())


def nonempty_value(value):
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, (list, dict)):
        return bool(value)
    return True


def validate_source_map(source_map):
    if not isinstance(source_map, dict) or source_map.get("schema_version") != MAP_SCHEMA_VERSION:
        raise GateInputError("source map schema_version must be " + MAP_SCHEMA_VERSION)
    sources = source_map.get("sources")
    nodes = source_map.get("nodes")
    if not isinstance(sources, list) or not sources:
        raise GateInputError("source map has no sources")
    if not isinstance(nodes, list) or not nodes:
        raise GateInputError("source map has no nodes")
    source_ids = set()
    rechecked = []
    for index, source in enumerate(sources):
        if not isinstance(source, dict) or not nonempty_text(source.get("source_id")):
            raise GateInputError("invalid source record at index %d" % index)
        source_id = source["source_id"]
        if source_id in source_ids:
            raise GateInputError("duplicate source_id: " + source_id)
        source_ids.add(source_id)
        digest = source.get("sha256")
        file_path = source.get("file_path")
        if not isinstance(digest, str) or not re.fullmatch(r"[0-9a-f]{64}", digest):
            raise GateInputError("invalid source byte SHA256 for " + source_id)
        if not nonempty_text(file_path):
            raise GateInputError("source map lacks re-checkable file_path for " + source_id)
        try:
            with open(file_path, "rb") as handle:
                actual = sha256_bytes(handle.read())
        except OSError as exc:
            raise GateInputError("cannot re-read source %s: %s" % (file_path, exc)) from exc
        if actual != digest:
            raise GateInputError("source bytes changed after indexing: " + file_path)
        rechecked.append({"source_id": source_id, "file_path": file_path, "sha256": actual})
    node_by_id = {}
    for index, node in enumerate(nodes):
        if not isinstance(node, dict):
            raise GateInputError("invalid node at index %d" % index)
        node_id = node.get("node_id")
        text = node.get("text")
        if not nonempty_text(node_id) or not isinstance(text, str) or not text.strip():
            raise GateInputError("node lacks node_id or non-empty text at index %d" % index)
        if node_id in node_by_id:
            raise GateInputError("duplicate node_id: " + node_id)
        if node.get("source_id") not in source_ids:
            raise GateInputError("node has unknown source_id: " + node_id)
        expected_text_hash = sha256_bytes(text.encode("utf-8"))
        if node.get("text_sha256") != expected_text_hash:
            raise GateInputError("node text hash mismatch: " + node_id)
        if node.get("normalized_text") != normalized(text):
            raise GateInputError("node normalized_text mismatch: " + node_id)
        if not nonempty_text(node.get("path")) or not isinstance(node.get("locator"), dict):
            raise GateInputError("node lacks path/locator: " + node_id)
        node_by_id[node_id] = node
    return node_by_id, rechecked


def answer_elements(reference):
    """Return (elements, errors); supported shapes are deliberately explicit."""
    errors = []
    raw_elements = None
    if isinstance(reference, str):
        raw_elements = [{"id": "answer", "text": reference}]
    elif isinstance(reference, list):
        raw_elements = reference
    elif isinstance(reference, dict):
        if "elements" not in reference:
            return [], [error("reference_answer_shape", "reference_answer object requires an elements list")]
        raw_elements = reference["elements"]
    else:
        return [], [error("reference_answer_shape", "reference_answer must be a string, list, or object with elements")]
    if not isinstance(raw_elements, list) or not raw_elements:
        return [], [error("reference_answer_empty", "reference_answer must have at least one substantive element")]
    elements = []
    seen = set()
    for position, entry in enumerate(raw_elements):
        if isinstance(entry, str):
            element_id = "answer" if len(raw_elements) == 1 else "answer_%d" % (position + 1)
            text = entry
        elif isinstance(entry, dict):
            element_id = entry.get("id")
            text = entry.get("text")
        else:
            errors.append(error("answer_element_shape", "answer element %d must be a string or id/text object" % position))
            continue
        if not nonempty_text(element_id) or not nonempty_text(text):
            errors.append(error("answer_element_empty", "answer element %d requires non-empty id and text" % position))
            continue
        if element_id in seen:
            errors.append(error("answer_element_duplicate", "duplicate answer element id: " + element_id))
            continue
        seen.add(element_id)
        elements.append({"id": element_id, "text": text})
    return elements, errors


def numeric_tokens(text):
    normalized_text = unicodedata.normalize("NFKC", text)
    return [match.group(0) for match in NUMERIC.finditer(normalized_text)]


def validate_rubric(rubric):
    if not isinstance(rubric, dict):
        return [error("rubric_shape", "rubric must be an object with 0/1/2 criteria")]
    errors = []
    for score in ("0", "1", "2"):
        if not nonempty_text(rubric.get(score)):
            errors.append(error("rubric_score_missing", "rubric requires non-empty criterion " + score))
    return errors


def verdict_for_draft(draft, node_by_id, allow_unsupported_numeric):
    global_errors = []
    item_verdicts = []
    zero_atom_items = []
    orphan_atom_ids = []
    all_atom_ids = set()
    bank = draft.get("Bank") if isinstance(draft, dict) else None
    if not isinstance(bank, list):
        global_errors.append(error("bank_shape", "draft top-level Bank must be a list"))
        bank = []
    if len(bank) != EXPECTED_ITEMS:
        global_errors.append(error("bank_item_count", "Bank must contain exactly four items; found %d" % len(bank)))
    atom_total = 0

    for item_index, item in enumerate(bank):
        if not isinstance(item, dict):
            item_verdicts.append({
                "item_index": item_index,
                "item_id": None,
                "status": "fail",
                "errors": [error("item_shape", "Bank item must be an object")],
                "answer_elements": [],
                "atoms": [],
            })
            continue
        item_id = item.get("id") if nonempty_text(item.get("id")) else "item_index_%d" % item_index
        errors = []
        if not nonempty_text(item.get("id")):
            errors.append(error("item_id_missing", "item requires a non-empty string id"))
        for field in ("task", "scope/input_material", "data_license"):
            if not nonempty_value(item.get(field)):
                errors.append(error("required_field_missing", "missing or empty " + field))
        if isinstance(item.get("difficulty"), bool) or not nonempty_value(item.get("difficulty")):
            errors.append(error("required_field_missing", "missing or empty difficulty"))
        errors.extend(validate_rubric(item.get("rubric")))
        elements, element_errors = answer_elements(item.get("reference_answer"))
        errors.extend(element_errors)
        element_ids = {element["id"] for element in elements}
        coverage = {element_id: [] for element_id in element_ids}
        evidence = item.get("evidence")
        if not isinstance(evidence, dict) or not isinstance(evidence.get("atoms"), list):
            errors.append(error("evidence_shape", "evidence must be an object containing an atoms list"))
            atoms = []
        else:
            atoms = evidence["atoms"]
        if not atoms:
            errors.append(error("zero_atoms", "item has zero evidence atoms"))
            zero_atom_items.append(item_id)
        atom_total += len(atoms)
        atom_verdicts = []

        for atom_index, atom in enumerate(atoms):
            atom_errors = []
            atom_warnings = []
            orphan = False
            if not isinstance(atom, dict):
                atom_verdicts.append({
                    "atom_index": atom_index,
                    "atom_id": None,
                    "status": "fail",
                    "errors": [error("atom_shape", "atom must be an object")],
                })
                continue
            atom_id = atom.get("id") if nonempty_text(atom.get("id")) else "%s_atom_%d" % (item_id, atom_index)
            if not nonempty_text(atom.get("id")):
                atom_errors.append(error("atom_id_missing", "atom requires a non-empty id"))
            elif atom_id in all_atom_ids:
                atom_errors.append(error("atom_id_duplicate", "atom id is not globally unique: " + atom_id))
            else:
                all_atom_ids.add(atom_id)
            for field in ("text", "type", "reason"):
                if not nonempty_text(atom.get(field)):
                    atom_errors.append(error("atom_field_missing", "atom requires non-empty " + field))
            mappings = atom.get("answer_element_ids")
            if not isinstance(mappings, list) or not mappings or not all(nonempty_text(entry) for entry in mappings):
                atom_errors.append(error("orphan_answer_mapping", "answer_element_ids must be a non-empty string list"))
                orphan = True
                mappings = []
            elif len(set(mappings)) != len(mappings):
                atom_errors.append(error("orphan_answer_mapping", "answer_element_ids contains duplicates"))
                orphan = True
            for mapped_id in mappings:
                if mapped_id not in element_ids:
                    atom_errors.append(error("orphan_answer_mapping", "unknown answer element: " + str(mapped_id)))
                    orphan = True
                else:
                    coverage[mapped_id].append(atom_id)

            atom_evidence = atom.get("evidence")
            quote = None
            node = None
            if not isinstance(atom_evidence, dict):
                atom_errors.append(error("evidence_atom_shape", "each atom requires one evidence object"))
                orphan = True
            else:
                if not nonempty_text(atom_evidence.get("reason")):
                    atom_errors.append(error("adjudication_reason_missing", "evidence.reason must record agent semantic adjudication"))
                node_id = atom_evidence.get("node_id")
                quote = atom_evidence.get("quote")
                if not nonempty_text(node_id) or node_id not in node_by_id:
                    atom_errors.append(error("orphan_node", "evidence node_id is absent from the source map"))
                    orphan = True
                else:
                    node = node_by_id[node_id]
                if not nonempty_text(quote):
                    atom_errors.append(error("quote_empty", "evidence quote must be non-empty text"))
                elif node is not None:
                    if normalized(quote) not in normalized(node["text"]):
                        atom_errors.append(error(
                            "quote_not_in_declared_node",
                            "NFKC/whitespace-normalized quote is not contained in the declared source node",
                        ))

            if nonempty_text(atom.get("text")):
                atom_numbers = numeric_tokens(atom["text"])
                atom_type = atom.get("type")
                if atom_type == "numeric" and not atom_numbers:
                    atom_errors.append(error("numeric_atom_empty", "numeric atom contains no numeric token"))
                if atom_numbers:
                    if isinstance(quote, str) and quote.strip():
                        quote_numbers = numeric_tokens(quote)
                        unsupported = [token for token in atom_numbers if token not in quote_numbers]
                    else:
                        unsupported = atom_numbers
                    if unsupported:
                        record = error(
                            "unsupported_numeric_atom",
                            "numeric tokens missing from exact evidence quote: " + ", ".join(unsupported),
                        )
                        if allow_unsupported_numeric:
                            atom_warnings.append(record)
                        else:
                            atom_errors.append(record)
            status = "orphan" if orphan else ("fail" if atom_errors else "pass")
            if orphan:
                orphan_atom_ids.append(atom_id)
            atom_verdict = {
                "atom_index": atom_index,
                "atom_id": atom_id,
                "status": status,
                "answer_element_ids": mappings,
                "declared_node_id": atom_evidence.get("node_id") if isinstance(atom_evidence, dict) else None,
                "source_file": node.get("source_file") if node else None,
                "source_path": node.get("path") if node else None,
                "locator": node.get("locator") if node else None,
                "page": node.get("page") if node else None,
                "errors": atom_errors,
                "warnings": atom_warnings,
            }
            atom_verdicts.append(atom_verdict)

        element_verdicts = []
        for element in elements:
            covered_by = coverage[element["id"]]
            if not covered_by:
                errors.append(error("uncovered_answer_element", "no atom covers answer element " + element["id"]))
            element_verdicts.append({"id": element["id"], "covered_by": covered_by})
        if any(atom["status"] != "pass" for atom in atom_verdicts):
            errors.append(error("atom_failure", "one or more atoms failed or are orphaned"))
        item_verdicts.append({
            "item_index": item_index,
            "item_id": item_id,
            "status": "fail" if errors else "pass",
            "errors": errors,
            "answer_elements": element_verdicts,
            "atoms": atom_verdicts,
        })

    failed_items = [item["item_id"] for item in item_verdicts if item["status"] != "pass"]
    ok = not global_errors and not failed_items and len(bank) == EXPECTED_ITEMS
    return {
        "schema_version": VERDICT_SCHEMA_VERSION,
        "ok": ok,
        "policy": {
            "expected_items": EXPECTED_ITEMS,
            "normalization": "NFKC then Unicode whitespace collapse",
            "numeric_policy": "warning_only" if allow_unsupported_numeric else "fail_unsupported",
            "semantic_status": "agent_adjudication_required_not_independently_validated",
            "semantic_warning": "Exact normalized substring containment does not prove scientific or semantic support.",
        },
        "summary": {
            "item_count": len(bank),
            "passed_items": len(bank) - len(failed_items),
            "failed_items": failed_items,
            "atom_count": atom_total,
            "zero_atom_items": zero_atom_items,
            "orphan_atom_ids": orphan_atom_ids,
        },
        "errors": global_errors,
        "items": item_verdicts,
    }


def main():
    parser = argparse.ArgumentParser(description="Fail closed on four-item draft structure, atom coverage, quotes, and numbers.")
    parser.add_argument("--draft", required=True)
    parser.add_argument("--source-map", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument(
        "--allow-unsupported-numeric",
        action="store_true",
        help="demote numeric mismatch to a visible warning; off by default and never a semantic validation",
    )
    args = parser.parse_args()
    try:
        source_map, source_map_raw = load_json(args.source_map, "source map")
        node_by_id, rechecked = validate_source_map(source_map)
        draft, draft_raw = load_json(args.draft, "draft")
        if not isinstance(draft, dict):
            raise GateInputError("draft top level must be an object")
        verdict = verdict_for_draft(draft, node_by_id, args.allow_unsupported_numeric)
        verdict["source_map_sha256"] = sha256_bytes(source_map_raw)
        verdict["draft_sha256"] = sha256_bytes(draft_raw)
        verdict["sources_rechecked"] = rechecked
        atomic_json(args.output, verdict)
    except (GateInputError, OSError) as exc:
        print("EVIDENCE_GATE_INPUT_ERROR: " + str(exc), file=sys.stderr)
        return 2
    count = verdict["summary"]
    print("EVIDENCE_GATE_%s items=%d/%d atoms=%d orphans=%d output=%s" % (
        "OK" if verdict["ok"] else "FAIL",
        count["passed_items"], count["item_count"], count["atom_count"],
        len(count["orphan_atom_ids"]), args.output,
    ))
    return 0 if verdict["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
