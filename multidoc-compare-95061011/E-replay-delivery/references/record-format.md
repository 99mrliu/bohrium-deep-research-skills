# 记录格式：cells.jsonl 与 decisions.jsonl（唯一事实来源）

两个文件都在 `work/` 下，每行一个 JSON 对象（UTF-8，JSONL）。所有人读产物由
`render_all.py` 从这两个文件确定性渲染；**任何修改只改记录，不改产物**。

## cells.jsonl：每格一条单元格记录

比较矩阵的每个 (论文 × 共同字段) 格子一条记录，包括"未报告"的格子。

| 键 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `cell_id` | string | 是 | 全局唯一，建议 `C-001` 起递增；渲染产物中以 `⟦C-xxx⟧` 引用 |
| `paper_document_id` | string | 是 | 语料文档 ID（如 `DOC-01`），与 workorder 的 document_id 一致 |
| `paragraph_id` | string | 是 | 该格证据所在的段落 ID（如 `P-03`）。未报告的格子也要给：指向能证明"文中未报告"的段落 |
| `field` | string | 是 | 共同字段名（如 `degradation_efficiency_pct`），与 workorder 的 common_fields 一致 |
| `value` | string\|null | 是 | 原文取值（文本）。数值格也建议填规范字符串；未报告填 null |
| `numeric_value` | number\|null | 是 | 数值化取值（用于矩阵数字与自校验对账）；非数值格/未报告填 null |
| `unit` | string\|null | 是 | 单位（如 `%`、`min^-1`、`mg`）；无单位填 null |
| `comparability` | object | 是 | 六维度判定，六个键一个不能少（见下） |
| `note` | string | 否 | 证据摘录/判定理由，一句话 |

### 六维度判定编码（comparability）

任何定量合成之前必须检验的六个维度，每维取四值之一：

| 编码 | 含义 |
|---|---|
| `comparable` | 与判定基准（workorder 的 reference_basis）可比 |
| `not_comparable` | 明确不可比（如染料不同、指标口径不同），**禁止合并**，但必须保留在矩阵中 |
| `not_reported` | 文中未报告，无法判定；以 `— ⟦NR⟧` 保留在矩阵中并进入 uncertainty |
| `unknown` | 提取不完整、暂无法判定 |

六个维度（键名固定）：

| 维度 | 判什么 |
|---|---|
| `task` | 实验任务是否同一类（如"可见光光催化染料降解"） |
| `metric` | 指标口径是否一致（降解效率 % vs 速率常数 k 属不同口径） |
| `units` | 单位是否一致或可无损换算 |
| `material` | 材料体系是否同族到可比较（g-C3N4 基 vs N-TiO2 不可合并） |
| `pollutant` | 目标污染物是否相同（RhB vs 亚甲基蓝不可合并） |
| `budget` | 资源/预算口径（如催化剂投加量）是否报告且可比 |

约定：整格未报告（value 与 numeric_value 均为 null）时，六个维度通常全填
`not_reported`。某维度的判定属于"实验设计层面"（如 pollutant）时，该论文所有
格子在此维度上保持一致判定。

### 示例

```json
{"cell_id": "C-003", "paper_document_id": "DOC-01", "paragraph_id": "P-01", "field": "degradation_efficiency_pct", "value": "96", "numeric_value": 96, "unit": "%", "comparability": {"task": "comparable", "metric": "comparable", "units": "comparable", "material": "comparable", "pollutant": "comparable", "budget": "comparable"}, "note": "90 min 降解效率 96%"}
{"cell_id": "C-016", "paper_document_id": "DOC-03", "paragraph_id": "P-02", "field": "rate_constant_k", "value": "0.031", "numeric_value": 0.031, "unit": "min^-1", "comparability": {"task": "comparable", "metric": "not_comparable", "units": "comparable", "material": "comparable", "pollutant": "comparable", "budget": "not_reported"}, "note": "仅报 k，未报效率；k 与效率%口径不同，不可并入效率合成"}
```

## decisions.jsonl：每条合成判定一条记录

对"能不能做某个跨论文定量合成"的判定。blocked 的判定具有否决权：对应数值
**不得合并、不得平均**，只能在矩阵中并列呈现。

| 键 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `decision_id` | string | 是 | 全局唯一，建议 `D-001` 起递增 |
| `subject` | string | 是 | 判定对象（如"degradation_efficiency_pct 跨论文定量合成"） |
| `verdict` | string | 是 | `allowed`（可合成）/ `blocked`（禁止合并）/ `partial`（可并列呈现但禁止合并，或覆盖不全） |
| `reason` | string | 是 | 判定理由，引用 cell_id |
| `based_on_cells` | list[string] | 是 | 依据的 cell_id 列表 |

### 示例

```json
{"decision_id": "D-001", "subject": "degradation_efficiency_pct 跨论文定量合成", "verdict": "blocked", "reason": "DOC-02 污染物不同（C-008），DOC-03 未报告效率（C-015）；不得合并不同染料数据集", "based_on_cells": ["C-003", "C-009", "C-015"]}
```

## 派生规则（渲染器实现，无需手写）

- `sources` = 按 paper_document_id 聚合所有记录的 paragraph_id 并排序。
- `status` = 无非 comparable 维度且无 blocked/partial 判定时 `success`，否则 `partial`。
- `uncertainty` = 每个 (论文 × 非 comparable 维度) 一条缺失边界（首见 cell_id + note），
  外加每条 blocked/partial 判定一条。
