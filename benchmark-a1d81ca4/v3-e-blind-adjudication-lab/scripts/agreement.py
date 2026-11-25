#!/usr/bin/env python3
"""Compare automatic and final scores, emitting descriptive small-N diagnostics and probes."""

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

CATEGORIES = (0, 1, 2)
SCHEMA_VERSION = "1.0"
MINIMUM_KAPPA_ITEMS = 4


class InputError(ValueError):
    pass


def load_json(path):
    try:
        with Path(path).open("r", encoding="utf-8") as handle:
            return json.load(handle)
    except (OSError, json.JSONDecodeError) as exc:
        raise InputError(f"Cannot read valid JSON from {path}: {exc}") from exc


def dump_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("w", encoding="utf-8") as handle:
        json.dump(value, handle, ensure_ascii=False, indent=2, sort_keys=True)
        handle.write("\n")
    temporary.replace(path)


def valid_score(value):
    return isinstance(value, int) and not isinstance(value, bool) and value in CATEGORIES


def unique_scores(document):
    if not isinstance(document, dict) or not isinstance(document.get("scores"), list):
        raise InputError("Automatic score file must contain a scores list")
    result = {}
    for row in document["scores"]:
        item_id = row.get("item_id") if isinstance(row, dict) else None
        if not isinstance(item_id, str) or not item_id:
            raise InputError("Every automatic score requires an item_id")
        if item_id in result:
            raise InputError(f"Duplicate automatic score for {item_id}")
        if not valid_score(row.get("score")):
            raise InputError(f"Automatic score for {item_id} must be 0, 1, or 2")
        result[item_id] = row["score"]
    return result


