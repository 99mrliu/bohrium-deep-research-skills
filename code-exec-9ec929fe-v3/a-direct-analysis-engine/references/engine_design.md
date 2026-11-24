# engine_design.md — 引擎设计说明

本文档说明 `scripts/case_engine.py` 的规则模式、默认清洗策略及其理由、异常分类、
契约字段映射策略、双通道复核方法与已知局限。

## 1. rules.json 模式

`run --rules rules.json` 可覆盖以下默认规则（未给出的键保持默认）：

```json
{
  "missing_tokens": ["", "NA", "N/A", "NaN", "nan", "null", "None", "-"],
  "drop_duplicates": true,
  "listwise_delete_missing": false,
  "coerce_numeric": true,
  "numeric_majority": 0.9,
  "outlier_iqr_factor": 1.5,
  "groupby_max_levels": 50
}
```

| 键 | 含义 |
|---|---|
| `missing_tokens` | 视为缺失（置 null）的字面标记集合，绝不当作 0 |
| `drop_duplicates` | 是否删除精确重复行（删除条数永远被记录） |
| `listwise_delete_missing` | 为 true 时整行删除含缺失行；默认 false，即行保留、缺失置 null |
| `coerce_numeric` | 数值列是否强制转型；失败值置 null 并记 `type_coercion_failure` |
| `numeric_majority` | 非缺失值中可解析为数值的比例阈值，达到即判为数值列 |
| `outlier_iqr_factor` | IQR 离群标记系数（默认 1.5，只标记不删除） |
| `groupby_max_levels` | 目标列水平数上限，超过则跳过逐水平 group-by 并记录原因 |

## 2. 默认清洗策略与理由

1. **缺失置 null、行保留**：缺失本身是信息；静默丢弃会改变样本构成且不可追溯。
   仅在 `listwise_delete_missing=true` 时整行删除，且删除条数进入行对账。
2. **精确重复行删除**：逐字节相同的行通常是录入/导出错误；删除但计数并记入
   `duplicate_rows` 异常与 row_reconciliation（raw → kept → duplicates_removed →
   final）。
3. **离群值只标记不删除**：离群可能是真实物理测量；引擎按 1.5×IQR 围栏计数
   （`outliers_iqr` 字段），是否处理交由人工裁决。
4. **数值列判定用多数决（90%）**：允许个别录入故障（如 "error"）不拖垮整列
   类型；故障值置 null 并记录，而非静默当作 0 或丢行。
5. **编码与分隔符容错**：utf-8-sig → gb18030 顺序解码；csv.Sniffer 嗅探分隔符，
   失败回退逗号。中文导出的 CSV 常见 BOM 与 GBK 编码，此顺序覆盖两种情形。

## 3. 异常分类（anomaly taxonomy）

| kind | 触发条件 |
|---|---|
| `missing_file` | case.json / task.md / 预期输入缺失 |
| `no_csv_found` | 输入中无 CSV |
| `undecodable_csv` | utf-8-sig 与 gb18030 均解码失败 |
| `undecodable_json` | case.json 解析失败 |
| `contract_shape_unknown` | output_contract 既非列表也非字典 |
| `missing_token` | 列内存在缺失标记（计数，行保留） |
| `duplicate_rows` | 删除的精确重复行数 |
| `listwise_deletion` | 按规则整行删除含缺失行（计数） |
| `type_coercion_failure` | 数值列中无法转型的值（计数 + 示例） |
| `db_error` | SQLite 打开/调查失败 |
| `sql_error` | SQL 语句执行失败（后续语句继续） |
| `empty_result` | SQL 返回 0 行（正常结果，非错误） |
| `figure_degraded` | matplotlib 不可用或无数值列可绘图 |
| `unmapped_contract_field` | 契约字段无法映射到引擎产物 |
| `rules_error` | rules 文件解析失败，回退默认规则 |
| `inventory_error` | 输入清点阶段读文件失败 |

## 4. 契约字段映射策略

1. 对契约字段名做归一化：NFKC、小写、去空白/下划线/连字符。
2. 先精确匹配映射表键（caseid、cleanedtable、statistics、figures、queries、
   provenance、anomalies、rowreconciliation、runlog、status 等）。
3. 再做包含匹配（任一方包含另一方，键长 ≥3）。
4. 仍无匹配则该字段置 null，记入 `missing_fields`（含原因）并记录
   `unmapped_contract_field` 异常；status 随之判为 `partial`。

映射是**名称相似度**层面的，语义含糊的字段（如 `unconventional_extra_field`）
必须由 Agent 对照 task.md 与数据字典裁决，裁决结果追加到 `change_records`。

## 5. 复核方法（双通道重算）

`verify` 与 `run` 使用**不同代码路径**：

- run 的统计走 `profile_columns` → `clean_rows` → `numeric_stats`（排序 + 求和）；
- verify 直接用 `csv.reader` 逐行读 cleaned CSV，纯 Python 循环累加求 n、mean、
  std（ddof=1），不调用 run 的任何统计函数。

比较容差：`|a-b| <= 1e-9 + 1e-9*max(|a|,|b|)`（rel/abs 1e-9）。cleaned CSV 中浮点
数以 `repr()` 落盘，保证字符串→浮点 round-trip 精确，故重算差异仅来自求和
顺序的浮点舍入，远小于容差。

verify 另外校验：

- 每个 figure_data CSV 的行数与 figures_manifest.json 记录一致；
- result.json 含 case_id、output_contract 全部字段，missing_fields 均有原因；
- result.json `artifacts` 中每个产物文件存在且 sha256 与记录一致；
- provenance 中登记的输入文件 sha256 与当前输入一致（防输入被替换）。

退出码：全部 PASS 为 0，任一 FAIL 为 1。

## 6. 已知局限

- 不做推断统计、显著性检验、建模与因果分析；
- 图形最多两张（直方图 + 散点），matplotlib 缺失时降级为规格 JSON + 数据 CSV；
- 目标列识别依赖命名模式（class|target|label|类别|强度|strength）；
- SQL 按分号切分，含分号的字符串字面量或存储过程不支持；
- group-by 对高基数（>50 水平）目标列自动跳过，仅记录原因；
- verify 复核数值与文件完整性，不能证明对任务语义的理解正确。
