# 质量报告（报告即聚合查询）

> 本报告全部由 report_queries.sql 的查询结果渲染；任何数字未手工填写。

## raw_rows

| n |
| --- |
| 9 |

## cleaned_rows

| n |
| --- |
| 8 |

## missing_by_class

| missing_class | n |
| --- | --- |
| below_detection | 1 |
| blank | 1 |
| sentinel | 1 |

## changes_by_field

| field | n |
| --- | --- |
| _row | 1 |
| sample_id | 1 |
| unit | 1 |
| value | 4 |

## issues_by_type

| issue_type | n |
| --- | --- |
| duplicate_removed | 1 |
| qc_out_of_bounds | 1 |

## qc_violations

| line_no | sample_id | parameter | value | unit | detail |
| --- | --- | --- | --- | --- | --- |
| 7 | W006 | arsenic | 250.0 | µg/L | value 250.0 µg/L outside [0.0,100.0] |

## 自检（报告数字 vs 对库表独立重算）

| metric | report_value | recomputed | status |
| --- | --- | --- | --- |
| raw_rows | 9 | 9 | match |
| cleaned_rows | 8 | 8 | match |
| issues_rows | 2 | 2 | match |
| change_log_rows | 7 | 7 | match |
| duplicates_dropped | 1 | 1 | match |

- cleaned.csv sha256：`27e4c544054dd5bcd77555eab20f6cedc4855fce34398440b5f0995edb6cf00d`
- 导出行数：cleaned=8，change_log=7，issues=2
