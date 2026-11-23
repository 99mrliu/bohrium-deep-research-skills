# result.json 输出合同（output contract）

`/app/output/result.json` 是唯一的机器可读交付声明。必须包含以下字段，
模板见 `assets/result.template.json`，组装与校验用 `scripts/build_result.py`。

## 字段语义

| 字段 | 类型 | 语义与诚实规则 |
|---|---|---|
| `case_id` | string | 从 `/input/case.json` 原样复制的案例标识，不得编造 |
| `status` | enum | `success`：全部合同产物齐备且校验通过；`partial`：有可交付物但缺项，**必须**配 `limits` 字段逐项命名缺什么、为什么；`failed`：无可交付图（仍须写 result.json 说明原因） |
| `limits` | string | 仅 `partial` 时必填；例："无 latex 引擎：仅交付 .tex 源，缺 PDF/PNG/SVG 导出与全部校验" |
| `editable_source` | string(路径) | 主 .tex 源文件的绝对路径（可编辑交付物本体）。编辑案例中是被编辑后的 .tex |
| `export_artifact` | string[](路径) | 实际生成的导出件列表（PDF/PNG/SVG）。没生成就不要列；列出的文件必须真实存在 |
| `content_map` | object | 图面关键元素 → 材料来源定位。键：实体名、边（"A -> B (relation)"）、图例条目、数值；值：如 `"paper.pdf p.4 Fig.2"`、`"paper.pdf p.6 Results para 2"`、`"data.csv:log2FC row GeneD=3.05"`。每个关键元素都要有；无来源的元素属于违规 |
| `compliance_checks` | array/object | 校验结果汇总：`compile`、`fonts_embedded`、`labels_present`、`pixel_probe`、`legend_data_consistency` 等，每项含 `name/status(pass|fail|skipped)/detail`。工具缺失导致的 skipped 必须如实标注 |
| `exceptions` | array | 所有歧义、缺失工具、未解决冲突的清单。空列表只在零例外时合法 |
| `generator` | string | 固定标识 `tikz-mechanism-typeset skill (LaTeX/TikZ typeset-driven)` |
| `notes` | string(可选) | 自由说明：产物清单、编辑日志路径、修复迭代次数等 |

## 诚实规则（不可违反）

1. `status` 宁低不高：有任何合同产物缺失或关键校验 fail，不得标 `success`。
2. 列出的 `export_artifact` 路径必须真实存在且由本技能脚本产出。
3. `content_map` 的定位必须指向真实读过的材料位置；没读过就不许写。
4. 工具缺失一律 `skipped` + exceptions，不得静默视为通过。
5. 合成示例（assets/example-*）的内容**永不**进入真实案例的 result.json。
6. 先写 partial 再增量改进：第一份可编译图出现后立刻写 result.json，
   后续每完成一个阶段就更新它，避免超时无交付。
