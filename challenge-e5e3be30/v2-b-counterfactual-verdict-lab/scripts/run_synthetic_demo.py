#!/usr/bin/env python3
"""Run the complete SYNTHETIC annotate -> detect -> re-review -> final pipeline."""
from __future__ import annotations

import argparse
import copy
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
from typing import Any

sys.dont_write_bytecode = True


def load(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def dump(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def invoke(arguments: list[str], expected: int) -> subprocess.CompletedProcess[str]:
    env = dict(os.environ)
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    completed = subprocess.run(
        [sys.executable, *arguments],
        text=True,
        capture_output=True,
        env=env,
        check=False,
    )
    sys.stdout.write(completed.stdout)
    sys.stderr.write(completed.stderr)
    if completed.returncode != expected:
        raise RuntimeError(
            f"command {' '.join(arguments)} returned {completed.returncode}, expected {expected}"
        )
    return completed


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--work-dir", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument(
        "--bundle-root",
        type=Path,
        default=Path(__file__).resolve().parent.parent,
        help=argparse.SUPPRESS,
    )
    args = parser.parse_args()
    root = args.bundle_root.resolve()
    examples = root / "examples" / "synthetic"
    scripts = root / "scripts"
    work = args.work_dir
    output = args.output_dir
    work.mkdir(parents=True, exist_ok=True)
    output.mkdir(parents=True, exist_ok=True)

    fixture_names = [
        "case.json",
        "claims-to-verify.json",
        "paper.txt",
        "sources.json",
        "probe-candidates.json",
        "independent-annotations.initial.json",
    ]
    for name in fixture_names:
        shutil.copyfile(examples / name, work / name)

    # The honest partial is written before any calibration begins.
    invoke(
        [
            str(scripts / "contract_tools.py"),
            "skeleton",
            "--case-json",
            str(work / "case.json"),
            "--output",
            str(output / "result.json"),
        ],
        0,
    )
    invoke(
        [
            str(scripts / "probe_ops.py"),
            "select",
            "--plan",
            str(work / "probe-candidates.json"),
            "--output",
            str(work / "probe-plan.json"),
            "--max-probes",
            "6",
            "--seed",
            "17",
        ],
        0,
    )
    selected = load(work / "probe-plan.json")
    assert selected["selection"]["candidate_count"] == 8
    assert selected["selection"]["selected_count"] == 6
    assert len(selected["selection"]["omitted"]) == 2
    assert {row["operator"] for row in selected["probes"]} == {
        "negation",
        "comparison_direction",
        "significance",
        "causal_correlation",
        "quantifier",
        "condition_scope",
    }

    # Initial independent annotations deliberately contain one scientific misclassification.
    invoke(
        [
            str(scripts / "transition_check.py"),
            "--claims",
            str(work / "claims-to-verify.json"),
            "--probe-plan",
            str(work / "probe-plan.json"),
            "--annotations",
            str(work / "independent-annotations.initial.json"),
            "--sources",
            str(work / "sources.json"),
            "--report",
            str(work / "transition-report.initial.json"),
        ],
        2,
    )
    initial_report = load(work / "transition-report.initial.json")
    failures = [row for row in initial_report["rows"] if not row["consistent"]]
    assert len(failures) == 1 and failures[0]["probe_id"] == "p-cause"
    assert failures[0]["observed_transition"] == "supported->contradicted"
    dump(output / "transition-report.initial.json", initial_report)
    invoke(
        [
            str(scripts / "render_transition_svg.py"),
            "--report",
            str(work / "transition-report.initial.json"),
            "--output",
            str(output / "transition-preview.initial.svg"),
        ],
        0,
    )

    # Apply only the explicitly documented source re-review, never a rule inferred from strings.
    review = load(examples / "review-record.json")
    reviewed = load(work / "independent-annotations.initial.json")
    targets = [row for row in reviewed["annotations"] if row["id"] == review["target_id"]]
    assert len(targets) == 1
    target = targets[0]
    assert target["verdict"] == review["before"]["verdict"]
    target["verdict"] = review["after"]["verdict"]
    target["rationale"] = review["after"]["rationale"]
    target["uncertainty"] = [
        "Causation remains unestablished by this observational subgroup; association remains supported."
    ]
    target["re_review_record_id"] = review["record_id"]
    reviewed["review_stage"] = "source-grounded correction after inconsistent transition; initial annotations retained separately"
    dump(work / "independent-annotations.reviewed.json", reviewed)
    shutil.copyfile(work / "independent-annotations.initial.json", output / "independent-annotations.initial.json")
    dump(output / "independent-annotations.reviewed.json", reviewed)
    dump(work / "change_records.json", [review])
    dump(output / "change_records.json", [review])

    invoke(
        [
            str(scripts / "transition_check.py"),
            "--claims",
            str(work / "claims-to-verify.json"),
            "--probe-plan",
            str(work / "probe-plan.json"),
            "--annotations",
            str(work / "independent-annotations.reviewed.json"),
            "--sources",
            str(work / "sources.json"),
            "--report",
            str(work / "transition-report.json"),
        ],
        0,
    )
    final_report = load(work / "transition-report.json")
    assert final_report["status"] == "consistent"
    assert final_report["summary"]["total"] == 6
    assert final_report["summary"]["consistent"] == 6
    assert final_report["summary"]["inconsistent"] == 0
    dump(output / "transition-report.json", final_report)
    invoke(
        [
            str(scripts / "render_transition_svg.py"),
            "--report",
            str(work / "transition-report.json"),
            "--output",
            str(output / "transition-preview.svg"),
        ],
        0,
    )

    # Populate the dynamically discovered contract; there is no expected-result fixture.
    result = load(output / "result.json")
    contract = load(work / "case.json")["output_contract"]
    claims = load(work / "claims-to-verify.json")["claims"]
    ann_by_id = {row["id"]: row for row in reviewed["annotations"]}
    field_values = {
        "answer": "SYNTHETIC DEMO: six independently adjudicated one-operator probes passed after one source-grounded re-review corrected causation from contradicted to insufficient_evidence.",
        "translation": "合成示例：六个单算子探针均完成独立核验；因果探针初检发现一处不一致，回到原文复核后由“反驳”修正为“证据不足”，随后全部通过。",
        "quotation": [
            {
                "claim_id": claim["claim_id"],
                "source_id": ann_by_id[claim["claim_id"]]["evidence"][0]["source_id"],
                "locator": ann_by_id[claim["claim_id"]]["evidence"][0]["locator"],
                "text": ann_by_id[claim["claim_id"]]["evidence"][0]["snippet"],
            }
            for claim in claims
        ],
    }
    for field, spec in contract.items():
        result[field] = copy.deepcopy(field_values.get(field, [] if spec == "array" else ""))
    result["original_verifications"] = [
        {
            "claim_id": claim["claim_id"],
            "question_not_fact": True,
            "verdict": ann_by_id[claim["claim_id"]]["verdict"],
            "rationale": ann_by_id[claim["claim_id"]]["rationale"],
        }
        for claim in claims
    ]
    result["probe_verifications"] = [
        {
            "probe_id": row["probe_id"],
            "base_claim_id": row["base_claim_id"],
            "operator": row["operator"],
            "expected_relation": row["expected_relation"],
            "verdict": row["probe_verdict"],
            "observed_transition": row["observed_transition"],
            "consistent": row["consistent"],
        }
        for row in final_report["rows"]
    ]
    result["calibration"] = {
        "selection": final_report["selection"],
        "summary": final_report["summary"],
        "initial_inconsistency": failures[0],
        "initial_report": "transition-report.initial.json",
        "final_report": "transition-report.json",
    }
    result["synthetic"] = True
    result["sources"] = load(work / "sources.json")["sources"]
    result["uncertainty"] = [
        "SYNTHETIC demonstration only; none of the fabricated scientific statements or values are real evidence.",
        "The observational association does not establish causation; the broader Treatment C severity scope remains unreported."
    ]
    result["change_records"] = [review]
    result["status"] = "success"
    dump(output / "result.json", result)
    invoke(
        [
            str(scripts / "contract_tools.py"),
            "validate-final",
            "--case-json",
            str(work / "case.json"),
            "--result",
            str(output / "result.json"),
        ],
        0,
    )
    summary = {
        "synthetic": True,
        "pipeline": "dynamic_partial -> risk_select_8_to_6 -> independent_transition_exit2 -> source_re_review -> transition_exit0 -> dynamic_final",
        "initial_inconsistencies": 1,
        "final_inconsistencies": 0,
        "final_result": str(output / "result.json"),
        "transition_preview": str(output / "transition-preview.svg"),
    }
    dump(output / "demo-summary.json", summary)
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
