#!/usr/bin/env python3
"""Assemble contract fields from an authored draft and its authored claims."""
from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List

from coverage_common import contract_fields, evidence_key


def aggregate_evidence(claims: Dict[str, Any]) -> List[Dict[str, Any]]:
    output: List[Dict[str, Any]] = []
    seen = set()
    for atom in claims.get("task_atoms") or []:
        if not isinstance(atom, dict):
            continue
        for claim in atom.get("claims") or []:
            if not isinstance(claim, dict):
                continue
            for evidence in claim.get("evidence") or []:
                if not isinstance(evidence, dict):
                    continue
                key = (atom.get("atom_id"), claim.get("claim_id")) + evidence_key(evidence) + (
                    str(evidence.get("relation", "")),)
                if key in seen:
                    continue
                seen.add(key)
                record = dict(evidence)
                record["atom_id"] = atom.get("atom_id")
                record["claim_id"] = claim.get("claim_id")
                record["origin"] = claim.get("origin")
                output.append(record)
    for contradiction in claims.get("contradictions") or []:
        if not isinstance(contradiction, dict):
            continue
        for evidence in contradiction.get("resolution_evidence") or []:
            if not isinstance(evidence, dict):
                continue
            key = ("contradiction", contradiction.get("contradiction_id")) + evidence_key(evidence) + (
                str(evidence.get("relation", "supports")),)
            if key in seen:
                continue
            seen.add(key)
            record = dict(evidence)
            record["contradiction_id"] = contradiction.get("contradiction_id")
            output.append(record)
    return output


def assemble_result(case: Dict[str, Any], draft: Dict[str, Any], claims: Dict[str, Any],
                    status: str, issues: List[Dict[str, Any]], work: Path) -> Dict[str, Any]:
    """Copy only declared draft fields, then populate system-generated metadata.

    In particular, this function never creates or repairs an `answers` value.
    """
    result: Dict[str, Any] = {}
    for field in contract_fields(case):
        if field in draft:
            result[field] = draft[field]
    result["case_id"] = case.get("case_id")
    result["status"] = status

    if "evidence" in contract_fields(case):
        result["evidence"] = aggregate_evidence(claims)
    if "uncertainty" in contract_fields(case):
        uncertainty = result.get("uncertainty")
        if isinstance(uncertainty, dict):
            named: List[str] = []
            for value in claims.get("missing_objects") or []:
                if isinstance(value, str) and value and value not in named:
                    named.append(value)
            for atom in claims.get("task_atoms") or []:
                if not isinstance(atom, dict):
                    continue
                for claim in atom.get("claims") or []:
                    if not isinstance(claim, dict):
                        continue
                    for value in (claim.get("missing_objects") or []):
                        if isinstance(value, str) and value and value not in named:
                            named.append(value)
            if named:
                uncertainty["missing_objects"] = named
            if issues:
                uncertainty["adjudication_gaps"] = issues
            result["uncertainty"] = uncertainty
    if "artifacts" in contract_fields(case) and isinstance(result.get("artifacts"), dict):
        result["artifacts"].update({
            "source_excerpt_ledger": str(work / "source_excerpts.json"),
            "claims_ledger": str(work / "claims.json"),
            "adjudication_report": str(work / "adjudication.json"),
            "change_log": str(work / "change_log.json"),
        })
    return result