def classify_failure(auto_score, final_score, item):
    verdicts = item.get("human_verdicts", [])
    dimensions = ("correctness", "completeness", "evidence")
    means = {}
    for dimension in dimensions:
        values = [v["judgments"][dimension] for v in verdicts]
        means[dimension] = sum(values) / len(values) if values else None
    weakest = min(dimensions, key=lambda d: means[d] if means[d] is not None else -1)
    if auto_score > final_score:
        category = {
            "evidence": "AUTO_OVERCREDIT_EVIDENCE",
            "completeness": "AUTO_OVERCREDIT_COMPLETENESS",
            "correctness": "AUTO_OVERCREDIT_CORRECTNESS",
        }[weakest]
        expected = f"Lower the unsupported automatic award from {auto_score} to the source-adjudicated {final_score}, applying the {weakest} rubric."
    else:
        category = {
            "evidence": "AUTO_UNDERCREDIT_EVIDENCE",
            "completeness": "AUTO_UNDERCREDIT_COMPLETENESS",
            "correctness": "AUTO_UNDERCREDIT_CORRECTNESS",
        }[weakest]
        expected = f"Recognize source-supported content and calibrate the automatic award from {auto_score} toward {final_score}, applying the {weakest} rubric."
    return category, weakest, means, expected


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--auto-scores", required=True)
    parser.add_argument("--adjudication", required=True)
    parser.add_argument("--output-dir", required=True)
    args = parser.parse_args()

    try:
        automatic_doc = load_json(args.auto_scores)
        automatic = unique_scores(automatic_doc)
        adjudication = load_json(args.adjudication)
        items = adjudication.get("per_item")
        if not isinstance(items, list) or len(items) != 4:
            raise InputError("Adjudication must contain exactly four per_item records")
        item_ids = []
        for item in items:
            item_id = item.get("item_id")
            if not isinstance(item_id, str) or item_id in item_ids:
                raise InputError("Adjudication has a missing or duplicate item_id")
            item_ids.append(item_id)
            if item.get("status") == "resolved" and not valid_score(item.get("final_score")):
                raise InputError(f"Resolved item {item_id} lacks valid final_score")
        missing_auto = sorted(set(item_ids) - set(automatic))
        extra_auto = sorted(set(automatic) - set(item_ids))
        if missing_auto or extra_auto:
            raise InputError(f"Automatic score ID mismatch; missing={missing_auto}, extra={extra_auto}")

        per_item = []
        failures = []
        probes = []
        unresolved_missing = []
        matrix = {str(auto): {str(final): 0 for final in CATEGORIES} for auto in CATEGORIES}
        for item in items:
            item_id = item["item_id"]
            final = item.get("final_score") if item.get("status") == "resolved" else None
            auto = automatic[item_id]
            comparable = valid_score(final)
            match = auto == final if comparable else None
            row = {
                "item_id": item_id,
                "automatic_score": auto,
                "adjudicated_final_score": final,
                "comparison_status": "comparable" if comparable else "unresolved_missing",
                "raw_agreement_match": match,
                "unresolved_reasons": item.get("unresolved_reasons", []) if not comparable else [],
            }
            per_item.append(row)
            if not comparable:
                unresolved_missing.append({
                    "item_id": item_id,
                    "automatic_score": auto,
                    "final_score": None,
                    "reason": "Unresolved final score is excluded from every agreement denominator."
                })
                continue
            matrix[str(auto)][str(final)] += 1
            if not match:
                category, weakest, means, expected = classify_failure(auto, final, item)
                failure_id = f"FAIL-{item_id}-AUTO{auto}-FINAL{final}"
                evidence = []
                basis_type = "unanimous_binary_source_review"
                basis_rationale = "Unanimous binary human verdicts supplied the operational final label; this concordance is not itself proof of truth."
                if isinstance(item.get("adjudication"), dict):
                    basis_type = "explicit_source_adjudication"
                    evidence = item["adjudication"].get("source_refs") or []
                    basis_rationale = item["adjudication"].get("rationale")
                if not evidence:
                    seen_refs = set()
                    review_comments = []
                    for verdict in item.get("human_verdicts", []):
                        review_comments.append(verdict.get("comments", ""))
                        for ref in verdict.get("source_refs", []):
                            key = (ref.get("source_id"), ref.get("locator"))
                            if key not in seen_refs:
                                seen_refs.add(key)
                                evidence.append({
                                    "source_id": key[0],
                                    "locator": key[1],
                                    "evidence_note": f"Independent review basis: {verdict.get('comments', '')}",
                                })
                    if not isinstance(item.get("adjudication"), dict):
                        basis_rationale = " | ".join(review_comments)
                failure = {
                    "failure_id": failure_id,
                    "item_id": item_id,
                    "taxonomy_version": "1.0",
                    "failure_category": category,
                    "observed_behavior": f"Automatic score {auto} differs from source-adjudicated final score {final}; weakest human dimension: {weakest}.",
                    "expected_behavior": expected,
                    "automatic_score": auto,
                    "adjudicated_final_score": final,
                    "human_dimension_means_descriptive": means,
                    "evidence_refs": evidence,
                    "adjudication_rationale": (item.get("adjudication") or {}).get("rationale"),
                    "final_score_basis": {
                        "type": basis_type,
                        "rationale": basis_rationale,
                        "evidence_refs": evidence,
                    },
                    "fix": {
                        "owner_surface": "next-version automatic scoring prompt/parser and targeted regression set",
                        "required_change": expected,
                        "not_a_fix": "Treating reviewer agreement or kappa as truth, or editing the final score to match automation."
                    },
                    "status": "open",
                    "search_keys": [category, item_id, weakest, "automatic-final-mismatch"],
                }
                probe = {
                    "probe_id": f"PROBE-{item_id}-RETEST",
                    "source_failure_ids": [failure_id],
                    "retest_item_ids": [item_id],
                    "probe_type": "source-conditioned targeted regression plus one held-out variant",
                    "reason": f"Reproduce {category}: automation awarded {auto}, final source adjudication awarded {final}.",
                    "source_evidence_refs": evidence,
                    "input_change": "Preserve the original item as a regression and create one independently reviewed variant that changes the surface wording but preserves the decisive evidence and rubric dimension.",
                    "expected_fix": expected,
                    "pass_condition": f"Automatic output is reproducible and the next-version score is {final} with an explicit {weakest} rationale grounded in the cited locator; unresolved remains a failure, not agreement.",
                    "expected_failure_if_unfixed": f"The scorer repeats automatic={auto} instead of final={final}, or gives a score without source-specific support.",
                    "blinding_requirement": "Review the held-out variant without exposing the old automatic score or adjudicator identity.",
                    "status": "planned",
                }
                failures.append(failure)
                probes.append(probe)

        comparable_rows = [row for row in per_item if row["comparison_status"] == "comparable"]
        n = len(comparable_rows)
        matches = sum(1 for row in comparable_rows if row["raw_agreement_match"])
        raw_agreement_value = matches / n if n else None
        auto_counts = Counter(row["automatic_score"] for row in comparable_rows)
        final_counts = Counter(row["adjudicated_final_score"] for row in comparable_rows)
        auto_support = sorted(auto_counts)
        final_support = sorted(final_counts)
        pe_terms = []
        expected = 0.0
        if n:
            for category in CATEGORIES:
                auto_probability = auto_counts[category] / n
                final_probability = final_counts[category] / n
                product = auto_probability * final_probability
                expected += product
                pe_terms.append({
                    "category": category,
                    "automatic_count": auto_counts[category],
                    "final_count": final_counts[category],
                    "automatic_probability": auto_probability,
                    "final_probability": final_probability,
                    "count_product_numerator": auto_counts[category] * final_counts[category],
                    "product": product,
                })
        observed = raw_agreement_value if raw_agreement_value is not None else 0.0
        denominator = 1.0 - expected if n else None
        support_reasons = []
        if n < MINIMUM_KAPPA_ITEMS:
            support_reasons.append(f"Need at least {MINIMUM_KAPPA_ITEMS} comparable items; have {n}.")
        if len(auto_support) < 2:
            support_reasons.append("Automatic scores occupy fewer than two categories.")
        if len(final_support) < 2:
            support_reasons.append("Final scores occupy fewer than two categories.")
        if denominator == 0:
            support_reasons.append("1 - pe equals zero, so the kappa denominator is undefined.")
        kappa_computable = not support_reasons
        kappa_value = (observed - expected) / denominator if kappa_computable else None
        kappa = {
            "status": "computed_descriptive_only" if kappa_computable else "not_computed_insufficient_support",
            "value": kappa_value,
            "formula": "kappa = (po - pe) / (1 - pe)",
            "po": {
                "value": raw_agreement_value,
                "numerator": matches,
                "denominator": n,
                "exact_expression": f"{matches}/{n}" if n else "undefined: 0/0",
            },
            "pe": {
                "value": expected if n else None,
                "formula": "sum_c(automatic_count_c/n * final_count_c/n), c in {0,1,2}",
                "exact_sum_count_expression": " + ".join(f"({term['automatic_count']}*{term['final_count']})/{n**2}" for term in pe_terms) if n else None,
                "terms": pe_terms,
                "denominator_for_each_count_product": n * n if n else None,
            },
            "numerator_po_minus_pe": (observed - expected) if n else None,
            "denominator_one_minus_pe": denominator,
            "category_support": {
                "minimum_comparable_items": MINIMUM_KAPPA_ITEMS,
                "comparable_n": n,
                "automatic_categories_observed": auto_support,
                "final_categories_observed": final_support,
                "reasons_not_computed": support_reasons,
            },
            "interpretation_limit": "Even when arithmetically defined, four synthetic items are a low-N descriptive diagnostic, not a reliability or truth claim.",
        }
        success = adjudication.get("status") == "success" and not unresolved_missing
        agreement = {
            "schema_version": SCHEMA_VERSION,
            "status": "success" if success else "partial",
            "case_id": adjudication.get("case_id"),
            "comparison_policy": {
                "scale_calibration": "Automatic and final scores use the same unweighted ordinal labels {0:incorrect, 1:partial, 2:correct}; no rescaling or imputation is performed.",
                "resolution_rule": "Only source-adjudicated resolved finals are comparable; unresolved/missing finals remain visible and are excluded from denominators.",
                "descriptive_label": "SYNTHETIC LOW-N DESCRIPTIVE COMPARISON; no inferential or DSH performance claim.",
                "truth_limit": "Agreement and kappa summarize label concordance only. Neither reviewer consensus nor kappa proves scientific truth."
            },
            "counts": {
                "total_items": len(items),
                "comparable_items": n,
                "unresolved_or_missing_finals": len(unresolved_missing),
                "matches": matches,
                "mismatches": sum(1 for row in comparable_rows if not row["raw_agreement_match"]),
            },
            "raw_agreement": {
                "value": raw_agreement_value,
                "numerator": matches,
                "denominator": n,
                "formula": "raw agreement = count(automatic_score == adjudicated_final_score) / count(comparable resolved items)",
                "exact_expression": f"{matches}/{n}" if n else "undefined: no comparable items",
            },
            "cohen_kappa_unweighted": kappa,
            "confusion_matrix": {
                "row_label": "automatic_score",
                "column_label": "adjudicated_final_score",
                "categories": list(CATEGORIES),
                "counts": matrix,
                "row_totals": {str(category): sum(matrix[str(category)].values()) for category in CATEGORIES},
                "column_totals": {str(category): sum(matrix[str(auto)][str(category)] for auto in CATEGORIES) for category in CATEGORIES},
            },
            "per_item": per_item,
            "unresolved_missing": unresolved_missing,
            "failure_ids": [failure["failure_id"] for failure in failures],
            "targeted_probe_ids": [probe["probe_id"] for probe in probes],
        }
        failure_doc = {
            "schema_version": SCHEMA_VERSION,
            "case_id": adjudication.get("case_id"),
            "status": "success" if success else "partial",
            "taxonomy_version": "1.0",
            "description": "Searchable automatic-versus-final mismatch examples; these diagnose scoring behavior rather than establish general model quality.",
            "failures": failures,
        }
        probe_doc = {
            "schema_version": SCHEMA_VERSION,
            "case_id": adjudication.get("case_id"),
            "status": "success" if success else "partial",
            "probes": probes,
            "retest_policy": "Retain original item IDs in retest_item_ids, add held-out source-conditioned variants, blind old scores, and compare expected fix against observed behavior."
        }
        output_dir = Path(args.output_dir)
        dump_json(output_dir / "agreement.json", agreement)
        dump_json(output_dir / "failures.json", failure_doc)
        dump_json(output_dir / "targeted_probes.json", probe_doc)
        print(json.dumps({"status": agreement["status"], "raw_agreement": raw_agreement_value, "kappa_status": kappa["status"], "failures": len(failures), "probes": len(probes)}, ensure_ascii=False))
        return 0
    except InputError as exc:
        print(f"agreement.py: INPUT ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
