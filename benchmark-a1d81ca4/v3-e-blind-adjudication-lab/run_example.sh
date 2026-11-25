#!/usr/bin/env bash
# Run from the bundle root: bash run_example.sh [optional-output-directory]
set -euo pipefail

BUNDLE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
INPUT_DIR="$BUNDLE_DIR/examples/input"
OUT_DIR="${1:-$(mktemp -d "${TMPDIR:-/tmp}/v3-e-blind-adjudication.XXXXXX")}"
mkdir -p "$OUT_DIR/output" "$OUT_DIR/work" "$OUT_DIR/negative" "$OUT_DIR/no-human/output"
export PYTHONDONTWRITEBYTECODE=1

# Create contract-complete early partials directly from case.json, never task prose.
python3 "$BUNDLE_DIR/scripts/finalize.py" \
  --case "$INPUT_DIR/case.json" \
  --output-dir "$OUT_DIR/output" \
  --early-partial
python3 "$BUNDLE_DIR/scripts/finalize.py" \
  --case "$INPUT_DIR/case.json" \
  --output-dir "$OUT_DIR/no-human/output" \
  --early-partial

# Primary no-human path: exactly four source-conditioned items are sufficient for success.
python3 "$BUNDLE_DIR/scripts/finalize.py" \
  --case "$INPUT_DIR/case.json" \
  --item-bank "$INPUT_DIR/item_bank.json" \
  --source-evidence "$INPUT_DIR/source_evidence.json" \
  --output-dir "$OUT_DIR/no-human/output"
python3 - "$INPUT_DIR/case.json" "$OUT_DIR/no-human/output/result.json" <<'PY'
import json
import sys
with open(sys.argv[1], encoding="utf-8") as handle:
    fields = list(json.load(handle)["output_contract"])
with open(sys.argv[2], encoding="utf-8") as handle:
    result = json.load(handle)
assert set(fields) == set(result), (fields, list(result))
assert all(result[field] is not None for field in fields)
assert result["status"] == "success", result["summary"]
assert result["summary"]["main_task_status"] == "success"
assert result["summary"]["items_completed"] == 4
assert result["review_status"] == "not_conducted_no_human_verdicts"
assert result["diagnostics"]["review_status"] == "not_conducted_no_human_verdicts"
assert len(result["item_bank"]["items"]) == 4
assert all(item["reference_answer"] and set(item["rubric"]) == {"0", "1", "2"} and item["evidence_refs"] for item in result["item_bank"]["items"])
assert result["sources"]["sources"] and result["uncertainty"] and result["change_records"]
assert result["adjudication"]["status"] == "not_applicable"
assert result["adjudication"]["review_status"] == "not_conducted_no_human_verdicts"
assert result["adjudication"]["human_verdicts"] == []
assert result["agreement"]["status"] == "not_applicable"
assert result["agreement"]["counts"]["comparable_items"] == 0
assert result["agreement"]["cohen_kappa_unweighted"] == {
    "status": "not_computed_no_human_verdicts",
    "value": None,
    "reason": "No actual human reviewer verdict artifacts were supplied; optional review was not conducted.",
}
assert result["failures"] == [] and result["targeted_probes"] == []
assert len(result["raw_agreements"]) == 4
assert all(row["comparison_status"] == "not_applicable_no_human_verdicts" for row in result["raw_agreements"])
print("No-human primary path verified: four items export success, every contract field is populated, review not conducted, and no human kappa is claimed.")
PY

# Verify list/direct-map/properties and dictionary field-list contract forms.
python3 "$BUNDLE_DIR/tests/verify_contracts.py" \
  --output-dir "$OUT_DIR/contract-shapes"

# Preserve the complete synthetic positive independent-review example.
python3 "$BUNDLE_DIR/scripts/prepare_review.py" \
  --item-bank "$INPUT_DIR/item_bank.json" \
  --candidate-outputs "$INPUT_DIR/candidate_outputs.json" \
  --auto-scores "$INPUT_DIR/auto_scores.json" \
  --source-evidence "$INPUT_DIR/source_evidence.json" \
  --reviewers "$INPUT_DIR/reviewers.json" \
  --output-dir "$OUT_DIR/work/prepare"

