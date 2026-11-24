# 合成示例任务（非正式案例）

输入 `measurements.csv` 为某合成实验的测量记录，列名与数据字典不完全一致，
含缺失标记与完全重复行。要求：

1. 依据 `data_dictionary.json` 对齐字段语义，清洗：删除完全重复行；缺失值不
   参与统计，不做插补。
2. 对数值列 `value` 给出 count / mean / sample std / min / max。
3. 给出行数对账：原始行数 → 去重后行数 → 含缺失行数 → 用于统计的行数。
4. 本合成案例不要求绘图，`figures` 字段填空数组即可。
5. 所有异常（未映射列、缺失、重复）写入 anomalies。

交付：`result.json`，含 case_id 与 output_contract 全部字段。
