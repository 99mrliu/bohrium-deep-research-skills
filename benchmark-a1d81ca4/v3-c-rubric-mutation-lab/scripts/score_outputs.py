#!/usr/bin/env python3
"""Score the four required raw outputs, with strict identity and size gates."""

import argparse
import hashlib
import sys

from score_engine import InputError, dump_json, load_json, score_candidate


def raw_ref(text):
    return "sha256:" + hashlib.sha256(text.encode("utf-8")).hexdigest()


def load_required_items(bank):
    if not isinstance(bank, dict) or not isinstance(bank.get("items"), list):
        raise InputError("item bank must be an object with an items array")
    if len(bank["items"]) != 4:
        raise InputError("score_outputs requires exactly four items")
    result = {}
    for item in bank["items"]:
        if not isinstance(item, dict) or not isinstance(item.get("item_id"), str):
            raise InputError("each item requires a string item_id")
        item_id = item["item_id"]
        if item_id in result:
            raise InputError("duplicate item_id in bank: " + item_id)
        if item.get("required") is not True:
            raise InputError("all four bank items must have required=true")
        result[item_id] = item
    return result


def score_outputs(bank, candidate_file, max_chars, allow_empty, allow_overlimit):
    items = load_required_items(bank)
    if not isinstance(candidate_file, dict) or not isinstance(candidate_file.get("outputs"), list):
        raise InputError("candidate file must contain an outputs array")
    seen = {}
    for index, record in enumerate(candidate_file["outputs"]):
        path = "outputs[%d]" % index
        if not isinstance(record, dict) or set(record) != {"item_id", "raw_output"}:
            raise InputError(path + " must contain exactly item_id and raw_output")
        item_id = record["item_id"]
        if not isinstance(item_id, str) or not item_id:
            raise InputError(path + ".item_id must be a nonempty string")
        if item_id in seen:
            raise InputError("duplicate candidate item_id: " + item_id)
        if item_id not in items:
            raise InputError("unknown candidate item_id: " + item_id)
        if not isinstance(record["raw_output"], str):
            raise InputError(path + ".raw_output must be a string")
        seen[item_id] = record["raw_output"]
    missing = sorted(set(items) - set(seen))
    extra = sorted(set(seen) - set(items))
    if missing or extra:
        raise InputError("required ID mismatch; missing=%s unknown=%s" % (missing, extra))

    records = []
    for item_id in sorted(items):
        text = seen[item_id]
        problems = []
        if not text.strip():
            if not allow_empty:
                raise InputError("empty output refused for %s (use --allow-empty to score 0)" % item_id)
            problems.append("empty_output")
        if len(text) > max_chars:
            if not allow_overlimit:
                raise InputError(
                    "output overlimit for %s: %d > %d chars (use --max-chars or --allow-overlimit)" %
                    (item_id, len(text), max_chars))
            problems.append("overlimit_output")
        scored = score_candidate(items[item_id], text)
        taxonomy = list(problems)
        if scored["score"] == 0 and "empty_output" not in taxonomy:
            taxonomy.append("zero_score")
        for check in scored["checks"]:
            if not check["passed"]:
                category = "failed_predicate:" + check["category"]
                if category not in taxonomy:
                    taxonomy.append(category)
        if scored["score"] == 1:
            taxonomy.append("partial_credit")
        records.append({
            "item_id": item_id,
            "required": True,
            "raw_output": text,
            "raw_output_ref": raw_ref(text),
            "output_char_count": len(text),
            "rubric_hash": scored["rubric_hash"],
            "score": scored["score"],
            "checks": scored["checks"],
            "score_band": scored["score_band"],
            "score_reason": scored["score_reason"],
            "failure_taxonomy": taxonomy,
        })
    total = sum(record["score"] for record in records)
    denominator = len(records)
    maximum = 2 * denominator
    if denominator != 4 or not 0 <= total <= maximum:
        raise InputError("internal rollup inconsistency")
    return {
        "schema_version": "1.0",
        "status": "scored",
        "policy": {
            "max_chars": max_chars, "allow_empty": allow_empty,
            "allow_overlimit": allow_overlimit,
        },
        "records": records,
        "rollup": {
            "score_total": total,
            "max_score": maximum,
            "scored_required_count": denominator,
            "required_denominator": denominator,
            "normalization_denominator": maximum,
            "normalized_score": total / maximum,
            "formula": "sum(score of scored required four) / (2 * scored required count)",
        },
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--items", required=True)
    parser.add_argument("--candidate-outputs", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--max-chars", type=int, default=4000)
    parser.add_argument("--allow-empty", action="store_true")
    parser.add_argument("--allow-overlimit", action="store_true")
    args = parser.parse_args(argv)
    if args.max_chars < 0:
        sys.stderr.write("score_outputs: --max-chars must be nonnegative\n")
        return 2
    try:
        bank = load_json(args.items)
        candidates = load_json(args.candidate_outputs)
        report = score_outputs(bank, candidates, args.max_chars,
                               args.allow_empty, args.allow_overlimit)
        dump_json(report, args.output)
    except InputError as exc:
        sys.stderr.write("score_outputs: %s\n" % exc)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
