---
name: budget-checkpoint-pilot
description: |
  预算感知的结构诊断编排器（Budgeted Orchestration with Checkpoints and Quality Gates）。重心在过程质量控制：把 64 请求/900 秒/16384 tokens 的硬预算编排成六阶段计划与出口门，用原子写检查点协议保证任何中断时刻 result.json 都是可交付的诚实 partial，用降级阶梯在预算/材料不足时保序收缩，最后用九项终检质量门决定 status 能否置 ok。同时给出九类输入失败的识别-处置表。
  触发：task.md 要求在固定预算内对论文/稿件做结构诊断并交付可复核结果时；多案例重复运行需稳定性保证时。不触发：语言润色、科学内容裁决。
  Trigger: budget-aware orchestration of manuscript structural diagnosis — phase budgets, atomic checkpoints, degradation ladder, final quality gate, failure taxonomy. Not for: language polish, scientific-correctness adjudication.
---

# 预算检查点领航员（Budget Checkpoint Pilot）

## 0. 定位与差异化

本 Skill 的重心是**过程质量控制**：同样能力的 Agent，在 64 请求/900 秒硬预算下的实际得分差异主要来自编排——前半程挥霍预算导致后半程截断、中断后交付无效 JSON、为追求完美诊断而牺牲契约完整性。本管线提供四层机制：

1. **预算编排**（`plan_budget.py` + `references/orchestration.md`）：六阶段请求/秒数分配与出口门；
2. **检查点协议**（`checkpoint.py`）：原子写 result.json，阶段出口打点，乱序打点自动记 uncertainty；
3. **降级阶梯**（`references/degradation_ladder.md`）：L0–L6 保序收缩，每级交付物自洽；
4. **终检质量门**（`quality_gate.py`）：九项检查，不过门不许 `status=ok`。

诊断方法本身（六维怎么判）由 Agent 按任务要求执行；本 Skill 保证**过程不失控、状态不撒谎、中断有交付**。

## 1. 运行时契约

| 项 | 约定 |
|---|---|
| 输入 | `/input/case.json`、`/input/task.md` 先读；`case.json.output_contract` 逐字段抄录，不凭题目猜。 |
| 工作目录 | `/app/work`（计划、中间稿）。 |
| 最终交付 | `/app/output/result.json`（含 `case_id` 与全部契约字段）、`plan.json`、`audit.md`、诊断与编辑计划产物。 |
| 预算 | 64 次模型请求 / 900 秒 / 16384 tokens 每响应——本 Skill 的存在理由。 |
| Skill 安装路径 | `/skills/weekly-skill`；路径不同时替换命令前缀。 |

## 2. 必需工作流（与六阶段一一对应）

### 阶段 1 — 契约与盘点
```
python3 /skills/weekly-skill/scripts/plan_budget.py /input /app/work/plan.json
python3 /skills/weekly-skill/scripts/checkpoint.py init /input/case.json /app/output/result.json
```
出口门：plan.json 生成；result.json 有效（partial）。

### 阶段 2 — 抽取
读真实文件（PDF `pdftotext -layout`；docx zip+xml 容错）。异常按 `references/failure_taxonomy.md` 识别处置。出口打点：
```
python3 /skills/weekly-skill/scripts/checkpoint.py mark /app/output/result.json --phase extraction --note "<抽取结果一句话>" --requests-used <N> --seconds-used <S>
```

### 阶段 3 — 六维诊断（预算主战场 45%）
high 子类优先：研究问题悬空、论证断裂、结论超界先查；长稿按 orchestration.md 分段读。出口打点 `--phase diagnosis_core`。

### 阶段 4 — 校验
逐条核对 finding 的引文逐字性与字段完整性（可用任一校验脚本或人工抽验，抽验比例 ≥30% 且覆盖全部 high）。出口打点 `--phase verification`。

### 阶段 5 — 产物
生成诊断 JSON 与编辑计划（diagnosis + editing_plan 是 quality_gate 的必查文件）。出口打点 `--phase deliverables`。

### 阶段 6 — 收尾
填契约字段，置 status（规则：契约字段齐 + 无未决 uncertainty → ok；有缺 → partial 并点名；材料整体不可用 → failed）。然后：
```
python3 /skills/weekly-skill/scripts/quality_gate.py /app/output/result.json /app/output /app/output/audit.md
```
退出码 1 时按 audit.md 修复，直至过门；打点 `--phase finalize`。

## 3. 熔断与降级

- 任一阶段实际请求 > 其 plan 预算 150% → 按 degradation_ladder.md 降一级，`--degraded "<原因>"` 打点；
- 剩余 <120 秒且未进 finalize → 立即跳到当前可完成的最高降级级；
- 材料部分不可读 → 只对受影响维度降级，不拖垮整体；
- 同一策略失败两次即换路，不反复重试。

## 4. 自查清单

- [ ] quality_gate 退出码 0，audit.md 归档
- [ ] checkpoints 覆盖 ≥4 阶段且按序
- [ ] 所有降级在 degradation_log 有原因
- [ ] status 与契约完整度一致（ok 必完整；partial 必有原因）
- [ ] 三次重复运行产物结构稳定（字段集合一致）

## 5. 最小示例

`examples/`：**合成示例**（非正式案例）。`bash examples/run_example.sh` 演示计划→五个检查点→故意留一个契约字段不填→质量门阻断→修复后过门的完整闭环；`expected/` 为真实跑出的示意输出。
