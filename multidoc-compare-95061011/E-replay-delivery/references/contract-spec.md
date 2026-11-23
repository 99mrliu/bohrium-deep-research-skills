# result.json 契约细则与 lint 项清单

## 契约建立（init_contract.py）

1. 读 case.json，取 `case_id`（原样复制，一个字符都不改）。
2. 取 `output_contract`：dict 取其键名、list 取其元素，**字段名原样照搬**，写入
   `work/result.schema.json` 的 `contract_fields`。
3. 无 `output_contract` 时退化为基础契约：`{case_id, status, result, sources, uncertainty}`。
4. 立即生成 `/app/output/result.json` 骨架：`status=partial`、契约字段全 null、
   `uncertainty` 含一条"骨架待渲染"说明。此刻即为降级梯 L2 可交付状态。

## result.json 必填结构

| 字段 | 规则 |
|---|---|
| `case_id` | 与 case.json 完全一致 |
| 契约字段（每个） | 字段名原样照搬；渲染器按名字映射填充，未识别的字段名填 null 也必须在场 |
| `status` | `success` / `partial` / `failed` 之一 |
| `sources` | `[{"document_id": ..., "paragraph_ids": [...]}, ...]`；每个引用必须存在于 work/cells.jsonl |
| `uncertainty` | 字符串列表；`status=partial` 时必须非空且写明缺失边界（哪些文档/字段/维度不可比或未报告） |

渲染器的字段名映射：`comparison_matrix`→单元格条目列表（含
cell_id/document_id/paragraph_id/field/value/numeric_value/unit）、
`comparability_assessment`→六维度判定列表、`synthesis`→判定列表、
`sources`/`uncertainty`→派生聚合。

## contract_lint.py 校验项（任一失败即非零退出）

1. result.json 存在且为合法 JSON。
2. `case_id` 与 case.json 一致。
3. `output_contract` 全部字段在场（字段名原样照搬）；无契约时检查基础字段。
4. `status ∈ {success, partial, failed}`。
5. `status=partial` ⇒ `uncertainty` 为非空字符串列表。
6. `sources` 引用的 document_id/paragraph_id 全部存在于 work/cells.jsonl。
7. 数值交叉校验：result.json 内 `comparison_matrix` 条目的
   `value`/`numeric_value` 与 cells.jsonl 中同 (document_id, paragraph_id, field)
   的记录一致——**手改 result.json 里的数字会被此项抓住**。

## 与确定性渲染的关系

- lint 是"产物 ↔ 契约 ↔ 记录"三角校验；render_all 的自校验是"markdown ↔ 记录"
  对账；replay 是"产物 ↔ 重跑产物"字节比对。三者互补，缺一不可。
- 修复顺序永远是：改记录（cells/decisions）→ 重渲染 → 再 lint。永远不要为通过
  lint 而手改 result.json。
