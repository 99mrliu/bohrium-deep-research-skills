#!/usr/bin/env python3
"""SYNTHETIC deterministic source calculator/scorer local to this skill bundle."""

from __future__ import annotations

import argparse
import csv
import io
import re
import sys
from pathlib import Path

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))

from common import (  # noqa: E402
    canonical_bytes,
    read_json,
    sha256_bytes,
    sha256_file,
    sha256_text,
    write_json_new,
)


def one_pattern(pattern: str, text: str) -> int:
    matches = re.findall(pattern, text)
    if len(matches) != 1:
        raise ValueError(f"pattern must match exactly once: {pattern!r}; matches={len(matches)}")
    return int(matches[0])


def table_rows(text: str) -> list[dict[str, str]]:
    rows = list(csv.DictReader(io.StringIO(text)))
    if not rows or set(rows[0]) != {"site", "day", "observations"}:
        raise ValueError("synthetic table schema is site,day,observations")
    return rows


def solve(item: dict[str, object], source_text: dict[str, str]) -> tuple[str, str]:
    spec = item["computation"]
    kind = spec["type"]
    if kind == "ratio_percent":
        text = source_text[spec["source"]]
        enrolled = one_pattern(spec["enrolled_pattern"], text)
        completed = one_pattern(spec["completed_pattern"], text)
        answer = f"{completed / enrolled * 100:.{int(spec['decimals'])}f}%"
        return answer, f"{completed}/{enrolled}*100={answer}"
    if kind == "difference":
        text = source_text[spec["source"]]
        received = one_pattern(spec["received_pattern"], text)
        excluded = one_pattern(spec["excluded_pattern"], text)
        return str(received - excluded), f"{received}-{excluded}={received - excluded}"
    if kind == "table_aggregate":
        rows = [row for row in table_rows(source_text[spec["source"]]) if row["site"] == spec["site"]]
        values = [int(row["observations"]) for row in rows]
        if len(values) != 2:
            raise ValueError("synthetic aggregate requires exactly two matching rows")
        if spec["aggregate"] == "sum":
            return str(sum(values)), f"{'+'.join(map(str, values))}={sum(values)}"
        if spec["aggregate"] == "mean":
            answer = f"{sum(values) / len(values):.1f}"
            return answer, f"({'+'.join(map(str, values))})/{len(values)}={answer}"
        raise ValueError(f"unsupported aggregate: {spec['aggregate']}")
    if kind == "cross_source_sum":
        paragraph_value = one_pattern(spec["paragraph_pattern"], source_text[spec["paragraph_source"]])
        matching = [
            row
            for row in table_rows(source_text[spec["table_source"]])
            if row["site"] == spec["site"] and int(row["day"]) == int(spec["day"])
        ]
        if len(matching) != 1:
            raise ValueError("cross-source table key must match exactly one row")
        table_value = int(matching[0]["observations"])
        return str(paragraph_value + table_value), f"{paragraph_value}+{table_value}={paragraph_value + table_value}"
    raise ValueError(f"unsupported computation type: {kind}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--item-bank", required=True)
    parser.add_argument("--materials", required=True)
    parser.add_argument("--run-config", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--only", action="append", help="Affected item ID; repeatable")
    parser.add_argument(
        "--synthetic-fail",
        action="store_true",
        help="Deliberately return nonzero after writing records for the negative example.",
    )
    args = parser.parse_args()
    bank_path = Path(args.item_bank).resolve()
    materials = Path(args.materials).resolve()
    config_path = Path(args.run_config).resolve()
    output_dir = Path(args.output_dir).resolve()
    bank = read_json(bank_path)
    config = read_json(config_path)
    if bank.get("synthetic") is not True:
        raise ValueError("this helper accepts only explicitly SYNTHETIC banks")
    if sha256_file(bank_path) != config.get("item_bank_sha256"):
        raise ValueError("bank bytes differ from run configuration")
    if materials != Path(config["materials_dir"]):
        raise ValueError("materials path differs from run configuration")
    run_id = config["run_id"]
    if output_dir.name != run_id:
        raise ValueError("output directory must be the initialized run directory")
    items = bank["items"]
    all_ids = [item["item_id"] for item in items]
    if len(all_ids) != 4 or len(set(all_ids)) != 4:
        raise ValueError("synthetic helper requires exactly four unique item IDs")
    selected = args.only if args.only else all_ids
    if len(selected) != len(set(selected)) or not set(selected).issubset(all_ids):
        raise ValueError("--only IDs must be unique members of the item bank")
    mode = "selective_recomputation" if args.only else "full"
    source_text = {}
    source_hashes = {}
    required_materials = sorted(
        {reference["material"] for item in items for reference in item["evidence"]}
    )
    for name in required_materials:
        path = materials / name
        source_text[name] = path.read_text(encoding="utf-8")
        source_hashes[name] = sha256_file(path)
    raw_dir = output_dir / "raw_outputs"
    raw_dir.mkdir(parents=True, exist_ok=False)
    scores = []
    errors = []
    for item in items:
        item_id = item["item_id"]
        if item_id not in selected:
            continue
        try:
            verified_evidence = []
            for reference in item["evidence"]:
                name = reference["material"]
                if reference["quote"] not in source_text[name]:
                    raise ValueError(f"evidence quote not found for {item_id}: {name}")
                verified_evidence.append(
                    {
                        "material": name,
                        "locator": reference["locator"],
                        "quote": reference["quote"],
                        "quote_sha256": sha256_text(reference["quote"]),
                        "source_sha256": source_hashes[name],
                    }
                )
            answer, calculation = solve(item, source_text)
            raw_text = (
                "SYNTHETIC RAW OUTPUT — benchmark-DRAFT\n"
                f"item_id={item_id}\n"
                f"evidence_locators={'; '.join(e['locator'] for e in verified_evidence)}\n"
                f"calculation={calculation}\n"
                f"answer={answer}\n"
            )
            raw_text_hash = sha256_text(raw_text)
            raw_output_id = "raw_" + sha256_text(item_id + "\n" + raw_text)[:24]
            raw = {
                "schema": "rerun-impact-ledger/raw-output-v1",
                "synthetic": True,
                "benchmark_status": "benchmark-DRAFT",
                "item_id": item_id,
                "run_id": run_id,
                "run_config_sha256": sha256_file(config_path),
                "raw_output_id": raw_output_id,
                "task_sha256": sha256_bytes(canonical_bytes(item["task"])),
                "reference_answer_sha256": sha256_bytes(canonical_bytes(item["reference_answer"])),
                "rubric_sha256": sha256_bytes(canonical_bytes(item["rubric"])),
                "computation_sha256": sha256_bytes(canonical_bytes(item["computation"])),
                "evidence": verified_evidence,
                "raw_output_text": raw_text,
                "raw_output_text_sha256": raw_text_hash,
                "answer": answer,
                "calculation": calculation,
                "scientific_correctness": "AGENT_REVIEW_REQUIRED",
            }
            raw_path = raw_dir / f"{item_id}.json"
            write_json_new(raw_path, raw)
            # Evidence verification above is a precondition for source_use in
            # the calculation component. Each item has only two 0/1 components,
            # so its score is consistently 0, 1, or 2.
            component_scores = {
                "calculation": 1 if calculation and verified_evidence else 0,
                "final_answer": 1 if answer == item["reference_answer"] else 0,
            }
            score_core = {
                "item_id": item_id,
                "run_id": run_id,
                "run_config_sha256": sha256_file(config_path),
                "raw_output_id": raw_output_id,
                "rubric_sha256": raw["rubric_sha256"],
                "component_scores": component_scores,
            }
            score = {
                "schema": "rerun-impact-ledger/score-v1",
                "synthetic": True,
                **score_core,
                "score_id": "score_" + sha256_bytes(canonical_bytes(score_core))[:24],
                "raw_output_file_sha256": sha256_file(raw_path),
                "raw_output_text_sha256": raw_text_hash,
                "score": sum(component_scores.values()),
                "max_score": item["rubric"]["max_score"],
                "status": "RECOMPUTED",
                "scorer": "examples/synthetic/scorer.py deterministic stdlib",
            }
            scores.append(score)
        except Exception as exc:
            errors.append({"item_id": item_id, "error": str(exc)})
    write_json_new(
        output_dir / "selection.json",
        {
            "schema": "rerun-impact-ledger/selection-v1",
            "synthetic": True,
            "run_id": run_id,
            "run_config_sha256": sha256_file(config_path),
            "bank_sha256": sha256_file(bank_path),
            "bank_version": bank["bank_version"],
            "mode": mode,
            "bank_item_count": 4,
            "selected_item_ids": selected,
            "selected_count": len(selected),
            "unaffected_item_ids_not_recomputed": [item_id for item_id in all_ids if item_id not in selected],
        },
    )
    write_json_new(
        output_dir / "scores.json",
        {
            "schema": "rerun-impact-ledger/scores-v1",
            "synthetic": True,
            "run_id": run_id,
            "run_config_sha256": sha256_file(config_path),
            "bank_sha256": sha256_file(bank_path),
            "scores": scores,
        },
    )
    if args.synthetic_fail:
        errors.append({"item_id": None, "error": "SYNTHETIC deliberate negative command failure"})
    write_json_new(output_dir / "errors.json", errors)
    for score in scores:
        print(f"{score['item_id']} score={score['score']}/{score['max_score']} raw={score['raw_output_id']}")
    if errors:
        print(f"SYNTHETIC scorer errors: {errors}", file=sys.stderr)
        return 3 if args.synthetic_fail else 1
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:
        print(f"scorer.py: ERROR: {exc}", file=sys.stderr)
        sys.exit(1)
