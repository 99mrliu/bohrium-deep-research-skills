#!/usr/bin/env bash
# 合成示例端到端演示（非正式案例结果）：
#   契约播种 -> 六维线索扫描 -> 覆盖门（演示缺维与空话两类拦截）
set -uo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
SKILL="$(dirname "$HERE")"
WORK="$HERE/work"
OUT="$HERE/expected"
rm -rf "$WORK"
mkdir -p "$WORK" "$OUT"

python3 "$SKILL/scripts/contract_seed.py" "$HERE/input/case.json" "$OUT/result.json" "$WORK/diagnosis.json"
python3 "$SKILL/scripts/dimension_scan.py" "$HERE/input/ms.txt" \
  "$SKILL/references/cue_lexicon.json" "$OUT/candidates.json"
cp "$HERE/curated_diagnosis.json" "$WORK/diagnosis.json"
# 覆盖门：预期退出码 1（缺「重复内容」维 + F006 空话），报告照常归档
python3 "$SKILL/scripts/coverage_gate.py" "$WORK/diagnosis.json" "$OUT/coverage_report.json"
echo "coverage_gate exit code: $? (预期 1，演示拦截)"
