#!/usr/bin/env bash
# 合成示例端到端演示（非正式案例结果）：
#   契约读取 -> 锚点抽取+QC -> 核验预制诊断 -> 收尾 result.json
# 注：curated_diagnosis.json 在真实运行中由 Agent 精读锚定文本产出；
#     本示例为演示机器管线而预制，标注为合成示例。
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
SKILL="$(dirname "$HERE")"
WORK="$HERE/work"
OUT="$HERE/expected"
rm -rf "$WORK"
mkdir -p "$WORK" "$OUT"

python3 "$SKILL/scripts/result_kit.py" init "$HERE/input/case.json" "$OUT/result.json" \
  --note "synthetic example run: contract read"
python3 "$SKILL/scripts/anchor_extract.py" "$HERE/input" "$WORK/anchors"
cp "$WORK/anchors/anchor_map.jsonl" "$WORK/anchors/manifest.json" "$OUT/"
python3 "$SKILL/scripts/verify_quotes.py" "$WORK/anchors/anchor_map.jsonl" \
  "$HERE/curated_diagnosis.json" "$OUT/quote_verification.json"
cp "$HERE/curated_diagnosis.json" "$OUT/diagnosis.json"
python3 "$SKILL/scripts/result_kit.py" final "$HERE/input/case.json" "$OUT/result.json" \
  --status partial --findings 6 --verified 1.0 \
  --note "synthetic example: machine pipeline demo; contract fields diagnosis/editing_plan/fact_source_map intentionally left null to show honest partial"
echo "--- result.json contract_check ---"
python3 -c "import json;print(json.dumps(json.load(open('$OUT/result.json'))['contract_check'],ensure_ascii=False))"
