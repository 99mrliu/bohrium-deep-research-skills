#!/usr/bin/env bash
# lint_negative_demo.sh — 负例演示（合成示例）：
# 在临时目录的计划副本中对调 method 与 results 两页（使 results 先于 method），
# plan_lint.py 必须 fail 并精确指出违规页。预期退出码：本脚本在门禁按预期失败时返回 0。
set -uo pipefail

SKILL_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TMP="$(mktemp -d)"
echo "[negative-demo] 临时目录: $TMP"

python3 "$SKILL_DIR/scripts/make_synthetic_case.py" --outdir "$TMP/input" >/dev/null
python3 "$SKILL_DIR/scripts/run_case.py" prepare \
  --input "$TMP/input" --work "$TMP/work" --output "$TMP/output" >/dev/null
python3 "$SKILL_DIR/scripts/fill_example_plan.py" --work "$TMP/work" >/dev/null

echo "[negative-demo] 在计划副本中对调 method 页与 results 页……"
python3 - "$TMP" <<'PY'
import json, pathlib, sys
plan_p = pathlib.Path(sys.argv[1]) / "work" / "slide_plan.json"
plan = json.loads(plan_p.read_text(encoding="utf-8"))
kinds = [s["kind"] for s in plan["slides"]]
i, j = kinds.index("method"), kinds.index("results")
plan["slides"][i], plan["slides"][j] = plan["slides"][j], plan["slides"][i]
plan_p.write_text(json.dumps(plan, ensure_ascii=False, indent=2), encoding="utf-8")
print(f"  已把 slide {i+1} ({kinds[i]}) 与 slide {j+1} ({kinds[j]}) 对调："
      f"现在 slide {i+1}=results、slide {j+1}=method（叙事顺序被破坏）")
PY

echo "[negative-demo] 运行 plan_lint.py（预期 fail）:"
python3 "$SKILL_DIR/scripts/plan_lint.py" \
  --work "$TMP/work" --output "$TMP/output" --input "$TMP/input"
RC=$?

echo "------------------------------------------------------------"
if [ "$RC" -eq 0 ]; then
  echo "[negative-demo] 失败：lint 未检出顺序违规（应 fail 却 pass）"
  exit 1
fi
echo "[negative-demo] R5_order 违规详情（精确到页）:"
python3 - "$TMP/output/plan_lint_report.json" <<'PY'
import json, sys
rep = json.load(open(sys.argv[1], encoding="utf-8"))
print("overall:", rep["overall"], "| fails:", rep["fails"])
r5 = next(r for r in rep["rules"] if r["rule"] == "R5_order")
for p in r5["details"].get("problems", []):
    print("  ✗", p)
PY
echo "[negative-demo] 成功：门禁按预期失败 (plan_lint exit=$RC)，构建被拒绝。"
