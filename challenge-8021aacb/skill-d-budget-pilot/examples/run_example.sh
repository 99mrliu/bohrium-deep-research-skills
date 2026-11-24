#!/usr/bin/env bash
# 合成示例端到端演示（非正式案例结果）：
#   计划 -> 初始化 -> 阶段打点 -> 质量门阻断（契约字段未填）-> 修复 -> 质量门通过
set -uo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
SKILL="$(dirname "$HERE")"
WORK="$HERE/work"
OUT="$HERE/expected"
rm -rf "$WORK"
mkdir -p "$WORK" "$OUT"

python3 "$SKILL/scripts/plan_budget.py" "$HERE/input" "$OUT/plan.json"
python3 "$SKILL/scripts/checkpoint.py" init "$HERE/input/case.json" "$OUT/result.json"
python3 "$SKILL/scripts/checkpoint.py" mark "$OUT/result.json" --phase contract_and_inventory \
  --note "契约两字段已抄录" --requests-used 2 --seconds-used 30
python3 "$SKILL/scripts/checkpoint.py" mark "$OUT/result.json" --phase extraction \
  --note "合成稿件 4 段可读" --requests-used 3 --seconds-used 90
python3 "$SKILL/scripts/checkpoint.py" mark "$OUT/result.json" --phase diagnosis_core \
  --note "演示：跳过真实诊断" --requests-used 20 --seconds-used 400 \
  --degraded "演示降级打点：诊断内容非本示例目的"
python3 "$SKILL/scripts/checkpoint.py" mark "$OUT/result.json" --phase deliverables \
  --note "演示产物已写" --requests-used 24 --seconds-used 500

# 演示产物（占位）
printf '# 合成示例诊断（占位）\n' > "$OUT/diagnosis.md"
printf '# 合成示例编辑计划（占位）\n' > "$OUT/editing_plan.md"

echo "=== 第一次质量门（预期 BLOCK：契约字段未填）==="
python3 "$SKILL/scripts/quality_gate.py" "$OUT/result.json" "$OUT" "$OUT/audit_blocked.md"
echo "exit=$?"

# 修复：填契约字段并收尾 status
python3 - "$OUT/result.json" <<'PY'
import json, sys
p = sys.argv[1]
d = json.load(open(p, encoding='utf-8'))
d['diagnosis'] = 'diagnosis.md'
d['editing_plan'] = 'editing_plan.md'
d['status'] = 'ok'
d['uncertainty'] = []
d['change_record'] = [{'action': 'fill contract fields', 'by': 'example script'}]
json.dump(d, open(p, 'w', encoding='utf-8'), ensure_ascii=False, indent=2)
PY
python3 "$SKILL/scripts/checkpoint.py" mark "$OUT/result.json" --phase finalize \
  --note "契约字段已填，status=ok" --requests-used 26 --seconds-used 560

echo "=== 第二次质量门（预期 PASS）==="
python3 "$SKILL/scripts/quality_gate.py" "$OUT/result.json" "$OUT" "$OUT/audit.md"
echo "exit=$?"
python3 "$SKILL/scripts/checkpoint.py" status "$OUT/result.json"
