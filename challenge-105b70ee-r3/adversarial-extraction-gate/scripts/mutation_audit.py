#!/usr/bin/env python3
"""Run isolated in-memory negative controls against the result validator."""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
from pathlib import Path
from typing import Any, Callable, Dict, List, Tuple

from result_contract import validate_result
import synthetic_fixture

SEMANTIC_LIMIT = (
    "Passing structural and mutation tests proves only these explicit validator behaviors "
    "on the synthetic fixture. It does not prove semantic correctness of this or any real extraction. "
    "An agent must perform decoy review against the original material."
)


def _pretty_bytes(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode("utf-8")


def _digest(value: Any) -> str:
    return hashlib.sha256(_pretty_bytes(value)).hexdigest()


def _both_fields(mutant: Dict[str, Any]) -> List[Dict[str, Any]]:
    fields = mutant["result"]["fields"]
    if "field_results" in mutant["result"]:
        mutant["result"]["field_results"] = copy.deepcopy(fields)
    return fields


def mutations() -> List[Tuple[str, str, str, Callable[[Dict[str, Any]], None]]]:
    """Return name, realistic failure, required rejection code, and mutator."""
    def first(mutant: Dict[str, Any]) -> Dict[str, Any]:
        return mutant["result"]["fields"][0]

    def wrong_subject(m: Dict[str, Any]) -> None:
        first(m)["subject"] = "SynB"

    def wrong_condition(m: Dict[str, Any]) -> None:
        first(m)["experimental_condition"] = "condition X"
        first(m)["condition"] = "condition X"

    def wrong_comparator(m: Dict[str, Any]) -> None:
        first(m)["comparator"] = "comparator X"

    def scalar_absent(m: Dict[str, Any]) -> None:
        first(m)["scalar"] = "99.9"

    def unit_altered(m: Dict[str, Any]) -> None:
        first(m)["units"] = "mg/mL"

    def statistic_dropped(m: Dict[str, Any]) -> None:
        first(m)["statistic"] = None

    def false_not_reported(m: Dict[str, Any]) -> None:
        first(m)["status"] = "not_reported"

    def unsupported_conflict(m: Dict[str, Any]) -> None:
        first(m)["status"] = "source_conflict"

    def duplicate_field(m: Dict[str, Any]) -> None:
        fields = _both_fields(m)
        fields.append(copy.deepcopy(fields[0]))
        _both_fields(m)

    def missing_field(m: Dict[str, Any]) -> None:
        fields = _both_fields(m)
        fields.pop()
        _both_fields(m)

    def quote_paragraph_mismatch(m: Dict[str, Any]) -> None:
        item = first(m)
        wrong_quote = "The investigators suggest SynA may alter downstream signaling under condition C."
        item["quote"] = wrong_quote
        item["evidence"]["quote"] = wrong_quote

    def hedged_claim_promoted(m: Dict[str, Any]) -> None:
        m["claims"][0]["kind"] = "explicit_conclusion"
        m["claims"][0]["statement"] = "SynA alters downstream signaling under condition C."

    def stale_condition_alias(m: Dict[str, Any]) -> None:
        first(m)["condition"] = "condition X"

    def stale_mirror(m: Dict[str, Any]) -> None:
        m["result"]["field_results"][0]["scalar"] = "88.8"

    return [
        ("wrong_subject", "Value is attributed to a different subject than requested.", "SUBJECT_MISMATCH", wrong_subject),
        ("wrong_condition", "The numeric result is detached from its requested condition.", "CONDITION_MISMATCH", wrong_condition),
        ("wrong_comparator", "The numeric result is attached to the wrong comparator.", "COMPARATOR_MISMATCH", wrong_comparator),
        ("scalar_absent_from_quote", "A plausible scalar is not present in the supporting quotation.", "SCALAR_ABSENT_FROM_QUOTE", scalar_absent),
        ("unit_altered", "The unit is changed after extraction.", "UNIT_NOT_IN_QUOTE", unit_altered),
        ("statistic_dropped", "A required statistic is omitted while the number remains.", "STATISTIC_DROPPED", statistic_dropped),
        ("false_not_reported", "A populated extraction is mislabeled as not_reported.", "VALUE_ON_NOT_REPORTED", false_not_reported),
        ("unsupported_source_conflict", "A conflict is declared without two conflicting evidence records.", "SOURCE_CONFLICT_REQUIRES_TWO_SOURCES", unsupported_conflict),
        ("duplicate_field", "One requested field_id is emitted twice.", "DUPLICATE_FIELD_ID", duplicate_field),
        ("missing_field", "A requested field_id is omitted.", "MISSING_FIELD_ID", missing_field),
        ("quotation_paragraph_mismatch", "A real quote from another paragraph is used with the original locator.", "QUOTE_NOT_IN_PARAGRAPH", quote_paragraph_mismatch),
        ("hedged_claim_promoted", "Suggest/may evidence is rewritten as an unhedged explicit conclusion.", "HEDGED_CLAIM_PROMOTED", hedged_claim_promoted),
        ("stale_condition_alias", "Condition alias is left inconsistent with experimental_condition.", "CONDITION_ALIAS_MISMATCH", stale_condition_alias),
        ("stale_mirrored_fields", "result.field_results silently diverges from result.fields.", "FIELD_RESULTS_NOT_MIRRORED", stale_mirror),
    ]


def run_audit(output_dir: Path = None) -> Dict[str, Any]:
    base = synthetic_fixture.valid_result()
    base_before = _pretty_bytes(base)
    base_digest = hashlib.sha256(base_before).hexdigest()
    target_data = synthetic_fixture.targets()
    corpus_data = synthetic_fixture.corpus()
    base_errors = validate_result(base, target_data, corpus_data, synthetic_fixture.CASE_ID)
    records = []
    corrupted: List[Tuple[str, Dict[str, Any]]] = []
    for name, description, expected_code, mutate in mutations():
        local_before = _pretty_bytes(base)
        mutant = copy.deepcopy(base)
        mutate(mutant)
        if name != "stale_mirrored_fields" and "field_results" in mutant["result"]:
            mutant["result"]["field_results"] = copy.deepcopy(mutant["result"]["fields"])
        local_base_after_mutation = _pretty_bytes(base)
        errors = validate_result(mutant, target_data, corpus_data, synthetic_fixture.CASE_ID)
        observed = sorted({error["code"] for error in errors})
        base_unchanged = local_before == local_base_after_mutation == base_before
        expected_rejection = any(error["code"] == expected_code for error in errors)
        passed = base_unchanged and not base_errors and expected_rejection
        records.append({
            "mutation": name,
            "failure_mode": description,
            "expected_rejection_code": expected_code,
            "actual_validator_rejected": bool(errors),
            "observed_error_codes": observed,
            "expected_code_observed": expected_rejection,
            "base_unchanged": base_unchanged,
            "pass": passed,
            "validation_errors": errors,
        })
        corrupted.append((name, mutant))
        if _pretty_bytes(base) != base_before:
            raise AssertionError("valid base result changed during mutation: %s" % name)
    final_base_unchanged = _pretty_bytes(base) == base_before
    overall = not base_errors and final_base_unchanged and all(record["pass"] for record in records)
    report = {
        "schema": "adversarial-mutation-audit/v1",
        "synthetic": True,
        "official_case": False,
        "benchmark_score": None,
        "case_id": synthetic_fixture.CASE_ID,
        "base": {
            "actual_pass": not base_errors,
            "validation_errors": base_errors,
            "sha256_before": base_digest,
            "sha256_after": _digest(base),
            "unchanged": final_base_unchanged,
        },
        "mutation_results": records,
        "observed_totals": {
            "mutations_run": len(records),
            "mutations_passed_expected_rejection": sum(1 for record in records if record["pass"]),
            "mutations_failed_expected_rejection": sum(1 for record in records if not record["pass"]),
        },
        "overall_actual_pass": overall,
        "semantic_limit": SEMANTIC_LIMIT,
    }
    if output_dir is not None:
        output_dir = Path(output_dir)
        corruption_dir = output_dir / "corrupted"
        corruption_dir.mkdir(parents=True, exist_ok=True)
        (output_dir / "valid-result.json").write_bytes(base_before)
        (output_dir / "target-fields.json").write_bytes(_pretty_bytes(target_data))
        (output_dir / "source-corpus.json").write_bytes(_pretty_bytes(corpus_data))
        (output_dir / "decoy-review.json").write_bytes(_pretty_bytes(synthetic_fixture.decoy_review()))
        (output_dir / "case.json").write_bytes(_pretty_bytes({"case_id": synthetic_fixture.CASE_ID, "synthetic": True}))
        for name, mutant in corrupted:
            (corruption_dir / (name + ".json")).write_bytes(_pretty_bytes(mutant))
        (output_dir / "audit-report.json").write_bytes(_pretty_bytes(report))
        delivered_digest = hashlib.sha256((output_dir / "valid-result.json").read_bytes()).hexdigest()
        if delivered_digest != base_digest or _pretty_bytes(base) != base_before:
            raise AssertionError("delivered valid base result was altered by mutation output")
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, help="Write synthetic base, audit, and corrupted copies here")
    args = parser.parse_args()
    report = run_audit(args.output_dir)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["overall_actual_pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
