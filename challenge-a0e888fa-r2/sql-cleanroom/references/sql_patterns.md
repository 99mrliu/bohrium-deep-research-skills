# SQL 模式库（清洗即查询）—— SQLite 方言

下列模式组成 `steps.sql`：由 `run_steps.py` 在**单事务**内按序逐条执行，每条语句
的序号与受影响行数记入 `query_log.json`。约定输入：`raw(line_no INTEGER, 其余列
全 TEXT)`；规则表 `rule_missing_tokens / rule_unit_map / rule_qc_bounds /
rule_key_fields`（含 `rule_id`）。完整可运行组合见 `examples/steps.sql`。

## 0. 登记表（每案必备）

```sql
CREATE TABLE change_log (
  line_no INTEGER, field TEXT, old_value TEXT, new_value TEXT, rule_id INTEGER
);
CREATE TABLE issues (
  line_no INTEGER, field TEXT, issue_type TEXT, detail TEXT, rule_id INTEGER
);
```

## 1. 缺失 token → NULL + 分类列保留

```sql
CREATE TABLE step1_missing AS
SELECT r.line_no,
       upper(trim(r.sample_id)) AS sample_id_norm,   -- 键规范化：lower 或 upper + trim
       r.sample_id              AS sample_id_orig,   -- 原值保留，供 change_log 比对
       lower(trim(r.parameter)) AS parameter,
       r.value                  AS value_orig,
       trim(r.value)            AS value_trim,
       mt.class                 AS missing_class,    -- 分类信息不丢
       mt.rule_id               AS missing_rule_id,
       trim(r.unit)             AS unit_orig
FROM raw r
LEFT JOIN rule_missing_tokens mt ON trim(r.value) = mt.token;
```

要点：LEFT JOIN 保证无匹配行不丢；`value` 的 NULL 化推迟到单位换算一步统一完成，
以便 change_log 仍能引用 `value_orig`。空白单元格即 token 为空串的规则行。

## 2. 单位换算 = JOIN unit_map

```sql
CREATE TABLE step2_units AS
SELECT s.*,
       COALESCE(um.to_unit, s.unit_orig) AS unit_norm,
       CASE
         WHEN s.missing_class IS NOT NULL THEN NULL              -- 缺失：不换算
         WHEN s.value_trim GLOB '*[^0-9eE+.-]*' THEN NULL        -- 非数值：不猜测
         WHEN um.factor IS NOT NULL THEN CAST(s.value_trim AS REAL) * um.factor
         ELSE CAST(s.value_trim AS REAL)
       END AS value_num,
       um.rule_id AS unit_rule_id
FROM step1_missing s
LEFT JOIN rule_unit_map um
  ON s.parameter = lower(um.field)
 AND s.unit_orig = um.from_unit;
```

要点：换算只发生在显式登记的 (field, from_unit) 上；`CAST(... AS REAL)` 之前用
GLOB 判定数值性，非数值源值置 NULL 并在第 6 节登记 `non_numeric_source`——
SQLite 的 CAST 对非数值会静默给 0.0，**必须防**。

## 3. 归一化主键去重（GROUP BY + keep 依据落表）

```sql
CREATE TABLE dedup_keep AS
SELECT sample_id_norm,
       MIN(line_no) AS keep_line,
       'normalized sample_id 分组保留最小 line_no（工单 W-02）' AS basis
FROM step2_units
GROUP BY sample_id_norm;

CREATE TABLE duplicates_dropped AS
SELECT s.line_no, s.sample_id_norm, k.keep_line
FROM step2_units s
JOIN dedup_keep k ON s.sample_id_norm = k.sample_id_norm
WHERE s.line_no <> k.keep_line;            -- 被剔除行全量落表，禁止静默丢弃

CREATE TABLE cleaned AS
SELECT s.line_no, s.sample_id_norm AS sample_id, s.station, s.parameter,
       s.value_num AS value, s.unit_norm AS unit, s.missing_class, s.sample_date
FROM step2_units s
JOIN dedup_keep k ON s.sample_id_norm = k.sample_id_norm AND s.line_no = k.keep_line
ORDER BY s.line_no;
```

