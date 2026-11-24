# 清洗闭合律与确定性账本

## 闭合律（closure law）

```
rows_raw == rows_kept + rows_dropped
```

任何一行原始数据必须落在且仅落在两个归宿之一：保留（kept）或剔除（dropped）。
不存在"悄悄消失"的行。该等式用台账自报数字先算一遍，再用重放数字独立验证。

## 三类规则语义（词汇表）

| 语义 | 含义 | 影响闭合律 |
|---|---|---|
| `drop` | 行从清洗产物中移除 | 计入 rows_dropped |
| `per-variable exclude` | 行保留；该变量分析时按有效 n 排除缺失 | 不影响行数 |
| `flag` | 行与值都保留，仅打标 | 不影响行数 |

默认规则集（case.json constraints 可覆盖）：

- **R1 `dedupe_exact_keep_first`**（drop）：整行 strip 后完全相同的行只保留第一行。
  理由：完全重复不携带新信息，保留会虚增 n、低估方差。
- **R2 `missing_report_and_exclude`**（per-variable exclude）：缺失 token
  `("", NA, N/A, NaN, null, -, none)`（大小写不敏感）→ 报告每列缺失数，
  统计时按各变量有效 n；**不零填、不插补、不整行删除**。
- **R3 `outlier_iqr_flag_only`**（flag）：数值列按 1.5×IQR 栅栏标记；
  **绝不静默删除异常值**。只有 agent 裁决（`outlier_action=drop`，必须给理由）才生成 R4 drop 规则。

## 账本字段（cleaning_ledger.json）

`source_file` / `source_sha256`（锚定原始文件）、`rules[]`（每条规则含影响行号集合）、
`rows_raw` / `rows_kept` / `rows_dropped` / `kept_raw_rows`、
`cleaned_sha256`（整文件）+ `row_hashes[]`（逐行内容哈希，单元格以 `\x1f` 连接取 sha256）。

## 机器核验（ledger_gate.py，不信台账）

1. **LEDGER_CLOSURE_MISMATCH**：台账自报数字不满足闭合律。
2. **RULE_REPLAY_MISMATCH**：重读原始文件、重放 R1（+R4）规则后，kept/dropped 行号集合
   或原始文件 sha256 与台账不一致——说明台账被改、原始文件被替换、或清洗非确定性。
3. **CLEANED_HASH_MISMATCH**：重算 cleaned_table.csv 整文件哈希或逐行哈希不符——产物被篡改。

全部通过 exit 0；任一违例 exit 1 并打印违例码。交付前必须 PASS。

## 确定性要求

同一输入必须产生同一账本：dedupe 用首次出现序、栅栏用 R type-7 分位数、bootstrap 用
固定 seed（20240501）的独立 Random 实例。禁止 wall-clock/随机源进入清洗路径。
