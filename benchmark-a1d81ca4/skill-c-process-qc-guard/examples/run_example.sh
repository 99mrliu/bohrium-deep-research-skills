#!/usr/bin/env bash
# 合成示例（SYNTHETIC EXAMPLE）端到端演示：process-qc-guard 全流程。
# 用法：bash run_example.sh [输出目录]（默认 ./out）
set -euo pipefail

OUT="${1:-./out}"
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$HERE/.." && pwd)"
WORK="$OUT/work"
OUTPUT="$OUT/output"
mkdir -p "$WORK" "$OUTPUT"

echo "== [0] init_run：预检 + 预算安全网骨架（result.json 立即就位）=="
python3 "$ROOT/scripts/init_run.py" --input-dir "$HERE" --work-dir "$WORK" --output-dir "$OUTPUT"

echo "== [1] 模拟 agent 起草（answers_draft.json 故意留空答案 + 缺证据）=="
cp "$HERE/answers_draft.json" "$WORK/answers.json"
python3 "$ROOT/scripts/checkpoint.py" --work-dir "$WORK" save --stage draft \
  --note "agent 初稿（故意缺陷演示）" \
  --dep "$HERE/task.md" --dep "$HERE/source_excerpt.txt" \
  --out "$WORK/answers.json"

echo "== [2] 失败探针：预期检出 P01 空答案 + P04 缺证据（退出码=命中数）=="
set +e
python3 "$ROOT/scripts/probe_failures.py" --input-dir "$HERE" --work-dir "$WORK" --output-dir "$OUTPUT"
echo "probes(draft) exit=$?（>0 表示命中数，属预期）"
set -e

echo "== [3] 修复为 answers_fixed.json，重跑探针（预期 0 命中）=="
cp "$HERE/answers_fixed.json" "$WORK/answers.json"
python3 "$ROOT/scripts/checkpoint.py" --work-dir "$WORK" save --stage fix \
  --note "修复空答案与证据锚点，q2 按诚实标记作答" \
  --dep "$HERE/task.md" --dep "$HERE/source_excerpt.txt" \
  --out "$WORK/answers.json"
python3 "$ROOT/scripts/probe_failures.py" --input-dir "$HERE" --work-dir "$WORK" --output-dir "$OUTPUT"

echo "== [4a] 复跑一致性：确定性复制命令（预期 STABLE）=="
mkdir -p "$WORK/derived"
cp "$HERE/source_excerpt.txt" "$WORK/derived/source_copy.txt"
python3 "$ROOT/scripts/rerun_consistency.py" --work-dir "$WORK" --tag stable \
  --cmd "copy-demo | cp '$HERE/source_excerpt.txt' '$WORK/derived/source_copy.txt' | derived/source_copy.txt"

echo "== [4b] 复跑一致性：注入 wall-clock 时间戳漂移（预期 DRIFT，退出码 3）=="
set +e
python3 "$ROOT/scripts/rerun_consistency.py" --work-dir "$WORK" --tag drift --inject-drift
echo "consistency(drift) exit=$?（3 表示检出 DRIFT，属预期）"
set -e

echo "== [5] 导出：checkpoint status 汇总 + probes 结果 → 刷新 result.json =="
python3 "$ROOT/scripts/checkpoint.py" --work-dir "$WORK" export \
  --input-dir "$HERE" --output-dir "$OUTPUT"
python3 "$ROOT/scripts/checkpoint.py" --work-dir "$WORK" status

echo "== 完成。产物位于 $OUT（work/ 与 output/result.json）=="
