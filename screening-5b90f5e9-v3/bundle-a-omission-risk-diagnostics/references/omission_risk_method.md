# 遗漏风险诊断方法学与理由码字典

> 本文档定义 omission-risk-diagnostics 的诊断语义。本技能只做**下游诊断**：消费上游已完成的
> 逐条纳排判定（judgments/decisions），不重新执行初筛判定，不做计数闭合审计，不声称全局召回。

## 1. 输入数据模型

### 1.1 judgments 文件（必需）

容器可为裸 list，或 `{"items": [...]}`。每条判定：

```json
{
  "record_id": "R03",
  "decision": "exclude",
  "primary_reason_code": "EX_POP_AGE",
  "criteria": [
    {
      "criterion_id": "C1_population",
      "verdict": "not_met",
      "rationale_code": "EX_POP_AGE",
      "evidence": {"quote": "adults aged 30-55", "source": "abstract", "anchor_strength": "strong"}
    }
  ]
}
```

- `decision` ∈ {`include`, `exclude`}（其他取值按未知处理，不进队列也不计入排除）。
- `verdict` ∈ {`met`, `not_met`, `uncertain`}。
- `evidence.quote` 必须是所引用记录标题/摘要的真实子串（selfcheck 强制校验）；
  `source` ∈ {`title`, `abstract`}（abstract 语义为"标题+摘要"范围内锚定）；
  `anchor_strength` ∈ {`strong`, `weak`}：weak 表示片段虽真实存在，但对该判定的支撑力弱
  （如过于泛化的单词、间接表述）。

### 1.2 records 文件（facet 核查与证据校验需要）

裸 list 或 `{"records": [...]}`，每条含 `record_id` / `title` / `abstract`。

### 1.3 case.json

含 `case_id`、`research_question`、`facets`（见 facet_model.md）、
`output_contract.required_fields`、`materials`（材料文件名声明）。

## 2. 险漏触发器（near-miss triggers）

针对 `decision=exclude` 的记录，命中任一触发器即入险漏队列：

| 触发器 | 定义 | 风险权重 | 遗漏机理 |
|---|---|---|---|
| `excluded_without_not_met` | 被排除但没有任何 not_met 判据 | 4 | 排除依据最脆弱，疑似仅凭 uncertain 或印象排除 |
| `single_criterion_exclusion` | 恰好一条判据 not_met，其余均 met | 3 | 唯一否决判据一旦判严即误伤，复核收益最高 |
| `uncertain_verdict` | 任一判据 verdict=uncertain | 2 / 条 | 信息不足时的排除决定最可能随证据补充而翻转 |
| `weak_evidence_anchor` | 任一判据证据 anchor_strength=weak | 2 / 条 | 证据片段支撑力弱，判定可能建立在误读上 |

风险分 `risk_score = Σ 权重`；复核工作清单按 risk_score 降序、同分按 record_id 字典序排列。

`decision=include` 但含 uncertain 判据的记录单列 `included_uncertain`：那是**错误纳入**风险
（另一方向的重心），本技能仅提示抽查，不计入险漏队列。

## 3. 排除稳健性（fragility）指标

- `reason_code_distribution`：排除记录的主理由码（primary_reason_code）分布，用于发现
  理由码使用是否集中、是否有 `UNSPECIFIED`（未填理由码的排除本身即风险信号）。
- `single_reason_exclusions`：恰好一条判据 not_met 的排除；其占比越高，排除面越依赖单点判断。
- `excluded_without_not_met`：无 not_met 依据的排除，最脆弱子集。
- `fragile_share = (单理由排除数 + 无 not_met 排除数) / 排除总数`；默认阈值 0.5
  （`--threshold` 可调），达到即 `fragile_flag=true`，建议整批排除面人工抽检。

## 4. 理由码字典（建议约定，上游判定时使用）

排除类（EX_）：

| 理由码 | 含义 |
|---|---|
| `EX_POP_AGE` | 人群年龄/阶段不符 |
| `EX_POP_CONDITION` | 人群疾病/状态不符 |
| `EX_INT_NOT_GLP1` | 干预非目标干预类（示例域：非 GLP-1 受体激动剂） |
| `EX_INT_CLASS` | 干预类别边界不清被排除（应慎用，宜先 uncertain） |
| `EX_COMPARATOR` | 对照设置不符 |
| `EX_OUTCOME_NO_BMI` | 未报告目标结局（示例域：BMI/体重） |
| `EX_DESIGN_NOT_RCT` | 研究设计不符（示例域：非随机对照试验） |
| `EX_PUBLICATION_TYPE` | 文献类型不符（综述/会议摘要/社论等） |
| `EX_DUPLICATE` | 重复导出/重复发表（须保留去重证据） |

不确定类（UNC_，应配 `verdict=uncertain` 而非直接排除）：

| 理由码 | 含义 |
|---|---|
| `UNC_INT_CLASS` | 干预类别归属不确定（如多靶点激动剂） |
| `UNC_OUTCOME_AMBIGUOUS` | 结局报告不完整，无法判定是否含目标结局 |
| `UNC_POP_MIXED` | 混合人群，无法从摘要确认目标亚组 |
| `UNC_ABSTRACT_ONLY` | 仅摘要可得，关键信息缺失 |

纳入类：`MET`（判据满足，附 strong 证据 quote）。

使用约束：`not_met` / `uncertain` 判据必须携带 rationale_code 与 evidence；`UNSPECIFIED`
主理由码会在 fragility 报告中显形并被遗漏说明点名。

## 5. 遗漏说明（omission statement）的固定六节

1. 排除了什么、按什么理由（理由码分布）；
2. 排除稳健性（单理由占比、无 not_met 排除、fragile_flag）；
3. 存在遗漏风险、须人工复核的条目（按风险分降序的工作清单）；
4. 主题面覆盖报警（零纳入 facet）；
5. 本快照无法回答的问题（固定声明，见脚本 CANNOT_ANSWER）；
6. 建议的后续人工动作。

遗漏说明由脚本生成，**不构成人工复核结论**；人工复核完成后应另行留痕并更新工作清单状态。
