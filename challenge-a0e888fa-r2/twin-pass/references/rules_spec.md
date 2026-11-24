# rules.json 规约 schema（version 1）

rules.json 是双引擎的**唯一输入**。它由 Agent 阅读数据字典、单位/QC 规则与清洗
工单后编写；两个引擎各自独立解析并校验它（校验失败退出码 3）。本文件给出完整
schema 与逐字段说明。编写时的总原则：

> **每条规则都必须带 `source` 出处定位**（指向字典/规则/工单的章节、条目或行
> 号）。没有出处的规则不得写入规约；工单未覆盖的语义要么查补依据，要么写入最贴
> 近的解读并在 result.json 的 uncertainty 中声明——不允许留白让引擎默认值替你做
> 决定。

## 顶层结构

```json
{
  "version": 1,
  "case_id": "CASE-XXXX",
  "key": {"column": "analyte"},
  "meta_columns": ["matrix", "batch"],
  "unit_column": { "...": "见下" },
  "measures": [ { "...": "见下" } ],
  "dedup": { "...": "见下" }
}
```

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `version` | number | 是 | 固定为 `1`。 |
| `case_id` | string | 是 | 案例标识，原样写入 summary.json，用于与 result.json 对齐。 |
| `key.column` | string | 是 | 主键列名（去重按此列归一化后分组）。 |
| `meta_columns` | string[] | 否 | 原样透传到 cleaned.csv 的非测量列（如基质、批次）。默认 `[]`。 |
| `unit_column` | object | 否 | 逐行单位列配置；无单位换算需求时整个省略。 |
| `measures` | object[] | 是 | 测量列规则，至少一条；列名不得重复。 |
| `dedup` | object | 是 | 主键归一化与去重保留规则。 |

## `unit_column`（逐行单位换算）

```json
"unit_column": {
  "column": "unit",
  "target": "mg/L",
  "factors": {"mg/L": 1.0, "μg/mL": 1.0, "μg/L": 0.001},
  "source": "unit_qc_rules.md#unit-map"
}
```

| 字段 | 说明 |
| --- | --- |
| `column` | 存放逐行单位标签的列名。 |
| `target` | 目标单位。cleaned.csv 中启用换算的测量列一律以目标单位输出。 |
| `factors` | 映射表 `{单位标签: 乘数}`，`换算值 = 原值 × factor`。**必须包含 target 自身**（通常 1.0）。标签按规范化工作副本中的精确字符串匹配（大小写、Unicode 归一化后）；遇到表外标签引擎退出码 4，此时应据字典把该单位与因子补入后双跑，字典无依据则不得编造。 |
| `source` | 映射表出处。 |

**作用域**：换算只作用于 `measures[].convert_units: true` 的测量列；百分比等无量
纲列不得换算（示例中 `recovery_pct` 即为 false）。物理界 `bounds` 在**换算后**的
目标单位下评估。

cleaned.csv 中该列以 `<column>_raw` 原样保留，便于核对换算前后单位。

## `measures[]`（测量列规则）

```json
{
  "column": "concentration",
  "source": "data_dictionary.md#concentration",
  "convert_units": true,
  "sentinels": [
    {"pattern": "",    "class": "not_detected",          "source": "work_order.md#sentinels"},
    {"pattern": "ND",  "class": "below_detection_limit", "source": "work_order.md#sentinels"},
    {"pattern": "-999","class": "entry_missing",         "source": "work_order.md#sentinels"}
  ],
  "zero_is_true": true,
  "bounds": {"min": 0, "max": 5000, "action": "flag_keep", "source": "unit_qc_rules.md#bounds"}
}
```

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `column` | string | 是 | 测量列名。 |
| `source` | string | 是 | 该列规则的总体出处（字典条目）。 |
| `convert_units` | bool | 否 | 是否按 `unit_column` 换算。默认 `false`。为 true 时规约必须含 `unit_column`。 |
| `sentinels` | object[] | 否 | 哨兵值分类表，见下。 |
| `zero_is_true` | bool | 否 | 数值 0 是否标记为 `true_zero`（真值 0，保留数值 0 并标记，不是缺失）。默认 `false`。 |
| `bounds` | object | 否 | 物理界 QC，见下。 |

