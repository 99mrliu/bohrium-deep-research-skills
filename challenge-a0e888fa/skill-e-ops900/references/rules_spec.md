# rules.json 配置规范

`rules.json` 是管道唯一的判断输入：Agent 读完数据字典、单位/QC 规则与工单后
编写。管道只执行配置里**显式声明**的处置；没写的就是不做，原值保留。

## 顶层字段

| 字段 | 必填 | 说明 |
|---|---|---|
| `input` | ✅ | 输入表路径（先自行修复为规范 CSV，utf-8/逗号/LF） |
| `encoding` | 否 | 默认 `utf-8-sig` |
| `key_columns` | 建议 | 归一化去重主键；缺省则不做去重 |
| `case_id` | ✅ | 写入 result.json |
| `contract_scaffold` | 建议 | 合同字段占位（键=字段名，值=类型占位），管道会并入实测 summary |
| `missing` | 否 | `tokens`: {哨兵: 四类语义}；`policy`: mark（默认）/empty |
| `units` | 否 | 换算声明列表（见下） |
| `bounds` | 否 | 物理界声明列表（见下） |
| `dedup.keep` | 否 | 默认 most_complete |

## missing.tokens 的四类语义

`not_detected`（未检出）、`below_lod`（低于检出限，`<数值` 形原样保留）、
`entry_missing`（录入缺失，含 -999/NA/空白）、`true_zero`（真值 0，不是缺失）。
分类只标记（台账记录），**管道没有插补功能**。

## units 条目

```json
{"field": "value", "from_column": "unit",
 "map": {"μg/L": ["mg/L", 0.001], "g/L": ["mg/L", 1000.0]}}
```

- 只有 `map` 里列出的 (原单位→目标单位, 倍率) 才会换算；
- 每次换算做逆运算复核，不可逆则保留原值并写入 review_queue；
- `from_column` 的单位标签随换算联动更新并入台账；
- 带偏移换算（℃/K）不要写进 map——管道只做纯倍率。

## bounds 条目

```json
{"field": "value", "by_column": "metric",
 "map": {"溶解氧": [0, 20], "总磷": [0, 5]}}
```

或全字段统一界：`{"field": "value", "range": [0, 100]}`。
越界只标记（`out_of_bounds_flag`），不剔除；剔除须工单显式下令，由 Agent
在管道外逐格处理并自记台账。

## dedup

归一化（大小写/空格）后按键分组：非键列全同 → 按 keep 去重，丢弃行整行
JSON 入台账；非键列不同 → 键冲突，全部保留进 review_queue。
