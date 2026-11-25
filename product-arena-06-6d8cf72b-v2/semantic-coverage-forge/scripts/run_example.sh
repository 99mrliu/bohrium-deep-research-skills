#!/usr/bin/env bash
# Runnable, entirely synthetic example; no network, packages, or external case data.
set -euo pipefail

if [ "$#" -gt 1 ]; then
  printf 'Usage: bash scripts/run_example.sh [OUTPUT_ROOT]\n' >&2
  exit 2
fi

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
BUNDLE_DIR=$(CDPATH= cd -- "$SCRIPT_DIR/.." && pwd)
EXAMPLE_DIR="$BUNDLE_DIR/examples/synthetic"
OUTPUT_ROOT=${1:-"$EXAMPLE_DIR/output"}
mkdir -p -- "$OUTPUT_ROOT"
export PYTHONDONTWRITEBYTECODE=1
PYTHON_BIN=${PYTHON:-python3}

"$PYTHON_BIN" - "$EXAMPLE_DIR" "$OUTPUT_ROOT" <<'PY'
import json
from pathlib import Path
import shutil
import sys

example = Path(sys.argv[1])
out = Path(sys.argv[2])
plan = json.loads((example / "plan.json").read_text(encoding="utf-8"))
shutil.copyfile(str(example / "authored_result.json"), str(out / "result.json"))
(out / "answer_matrix.json").write_text(
    json.dumps({
        "label": "SYNTHETIC answer matrix — fictional example only",
        "synthetic": True,
        "case_id": plan["case_id"],
        "answer_matrix": plan["answer_matrix"],
        "item_id_contracts": plan["item_id_contracts"]
    }, ensure_ascii=False, indent=2) + "\n",
    encoding="utf-8"
)
PY

"$PYTHON_BIN" "$BUNDLE_DIR/scripts/semantic_coverage_auditor.py" \
  --plan "$EXAMPLE_DIR/plan.json" \
  --result "$OUTPUT_ROOT/result.json" \
  --case "$EXAMPLE_DIR/case.json" \
  --task "$EXAMPLE_DIR/task.md" \
  --source "$EXAMPLE_DIR/source.json" \
  --report "$OUTPUT_ROOT/audit_report.json"

"$PYTHON_BIN" - "$EXAMPLE_DIR" "$OUTPUT_ROOT" <<'PY'
import json
from pathlib import Path
import sys

example = Path(sys.argv[1])
out = Path(sys.argv[2])
plan = json.loads((example / "plan.json").read_text(encoding="utf-8"))
result = json.loads((out / "result.json").read_text(encoding="utf-8"))
report = json.loads((out / "audit_report.json").read_text(encoding="utf-8"))
rows = plan["answer_matrix"]["items"]

