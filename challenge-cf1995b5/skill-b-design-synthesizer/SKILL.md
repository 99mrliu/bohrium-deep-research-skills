---
name: exp-design-synthesizer
description: 当任务给出有限参数域（parameter_domains）、资源/价格/预约合同（resource_contract）和若干版本化候选实验方案（candidate_plans），需要"选哪个实验设计"时用本 skill：脚本枚举合法设计空间、用整数/Decimal 算术逐点核算成本与工期、按预算/截止/域合法性过滤、按信息准则排序，使设计选择成为算术结论而非语言偏好；再以选中设计为骨架产出覆盖六要素的完整方案。
---

# exp-design-synthesizer — 有限域组合设计合成

## 1. 用途与新增价值

核心主张：**合法实验设计的空间有限，选择应是算术结论**。
给定有限参数域与合同价格/预约吞吐，本 skill 用脚本机械完成四件事：

1. `enumerate`：展开 parameter_domains 的全部合法组合（range 按 min/max/step，
   enum 按 values），给出设计空间规模与网格表；
2. `score`：对候选方案和任意新策略**逐点核算**——样本数×重复 → 各设备机时 →
   按 price_per_hour 与 pack_size 向上取整的采购成本 → 总成本；按
   slots_per_week × slot_hours 的每周吞吐核算各设备周数 → 关键设备决定 est_days；
   输出逐项可重算的 cost_breakdown、三项可行性布尔与 reject_reasons；
3. `select`：仅在 feasible 设计中按 可行性→信息度→成本 排序，输出推荐、备选、
   以及被否决设计的完整否决理由表；
4. 以选中设计为骨架，由 Agent 撰写覆盖六要素的完整方案。

相对通用 Agent 的新增价值：候选方案常见的算术错误（total_cost 与 cost_items
不符、把"包数"当"单位数"计价）、超出预约吞吐的 est_days、越出有限域的参数、
以及 equipment_domain_note 里文本内嵌、未列入 equipment 列表的设备，全部由
脚本发现而非凭肉眼。

## 2. 适用条件与不适用情况

**适用**：case.json 含 `parameter_domains`（range/enum）、`resource_contract`
（budget_cap/deadline_days/equipment/reagents）以及通常存在的
`candidate_plans`；任务是设计/优化/审稿实验方案。

**不适用**：
- 参数域为连续无界空间、需贝叶斯优化等序贯方法（本 skill 只做有限枚举）；
- 无资源合同、无预算/截止约束的纯文献综述任务；
- 单样本消耗模型完全无法从任务推导、且不允许声明假设的场景
  （此时脚本输出 unknown 字段的 honest partial，而非伪造数字）。

## 3. 运行时契约与路径

- 输入：`/input/case.json`、`/input/task.md`（可能还有论文 PDF）。
- 工作目录：`/app/work`（中间产物：design_space.json、strategies.json、
  design_table.json、selection.json）。
- 交付：`/app/output/result.json`（必需）、`plan.json`、`plan.md`。
- 脚本：`/skills/weekly-skill/scripts/design_space.py`，仅 Python 3 标准库，
  确定性，单次运行 <5 秒，支持 `--help`，缺键降级为 partial 报告且 exit 0。
- 参考文档：`/skills/weekly-skill/references/{design_methods,cost_model,selection_rubric}.md`。

## 4. 工作流（编号步骤，命令可直接复制）

**步骤 1 — 读 case，定位关键字段**（1 次模型请求内完成）：
case_id、parameter_domains、resource_contract（budget_cap、deadline_days、
equipment、reagents）、equipment_domain_note、candidate_plans、
experiment_model（若缺，从任务步骤推导单样本机时/试剂消耗，写成
/app/work/model.json 并记为假设）。

**步骤 2 — 枚举设计空间**：
```bash
python3 /skills/weekly-skill/scripts/design_space.py enumerate \
  --case /input/case.json --out /app/work/design_space.json
python3 /skills/weekly-skill/scripts/design_space.py enumerate \
  --case /input/case.json --levels 3 --out /app/work/design_space_3lvl.json
```
全空间过大时用 `--factors`/`--levels` 看缩减网格。

**步骤 3 — 对 3 个候选方案跑 score（量化体检）**：
```bash
python3 /skills/weekly-skill/scripts/design_space.py score \
  --case /input/case.json --out /app/work/design_table_candidates.json
# 若 case 缺 experiment_model，加 --model /app/work/model.json
```
从输出逐行提取：核算 total_cost、est_days、feasible 三项布尔、
reject_reasons、consistency_warnings（自报数对账）。超预算/超工期/越域/
重复不足的候选在这里被算术否决。

**步骤 4 — 生成 2–4 个新设计策略**：参考
`/skills/weekly-skill/references/design_methods.md` 的适用判据，写
`/app/work/strategies.json`（类型：full_factorial / ofat_scan / orthogonal /
explicit；字段：factors、fixed、levels_per_factor、replicates、rationale）。
典型组合：一个 3 水平全因子（检验规模上限）、一个部分因子（保留关键交互）、
一个 OFAT 链式扫描（低成本对照）、可选一个正交主效应计划。

