#!/usr/bin/env python3
"""Create exactly four-item blind review packets using only the stdlib."""

import argparse
import hashlib
import json
import os
import sys
from pathlib import Path

SCHEMA_VERSION = "1.0"
FORBIDDEN_PACKET_KEYS = {
    "auto_score", "auto_scores", "model_score", "scorer", "reviewer_id",
    "reviewer_name", "display_name", "candidate_author", "private_key",
}


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


def rows(document, key):
    if not isinstance(document, dict) or not isinstance(document.get(key), list):
        raise InputError(f"Expected an object containing a '{key}' list")
    return document[key]


def unique_index(entries, id_key, label, required_ids=None):
    result = {}
    duplicates = []
    for position, entry in enumerate(entries, 1):
        if not isinstance(entry, dict) or not isinstance(entry.get(id_key), str) or not entry[id_key]:
            raise InputError(f"{label} row {position} lacks a nonempty {id_key}")
        entry_id = entry[id_key]
        if entry_id in result:
            duplicates.append(entry_id)
        result[entry_id] = entry
    if duplicates:
        raise InputError(f"Duplicate {label} ID(s): {sorted(set(duplicates))}")
    if required_ids is not None:
        missing = sorted(set(required_ids) - set(result))
        extra = sorted(set(result) - set(required_ids))
        if missing or extra:
            raise InputError(f"{label} ID mismatch; missing={missing}, extra={extra}")
    return result


def require_text(entry, field, label):
    if not isinstance(entry.get(field), str) or not entry[field].strip():
        raise InputError(f"{label} requires nonempty text field '{field}'")


def valid_score(value):
    return isinstance(value, int) and not isinstance(value, bool) and value in (0, 1, 2)


def validate_alias_uniqueness(assignments):
    aliases = [row["assignment_alias"] for row in assignments]
    if len(aliases) != len(set(aliases)):
        raise InputError("Anonymous assignment aliases are not unique")


