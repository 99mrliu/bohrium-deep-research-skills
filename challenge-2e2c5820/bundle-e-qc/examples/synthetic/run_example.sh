#!/usr/bin/env bash
# run_example.sh — bundle-e-qc 合成示例全链路演示（正例 pipeline + 负例 lint 演示）。
# 在本目录内运行：bash run_example.sh   （cwd 无关，内部全部使用绝对路径）
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SCRIPTS="$HERE/../../scripts"
OUT="$HERE/output"
CASE="$HERE/case.json"
PY=python3

mkdir -p "$OUT"

echo "== 步骤0：parse_contract（契约解析 + honest-partial 骨架）=="
"$PY" "$SCRIPTS/parse_contract.py" "$CASE" "$OUT"

echo "== 步骤0.5：骨架立即落地为 result.json（自第一分钟起 partial）=="
cp "$OUT/result.skeleton.json" "$OUT/result.json"

echo "== 步骤1-3（演示）：将合成审查结论 merge 进 result.json =="
"$PY" - "$OUT/result.json" <<'PYEOF'
import json, sys, datetime
path = sys.argv[1]
with open(path, encoding="utf-8") as f:
    r = json.load(f)
now = datetime.datetime.now().isoformat(timespec="seconds")
r.update({
  "verdict_summary": "plan_v1 可行；plan_v2 有条件可行（压缩表征轮次并确认周末机时）；plan_v3 不可行。推荐 plan_v2。",
  "per_plan_verdicts": [
    {"plan_id": "plan_v1", "verdict": "可行", "conditions": []},
    {"plan_id": "plan_v2", "verdict": "有条件可行",
     "conditions": ["XRD 表征由 4 轮压缩为 2 轮（机时 36h→30h）",
                    "确认手套箱周末时段可预订后再锁定第 3 周排期"]},
    {"plan_id": "plan_v3", "verdict": "不可行", "conditions": []}
  ],
  "resource_check": {
    "手套箱机时_小时": {"需求": 30, "合同上限": 32, "满足": True},
    "预算_元": {"需求": 18600, "合同上限": 20000, "满足": True},
    "核算": "手套箱 30h x 500 元/h = 15000 元；XRD 8h x 450 元/h = 3600 元；合计 18600 元"
  },
  "budget_estimate_cny": 18600.0,
  "timeline_feasible": True,
  "risks": ["周末机时不可预订则 plan_v2 排期顺延一周",
            "表征轮次压缩后统计功效下降，需在正式报告中声明"],
  "recommended_plan_version": "plan_v2",
  "review_notes": "合成示例，非正式案例数据。详细论证见 review_report.md。",
  "status": "complete",
  "sources": ["case.json", "task.md", "review_report.md"],
  "uncertainty": []
})
r["change_record"].append({
  "ts": now, "actor": "run_example.sh(模拟模型merge)", "action": "merge_findings",
  "detail": "七类约束审查完成，填入全部契约字段并将状态置为 complete。"})
with open(path, "w", encoding="utf-8") as f:
    json.dump(r, f, ensure_ascii=False, indent=2)
print("result.json 已更新为 complete。")
PYEOF

echo "== 步骤4：写入审查报告（合成正例 review_report.md）=="
cp "$HERE/review_report.md" "$OUT/review_report.md"

echo "== 步骤5a：lint_review（正例，--strict）=="
"$PY" "$SCRIPTS/lint_review.py" "$OUT/review_report.md" --strict

echo "== 步骤5b：validate_result（契约符合性）=="
"$PY" "$SCRIPTS/validate_result.py" "$CASE" "$OUT/result.json"

echo "== 步骤6：render_report（stdlib-only 独立 HTML）=="
"$PY" "$SCRIPTS/render_report.py" "$OUT/review_report.md" "$OUT/result.json" "$OUT/review_report.html"

echo "== 步骤7：make_manifest（SHA-256 可复算清单）=="
cat > "$OUT/commands.txt" <<'CMDS'
python3 ../../scripts/parse_contract.py case.json output
cp output/result.skeleton.json output/result.json
python3 - output/result.json    # heredoc：merge 审查结论（见 run_example.sh）
cp review_report.md output/review_report.md
python3 ../../scripts/lint_review.py output/review_report.md --strict
python3 ../../scripts/validate_result.py case.json output/result.json
python3 ../../scripts/render_report.py output/review_report.md output/result.json output/review_report.html
python3 ../../scripts/make_manifest.py case.json task.md review_report.md output -o output --commands output/commands.txt
python3 ../../scripts/selfcheck.py output case.json
CMDS
(cd "$HERE" && "$PY" "$SCRIPTS/make_manifest.py" case.json task.md review_report.md output -o output --commands output/commands.txt)

echo "== 步骤8：selfcheck（G1-G6 聚合质控门）=="
"$PY" "$SCRIPTS/selfcheck.py" "$OUT" "$CASE"

echo
echo "== 负例演示：lint_review 应检出 bad_review_report.md 的植入缺陷 =="
set +e
"$PY" "$SCRIPTS/lint_review.py" "$HERE/bad_review_report.md"
rc=$?
set -e
if [ "$rc" -eq 0 ]; then
  echo "UNEXPECTED PASS: lint_review 未检出植入缺陷" >&2
  exit 1
else
  echo "expected failure observed: lint_review 以 exit=$rc 拒绝 bad_review_report.md"
fi

echo
echo "== 全链路演示完成（exit 0）；产物见 $OUT =="
