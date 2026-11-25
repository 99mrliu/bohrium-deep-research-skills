#!/usr/bin/env python3
"""Source/version reconciliation. Python 3.9+ standard library only.

The program inventories and validates mechanical facts. It does not infer semantic
entailment: a human/agent supplies evidence bindings and per-document examined outcomes.
"""

from __future__ import annotations

import argparse
import hashlib
import html
import json
import os
from pathlib import Path, PurePosixPath
import sys
from typing import Any, Dict, Iterable, List, Optional, Tuple

STATUS_VALUES = {"supported", "partially_supported", "contradicted", "insufficient_evidence"}
RELATION_TYPES = {"revises", "corrects", "supplements", "retracts", "version_of", "related_to"}
CONTROL_ROOT_FILES = {"case.json", "task.md", "claims-to-verify.json"}
TEXT_SUFFIXES = {
    ".txt", ".text", ".md", ".csv", ".tsv", ".json", ".jsonl", ".html",
    ".htm", ".xml", ".tex", ".srt", ".vtt", ".yaml", ".yml", ".log",
}
ID_ERROR = "document_id must match [A-Za-z0-9][A-Za-z0-9_.-]{0,127}"


class ReconcileError(Exception):
    """A controlled validation failure; CLI exits 1 without a traceback."""


def read_json(path: Path) -> Any:
    try:
        with path.open("r", encoding="utf-8") as handle:
            return json.load(handle)
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ReconcileError(f"cannot read JSON {path}: {exc}") from exc


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    with temporary.open("w", encoding="utf-8", newline="\n") as handle:
        json.dump(value, handle, ensure_ascii=False, indent=2, sort_keys=False)
        handle.write("\n")
    os.replace(temporary, path)


def required_dict(value: Any, label: str) -> Dict[str, Any]:
    if not isinstance(value, dict):
        raise ReconcileError(f"{label} must be an object")
    return value


def load_claims(path: Path) -> List[Dict[str, Any]]:
    value = read_json(path)
    if isinstance(value, dict):
        value = value.get("claims")
    if not isinstance(value, list):
        raise ReconcileError("claims-to-verify.json must be a list or an object with a claims list")
    claims = []
    seen = set()
    for index, item in enumerate(value):
        claim = required_dict(item, f"claim[{index}]")
        claim_id = claim.get("claim_id")
        if not isinstance(claim_id, str) or not claim_id:
            raise ReconcileError(f"claim[{index}] has no nonempty claim_id")
        if claim_id in seen:
            raise ReconcileError(f"duplicate claim_id: {claim_id}")
        seen.add(claim_id)
        copied = dict(claim)
        copied.setdefault("claim", "")
        copied.setdefault("version_scope", [])
        claims.append(copied)
    return claims


def load_case(input_dir: Path) -> Dict[str, Any]:
    case = required_dict(read_json(input_dir / "case.json"), "case.json")
    if not isinstance(case.get("case_id"), str) or not case["case_id"]:
        raise ReconcileError("case.json requires a nonempty case_id")
    if not isinstance(case.get("output_contract"), dict):
        raise ReconcileError("case.json requires an output_contract object")
    return case


def safe_output(path: Path) -> None:
    if path.exists() and path.is_symlink():
        raise ReconcileError(f"refusing symlink output: {path}")


def initial_claim(claim: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "claim_id": claim["claim_id"],
        "claim": claim.get("claim", ""),
        "status": "insufficient_evidence",
        "version_scope": claim.get("version_scope", []),
        "evidence": [],
        "rationale": "Not yet reconciled; claims are hypotheses, not established facts.",
        "condition": claim.get("condition"),
        **({"supplement_only": True} if claim.get("supplement_only") else {}),
    }


def command_init(args: argparse.Namespace) -> None:
    input_dir = Path(args.input)
    output = Path(args.output)
    safe_output(output)
    case = load_case(input_dir)
    claims = load_claims(input_dir / "claims-to-verify.json")
    result: Dict[str, Any] = {
        "case_id": case["case_id"],
        "status": "partial",
        "sources": [],
        "uncertainty": [
            "Initialization only: source identities, versions, quotations, and claim support remain unverified."
        ],
        "change_records": [
            {"sequence": 1, "phase": "initialize", "change": "Wrote an honest partial result before analysis."}
        ],
    }
    # Materialize every contract field with its declared container kind, even before evidence exists.
    for key, specification in case["output_contract"].items():
        if key in result:
            continue
        if key in {"claims", "verifications", "claim_verdicts", "results"}:
            result[key] = [initial_claim(claim) for claim in claims] if isinstance(specification, list) else {}
        elif isinstance(specification, list):
            result[key] = []
        elif isinstance(specification, dict):
            result[key] = {}
        else:
            result[key] = None
    write_json(output, result)