### 哨兵分类（标记，不插补）

- `pattern`：单元格**去首尾空白后**的精确匹配串；空串 `""` 匹配空单元格。
- `class` 只能取：
  - `not_detected`（未检测）
  - `below_detection_limit`（低于检出限）
  - `entry_missing`（录入缺失）
- 命中哨兵的单元格：cleaned.csv 值列输出空，class 列输出对应类别，台账记录
  `cell_flag`，**绝不填任何替代值**。
- 真值 0 不走哨兵表：数值解析为 0 且 `zero_is_true: true` 时标记 `true_zero`，
  值列保留 `0`。
- 既不命中哨兵又无法解析为有限数的单元格：类别 `unparseable`、flag
  `unparseable_value`、**原值保留**，台账记录。出现此类通常说明哨兵表不全——
  优先回字典补哨兵规则，再双跑。

### 物理界 QC（保留原值 + flag）

- `min`/`max`：闭区间界，目标单位下评估（若启用换算）。`min <= max`，校验强制。
- `action`：只允许 `"flag_keep"`——越界值**保留原值**，flag 列输出
  `out_of_bounds_high` / `out_of_bounds_low`，台账记录。禁止删除或改写越界值。

## `dedup`（归一化主键去重）

```json
"dedup": {
  "normalize": ["trim", "collapse_ws", "lower"],
  "keep": "most_complete",
  "tie": "first_occurrence",
  "source": "work_order.md#dedup"
}
```

| 字段 | 说明 |
| --- | --- |
| `normalize` | 归一化步骤，按序执行。允许值：`trim`（去首尾空白）、`collapse_ws`（折叠内部连续空白为单个空格）、`lower`（小写）、`nfc`（Unicode NFC）。 |
| `keep` | 固定 `most_complete`：在归一化键相同的候选行中，保留**完整度得分**最高者。完整度 = 该行的测量列中“非哨兵且可解析为有限数”的单元格数（0 与越界值算完整；哨兵与不可解析文本不算）。 |
| `tie` | **平局规则，必须显式给出**：`first_occurrence`（仍并列取首现）或 `last_occurrence`（取末现）。省略时引擎各自使用文档化的相反默认值（A 首现 / B 末现），双跑必然分歧——这正是用来暴露规约歧义的机制，不要依赖它。 |
| `source` | 去重规则出处。 |

被保留行记 `dedup_keep`、被丢弃行记 `dedup_drop`（含双方得分与所用平局规则），
写入 ledger.csv。

## 输出契约（两引擎一致，确定性）

- `cleaned.csv`：`src_row,<key>_raw,<key>_norm,<meta...>,[<unit>_raw,]` 后接每个测
  量列三件套 `<col>,<col>_class,<col>_flag`；行按保留行 src_row 升序；浮点固定
  `.10g` 格式；LF 行尾。
- `ledger.csv`：`record,src_row,field,record_class,detail,source`，按
  `(src_row, field, record, record_class)` 显式排序。record 取值：
  `dedup_keep / dedup_drop / cell_flag / unit_convert`。
- `summary.json`：仅过程计数（rows_input/rows_output/duplicates_dropped/
  cell_class_counts/flag_counts/unit_conversions），`aggregate_statistics` 固定
  为禁用声明；键排序、缩进 2。**禁止任何总体统计量。**
- 引擎退出码：`0` 成功；`3` 规约校验失败；`4` 输入表错误（缺列、长短行、空表、
  未知单位标签）。

## source 字段的写法

`source` 是自由字符串，但必须能让人（与评审）定位依据，推荐形态：

```
<file>#<section-or-anchor>            例：data_dictionary.md#concentration
<file>:L<行号>                        例：work_order.md:L42
case.json:<json路径>                  例：case.json:qc_rules.units
synthetic:<说明>                      仅示例/合成数据使用
```

result.json 的 `sources` 字段应汇总 rules.json 中出现的全部 source。
