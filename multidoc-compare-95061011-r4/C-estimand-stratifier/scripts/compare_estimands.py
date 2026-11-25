#!/usr/bin/env python3
"""Run the deterministic half of estimand-specific multi-document comparison.

Runtime: python scripts/compare_estimands.py --input /input --work /app/work --output /app/output
The agent writes /app/work/estimands.json after reading task.md and every corpus document.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Mapping, Sequence

from estimand_core import (
    DIMENSIONS, NOT_REPORTED, OperationBlocked, SchemaError, evaluate_all,
    ensure_operations_allowed, fingerprint, load_all_corpus_documents, load_json,
    preflight_rows, stratum_key, unknown_paths, validate_operation_requests, validate_records,
)
from result_contract import render_result

RECOGNIZED_CONTRACT_TOKENS = {
    "caseid", "comparisonmatrix", "matrix", "comparisonoperations", "operations", "status",
    "sources", "source", "uncertainty", "uncertainties", "changerecords", "changelog",
    "operationresults", "operationsresults", "strata", "stratumregister", "estimandregister",
    "estimands",
}


def compact(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def cell(value: Any) -> str:
    if isinstance(value, (dict, list)):
        text = compact(value)
    else:
        text = str(value)
    return text.replace("|", "\\|").replace("\n", "<br>")


def table(headers: Sequence[str], rows: Sequence[Sequence[Any]]) -> List[str]:
    lines = ["| " + " | ".join(headers) + " |", "| " + " | ".join("---" for _ in headers) + " |"]
    lines.extend("| " + " | ".join(cell(item) for item in row) + " |" for row in rows)
    return lines


def build_strata(indexed: Mapping[str, Any]) -> Dict[str, Any]:
    grouped: Dict[str, Any] = {}
    for estimand_id, record in indexed.items():
        key = stratum_key(record)
        digest = fingerprint(key)
        if digest not in grouped:
            grouped[digest] = {"canonical_key": key, "estimand_ids": []}
        grouped[digest]["estimand_ids"].append(estimand_id)
    return grouped


def build_sources(documents: Mapping[str, Any], indexed: Mapping[str, Any]) -> List[Dict[str, Any]]:
    by_source: Dict[str, List[str]] = {source_id: [] for source_id in documents}
    for estimand_id, record in indexed.items():
        by_source[record["source_document_id"]].append(estimand_id)
    sources = []
    for source_id, document in documents.items():
        sources.append({
            "source_document_id": source_id,
            "path": document["path"],
            "text_sha256": document["text_sha256"],
            "paragraph_ids": list(document["paragraphs"]),
            "estimand_ids": sorted(by_source[source_id]),
            "coverage": "read_in_full",
        })
    return sources


def render_matrix(case_id: str, task_id: str, documents: Mapping[str, Any], indexed: Mapping[str, Any],
                  strata: Mapping[str, Any]) -> str:
    lines = [
        "# Comparison matrix", "", f"Case: `{case_id}`", f"Task: `{task_id}`", "",
        "Descriptive comparison is retained even when estimands differ or cells are `not_reported`. "
        "Nothing in this matrix is a pooled estimate.", "",
        "## Required preflight: task, metric, units, material, pollutant, budget", "",
    ]
    rows = []
    for row in preflight_rows(indexed, task_id):
        rows.append([row[key] for key in ("estimand_id", "task", "metric", "unit", "material", "pollutant", "budget")])
    lines.extend(table(["estimand_id", "task", "metric", "unit", "material", "pollutant", "budget"], rows))
    lines.extend(["", "`not_reported` is preserved and blocks quantitative gates; it does not erase this descriptive matrix.", "",
                  "## Corpus coverage (every document)", ""])
    coverage_rows = []
    for source_id, document in documents.items():
        estimand_ids = [item for item, record in indexed.items() if record["source_document_id"] == source_id]
        coverage_rows.append([source_id, document["path"], ", ".join(document["paragraphs"]),
                              ", ".join(estimand_ids) if estimand_ids else NOT_REPORTED, "read_in_full"])
    lines.extend(table(["source_document_id", "path", "paragraph_ids read", "estimand_ids", "coverage"], coverage_rows))
    lines.extend(["", "## Evidence-backed normalized estimands", ""])
    headers = ["estimand_id", "source_document_id", "outcome", "metric", "population", "material", "pollutant",
               "intervention", "condition", "budget", "time/horizon", "unit/scale", "estimate", "stratum"]
    rows = []
    for estimand_id, record in indexed.items():
        rows.append([
            estimand_id, record["source_document_id"], record["outcome"],
            {"name": record["metric"]["name"], "definition": record["metric"]["definition"]},
            record["population"], record["material"], record["pollutant"], record["intervention"], record["condition"],
            record["budget"], record["time"], {"unit": record["unit"], "scale": record["scale"]},
            record["estimate"], fingerprint(stratum_key(record))[:16],
        ])
    lines.extend(table(headers, rows))
    lines.extend(["", "## Exact source evidence", "",
                  "Each quote below is an exact substring of the cited source paragraph; no ellipsis or numeric rewriting is added.", ""])
    for estimand_id, record in indexed.items():
        lines.extend([f"### {estimand_id}", ""])
        for evidence in record["evidence"]:
            lines.extend([
                f"Source: `{evidence['source_document_id']}`; paragraph: `{evidence['paragraph_id']}`", "",
                "> " + evidence["quote"], "",
            ])
    lines.extend(["## Raw stratum register", ""])
    stratum_rows = []
    for digest, item in strata.items():
        stratum_rows.append([digest, ", ".join(item["estimand_ids"]), item["canonical_key"]])
    lines.extend(table(["sha256(stratum_key)", "estimand_ids", "canonical_key"], stratum_rows))
    lines.append("")
    return "\n".join(lines)


def render_operations(case_id: str, status: str, requests: Sequence[Mapping[str, Any]],
                      results: Sequence[Mapping[str, Any]]) -> str:
    lines = [
        "# Comparison operations", "", f"Case: `{case_id}`", f"Completion status: **{status}**", "",
        "Status reflects work completion, not whether every requested operation is allowed. "
        "A completed comparison can be `success` with blocked RANK/POOL operations. "
        "This script never performs meta-analysis or invents heterogeneity statistics.", "",
    ]
    by_id = {request["operation_id"]: request for request in requests}
    for result in results:
        operation_id = result["operation_id"]
        request = by_id[operation_id]
        lines.extend([
            f"## {operation_id}: {result['operation']}", "",
            f"Decision: **{'ALLOWED' if result['allowed'] else 'BLOCKED'}**", "",
            f"Estimands: {', '.join('`' + item + '`' for item in result['estimand_ids'])}", "",
            f"Raw estimand comparability: **{result['comparability']}**", "",
            f"Rationale: {result['rationale']}", "",
        ])
        if result["blocking_reasons"]:
            lines.append("Blocking reasons:")
            lines.extend(f"- `{reason}`" for reason in result["blocking_reasons"])
            lines.append("")
        else:
            lines.extend(["Blocking reasons: none.", ""])
        if result["caveats"]:
            lines.append("Caveats:")
            lines.extend(f"- {caveat}" for caveat in result["caveats"])
            lines.append("")
        if result["mismatches_after_requested_transforms"]:
            lines.extend(["Mismatching estimand dimensions after requested transforms: "
                          + ", ".join(result["mismatches_after_requested_transforms"]), ""])
        if result["operation"] == "DIRECTION":
            lines.append("Qualitative directions only (not effect-size ranks):")
            lines.append("")
            lines.extend(f"- `{item['estimand_id']}`: **{item['direction']}**" for item in result["directions"])
            lines.append("")
            caveats = request.get("caveats", [])
            if caveats:
                lines.extend(f"- Explicit request caveat: {item}" for item in caveats)
                lines.append("")
        if result["transform_audit"]:
            lines.extend(["Exact transform audit (in-memory copies; source records and quotes are unchanged):", ""])
            transform_rows = []
            for item in result["transform_audit"]:
                transform_rows.append([item["estimand_id"], item["field"], item["conversion"], item["definition"],
                                       item["before"], item["after"], item["reason"]])
            lines.extend(table(["estimand_id", "field", "conversion", "exact definition", "before", "after", "reason"], transform_rows))
            lines.append("")
        if result["operation"] == "POOL":
            lines.extend(["Numeric synthesis: **not_performed**. Even an allowed POOL gate would require a separately specified analysis.", ""])
    lines.extend(["## Minimal operation semantics", "",
                  "- **DESCRIBE**: side-by-side unlike measures and not-reported cells remain visible.",
                  "- **DIRECTION**: qualitative directions only, with explicit caveats; no ranking by effect size.",
                  "- **RANK**: one known estimand and one compatible scale after approved exact transforms.",
                  "- **TRANSFORM**: only exact, whitelisted, requested conversions with before/after audit.",
                  "- **POOL**: additionally requires explicit strong exchangeability; no automatic pooled estimate.",
                  ""])
    return "\n".join(lines)


def _contract_token(name: str) -> str:
    return re.sub(r"[^a-z0-9]", "", name.lower())


def build_uncertainty(indexed: Mapping[str, Any], results: Sequence[Mapping[str, Any]],
                      unmapped_fields: Sequence[str], incomplete: Sequence[str]) -> List[Dict[str, Any]]:
    uncertainty: List[Dict[str, Any]] = []
    for estimand_id, record in indexed.items():
        for dimension in DIMENSIONS:
            for path in unknown_paths(record[dimension], dimension):
                uncertainty.append({"code": "NOT_REPORTED", "estimand_id": estimand_id,
                                    "field": path, "value": NOT_REPORTED})
        for path in unknown_paths(record["estimate"], "estimate"):
            uncertainty.append({"code": "NOT_REPORTED", "estimand_id": estimand_id,
                                "field": path, "value": NOT_REPORTED})
    for result in results:
        if not result["allowed"]:
            uncertainty.append({"code": "OPERATION_BLOCKED", "operation_id": result["operation_id"],
                                "operation": result["operation"], "reasons": result["blocking_reasons"],
                                "impact": "No result is produced for this operation; its gate evaluation and the overall comparison are complete."})
    for field in unmapped_fields:
        uncertainty.append({"code": "UNMAPPED_CONTRACT_FIELD", "field": field,
                            "impact": "Preserved with an empty value of the contracted type; no content was invented."})
    for item in incomplete:
        uncertainty.append({"code": "INCOMPLETE_WORK", "field": item, "impact": "Completion status is partial."})
    return uncertainty


def run(input_root: Path, work: Path, output: Path, strict_operations: bool = False) -> Dict[str, Any]:
    case_path = input_root / "case.json"
    task_path = input_root / "task.md"
    workorder_path = input_root / "comparison-workorder.json"
    estimands_path = work / "estimands.json"
    case = load_json(case_path)
    workorder = load_json(workorder_path)
    estimand_envelope = load_json(estimands_path)
    try:
        task_text = task_path.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        raise SchemaError(f"Cannot read task.md: {exc}") from exc
    for label, value in (("case.json", case), ("comparison-workorder.json", workorder),
                         ("estimands.json", estimand_envelope)):
        if not isinstance(value, Mapping):
            raise SchemaError(f"{label} must contain a JSON object")
    case_id = case.get("case_id")
    if workorder.get("case_id") != case_id or estimand_envelope.get("case_id") != case_id:
        raise SchemaError("case_id must match exactly across case, workorder, and estimands")
    if workorder.get("task_id") != estimand_envelope.get("task_id"):
        raise SchemaError("task_id must match across workorder and estimands")
    task_id = workorder.get("task_id")
    documents = load_all_corpus_documents(input_root, case.get("corpus_documents"))
    indexed = validate_records(estimand_envelope.get("records"), documents, case_id, task_id, task_text)
    requests = validate_operation_requests(workorder.get("operation_requests"), indexed)
    # Quantitative operation gating happens only after all schema/source/preflight checks above.
    results = evaluate_all(requests, indexed)
    if strict_operations:
        ensure_operations_allowed(results)

    completion = workorder.get("completion")
    if not isinstance(completion, Mapping):
        raise SchemaError("workorder completion must be an object with three boolean flags")
    completion_flags = ("all_documents_reviewed", "all_requested_operations_evaluated",
                        "all_output_contract_fields_addressed")
    incomplete = []
    for flag in completion_flags:
        if not isinstance(completion.get(flag), bool):
            raise SchemaError(f"completion.{flag} must be boolean")
        if not completion[flag]:
            incomplete.append(flag)
    output_contract = case.get("output_contract")
    if not isinstance(output_contract, Mapping) or not output_contract:
        raise SchemaError("case.output_contract must be a nonempty object")
    unmapped_fields = [field for field in output_contract
                       if _contract_token(field) not in RECOGNIZED_CONTRACT_TOKENS]
    status = "success" if not incomplete and not unmapped_fields else "partial"

    strata = build_strata(indexed)
    sources = build_sources(documents, indexed)
    matrix = render_matrix(case_id, task_id, documents, indexed, strata)
    operations = render_operations(case_id, status, requests, results)
    output.mkdir(parents=True, exist_ok=True)
    matrix_path = output / "comparison-matrix.md"
    operations_path = output / "comparison-operations.md"
    result_path = output / "result.json"
    matrix_path.write_text(matrix, encoding="utf-8")
    operations_path.write_text(operations, encoding="utf-8")
    change_records = [
        {"sequence": 1, "path": matrix_path.name, "action": "rendered",
         "sha256": hashlib.sha256(matrix.encode("utf-8")).hexdigest()},
        {"sequence": 2, "path": operations_path.name, "action": "rendered",
         "sha256": hashlib.sha256(operations.encode("utf-8")).hexdigest()},
        {"sequence": 3, "path": result_path.name, "action": "rendered",
         "detail": "case_id and original output_contract keys rendered dynamically; source records were not edited"},
    ]
    for item in change_records[:2]:
        actual = hashlib.sha256((output / item["path"]).read_bytes()).hexdigest()
        if actual != item["sha256"]:
            raise OSError(f"Write verification failed for {item['path']}")
    uncertainty = build_uncertainty(indexed, results, unmapped_fields, incomplete)
    context = {
        "status": status, "matrix_path": matrix_path.name, "operations_path": operations_path.name,
        "sources": sources, "uncertainty": uncertainty, "change_records": change_records,
        "operation_results": results, "strata": strata, "estimands": copy.deepcopy(list(indexed.values())),
    }
    result = render_result(case_id, output_contract, context)
    if result.get("case_id") != case_id or set(result) != (set(output_contract) | {"case_id"}):
        raise SchemaError("Internal result contract rendering error")
    result_path.write_text(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=False) + "\n", encoding="utf-8")
    # Verify the actual JSON artifact and exact case identity after writing.
    verified = load_json(result_path)
    if verified != result or verified["case_id"] != case_id:
        raise OSError("result.json write verification failed")
    return result


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=Path("/input"))
    parser.add_argument("--work", type=Path, default=Path("/app/work"))
    parser.add_argument("--output", type=Path, default=Path("/app/output"))
    parser.add_argument("--strict-operations", action="store_true",
                        help="Fail on any blocked operation; useful for negative tests, not normal comparisons")
    args = parser.parse_args(argv)
    try:
        result = run(args.input, args.work, args.output, args.strict_operations)
    except (SchemaError, OperationBlocked, OSError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    print(json.dumps({"case_id": result["case_id"], "status": result.get("status", "contract_specific_status"),
                      "output": str(args.output)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
