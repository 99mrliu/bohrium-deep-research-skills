# Audit field specification and state machine

所有示例内容均为 **SYNTHETIC / 合成样例，非正式科研结果**。

## 1. 输入与权威顺序

- `/input/case.json`：只读。顶层至少有 `case_id`、`assertions`、`sources`。每个 assertion 有唯一 `input_id`、原 `claim`、布尔 `compound`；每个 source 有唯一 `source_id` 和原始 `text`。
- `/input/task.md`：只读。`## output_contract` 后第一个 JSON fenced block 是机器可读权威契约。其 `required_result_fields`、状态字段名、制品字段名优先于 Skill 文档与示例。即使实际契约与本参考不同，也必须满足实际契约；本 checker 对未知必需字段只验证存在，不擅自重命名。
- `environment/resources.yaml`：运行预算与路径。最多64次 requests、总时长900秒，Python 3.9+，仅用标准库。工作文件在 `/app/work`，最终交付在 `/app/output`。

## 2. 裁决台账

`adjudication-ledger.json` 顶层字段：

| 字段 | 类型与要求 |
| --- | --- |
| `schema_version` | 字符串 |
| `synthetic` | 合成样例为 true；实战按输入事实填写 |
| `case_id` | 与输入完全相同 |
| `audit_complete` | 全部 ID 都完成时才为 true |
| `assertions` | 每个输入 ID 恰好一条；顺序应与输入一致，无额外 ID |
| `corrected_claims` | 独立修正建议数组，绝不覆盖输入 |
| `sources` | 字符串 source ID 数组；完整审计中覆盖输入全部来源且无重复、无未知 ID |
| `uncertainty` | 数组；空数组也保留，记录冲突、证据边界、模态和未决事项 |
| `change_records` | 数组；空数组也保留，记录修正建议而非篡改原输入 |

每条 `assertions[]`：

- `input_id`、`original_claim`：原 ID 一次且原文精确保留。
- `decision_status`：`adjudicated` 或 `pending`。
- `verdict`：完成时取 supported/contradicted/not_established/mixed；pending 时必须为 null。
- `components`：pending 时为空；完成时按 verdict-logic.md 拆分为原子命题。字段至少包括 `component_id`、`text`、`disposition`、`claim_nature`、`evidence_basis`、`rationale`、`evidence`。
- `evidence[]`：至少 `source_id`、`quote`、`location`、`stance`；stance 为 support/reverse/context。
- `corrected_claim_ids`：独立修正 ID 数组。supported 必须为空；其余可空，但列出的每个 ID 必须存在且反向链接当前 input_id。
- `review_disposition`：完成时 accept/rewrite/reject；pending 时 pending。reject 不决定 process status。

每条 `corrected_claims[]`：`corrected_claim_id` 唯一，`input_id` 指向已有断言，`corrected_text` 不等于原文，`rationale` 非空，`source_ids` 均存在。每个修正只被其所属断言引用一次；所有修正均须被引用，且至少有一条 change record 链接它。

每条 `change_records[]`：`change_id` 唯一、`input_id` 存在、`corrected_claim_ids` 均有效、`change_type` 非空、`original_preserved=true`。checker 比对台账与 result 中该数组，防止交付时遗漏变化和不确定性。

## 3. result 与report

默认示例的 `result.json` 含 `case_id`、`status`、`adjudication_report`、`adjudication_ledger`、`input_count`、`adjudicated_count`、`verdict_counts`、`sources`、`uncertainty`、`change_records`；实际运行的权威集合以 task output_contract 为准。

- `case_id` 保原值，必需字段一个不能少。
- `input_count` 必须等于输入断言数；`adjudicated_count` 只能统计已裁决项。
- `verdict_counts` 固定含四种 verdict 的键（含零），与完成项一致。
- 路径字段至少指向相应制品 basename；`sources`、`uncertainty`、`change_records` 与台账深度相等。
- `adjudication-report.json` 由 checker 真实运行生成，含 valid、覆盖数、pending IDs、计数、逐项检查结果和 errors；失败也保存，不能用缺失报告伪装成功。

## 4. 合法状态机

```text
START
  -> PARTIAL_SAVED   (先登记全部 input_id；允许部分 pending)
  -> PARTIAL_SAVED   (继续裁决并覆盖工作快照，不丢已保留原文)
  -> SUCCESS         (全部 adjudicated + audit_complete=true + 结构/证据检查通过)
  -> VALIDATION_ERROR(任一阶段发现缺 ID、重复 ID、改原文、非法逻辑/链接/证据)
```

`status=success` 只表示审计流程完整且制品通过验证，不表示所有断言被接受。`review_disposition` 可含 rewrite/reject，verdict 可含 contradicted/not_established/mixed；这些都不阻止 success。

合法的 `status=partial` 仍保留每一个输入 ID；未完成项使用 `decision_status=pending`、`verdict=null`、`components=[]`、`corrected_claim_ids=[]`、`review_disposition=pending`，且 `audit_complete=false`。所有 output_contract 必需字段仍保留。若已 `audit_complete=true` 且全部完成，则只允许 success。

完全跳过 ID、重复 ID、额外 ID 或非法 mixed 是验证错误，不是 partial，checker 退非零。接近64 requests或900秒时立即停止新增工作，保留原 ID、当前证据和 uncertainty，把工作快照写入 `/app/work`，并将诚实的 partial 制品写入任务契约要求的位置；不得删除未裁决 ID 来制造 success。

## 5. 产物与预算限制

最终 JSON 均为 UTF-8 文本，输入不可写。运行只创建任务契约要求的 ledger/report/result 与必要工作快照；不生成PDF、版面标注、问题矩阵、数值计算表或导出工程。任何源获取、重试和解析请求都计入64次总预算；全部工作必须在900秒内停止并落盘。
