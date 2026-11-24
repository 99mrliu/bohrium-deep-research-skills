# 数据字典可解析语法清单（compile_dictionary.py 所支持的全部写法）

编译器是机械的：**只**识别本文件列出的写法；遇到任何其他写法一律登记为
未解析项（U 编号），交由人工在 resolutions.json 中裁决，编译器自身绝不猜测。

## 1. 行级结构

### 1.1 Markdown 表格

表头单元格按下表映射（不区分大小写；未识别列忽略）：

| 表头写法 | 角色 |
| --- | --- |
| 字段 / 字段名 / 名称 / field / column | field |
| 单位 / unit | unit |
| 哨兵 / 哨兵值 / 缺失标记 / sentinel | sentinel |
| 有效范围 / 范围 / range | range |
| 检出限 / 检出下限 / lod | lod |
| 说明 / 备注 / 描述 / desc / description | 忽略 |

示例：

```
| 字段 | 单位 | 哨兵值 | 有效范围 | 检出限 | 说明 |
| --- | --- | --- | --- | --- | --- |
| concentration | mg/L | -999, ND | [0, 100) | 0.01 | 目标物浓度 |
```

抽取结果（source 指向该行）：

```json
[
  {"kind": "sentinel_missing", "field": "concentration", "params": {"tokens": ["-999", "ND"]}},
  {"kind": "range_qc", "field": "concentration",
   "params": {"lo": 0, "hi": 100, "lo_inclusive": true, "hi_inclusive": false}},
  {"kind": "lod_below", "field": "concentration", "params": {"lod": 0.01}}
]
```

单元格为 `-` / `—` / `–` / `/` / `无` / 空 时视为“无”，跳过。单位不产生规则，
只登记进 fields 元数据（供单位换算一致性核对）。

### 1.2 条目列表（bullet）

写法：`- 字段名: 关键字 值；关键字 值；描述文字…`（`;` 与 `；` 均可分段；
`关键字 值` 与 `关键字=值` 均可；关键字同 1.1，外加 `物理界`）。

示例：

```
- volume_ml: 单位 mL；哨兵 -999；物理界 [0, 1000]；量取样体积
```

抽取结果：

```json
[
  {"kind": "sentinel_missing", "field": "volume_ml", "params": {"tokens": ["-999"]}},
  {"kind": "physical_bound", "field": "volume_ml",
   "params": {"lo": 0, "hi": 1000, "lo_inclusive": true, "hi_inclusive": true}}
]
```

（`量取样体积` 不以任何关键字开头，按描述段忽略并记入 parse_report。）

### 1.3 键值行

写法：`字段名: 关键字 值；…`（无 `-` 前缀），与 1.2 同法解析。

## 2. 值级语法

### 2.1 范围（range_qc / physical_bound）

| 写法 | 抽取结果 |
| --- | --- |
| `[0, 100)` | lo=0 含, hi=100 不含 |
| `(0, 100]` | lo=0 不含, hi=100 含 |
| `[-50, 60]` | 闭区间 |
| `0–100`（en dash – 或 em dash —） | 闭区间 [0, 100] |

**不支持**：无括号波浪号 `0 ~ 100`、`约 0 到 100`、`0至100`、`≥0 且 ≤100`
等——一律登记未解析，交人工裁决。

### 2.2 哨兵 token（sentinel_missing）

逗号/顿号/斜杠分隔：`-999, ND` → `["-999", "ND"]`。
特殊归一：`blank` / `空` / `空格` / `空字符串` → 空串 `""`（匹配空白单元格）。
其余 token 按字面、去首尾空白后精确匹配（大小写敏感）。

### 2.3 检出限（lod_below）

`0.01` 或 `0.01 mg/L` → `{"lod": 0.01, "unit": "mg/L"}`（unit 可省）。
任何非数值开头的表述（如 `见附录 B`）一律登记未解析。

### 2.4 单位换算（unit_scale，由工单条目编译）

可编译句式：`将 <field> 由|从 <from> 换算为|转换为|→ <to>`，系数来自：

1. 显式写法 `×1000` / `x1000` / `1000 倍`；或
2. 内置单位对表：mg/L↔μg/L、μg/mL↔mg/L、g/L↔mg/L、ng/mL↔μg/L。

两者都缺失 → 登记未解析，交人工裁决（approve 时须给出 factor）。

### 2.5 去重（dedup，由工单条目编译）

可编译句式：`按 <field> …去重…保留首条|末条`。
抽取：`{"key": field, "normalize": ["strip", "upper"], "keep": "first"|"last"}`；
未写保留规则时默认 `first`（保留首条）。

## 3. 不可解析时的裁决流程

1. 编译器在 `parse_report.md` 的“未解析/歧义项”表登记 U 编号、原文、原因。
2. Agent（或人工）在 `resolutions.json` 中对每个 U 编号三选一：
   - `approve`：认可该行的语义并给出完整 rule（kind/field/params）；
   - `adjust`：同上，但明确是对原文写法的修正性补全（rationale 说明修正依据）；
   - `reject`：该行不产生规则（rationale 写明原因，如“附录未随案提供”）。
3. 每条裁决的 `source.file`/`source.line` 必须与 parse_report 登记的未解析项
   位置**完全一致**；validate_rules.py 会强制核对，不符即退出码 4。
4. 语义无法确定的，**必须 reject 并在 uncertainty 中说明，绝不猜测**。
5. 未裁决的未解析项不会失败终止，但会作为 `unresolved_line` 缺口写入
   `rules.final.json` 的 gaps 与 coverage_matrix.csv，并最终写入 result.json
   的 uncertainty。
