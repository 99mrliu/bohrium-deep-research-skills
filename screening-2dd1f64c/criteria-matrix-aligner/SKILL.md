---
name: criteria-matrix-aligner
description: 文献筛选任务的上游判据保真引擎。从 /input/case.json 自带的标注标准（annotation_standard / screening_criteria / criteria / inclusion / exclusion 等键）逐字抽取判据注册表并附来源指针，再以一次批量模型调用产出"记录 × 判据"逐格判定矩阵（met/unmet/unknown + 该记录标题或摘要的逐字引用），由脚本以确定性规则完成标签、评分、排序与契约化交付，使与标注标准的一致性可逐格审计。当任务要求按案例自带判据做全记录筛选、判定过程须可复核、缺失与冲突须显式报告时使用。
---

# criteria-matrix-aligner

## 用途与重心

本 Skill 的重心是**上游判据保真**：筛选判据不得由模型即兴拟定，而应从案例自带的标注标准中**逐字（verbatim）抽取**为判据注册表，每条判据携带来源指针（case.json 键路径或 task.md 行号）；仅当案例不含标注标准时，才允许从 research_question / retrieval_scope 派生判据，且必须诚实标注 `derived:true`。在此基础上，每条记录获得一张"记录 × 判据"的逐格判定矩阵（verdict ∈ met/unmet/unknown，并附该记录标题或摘要的逐字引用），标签（keep/pending/exclude）、分值与名次全部由脚本按确定性规则从矩阵重算——与标注标准的一致性因此可逐格审计，而非整体印象。本 Skill 不替代判据的语义判断，而是保证判据来源真实、判定逐格留痕、结论可独立复算。

## 适用条件

- 输入为 `/input/case.json`（固定科研问题、实际查询输入、约 9 条真实署名文献的有限快照；部分案例含以 `fixture_note` 等字段显式标注的合成重复导出或冲突意见夹具——仅可作 provenance，绝不可作为判定依据或预期答案）与 `/input/task.md`。
- 要求**全记录筛选**：每条输入记录恰好覆盖一次，unknown 也是合法判定，禁止静默排除。
- 平台运行契约：在 `/app/work` 下工作，最终结果写入 `/app/output/result.json`，须含 `case_id` 回显与 `output_contract` 声明的全部字段，以及诚实的 `status`（state: complete|partial、completed、incomplete、limits）、`uncertainty`、`change_records`。

## 运行契约与预算纪律（64 次模型请求 / 900 秒）

按以下四步执行，模型调用 **≤2 次**（第 2 步一次批量调用覆盖全部记录；9 条规模禁止逐条调用），任何一步失败均跳到第 4 步以退化路径交付诚实 partial：

1. **判据抽取（脚本，无模型调用）**
   `python3 /skills/weekly-skill/scripts/criteria_engine.py extract --case /input/case.json --task /input/task.md --out /app/work/criteria.json`
   读取 criteria.json：`criteria` 为逐字判据注册表（含 criterion_id、text、source、derived）；`record_ids` 为全覆盖基线；`notes` 记录派生警告与夹具提示。
2. **批量矩阵判定（1 次模型调用）**：对全部记录 × 全部判据一次性输出 `/app/work/matrix.json`，形如 `{"cells":[{"record_id","criterion_id","verdict": "met|unmet|unknown","quote"}]}`。`quote` 必须是**该记录标题或摘要的逐字子串**；判不了的一律 `unknown` 且 `quote` 为 null，不得编造证据。`fixture_note` 只能写入备注，不得作为 verdict 来源。判据语义边界见 `references/criteria-playbook.md`。
3. **决定与装配（脚本）**
   `python3 /skills/weekly-skill/scripts/criteria_engine.py decide --case /input/case.json --criteria /app/work/criteria.json --matrix /app/work/matrix.json --out /app/output/result.json`
   脚本完成：确定性标签规则（全 met → keep/direct；≥1 unmet → exclude/none；其余 → pending/indirect）、分值（100×met 比例 − 50×unmet 比例，钳制 [0,100] 取整）、确定性排序（keep<pending<exclude，同层分值降序，再按 record_id；同 (label,score) 共享名次并标 `tie_group`）、契约字段镜像——不可产出的字段以显式 `null` + `status.incomplete` 说明，绝不静默丢弃。
4. **交付校验（脚本）**
   `python3 /skills/weekly-skill/scripts/criteria_engine.py validate --case /input/case.json --criteria /app/work/criteria.json --result /app/output/result.json`
   FAIL 则按打印的问题清单修复后重跑第 3 步；PASS 才视为可交付。**退化路径**：时间或预算不足时省略第 2 步，`decide` 不带 `--matrix` 即产出全 pending/unknown 的诚实 partial——validate 仍可通过，先保底再改进。

## 输入 / 输出

- 输入：`/input/case.json`、`/input/task.md`；中间物：`/app/work/criteria.json`（判据注册表）、`/app/work/matrix.json`（判定矩阵）。
- 输出：`/app/output/result.json`，含 `case_id`、`criteria`（判据注册表）、`screened_records`（全记录，含 label/decision/score/rank/逐格 verdicts 与 quotes）、`ranking`、`evidence_records`（非空引用清单）、`summary`（计数与 unknown 单元格统计）、`status{state,completed,incomplete,limits}`、`uncertainty`、`change_records`，以及 `output_contract` 声明的每个其他字段。
- 异常处理：case.json 无法解析 → 脚本以非零退出并说明；未找到标注标准 → 派生判据并标注 `derived:true` 且写入 `status.limits`；判据与候选均为空 → 全 pending 的 partial；矩阵缺失或含 unknown 单元格 → `status.state=partial` 并明示数量；契约字段不可产出 → 显式 null + 原因。不补造文献、不把夹具标注当作预期答案。

## 方法说明与限制

- 判据注册表是只读事实：脚本不改写判据文字、不合并冲突判据；标注标准内部冲突时两条均保留并在矩阵中各自判定，由逐格矩阵呈现分歧（详见 playbook）。
- 标签、分值、名次完全由矩阵经确定性规则重算：同一 matrix.json 必得同一 result.json，任何第三方可独立复核模型判定与最终结论之间的一致性。
- `validate` 执行反编造检查：每个非空 quote 必须是该记录标题或摘要的逐字子串；标签与分值必须与矩阵按规则重算结果一致；任一不满足即 FAIL。
- 局限：判据的语义判定质量取决于第 2 步的模型判断，本 Skill 保证的是判据来源保真、逐格可审计与交付合规；标注标准键名拼写超出已知候选时按研究问题派生并如实标注，不做语义猜测。
- 自查方法：`validate` PASS 且 `status.state` 与人工预期一致；抽查若干非空 quote 可在原文中检索到；unknown 单元格数与 `summary.cells_unknown` 一致。示例见 `examples/minimal/`（合成示例，不冒充正式案例结果）。
