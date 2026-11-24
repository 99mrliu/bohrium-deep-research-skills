-- steps.sql —— 清洗即查询（示例：water_quality）
-- 全部变换表达为 SQLite 关系操作，由 run_steps.py 在单个事务内按序执行。
-- 约定：raw 表由 load_raw.py 创建（全 TEXT）；规则表 rule_* 由 run_steps.py 创建。
-- 每个中间结果落表（step1_*/step2_*/dedup_keep/duplicates_dropped），保证谱系可复核。

-- S0 登记表：逐格变更与问题
CREATE TABLE change_log (
  line_no INTEGER,
  field TEXT,
  old_value TEXT,
  new_value TEXT,
  rule_id INTEGER
);

CREATE TABLE issues (
  line_no INTEGER,
  field TEXT,
  issue_type TEXT,
  detail TEXT,
  rule_id INTEGER
);

-- S1 缺失 token 分类 + 键/字段名规范化（规则表 LEFT JOIN，NULL 化在 S2 完成）
CREATE TABLE step1_missing AS
SELECT r.line_no,
       upper(trim(r.sample_id)) AS sample_id_norm,
       r.sample_id              AS sample_id_orig,
       trim(r.station)          AS station,
       lower(trim(r.parameter)) AS parameter,
       r.value                  AS value_orig,
       trim(r.value)            AS value_trim,
       mt.class                 AS missing_class,
       mt.rule_id               AS missing_rule_id,
       trim(r.unit)             AS unit_orig,
       trim(r.sample_date)      AS sample_date
FROM raw r
LEFT JOIN rule_missing_tokens mt
  ON trim(r.value) = mt.token;

-- S2 单位换算（JOIN rule_unit_map；缺失值不参与换算；非数值如实置 NULL 并记 issues）
CREATE TABLE step2_units AS
SELECT s.*,
       COALESCE(um.to_unit, s.unit_orig) AS unit_norm,
       CASE
         WHEN s.missing_class IS NOT NULL THEN NULL
         WHEN s.value_trim GLOB '*[^0-9eE+.-]*' THEN NULL   -- 非数值：不猜测
         WHEN um.factor IS NOT NULL THEN CAST(s.value_trim AS REAL) * um.factor
         ELSE CAST(s.value_trim AS REAL)
       END AS value_num,
       um.rule_id AS unit_rule_id
FROM step1_missing s
LEFT JOIN rule_unit_map um
  ON s.parameter = lower(um.field)
 AND s.unit_orig = um.from_unit;

-- S3 归一化主键去重：保留 line_no 最小者，keep 依据落表
CREATE TABLE dedup_keep AS
SELECT sample_id_norm,
       MIN(line_no) AS keep_line,
       'normalized sample_id 分组保留最小 line_no（清洗工单 W-02）' AS basis
FROM step2_units
GROUP BY sample_id_norm;

CREATE TABLE duplicates_dropped AS
SELECT s.line_no, s.sample_id_norm, k.keep_line
FROM step2_units s
JOIN dedup_keep k ON s.sample_id_norm = k.sample_id_norm
WHERE s.line_no <> k.keep_line;

CREATE TABLE cleaned AS
SELECT s.line_no,
       s.sample_id_norm AS sample_id,
       s.station,
       s.parameter,
       s.value_num      AS value,
       s.unit_norm      AS unit,
       s.missing_class,
       s.sample_date
FROM step2_units s
JOIN dedup_keep k
  ON s.sample_id_norm = k.sample_id_norm
 AND s.line_no = k.keep_line
ORDER BY s.line_no;

-- S4 change_log：缺失 token -> NULL（保留分类列 missing_class）
INSERT INTO change_log
SELECT s.line_no, 'value', s.value_orig, NULL, s.missing_rule_id
FROM step2_units s
WHERE s.missing_class IS NOT NULL;

-- S5 change_log：单位换算（值与单位各记一格）
INSERT INTO change_log
SELECT s.line_no, 'value', s.value_trim, CAST(s.value_num AS TEXT), s.unit_rule_id
FROM step2_units s
WHERE s.unit_rule_id IS NOT NULL AND s.missing_class IS NULL;

INSERT INTO change_log
SELECT s.line_no, 'unit', s.unit_orig, s.unit_norm, s.unit_rule_id
FROM step2_units s
WHERE s.unit_rule_id IS NOT NULL AND s.missing_class IS NULL;

-- S6 change_log：主键规范化（大小写/空格）
INSERT INTO change_log
SELECT s.line_no, 'sample_id', s.sample_id_orig, s.sample_id_norm, kf.rule_id
FROM step2_units s, rule_key_fields kf
WHERE kf.field = 'sample_id' AND kf.role = 'natural_key'
  AND s.sample_id_orig <> s.sample_id_norm;

-- S7 change_log：重复行剔除（行级变更，field 记为 _row）
INSERT INTO change_log
SELECT d.line_no, '_row',
       'duplicate of line ' || d.keep_line, NULL, kf.rule_id
FROM duplicates_dropped d, rule_key_fields kf
WHERE kf.field = 'sample_id' AND kf.role = 'natural_key';

-- S8 issues：QC 越界标记（仅 flag 动作；值缺失者不参与）
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

-- S9 issues：非数值源值（未猜测、置 NULL，如实登记）
INSERT INTO issues
SELECT s.line_no, 'value', 'non_numeric_source',
       'source value ' || quote(s.value_orig) || ' is not numeric; stored as NULL',
       NULL
FROM step2_units s
WHERE s.missing_class IS NULL
  AND s.value_trim GLOB '*[^0-9eE+.-]*';

-- S10 issues：重复剔除登记
INSERT INTO issues
SELECT d.line_no, 'sample_id', 'duplicate_removed',
       'normalized key ' || d.sample_id_norm || ' duplicated; kept line ' || d.keep_line,
       kf.rule_id
FROM duplicates_dropped d, rule_key_fields kf
WHERE kf.field = 'sample_id' AND kf.role = 'natural_key';
