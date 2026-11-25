#!/usr/bin/env python3
"""Gate a draft on contract checks, mutation controls, and explicit decoy review."""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
from pathlib import Path
from typing import Any, Dict, List, Mapping, Sequence

from mutation_audit import SEMANTIC_LIMIT, run_audit
from result_contract import InputDataError, load_json, parse_targets, validate_result
from scaffold import atomic_write, dumps


def _review_errors(review: Any, case_id: str, targets: Sequence[Mapping[str, Any]], claims: Any) -> List[Dict[str, str]]:
    errors = []
    if not isinstance(review, dict):
        return [{"code": "REVIEW_NOT_OBJECT", "message": "decoy review must be an object"}]
    if review.get("case_id") != case_id:
        errors.append({"code": "REVIEW_CASE_MISMATCH", "message": "review case_id must match the candidate"})
    if review.get("semantic_correctness_not_proven") is not True:
        errors.append({"code": "REVIEW_LIMIT_NOT_ACKNOWLEDGED", "message": "semantic_correctness_not_proven must be true"})
    if not isinstance(review.get("reviewer"), str) or not review["reviewer"].strip():
        errors.append({"code": "REVIEWER_REQUIRED", "message": "identify the agent/person performing decoy review"})
    field_reviews = review.get("field_reviews")
    if not isinstance(field_reviews, list):
        errors.append({"code": "FIELD_REVIEWS_REQUIRED", "message": "field_reviews must be an array"})
        field_reviews = []
    by_field: Dict[str, int] = {}
    for item in field_reviews:
        if not isinstance(item, dict) or not isinstance(item.get("field_id"), str):
            errors.append({"code": "INVALID_FIELD_REVIEW", "message": "each field review needs field_id"})
            continue
        field_id = item["field_id"]
        by_field[field_id] = by_field.get(field_id, 0) + 1
        if item.get("verdict") != "pass":
            errors.append({"code": "FIELD_NEEDS_REVISION", "message": "decoy review is not pass for %s" % field_id})
        if not isinstance(item.get("decoys_checked"), list) or not item["decoys_checked"]:
            errors.append({"code": "DECOYS_NOT_RECORDED", "message": "record concrete decoys checked for %s" % field_id})
        if not isinstance(item.get("observation"), str) or not item["observation"].strip():
            errors.append({"code": "REVIEW_OBSERVATION_REQUIRED", "message": "record source-based observation for %s" % field_id})
    for target in targets:
        field_id = target["field_id"]
        if by_field.get(field_id, 0) != 1:
            errors.append({"code": "FIELD_REVIEW_CARDINALITY", "message": "need exactly one review for %s" % field_id})
    for field_id in by_field:
        if field_id not in {target["field_id"] for target in targets}:
            errors.append({"code": "UNREQUESTED_FIELD_REVIEW", "message": "unrequested reviewed field: %s" % field_id})

    claim_reviews = review.get("claim_reviews", [])
    if not isinstance(claim_reviews, list):
        errors.append({"code": "CLAIM_REVIEWS_NOT_ARRAY", "message": "claim_reviews must be an array"})
        claim_reviews = []
    reviewed_claims = [item.get("claim_id") for item in claim_reviews if isinstance(item, dict)]
    for item in claim_reviews:
        if not isinstance(item, dict) or item.get("verdict") != "pass" or not item.get("decoys_checked") or not item.get("observation"):
            errors.append({"code": "CLAIM_NEEDS_REVISION", "message": "every claim review needs pass, decoys_checked, and observation"})
    for claim in claims if isinstance(claims, list) else []:
        claim_id = claim.get("claim_id") if isinstance(claim, dict) else None
        if not isinstance(claim_id, str) or reviewed_claims.count(claim_id) != 1:
            errors.append({"code": "CLAIM_REVIEW_CARDINALITY", "message": "each claim needs a unique claim_id and exactly one review"})
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--case", type=Path, default=Path("/input/case.json"))
    parser.add_argument("--targets", type=Path, default=Path("/input/target-fields.json"))
    parser.add_argument("--corpus", type=Path, default=Path("/app/work/source-corpus.json"))
    parser.add_argument("--draft", type=Path, default=Path("/app/work/draft-result.json"))
    parser.add_argument("--review", type=Path, default=Path("/app/work/decoy-review.json"))
    parser.add_argument("--output", type=Path, default=Path("/app/output"))
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    final_path = args.output / "result.json"
    prior_bytes = final_path.read_bytes() if final_path.exists() else None
    try:
        case = load_json(args.case)
        if not isinstance(case, dict) or not isinstance(case.get("case_id"), str):
            raise InputDataError("case.json needs a string case_id")
        targets = parse_targets(load_json(args.targets))
        corpus = load_json(args.corpus)
        draft = load_json(args.draft)
        review = load_json(args.review)
        contract_errors = validate_result(draft, targets, corpus, case["case_id"])
        review_errors = _review_errors(review, case["case_id"], targets, draft.get("claims") if isinstance(draft, dict) else None)
    except (InputDataError, OSError, UnicodeError, ValueError) as exc:
        report = {"actual_pass": False, "exit_status": 2, "input_error": str(exc), "final_result_written": False, "semantic_limit": SEMANTIC_LIMIT}
        atomic_write(args.output / "finalization-report.json", dumps(report))
        print(dumps(report))
        return 2

    mutation_report = run_audit()
    atomic_write(args.output / "mutation-audit.json", dumps(mutation_report))
    errors = copy.deepcopy(contract_errors) + copy.deepcopy(review_errors)
    if not mutation_report["overall_actual_pass"]:
        errors.append({"code": "MUTATION_SELF_TEST_FAILED", "message": "validator negative controls did not all behave as specified"})
    accepted = not errors
    if accepted:
        final_bytes = (json.dumps(draft, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode("utf-8")
        temporary = final_path.with_name("result.json.tmp")
        temporary.write_bytes(final_bytes)
        temporary.replace(final_path)
        atomic_write(args.output / "decoy-review.json", dumps(review))
    else:
        if prior_bytes is None:
            if final_path.exists():
                raise RuntimeError("refused to remove an unexpected result file")
        elif not final_path.exists() or final_path.read_bytes() != prior_bytes:
            raise RuntimeError("existing result changed despite finalization rejection")
    report = {
        "actual_pass": accepted,
        "exit_status": 0 if accepted else 1,
        "candidate_sha256": hashlib.sha256(dumps(draft).encode("utf-8")).hexdigest(),
        "contract_errors": contract_errors,
        "decoy_review_errors": review_errors,
        "mutation_controls_actual_pass": mutation_report["overall_actual_pass"],
        "final_result_written": accepted,
        "rejected_candidate_preserved_only_in_work": not accepted,
        "existing_output_unchanged_on_rejection": not accepted,
        "semantic_correctness_proven": False,
        "semantic_limit": SEMANTIC_LIMIT,
    }
    atomic_write(args.output / "finalization-report.json", dumps(report))
    print(dumps(report))
    return 0 if accepted else 1


if __name__ == "__main__":
    raise SystemExit(main())
