#!/usr/bin/env python3
"""Independently audit a generated result and graph against sources and targets."""
from __future__ import annotations

import argparse
import sys
from collections import Counter
from pathlib import Path

from common import ContractError, atomic_json, load_json, normalize_target_fields, source_paragraph_index, verify_evidence
from build_graph import verify_claim_guards


def validate(result, graph, targets, sources):
    paragraph_index = source_paragraph_index(sources)
    for key in ("case_id", "status", "result", "claims", "uncertainties"):
        if key not in result:
            raise ContractError(f"result.json lacks top-level {key}")
    if not isinstance(result["case_id"], str) or not result["case_id"]:
        raise ContractError("result case_id must be a nonempty string")
    if result["status"] not in {"answered", "partial", "insufficient_evidence", "input_error"}:
        raise ContractError("Invalid run status")
    if not isinstance(result["result"], dict):
        raise ContractError("result.result must be an object")
    fields = result["result"].get("fields")
    mirrored = result["result"].get("field_results")
    if not isinstance(fields, list) or not isinstance(mirrored, list) or fields != mirrored:
        raise ContractError("result.fields and result.field_results must be identical mirrors")
    expected = [target["field_id"] for target in targets]
    actual = [field.get("field_id") for field in fields]
    if actual != expected:
        raise ContractError(f"Field coverage/order mismatch: expected {expected}, got {actual}")
    required = {
        "field_id", "status", "scalar", "units", "statistic", "experimental_condition", "condition",
        "comparator", "paragraph_id", "quote", "evidence", "notes",
    }
    evidence_edges = 0
    for field in fields:
        context = f"Field {field.get('field_id')}"
        missing = required - set(field)
        if missing:
            raise ContractError(f"{context}: missing keys {sorted(missing)}")
        if field["status"] not in {"reported", "not_reported", "source_conflict", "extraction_failed"}:
            raise ContractError(f"{context}: invalid status")
        if field["experimental_condition"] != field["condition"]:
            raise ContractError(f"{context}: condition aliases differ")
        if not isinstance(field["evidence"], list):
            raise ContractError(f"{context}: evidence must be a list")
        for evidence in field["evidence"]:
            verify_evidence(evidence, paragraph_index, context)
        if field["status"] in {"reported", "not_reported", "source_conflict"} and not field["evidence"]:
            raise ContractError(f"{context}: status requires evidence")
        if field["status"] == "reported" and field["scalar"] is None:
            raise ContractError(f"{context}: reported scalar is null")
        if field["status"] in {"not_reported", "source_conflict", "extraction_failed"} and field["scalar"] is not None:
            raise ContractError(f"{context}: unresolved field has a scalar")
        if field["evidence"]:
            if not any(e["paragraph_id"] == field["paragraph_id"] and e["quote"] == field["quote"] for e in field["evidence"]):
                raise ContractError(f"{context}: primary location/quote not in evidence")
        elif field["paragraph_id"] is not None or field["quote"] != "":
            raise ContractError(f"{context}: evidence-free field has a location")
    if not isinstance(result["claims"], list) or not isinstance(result["uncertainties"], list):
        raise ContractError("claims and uncertainties must be lists")
    for claim in result["claims"]:
        for key in ("claim_id", "text", "kind", "epistemic_status", "modality", "attribution", "evidence", "source_id", "location"):
            if key not in claim:
                raise ContractError(f"Claim is missing {key}")
        if not isinstance(claim["location"], dict):
            raise ContractError(f"Claim {claim.get('claim_id')}: location must be an object")
        if claim["source_id"] != claim["evidence"][0]["source_id"] or claim["location"].get("paragraph_id") != claim["evidence"][0]["paragraph_id"]:
            raise ContractError(f"Claim {claim.get('claim_id')}: primary source/location do not match first evidence")
        for evidence in claim["evidence"]:
            verify_evidence(evidence, paragraph_index, f"Claim {claim.get('claim_id')}")
        verify_claim_guards(claim, paragraph_index)

    if graph["case_id"] != result["case_id"] or graph["status"] != result["status"]:
        raise ContractError("Graph and result case/status mismatch")
    nodes = graph.get("nodes")
    edges = graph.get("edges")
    if not isinstance(nodes, list) or not isinstance(edges, list):
        raise ContractError("Graph nodes and edges must be lists")
    node_ids = [node.get("id") for node in nodes]
    if len(node_ids) != len(set(node_ids)) or any(not isinstance(node_id, str) for node_id in node_ids):
        raise ContractError("Graph node IDs must be unique strings")
    node_set = set(node_ids)
    for edge in edges:
        if edge.get("from") not in node_set or edge.get("to") not in node_set:
            raise ContractError(f"Dangling graph edge: {edge}")
        if edge.get("type") == "grounded_in":
            verify_evidence(edge.get("evidence"), paragraph_index, "Graph grounded_in edge")
            evidence_edges += 1
    for field in fields:
        if f"field:{field['field_id']}" not in node_set:
            raise ContractError(f"Graph lacks field node {field['field_id']}")
    return {
        "valid": True,
        "case_id": result["case_id"],
        "status": result["status"],
        "requested_field_count": len(expected),
        "field_status_counts": dict(Counter(field["status"] for field in fields)),
        "claim_count": len(result["claims"]),
        "claim_kind_counts": dict(Counter(claim["kind"] for claim in result["claims"])),
        "graph_node_count": len(nodes),
        "graph_edge_count": len(edges),
        "verbatim_grounded_edge_count": evidence_edges,
        "checks": [
            "all requested field_ids occur once in both mirrors in request order",
            "required per-field keys and condition alias equality",
            "all evidence quotations are exact substrings of registered paragraphs",
            "cited/hedged/speculative claim non-promotion guards",
            "graph edge endpoints and evidence-backed grounded_in edges",
        ],
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--result", type=Path, required=True)
    parser.add_argument("--graph", type=Path, required=True)
    parser.add_argument("--targets", type=Path, required=True)
    parser.add_argument("--sources", type=Path, required=True)
    parser.add_argument("--report", type=Path)
    args = parser.parse_args(argv)
    try:
        report = validate(load_json(args.result), load_json(args.graph), normalize_target_fields(load_json(args.targets)), load_json(args.sources))
        if args.report:
            atomic_json(args.report, report)
    except ContractError as exc:
        print(f"VALIDATION_ERROR: {exc}", file=sys.stderr)
        return 2
    except OSError as exc:
        print(f"IO_ERROR: {exc}", file=sys.stderr)
        return 3
    print(f"VALID: {report['case_id']}; fields={report['requested_field_count']}; claims={report['claim_count']}; nodes={report['graph_node_count']}; edges={report['graph_edge_count']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
