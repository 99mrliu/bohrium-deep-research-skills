# 合成示例任务（SYNTH-DEMO-001）

**说明：本任务为合成示例，数据为虚构的合金强度试验记录，仅用于演示
direct-analysis-engine 的行为，不构成任何真实科研结论。**

请对 `alloy_strength_syn.csv` 完成科研数据分析：

1. 数据清洗：识别缺失标记（空串、NA、N/A 等），置 null 且保留所在行；
   删除精确重复行并记录条数；不得删除离群值，仅按 1.5×IQR 标记计数；
   数值列中的非数值故障（如 "error"）置 null 并记录。
2. 描述统计：每个数值列给出 n、mean、std（ddof=1）、median、q1/q3
   （type-7 线性插值）、min、max 与离群计数；文本列给出 top-5 频次。
3. 以强度列（strength_mpa）为目标，尝试分组统计。
4. 图形：目标列直方图与前两个数值列散点图，并输出绘图数据 CSV。
5. 产出 /app/output/result.json：包含 case_id 与 case.json 中
   output_contract 列出的全部字段；无法推断的字段保留为 null 并写入
   missing_fields（含原因），status 据实标注 complete 或 partial。

注：契约中的 `unconventional_extra_field` 为刻意设置的不可映射字段，
用于演示引擎的诚实 partial 行为。