keep 依据（最小 line_no / 工单指定列优先等）必须来自工单并写进 `basis` 列。

## 4. QC 约束 → issues 表（只标记，不改不删）

```sql
INSERT INTO issues
SELECT c.line_no, 'value', 'qc_out_of_bounds',
       'value ' || CAST(c.value AS TEXT) || ' ' || c.unit ||
       ' outside [' || qb.lo || ',' || qb.hi || ']',
       qb.rule_id
FROM cleaned c
JOIN rule_qc_bounds qb ON lower(qb.field) = c.parameter
WHERE c.value IS NOT NULL
  AND (c.value < qb.lo OR c.value > qb.hi)
  AND qb.action = 'flag';
```

## 5. change_log 侧写（INSERT…SELECT，代替触发器）

SQLite 触发器在逐条执行模式下需 executescript 语义，且隐式触发不利于审计；本技能
一律用**显式 INSERT…SELECT 侧写**，每类变换一条语句，行数即变更格数：

```sql
-- 缺失 token → NULL
INSERT INTO change_log
SELECT s.line_no, 'value', s.value_orig, NULL, s.missing_rule_id
FROM step2_units s WHERE s.missing_class IS NOT NULL;

-- 单位换算：值与单位各记一格
INSERT INTO change_log
SELECT s.line_no, 'value', s.value_trim, CAST(s.value_num AS TEXT), s.unit_rule_id
FROM step2_units s WHERE s.unit_rule_id IS NOT NULL AND s.missing_class IS NULL;
INSERT INTO change_log
SELECT s.line_no, 'unit', s.unit_orig, s.unit_norm, s.unit_rule_id
FROM step2_units s WHERE s.unit_rule_id IS NOT NULL AND s.missing_class IS NULL;

-- 主键规范化（原值 ≠ 规范化值才记）
INSERT INTO change_log
SELECT s.line_no, 'sample_id', s.sample_id_orig, s.sample_id_norm, kf.rule_id
FROM step2_units s, rule_key_fields kf
WHERE kf.field = 'sample_id' AND kf.role = 'natural_key'
  AND s.sample_id_orig <> s.sample_id_norm;

-- 行级剔除：field 记 _row
INSERT INTO change_log
SELECT d.line_no, '_row', 'duplicate of line ' || d.keep_line, NULL, kf.rule_id
FROM duplicates_dropped d, rule_key_fields kf
WHERE kf.field = 'sample_id' AND kf.role = 'natural_key';
```

## 6. 非数值源值登记（诚实原则）

```sql
INSERT INTO issues
SELECT s.line_no, 'value', 'non_numeric_source',
       'source value ' || quote(s.value_orig) || ' is not numeric; stored as NULL',
       NULL
FROM step2_units s
WHERE s.missing_class IS NULL
  AND s.value_trim GLOB '*[^0-9eE+.-]*';
```

## SQLite 方言注意事项

- `trim()` 只去空格，不去制表符；必要时 `trim(x, char(9))`。
- 字符串比较默认**区分大小写**（`=` 不走 NOCASE）；统一用 `upper()/lower()` 显式
  规范化后再比较，避免依赖排序规则。
- 无布尔类型，用 0/1；无日期类型，日期保持 TEXT（ISO 格式可直接比较）。
- `||` 任一端为 NULL 则结果为 NULL——拼接 detail 前先 `COALESCE`。
- `CAST('abc' AS REAL)` 静默得 0.0，务必先 GLOB 判定（见第 2 节）。
- GLOB 大小写敏感、LIKE 对 ASCII 不敏感；字符类写法 `GLOB '*[^0-9eE+.-]*'`。
- 语句以分号结尾；`run_steps.py` 用 `sqlite3.complete_statement` 切分，**不要在
  字符串字面量里放孤立分号**。
- `CREATE TABLE ... AS SELECT` 不保留约束，只有动态类型；cleaned 的列序即 SELECT
  列序，导出 cleaned.csv 时按 `ORDER BY line_no` 固定行序，保证字节级可重放。
- 每个中间结果落表（step1_*/step2_*/dedup_keep/duplicates_dropped），谱系可复核；
  不要为省步骤把全部逻辑塞进一条巨型 SELECT。
