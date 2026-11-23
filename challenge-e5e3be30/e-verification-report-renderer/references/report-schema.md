# result.json 与判定对象 schema 定义

本文件是 `contract_assemble.py`、`cards_render.py`、`gate.py` 共用的数据契约。
字段语义以本文件为准；脚本内嵌校验与本文件保持一致。

## 1. result.json 顶层结构

`/app/output/result.json` 必须包含以下三类字段：

### 1.1 固定标准字段

| 字段 | 类型 | 约束 |
| --- | --- | --- |
| `case_id` | string | 必须与 `/input/case.json` 的 `case_id` 完全一致 |
| `status` | string | 枚举：`success` / `partial` / `cannot_determine` / `refused`，必须与内容自洽 |
| `sources` | array | 引用的证据来源列表（论文、页码、工具产物等），可为空数组 |
| `uncertainty` | string | 总体不确定性声明，可为空字符串但键必须存在 |
| `change_records` | array | 变更记录，每条 `{timestamp, action, detail}`；骨架生成与每次 merge 自动追加 |
| `missing_items` | array | `status=partial` 时必填的非空数组，必须覆盖全部缺失/空契约字段 |

### 1.2 output_contract 字段（动态发现）

`case.json` 的 `output_contract`（dict 的键名集合，或 list 的元素）声明了
评测方要求的全部交付字段。`result.json` 必须逐键包含这些字段：

- `status=success`：全部契约字段非空（非 `null`/`""`/`[]`/`{}`）；
- `status=partial`：允许契约字段为空，但 `missing_items` 必须逐一列出空/缺字段；
- `status=cannot_determine` / `refused`：允许契约字段为空，必须在 `uncertainty`
  中说明原因。

### 1.3 演示案例的 8 个契约字段（examples/case.json）

| 字段 | 类型 | 含义 |
| --- | --- | --- |
| `verdicts` | array | 判定对象数组（见第 2 节） |
| `summary` | string | 总体结论摘要 |
| `verdict_distribution` | object | 四级判定计数 |
| `evidence_cards_path` | string | 证据卡片 Markdown 路径 |
| `report_markdown_path` | string | 核验报告 Markdown 路径 |
| `report_preview_path` | string | 真实渲染预览路径（PDF 或 HTML） |
| `render_chain_used` | string | 实际渲染链：xelatex / pdflatex / pandoc / html |
| `open_questions` | array | 未决问题清单 |

实际评测时契约字段由评测方 case 决定，**以运行期 `skeleton` 子命令发现为准**，
不要硬编码字段名。

## 2. 判定对象（verdicts 数组元素）

| 字段 | 类型 | 约束 |
| --- | --- | --- |
| `claim_id` | string | 非空，全局唯一 |
| `claim_text` | string | 非空，论断原文照录 |
| `verdict` | string | 枚举：`supported` / `partially_supported` / `contradicted` / `insufficient_evidence` |
| `quotes` | array | 非空；每项见第 3 节 |
| `rationale` | string | 非空，判定理由（为何是该判定而非相邻判定） |
| `uncertainty` | string | 键必须存在；无不确定性用空字符串 |
| `conflicts` | array | 可选；每项 `{side_a, side_b, note?}`，side 为证据对象 |

判定纪律（评测契约）：

- 四级判定互斥；主题相关 ≠ 支持；未报告 ≠ 反驳；
- 证据冲突时判 `partially_supported`（或 `insufficient_evidence`），
  并在 `conflicts` 中并列双方原话，不替作者取舍；
- 每条 quote 必须能在声明页码的分页文本中逐字（归一化后）找到，`gate.py` 强制回查。

## 3. 证据对象（quotes 元素 / conflicts 的 side）

| 字段 | 类型 | 约束 |
| --- | --- | --- |
| `quote` | string | 非空，逐字引用（gate 归一化回查：NFKC、弯引号归一、空白折叠） |
| `page` | int | 正整数，PDF 页码（与 pages.jsonl 的 `page` 对应） |
| `paragraph` | string | 可选，段落/章节定位（如 "2. Methods"） |
| `source` | string | 可选，来源描述（文件名、DOI 等） |

## 4. pages.jsonl

每行一个 JSON 对象：`{"page": <正整数>, "text": "<该页纯文本>"}`。
由 PDF 分页抽取得到（平台 pdf-render-tool / pdftotext -layout，或示例中的
`\f` 分页纯文本）。gate.py 以它为回查基准。
