# 合成示例任务（非正式案例）

`mix_data.csv` 为合成的水泥混合料记录（列含缺失、完全重复行与不可解析值），
`lab.db` 为合成的 SQLite 批次登记库。要求：

1. 清洗：删除完全重复行；`strength` 与 `cement` 中不可解析的值置为缺失；
   缺失不参与统计。
2. 给出 `strength` 的 count/mean/std/min/max；按 `batch` 分组的 mean/std/count。
3. 比较 batch A 与 B 的 strength（Welch t 检验，注明前提检查情况）。
4. 计算 cement 与 strength 的 Pearson 相关。
5. 查询 lab.db 中批次登记行数与每个批次的登记样品数。
6. 绘制 strength 直方图（轴标签带单位）。
7. 所有缺失、重复、空查询风险写入 anomalies；交付 result.json。