def assert_packet_blind(packet, forbidden_strings):
    def walk(value):
        if isinstance(value, dict):
            for key, child in value.items():
                if key in FORBIDDEN_PACKET_KEYS or key.startswith("auto_"):
                    raise InputError(f"Blinding failure: packet key '{key}' is forbidden")
                walk(child)
        elif isinstance(value, list):
            for child in value:
                walk(child)
    walk(packet)
    serialized = json.dumps(packet, ensure_ascii=False, sort_keys=True)
    exposed = sorted(text for text in forbidden_strings if text and text in serialized)
    if exposed:
        raise InputError(f"Blinding failure: reviewer identity string(s) exposed: {exposed}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--item-bank", required=True)
    parser.add_argument("--candidate-outputs", required=True)
    parser.add_argument("--auto-scores", required=True)
    parser.add_argument("--source-evidence", required=True)
    parser.add_argument("--reviewers", required=True, help="JSON file with a reviewers list")
    parser.add_argument("--output-dir", required=True)
    args = parser.parse_args()

    try:
        item_bank = load_json(args.item_bank)
        outputs = load_json(args.candidate_outputs)
        automatic = load_json(args.auto_scores)
        evidence = load_json(args.source_evidence)
        reviewers_doc = load_json(args.reviewers)

        item_rows = rows(item_bank, "items")
        if len(item_rows) != 4:
            raise InputError(f"Exactly four items are required; received {len(item_rows)}")
        items = unique_index(item_rows, "item_id", "item")
        item_ids = list(items)
        if len(set(item_ids)) != 4:
            raise InputError("Exactly four unique item IDs are required")
        output_rows = unique_index(rows(outputs, "outputs"), "item_id", "candidate output", item_ids)
        auto_rows = unique_index(rows(automatic, "scores"), "item_id", "automatic score", item_ids)
        source_rows = unique_index(rows(evidence, "sources"), "source_id", "source")
        reviewers = rows(reviewers_doc, "reviewers")
        if len(reviewers) < 2:
            raise InputError("At least two independent reviewers are required")
        reviewer_ids = unique_index(reviewers, "reviewer_id", "reviewer")
        if len(reviewer_ids) != len(reviewers):
            raise InputError("Reviewer IDs must be unique")

        source_index = {}
        for source_id, source in source_rows.items():
            require_text(source, "title", f"Source {source_id}")
            excerpts = source.get("excerpts")
            if not isinstance(excerpts, list) or not excerpts:
                raise InputError(f"Source {source_id} requires a nonempty excerpts list")
            excerpt_index = {}
            for excerpt in excerpts:
                require_text(excerpt, "locator", f"Source {source_id} excerpt")
                require_text(excerpt, "text", f"Source {source_id} excerpt")
                locator = excerpt["locator"]
                if locator in excerpt_index:
                    raise InputError(f"Duplicate locator {source_id} / {locator}")
                excerpt_index[locator] = excerpt
            source_index[source_id] = excerpt_index

        for item_id, item in items.items():
            for field in ("prompt", "reference_answer"):
                require_text(item, field, f"Item {item_id}")
            if not isinstance(item.get("rubric"), dict):
                raise InputError(f"Item {item_id} requires a rubric object")
            for level in ("0", "1", "2"):
                require_text(item["rubric"], level, f"Item {item_id} rubric")
            refs = item.get("evidence_refs")
            if not isinstance(refs, list) or not refs:
                raise InputError(f"Item {item_id} requires source evidence_refs")
            for ref in refs:
                source_id, locator = ref.get("source_id"), ref.get("locator")
                if source_id not in source_index or locator not in source_index.get(source_id, {}):
                    raise InputError(f"Item {item_id} has unknown evidence ref {source_id} / {locator}")
            require_text(output_rows[item_id], "answer_text", f"Candidate output {item_id}")
            if not valid_score(auto_rows[item_id].get("score")):
                raise InputError(f"Automatic score for {item_id} must be integer 0, 1, or 2")

        output_dir = Path(args.output_dir)
        packet_root = output_dir / "review_packets"
        private_dir = output_dir / "private"
        packet_root.mkdir(parents=True, exist_ok=True)
        private_dir.mkdir(parents=True, exist_ok=True)
        assignments = []
        private_assignments = []
        forbidden_identity_strings = set()
        for number, reviewer in enumerate(reviewers, 1):
            reviewer_id = reviewer["reviewer_id"]
            display_name = reviewer.get("display_name", "")
            if not isinstance(display_name, str):
                raise InputError(f"Reviewer {reviewer_id} display_name must be a string")
            forbidden_identity_strings.update((reviewer_id, display_name))
            digest = hashlib.sha256(f"v3-e-assignment-v1|{number}|{reviewer_id}".encode("utf-8")).hexdigest()
            alias = f"blind-{digest[:12]}"
            relative_packet = Path("review_packets") / f"packet-{number:02d}.json"
            assignments.append({
                "assignment_alias": alias,
                "packet_file": relative_packet.as_posix(),
            })
            private_assignments.append({
                "assignment_alias": alias,
                "reviewer_id": reviewer_id,
                "display_name": display_name,
                "packet_file": relative_packet.as_posix(),
            })
        validate_alias_uniqueness(assignments)

        source_locators = {
            source_id: sorted(locators) for source_id, locators in sorted(source_index.items())
        }
        for number, assignment in enumerate(assignments, 1):
            packet_items = []
            for item_id in item_ids:
                item = items[item_id]
                selected_evidence = []
                for ref in item["evidence_refs"]:
                    source = source_rows[ref["source_id"]]
                    excerpt = source_index[ref["source_id"]][ref["locator"]]
                    selected_evidence.append({
                        "source_id": ref["source_id"],
                        "title": source["title"],
                        "source_type": source.get("source_type", "unspecified"),
                        "synthetic": bool(source.get("synthetic", False)),
                        "locator": ref["locator"],
                        "text": excerpt["text"],
                    })
                packet_items.append({
                    "item_id": item_id,
                    "prompt": item["prompt"],
                    "actual_answer": output_rows[item_id]["answer_text"],
                    "reference_answer": item["reference_answer"],
                    "rubric": item["rubric"],
                    "evidence_refs": item["evidence_refs"],
                    "source_evidence": selected_evidence,
                })
            packet = {
                "schema_version": SCHEMA_VERSION,
                "packet_id": f"packet-{number:02d}",
                "assignment_alias": assignment["assignment_alias"],
                "blinding_notice": "Only the deterministic assignment alias is shown. Do not seek reviewer identity or automatic scores.",
                "score_categories": {"0": "incorrect", "1": "partial", "2": "correct"},
                "required_verdict": {
                    "item_id": "one manifest item ID",
                    "assignment_alias": "this packet alias",
                    "score": "integer 0, 1, or 2",
                    "judgments": {"correctness": "0/1/2", "completeness": "0/1/2", "evidence": "0/1/2"},
                    "comments": "specific independent rationale",
                    "source_refs": [{"source_id": "known ID", "locator": "exact locator"}],
                    "submitted_at": "ISO-8601 timestamp with timezone"
                },
                "items": packet_items,
            }
            assert_packet_blind(packet, forbidden_identity_strings)
            dump_json(output_dir / assignment["packet_file"], packet)

        manifest = {
            "schema_version": SCHEMA_VERSION,
            "status": "success",
            "case_id": item_bank.get("case_id"),
            "item_ids": item_ids,
            "expected_reviewer_count": len(reviewers),
            "assignments": assignments,
            "source_locators": source_locators,
            "blinding": {
                "method": "ordered deterministic SHA-256-derived aliases",
                "security_limit": "Deterministic aliases are not access control and do not prevent re-identification by someone holding the input identities.",
                "excluded_from_packets": sorted(FORBIDDEN_PACKET_KEYS | {"automatic score input file"}),
            },
        }
        private_key = {
            "schema_version": SCHEMA_VERSION,
            "case_id": item_bank.get("case_id"),
            "warning": "Private handoff key; keep outside every reviewer packet. Aliases are deterministic, not irreversible anonymization.",
            "assignments": private_assignments,
        }
        dump_json(output_dir / "prepare_manifest.json", manifest)
        key_path = private_dir / "private_key.json"
        dump_json(key_path, private_key)
        try:
            os.chmod(key_path, 0o600)
        except OSError:
            pass
        print(json.dumps({"status": "success", "items": 4, "packets": len(assignments), "output_dir": str(output_dir)}, ensure_ascii=False))
        return 0
    except InputError as exc:
        print(f"prepare_review.py: INPUT ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
