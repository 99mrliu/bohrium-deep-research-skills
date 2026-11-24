#!/usr/bin/env bash
# run_example.sh — 合成示例（非正式案例数据）全流程运行：v1/v2/v3 三版本。
# 可从任意 cwd 运行；脚本用自身位置定位 ../../scripts 与 references。
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SCRIPTS="$(cd "$HERE/../../scripts" && pwd)"
OUT="$HERE/output"
PY="${PYTHON:-python3}"
mkdir -p "$OUT"

echo "== 1. inspect case =="
"$PY" "$SCRIPTS/inspect_case.py" "$HERE/case.json" "$OUT/inspect_case_map.json"

for V in v1 v2 v3; do
  echo "== 2. [$V] normalize =="
  "$PY" "$SCRIPTS/normalize_entities.py" "$HERE/requirements_$V.json" "$OUT/requirements_${V}_normalized.json"
  echo "== 3. [$V] match resources =="
  "$PY" "$SCRIPTS/match_resources.py" "$OUT/requirements_${V}_normalized.json" "$HERE/case.json" "$OUT/match_$V.json"
  echo "== 4. [$V] check booking =="
  "$PY" "$SCRIPTS/check_booking.py" "$HERE/requirements_$V.json" "$HERE/case.json" "$OUT/booking_$V.json"
  echo "== 5. [$V] check samples =="
  "$PY" "$SCRIPTS/check_samples.py" "$HERE/requirements_$V.json" "$HERE/case.json" "$OUT/samples_$V.json"
done

echo "== 6. assemble result =="
"$PY" "$SCRIPTS/assemble_result.py" --case "$HERE/case.json" --artifacts "$OUT" \
  --out "$OUT/result.json" --status complete \
  --note "run_example.sh 全流程运行（合成示例 v1/v2/v3）"

echo "== 完成：产物在 $OUT =="
