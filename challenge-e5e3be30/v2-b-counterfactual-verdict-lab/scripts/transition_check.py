#!/usr/bin/env python3
"""Validate one-operator probes and independently annotated verdict transitions."""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any

VERDICTS = {
    "supported",
    "partially_supported",
    "contradicted",
    "insufficient_evidence",
}
OPERATORS = {
    "negation",
    "comparison_direction",
    "significance",
    "causal_correlation",
    "quantifier",
    "condition_scope",
}
SEMANTIC_RELATIONS = {"same", "weaken", "strengthen"}
EXPECTED_RELATIONS = {
    "same",
    "weaken",
    "strengthen",
    "flip_to_contradicted",
    "become_insufficient",
}
WEAKEN = {
    ("supported", "partially_supported"),
    ("supported", "insufficient_evidence"),
    ("partially_supported", "insufficient_evidence"),
}
STRENGTHEN = {
    ("insufficient_evidence", "partially_supported"),
    ("insufficient_evidence", "supported"),
    ("partially_supported", "supported"),
}


def load_json(path: Path) -> Any:
    def no_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        output: dict[str, Any] = {}
        for key, value in pairs:
            if key in output:
                raise ValueError(f"duplicate JSON key: {key}")
            output[key] = value
        return output

    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle, object_pairs_hook=no_duplicates)


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def normalize_claims(document: Any) -> dict[str, dict[str, Any]]:
    rows = document
    if isinstance(document, dict):
        rows = next(
            (document[key] for key in ("claims", "claims_to_verify", "items") if isinstance(document.get(key), list)),
            None,
        )
    if not isinstance(rows, list):
        raise ValueError("claims input must be a list or contain claims/claims_to_verify/items")
    output: dict[str, dict[str, Any]] = {}
    for index, row in enumerate(rows, start=1):
        if not isinstance(row, dict):
            raise ValueError(f"claim {index} must be an object")
        claim_id = row.get("claim_id", row.get("id", f"claim-{index:03d}"))
        text = next((row[key] for key in ("text", "claim", "question", "statement") if isinstance(row.get(key), str)), None)
        if not isinstance(claim_id, str) or not claim_id or not text:
            raise ValueError(f"claim {index} needs a string id and text/claim/question/statement")
        if claim_id in output:
            raise ValueError(f"duplicate claim id: {claim_id}")
        output[claim_id] = {"id": claim_id, "text": text, "raw": row}
    return output


def normalize_annotations(document: Any) -> dict[str, dict[str, Any]]:
    if not isinstance(document, dict) or not isinstance(document.get("annotations"), list):
        raise ValueError("annotations must be an object with an annotations list")
    output: dict[str, dict[str, Any]] = {}
    for row in document["annotations"]:
        if not isinstance(row, dict) or not isinstance(row.get("id"), str):
            raise ValueError("each annotation needs a string id")
        if row["id"] in output:
            raise ValueError(f"duplicate annotation id: {row['id']}")
        if row.get("verdict") not in VERDICTS:
            raise ValueError(f"invalid independent verdict for {row['id']}")
        if not isinstance(row.get("text"), str) or not row["text"]:
            raise ValueError(f"annotation {row['id']} lacks exact text")
        signature = row.get("semantic_signature")
        if not isinstance(signature, dict) or set(signature) != OPERATORS:
            raise ValueError(f"annotation {row['id']} must have all six semantic signature keys")
        evidence = row.get("evidence")
        if not isinstance(evidence, list) or not evidence:
            raise ValueError(f"annotation {row['id']} needs at least one evidence record")
        for item in evidence:
            if not isinstance(item, dict) or not all(isinstance(item.get(key), str) and item[key] for key in ("source_id", "locator", "snippet")):
                raise ValueError(f"annotation {row['id']} has an incomplete evidence record")
        output[row["id"]] = row
    return output


