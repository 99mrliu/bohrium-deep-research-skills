#!/usr/bin/env bash
# run_example.sh — 合成示例端到端演示（非正式测试案例）。
# 全程在 $(mktemp -d) 临时目录运行，绝不写回 bundle。
set -euo pipefail

SKILL_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TMP="$(mktemp -d)"
echo "============================================================"
echo "[example] 合成示例（synthetic-demo-05），临时目录: $TMP"
echo "============================================================"

echo "--- [1/4] 生成合成案例（template.pptx + paper.pdf + case.json + task.md）"
python3 "$SKILL_DIR/scripts/make_synthetic_case.py" --outdir "$TMP/input"

echo "--- [2/4] prepare：抽取论文/模板，预填 storyline + slide_plan 骨架"
python3 "$SKILL_DIR/scripts/run_case.py" prepare \
  --input "$TMP/input" --work "$TMP/work" --output "$TMP/output"

echo "--- [3/4] 自动填写 storyline.json + slide_plan.json（合成示例专用）"
python3 "$SKILL_DIR/scripts/fill_example_plan.py" --work "$TMP/work"

echo "--- [4/4] finish：plan_lint 门禁 → build deck.pptx → 导出 PDF/PNG → result.json"
python3 "$SKILL_DIR/scripts/run_case.py" finish \
  --input "$TMP/input" --work "$TMP/work" --output "$TMP/output"

echo "============================================================"
echo "[example] 产物清单（$TMP/output）:"
find "$TMP/output" -type f | sort | while read -r f; do
  printf "  %8d  %s\n" "$(stat -f%z "$f")" "${f#"$TMP"/}"
done

echo "============================================================"
echo "[example] plan_lint 计时表（R6_time_budget）:"
python3 - "$TMP/output/plan_lint_report.json" <<'PY'
import json, sys
rep = json.load(open(sys.argv[1], encoding="utf-8"))
print("overall:", rep["overall"], "| fails:", rep["fails"], "| warns:", rep["warns"])
r6 = next(r for r in rep["rules"] if r["rule"] == "R6_time_budget")["details"]
print(f"duration={r6['duration_min']}min ({r6['duration_source']}) "
      f"budget={r6['budget_seconds']}s total={r6['total_seconds']}s")
for t in r6["timeline"]:
    print(f"  slide {t['slide']} [{t['kind']:<10}] ~{t['seconds']:>3}s  累计 {t['cumulative_s']:>3}s  {t['title'][:24]}")
PY

echo "[example] OK — 所有产物在临时目录，未写回 bundle。"
