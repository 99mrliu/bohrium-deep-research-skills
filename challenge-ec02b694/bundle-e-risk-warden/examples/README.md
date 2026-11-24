# examples — 合成示例（synthetic example）

本目录全部内容为**合成示例**：案例、材料、事实汇总与结果均为人工构造，仅用于演示
risk-warden 的端到端行为，不代表任何真实实验数据。

## 场景设定

`case_id = synthetic-ec02b694-001`：陶瓷粉体焙烧工艺优化。材料中故意埋入两类异常：

1. **约束冲突**：`materials/brief.md` 要求目标焙烧温度 1000°C，
   `materials/material_spec.txt` 给出材料耐温上限 950°C（安全红线）；
2. **缺失材料**：case.json 声明的 `materials/prior_runs.csv` 不存在。

## 输入（synthetic-input/）

| 文件 | 说明 |
|---|---|
| case.json | case_id、output_contract 三字段（experiment_plan / evidence_and_risk / confirmation_items）、材料路径 |
| materials/brief.md | 任务简报（含 1000°C 目标） |
| materials/material_spec.txt | 材料规格书（含 950°C 耐温上限） |
| facts_initial.json | Agent 汇总的首轮异常事实（冲突 resolvable=false + 关键缺失） |
| facts_resolved.json | 人工裁决后的修复状态（异常全部解除） |
| result_bad_placeholder.json | 负例：evidence_and_risk 残留占位却声称 success |

## 复现命令（在 bundle 根目录执行）

```bash
# (a) 启动守护：首份 partial 先于任何实质计算落盘；缺失材料被抓出
python3 scripts/warden_boot.py \
  --case examples/synthetic-input/case.json \
  --output examples/synthetic-output \
  --work examples/synthetic-output/work
# 预期 exit=0；产物：result.json(partial)、intake_manifest.json、work_plan.md

# (b) 首轮分流：命中 constraint_conflict + missing_data → handoff_to_human
python3 scripts/triage.py \
  --facts examples/synthetic-input/facts_initial.json \
  --out examples/synthetic-output/triage_handoff.json
# 预期 exit=3；final_action=handoff_to_human（规则 R_CON_01、R_MIS_01）

# (c) 人工裁决后重跑分流 → proceed
python3 scripts/triage.py \
  --facts examples/synthetic-input/facts_resolved.json \
  --out examples/synthetic-output/triage_proceed.json
# 预期 exit=0；final_action=proceed（规则 R_OK_01）

# (d) 填齐三字段的完整 result.json 交付前审计 → 通过
python3 scripts/final_audit.py \
  --result examples/synthetic-output/result_success.json \
  --case examples/synthetic-input/case.json \
  --out examples/synthetic-output/audit_report.json
# 预期 exit=0；verdict=pass

# (e) 负例：占位残留 + 声称 success → 被强制回退 partial
cp examples/synthetic-input/result_bad_placeholder.json \
   examples/synthetic-output/result_forced_partial.json
python3 scripts/final_audit.py \
  --result examples/synthetic-output/result_forced_partial.json \
  --case examples/synthetic-input/case.json \
  --out examples/synthetic-output/audit_forced_partial.json
# 预期 exit=3；verdict=fail、forced_partial=true，
# result_forced_partial.json 被就地改写为 status=partial 并写明 partial_reason
```

## 输出（synthetic-output/，全部为真实运行产物，已目检）

| 文件 | 步骤 | 关键内容 |
|---|---|---|
| result.json | (a) | 首份 partial：三契约字段为 `_placeholder` 占位，uncertainty 记录缺失材料 |
| intake_manifest.json | (a) | 3 项材料；prior_runs.csv exists=false 被抓出，另两份含 sha256 |
| work/intake_manifest.json、work/work_plan.md | (a) | 工作目录副本与六步勾选清单 |
| triage_handoff.json | (b) | R_CON_01 + R_MIS_01 → handoff_to_human，exit 3 |
| triage_proceed.json | (c) | R_OK_01 → proceed，exit 0 |
| result_success.json | (d) | 三字段填齐、每条推荐值带证据引用、status=success |
| audit_report.json | (d) | C1–C8 全部通过，verdict=pass，exit 0 |
| result_forced_partial.json | (e) | 被审计器就地改写：status 由 success 强制回退 partial |
| audit_forced_partial.json | (e) | C3/C4 违例，verdict=fail、forced_partial=true，exit 3 |
