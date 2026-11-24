#!/usr/bin/env bash
# 合成示例 / SYNTHETIC DEMO — 非交互全流程。
# 一切产物写在 $(mktemp -d) 里，绝不写回 bundle。
# 流程: 生成合成案例 → prepare → 自动填 plan → finish → 负向主题指纹测试。
set -euo pipefail

S="$(cd "$(dirname "$0")/.." && pwd)"   # bundle root
TMP="$(mktemp -d)"
IN="$TMP/input"; WORK="$TMP/work"; OUT="$TMP/output"
mkdir -p "$IN" "$WORK" "$OUT"
echo "== tmpdir: $TMP"

echo "== [0/4] generate synthetic case"
python3 "$S/scripts/make_synthetic_case.py" "$IN"

echo "== [1/4] prepare"
python3 "$S/scripts/run_case.py" prepare --input "$IN" --work "$WORK" --output "$OUT"

echo "== [2/4] auto-fill plan (stands in for the agent's creative step)"
python3 "$S/scripts/fill_example_plan.py" --work "$WORK"

echo "== [3/4] finish (build + audit + render + result.json)"
python3 "$S/scripts/run_case.py" finish --input "$IN" --work "$WORK" --output "$OUT"

echo "== [4/4] negative theme-fingerprint test"
# Build a foreign deck with the python-pptx DEFAULT theme (not our custom
# template theme) and audit it against the synthetic template: the theme
# fingerprint must mismatch and overall_pass must be false.
python3 - "$TMP" <<'PYEOF'
import sys
from pptx import Presentation
prs = Presentation()  # default Office theme, NOT the synthetic custom theme
slide = prs.slides.add_slide(prs.slide_masters[0].slide_layouts[1])
slide.shapes.title.text = "foreign-theme deck (negative test)"
prs.save(sys.argv[1] + "/foreign.pptx")
PYEOF
set +e
python3 "$S/scripts/audit_inheritance.py" \
    --deck "$TMP/foreign.pptx" --template "$IN/template.pptx" \
    --inventory "$WORK/template_inventory.json" \
    --out "$TMP/foreign_inheritance.json"
NEG_RC=$?
set -e
python3 - "$TMP/foreign_inheritance.json" <<'PYEOF'
import json, sys
r = json.load(open(sys.argv[1]))
print("negative test: theme_preserved =", r["theme_preserved"],
      "| overall_pass =", r["overall_pass"],
      "| failures =", r["failures"])
assert r["theme_preserved"] is False, "expected theme fingerprint mismatch!"
assert r["overall_pass"] is False, "expected overall_pass=false!"
print("negative test OK: foreign theme correctly flagged")
PYEOF
echo "(audit exit code on foreign deck: $NEG_RC — non-zero is EXPECTED)"

echo
echo "== artifacts (all inside $TMP) =="
find "$OUT" -type f | sort
echo "== result.json status =="
python3 -c "import json;r=json.load(open('$OUT/result.json'));print(r['status']);print(r['summary'])"
echo "== DONE. tmpdir kept for inspection: $TMP"