def inventory_files(input_dir: Path) -> Dict[str, Any]:
    if not input_dir.is_dir():
        raise ReconcileError(f"input directory does not exist: {input_dir}")
    input_root = input_dir.resolve()
    records: List[Dict[str, Any]] = []
    first_by_hash: Dict[str, str] = {}
    for path in sorted(input_root.rglob("*"), key=lambda p: p.relative_to(input_root).as_posix()):
        if path.is_symlink():
            raise ReconcileError(f"symlink input is not supported: {path}")
        if not path.is_file():
            continue
        relative = path.relative_to(input_root)
        if len(relative.parts) == 1 and relative.name in CONTROL_ROOT_FILES:
            continue
        file_id = relative.as_posix()
        if PurePosixPath(file_id).is_absolute() or ".." in PurePosixPath(file_id).parts:
            raise ReconcileError(f"unsafe inventory path: {file_id}")
        try:
            payload = path.read_bytes()
        except OSError as exc:
            raise ReconcileError(f"cannot inventory {file_id}: {exc}") from exc
        digest = hashlib.sha256(payload).hexdigest()
        readable = False
        error: Optional[str] = None
        if path.suffix.lower() in TEXT_SUFFIXES:
            try:
                payload.decode("utf-8")
                readable = True
            except UnicodeDecodeError as exc:
                error = f"not valid UTF-8: byte {exc.start}"
        else:
            error = "no built-in text extractor for this file type"
        records.append({
            "file_id": file_id,
            "sha256": digest,
            "size_bytes": len(payload),
            "text_readable": readable,
            "text_error": error,
            "duplicate_of": first_by_hash.get(digest),
        })
        first_by_hash.setdefault(digest, file_id)
    return {
        "inventory_algorithm": "SHA-256 over actual input bytes; duplicate_of is the first path with the same digest",
        "input_control_files_excluded": sorted(CONTROL_ROOT_FILES),
        "files": records,
        "file_count": len(records),
        "duplicate_file_count": sum(1 for record in records if record["duplicate_of"] is not None),
    }


def command_inventory(args: argparse.Namespace) -> None:
    case = load_case(Path(args.input))
    inventory = inventory_files(Path(args.input))
    # Case provenance keeps example outputs explicitly SYNTHETIC without hardcoding that label for real cases.
    inventory["case_id"] = case["case_id"]
    if case.get("labels") is not None:
        inventory["case_labels"] = case["labels"]
    write_json(Path(args.output), inventory)


def valid_document_id(document_id: Any) -> bool:
    if not isinstance(document_id, str) or not document_id or len(document_id) > 128:
        return False
    if not (document_id[0].isascii() and document_id[0].isalnum()):
        return False
    return all(character.isascii() and (character.isalnum() or character in "_.-") for character in document_id)


def load_inventory(work_dir: Path) -> Dict[str, Any]:
    return required_dict(read_json(work_dir / "source-inventory.json"), "source inventory")


def load_metadata(path: Path) -> List[Dict[str, Any]]:
    raw = required_dict(read_json(path), "source metadata")
    documents = raw.get("documents")
    if not isinstance(documents, list) or not documents:
        raise ReconcileError("source metadata requires a nonempty documents list")
    result = []
    seen = set()
    for index, value in enumerate(documents):
        document = required_dict(value, f"documents[{index}]")
        document_id = document.get("document_id")
        if not valid_document_id(document_id):
            raise ReconcileError(f"documents[{index}]: {ID_ERROR}")
        if document_id in seen:
            raise ReconcileError(f"duplicate document_id: {document_id}")
        seen.add(document_id)
        result.append(document)
    return result


def resolve_input_file(input_dir: Path, file_id: str) -> Path:
    if not isinstance(file_id, str) or not file_id:
        raise ReconcileError("file_id must be a nonempty string")
    relative = PurePosixPath(file_id)
    if relative.is_absolute() or ".." in relative.parts or "." in relative.parts:
        raise ReconcileError(f"unsafe file_id: {file_id}")
    path = (input_dir / Path(*relative.parts)).resolve()
    try:
        path.relative_to(input_dir.resolve())
    except ValueError as exc:
        raise ReconcileError(f"file escapes input root: {file_id}") from exc
    if path.is_symlink() or not path.is_file():
        raise ReconcileError(f"file missing or symlinked: {file_id}")
    return path


