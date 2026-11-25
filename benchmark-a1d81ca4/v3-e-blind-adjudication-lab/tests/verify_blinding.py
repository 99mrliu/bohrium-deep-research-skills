#!/usr/bin/env python3
"""Fail if reviewer packets expose identities, candidate authors, or automatic-score metadata."""

import argparse
import json
import sys
from pathlib import Path

FORBIDDEN_KEYS = {
    "auto_score", "auto_scores", "model_score", "scorer", "reviewer_id",
    "reviewer_name", "display_name", "candidate_author", "private_key",
}


def read_json(path):
    with Path(path).open("r", encoding="utf-8") as handle:
        return json.load(handle)


def walk_keys(value):
    if isinstance(value, dict):
        for key, child in value.items():
            yield key
            yield from walk_keys(child)
    elif isinstance(value, list):
        for child in value:
            yield from walk_keys(child)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--review-dir", required=True)
    parser.add_argument("--reviewers", required=True)
    parser.add_argument("--auto-scores", required=True)
    parser.add_argument("--candidate-outputs", required=True)
    args = parser.parse_args()
    root = Path(args.review_dir)
    packet_root = root / "review_packets"
    packets = sorted(packet_root.glob("packet-*.json"))
    errors = []
    if not packets:
        errors.append("No packet-*.json files found")
    reviewers = read_json(args.reviewers)["reviewers"]
    candidates = read_json(args.candidate_outputs)["outputs"]
    automatic = read_json(args.auto_scores)
    forbidden_strings = set()
    for reviewer in reviewers:
        forbidden_strings.update((reviewer.get("reviewer_id", ""), reviewer.get("display_name", "")))
    forbidden_strings.update(row.get("candidate_author", "") for row in candidates)
    forbidden_strings.add(automatic.get("scorer", ""))
    forbidden_strings.discard("")
    for packet_path in packets:
        packet = read_json(packet_path)
        keys = set(walk_keys(packet))
        bad_keys = sorted(key for key in keys if key in FORBIDDEN_KEYS or key.startswith("auto_"))
        if bad_keys:
            errors.append(f"{packet_path.name}: forbidden keys {bad_keys}")
        serialized = json.dumps(packet, ensure_ascii=False, sort_keys=True)
        leaked = sorted(text for text in forbidden_strings if text in serialized)
        if leaked:
            errors.append(f"{packet_path.name}: exposed identity/scorer strings {leaked}")
        if len(packet.get("items", [])) != 4:
            errors.append(f"{packet_path.name}: does not contain exactly four items")
        for item in packet.get("items", []):
            if not item.get("actual_answer") or not item.get("source_evidence"):
                errors.append(f"{packet_path.name}/{item.get('item_id')}: missing actual answer or source evidence")
            for evidence in item.get("source_evidence", []):
                if not evidence.get("source_id") or not evidence.get("locator"):
                    errors.append(f"{packet_path.name}/{item.get('item_id')}: missing source locator")
    private_keys = list(packet_root.rglob("*private*key*.json")) if packet_root.exists() else []
    if private_keys:
        errors.append("Private key found inside reviewer packet tree")
    standalone_key = root / "private" / "private_key.json"
    if not standalone_key.is_file():
        errors.append("Separate private/private_key.json is missing")
    if errors:
        for error in errors:
            print(f"BLINDING FAILURE: {error}", file=sys.stderr)
        return 1
    print(f"Blinding verified: {len(packets)} packets, four items each, no forbidden identity/automatic-score keys or strings; private key separate.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