def source_ids(document: Any, manifest_path: Path) -> set[str]:
    if not isinstance(document, dict) or not isinstance(document.get("sources"), list):
        raise ValueError("sources manifest must contain a sources list")
    ids: set[str] = set()
    for source in document["sources"]:
        if not isinstance(source, dict) or not isinstance(source.get("source_id"), str) or not isinstance(source.get("path"), str):
            raise ValueError("each source needs source_id and path")
        source_path = Path(source["path"])
        if not source_path.is_absolute():
            source_path = manifest_path.parent / source_path
        if not source_path.is_file():
            raise ValueError(f"source file does not exist: {source['path']}")
        if source["source_id"] in ids:
            raise ValueError(f"duplicate source_id: {source['source_id']}")
        ids.add(source["source_id"])
    return ids


def expectation_matches(expected: str, before: str, after: str) -> bool:
    transition = (before, after)
    if expected == "same":
        return before == after
    if expected == "weaken":
        return transition in WEAKEN
    if expected == "strengthen":
        return transition in STRENGTHEN
    if expected == "flip_to_contradicted":
        return before != "contradicted" and after == "contradicted"
    if expected == "become_insufficient":
        return before != "insufficient_evidence" and after == "insufficient_evidence"
    raise ValueError(f"unknown expected relation: {expected}")


def compact_evidence(annotation: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        {
            "source_id": item["source_id"],
            "locator": item["locator"],
            "snippet": item["snippet"],
            "stance": item.get("stance", "unmarked"),
        }
        for item in annotation["evidence"]
    ]


