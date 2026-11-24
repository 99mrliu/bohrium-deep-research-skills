# 跨源一致性核对（CSV ↔ SQLite）

目标：在计算任何统计量之前回答"两个源是不是同一份数据"。本文件是 `source_audit.py` 的方法依据。

## 核对层级（由粗到细）

1. **行数闭合**：`rows_csv == rows_db`。不等 → `row_count_mismatch`，不再做逐值比对（错位比对无意义），写 warning。
2. **列映射**（三级，按优先级）：
   - `exact`：列名完全相等；
   - `fuzzy`：规范化（小写、剔除非字母数字字符）后相等，如 `Petal.Length` ↔ `petal_length`；
   - `positional`：按列序一一对应（无表头 CSV、DB 占位列名 c0..cN 时的唯一可行口径）。
   映射方法必须写入审计结果——positional 映射的"一致"结论强度弱于 exact。
3. **逐值比对**：
   - 行数 ≤5000：**全量**比对；
   - 行数 >5000：**确定性 stride 采样**（每隔 ⌈n/5000⌉ 行），把采样口径写进结果，不用随机抽样（保证可复现）；
   - 两侧都可解析为数值 → 按数值比，容差 `max(1e-9·max(|a|,|b|), 1e-12)`（吸收 REAL 浮点表示差）；
   - 任一侧不可解析 → 按 strip 后字符串比；
   - 缺失 token（"", NA, N/A, NaN, null, -, none）与 SQL NULL 视为等价。

## 结论词汇（verdict）

| verdict | 含义 |
|---|---|
| `consistent` | 行数一致且采样/全量范围内 0 处值不一致 |
| `consistent_with_type_coercion` | 值一致，但 DB 侧存在 numeric-in-text 列（值按数值强转后一致） |
| `row_count_mismatch` | 行数不一致（warning） |
| `value_mismatch(...)` | 存在值不一致单元格，示例已记录（warning） |

## 已知数据集指纹软核对

注册表（形状 = 数据行×列）：

| 形状 | 数据集 | 关键词 |
|---|---|---|
| 1030×9 | UCI Concrete | concrete / 混凝土 |
| 150×5 | Iris (Bezdek) | iris / 鸢尾 |
| 178×14 | UCI Wine | wine / 葡萄 |

规则：形状命中 ∧ 关键词命中 → `consistent`（仅提示）；两者只中其一 → `warning`。
**绝不硬拒**：指纹只是合理性线索，新数据集/裁剪过的数据完全合法。
指纹的另一用途：无表头 CSV 且形状唯一命中时，提供提示性列名（在结果中标注 `fingerprint_hint` 来源并列入待确认裁决）。

## 纪律

- 跨源一致 ≠ 数据真实：它只证明两个文件记录级一致，不证明采集过程无问题。结论措辞必须保留这一边界。
- 不一致时**不擅自以某一源为准**：写 warning + 在 digest 列 `primary_source` 裁决项，由 agent 决定。
