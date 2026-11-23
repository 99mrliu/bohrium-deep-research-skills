#!/usr/bin/env bash
# run_example.sh — 合成示例端到端演示：BLOCK（缺字段）→ DELIVER（补全）。
# 用法: bash run_example.sh [输出目录，默认 ./out]
set -uo pipefail

OUT="${1:-./out}"
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(dirname "$HERE")"
IN="$OUT/input"; WORK="$OUT/work"; RES="$OUT/output"

rm -rf "$OUT"
mkdir -p "$IN" "$WORK" "$RES"
cp "$HERE/case.json" "$HERE/task.md" "$HERE/source_excerpt.txt" "$IN/"
cp "$HERE/evidence_map.json" "$WORK/evidence_map.json"

echo "== [1/6] contract_scan：动态解析 output_contract =="
python3 "$ROOT/scripts/contract_scan.py" --case "$IN/case.json" \
  --out "$WORK/contract.json" || exit 1

echo "== [2/6] fill_result --init：尽早写合法的部分 result.json =="
python3 "$ROOT/scripts/fill_result.py" --init --contract "$WORK/contract.json" \
  --result "$RES/result.json" --input-dir "$IN" || exit 1

echo "== [3/6] ROUND 1：缺字段变体（item_bank 被移除），预期 BLOCK =="
# 缺字段变体由本脚本就地生成（examples/ 不额外携带变体文件）
python3 - "$HERE/items.json" "$WORK/items.json" <<'PY'
import json, sys
obj = json.load(open(sys.argv[1], encoding="utf-8"))
obj.pop("item_bank", None)          # 制造缺失：item_bank 不可填充
with open(sys.argv[2], "w", encoding="utf-8") as f:
    json.dump(obj, f, ensure_ascii=False, indent=2, sort_keys=True)
    f.write("\n")
PY
python3 "$ROOT/scripts/fill_result.py" --contract "$WORK/contract.json" \
  --work-dir "$WORK" --result "$RES/result.json" --input-dir "$IN"
python3 "$ROOT/scripts/render_preview.py" --contract "$WORK/contract.json" \
  --result "$RES/result.json" --out-dir "$RES"
python3 "$ROOT/scripts/selfcheck_gate.py" --case "$IN/case.json" \
  --contract "$WORK/contract.json" --result "$RES/result.json" \
  --record "$RES/preview_record.json" --out "$RES/gate_report.json"
RC1=$?
python3 -c "import json;r=json.load(open('$RES/gate_report.json'));print('ROUND1 verdict:',r['verdict']);print('ROUND1 null_fields:',r['null_fields'])"
echo "(round1 gate exit code = $RC1)"

echo "== [4/6] ROUND 2：补全 item_bank，重新填充 =="
cp "$HERE/items.json" "$WORK/items.json"
python3 "$ROOT/scripts/fill_result.py" --contract "$WORK/contract.json" \
  --work-dir "$WORK" --result "$RES/result.json" --input-dir "$IN"

echo "== [5/6] render_preview：SVG + 内置 PNG (+ 可选外部高清 PNG) =="
python3 "$ROOT/scripts/render_preview.py" --contract "$WORK/contract.json" \
  --result "$RES/result.json" --out-dir "$RES"

echo "== [6/6] selfcheck_gate：预期 DELIVER =="
python3 "$ROOT/scripts/selfcheck_gate.py" --case "$IN/case.json" \
  --contract "$WORK/contract.json" --result "$RES/result.json" \
  --record "$RES/preview_record.json" --out "$RES/gate_report.json"
RC2=$?
python3 -c "import json;r=json.load(open('$RES/gate_report.json'));print('ROUND2 verdict:',r['verdict'])"
echo "(round2 gate exit code = $RC2)"

echo "== 产物目录：$RES =="
ls -la "$RES"
