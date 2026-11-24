#!/usr/bin/env bash
# 合成示例端到端演示（非正式案例结果）：
#   result 骨架 -> 坏结构计划编译门拦截 -> 超期/超载计划裁定门拦截
#   -> 修复后计划两级门控通过 -> result.json 诚实 partial
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
SKILL="$(dirname "$HERE")"
WORK="$HERE/work"
OUT="$HERE/expected"
rm -rf "$WORK" "$OUT"
mkdir -p "$WORK" "$OUT"

echo "== 0. result.json 骨架（诚实 partial 起步） =="
python3 "$SKILL/scripts/resultkit.py" init "$HERE/input/case.json" "$WORK/result.json"

echo "== 1. 编译门：结构/依赖坏计划（预期拦截） =="
rc=0
python3 "$SKILL/scripts/plan_compile.py" "$HERE/plan_broken.json" \
  "$OUT/compile_broken.json" || rc=$?
echo "plan_broken 编译退出码: $rc（预期 1：成环 + 悬空依赖 + 无编制角色 + 里程碑无交付物）"
[ "$rc" -eq 1 ]

echo "== 2. 编译门：超期计划结构合法（预期通过） =="
python3 "$SKILL/scripts/plan_compile.py" "$HERE/plan_overrun.json" \
  "$OUT/compile_overrun.json"

echo "== 3. 裁定门：超期计划 CPM 裁定（预期 fail） =="
rc=0
python3 "$SKILL/scripts/cpm_check.py" "$HERE/plan_overrun.json" \
  "$OUT/feasibility_report.json" || rc=$?
echo "plan_overrun 裁定退出码: $rc（预期 1：超期 2 月 + 人力超载月份）"
[ "$rc" -eq 1 ]

echo "== 4. 修复后计划：两级门控（预期全过） =="
python3 "$SKILL/scripts/plan_compile.py" "$HERE/plan_fixed.json" \
  "$OUT/compile_fixed.json"
python3 "$SKILL/scripts/cpm_check.py" "$HERE/plan_fixed.json" \
  "$OUT/feasibility_fixed.json"

echo "== 5. 排期摘要（供开题稿阶段计划章节引用） =="
python3 - "$OUT/feasibility_fixed.json" "$OUT/schedule_summary.md" <<'PYEOF'
import json, sys
rep = json.load(open(sys.argv[1], encoding="utf-8"))
L = ["# 阶段计划排期摘要（经 cpm_check 裁定通过）", "",
     "- 计划：%s；总工期 %.1f 月 / 给定周期 %s 月" % (
         rep["plan_id"], rep["project_duration_months"], rep["period_months"]),
     "- 关键路径：" + " → ".join(rep["critical_path"]),
     "- 计划经费 %d 元 / 预算 %d 元" % (
         rep["budget"]["total_planned_cny"], rep["budget"]["budget_cny"]),
     "- 人力超载月份：%d；窗口违例：%d" % (
         len(rep["staffing"]["overloaded_months"]),
         len(rep["window_violations"])), "",
     "| 任务 | 名称 | 工期(月) | 最早开始-结束 | 总时差(月) |",
     "|---|---|---|---|---|"]
for t in rep["tasks"]:
    L.append("| %s | %s | %.1f | %.0f–%.0f | %.1f |" % (
        t["id"], t["name"], t["duration_months"],
        t["es_month"] + 1, t["ef_month"], t["slack_months"]))
open(sys.argv[2], "w", encoding="utf-8").write("\n".join(L) + "\n")
print("schedule_summary.md written")
PYEOF

echo "== 6. 填契约字段并收尾（诚实 partial：本 bundle 只产出排期类字段） =="
python3 - "$WORK/result.json" "$OUT/feasibility_fixed.json" <<'PYEOF'
import json, sys
res_p, fea_p = sys.argv[1], sys.argv[2]
doc = json.load(open(res_p, encoding="utf-8"))
fea = json.load(open(fea_p, encoding="utf-8"))
doc["schedule"] = {"plan_id": fea["plan_id"],
                   "duration_months": fea["project_duration_months"],
                   "period_months": fea["period_months"],
                   "critical_path": fea["critical_path"],
                   "summary_md": "expected/schedule_summary.md"}
doc["feasibility_report"] = fea
doc["sources"] = ["examples/input/case.json", "examples/input/task.md",
                  "examples/input/materials_note.md",
                  "examples/plan_fixed.json"]
doc["uncertainty"] = ["示例仅演示排期裁定链路；proposal_draft / "
                      "risk_register / fact_source_map 属其他 bundle 职责，"
                      "本示例不填"]
doc["change_records"].append(
    {"ts": "synthetic", "action": "set",
     "detail": "填入 schedule 与 feasibility_report（裁定通过版）"})
json.dump(doc, open(res_p, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
PYEOF
rc=0
python3 "$SKILL/scripts/resultkit.py" final "$WORK/result.json" || rc=$?
echo "resultkit final 退出码: $rc（预期 1：诚实 partial，缺项被点名）"
[ "$rc" -eq 1 ]
cp "$WORK/result.json" "$OUT/result.json"

echo "== 全部步骤完成；产物见 examples/expected/ =="
