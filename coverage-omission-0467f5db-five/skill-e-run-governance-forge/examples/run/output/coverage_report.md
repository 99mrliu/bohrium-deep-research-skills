# 覆盖率与遗漏分析报告（证据绑定版）

- case_id: `synthetic-demo-governance-001`
- 分母 7 [B1] / 命中 5 [B2] / 漏检 2 [B3]，覆盖率 0.7143 [B4]
- 复核抽检：抽样 3 条 [B6]，一致率 1.0 [B5]；分歧 0 条（全部转人工并保留主管线状态）
- 每个 [Bn] 绑定号可在 binding_map.json 中查到账本路径；coverage_chart.svg 为同数据渲染图

## 逐条命中状态

| ref_id | status | level |
|---|---|---|
| R001 | hit | L1 |
| R002 | hit | L1 |
| R003 | miss | - |
| R004 | hit | L1 |
| R005 | hit | L1 |
| R006 | hit | L1 |
| R007 | miss | - |
