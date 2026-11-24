# 契约协议参考（semalign-contract）

## output_contract 的解读规则

`case.json` 中的 `output_contract` 是评分的证据范围，兼容三种形态：

- 字符串数组：`["cleaned_table", "summary_statistics", "figures"]`
- 对象数组：`[{"name": "cleaned_table", "type": "csv", ...}, ...]`（取 `name`/`field` 键）
- 对象：`{"fields": [...]}` 或直接以字段名为键的 dict

契约字段是**必须出现且必须非 null** 的最低集合；你可以增加额外字段（如行数对账、中间表路径），不得减少。

## result.json 填写规范

| 字段 | 要求 |
|-|-|
| `case_id` | 与 case.json 逐字符一致，gate 会核对 |
| `status` | `success`（全部字段落实且 gate 通过）/ `partial`（有 missing_fields 说明）/ `failed`（无法完成，仍须交付骨架说明原因） |
| 契约字段 | 真实计算结果；数字保留与数据精度相符的有效数字；文件用 `/app/output` 下的路径 |
| `anomalies` | 数组。每条记录一个缺失/异常/未裁决项：发现位置、影响、处置。空数组仅当确实无异常 |
| `missing_fields` | 仅 partial 时使用：`[{"field": "...", "reason": "..."}]` |
| `provenance` | 骨架已含 `input_hashes` 与 python 版本；追加你实际运行的命令清单与工具版本 |

## 常见契约违例（gate 会拦截）

1. 骨架字段留着 null 就交付 —— 最常见的"看起来完成了"。
2. `status="success"` 但某字段实际没算出来。
3. 图字段登记了路径但文件未写入 `/app/output`（路径写错、相对路径解析不到）。
4. `case_id` 从 task.md 标题抄写而非读自 case.json。
5. `anomalies` 写成字符串而非数组，或把异常直接删除不留记录。
6. 重跑后 `provenance.input_hashes` 与实际输入不符（换了数据没重跑 inspect）。

## 字段对齐裁决记录模板

```json
{"issue": "字典字段 'Compressive strength (MPa)' 与实际列 'ccs' 仅模糊匹配 (score=0.62)",
 "decision": "采纳映射：列取值范围 2.3–82.6 与 MPa 量级一致，且为唯一数值型强度候选列",
 "alternative": "拒绝映射则强度相关统计全部无法交付",
 "decided_by": "agent", "confidence": "medium"}
```

每条裁决写入 `anomalies`，使复核者能重演你的选择。
