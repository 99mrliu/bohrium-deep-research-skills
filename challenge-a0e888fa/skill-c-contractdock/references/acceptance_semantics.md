# 验收语义：contract_verify.py 每项检查的含义与修复路径

| 检查 | 含义 | 失败时修复 |
|---|---|---|
| `case_id_present` | result.json 的 case_id 与合同一致 | 从 case.json 重取，不得凭记忆写 |
| `contract_fields_present` | 合同声明的字段路径全部存在（嵌套逐层找） | 用脚手架补齐，缺失值先填实测/空容器 |
| `contract_field_types` | 类型匹配；布尔不被当 integer/number | 按合同类型改值，不改合同 |
| `required_fields_filled` | 必填字段非 null 非空串 | 实在没有值 → 说明原因并改 status=partial |
| `referenced_artifacts_exist` | result.json 引用的相对路径文件都在输出目录 | 补产物或改路径；引用 /app/work 中间态是错误 |
| `report_self_consistent` | 报告 rows_out/rows_in/ledger_entries 与现场重算一致 | **以重算为准**重出报告；禁止手改数字 |

## 为什么"以重算为准"

评审看的是"报告数字与结果表对得上"。数字分歧只有两种来源：产物改了没重出
报告（最常见），或报告生成器本身有 bug。两者都靠重新生成解决；手工把数字改
一致而不重算，等于把第二个错误盖在第一个错误上。

## 验收时序

验收必须发生在**所有产物冻结之后**：任何产物在验收后被修改，验收即作废，
必须重跑。建议把 contract_verify 作为交付前最后一个命令，并将其
verify_verdict.json 一并交付，作为"已验收"的证据。
