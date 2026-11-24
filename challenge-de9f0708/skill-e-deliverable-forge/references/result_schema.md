# result.json 完整字段规范与常见验收失败模式

本规范是 `contract_validate.py` 的验收依据。案例的**最终权威契约以 case.json 的
`output_contract.required_fields` 为准**；本文给出各字段语义与写法。

## 顶层字段

| 字段 | 类型 | 语义与写法 |
|---|---|---|
| `case_id` | string | 与 case.json 的 `case_id` 完全一致，逐字复制。 |
| `status` | enum | `complete` / `partial` / `blocked`。见下「status 语义」。 |
| `summary` | string | 3-6 句总览：审查了哪些面、发现几类问题、总体结论。 |
| `findings` | list | 问题条目数组，要素见下节；无问题也得是 `[]` 并在 summary 说明。 |
| `sources` | list | 实际使用过的材料与外部来源（文件名、URL、数据库记录）。没用过就写本地材料清单。 |
| `uncertainty` | list[string] | 无法确认的事项，每条一句，写明"是什么不确定 + 为什么"。 |
| `change_log` | list[string] | 结果文件的演化记录：每次重要修改/降级一条，含原因。 |
| `not_reviewed` | list | 未覆盖的审查面。每条 `{facet, reason}` 对象或一句字符串。为空列表 = 全部覆盖。 |
| `facets_reviewed` | list[string]（可选） | 已覆盖审查面清单；dashboard 的覆盖率记账使用。 |

**非空判定**：`null`、空字符串、空白字符串、空列表 `[]`、空对象 `{}` 一律视为"空"，
required_fields 里出现即 FAIL。例外：`not_reviewed`、`uncertainty` 这类"如实为空"的字段——
若 contract 要求它存在，至少要有一条说明性条目（如 `无未覆盖审查面` 写在 summary，或
not_reviewed 保持 `[]` 但确认 contract 允许）；拿不准就放一条说明字符串，绝不冒 FAIL 风险。

## status 语义

- `complete`：case.json 声明的**全部审查面**均已审查，findings 全部有定位与依据，
  `not_reviewed` 为空。**有 not_reviewed 条目却自称 complete 是语义矛盾**，验收器不拦但评审会拦。
- `partial`：部分审查面未覆盖或部分结论无法确认。必须在 `not_reviewed`/`uncertainty` 写明
  具体局限。
- `blocked`：材料不可读/不可用，无法开展实质审查。说明阻塞原因。

机械降级规则：验收 FAIL 时脚本自动 `status → partial`；原为 `blocked` 则保持（不会反向升级）。
修复后由 Agent 改回 `complete` 并重跑验收确认。

## findings 要素（每条必备）

| 要素 | 要求 |
|---|---|
| `id` | 稳定编号（F01、F02…），复跑之间不漂移。 |
| `type` | 类型细分，小写蛇形，如 `figure_number_mismatch`、`missing_ethics_statement`。 |
| `category` | （建议）fact_error / insufficient_evidence / norm_issue / suggestion 四选一。 |
| `severity` | critical / major / minor / info，枚举外一律 FAIL。 |
| `location.file` | 材料文件名，如 `paper.pdf`。 |
| `location.page` | 页码（数字或字符串均可，但不得为空）。 |
| `location.section` | 章节名（建议有，不做硬性 FAIL）。 |
| `location.quote` | **原文逐字摘录**，不得改写、不得省略号拼接、不得为空。 |
| `evidence` | 判定依据：本地规则名 / 规范条款（真实存在、不得编造）/ 外部来源及检索到的原文。 |
| `suggestion` | 可执行动作：谁、改哪里、改成什么。禁止"建议检查格式是否规范"式空话。 |
| `verdict_status` | 以 `确认` 或 `待复核` 开头；待复核必须附理由，如 `待复核：需联网核验 DOI 记录`。 |

## 常见验收失败模式（FAIL 明细 → 修复动作）

1. `required field missing` → 顶层缺字段；对照 required_fields 补齐。
2. `required field is empty` → 字段是 `""`/`[]`/`{}`/null；填实质内容或一条说明。
3. `status must be one of [...]` → 拼写错误或自创枚举（如 `done`）；改回三选一。
4. `finding Fx missing or empty 'quote'` → 回原文抄逐字摘录；确实抄不到的，删除该条或
   把 verdict_status 改为 `待复核：` 并说明（quote 仍不能为空——无法定位的问题不得报出，
   只能进 uncertainty）。
5. `severity must be one of [...]` → 大小写/自创等级（如 `high`）；改为四选一。
6. `verdict_status must start with '确认' or '待复核'` → 写成 `confirmed` 等英文或空值；
   改为规定前缀。
7. `findings must be a list` → findings 写成了对象；包成数组。

## 自动降级示例

FAIL 后 result.json 被机械改写：

```json
{
  "status": "partial",
  "change_log": ["…原有记录…", "机械验收未过，状态自动降级为 partial；缺失/非法字段：sources、not_reviewed"],
  "uncertainty": ["机械验收未通过项：required field missing", "..."]
}
```

该记录**不得删除**——它是交付物诚实性的一部分；修复后追加新 change_log 条目说明修复即可。
