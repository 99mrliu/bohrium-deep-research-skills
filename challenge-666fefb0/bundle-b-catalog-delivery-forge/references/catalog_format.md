# 交付物格式契约（四件套）

四件套全部由 `render_catalog.py` 从同一份 `operations.jsonl` + `merged_plan.json`
渲染，单一数据源保证它们彼此一致、且与 result.json 一致。任何手工编辑都会在
下一次 finalize 重跑时被覆盖——要改结论，改 `overrides.json` 后重跑。

## 1. catalog.md（人读总目录）

- 头部：case_id、生成时间、输入/已归档/跳过计数。
- `## 已归档`：按 `category/subcategory` 分组；条目含规范名（粗体）、fid、
  原始路径 → 归档路径、SHA-256 短码、年份、DOI、版本关系标注、低置信度标记。
- `## 未归档（skipped）`：每个未归档文件一行，含状态与恢复建议。
- `## 版本关系`：版本组、relation、canonical 与证据。

## 2. catalog.csv（机读平表）

14 列固定表头：`fid,status,doc_type,category,subcategory,new_name,original_path,
archived_path,sha256,size_bytes,year,doi,disposition,note`。每输入文件恰好一行，
`status` 为 `archived` 或 `skipped: <reason>`。

## 3. tree_diff.md（前后对照）

- 上部：整理前/整理后目录树两栏并排。
- 下部：逐文件移动对照（原始路径 → 归档路径 + disposition；未移动的注明原因）。

## 4. verify_report.md（哈希复核）

逐操作一行：`op_id | 源 SHA-256 短码 | 目标 SHA-256 短码 | 一致/不一致`。
结论行为"全部一致 ✓"或"存在不一致 ✗"；不一致明细单列一节，且必须同步出现在
result.json 的 uncertainties。

## 交叉链接规则

- fid（F001…）是四件套与 result.json 之间的唯一连接键。
- operations.jsonl 的 `op_id = op-<fid>`；library_index 条目含同一 fid。
- 复核路径：catalog.md 条目 → fid → operations.jsonl 哈希 → verify_report.md 结论。