python3 "$BUNDLE_DIR/tests/verify_blinding.py" \
  --review-dir "$OUT_DIR/work/prepare" \
  --reviewers "$INPUT_DIR/reviewers.json" \
  --auto-scores "$INPUT_DIR/auto_scores.json" \
  --candidate-outputs "$INPUT_DIR/candidate_outputs.json"

python3 "$BUNDLE_DIR/scripts/adjudicate.py" \
  --review-manifest "$OUT_DIR/work/prepare/prepare_manifest.json" \
  --human-verdicts "$INPUT_DIR/human_verdicts_reviewer_1.jsonl" \
  --human-verdicts "$INPUT_DIR/human_verdicts_reviewer_2.jsonl" \
  --adjudications "$INPUT_DIR/adjudications.jsonl" \
  --deadline "2026-03-01T00:00:00Z" \
  --output-dir "$OUT_DIR/work/adjudication"

python3 "$BUNDLE_DIR/scripts/agreement.py" \
  --auto-scores "$INPUT_DIR/auto_scores.json" \
  --adjudication "$OUT_DIR/work/adjudication/adjudication.json" \
  --output-dir "$OUT_DIR/work/agreement"

python3 "$BUNDLE_DIR/scripts/finalize.py" \
  --case "$INPUT_DIR/case.json" \
  --item-bank "$INPUT_DIR/item_bank.json" \
  --adjudication "$OUT_DIR/work/adjudication/adjudication.json" \
  --agreement "$OUT_DIR/work/agreement/agreement.json" \
  --failures "$OUT_DIR/work/agreement/failures.json" \
  --targeted-probes "$OUT_DIR/work/agreement/targeted_probes.json" \
  --source-evidence "$INPUT_DIR/source_evidence.json" \
  --output-dir "$OUT_DIR/output"

python3 - "$INPUT_DIR/case.json" "$OUT_DIR/output/result.json" <<'PY'
import json
import sys
with open(sys.argv[1], encoding="utf-8") as handle:
    fields = list(json.load(handle)["output_contract"])
with open(sys.argv[2], encoding="utf-8") as handle:
    result = json.load(handle)
assert result["status"] == "success", result["summary"]
assert result["review_status"] == "conducted"
assert set(fields) == set(result), (fields, list(result))
assert all(result[field] is not None for field in fields)
assert len(result["item_bank"]["items"]) == 4
assert result["summary"]["pairwise_disagreements"] >= 1
assert result["summary"]["automatic_final_mismatches"] == 2
assert len(result["failures"]) == 2
assert len(result["targeted_probes"]) == 2
assert all(probe["reason"] and probe["expected_fix"] and probe["retest_item_ids"] for probe in result["targeted_probes"])
assert all(failure["evidence_refs"] and failure["final_score_basis"]["rationale"] for failure in result["failures"])
assert all(probe["source_evidence_refs"] for probe in result["targeted_probes"])
assert {row["item_id"] for row in result["raw_agreements"] if not row["raw_agreement_match"]} == {"DRAFT-002", "DRAFT-004"}
print("Positive workflow verified: primary success plus conducted synthetic review, disagreement adjudication, and mismatch failures/probes.")
PY

# Negative control 1: the leak detector must reject a deliberately modified packet.
mkdir -p "$OUT_DIR/negative/leaky/review_packets" "$OUT_DIR/negative/leaky/private"
cp "$OUT_DIR/work/prepare/review_packets/packet-01.json" "$OUT_DIR/negative/leaky/review_packets/packet-01.json"
cp "$OUT_DIR/work/prepare/private/private_key.json" "$OUT_DIR/negative/leaky/private/private_key.json"
python3 - "$OUT_DIR/negative/leaky/review_packets/packet-01.json" <<'PY'
import json
import sys
path = sys.argv[1]
with open(path, encoding="utf-8") as handle:
    packet = json.load(handle)
packet["items"][0]["auto_score"] = 2
packet["items"][0]["reviewer_id"] = "synthetic-reviewer-alpha"
with open(path, "w", encoding="utf-8") as handle:
    json.dump(packet, handle, ensure_ascii=False, indent=2)
PY
set +e
python3 "$BUNDLE_DIR/tests/verify_blinding.py" \
  --review-dir "$OUT_DIR/negative/leaky" \
  --reviewers "$INPUT_DIR/reviewers.json" \
  --auto-scores "$INPUT_DIR/auto_scores.json" \
  --candidate-outputs "$INPUT_DIR/candidate_outputs.json"
