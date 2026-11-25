#!/usr/bin/env python3
"""Validate real human verdicts and require source-specific dispute adjudication."""

import argparse
import itertools
import json
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

SCHEMA_VERSION = "1.0"
DIMENSIONS = ("correctness", "completeness", "evidence")


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


def read_jsonl(path):
    records = []
    try:
        with Path(path).open("r", encoding="utf-8") as handle:
            for line_number, line in enumerate(handle, 1):
                if not line.strip():
                    continue
                try:
                    value = json.loads(line)
                except json.JSONDecodeError as exc:
                    records.append({"_parse_error": str(exc), "_line": line_number, "_file": Path(path).name})
                    continue
                if not isinstance(value, dict):
                    records.append({"_parse_error": "JSONL row is not an object", "_line": line_number, "_file": Path(path).name})
                    continue
                value = dict(value)
                value["_line"] = line_number
                value["_file"] = Path(path).name
                records.append(value)
    except OSError as exc:
        raise InputError(f"Cannot read JSONL {path}: {exc}") from exc
    return records


def valid_score(value):
    return isinstance(value, int) and not isinstance(value, bool) and value in (0, 1, 2)


def nonempty_text(value):
    return isinstance(value, str) and bool(value.strip())


def parse_time(value):
    if not nonempty_text(value):
        raise ValueError("timestamp is missing")
    normalized = value.replace("Z", "+00:00")
    parsed = datetime.fromisoformat(normalized)
    if parsed.tzinfo is None:
        raise ValueError("timestamp lacks timezone")
    return parsed.astimezone(timezone.utc)


def ref_key(ref):
    return (ref.get("source_id"), ref.get("locator"))


def validate_refs(value, known_refs, require_specificity=False):
    if not isinstance(value, list) or not value:
        return ["source_refs must be a nonempty list"]
    errors = []
    seen = set()
    for index, ref in enumerate(value):
        if not isinstance(ref, dict):
            errors.append(f"source_refs[{index}] is not an object")
            continue
        if not nonempty_text(ref.get("source_id")) or not nonempty_text(ref.get("locator")):
            errors.append(f"source_refs[{index}] lacks source_id/locator")
            continue
        key = ref_key(ref)
        if key not in known_refs:
            errors.append(f"unknown source ref {key[0]} / {key[1]}")
        if key in seen:
            errors.append(f"duplicate source ref {key[0]} / {key[1]}")
        seen.add(key)
        if require_specificity and not nonempty_text(ref.get("evidence_note")):
            errors.append(f"source_refs[{index}] lacks evidence_note tying it to the decision")
    return errors


