# SQL 静默错手册（sql_playbook）

本手册枚举 SQLite 查询中的高频静默错误（查询能执行、结果看似合理但语义错误），
给出最小反例与检测方法，并给出行数对账方法论、空结果纪律与查询计划阅读要点。

## 一、高频静默错目录

### 1. 漏过滤字段，行数偏多（本技能的头号敌人）

任务要求“有效读数”，表中有 `status` 列，查询只写了日期条件：

```sql
-- 错误：漏掉 status 过滤，把 status='void' 的作废行也计入
SELECT COUNT(*) FROM readings WHERE ts >= '2026-11-01';
-- 正确
SELECT COUNT(*) FROM readings WHERE ts >= '2026-11-01' AND status = 'valid';
```

检测：exec 的 `baseline_reconciliation` 中 `ratio_rows_returned_over_baseline`
显著高于任务语义预期（如“某一小类”的比值接近 1.0）；survey 的去重计数显示
存在状态/类别列而 SQL 未引用之。

### 2. JOIN 扇出重复计数

连接键在被连接表中不唯一，行数被成倍放大：

```sql
-- 若 readings.site_id 对 sites 之外还存在第二张同键表，或连接条件写错，
-- COUNT 会被放大：
SELECT COUNT(*) FROM readings r JOIN sites s ON r.value >= 10;  -- 非键条件：扇出
```

检测：exec 的 `fanout_warning`（JOIN 且结果行数 > 最大单表基线）；survey.md
的“潜在连接键”一节列出跨表同名列，写 JOIN 前先确认该键在两侧的唯一性
（比对 survey 中去重计数与行数）。

### 3. NULL 三值逻辑：`col != 'x'` 会排除 NULL 行

```sql
-- value 为 NULL 的行：NULL != 'void' 结果为 NULL，被 WHERE 丢弃
SELECT COUNT(*) FROM readings WHERE status != 'void';          -- NULL status 行被静默排除
SELECT COUNT(*) FROM readings WHERE status != 'void' OR status IS NULL;  -- 显式保留
```

规则：`NULL` 与任何值的比较结果都是 NULL（非 TRUE）。需要“非某值”的语义时，
先查 survey 的 NULL 行数，决定是否补 `OR col IS NULL`。

### 4. COUNT(col) 与 COUNT(\*) 不等价

```sql
SELECT COUNT(value), COUNT(*) FROM readings;  -- 前者跳过 value 为 NULL 的行
```

规则：`COUNT(col)` 只计非 NULL 行，`COUNT(*)` 计全部行。报告“样本数”时
必须明确口径，并与 survey 的 NULL 计数对照。

### 5. DISTINCT 与 GROUP BY 混用 / 重复去重

```sql
SELECT DISTINCT region, COUNT(*) FROM sites GROUP BY region;  -- 冗余且掩盖逻辑混乱
-- 重复入库检测（本包合成示例即埋此陷阱）：
SELECT COUNT(*) - (SELECT COUNT(*) FROM (SELECT DISTINCT site_id, ts, value
                   FROM readings WHERE status='valid' AND value IS NOT NULL))
FROM readings WHERE status='valid' AND value IS NOT NULL;       -- 非 0 即存在重复批次
```

### 6. 隐式类型转换：'123' 与 123

SQLite 的动态类型会让 TEXT 与 INTEGER 的比较按类型亲和性走：

```sql
SELECT * FROM t WHERE code = 123;    -- code 若存为 TEXT '123'，此行不匹配
SELECT * FROM t WHERE code = '123';  -- 需与存储类型一致
```

检测：survey 的列类型与样例值；对可疑列执行 `SELECT DISTINCT typeof(col)`。

### 7. LIKE 的大小写与通配

SQLite 的 `LIKE` 默认仅对 ASCII 不区分大小写，对非 ASCII 区分；`%`/`_`
是通配符。匹配中文或需要严格区分大小写时，用 `GLOB`（区分大小写）或
`LOWER(col) = LOWER(?)` 并声明口径。

## 二、行数对账方法论

1. **基线**：对 SQL 中命名的每张表取未过滤 `COUNT(*)` 作为基线
   （exec 自动完成，记录于 meta 的 `baseline_reconciliation`）。
2. **比值**：`rows_returned / baseline`。过滤型查询的比值应与任务语义相容
   （“某类别”通常远小于 1；接近 1 说明过滤可能漏字段）；聚合型查询的行数
   应等于分组基数（可与 survey 的去重计数对照）。
3. **扇出公式**：JOIN 结果行数 > max(各参与表基线) 即触发预警；预期内的
   放大（一对多展开）须在 anomalies 中用文字解释，否则视为连接条件错误。
4. **交叉复核**：进入答案的每个关键数字，用语义等价而写法独立的第二条 SQL
   重算（JOIN+GROUP BY 对 IN 子查询；朴素 COUNT 对 DISTINCT 去重计数），
   交 reconcile 仲裁。两条独立路径得到同一数字，才写入 result.json。

## 三、空结果处理纪律

空结果有三种成因，必须在 anomalies 中区分并注明判断依据：

- **条件过严**：阈值写错或单位不符（对照 survey 的 min/max 可发现）——
  修正后重跑并记录变更；
- **语义真空**：条件本身合法但物理上不可能（如本包 q3：value > 1000000）——
  如实报告 0 行，说明语义；
- **数据缺失**：相关列大量 NULL 或关联表为空（survey 的 NULL 计数、行数
  可证）——报告数据缺口，不补造数据。

铁律：空结果只记录、只解释，**绝不静默放宽 WHERE 条件**。

## 四、EXPLAIN QUERY PLAN 阅读要点

- `SCAN t`：全表扫描。小表（挑战赛规模）无碍；大表上的过滤查询出现 SCAN
  说明没有可用索引，留意耗时与超时。
- `SEARCH t USING INDEX ...` / `USING AUTOMATIC ... INDEX`：走了索引；
  `AUTOMATIC` 表示 SQLite 临时建索引，频繁出现说明连接/过滤列缺索引。
- `USE TEMP B-TREE FOR ORDER BY / GROUP BY`：需要额外排序，行数大时耗时。
- `BLOOM FILTER`：新版本 SQLite 对 JOIN 的预过滤优化，属正常。
- 计划先行是 exec 的设计：语句先在计划阶段暴露“表不存在”等错误，再执行。
