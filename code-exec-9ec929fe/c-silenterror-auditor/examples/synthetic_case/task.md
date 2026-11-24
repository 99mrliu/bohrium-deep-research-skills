# 合成示例任务（非正式案例）

`readings.csv` 埋有四类静默错误陷阱：`NA` 缺失标记、完全重复行、`-999`
哨兵值；`lab.db` 中表无主键且含 NULL。要求清洗后给出 reading 的
count/mean/std/min/max，并把所有陷阱的处置写入 anomalies。