def public_verdict(record):
    return {
        "assignment_alias": record["assignment_alias"],
        "item_id": record["item_id"],
        "score": record["score"],
        "judgments": record["judgments"],
        "comments": record["comments"],
        "source_refs": record["source_refs"],
        "submitted_at": record["submitted_at"],
        "input_file": record["_file"],
        "input_line": record["_line"],
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--review-manifest", required=True)
    parser.add_argument("--human-verdicts", required=True, action="append", help="Repeat for each independent JSONL file")
    parser.add_argument("--adjudications", help="JSONL of actual adjudicator decisions; never synthesized")
    parser.add_argument("--deadline", required=True, help="Inclusive ISO-8601 deadline with timezone")
    parser.add_argument("--output-dir", required=True)
    args = parser.parse_args()

    try:
        manifest = load_json(args.review_manifest)
        item_ids = manifest.get("item_ids")
        assignments = manifest.get("assignments")
        if not isinstance(item_ids, list) or len(item_ids) != 4 or len(set(item_ids)) != 4:
            raise InputError("Review manifest must contain exactly four unique item_ids")
        if not isinstance(assignments, list) or len(assignments) < 2:
            raise InputError("Review manifest must contain at least two assignments")
        aliases = [row.get("assignment_alias") for row in assignments]
        if any(not nonempty_text(alias) for alias in aliases) or len(aliases) != len(set(aliases)):
            raise InputError("Review manifest has invalid or duplicate assignment aliases")
        deadline = parse_time(args.deadline)
        known_refs = set()
        locators = manifest.get("source_locators", {})
        for source_id, source_locs in locators.items():
            for locator in source_locs:
                known_refs.add((source_id, locator))

        input_records = []
        for filename in args.human_verdicts:
            input_records.extend(read_jsonl(filename))
        if not input_records:
            raise InputError("No actual human verdict records were supplied")

        malformed = []
        unknown_ids = []
        duplicate_records = []
        late_records = []
        grouped = defaultdict(list)
        for record in input_records:
            location = {"input_file": record.get("_file"), "input_line": record.get("_line")}
            if record.get("_parse_error"):
                malformed.append({**location, "error": record["_parse_error"]})
                continue
            alias, item_id = record.get("assignment_alias"), record.get("item_id")
            if alias not in aliases or item_id not in item_ids:
                unknown_ids.append({**location, "assignment_alias": alias, "item_id": item_id})
                continue
            errors = []
            if not valid_score(record.get("score")):
                errors.append("score must be integer 0, 1, or 2")
            judgments = record.get("judgments")
            if not isinstance(judgments, dict) or set(judgments) != set(DIMENSIONS):
                errors.append(f"judgments must contain exactly {', '.join(DIMENSIONS)}")
            else:
                for dimension in DIMENSIONS:
                    if not valid_score(judgments[dimension]):
                        errors.append(f"judgments.{dimension} must be integer 0, 1, or 2")
            if not nonempty_text(record.get("comments")):
                errors.append("comments must be a substantive nonempty string")
            errors.extend(validate_refs(record.get("source_refs"), known_refs))
            try:
                submitted = parse_time(record.get("submitted_at"))
            except (ValueError, TypeError) as exc:
                errors.append(f"invalid submitted_at: {exc}")
                submitted = None
            if errors:
                malformed.append({**location, "assignment_alias": alias, "item_id": item_id, "errors": errors})
                continue
            key = (alias, item_id)
            if submitted > deadline:
                late_records.append({**public_verdict(record), "deadline": args.deadline})
                continue
            grouped[key].append(record)

        valid_verdicts = []
        duplicate_keys = set()
        for key, records_at_key in grouped.items():
            if len(records_at_key) > 1:
                duplicate_keys.add(key)
                duplicate_records.append({
                    "assignment_alias": key[0], "item_id": key[1],
                    "occurrences": [{"input_file": r["_file"], "input_line": r["_line"]} for r in records_at_key],
                    "handling": "All duplicates excluded; independent resubmission required."
                })
            else:
                valid_verdicts.append(public_verdict(records_at_key[0]))

        adjudication_records = defaultdict(list)
        if args.adjudications:
            for record in read_jsonl(args.adjudications):
                if record.get("_parse_error"):
                    malformed.append({"input_file": record["_file"], "input_line": record["_line"], "error": record["_parse_error"], "record_type": "adjudication"})
                    continue
                item_id = record.get("item_id")
                if item_id not in item_ids:
                    unknown_ids.append({"input_file": record["_file"], "input_line": record["_line"], "item_id": item_id, "assignment_alias": "adjudicator"})
                    continue
                adjudication_records[item_id].append(record)

        verdict_lookup = {(row["assignment_alias"], row["item_id"]): row for row in valid_verdicts}
        per_item = []
        pairwise_disagreements = []
        all_unresolved = []
        missing = []
        used_adjudications = []
        for item_id in item_ids:
            item_verdicts = [verdict_lookup[(alias, item_id)] for alias in aliases if (alias, item_id) in verdict_lookup]
            present_aliases = {row["assignment_alias"] for row in item_verdicts}
            item_missing = [alias for alias in aliases if (alias, item_id) not in verdict_lookup]
            for alias in item_missing:
                reason = "no timely valid independent verdict"
                if (alias, item_id) in duplicate_keys:
                    reason = "duplicate verdicts excluded"
                missing.append({"assignment_alias": alias, "item_id": item_id, "reason": reason})
            item_disagreements = []
            for left, right in itertools.combinations(sorted(item_verdicts, key=lambda row: row["assignment_alias"]), 2):
                dimension_diffs = [d for d in DIMENSIONS if left["judgments"][d] != right["judgments"][d]]
                if left["score"] != right["score"] or dimension_diffs:
                    disagreement = {
                        "item_id": item_id,
                        "reviewer_pair": [left["assignment_alias"], right["assignment_alias"]],
                        "score_pair": [left["score"], right["score"]],
                        "differing_dimensions": dimension_diffs,
                        "judgment_pairs": {d: [left["judgments"][d], right["judgments"][d]] for d in DIMENSIONS},
                        "resolution_requirement": "Explicit source-grounded adjudication; agreement itself is not evidence of truth."
                    }
                    item_disagreements.append(disagreement)
                    pairwise_disagreements.append(disagreement)
            nonbinary = any(row["score"] == 1 or any(row["judgments"][d] == 1 for d in DIMENSIONS) for row in item_verdicts)
            adjudication_required = bool(item_disagreements or nonbinary or item_missing)
            candidates = adjudication_records.get(item_id, [])
            unresolved_reasons = []
            adjudication = None
            final_score = None
            if item_missing:
                unresolved_reasons.append("missing timely valid independent verdict(s)")
            if len(candidates) > 1:
                unresolved_reasons.append("duplicate adjudication records")
            if candidates:
                raw = candidates[0]
                errors = []
                status = raw.get("status")
                if status not in ("resolved", "unresolved"):
                    errors.append("status must be resolved or unresolved")
                if not nonempty_text(raw.get("rationale")):
                    errors.append("rationale is required")
                errors.extend(validate_refs(raw.get("source_refs"), known_refs, require_specificity=True))
                if status == "resolved" and not valid_score(raw.get("final_score")):
                    errors.append("resolved adjudication requires final_score integer 0, 1, or 2")
                if status == "unresolved" and raw.get("final_score") is not None:
                    errors.append("unresolved adjudication must use final_score:null")
                if errors:
                    unresolved_reasons.extend(errors)
                    final_score = None
                elif status == "resolved":
                    final_score = raw["final_score"]
                else:
                    unresolved_reasons.append(raw.get("unresolved_reason") or "adjudicator marked item unresolved")
                adjudication = {
                    "item_id": item_id,
                    "status": status if status in ("resolved", "unresolved") else "invalid",
                    "final_score": raw.get("final_score"),
                    "rationale": raw.get("rationale"),
                    "source_refs": raw.get("source_refs"),
                    "unresolved_reason": raw.get("unresolved_reason"),
                    "input_file": raw.get("_file"),
                    "input_line": raw.get("_line"),
                    "validation_errors": errors,
                }
                used_adjudications.append(adjudication)
            elif adjudication_required:
                unresolved_reasons.append("explicit adjudication record is missing")
            elif len(item_verdicts) == len(aliases):
                scores = {row["score"] for row in item_verdicts}
                if len(scores) == 1:
                    final_score = item_verdicts[0]["score"]
                else:
                    unresolved_reasons.append("score disagreement lacks adjudication")
            if final_score is None:
                unresolved_reasons.append("no adjudicated final score")
            status = "resolved" if final_score is not None and not unresolved_reasons else "unresolved"
            if status == "unresolved":
                all_unresolved.append({"item_id": item_id, "reasons": sorted(set(unresolved_reasons))})
            per_item.append({
                "item_id": item_id,
                "status": status,
                "human_verdicts": item_verdicts,
                "expected_aliases": aliases,
                "received_aliases": sorted(present_aliases),
                "pairwise_disagreements": item_disagreements,
                "nonbinary_observed": nonbinary,
                "adjudication_required": adjudication_required,
                "adjudication": adjudication,
                "final_score": final_score,
                "unresolved_reasons": sorted(set(unresolved_reasons)),
            })

        unused_adjudications = []
        for item_id in item_ids:
            candidates = adjudication_records.get(item_id, [])
            if len(candidates) > 1:
                unused_adjudications.extend(row.get("_line") for row in candidates[1:])
        structural_problems = bool(malformed or unknown_ids or late_records or duplicate_records or unused_adjudications)
        success = not structural_problems and not all_unresolved and len(valid_verdicts) == len(item_ids) * len(aliases)
        result = {
            "schema_version": SCHEMA_VERSION,
            "status": "success" if success else "partial",
            "case_id": manifest.get("case_id"),
            "policy": {
                "score_categories": [0, 1, 2],
                "dimensions": list(DIMENSIONS),
                "adjudication_trigger": "Any pairwise score/dimension disagreement, any nonbinary verdict, or missing timely valid verdict.",
                "truth_caveat": "Reviewer agreement and Cohen kappa are not treated as proof of answer truth; final scores require source-specific rationale when triggered.",
                "late_rule": f"submitted_at > {args.deadline} is excluded",
                "duplicate_rule": "All duplicate alias/item records are excluded and require independent resubmission."
            },
            "expected_verdict_count": len(item_ids) * len(aliases),
            "accepted_verdict_count": len(valid_verdicts),
            "human_verdicts": sorted(valid_verdicts, key=lambda row: (row["item_id"], row["assignment_alias"])),
            "pairwise_disagreements": pairwise_disagreements,
            "per_item": per_item,
            "adjudications": used_adjudications,
            "missing_verdicts": missing,
            "duplicate_verdicts": duplicate_records,
            "late_verdicts": late_records,
            "malformed_verdicts": malformed,
            "unknown_id_records": unknown_ids,
            "duplicate_adjudications": [{"item_id": item_id, "count": len(rows)} for item_id, rows in adjudication_records.items() if len(rows) > 1],
            "unresolved_items": all_unresolved,
        }
        output_dir = Path(args.output_dir)
        dump_json(output_dir / "adjudication.json", result)
        print(json.dumps({"status": result["status"], "accepted_verdicts": len(valid_verdicts), "disagreements": len(pairwise_disagreements), "unresolved_items": len(all_unresolved)}, ensure_ascii=False))
        return 0 if success else 3
    except InputError as exc:
        print(f"adjudicate.py: INPUT ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