LEAK_RC=$?
set -e
if [[ "$LEAK_RC" -ne 1 ]]; then
  echo "Expected deliberately leaky packet verification to exit 1; got $LEAK_RC" >&2
  exit 1
fi
echo "Negative leak control verified: reviewer identity and automatic-score injection are rejected."

# Negative control 2: unresolved review stays partial while the complete item bank succeeds.
set +e
python3 "$BUNDLE_DIR/scripts/adjudicate.py" \
  --review-manifest "$OUT_DIR/work/prepare/prepare_manifest.json" \
  --human-verdicts "$INPUT_DIR/human_verdicts_reviewer_1.jsonl" \
  --human-verdicts "$INPUT_DIR/human_verdicts_reviewer_2.jsonl" \
  --adjudications "$BUNDLE_DIR/examples/negative/adjudications_unresolved.jsonl" \
  --deadline "2026-03-01T00:00:00Z" \
  --output-dir "$OUT_DIR/negative/adjudication"
UNRESOLVED_RC=$?
set -e
if [[ "$UNRESOLVED_RC" -ne 3 ]]; then
  echo "Expected unresolved adjudication to exit 3; got $UNRESOLVED_RC" >&2
  exit 1
fi
python3 "$BUNDLE_DIR/scripts/agreement.py" \
  --auto-scores "$INPUT_DIR/auto_scores.json" \
  --adjudication "$OUT_DIR/negative/adjudication/adjudication.json" \
  --output-dir "$OUT_DIR/negative/agreement"
python3 "$BUNDLE_DIR/scripts/finalize.py" \
  --case "$INPUT_DIR/case.json" \
  --item-bank "$INPUT_DIR/item_bank.json" \
  --adjudication "$OUT_DIR/negative/adjudication/adjudication.json" \
  --agreement "$OUT_DIR/negative/agreement/agreement.json" \
  --failures "$OUT_DIR/negative/agreement/failures.json" \
  --targeted-probes "$OUT_DIR/negative/agreement/targeted_probes.json" \
  --source-evidence "$INPUT_DIR/source_evidence.json" \
  --output-dir "$OUT_DIR/negative/output"

python3 - "$INPUT_DIR/case.json" "$OUT_DIR/negative/output/result.json" "$OUT_DIR/negative/agreement/agreement.json" <<'PY'
import json
import sys
with open(sys.argv[1], encoding="utf-8") as handle:
    fields = list(json.load(handle)["output_contract"])
with open(sys.argv[2], encoding="utf-8") as handle:
    result = json.load(handle)
with open(sys.argv[3], encoding="utf-8") as handle:
    agreement = json.load(handle)
assert result["status"] == "success"
assert result["summary"]["main_task_status"] == "success"
assert result["review_status"] == "partial"
assert set(fields) == set(result)
assert all(result[field] is not None for field in fields)
assert result["summary"]["unresolved_items"] == 1
assert result["summary"]["review_limitations"]
assert result["adjudication"]["status"] == "partial"
assert result["adjudication"]["per_item"][2]["final_score"] is None
assert result["agreement"]["status"] == "partial"
assert agreement["counts"]["comparable_items"] == 3
assert [row["item_id"] for row in agreement["unresolved_missing"]] == ["DRAFT-003"]
kappa = agreement["cohen_kappa_unweighted"]
assert kappa["status"] == "not_computed_insufficient_support"
assert kappa["value"] is None
print("Negative unresolved control verified: review remains partial with undefined kappa, while the completed four-item primary task remains success.")
PY

python3 "$BUNDLE_DIR/tests/static_audit.py"

cat <<EOF
No-human path, full synthetic positive/negative examples, contract shapes, and static audit completed.
No-human successful primary result: $OUT_DIR/no-human/output/result.json
Contract-shape results: $OUT_DIR/contract-shapes
Review packets: $OUT_DIR/work/prepare/review_packets
Separate private key: $OUT_DIR/work/prepare/private/private_key.json
Adjudication: $OUT_DIR/work/adjudication/adjudication.json
Agreement/failures/probes: $OUT_DIR/work/agreement
Final reviewed result: $OUT_DIR/output/result.json
Unresolved-review / successful-primary result: $OUT_DIR/negative/output/result.json
EXAMPLE_OUTPUT_DIR=$OUT_DIR
EOF
