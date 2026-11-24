# 文件名语法正则集（L3，naming patterns）

每个 pattern 有稳定 `pattern_id`，registry 与校验器按 id 对应；修改正则必须保留 id 语义，否则校验器会判"重跑抽取值不符"。作用于文件 basename（NFC）。

| pattern_id | field | regex | 说明 |
|---|---|---|---|
| rx_year_prefix | year | `^((?:19|20)\d{2})[_\-]` | 年份前缀，如 `2022_summary.csv` → 2022 |
| rx_year_anywhere | year | `(?<!\d)((?:19|20)\d{2})(?!\d)` | 文件名任意处的独立 4 位年份（候选次序在后） |
| rx_project_code | project | `(?<![A-Za-z0-9])(NSFC[-_]?\d{6,}|[A-Z]{2,5}[-_]\d{3,})(?![A-Za-z0-9])` | 项目号形态；**大小写敏感**且有边界环视，避免把 `spectrum_2020` 误切成项目号 |
| rx_version_suffix | version_note | `(?:^|[_\-（(])(v\d+|final|最终版|终稿|定稿|副本|copy)(?=[)）_.]|$)` | 版本后缀（忽略大小写），如 `report_v1.txt` → v1 |
| rx_dtype_raw | data_type | `(?:^|[_\-])raw(?:[_\-.]|$)` → 固定值 `raw_data` | 原始数据标记 |
| rx_dtype_report | data_type | `report|报告` → 固定值 `report` | 报告类（忽略大小写） |

## 内容首部模式（L2，CONTENT_PATTERNS）

作用于文本类文件（.txt/.md/.csv/.tsv/.json/.log/.dat 等，首部 4KB，utf-8/replace 解码；替换符过多视为非文本跳过）。每字段每文件只取第一次命中。

| pattern_id | field | regex 摘要 |
|---|---|---|
| cx_project_cn | project | `项目号：X` |
| cx_project_en | project | `Project: X` / `Grant No: X` |
| cx_instrument_cn | instrument | `仪器：X` / `仪器型号：X` |
| cx_instrument_en | instrument | `Instrument: X` |
| cx_author_cn | author | `作者：X` |
| cx_year_cn | year | `年份：YYYY` / `年度：YYYY` |

## 版本词干规范化（版本链用，与 L3 无关）

分组键 = basename 去扩展名后，剥除尾部版本标记（`v\d+ / final / 最终版 / 终稿 / 定稿 / 副本 / copy`），小写化。同词干同扩展名且 ≥2 个不同内容哈希 → 版本链，按 mtime 升序。

## 缺省类别桶（task.md 无模板时的目标路由）

`papers/ data/ scans/ supplementary/ drafts/ admin/ _unassigned/`。规则：伴随表/行政备注→admin；.csv/.tsv/.json/.dat→data；名称含 supp/补充→supplementary；含 draft/草稿→drafts；.txt/.md→papers；图像扩展→scans；其余→_unassigned（记原因）。名称含 行政/备注/admin/note → admin。task.md 给出 `{var}/{var}/...` 模板时模板优先，变量取自 registry winner 值，缺字段进 `_unassigned/` 并逐条记录缺哪些字段。
