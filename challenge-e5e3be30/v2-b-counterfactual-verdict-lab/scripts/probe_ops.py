#!/usr/bin/env python3
"""Pre-verdict, operator-stratified risk sampling to bound probe growth."""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any

OPERATOR_RISK = {
    "causal_correlation": 100,
    "negation": 95,
    "comparison_direction": 90,
    "significance": 88,
    "quantifier": 85,
    "condition_scope": 80,
}
HARD_CAP = 24


def load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def risk_score(probe: dict[str, Any]) -> int:
    operator = probe.get("operator")
    if operator not in OPERATOR_RISK:
        raise ValueError(f"unknown operator in {probe.get('probe_id')!r}: {operator!r}")
    boost = probe.get("risk_boost", 0)
    flags = probe.get("risk_flags", [])
    if not isinstance(boost, int) or isinstance(boost, bool) or boost < 0:
        raise ValueError(f"risk_boost must be a nonnegative integer in {probe.get('probe_id')!r}")
    if not isinstance(flags, list) or not all(isinstance(flag, str) for flag in flags):
        raise ValueError(f"risk_flags must be a string list in {probe.get('probe_id')!r}")
    # Deliberately do not inspect verdicts or expected/observed transition outcomes.
    return OPERATOR_RISK[operator] + boost + 5 * len(flags)


def select_probes(plan: Any, max_probes: int, seed: int) -> dict[str, Any]:
    if not isinstance(plan, dict) or not isinstance(plan.get("probes"), list):
        raise ValueError("probe plan must be an object with a probes list")
    if not 1 <= max_probes <= HARD_CAP:
        raise ValueError(f"max_probes must be between 1 and {HARD_CAP}")
    probes = plan["probes"]
    if not all(isinstance(probe, dict) for probe in probes):
        raise ValueError("every probe must be an object")
    ids = [probe.get("probe_id") for probe in probes]
    if any(not isinstance(probe_id, str) or not probe_id for probe_id in ids):
        raise ValueError("every probe needs a nonempty probe_id")
    if len(set(ids)) != len(ids):
        raise ValueError("duplicate probe_id")

    ranked = []
    for index, probe in enumerate(probes):
        tie = hashlib.sha256(f"{seed}:{probe['probe_id']}".encode("utf-8")).hexdigest()
        ranked.append((probe, risk_score(probe), tie, index))
    grouped: dict[str, list[tuple[dict[str, Any], int, str, int]]] = {}
    for row in ranked:
        grouped.setdefault(row[0]["operator"], []).append(row)
    for rows in grouped.values():
        rows.sort(key=lambda row: (-row[1], row[2], row[0]["probe_id"]))
    coverage_order = sorted(
        grouped,
        key=lambda op: (-grouped[op][0][1], grouped[op][0][2], op),
    )

    selected_rows: list[tuple[dict[str, Any], int, str, int]] = []
    round_index = 0
    while len(selected_rows) < min(max_probes, len(ranked)):
        added = False
        for operator in coverage_order:
            rows = grouped[operator]
            if round_index < len(rows):
                selected_rows.append(rows[round_index])
                added = True
                if len(selected_rows) == max_probes:
                    break
        if not added:
            break
        round_index += 1

    selected_ids = {row[0]["probe_id"] for row in selected_rows}
    selected_set = set(selected_ids)
    selected = [probe for probe in probes if probe["probe_id"] in selected_set]
    score_by_id = {row[0]["probe_id"]: row[1] for row in ranked}
    omitted = [
        {
            "probe_id": probe["probe_id"],
            "operator": probe["operator"],
            "pre_verdict_risk_score": score_by_id[probe["probe_id"]],
            "reason": "budget_after_operator_stratified_risk_sampling",
        }
        for probe in probes
        if probe["probe_id"] not in selected_set
    ]
    output = {key: value for key, value in plan.items() if key != "selection"}
    output["probes"] = selected
    output["selection"] = {
        "policy": "operator_stratified_pre_verdict_risk_with_deterministic_ties",
        "seed": seed,
        "candidate_count": len(probes),
        "max_probes": max_probes,
        "selected_count": len(selected),
        "operator_weights": OPERATOR_RISK,
        "selected": [
            {
                "probe_id": probe["probe_id"],
                "operator": probe["operator"],
                "pre_verdict_risk_score": score_by_id[probe["probe_id"]],
            }
            for probe in selected
        ],
        "omitted": omitted,
    }
    return output


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    select = sub.add_parser("select")
    select.add_argument("--plan", required=True, type=Path)
    select.add_argument("--output", required=True, type=Path)
    select.add_argument("--max-probes", type=int, default=12)
    select.add_argument("--seed", type=int, default=17)
    args = parser.parse_args()
    try:
        if args.command == "select":
            selected = select_probes(load_json(args.plan), args.max_probes, args.seed)
            write_json(args.output, selected)
            metadata = selected["selection"]
            print(
                f"selected {metadata['selected_count']} of {metadata['candidate_count']} "
                f"pre-verdict candidates (cap {metadata['max_probes']})"
            )
            return 0
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