# Deliberately item-specific records: this is a review of the authored claims, not the
# same checklist prose copied under three different item IDs.
review_by_item = {
    "Q1": {
        "omission": "Both requested components are present: the 12-week orientation mean (82.4 points) and its author-reported rather than calculated provenance.",
        "comparator": "Q1 requests one reported mean, not a group contrast; no between-group direction or baseline was invented.",
        "negation": "The phrase 'not calculated from the excerpt' preserves the provenance limit while leaving the reported value intact.",
        "condition": "The 12-week endpoint, orientation-score endpoint, points unit, and n=36 denominator all match S1.",
        "unsupported_generalization": "The answer reports a study mean only; it makes no efficacy, participant-wide, or beyond-excerpt claim.",
        "whole_answer_entailment": "The single S1 quotation contains the mean, time point, unit, sample size, and author-reported wording used by the answer; human entailment review remains required.",
        "conflicts_two_sided": "No competing orientation mean appears in S1, S2, or T1, so there is no Q1 value conflict to reconcile.",
        "formula_derived_vs_author_reported": "The 82.4-point value is labelled author-reported; SEM 1.2 was not used to derive a new estimate.",
        "status_integrity": "Q1 is answered with one S1 evidence item whose anchor is inside its declared checked scope."
    },
    "Q2": {
        "omission": "The response supplies both Reed means, their direction and difference, minutes, per-group n, exploratory/unadjusted conditions, and an explicit answer about other-site generalization.",
        "comparator": "Compass A (8.1 minutes) is correctly described as 1.3 minutes lower than Compass B (9.4 minutes), using B as the stated baseline.",
        "negation": "The explicit 'No' blocks the requested other-site generalization instead of implying it from a favourable numerical difference.",
        "condition": "Every comparison clause remains tied to Reed site only and to the exploratory, unadjusted T1 analysis with n=12 per group.",
        "unsupported_generalization": "The response does not infer superiority at other sites or statistical significance from an unadjusted descriptive comparison.",
        "whole_answer_entailment": "T1 supports both input means and all restrictions; the matrix separately documents the calculated subtraction rather than pretending T1 reports 1.3 minutes.",
        "conflicts_two_sided": "T1 contains one Reed comparison and no other-site completion results, so the answer does not suppress a competing site estimate.",
        "formula_derived_vs_author_reported": None,
        "status_integrity": "Q2 is answered with mixed evidence: T1 supplies the reported means while the matrix records the derived direction and difference."
    },
    "Q3": {
        "omission": "The response states that no 95% CI or CI bounds are reported for the 12-week mean and separately notes that no CI was calculated.",
        "comparator": "Q3 requests interval bounds rather than an arm comparison; no lower/upper pair or arm contrast was fabricated.",
        "negation": "'Not reported in the checked excerpt' is explicitly bounded and does not become a claim that no study anywhere reports this interval.",
        "condition": "The absence statement remains restricted to the 12-week orientation score and the enumerated S1, S2, and T1 excerpt anchors.",
        "unsupported_generalization": "The answer neither converts SEM 1.2 into a confidence level nor invents a symmetric interval around 82.4 points.",
        "whole_answer_entailment": "S1 provides the near-miss SEM while S2 explicitly excludes CI bounds and calculations; these are reviewed as scope evidence, not inserted as fake support quotes.",
        "conflicts_two_sided": "The excerpt contains no competing CI bounds; the only potential confusion is SEM versus CI, which the answer resolves without substitution.",
        "formula_derived_vs_author_reported": "No CI formula was applied and no interval is represented as author-reported; the task prohibits deriving one from SEM here.",
        "status_integrity": "Q3 uses not_reported, retains evidence=[], and documents all three checked anchors rather than manufacturing an absence quotation."
    }
}
# Reuse Q2's structured derivation so formula, input, and rounding records cannot drift.
review_by_item["Q2"]["formula_derived_vs_author_reported"] = next(
    row["derivation"] for row in rows if row["item_id"] == "Q2"
)

review_rows = []
for row in rows:
    item_id = row["item_id"]
    review_rows.append({
        "item_id": item_id,
        "question": row["question"],
        "direct_answer": result[item_id]["answer"],
        "status": result[item_id]["status"],
        "evidence_role": row["evidence_role"],
        "evidence_count": len(result[item_id]["evidence"]),
        "checked_scope": result[item_id]["checked_scope"],
        "declared_source_scope": row["checked_source_scope"],
        "adversarial_review": review_by_item[item_id],
        "residual_uncertainty": row["uncertainty"]
    })

