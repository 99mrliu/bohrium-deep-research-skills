# 覆盖率报告（判定仪器标定版）

- case_id: `synthetic-demo-calibrator-001`
- 仪器：规则规范 2026.11，L2 阈值 0.80，标定状态：已标定
- 分母 10 / 命中 6 / 漏检 4，覆盖率 0.6000，Wilson95 [0.3127, 0.8318]
- L3 人工裁决队列：1 条（保守计入 miss）

## 标定摘要

- 标定片段 8 对；默认阈值下 precision=1.0 recall=1.0
- keep default 0.80: no threshold strictly dominates (or fragment < 30 pairs)

## 逐条裁决

| ref_id | status | level | score |
|---|---|---|---|
| R001 | hit | L1_doi | 1.0 |
| R002 | hit | L1_doi | 1.0 |
| R003 | hit | L1_doi | 1.0 |
| R004 | hit | L1_doi | 1.0 |
| R005 | hit | L1_doi | 1.0 |
| R006 | hit | L2_title_year | 1.0 |
| R007 | miss | L2_gray_zone | 0.7143 |
| R008 | miss | L2_below | 0.1 |
| R009 | miss | L2_below | 0.0 |
| R010 | miss | L2_below | 0.1111 |
