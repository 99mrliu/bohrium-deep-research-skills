#!/usr/bin/env python3
"""Initialize, build, or check results from semantic ledger-ID selections."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

from numeric_ledger import LedgerError, harvest_sources, read_ledger

RESULT_SCHEMA = "numeric-provenance-result/v1"
SELECTION_SCHEMA = "numeric-selection/v1"
FIELD_STATUSES = {"reported", "not_reported", "source_conflict", "extraction_failed"}
OVERALL_STATUSES = {"answered", "partial", "insufficient_evidence", "input_error"}


class ResultError(ValueError):
    """A selection, contract, or provenance invariant was violated."""


def load_json(path: Path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ResultError(f"cannot read JSON {path}: {exc}") from exc


def canonical_hash(value):
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def load_case(path: Path):
    case = load_json(path)
    if not isinstance(case, dict) or not isinstance(case.get("case_id"), str) or not case["case_id"]:
        raise ResultError("case.json must contain a non-empty string case_id")
    return case


def load_targets(path: Path):
    document = load_json(path)
    if isinstance(document, list):
        fields = document
    elif isinstance(document, dict):
        fields = document.get("fields", document.get("target_fields"))
    else:
        fields = None
    if not isinstance(fields, list) or not fields:
        raise ResultError("target-fields.json must be a non-empty list or contain fields/target_fields")
    output = []
    seen = set()
    for item in fields:
        if isinstance(item, str):
            field_id = item
            target = {"field_id": item}
        elif isinstance(item, dict):
            field_id = item.get("field_id", item.get("id"))
            target = dict(item)
            target["field_id"] = field_id
        else:
            raise ResultError("every target field must be an object or field_id string")
        if not isinstance(field_id, str) or not field_id or field_id in seen:
            raise ResultError(f"missing or duplicate target field_id: {field_id!r}")
        seen.add(field_id)
        output.append(target)
    return output


def empty_ledger_ids():
    return {"value": [], "condition": [], "statistic": [], "reference": []}


def base_field(status="extraction_failed"):
    return {
        "field_id": None,
        "status": status,
        "scalar": None,
        "units": None,
        "statistic": None,
        "experimental_condition": None,
        "condition": None,
        "comparator": None,
        "paragraph_id": None,
        "quote": None,
        "evidence": [],
        "notes": "",
        "ledger_ids": empty_ledger_ids(),
    }


def source_indexes(document):
    sources = document.get("sources") if isinstance(document, dict) else document
    if not isinstance(sources, list):
        raise ResultError("invalid sources document")
    paragraphs = {}
    metadata = []
    for source in sources:
        source_id = source.get("source_id")
        for paragraph in source.get("paragraphs", []):
            key = (source_id, paragraph.get("paragraph_id"))
            if key in paragraphs:
                raise ResultError(f"duplicate source paragraph: {key}")
            paragraphs[key] = {
                "text": paragraph["text"],
                "page": paragraph.get("page", source.get("page")),
            }
        metadata.append({
            key: source[key]
            for key in ("source_id", "title", "doi", "url")
            if key in source
        })
    return paragraphs, metadata


def prepare_tokens(document, ledger_path):
    expected = harvest_sources(document)
    expected_by_id = {record["token_id"]: record for record in expected}
    existing = read_ledger(ledger_path)
    existing_by_id = {record["token_id"]: record for record in existing}
    for record in expected:
        saved = existing_by_id.get(record["token_id"])
        if saved != record:
            raise ResultError(
                f"ledger does not exactly match current sources at {record['token_id']}; harvest or investigate first"
            )
    paragraphs, metadata = source_indexes(document)
    for record in expected:
        item = paragraphs.get((record["source_id"], record["paragraph_id"]))
        if item is None:
            raise ResultError(f"missing selected source paragraph for {record['token_id']}")
    return expected_by_id, paragraphs, metadata


def selection_fields(selection, targets):
    if not isinstance(selection, dict) or selection.get("schema_version") != SELECTION_SCHEMA:
        raise ResultError(f"selection schema_version must be {SELECTION_SCHEMA}")
    fields = selection.get("fields")
    if not isinstance(fields, dict):
        raise ResultError("selection.fields must be an object keyed by field_id")
    expected_ids = [target["field_id"] for target in targets]
    missing = [field_id for field_id in expected_ids if field_id not in fields]
    extra = [field_id for field_id in fields if field_id not in set(expected_ids)]
    if missing or extra:
        raise ResultError(f"selection field coverage mismatch; missing={missing}, extra={extra}")
    return [fields[field_id] for field_id in expected_ids]


def condition_from_ids(ids, token_by_id, paragraphs, value_token=None):
    if not ids:
        return None
    tokens = [token_by_id[token_id] for token_id in ids]
    first = tokens[0]
    scope = (first["source_id"], first["paragraph_id"], first["statement_id"])
    for token in tokens[1:]:
        if (token["source_id"], token["paragraph_id"], token["statement_id"]) != scope:
            raise ResultError("condition tokens must share the value's statement; do not bind across conditions")
    if value_token is not None and (
        value_token["source_id"], value_token["paragraph_id"], value_token["statement_id"]
    ) != scope:
        raise ResultError(
            f"wrong condition binding: value {value_token['token_id']} and condition tokens are in different statements"
        )
    start = min(token["start"] for token in tokens)
    end = max(token["end"] for token in tokens)
    return paragraphs[(first["source_id"], first["paragraph_id"])]["text"][start:end]


def grouped_evidence(token_ids, token_by_id):
    groups = {}
    order = []
    for token_id in token_ids:
        token = token_by_id[token_id]
        statement_id = token["statement_id"]
        if statement_id not in groups:
            groups[statement_id] = []
            order.append(statement_id)
        groups[statement_id].append(token)
    evidence = []
    for statement_id in order:
        tokens = sorted(groups[statement_id], key=lambda item: (item["start"], item["token_id"]))
        first = tokens[0]
        evidence.append({
            "source_id": first["source_id"],
            "page": first["page"],
            "paragraph_id": first["paragraph_id"],
            "quote": first["statement_quote"],
            "statement_id": statement_id,
            "token_ids": [token["token_id"] for token in tokens],
            "spans": [{"token_id": t["token_id"], "start": t["start"], "end": t["end"]} for t in tokens],
        })
    return evidence


def coverage_evidence(coverage, paragraphs):
    if not isinstance(coverage, list):
        raise ResultError("coverage must be a list")
    evidence = []
    for item in coverage:
        if not isinstance(item, dict):
            raise ResultError("coverage entries must be objects")
        source_id = item.get("source_id")
        paragraph_id = item.get("paragraph_id")
        quote = item.get("quote")
        key = (source_id, paragraph_id)
        if key not in paragraphs or not isinstance(quote, str) or not quote:
            raise ResultError("coverage entry needs a known source_id/paragraph_id and non-empty exact quote")
        text = paragraphs[key]["text"]
        start = item.get("start")
        end = item.get("end")
        if start is None and end is None:
            start = text.find(quote)
            if start < 0 or text.find(quote, start + 1) >= 0:
                raise ResultError("coverage quote must occur exactly once or supply exact start/end")
            end = start + len(quote)
        if (
            not isinstance(start, int) or not isinstance(end, int)
            or not (0 <= start < end <= len(text)) or text[start:end] != quote
        ):
            raise ResultError("coverage quote/span does not exactly match source text")
        evidence.append({
            "source_id": source_id,
            "page": paragraphs[key]["page"],
            "paragraph_id": paragraph_id,
            "quote": quote,
            "statement_id": None,
            "token_ids": [],
            "spans": [{"start": start, "end": end}],
        })
    return evidence


def statistic_value(value_token, statistic_tokens):
    values = []
    if value_token["statistic"] is not None:
        values.append(value_token["statistic"])
    for token in statistic_tokens:
        values.append(token["statistic"] if token["statistic"] is not None else token["raw"])
    if not values:
        return None
    if len(values) == 1:
        return values[0]
    return values


def build_reported(field_id, rule, token_by_id, paragraphs):
    value_ids = rule.get("value_token_ids", [])
    condition_ids = rule.get("condition_token_ids", [])
    statistic_ids = rule.get("statistic_token_ids", [])
    reference_ids = rule.get("reference_token_ids", [])
    for name, ids in (
        ("value_token_ids", value_ids), ("condition_token_ids", condition_ids),
        ("statistic_token_ids", statistic_ids), ("reference_token_ids", reference_ids),
    ):
        if not isinstance(ids, list) or any(token_id not in token_by_id for token_id in ids):
            raise ResultError(f"{field_id}: {name} contains an unknown token ID or is not a list")
        if len(set(ids)) != len(ids):
            raise ResultError(f"{field_id}: duplicate IDs in {name}")
    if len(value_ids) != 1:
        raise ResultError(f"{field_id}: reported requires exactly one value_token_id")
    value = token_by_id[value_ids[0]]
    if value["scalar"] is None or value["kind"] in {"table_reference", "figure_reference"}:
        raise ResultError(f"{field_id}: selected value is a reference, not a scalar-bearing numeric expression")
    statistics = [token_by_id[token_id] for token_id in statistic_ids]
    for token in statistics:
        if token["kind"] not in {"p_statistic", "n_statistic", "confidence_interval"}:
            raise ResultError(f"{field_id}: statistic token {token['token_id']} is not a p/n/CI statistic expression")
    references = [token_by_id[token_id] for token_id in reference_ids]
    if any(token["kind"] not in {"table_reference", "figure_reference"} for token in references):
        raise ResultError(f"{field_id}: reference_token_ids must select table/figure references")
    condition = condition_from_ids(condition_ids, token_by_id, paragraphs, value)
    comparators = [token["comparator"] for token in [value, *statistics] if token["comparator"] is not None]
    distinct_comparators = list(dict.fromkeys(comparators))
    if len(distinct_comparators) > 1:
        raise ResultError(f"{field_id}: conflicting comparators require source_conflict or separate fields")
    field = base_field("reported")
    field.update({
        "field_id": field_id,
        "scalar": value["scalar"],
        "units": value["units"],
        "statistic": statistic_value(value, statistics),
        "experimental_condition": condition,
        "condition": condition,
        "comparator": distinct_comparators[0] if distinct_comparators else None,
        "paragraph_id": value["paragraph_id"],
        "quote": value["statement_quote"],
        "evidence": grouped_evidence(
            value_ids + condition_ids + statistic_ids + reference_ids, token_by_id
        ),
        "notes": rule.get("notes", ""),
        "ledger_ids": {
            "value": value_ids,
            "condition": condition_ids,
            "statistic": statistic_ids,
            "reference": reference_ids,
        },
    })
    if not isinstance(field["notes"], str):
        raise ResultError(f"{field_id}: notes must be a string")
    return field


def build_conflict(field_id, rule, token_by_id, paragraphs):
    variants = rule.get("variants")
    if not isinstance(variants, list) or len(variants) < 2:
        raise ResultError(f"{field_id}: source_conflict requires at least two variants")
    built = [
        build_reported(f"{field_id}.variant[{index}]", variant, token_by_id, paragraphs)
        for index, variant in enumerate(variants)
    ]
    conditions = [variant["experimental_condition"] for variant in built]
    if any(condition != conditions[0] for condition in conditions[1:]):
        raise ResultError(f"{field_id}: conflict variants are not bound to the identical lexical condition")
    representations = {
        json.dumps([v["scalar"], v["units"], v["statistic"], v["comparator"]], ensure_ascii=False)
        for v in built
    }
    if len(representations) < 2:
        raise ResultError(f"{field_id}: variants are lexically identical, not a source conflict")
    field = base_field("source_conflict")
    evidence = []
    seen_evidence = set()
    for variant in built:
        for item in variant["evidence"]:
            fingerprint = canonical_hash(item)
            if fingerprint not in seen_evidence:
                evidence.append(item)
                seen_evidence.add(fingerprint)
    notes = rule.get("notes", "")
    if not isinstance(notes, str) or not notes.strip():
        raise ResultError(f"{field_id}: source_conflict notes must explain the unresolved alternatives")
    field.update({
        "field_id": field_id,
        "experimental_condition": conditions[0],
        "condition": conditions[0],
        "evidence": evidence,
        "notes": notes,
        "ledger_ids": {
            category: [token_id for variant in built for token_id in variant["ledger_ids"][category]]
            for category in empty_ledger_ids()
        },
        "conflicts": built,
    })
    return field


def build_unresolved(field_id, rule, paragraphs):
    status = rule["status"]
    token_keys = ("value_token_ids", "condition_token_ids", "statistic_token_ids", "reference_token_ids")
    if any(rule.get(key) for key in token_keys) or rule.get("variants"):
        raise ResultError(f"{field_id}: {status} cannot silently carry reported-value selections")
    coverage = rule.get("coverage", [])
    if status == "not_reported" and not coverage:
        raise ResultError(f"{field_id}: not_reported requires exact searched-scope coverage evidence")
    evidence = coverage_evidence(coverage, paragraphs)
    notes = rule.get("notes", "")
    if not isinstance(notes, str) or not notes.strip():
        raise ResultError(f"{field_id}: {status} notes are mandatory")
    field = base_field(status)
    field["field_id"] = field_id
    field["notes"] = notes
    field["evidence"] = evidence
    if evidence:
        field["paragraph_id"] = evidence[0]["paragraph_id"]
        field["quote"] = evidence[0]["quote"]
    if status == "extraction_failed":
        failure_kind = rule.get("failure_kind")
        if not isinstance(failure_kind, str) or not failure_kind.strip():
            raise ResultError(f"{field_id}: extraction_failed needs an explicit failure_kind")
        field["failure_kind"] = failure_kind
    return field


def uncertainty_for(field):
    if field["status"] == "reported":
        return None
    item = {
        "field_id": field["field_id"],
        "type": field["status"],
        "notes": field["notes"],
        "evidence": field["evidence"],
    }
    if field["status"] == "source_conflict":
        item["alternatives"] = [
            {
                "scalar": v["scalar"], "units": v["units"], "statistic": v["statistic"],
                "experimental_condition": v["experimental_condition"], "quote": v["quote"],
                "evidence": v["evidence"],
            }
            for v in field["conflicts"]
        ]
        item["notes"] += " No value was averaged, converted, or automatically preferred."
    elif field["status"] == "not_reported":
        item["notes"] += " Absence is a semantic reading of the stated coverage, not a zero and not unreadability."
    else:
        item["failure_kind"] = field["failure_kind"]
    return item


def overall_status(fields):
    if not fields:
        return "input_error"
    if any(field["status"] == "extraction_failed" for field in fields):
        return "partial" if any(field["status"] == "reported" for field in fields) else "insufficient_evidence"
    if all(field["status"] == "not_reported" for field in fields):
        return "insufficient_evidence"
    # A scoped non-report or an explicitly preserved conflict is a completed
    # adjudication, not an unfinished extraction.
    return "answered"


def validate_contract(result, targets):
    required_top = {"case_id", "status", "result", "claims", "uncertainties"}
    if not required_top.issubset(result) or result["status"] not in OVERALL_STATUSES:
        raise ResultError("result lacks required top-level keys or has invalid overall status")
    fields = result["result"].get("fields")
    if not isinstance(fields, list):
        raise ResultError("result.fields must be a list")
    expected_ids = [target["field_id"] for target in targets]
    actual_ids = [field.get("field_id") for field in fields]
    if len(actual_ids) != len(set(actual_ids)) or set(actual_ids) != set(expected_ids) or len(fields) != len(targets):
        raise ResultError("result.fields must contain exactly one record per requested field_id")
    if "field_results" in result["result"] and result["result"]["field_results"] != fields:
        raise ResultError("mirrored result.field_results differs from result.fields")
    pending_partial = (
        result["status"] == "partial" and fields
        and all(field.get("status") == "extraction_failed" and field.get("failure_kind") == "pending_read" for field in fields)
    )
    if result["status"] != overall_status(fields) and not pending_partial:
        raise ResultError("overall status does not match field statuses")
    required = set(base_field())
    for field in fields:
        if not required.issubset(field) or field["status"] not in FIELD_STATUSES:
            raise ResultError(f"invalid or incomplete field record: {field.get('field_id')}")
        if field["condition"] != field["experimental_condition"]:
            raise ResultError(f"condition alias mismatch: {field['field_id']}")
        for evidence in field["evidence"]:
            if not {"source_id", "page", "paragraph_id", "quote"}.issubset(evidence):
                raise ResultError(f"incomplete evidence: {field['field_id']}")


def build_result(case, targets, selection, token_by_id, paragraphs, metadata, ledger_path):
    fields = []
    for target, rule in zip(targets, selection_fields(selection, targets)):
        field_id = target["field_id"]
        if not isinstance(rule, dict) or rule.get("status") not in FIELD_STATUSES:
            raise ResultError(f"{field_id}: invalid or missing field status")
        if rule["status"] == "reported":
            field = build_reported(field_id, rule, token_by_id, paragraphs)
        elif rule["status"] == "source_conflict":
            field = build_conflict(field_id, rule, token_by_id, paragraphs)
        else:
            field = build_unresolved(field_id, rule, paragraphs)
        fields.append(field)
    claims = []
    for field in fields:
        if field["status"] not in {"reported", "source_conflict"}:
            continue
        first = field["evidence"][0] if field["evidence"] else None
        claims.append({
            "kind": "numeric_field" if field["status"] == "reported" else "source_conflict",
            "field_id": field["field_id"],
            "quote": field["quote"],
            "source_id": first["source_id"] if first else None,
            "location": {
                "page": first["page"] if first else None,
                "paragraph_id": first["paragraph_id"] if first else None,
            },
            "evidence": field["evidence"],
        })
    result = {
        "case_id": case["case_id"],
        "status": overall_status(fields),
        "result": {
            "schema_version": RESULT_SCHEMA,
            "fields": fields,
            "selection_sha256": canonical_hash(selection),
        },
        "claims": claims,
        "uncertainties": [item for field in fields if (item := uncertainty_for(field)) is not None],
        "sources": metadata,
        "change_records": [{
            "action": "built_only_from_semantic_ledger_id_selection",
            "selection_sha256": canonical_hash(selection),
            "ledger_sha256": hashlib.sha256(ledger_path.read_bytes()).hexdigest(),
            "numeric_conversion": False,
            "similarity_ranking": False,
        }],
    }
    validate_contract(result, targets)
    return result


def write_audit(path: Path, result, targets):
    status_counts = {status: 0 for status in sorted(FIELD_STATUSES)}
    for field in result["result"]["fields"]:
        status_counts[field["status"]] += 1
    lines = [
        "# Numeric provenance audit",
        "",
        f"Case: `{result['case_id']}`  ",
        f"Overall status: **{result['status']}**  ",
        f"Field statuses: `{json.dumps(status_counts, sort_keys=True)}`",
        "",
        "Every reported representation below is copied from selected ledger tokens. Statement-level condition binding is checked mechanically; semantic target matching and absence decisions remain Agent responsibilities.",
        "",
        "| Field | Status | Verbatim scalar | Verbatim units | Verbatim statistic | Condition | Comparator | Ledger IDs |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for field in result["result"]["fields"]:
        ids = field["ledger_ids"]
        id_text = ", ".join(token_id for values in ids.values() for token_id in values) or "—"
        cells = [
            field["field_id"], field["status"], field["scalar"], field["units"],
            field["statistic"], field["experimental_condition"], field["comparator"], id_text,
        ]
        rendered = []
        for cell in cells:
            text = "—" if cell is None else json.dumps(cell, ensure_ascii=False) if isinstance(cell, (list, dict)) else str(cell)
            rendered.append(text.replace("|", "\\|").replace("\n", "\\n"))
        lines.append("| " + " | ".join(rendered) + " |")
    lines.extend(["", "## Evidence and unresolved readings", ""])
    for field in result["result"]["fields"]:
        lines.append(f"### {field['field_id']} — {field['status']}")
        lines.append("")
        lines.append(f"Notes: {field['notes'] or '—'}")
        if field["quote"] is not None:
            lines.append(f"Primary quote ({field['paragraph_id']}): {field['quote']}")
        for index, evidence in enumerate(field["evidence"], 1):
            lines.append(
                f"- Evidence {index}: source={evidence['source_id']}; page={evidence['page']}; "
                f"paragraph={evidence['paragraph_id']}; tokens={evidence['token_ids']}"
            )
            lines.append(f"  > {evidence['quote']}")
            lines.append(f"  Exact spans: `{json.dumps(evidence['spans'], ensure_ascii=False)}`")
        for index, variant in enumerate(field.get("conflicts", []), 1):
            lines.append(
                f"- Conflict variant {index}: scalar={variant['scalar']!r}; units={variant['units']!r}; "
                f"condition={variant['experimental_condition']!r}; quote={variant['quote']}"
            )
        lines.append("")
    lines.extend([
        "## Mechanical boundary",
        "",
        "`not_reported` is not inferred by a script from a failed regex match; its coverage quote scopes a human/Agent absence decision. `extraction_failed` names an unreadable or failed operation. `source_conflict` preserves all selected variants without choosing by similarity.",
        "",
        f"Requested field count: {len(targets)}. Emitted field count: {len(result['result']['fields'])}.",
    ])
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def initialize(case_path, target_path, output_path):
    try:
        case = load_case(case_path)
        targets = load_targets(target_path)
        fields = []
        uncertainties = []
        for target in targets:
            field = base_field("extraction_failed")
            field.update({
                "field_id": target["field_id"],
                "notes": "Not yet processed; early honest partial placeholder awaiting source reading and ledger selection.",
                "failure_kind": "pending_read",
            })
            fields.append(field)
            uncertainties.append({
                "field_id": target["field_id"], "type": "pending_read",
                "failure_kind": "pending_read", "notes": field["notes"], "evidence": [],
            })
        result = {
            "case_id": case["case_id"],
            "status": "partial",
            "result": {"schema_version": RESULT_SCHEMA, "fields": fields},
            "claims": [],
            "uncertainties": uncertainties,
            "sources": [],
            "change_records": [{"action": "early_partial_initialized_before_extraction"}],
        }
        validate_contract(result, targets)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(json.dumps({"status": "partial", "fields_initialized": len(fields), "output": str(output_path)}))
        return 0
    except ResultError as exc:
        fallback = {
            "case_id": None, "status": "input_error", "result": {"fields": []}, "claims": [],
            "uncertainties": [{"type": "input_error", "notes": str(exc)}],
        }
        try:
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_text(json.dumps(fallback, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        except OSError:
            pass
        print(f"numeric_result init error: {exc}", file=sys.stderr)
        return 2


def run_build(args, check_only=False):
    case = load_case(args.case)
    targets = load_targets(args.targets)
    sources = load_json(args.sources)
    selection = load_json(args.selection)
    token_by_id, paragraphs, metadata = prepare_tokens(sources, args.ledger)
    expected = build_result(
        case, targets, selection, token_by_id, paragraphs, metadata, args.ledger
    )
    if args.audit:
        write_audit(args.audit, expected, targets)
    if check_only:
        actual = load_json(args.output)
        validate_contract(actual, targets)
        if actual != expected:
            # Pinpoint scalar/unit/condition edits rather than returning only a diff opcode.
            actual_by_id = {item.get("field_id"): item for item in actual["result"]["fields"]}
            for wanted in expected["result"]["fields"]:
                got = actual_by_id.get(wanted["field_id"], {})
                for key in ("status", "scalar", "units", "statistic", "experimental_condition", "condition", "comparator", "quote", "evidence", "ledger_ids"):
                    if got.get(key) != wanted[key]:
                        raise ResultError(
                            f"verification rejected {wanted['field_id']}.{key}: altered or not losslessly ledger-grounded"
                        )
            raise ResultError("verification rejected result: full JSON differs from selected ledger construction")
        print(json.dumps({"status": "verified", "fields": len(expected["result"]["fields"])}))
    else:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(expected, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(json.dumps({"status": expected["status"], "fields": len(expected["result"]["fields"]), "output": str(args.output)}))
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    init_parser = subparsers.add_parser("init", help="Write an early honest partial result")
    init_parser.add_argument("--case", required=True, type=Path)
    init_parser.add_argument("--targets", required=True, type=Path)
    init_parser.add_argument("--output", required=True, type=Path)
    for command in ("build", "check"):
        child = subparsers.add_parser(command, help="Build result.json" if command == "build" else "Reject any altered result")
        child.add_argument("--case", required=True, type=Path)
        child.add_argument("--targets", required=True, type=Path)
        child.add_argument("--sources", required=True, type=Path)
        child.add_argument("--ledger", required=True, type=Path)
        child.add_argument("--selection", required=True, type=Path)
        child.add_argument("--output", required=True, type=Path)
        child.add_argument("--audit", type=Path)
    args = parser.parse_args(argv)
    if args.command == "init":
        return initialize(args.case, args.targets, args.output)
    try:
        return run_build(args, check_only=args.command == "check")
    except (OSError, UnicodeError, json.JSONDecodeError, LedgerError, ResultError, KeyError, TypeError) as exc:
        print(f"numeric_result {args.command} error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
