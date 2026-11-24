#!/bin/bash
# run_example.sh — source-fidelity-firewall 合成示例，一键端到端跑通。
# 模拟 /input、/app/work、/app/output 三段式（本目录下 work_sim/），
# 演示：extract → ground →（注入材料外数字的错误编辑 → guard 捕获）→
#       修复 → guard PASS → make_result。
# macOS /bin/bash + 系统 python3；输出确定性（相对路径、无时间戳）。
set -u
cd "$(dirname "$0")"
BUNDLE="$(cd ../.. && pwd)"
SIM="work_sim"
PY=python3

rm -rf "$SIM"
mkdir -p "$SIM/input" "$SIM/work" "$SIM/output/edited_chapters"
cp -R input/ "$SIM/input/"

CHAPTERS="$SIM/input/chapters"
MATERIALS="$SIM/input/materials"
WORK="$SIM/work"
OUT="$SIM/output"

step() { printf '\n=== %s ===\n' "$1"; }

step "1/6 extract_facts（章节 → facts.json）"
$PY "$BUNDLE/scripts/extract_facts.py" --chapters "$CHAPTERS" \
  --out "$WORK/facts.json" || exit 1

step "2/6 ground_evidence（逐条回源 → evidence_map.json）"
$PY "$BUNDLE/scripts/ground_evidence.py" --facts "$WORK/facts.json" \
  --materials "$MATERIALS" --out "$WORK/evidence_map.json" || exit 1

step "3/6 模拟编辑：执行工单改写，但故意注入材料外数字 92%"
mkdir -p "$WORK/edited"
cp "$CHAPTERS"/*.md "$WORK/edited/"
TARGET="$WORK/edited/03_results.md" $PY - <<'PYEOF'
import os
p = os.environ["TARGET"]
s = open(p, encoding="utf-8").read()
old = "全电池在 200 次循环后容量保持率为 85% [1]。"
new = "全电池在 200 次循环后容量保持率高达 92%，远优于同类报道。"
assert old in s, "faulty-edit anchor not found"
open(p, "w", encoding="utf-8").write(s.replace(old, new))
print("injected fault: 85% -> 92%（材料外数字）")
PYEOF

step "4/6 fact_diff_guard（应捕获注入错误，退出码 1）"
if $PY "$BUNDLE/scripts/fact_diff_guard.py" --before "$CHAPTERS" \
   --after "$WORK/edited" --evidence "$WORK/evidence_map.json" \
   --materials "$MATERIALS" --out "$OUT/guard_report_injected-fault.json"; then
  echo "ERROR: guard 未捕获注入错误，示例失败" >&2
  exit 1
else
  echo "OK: guard 如期捕获注入错误（退出码 $?）→ guard_report_injected-fault.json"
fi

step "5/6 修复编辑（回到可回源的 85% 表述）并重跑 guard（应 PASS）"
TARGET="$WORK/edited/03_results.md" $PY - <<'PYEOF'
import os
p = os.environ["TARGET"]
s = open(p, encoding="utf-8").read()
old = "全电池在 200 次循环后容量保持率高达 92%，远优于同类报道。"
new = "循环 200 次后，全电池容量保持率仍维持在 85% [1]，与实验记录一致。"
assert old in s, "fix anchor not found"
open(p, "w", encoding="utf-8").write(s.replace(old, new))
print("fixed: 恢复为材料可支持的表述")
PYEOF
$PY "$BUNDLE/scripts/fact_diff_guard.py" --before "$CHAPTERS" \
  --after "$WORK/edited" --evidence "$WORK/evidence_map.json" \
  --materials "$MATERIALS" --out "$OUT/guard_report.json" || exit 1

step "6/6 make_result（按 output_contract 装配 result.json）"
cat > "$WORK/changes.json" <<'JSON'
[
  {
    "id": 1,
    "title": "结果句改写",
    "target": "03_results.md",
    "before": "全电池在 200 次循环后容量保持率为 85% [1]。",
    "after": "循环 200 次后，全电池容量保持率仍维持在 85% [1]，与实验记录一致。",
    "guard": "PASS",
    "note": "SYNTHETIC EXAMPLE — 合成示例，非正式案例结果"
  }
]
JSON
$PY "$BUNDLE/scripts/make_result.py" --case "$SIM/input/case.json" \
  --evidence "$WORK/evidence_map.json" --guard "$OUT/guard_report.json" \
  --edited-chapters "$WORK/edited" --changes "$WORK/changes.json" \
  --note "SYNTHETIC EXAMPLE — 合成示例，非正式案例结果" \
  --out "$OUT/result.json" || exit 1

cp "$WORK/facts.json" "$WORK/evidence_map.json" "$OUT/"
cp "$WORK"/edited/*.md "$OUT/edited_chapters/"

step "与 expected/ 冻结产物对比"
if [ ! -d expected ] || [ -z "$(ls -A expected 2>/dev/null)" ]; then
  echo "expected/ 为空：首次固化，请将 $OUT 内容复制进 expected/ 并目检。"
  exit 0
fi
if diff -r expected "$OUT"; then
  echo "EXAMPLE PASS: 输出与 expected/ 完全一致"
else
  echo "EXAMPLE FAIL: 输出与 expected/ 不一致" >&2
  exit 1
fi
