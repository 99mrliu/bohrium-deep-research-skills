# 字段级文件格式（renumber-sync-engine）

所有文件 UTF-8、LF 换行、无时间戳（保证确定性复跑逐字节一致）。JSON 一律
`ensure_ascii=False`。示例均取自 `examples/output/`（全虚构合成数据的真实运行产物）。

## 1. occurrences.jsonl（cite_scan 产物）

每行一个 JSON 对象，按 reading_order 升序。字段：

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| reading_order | int，自 1 | 全局真实阅读序（行升序、行内列升序） |
| region | string | body / figure_caption / table_caption / footnote / appendix |
| line | int，1 基 | 所在行号 |
| col | int，0 基 | 标记起始字符列 |
| raw | string | 标记原始文本，如 `[7,3]`、`^[1-3]^`、`(Smith, 2020a)` |
| style | string | numeric-bracket / numeric-superscript / author-year / author-year-cjk |
| body | string | 标记体（括号内内容），供区间解析与 V4 使用 |
| refs | [string] | 展开后的条目引用集（原标签），如 `["1","2","3"]`；著者-年为单元素键 |
| para | int，0 基 | 所在段落索引（段落=空行分隔的非空行块），供 merge_paragraphs 使用 |

示例：

```json
{"reading_order": 6, "region": "body", "line": 23, "col": 36, "raw": "[7,3]", "style": "numeric-bracket", "body": "7,3", "refs": ["7", "3"], "para": 5}
```

## 2. labels.json（cite_scan 产物）

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| style_hint | string | numeric / author-year / mixed / none（按标记与列表形态推断） |
| labels | object | 原标签 → sid（按全局首现顺序 sid-001…；未引条目按列表顺序续赋） |
| sid_to_label | object | sid → 原标签（labels 的逆映射） |
| entries | [object] | 每个列表条目：sid、original_label、kind（numeric/author-year）、text、ref_line |
| dangling | [string] | 悬空标签：被标记引用但不在列表中的原标签（按首现顺序） |
| uncited | [string] | 未引用标签：在列表中但从未被任何标记引用的原标签（按列表顺序） |
| occurrence_count | int | 标记总数 |
| reference_count | int | 列表条目数 |
| manuscript / references | string | 输入文件名（仅basename，审计用） |
| region_counts | object | 各区域的标记计数 |
| unparsed_reference_lines | [object] | 无法解析的列表行（line/text），正常应为空 |

## 3. ops.json（人工/模型编写，plan 输入）

顶层 `{"ops": [op, ...]}`；坐标一律指向原始稿件。op 形态：

```json
{"op": "delete_marker", "reading_order": 4}
{"op": "insert_marker", "line": 44, "after_text": "aged fastest", "labels": ["2"]}
{"op": "insert_marker", "line": 44, "col": 37, "labels": ["4", "6"]}
{"op": "merge_paragraphs", "para_a": 2, "para_b": 3}
{"op": "move_section", "heading": "^## 2\\.", "after_heading": "^## 3\\."}
{"op": "merge_entries", "keep": "3", "drop": "7"}
```

- line 1 基；col 0 基；after_text 为该行进首个匹配子串，插入点在其末尾。
- para_a/para_b 为 0 基段落索引（= occurrences.jsonl 的 para 字段）。
- heading/after_heading 为正则，须在标题行中唯一匹配，否则 plan 报错。
- 每个 op 可附任意说明字段（如 reason），引擎忽略但保留进 label_map。

## 4. label_map.json（plan 产物 / apply 输入与产物）

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| format_version | string | 当前 `1.0` |
| style | string | numeric-bracket / numeric-superscript / author-year |
| ops | [object] | 本次施加的操作集（apply 复算的依据） |
| mappings | [object] | 三层映射，按 sid 排序。字段：sid、original_label、new_label（string 或 null）、status（cited / uncited_retained / merged_away）；merged_away 另带 merged_into |
| reference_order | [string] | 重排后列表的 sid 顺序 |
| dangling_removed | [object] | 被 delete_marker 删除的标记（reading_order/raw/region/line） |
| uncited_retained | [string] | 保留的未引用条目原标签 |
| edited_manuscript_text | string | 渲染后的完整稿件文本（plan 渲染，apply 校验后落盘） |
| edited_references_text | string | 重排渲染后的完整文献表文本 |
| notes | [string] | 判定依据（合并、移动、后缀重赋等） |

apply 逐字段比对的键：format_version、style、ops、mappings、reference_order、
dangling_removed、uncited_retained、edited_manuscript_text、edited_references_text。

## 5. sync_report.json / sync_report.md（sync_verify 产物）

sync_report.json：

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| all_pass | bool | V1–V8 是否全部通过（退出码 0/1 的依据） |
| style_detected | string | 核验时使用的样式（label_map 提供，否则自动推断） |
| rules | object | V1–V8 → {name, pass, detail}；detail 含违规的行列与期望/实际值 |
| summary | object | occurrences、numeric_markers、author_year_markers、reference_entries、numeric_labels、retained_uncited_entries、unparsed_reference_lines、failed_rules |

sync_report.md 为同内容的 Markdown 表格，供人审。任何规则 pass=false 时进程
退出码为 1，且两份报告照常写出。

## 6. 退出码约定

| 进程 | 0 | 1 | 2 |
| --- | --- | --- | --- |
| cite_scan.py | 成功 | — | 输入/参数错误 |
| renumber.py plan | 成功 | — | PlanError（坐标/操作/悬空等） |
| renumber.py apply | 成功 | 校验失败（label_map 与复算不一致、样式不符、占位符残留），不写任何文件 | 输入读取失败 |
| sync_verify.py | V1–V8 全过 | 存在违规（报告照常写出） | 输入/参数错误 |