def validate_documents(input_dir: Path, inventory: Dict[str, Any], documents: List[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    raw_files = inventory.get("files")
    if not isinstance(raw_files, list):
        raise ReconcileError("inventory files must be a list")
    inventory_by_id = {}
    for value in raw_files:
        record = required_dict(value, "inventory file")
        file_id = record.get("file_id")
        if not isinstance(file_id, str) or file_id in inventory_by_id:
            raise ReconcileError(f"invalid or duplicate inventory file_id: {file_id}")
        inventory_by_id[file_id] = record
    by_document: Dict[str, Dict[str, Any]] = {}
    claimed_files = set()
    for document in documents:
        document_id = document["document_id"]
        file_ids = document.get("files")
        if not isinstance(file_ids, list) or not file_ids:
            raise ReconcileError(f"{document_id}: files must be a nonempty list")
        hashes = set()
        checked_files = []
        for file_id in file_ids:
            if file_id in claimed_files:
                raise ReconcileError(f"file {file_id} is assigned to more than one document/version")
            claimed_files.add(file_id)
            if file_id not in inventory_by_id:
                raise ReconcileError(f"{document_id}: dangling file_id {file_id}")
            record = inventory_by_id[file_id]
            path = resolve_input_file(input_dir, file_id)
            actual_hash = hashlib.sha256(path.read_bytes()).hexdigest()
            if actual_hash != record.get("sha256"):
                raise ReconcileError(f"stale inventory/hash mismatch for {file_id}; rerun inventory")
            actual_size = path.stat().st_size
            if actual_size != record.get("size_bytes"):
                raise ReconcileError(f"stale inventory/size mismatch for {file_id}; rerun inventory")
            hashes.add(actual_hash)
            checked_files.append(record)
        if len(hashes) != 1:
            raise ReconcileError(f"{document_id}: all files bound to one document/version must have the same hash")
        version = document.get("version")
        if version is not None and (not isinstance(version, str) or not version.strip()):
            raise ReconcileError(f"{document_id}: version must be a nonempty string or null")
        document_date = document.get("date")
        if document_date is not None and not isinstance(document_date, str):
            raise ReconcileError(f"{document_id}: date must be a string or null")
        for field in ("doi", "title", "kind"):
            if document.get(field) is not None and not isinstance(document.get(field), str):
                raise ReconcileError(f"{document_id}: {field} must be a string or null")
        relations = document.get("relations", [])
        if not isinstance(relations, list):
            raise ReconcileError(f"{document_id}: relations must be a list")
        for relation in relations:
            relation = required_dict(relation, f"{document_id} relation")
            if relation.get("type") not in RELATION_TYPES or not valid_document_id(relation.get("target_id")):
                raise ReconcileError(f"{document_id}: invalid relation type or target_id")
        copied = dict(document)
        copied["_checked_files"] = checked_files
        by_document[document_id] = copied
    for document in documents:
        for relation in document.get("relations", []):
            if relation["target_id"] not in by_document:
                raise ReconcileError(
                    f"dangling relation: {document['document_id']} -> {relation['target_id']}"
                )
    return by_document


def build_and_validate_dag(documents: List[Dict[str, Any]]) -> Dict[str, Any]:
    known = {document["document_id"] for document in documents}
    adjacency = {document_id: [] for document_id in known}
    edges = []
    for document in documents:
        source = document["document_id"]
        for relation in document.get("relations", []):
            target = relation["target_id"]
            if target not in known:
                raise ReconcileError(f"dangling relation: {source} -> {target}")
            if source == target:
                raise ReconcileError(f"source-version DAG cycle includes self relation: {source}")
            adjacency[source].append(target)
            edges.append({"source": source, "target": target, "type": relation["type"]})
    visiting, finished, order = set(), set(), []

    def visit(node: str, trail: List[str]) -> None:
        if node in visiting:
            start = trail.index(node) if node in trail else 0
            cycle = trail[start:] + [node]
            raise ReconcileError("source-version DAG cycle detected: " + " -> ".join(cycle))
        if node in finished:
            return
        visiting.add(node)
        for target in adjacency[node]:
            visit(target, trail + [target])
        visiting.remove(node)
        finished.add(node)
        order.append(node)

    for node in sorted(known):
        visit(node, [node])
    order.reverse()
    return {
        "validation": "acyclic; every relation target and bound file exists; hashes match the actual inputs",
        "nodes": sorted(known),
        "edges": sorted(edges, key=lambda edge: (edge["source"], edge["target"], edge["type"])),
        "topological_order": order,
        "authority_rule": "DAG order is structural only: newer/later documents do not automatically win.",
    }


def load_documents_and_dag(input_dir: Path, work_dir: Path, metadata_path: Path) -> Tuple[List[Dict[str, Any]], Dict[str, Dict[str, Any]], Dict[str, Any], Dict[str, Any]]:
    inventory = load_inventory(work_dir)
    documents = load_metadata(metadata_path)
    by_document = validate_documents(input_dir, inventory, documents)
    dag = build_and_validate_dag(documents)
    for document in documents:
        document["_checked_files"] = by_document[document["document_id"]]["_checked_files"]
    return documents, by_document, dag, inventory


def command_validate(args: argparse.Namespace) -> None:
    work_dir = Path(args.work)
    documents, _by_document, dag, _inventory = load_documents_and_dag(
        Path(args.input), work_dir, Path(args.metadata)
    )
    dag["nodes"] = [document["document_id"] for document in documents]
    dag["topological_order"] = [node for node in dag["topological_order"] if node in set(dag["nodes"])]
    write_json(work_dir / "source-version-dag.json", dag)


def load_evidence(path: Path, claims: List[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    raw = required_dict(read_json(path), "evidence mapping")
    decisions = raw.get("claim_decisions")
    if not isinstance(decisions, list):
        raise ReconcileError("evidence mapping requires a claim_decisions list")
    claim_ids = {claim["claim_id"] for claim in claims}
    mapped = {}
    for value in decisions:
        decision = required_dict(value, "claim decision")
        claim_id = decision.get("claim_id")
        if claim_id not in claim_ids:
            raise ReconcileError(f"evidence mapping has unknown claim_id: {claim_id}")
        if claim_id in mapped:
            raise ReconcileError(f"evidence mapping repeats claim_id: {claim_id}")
        evidence = decision.get("evidence", [])
        if not isinstance(evidence, list):
            raise ReconcileError(f"{claim_id}: evidence must be a list")
        mapped[claim_id] = decision
    missing = claim_ids - set(mapped)
    if missing:
        raise ReconcileError("claims without reviewed decisions: " + ", ".join(sorted(missing)))
    return mapped


def exact_quote(document: Dict[str, Any], quote: Any) -> Tuple[bool, Optional[str], Optional[str]]:
    if not isinstance(quote, str) or not quote:
        return False, None, "quote must be a nonempty string"
    unreadable = []
    for file in document["_checked_files"]:
        if not file.get("text_readable"):
            unreadable.append(file["file_id"])
            continue
        # File hashes and types were just revalidated. Read the exact bound document only.
        path = Path(file["_absolute_path"])
        text = path.read_text(encoding="utf-8")
        if quote in text:
            return True, file["file_id"], None
    if unreadable and len(unreadable) == len(document["_checked_files"]):
        return False, None, "bound document has no readable text; quote cannot be checked"
    return False, None, "quote is absent from the bound document/version (absence is not contradiction)"


def combine_document_outcomes(outcomes: List[str]) -> str:
    if not outcomes:
        return "missing"
    unique = set(outcomes)
    if unique == {"supported"}:
        return "supported"
    if unique == {"contradicted"}:
        return "contradicted"
    if unique <= {"insufficient_evidence"}:
        return "insufficient_evidence"
    return "partially_supported"


def verdict_for_scope(claim: Dict[str, Any], per_document: Dict[str, str]) -> str:
    scope = claim.get("version_scope", [])
    if not isinstance(scope, list) or not scope:
        return "insufficient_evidence"
    if claim.get("claim_class") == "version_comparison" and len(scope) < 2:
        return "insufficient_evidence"
    outcomes = [per_document.get(document_id, "missing") for document_id in scope]
    if len(scope) == 1:
        outcome = outcomes[0]
        return outcome if outcome in STATUS_VALUES else "insufficient_evidence"
    if any(outcome in {"missing", "insufficient_evidence"} for outcome in outcomes):
        if any(outcome in {"supported", "partially_supported", "contradicted"} for outcome in outcomes):
            return "partially_supported"
        return "insufficient_evidence"
    if all(outcome == "supported" for outcome in outcomes):
        return "supported"
    if all(outcome == "contradicted" for outcome in outcomes):
        return "contradicted"
    return "partially_supported"


def evaluate_claims(
    input_dir: Path,
    claims: List[Dict[str, Any]],
    decisions: Dict[str, Dict[str, Any]],
    by_document: Dict[str, Dict[str, Any]],
) -> Tuple[List[Dict[str, Any]], List[str]]:
    all_uncertainties: List[str] = []
    evaluated = []
    for claim in claims:
        claim_id = claim["claim_id"]
        decision = decisions[claim_id]
        scope = claim.get("version_scope", [])
        scope_valid = isinstance(scope, list) and bool(scope) and all(isinstance(item, str) for item in scope)
        if scope_valid and (len(set(scope)) != len(scope) or any(item not in by_document for item in scope)):
            raise ReconcileError(f"{claim_id}: version_scope has duplicates or unknown document_ids")
        if not scope_valid:
            all_uncertainties.append(f"{claim_id}: version_scope is empty or invalid; no cross-version verdict was attempted.")
            scope = []
        checked_evidence = []
        buckets = {"supported": [], "partially_supported": [], "contradicted": [], "insufficient_evidence": []}
        for index, value in enumerate(decision.get("evidence", [])):
            evidence = required_dict(value, f"{claim_id} evidence[{index}]")
            document_id = evidence.get("document_id")
            if "document_ids" in evidence or not isinstance(document_id, str):
                raise ReconcileError(f"{claim_id}: each evidence item must bind exactly one document_id")
            if document_id not in by_document:
                raise ReconcileError(f"{claim_id}: evidence binds unknown document_id {document_id}")
            if document_id not in scope:
                raise ReconcileError(f"{claim_id}: evidence document {document_id} is outside version_scope")
            outcome = evidence.get("outcome")
            if outcome not in STATUS_VALUES:
                raise ReconcileError(f"{claim_id}: invalid examined evidence outcome {outcome}")
            verified, matched_file, quote_error = exact_quote(by_document[document_id], evidence.get("quote"))
            effective_outcome = outcome if verified else "insufficient_evidence"
            if verified:
                buckets[effective_outcome].append(document_id)
            if quote_error:
                all_uncertainties.append(f"{claim_id}: {document_id}: {quote_error}")
            checked = {
                "document_id": document_id,
                "version": by_document[document_id].get("version"),
                "quote": evidence.get("quote"),
                "locator": evidence.get("locator"),
                "quote_verified": verified,
                "outcome": effective_outcome,
                "matched_file_id": matched_file,
                "quote_check_note": quote_error,
                "review_note": evidence.get("review_note"),
            }
            checked_evidence.append(checked)
        per_document = {}
        for document_id in scope:
            document_evidence = [item for item in checked_evidence if item["document_id"] == document_id and item["quote_verified"]]
            per_document[document_id] = combine_document_outcomes([item["outcome"] for item in document_evidence])
        status = verdict_for_scope(claim, per_document)
        rationale = decision.get("rationale")
        if not isinstance(rationale, str) or not rationale.strip():
            raise ReconcileError(f"{claim_id}: reviewed rationale is required")
        scope_note = "Verdict applies only to version_scope=" + (", ".join(scope) if scope else "UNRESOLVED") + "; no version pooling."
        result = {
            "claim_id": claim_id,
            "claim": claim.get("claim", ""),
            "status": status,
            "version_scope": scope,
            "evidence": checked_evidence,
            "rationale": rationale + " " + scope_note,
            "condition": claim.get("condition"),
            "documents_supported": [doc for doc in scope if per_document.get(doc) == "supported"],
            "documents_partial": [doc for doc in scope if per_document.get(doc) == "partially_supported"],
            "documents_contradicted": [doc for doc in scope if per_document.get(doc) == "contradicted"],
            "documents_insufficient": [doc for doc in scope if per_document.get(doc) == "insufficient_evidence"],
            "documents_missing": [doc for doc in scope if per_document.get(doc) == "missing"],
            "per_document_outcomes": per_document,
        }
        if claim.get("claim_class") is not None:
            result["claim_class"] = claim["claim_class"]
        if claim.get("supplement_only"):
            result["supplement_only"] = True
            result["scope_limitation"] = "Supplement-local evidence only; main-text pagination and conditions are not inherited."
        if claim.get("claim_class") == "version_comparison" and len(scope) < 2:
            result["scope_limitation"] = "Cannot perform cross-version comparison with fewer than two documents in version_scope."
            all_uncertainties.append(f"{claim_id}: cross-version comparison is impossible with fewer than two scoped documents.")
        evaluated.append(result)
    if len(by_document) == 1:
        all_uncertainties.append("Only one source document was provided: cross-version comparison is impossible; no additional version was inferred.")
    return evaluated, all_uncertainties


def make_sources(documents: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    sources = []
    for document in documents:
        files = document["_checked_files"]
        sources.append({
            "document_id": document["document_id"],
            "doi": document.get("doi"),
            "title": document.get("title"),
            "version": document.get("version"),
            "date": document.get("date"),
            "kind": document.get("kind"),
            "files": [file["file_id"] for file in files],
            "sha256": files[0]["sha256"],
            "duplicate_files": [file["file_id"] for file in files if file.get("duplicate_of")],
            "relations": document.get("relations", []),
            "unknown_fields": "null means unknown; never guessed",
        })
    return sources


def make_version_matrix(documents: List[Dict[str, Any]], claims: List[Dict[str, Any]]) -> Dict[str, Any]:
    rows = []
    for document in documents:
        document_id = document["document_id"]
        statements = []
        for claim in claims:
            for evidence in claim["evidence"]:
                if evidence["document_id"] == document_id:
                    statements.append({
                        "claim_id": claim["claim_id"],
                        "quote": evidence["quote"],
                        "quote_verified": evidence["quote_verified"],
                        "outcome": evidence["outcome"],
                        "condition": claim.get("condition"),
                        "supplement_only": bool(claim.get("supplement_only")),
                    })
        rows.append({
            "document_id": document_id,
            "work_title": document.get("title"),
            "doi": document.get("doi"),
            "version": document.get("version"),
            "date": document.get("date"),
            "kind": document.get("kind"),
            "files": [file["file_id"] for file in document["_checked_files"]],
            "sha256": document["_checked_files"][0]["sha256"],
            "relations": document.get("relations", []),
            "claim_statements": statements,
        })
    return {
        "columns": ["document_id", "version", "date", "kind", "claim_statements", "relations"],
        "rows": rows,
        "by_document": {row["document_id"]: row for row in rows},
        "comparison_rule": "Statements are displayed side by side. They are not pooled, ranked by recency, or treated as independent corroboration when file hashes match.",
    }


def render_svg(documents: List[Dict[str, Any]], dag: Dict[str, Any], output: Path) -> None:
    width = 1100
    height = 140 + 150 * len(documents)
    case_id = str(dag.get("case_id", "UNSPECIFIED"))
    synthetic_prefix = "SYNTHETIC — " if "SYNTHETIC" in case_id.upper() else ""
    lines = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">',
        '<rect width="100%" height="100%" fill="#ffffff"/>',
        '<style>text{font-family:monospace;fill:#17202a}.node{fill:#eef4ff;stroke:#315b9a}.edge{stroke:#67748a;fill:none;marker-end:url(#arrow)}.small{font-size:13px}.main{font-size:16px;font-weight:bold}</style>',
        '<defs><marker id="arrow" markerWidth="10" markerHeight="7" refX="9" refY="3.5" orient="auto"><polygon points="0 0,10 3.5,0 7" fill="#67748a"/></marker></defs>',
        f'<text x="24" y="30" class="main">{html.escape(synthetic_prefix + "Source/version provenance — structural relations, not authority ranking")}</text>',
        f'<text x="24" y="50" class="small">case={html.escape(case_id)}</text>',
    ]
    # Linear placement is deliberately simple and deterministic for small audit diagrams.
    positions = {document["document_id"]: (30, 85 + index * 150) for index, document in enumerate(documents)}
    for edge in dag["edges"]:
        x1, y1 = positions[edge["source"]]
        x2, y2 = positions[edge["target"]]
        lines.append(f'<path class="edge" d="M {x1+485} {y1+48} C 1030 {y1+48}, 1030 {y2+48}, {x2+490} {y2+48}"/>')
        lines.append(f'<text x="1000" y="{(y1+y2)//2+42}" class="small">{html.escape(edge["type"])}</text>')
    for document in documents:
        document_id = document["document_id"]
        x, y = positions[document_id]
        digest = document["_checked_files"][0]["sha256"]
        literals = [
            f'{document_id} | version={document.get("version") if document.get("version") is not None else "null"} | date={document.get("date") if document.get("date") is not None else "null"}',
            f'kind={document.get("kind") if document.get("kind") is not None else "null"} | DOI={document.get("doi") if document.get("doi") is not None else "null"}',
            f'sha256={digest}',
            'duplicate copies: ' + ", ".join(file["file_id"] for file in document["_checked_files"] if file.get("duplicate_of")),
        ]
        lines.append(f'<rect class="node" x="{x}" y="{y}" width="485" height="105" rx="8"/>')
        for offset, literal in enumerate(literals):
            lines.append(f'<text x="{x+12}" y="{y+23+20*offset}" class="small">{html.escape(literal)}</text>')
    lines.append(f'<text x="24" y="{height-18}" class="small">Null identity metadata is unknown. Supplement pagination is local. Generated by reconciliation from reviewed evidence bindings.</text>')
    lines.append('</svg>')
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text("\n".join(lines) + "\n", encoding="utf-8")


def project_record(record: Dict[str, Any], template: Any) -> Dict[str, Any]:
    if not isinstance(template, dict):
        return record
    projected = {}
    for key, specification in template.items():
        if key in record:
            value = record[key]
        elif key == "verified_at":
            value = None
        else:
            value = [] if isinstance(specification, list) else {} if isinstance(specification, dict) else None
        if isinstance(specification, list) and specification and isinstance(specification[0], dict) and isinstance(value, list):
            value = [project_record(item, specification[0]) if isinstance(item, dict) else item for item in value]
        elif isinstance(specification, dict) and isinstance(value, dict) and set(value).issubset(set(record)):
            # Contract descriptors are not a license to discard document- or claim-keyed mappings.
            value = value
        projected[key] = value
    return projected


def adapt_matrix(specification: Any, matrix: Dict[str, Any]) -> Any:
    if isinstance(specification, list):
        template = specification[0] if specification and isinstance(specification[0], dict) else None
        return [project_record(row, template) if template else row for row in matrix["rows"]]
    if isinstance(specification, dict) and ("rows" in specification or "columns" in specification):
        result = {}
        for key, value in specification.items():
            if key == "rows":
                template = value[0] if isinstance(value, list) and value and isinstance(value[0], dict) else None
                result[key] = [project_record(row, template) if template else row for row in matrix["rows"]]
            elif key == "columns":
                result[key] = matrix["columns"]
            elif key == "by_document":
                result[key] = matrix["by_document"]
            elif key == "comparison_rule":
                result[key] = matrix["comparison_rule"]
            else:
                result[key] = matrix.get(key, [] if isinstance(value, list) else {} if isinstance(value, dict) else None)
        return result
    return matrix["by_document"]


def adapt_dag(specification: Any, dag: Dict[str, Any]) -> Any:
    if not isinstance(specification, dict):
        return dag
    result = {}
    for key, value in specification.items():
        result[key] = dag.get(key, [] if isinstance(value, list) else {} if isinstance(value, dict) else None)
    return result


def apply_output_contract(result: Dict[str, Any], contract: Dict[str, Any], claims: List[Dict[str, Any]], matrix: Dict[str, Any], dag: Dict[str, Any], inventory: Dict[str, Any]) -> None:
    for key, specification in contract.items():
        if key in result and key not in {"status", "sources", "uncertainty", "change_records"}:
            continue
        if key in {"claims", "verifications", "claim_verdicts", "results"}:
            if isinstance(specification, dict):
                template = specification.get(next(iter(specification))) if specification else None
                result[key] = {claim["claim_id"]: project_record(claim, template) for claim in claims}
            else:
                template = specification[0] if isinstance(specification, list) and specification and isinstance(specification[0], dict) else None
                result[key] = [project_record(claim, template) if template else claim for claim in claims]
        elif key in {"version_matrix", "version_comparison", "version_comparisons"}:
            result[key] = adapt_matrix(specification, matrix)
        elif key in {"source_version_dag", "provenance_dag", "source_dag", "dag"}:
            result[key] = adapt_dag(specification, dag)
        elif key in {"source_inventory", "inventory"}:
            result[key] = inventory["files"] if isinstance(specification, list) else inventory
        else:
            if key not in result:
                result[key] = [] if isinstance(specification, list) else {} if isinstance(specification, dict) else None


def validate_final_contract(result: Dict[str, Any], case: Dict[str, Any]) -> None:
    for key, specification in case["output_contract"].items():
        if key not in result:
            raise ReconcileError(f"internal error: missing output_contract field {key}")
        if isinstance(specification, list) and not isinstance(result[key], list):
            raise ReconcileError(f"output_contract field {key} must remain a list")
        if isinstance(specification, dict) and not isinstance(result[key], dict):
            raise ReconcileError(f"output_contract field {key} must remain an object")
    for key in ("case_id", "status", "sources", "uncertainty", "change_records"):
        if key not in result:
            raise ReconcileError(f"internal error: missing top-level field {key}")
    for key in ("sources", "uncertainty", "change_records"):
        if not isinstance(result[key], list):
            raise ReconcileError(f"top-level field {key} must be a list")
    if result["case_id"] != case["case_id"] or result["status"] not in {"partial", "complete"}:
        raise ReconcileError("internal error: invalid case_id or status")
    for key in ("claims", "verifications", "claim_verdicts", "results"):
        claim_values = result.get(key)
        if key in case["output_contract"] and isinstance(claim_values, list):
            for claim in claim_values:
                if not isinstance(claim, dict) or claim.get("status") not in STATUS_VALUES:
                    raise ReconcileError(f"output_contract field {key} contains an invalid claim verdict")
                if not isinstance(claim.get("version_scope"), list):
                    raise ReconcileError(f"{key}: each final claim requires a version_scope list")
                for evidence in claim.get("evidence", []):
                    if not isinstance(evidence.get("document_id"), str) or "document_ids" in evidence:
                        raise ReconcileError(f"{key}: final evidence must bind exactly one document_id")
                    if not isinstance(evidence.get("quote_verified"), bool):
                        raise ReconcileError(f"{key}: final evidence requires boolean quote_verified")


def command_finalize(args: argparse.Namespace) -> None:
    input_dir = Path(args.input)
    work_dir = Path(args.work)
    case = load_case(input_dir)
    claims = load_claims(input_dir / "claims-to-verify.json")
    documents, by_document, dag, inventory = load_documents_and_dag(input_dir, work_dir, Path(args.metadata))
    # Exact lookup uses validated resolved paths, never agent-supplied absolute paths.
    for document in by_document.values():
        for file in document["_checked_files"]:
            file["_absolute_path"] = str(resolve_input_file(input_dir, file["file_id"]))
    decisions = load_evidence(Path(args.evidence), claims)
    evaluated, uncertainties = evaluate_claims(input_dir, claims, decisions, by_document)
    assigned_files = {file_id for document in documents for file_id in document["files"]}
    unassigned_files = [file["file_id"] for file in inventory["files"] if file["file_id"] not in assigned_files]
    if unassigned_files:
        uncertainties.append("Inventory material not assigned to any immutable document: " + ", ".join(unassigned_files))
    matrix = make_version_matrix(documents, evaluated)
    matrix["case_id"] = case["case_id"]
    dag["case_id"] = case["case_id"]
    write_json(work_dir / "version-matrix.json", matrix)
    write_json(work_dir / "source-version-dag.json", dag)
    write_json(work_dir / "evidence-map-checked.json", {"case_id": case["case_id"], "claims": evaluated})
    render_svg(documents, dag, work_dir / "provenance.svg")
    sources = make_sources(documents)
    if any(claim["status"] == "insufficient_evidence" for claim in evaluated):
        final_status = "partial"
    elif any(claim["status"] == "partially_supported" for claim in evaluated):
        final_status = "partial"
    else:
        final_status = "complete"
    change_records = [
        {"sequence": 1, "phase": "initialize", "change": "Partial result contract was established before evidence analysis."},
        {"sequence": 2, "phase": "inventory", "change": f"Hashed {inventory['file_count']} material files; detected {inventory['duplicate_file_count']} duplicate copies."},
        {"sequence": 3, "phase": "metadata", "change": "Validated immutable document/version bindings and the source-version DAG."},
        {"sequence": 4, "phase": "evidence", "change": f"Checked exact quotes separately for {len(evaluated)} claims; no cross-document quote reuse."},
        {"sequence": 5, "phase": "finalize", "change": "Generated version matrix, provenance SVG, and version-scoped verdicts without pooling."},
    ]
    result: Dict[str, Any] = {
        "case_id": case["case_id"],
        "status": final_status,
        "sources": sources,
        "uncertainty": uncertainties + ["Verdicts are reviewed mappings with mechanical quote validation, not automatic semantic entailment."],
        "change_records": change_records,
    }
    apply_output_contract(result, case["output_contract"], evaluated, matrix, dag, inventory)
    validate_final_contract(result, case)
    output = Path(args.output)
    safe_output(output)
    write_json(output, result)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    init_parser = subparsers.add_parser("init", help="write an honest partial dynamic result skeleton first")
    init_parser.add_argument("--input", required=True)
    init_parser.add_argument("--output", required=True)
    init_parser.set_defaults(function=command_init)
    inventory_parser = subparsers.add_parser("inventory", help="hash actual input files and detect duplicate bytes")
    inventory_parser.add_argument("--input", required=True)
    inventory_parser.add_argument("--output", required=True)
    inventory_parser.set_defaults(function=command_inventory)
    validate_parser = subparsers.add_parser("validate", help="validate identities, hashes, evidence targets, and DAG")
    validate_parser.add_argument("--input", required=True)
    validate_parser.add_argument("--work", required=True)
    validate_parser.add_argument("--metadata", required=True)
    validate_parser.set_defaults(function=command_validate)
    final_parser = subparsers.add_parser("finalize", help="check quotes, calculate scoped verdicts, and render artifacts")
    final_parser.add_argument("--input", required=True)
    final_parser.add_argument("--work", required=True)
    final_parser.add_argument("--metadata", required=True)
    final_parser.add_argument("--evidence", required=True)
    final_parser.add_argument("--output", required=True)
    final_parser.set_defaults(function=command_finalize)
    return parser


def main(argv: Optional[List[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        args.function(args)
        return 0
    except ReconcileError as exc:
        print(f"RECONCILE_ERROR: {exc}", file=sys.stderr)
        return 1
    except OSError as exc:
        print(f"RECONCILE_ERROR: file operation failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
