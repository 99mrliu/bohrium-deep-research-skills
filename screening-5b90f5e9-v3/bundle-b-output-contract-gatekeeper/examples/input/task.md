# 合成示例任务书（非真实评测案例）

case_id: search09-synthetic-demo

对 `/input/case.json` 中 5 条合成题录执行全量题录筛选：解析检索式、逐条纳入/排除、
处理组织方标注的合成重复导出（R03）与冲突双人意见夹具（R05），交付到 `/app/output/result.json`。

## 输出合同（output_contract）

result.json 必须包含以下字段（与 case.json 中 output_contract.fields 一致）：

- decisions: 逐题录纳入/排除决定及理由
- dedup_report: 合成重复导出的识别与处置
- conflict_resolutions: 冲突双人意见的调解记录
- screening_summary: 筛选统计汇总
- limits: 限制说明；填不了为 null 且须在 uncertainty 中说明

status 取 completed/partial/failed，必须诚实；partial 必须说明限制。