**步骤 5 — 全量 score + select**：
```bash
python3 /skills/weekly-skill/scripts/design_space.py score \
  --case /input/case.json --strategies /app/work/strategies.json \
  --out /app/work/design_table.json
python3 /skills/weekly-skill/scripts/design_space.py select \
  --table /app/work/design_table.json --out /app/work/selection.json
```

**步骤 6 — 以选中设计为骨架撰写完整方案**（见第 5 节结构），
plan.md 的统计依据段套用 design_methods.md 第 4 节模板；
成本/工期数字直接引用 design_table.json 的 cost_breakdown 行（可重算）；
步骤绑定设备型号（equipment_register 里的 name+model）。

**步骤 7 — 写 result.json**（见第 5 节字段契约），
candidate_assessment 引用步骤 3 的量化结论（含被否决候选的 reject_reasons），
未确认项进 confirmation_items。

## 5. 输出契约

**result.json** 必须含 output_contract.required_fields 全部字段：

- `case_id`：与 case.json 一致；
- `revised_plan`：对象或指向 plan.json 的摘要，含 selected_design_id、
  n_conditions、replicates、total_cost、est_days、feasible 快照；
- `candidate_assessment`：数组，每个候选 {version, feasible,
  computed_total_cost, computed_est_days, reject_reasons,
  consistency_warnings}——数字全部来自 design_table.json；
- `validation`：{design_space_size, n_designs_scored, n_feasible,
  ranking_rule, scripts_run: [...]}；
- `status`：complete / partial / blocked（诚实标注）；
- `uncertainty`：假设清单（如自推导的 per_sample 模型）；
- `sources`：引用 case.json 路径与 references 文件；
- `change_log`：改动记录（含排序参数若有调整）；
- `confirmation_items`：前瞻合同价格/排期未确认等需组织方确认项。

**plan.json** 结构（六要素齐备）：
`assumptions[]`（假设与变量依据）、`variables{}`（每个因子：角色、水平、
操作定义、来源）、`controls_and_confounds[]`（对照组与排除的混杂：
基线条件即对照；随机化/区组安排；被固定因子=外推混杂，须声明）、
`equipment_materials[]`（id+name+model 绑定到具体步骤）、
`procedure_steps[]`（每步：设备型号、参数值、单样本机时）、
`schedule_cost{}`（n_samples、est_days、cost_breakdown 引用）、
`parameter_ranges{}`（合法域摘录）、`readout_criteria[]`（判读标准：
指标、阈值、显著性判据）、`risks[]`（风险与异常处置）、
`provenance{selection_json, design_table_json}`。

**plan.md**：同内容的可读版，统计依据段用 design_methods.md 模板。

## 6. 失败模式与止损表

| 失败模式 | 症状 | 止损 |
|---|---|---|
| 候选自报成本/工期造假或算错 | consistency_warnings 非空 | 以核算值为准，写入 candidate_assessment |
| 候选/策略超预算、超工期 | within_budget/within_deadline=False | 进 reject_reasons，不得硬推；缩 levels_per_factor 或 replicates 后重跑 |
| 参数越出有限域 | in_domain=False | 否决该设计；若为笔误在 change_log 记录，不擅自改值 |
| 内嵌设备漏算 | equipment_register 缺设备 | 检查 equipment_domain_note 解析；warn 后重跑 score |
| 缺 per_sample 消耗模型 | est_days/成本为 unknown | 推导 model.json 显式假设；无法推导则 status=partial |
| 无 feasible 设计 | select 输出 partial | 执行 degraded_action：放宽 --min-replicates、缩规模，或申请追加预算/延期；result.json 标 partial |
| 枚举空间爆炸 | total_combinations 巨大 | 只输出前 10000 行（truncated 标记），用 --factors/--levels 缩减 |

## 7. 输入缺失/约束冲突的降级（honest partial）

- 缺 budget_cap/deadline_days：对应可行性布尔输出 unknown，
  设计按"不可推荐"处理，select 给 partial 与建议；
- 缺 experiment_model：机时/工期/设备成本 unknown，但域合法性与
  自报数对账仍可输出——先交 partial 再补模型重跑；
- 预算与截止互相冲突（任何合法重复次数都不可行）：如实输出
  rejected 全表与最小可行设计（min_replicates=1 的参考行），
  把追加资源请求写进 confirmation_items；
- 任何降级都保留：已算出的数字 + 明确的 unknown 字段 + 下一步命令。

## 8. 预算意识（先存 partial 再迭代）

- 机械工作全交脚本：enumerate/score/select 三次调用共 <5 秒、零模型请求；
- 模型请求优先级：①读 case + 写 strategies.json ②写 plan/result；
  中间不重读脚本输出全文，只取 select 的 recommended/alternates/rejected 摘要；
- 每完成一个脚本步骤立即把输出复制进 /app/work 并在 result.json 草稿里
  落一次 partial（status=partial + 已有字段），再迭代补全；
-  tokens 紧张时：plan.md 可从 plan.json 摘要生成，候选人工分析让位于
  design_table.json 的原文引用。
