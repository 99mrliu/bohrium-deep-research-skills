#!/usr/bin/env python3
"""Execute independent, human-classified probe suites for exactly four items."""

import argparse
import hashlib
import sys

from score_engine import InputError, canonical_hash, dump_json, load_json, score_candidate


REQUIRED_PROBE_CLASSES = (
    "exact",
    "paraphrase",
    "partial",
    "wrong_entity",
    "wrong_numeric",
    "wrong_value",
    "wrong_unit",
    "omitted_condition",
    "negation_reversal",
    "empty",
    "unsupported",
)
UNREPORTED_CLASS = "legitimate_unreported"
VALID_CLASSES = set(REQUIRED_PROBE_CLASSES) | {UNREPORTED_CLASS}


def raw_ref(text):
    return "sha256:" + hashlib.sha256(text.encode("utf-8")).hexdigest()


def validate_bank(bank):
    if not isinstance(bank, dict) or not isinstance(bank.get("items"), list):
        raise InputError("item bank must be an object with an items array")
    items = bank["items"]
    if len(items) != 4:
        raise InputError("exactly four items are required; found %d" % len(items))
    ids = []
    for item in items:
        if not isinstance(item, dict) or not isinstance(item.get("item_id"), str):
            raise InputError("every item requires a string item_id")
        ids.append(item["item_id"])
        if not isinstance(item.get("probes"), list) or not item["probes"]:
            raise InputError("item %s requires a nonempty probes array" % item["item_id"])
    if len(set(ids)) != 4:
        raise InputError("item_id values must be unique")
    return items


def execute_bank(bank):
    report = {
        "schema_version": "1.0",
        "status": "failed",
        "synthetic_only": bank.get("synthetic_only", False) if isinstance(bank, dict) else False,
        "expected_classifications_are_independent": True,
        "required_probe_classes": list(REQUIRED_PROBE_CLASSES),
        "summary": {},
        "validation_errors": [],
        "items": [],
    }
    errors = report["validation_errors"]
    try:
        items = validate_bank(bank)
    except InputError as exc:
        errors.append(str(exc))
        report["summary"] = {"item_count": 0, "probe_count": 0,
                             "disagreement_count": 0, "passed": False}
        return report

    all_probe_ids = set()
    total_disagreements = 0
    total_probes = 0
    for item in items:
        item_id = item["item_id"]
        predicates = item.get("rubric", {}).get("predicates", [])
        predicate_ids = [entry.get("id") for entry in predicates
                         if isinstance(entry, dict)]
        item_record = {
            "item_id": item_id,
            "rubric_hash": canonical_hash(item.get("rubric")),
            "probe_results": [],
            "missing_classes": [],
            "unexpected_classes": [],
            "passed": False,
        }
        probes = item["probes"]
        local_ids = set()
        classes = []
        for index, probe in enumerate(probes):
            total_probes += 1
            path = "%s.probes[%d]" % (item_id, index)
            if not isinstance(probe, dict):
                errors.append(path + " must be an object")
                continue
            required = {"probe_id", "probe_class", "raw_output", "expected_score",
                        "expected_predicates", "rationale"}
            if set(probe) != required:
                errors.append("%s keys must be exactly %s" % (path, sorted(required)))
                continue
            probe_id = probe["probe_id"]
            probe_class = probe["probe_class"]
            if not isinstance(probe_id, str) or not probe_id:
                errors.append(path + ".probe_id must be a nonempty string")
                continue
            if probe_id in local_ids or probe_id in all_probe_ids:
                errors.append("duplicate probe_id: " + probe_id)
            local_ids.add(probe_id)
            all_probe_ids.add(probe_id)
            classes.append(probe_class)
            if probe_class not in VALID_CLASSES:
                errors.append("%s has unknown probe_class %s" % (path, probe_class))
            if not isinstance(probe["raw_output"], str):
                errors.append(path + ".raw_output must be a string (empty is allowed)")
                continue
            expected_score = probe["expected_score"]
            if isinstance(expected_score, bool) or expected_score not in (0, 1, 2):
                errors.append(path + ".expected_score must be integer 0, 1, or 2")
                continue
            expected_predicates = probe["expected_predicates"]
            if not isinstance(expected_predicates, dict):
                errors.append(path + ".expected_predicates must be an object")
                continue
            if set(expected_predicates) != set(predicate_ids):
                errors.append("%s expected_predicates must cover exactly %s" %
                              (path, sorted(predicate_ids)))
                continue
            if any(not isinstance(value, bool) for value in expected_predicates.values()):
                errors.append(path + " expected predicate values must all be Boolean")
                continue
            if not isinstance(probe["rationale"], str) or not probe["rationale"]:
                errors.append(path + ".rationale must explain the independent label")
                continue
            try:
                actual = score_candidate(item, probe["raw_output"])
            except InputError as exc:
                errors.append("%s scoring error: %s" % (path, exc))
                continue
            actual_predicates = {check["id"]: check["passed"]
                                 for check in actual["checks"]}
            predicate_disagreements = {}
            for predicate_id in sorted(expected_predicates):
                if actual_predicates[predicate_id] != expected_predicates[predicate_id]:
                    predicate_disagreements[predicate_id] = {
                        "expected": expected_predicates[predicate_id],
                        "actual": actual_predicates[predicate_id],
                    }
            score_agrees = actual["score"] == expected_score
            passed = score_agrees and not predicate_disagreements
            if not passed:
                total_disagreements += 1
            item_record["probe_results"].append({
                "probe_id": probe_id,
                "probe_class": probe_class,
                "rationale": probe["rationale"],
                "raw_output": probe["raw_output"],
                "raw_output_ref": raw_ref(probe["raw_output"]),
                "expected_score": expected_score,
                "actual_score": actual["score"],
                "expected_predicates": expected_predicates,
                "actual_predicates": actual_predicates,
                "predicate_disagreements": predicate_disagreements,
                "actual_checks": actual["checks"],
                "actual_score_reason": actual["score_reason"],
                "passed": passed,
            })
        required = set(REQUIRED_PROBE_CLASSES)
        if item.get("requires_unreported_probe") is True:
            required.add(UNREPORTED_CLASS)
        item_record["missing_classes"] = sorted(required - set(classes))
        item_record["unexpected_classes"] = sorted(set(classes) - VALID_CLASSES)
        for missing in item_record["missing_classes"]:
            errors.append("%s missing required probe class %s" % (item_id, missing))
        item_record["passed"] = not item_record["missing_classes"] and all(
            probe["passed"] for probe in item_record["probe_results"]
        ) and len(item_record["probe_results"]) == len(probes)
        report["items"].append(item_record)
    # Validation errors are disagreements with the probe contract even when all
    # executable expected scores happen to match.
    passed = not errors and total_disagreements == 0 and all(
        item["passed"] for item in report["items"])
    report["status"] = "passed" if passed else "failed"
    report["summary"] = {
        "item_count": len(report["items"]), "probe_count": total_probes,
        "disagreement_count": total_disagreements,
        "validation_error_count": len(errors), "passed": passed,
    }
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--items", required=True, help="four-item bank containing probes")
    parser.add_argument("--output", required=True)
    args = parser.parse_args(argv)
    try:
        bank = load_json(args.items)
        report = execute_bank(bank)
        dump_json(report, args.output)
    except InputError as exc:
        sys.stderr.write("mutation_check: %s\n" % exc)
        return 2
    if report["status"] != "passed":
        sys.stderr.write("mutation_check: probe disagreements or suite validation failed\n")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
