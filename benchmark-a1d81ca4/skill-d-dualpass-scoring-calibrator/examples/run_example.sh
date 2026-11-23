#!/usr/bin/env bash
set -euo pipefail
export PYTHONDONTWRITEBYTECODE=1

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
EXAMPLES="$ROOT/examples"
OUT="${1:-./out}"
WORK="$OUT/work"
FINAL="$OUT/output"
mkdir -p "$WORK" "$FINAL"
SOURCE_INPUT="$WORK/input"
mkdir -p "$SOURCE_INPUT"
cp "$EXAMPLES/source_excerpt.txt" "$SOURCE_INPUT/source_excerpt.txt"

echo "[0] 初始化合法部分 result.json"
python3 "$ROOT/scripts/score_pass.py" --init \
  --case "$EXAMPLES/case.json" --output-dir "$FINAL"

echo "[1] 编译 rubric"
python3 "$ROOT/scripts/rubric_compile.py" \
  --case "$EXAMPLES/case.json" --task "$EXAMPLES/task.md" \
  --source-root "$SOURCE_INPUT" --output "$WORK/rubric.json"

echo "[2] 通道 1：机判 + pass1 语义理由"
python3 "$ROOT/scripts/score_pass.py" \
  --case "$EXAMPLES/case.json" --task "$EXAMPLES/task.md" \
  --rubric "$WORK/rubric.json" --items "$EXAMPLES/agent_items.json" \
  --semantic "$EXAMPLES/pass1_semantic.json" --source-root "$SOURCE_INPUT" \
  --output "$WORK/pass1_scores.json"

echo "[3] 通道 2：盲态复评，输出一致率、kappa 与分歧"
python3 "$ROOT/scripts/blind_rescore.py" \
  --case "$EXAMPLES/case.json" --task "$EXAMPLES/task.md" \
  --rubric "$WORK/rubric.json" --items "$EXAMPLES/agent_items.json" \
  --semantic "$EXAMPLES/pass2_semantic.json" --source-root "$SOURCE_INPUT" \
  --pass1 "$WORK/pass1_scores.json" --output "$WORK/pass2_scores.json" \
  --agreement-out "$WORK/agreement_raw.json" \
  --disagreements-out "$WORK/disagreements.json"

echo "[4] 裁决：第一条记录缺 rationale，被拒绝；第二条补全并清零 pending"
python3 "$ROOT/scripts/adjudicate.py" \
  --case "$EXAMPLES/case.json" --pass1 "$WORK/pass1_scores.json" \
  --pass2 "$WORK/pass2_scores.json" --agreement "$WORK/agreement_raw.json" \
  --disagreements "$WORK/disagreements.json" \
  --adjudications "$EXAMPLES/adjudication.json" --items "$EXAMPLES/agent_items.json" \
  --source-root "$SOURCE_INPUT" --final-out "$WORK/final_scores.json" \
  --report-out "$WORK/agreement_report.md" --result "$FINAL/result.json" \
  --human-review-out "$WORK/human_review.md"

echo "[5] 摘要"
python3 - "$WORK" "$FINAL/result.json" <<'PY'
import json
import sys
work, result_path = sys.argv[1], sys.argv[2]
with open(work + "/agreement_raw.json", encoding="utf-8") as fh:
    agreement = json.load(fh)
with open(work + "/disagreements.json", encoding="utf-8") as fh:
    disagreements = json.load(fh)
with open(work + "/final_scores.json", encoding="utf-8") as fh:
    final = json.load(fh)
with open(result_path, encoding="utf-8") as fh:
    result = json.load(fh)
print(json.dumps({
    "n_pairs": agreement["n_pairs"],
    "observed_agreement": agreement["observed_agreement"],
    "expected_agreement": agreement["expected_agreement"],
    "cohens_kappa": agreement["cohens_kappa"],
    "disagreements": disagreements["disagreements"],
    "pending_count": final["pending_count"],
    "result_status": result["status"],
    "result_path": result_path,
}, ensure_ascii=False, indent=2, sort_keys=True))
PY

echo "完成。工作产物：$WORK；最终交付：$FINAL/result.json"
