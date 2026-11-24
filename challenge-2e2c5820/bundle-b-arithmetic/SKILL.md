---
name: deterministic-arithmetic-feasibility-core
description: 确定性实算核验中枢。适用于"实验方案可行性评估"等需要真实数值核验的场景（预算对上限、进度关键路径对时限、参数对有限域、物料库存对需求、单位归一化）。核心机制：模型只做带定位符（locator）的结构化抽取，逐字抄数、绝不算数；一切数值结论由 Python 脚本以 Decimal 确定性实算，逐行打印公式与操作数，reviewer 重跑可得完全相同的数字。任何脚本无法复算的数字一律标记 unverified，绝不采信、绝不编造。
---

# 确定性实算核验中枢（deterministic-arithmetic-feasibility-core）

## 解决什么问题

1. **时间成本靠感觉给数**：模型拍脑袋说"约 3 天"，没人验证关键路径。→ 本 Skill 用 DAG + 前向递推实算每步 ES/EF、关键路径与总工期，链式打印可解释。
2. **预算不复算**：方案里申报小计可能算错，合计与上限没人对。→ 逐行 `单价×数量` 复算、申报小计漂移 >0.5% 即标记、合计对上限给精确 delta。
3. **参数容差无依据**：方案参数是否落在主办方有限域内靠猜。→ 枚举/区间域成员判定 + 单位归一化（mL↔µL、min↔h），rpm↔g 等不可换算的如实标记请专家复核。

## 输入 / 输出契约

- 输入：`/input/case.json` + `/input/task.md`。**字段名不固定**——必须先探结构，禁止猜。
- 工作目录：`/app/work`（中间产物：结构地图、各版 extraction、各脚本报告）。
- 最终交付：`/app/output/result.json`，必须含 `case_id` + case.json 中 `output_contract` 声明的**全部字段**（形状可能是 list/dict/properties 风格）+ `status`（complete/partial/failed）+ `sources` + `uncertainty` + `change_record`。partial 必须说明限制。

## 严格按序工作流

> 运行时脚本路径：`/skills/weekly-skill/scripts/...`，参考文件：`/skills/weekly-skill/references/...`。

**步骤 1 — 探结构（0 次模型调用）**

```bash
python3 /skills/weekly-skill/scripts/inspect_case.py /input/case.json /app/work/inspect_map.json
```

得到 case_id、候选方案、合同（价格/预算上限/预约时限）、参数域、output_contract 的真实 JSON 路径地图。

**步骤 2 — 逐版抽取（模型，≤6 次调用）**

按 `references/extraction_schema.md`，为每个方案版本写一个 `/app/work/extraction_<plan>.json`。
铁律：**数字逐字抄写，永不四舍五入，永不在脑中做乘法/加法**；每条记录带非空 locator
（`<plan_id>#<小节>#<行/条目>`）。3 个版本预算 ≤6 次模型调用（每版最多 2 次：抽 + 修）。

**步骤 3 — 校验抽取（每版）**

```bash
python3 /skills/weekly-skill/scripts/validate_extraction.py /app/work/extraction_<plan>.json
```

exit 2 → 按列出的违规修复后重抽（计入步骤 2 的调用预算）。校验不通过**禁止**进入实算。

**步骤 4 — 三个实算脚本（每版，0 次模型调用）**

```bash
python3 /skills/weekly-skill/scripts/recalc_budget.py   /app/work/extraction_<plan>.json /input/case.json /app/work/budget_<plan>.md   --json-out /app/work/budget_<plan>.json
python3 /skills/weekly-skill/scripts/recalc_schedule.py /app/work/extraction_<plan>.json /app/work/schedule_<plan>.md --case /input/case.json --json-out /app/work/schedule_<plan>.json
python3 /skills/weekly-skill/scripts/check_domains.py   /app/work/extraction_<plan>.json /input/case.json /app/work/domains_<plan>.md  --json-out /app/work/domains_<plan>.json
```

**步骤 5 — 结论分级**

| 实算输出 | 级别 |
|---|---|
| 预算 `超支` / 进度 `超出` / 参数 `out_of_domain` | **gating fail**（该方案不可行） |
| 申报漂移、`no_domain_found`、`unit_unconvertible`、cap/deadline 未找到 | unverified，写入 uncertainty，不静默放过 |
| 三项均无 gating fail | pass，可作为 chosen_plan |

**步骤 6 — 装配（0 次模型调用）**

```bash
python3 /skills/weekly-skill/scripts/assemble_result.py --case /input/case.json --artifacts /app/work --out /app/output/result.json --status complete --note "…"
```

脚本保证：case_id + 全部 contract 字段 + status + sources + uncertainty + change_record；
合并实算结论；**绝不覆盖已有非空值**；填不了的字段置 null 并记入 uncertainty；追加 change_record。

**步骤 7 — 自查（≤1 次模型调用）**

读回 result.json 与三份 .md 报告：contract 字段无缺失；每个数字都能在报告里找到对应公式行；uncertainty 列出了全部 unverified 项；若 status=partial，限制已写明。

## 异常处理

- **case.json 里找不到预算上限/参数域/时限**：脚本输出 `unverified_cap_not_found` / `no_domain_found` / `unverified_no_deadline`——如实报告，**绝不编造**上限或域。可用 `--cap` / `--deadline-hours` / `--domains` 显式补供。
- **抽取被 validate 拒绝**：按违规清单修复重抽；连续失败则该版标记 failed，result 降级 partial 并说明。
- **超长文档**：只抽数值表（预算表/进度表/参数表），其余不抽，在 uncertainty 记录"仅覆盖数值相关小节"。
- **依赖成环**：`recalc_schedule.py` exit 2 并列出成环节点；回查 locator 修正抽取（多半是抄错了 depends_on），不是改脚本。
- **rpm↔g、跨维度单位**：`unit_unconvertible`，请专家复核，绝不猜换算（见 references/units.json）。
- **脚本因任何原因跑不完**：先保存已有 partial（assemble 支持反复运行、只补不覆盖），再在 change_record 记录中断点。

## 预算意识（运行时 ~64 次模型请求 / 900 s）

- 模型调用只花在：读 task/case 摘要（≤2）、抽取（≤6）、修复重抽（计入 ≤6）、装配后自查（≤1）。**总计 ≤10 次**，远离预算上限。
- 一切实算零模型调用，全部交给脚本。
- 每个版本校验通过立刻落盘 extraction 与三份报告（save partials early）；装配脚本可增量合并，中断后重跑不丢已有结论。