def check(claims_doc: Any, plan: Any, annotations_doc: Any, sources_doc: Any, sources_path: Path) -> tuple[dict[str, Any], int]:
    claims = normalize_claims(claims_doc)
    annotations = normalize_annotations(annotations_doc)
    known_sources = source_ids(sources_doc, sources_path)
    if not isinstance(plan, dict) or not isinstance(plan.get("probes"), list):
        raise ValueError("probe plan must contain a probes list")
    if not plan["probes"]:
        raise ValueError("no selected probes; annotate original claims and deliver partial rather than calibrating nothing")
    if len(plan["probes"]) > 24:
        raise ValueError("selected probe count exceeds hard cap 24")
    seen: set[str] = set()
    rows: list[dict[str, Any]] = []
    errors: list[str] = []

    for probe in plan["probes"]:
        if not isinstance(probe, dict):
            raise ValueError("each selected probe must be an object")
        probe_id = probe.get("probe_id")
        base_id = probe.get("base_claim_id")
        if not isinstance(probe_id, str) or not probe_id or probe_id in seen:
            raise ValueError(f"duplicate or invalid probe_id: {probe_id!r}")
        seen.add(probe_id)
        if base_id not in claims:
            raise ValueError(f"{probe_id}: unknown base claim {base_id!r}")
        base = claims[base_id]
        if base_id not in annotations or probe_id not in annotations:
            raise ValueError(f"{probe_id}: independent annotations are required for both {base_id} and {probe_id}")
        base_ann = annotations[base_id]
        probe_ann = annotations[probe_id]
        probe_text = probe.get("probe_text")
        if not isinstance(probe_text, str) or not probe_text:
            raise ValueError(f"{probe_id}: missing probe_text")
        operator = probe.get("operator")
        if operator not in OPERATORS:
            raise ValueError(f"{probe_id}: unknown operator {operator!r}")
        base_sig = probe.get("base_signature")
        probe_sig = probe.get("probe_signature")
        if not isinstance(base_sig, dict) or not isinstance(probe_sig, dict) or set(base_sig) != OPERATORS or set(probe_sig) != OPERATORS:
            raise ValueError(f"{probe_id}: plan signatures must contain all six operators")
        changed = sorted(key for key in OPERATORS if base_sig[key] != probe_sig[key])
        if changed != [operator]:
            raise ValueError(
                f"{probe_id}: illegal {len(changed)}-operator perturbation; changed={changed}, declared={operator}"
            )
        if base_ann["text"] != base["text"] or probe_ann["text"] != probe_text:
            raise ValueError(f"{probe_id}: annotation text does not exactly match claim/probe text")
        supplied_base_sig = base["raw"].get("semantic_signature")
        if supplied_base_sig is not None and supplied_base_sig != base_sig:
            raise ValueError(f"{probe_id}: plan base signature differs from claims input")
        if base_ann["semantic_signature"] != base_sig or probe_ann["semantic_signature"] != probe_sig:
            raise ValueError(f"{probe_id}: independent annotation signatures differ from the plan")
        edit = probe.get("edit_contract")
        if not isinstance(edit, dict) or not isinstance(edit.get("find"), str) or not isinstance(edit.get("replace"), str):
            raise ValueError(f"{probe_id}: exact edit_contract find/replace is required")
        find = edit["find"]
        if not find or base["text"].count(find) != 1:
            raise ValueError(f"{probe_id}: edit find must occur exactly once and be nonempty")
        if base["text"].replace(find, edit["replace"], 1) != probe_text:
            raise ValueError(f"{probe_id}: one-span edit does not exactly produce probe_text")
        if edit["replace"] == find:
            raise ValueError(f"{probe_id}: zero textual perturbation")
        if probe.get("semantic_relation") not in SEMANTIC_RELATIONS:
            raise ValueError(f"{probe_id}: invalid semantic_relation")
        expected = probe.get("expected_relation")
        if expected not in EXPECTED_RELATIONS:
            raise ValueError(f"{probe_id}: invalid expected_relation")
        for annotation in (base_ann, probe_ann):
            unknown = [item["source_id"] for item in annotation["evidence"] if item["source_id"] not in known_sources]
            if unknown:
                raise ValueError(f"{annotation['id']}: unknown evidence source IDs {unknown}")

        before = base_ann["verdict"]
        after = probe_ann["verdict"]
        consistent = expectation_matches(expected, before, after)
        row = {
            "probe_id": probe_id,
            "base_claim_id": base_id,
            "operator": operator,
            "semantic_relation": probe["semantic_relation"],
            "expected_relation": expected,
            "original_verdict": before,
            "probe_verdict": after,
            "observed_transition": f"{before}->{after}",
            "consistent": consistent,
            "review_required": not consistent,
            "original_annotation": {
                "rationale": base_ann.get("rationale", ""),
                "evidence": compact_evidence(base_ann),
            },
            "probe_annotation": {
                "rationale": probe_ann.get("rationale", ""),
                "evidence": compact_evidence(probe_ann),
            },
        }
        rows.append(row)
        if not consistent:
            errors.append(
                f"{probe_id}: expected {expected}, observed {before}->{after}; mandatory original-source re-review"
            )

    transition_counts = Counter(row["observed_transition"] for row in rows)
    report = {
        "schema_version": 1,
        "synthetic": bool(
            (isinstance(claims_doc, dict) and claims_doc.get("synthetic"))
            or plan.get("synthetic")
            or annotations_doc.get("synthetic")
        ),
        "status": "consistent" if not errors else "needs_re_review",
        "summary": {
            "total": len(rows),
            "consistent": sum(row["consistent"] for row in rows),
            "inconsistent": len(errors),
            "operators": dict(sorted(Counter(row["operator"] for row in rows).items())),
            "observed_transitions": dict(sorted(transition_counts.items())),
        },
        "selection": plan.get("selection"),
        "rows": rows,
        "review_instructions": [] if not errors else errors,
        "verdict_provenance": "independent source-grounded annotations; no string-based verdict inference",
    }
    return report, (2 if errors else 0)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--claims", required=True, type=Path)
    parser.add_argument("--probe-plan", required=True, type=Path)
    parser.add_argument("--annotations", required=True, type=Path)
    parser.add_argument("--sources", required=True, type=Path)
    parser.add_argument("--report", required=True, type=Path)
    args = parser.parse_args()
    try:
        report, code = check(
            load_json(args.claims),
            load_json(args.probe_plan),
            load_json(args.annotations),
            load_json(args.sources),
            args.sources,
        )
        write_json(args.report, report)
        print(
            f"transition status={report['status']} total={report['summary']['total']} "
            f"inconsistent={report['summary']['inconsistent']}"
        )
        for message in report["review_instructions"]:
            print(f"RE-REVIEW: {message}", file=sys.stderr)
        return code
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        failure = {
            "schema_version": 1,
            "status": "invalid",
            "summary": {"total": 0, "consistent": 0, "inconsistent": 0},
            "rows": [],
            "errors": [str(exc)],
            "verdict_provenance": "no verdict inference performed",
        }
        try:
            write_json(args.report, failure)
        except OSError:
            pass
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
