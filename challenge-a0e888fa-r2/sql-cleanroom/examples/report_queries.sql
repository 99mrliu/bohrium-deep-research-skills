-- report_queries.sql —— 报告即聚合查询（示例：water_quality）
-- 每条 SELECT 以 `-- @name: <名称>` 标记；export_report.py 执行并渲染，数字禁止手写。
-- selfcheck 为强制项：必须返回 (metric, value) 两列，供独立重算比对。

-- @name: raw_rows
SELECT COUNT(*) AS n FROM raw;

-- @name: cleaned_rows
SELECT COUNT(*) AS n FROM cleaned;

-- @name: missing_by_class
SELECT missing_class, COUNT(*) AS n
FROM cleaned
WHERE missing_class IS NOT NULL
GROUP BY missing_class
ORDER BY missing_class;

-- @name: changes_by_field
SELECT field, COUNT(*) AS n
FROM change_log
GROUP BY field
ORDER BY field;

-- @name: issues_by_type
SELECT issue_type, COUNT(*) AS n
FROM issues
GROUP BY issue_type
ORDER BY issue_type;

-- @name: qc_violations
SELECT c.line_no, c.sample_id, c.parameter, c.value, c.unit, i.detail
FROM issues i
JOIN cleaned c ON c.line_no = i.line_no
WHERE i.issue_type = 'qc_out_of_bounds'
ORDER BY c.line_no;

-- @name: selfcheck
SELECT 'raw_rows' AS metric, COUNT(*) AS value FROM raw
UNION ALL
SELECT 'cleaned_rows', COUNT(*) FROM cleaned
UNION ALL
SELECT 'issues_rows', COUNT(*) FROM issues
UNION ALL
SELECT 'change_log_rows', COUNT(*) FROM change_log
UNION ALL
SELECT 'duplicates_dropped', COUNT(*) FROM duplicates_dropped;
