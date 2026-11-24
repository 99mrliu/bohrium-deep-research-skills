# 规则表（规则即数据）—— schema、出处要求与填写示例

四张规则 CSV 由 Agent 根据**数据字典、按指标给出的单位/QC 规则、清洗工单**编写，
`run_steps.py` 校验后载入同名 SQLite 规则表（表名加 `rule_` 前缀，另增自增列
`rule_id`，供 change_log / issues 引用）。

**出处（source）铁律**：每一行规则的 `source` 列必须非空，且必须指认具体出处
（数据字典编号/章节、单位QC规则编号、工单编号）。`run_steps.py` 发现空 source
即以退出码 4 拒绝执行。找不到出处的规则宁可不写，并在 result.json 的
uncertainty 中说明；禁止编造出处。

CSV 约定：UTF-8（可有 BOM）、逗号分隔、首行表头；`token` 列原样保留（空串表示
空白单元格哨兵），其余列读取时去首尾空白。

---

## 1. missing_tokens.csv → rule_missing_tokens

| 列 | 类型 | 含义 |
| --- | --- | --- |
| token | TEXT | 源文件中代表“缺失/非法”的字面量（空白单元格用空串） |
| class | TEXT | 缺失分类，自定义受控词表：sentinel / below_detection / blank / invalid … |
| source | TEXT | 出处（必填） |

填写示例：

```csv
token,class,source
-999,sentinel,数据字典 v1.2 第3节：-999 为缺测哨兵值
ND,below_detection,数据字典 v1.2 第3节：ND 表示低于检出限
,blank,清洗工单 W-01：空白单元格视为缺失
N/A,not_reported,工单 W-01 附注：N/A 按未报告处理
```

清洗效果：`cleaned.value` 置 NULL，`cleaned.missing_class` 保留分类——**分类信息
不丢，值不猜**。

## 2. unit_map.csv → rule_unit_map

| 列 | 类型 | 含义 |
| --- | --- | --- |
| field | TEXT | 指标/字段名（与规范化后的 parameter 小写匹配） |
| from_unit | TEXT | 源文件中的单位字面量 |
| to_unit | TEXT | 数据字典规定的规范单位 |
| factor | REAL | 换算因子：new_value = old_value × factor（必须可解析为数值） |
| source | TEXT | 出处（必填） |

填写示例：

```csv
field,from_unit,to_unit,factor,source
lead,µg/mL,µg/L,1000,单位QC规则 U-03：Lead 以 µg/L 为准，1 µg/mL = 1000 µg/L
nitrate,mg/L,µg/L,1000,单位QC规则 U-05：Nitrate 以 µg/L 上报
```

注意：只登记数据字典/单位QC规则**明确给出**的换算；单位相同但大小写混写
（如 MG/L 与 mg/L）也应以一条 factor=1 的规则显式登记，使单位列统一可审计。

## 3. qc_bounds.csv → rule_qc_bounds

| 列 | 类型 | 含义 |
| --- | --- | --- |
| field | TEXT | 指标/字段名（小写匹配） |
| lo | REAL | 合法下界（含） |
| hi | REAL | 合法上界（含） |
| action | TEXT | 处置动作，受控词表：flag（登记 issues，保留原值）/ 其他值暂不实现 |
| source | TEXT | 出处（必填） |

填写示例：

```csv
field,lo,hi,action,source
ph,0,14,flag,单位QC规则 Q-01：pH 合法区间 [0,14]
arsenic,0,100,flag,单位QC规则 Q-02：Arsenic 不得超过 100 µg/L
```

铁律：QC 越界行**只标记、不修改、不删除**；issues 表记录 line_no 与区间。

## 4. key_fields.csv → rule_key_fields

| 列 | 类型 | 含义 |
| --- | --- | --- |
| field | TEXT | 构成主键的字段名 |
| role | TEXT | 角色，受控词表：natural_key（自然键，参与去重）/ attribute（普通属性） |
| source | TEXT | 出处（必填，须写明 keep 依据，如“保留 line_no 最小者”） |

填写示例：

```csv
field,role,source
sample_id,natural_key,清洗工单 W-02：以 sample_id 为自然键，upper+trim 规范化后去重，保留 line_no 最小者
```

去重规则必须来自工单；keep 依据同时落进 `dedup_keep.basis` 列（见
`sql_patterns.md` 第 3 节），重复行全部登记 issues，不静默丢弃。