review = {
    "label": "SYNTHETIC semantic review — fictional example only",
    "synthetic": True,
    "case_id": plan["case_id"],
    "authored_review_status": "CHECKLIST_RECORDED_NOT_INDEPENDENT_TRUTH_CERTIFICATION",
    "structural_gate": report["structural_status"],
    "machine_semantic_status": report["semantic_status"],
    "truth_notice": report["truth_notice"],
    "review_order": [
        "explicit_question_and_contract_decomposition",
        "direct_answer_before_citation",
        "adversarial_omission_comparator_negation_condition_generalization_review",
        "whole_answer_evidence_entailment_human_check",
        "two_sided_conflict_and_derivation_check",
        "absence_status_and_checked_scope_check",
        "structural_schema_as_final_gate"
    ],
    "items": review_rows,
    "machine_findings": report["findings"],
    "change_records": [
        {
            "item_id": "Q2",
            "change": "The authored answer includes Reed-only, exploratory, unadjusted, n=12 per group, comparator direction, units, calculated provenance, and refusal to generalize.",
            "reason": "Condition, comparator, derivation, and unsupported-generalization review."
        },
        {
            "item_id": "Q3",
            "change": "The authored answer distinguishes SEM from a 95% CI, leaves evidence empty, and lists S1, S2, and T1 as checked scope.",
            "reason": "Not-reported integrity; no fabricated evidence or derived CI."
        }
    ],
    "paths": {
        "result": "result.json",
        "answer_matrix": "answer_matrix.json",
        "audit_report": "audit_report.json",
        "semantic_review_json": "semantic_review.json",
        "semantic_review_markdown": "semantic_review.md"
    }
}
(out / "semantic_review.json").write_text(
    json.dumps(review, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
)

lines = [
    "# SYNTHETIC semantic review",
    "",
    "**Entirely fictional example; not real research evidence.**",
    "",
    "Structural gate: **%s**. Machine semantic status: **%s**." % (
        report["structural_status"], report["semantic_status"]
    ),
    "",
    "This authored checklist is not independent truth certification. Exact quote retrieval, schema validity, and required-term presence do not prove whole-answer entailment or completeness.",
    "",
    "## Review protocol",
    "",
]
for step in review["review_order"]:
    lines.append("1. `%s`" % step)
lines.extend(["", "## Item reviews", ""])
for item in review_rows:
    lines.extend([
        "### %s — %s" % (item["item_id"], item["status"]),
        "",
        "**Question:** %s" % item["question"],
        "",
        "**Direct answer:** %s" % item["direct_answer"],
        "",
        "**Evidence role/count:** `%s` / %d" % (item["evidence_role"], item["evidence_count"]),
        "",
        "**Checked scope:** %s" % item["checked_scope"],
        "",
    ])
    for name, note in item["adversarial_review"].items():
        if name == "formula_derived_vs_author_reported" and isinstance(note, dict):
            note = "Formula: %s Inputs: %s Rounding: %s" % (
                note["formula"], "; ".join(note["inputs"]), note["rounding"]
            )
        lines.append("- **%s:** %s" % (name.replace("_", " "), note))
    lines.extend(["- **Residual uncertainty:** %s" % item["residual_uncertainty"], ""])
lines.extend([
    "## Honest not-reported handling",
    "",
    "Q3 has `evidence: []`. Its checked scope enumerates S1, S2, and T1. SEM is not converted to a CI, and no evidence item was fabricated to make the row look supported.",
    "",
    "## Change records",
    "",
])
for change in review["change_records"]:
    lines.append("- **%s:** %s **Reason:** %s" % (change["item_id"], change["change"], change["reason"]))
lines.extend(["", "## Paths", ""])
for name, path in review["paths"].items():
    lines.append("- `%s`: `%s`" % (name, path))
(out / "semantic_review.md").write_text("\n".join(lines) + "\n", encoding="utf-8")

# Required read-back: fail loudly if generated files drift or are malformed.
loaded_matrix = json.loads((out / "answer_matrix.json").read_text(encoding="utf-8"))
loaded_review = json.loads((out / "semantic_review.json").read_text(encoding="utf-8"))
loaded_result = json.loads((out / "result.json").read_text(encoding="utf-8"))
loaded_report = json.loads((out / "audit_report.json").read_text(encoding="utf-8"))
assert set(loaded_result) == {"case_id", "Q1", "Q2", "Q3"}
assert [loaded_result[key]["item_id"] for key in ("Q1", "Q2", "Q3")] == ["Q1", "Q2", "Q3"]
assert len(loaded_matrix["answer_matrix"]["items"]) == 3
assert loaded_result["Q3"]["status"] == "not_reported"
assert loaded_result["Q3"]["evidence"] == []
assert loaded_report["structural_status"] == "PASS"
assert loaded_review["synthetic"] is True
assert (out / "semantic_review.md").read_text(encoding="utf-8").startswith("# SYNTHETIC")
print("Read-back OK: exact Q1/Q2/Q3; 3 matrix rows; Q3 evidence=[]; all five outputs parsed.")
print("Output root: %s" % out.resolve())
PY
