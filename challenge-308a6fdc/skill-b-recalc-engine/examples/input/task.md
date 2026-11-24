# 任务说明（合成示例，非正式案例）

依据 `experiment_data.csv` 中的两组重复测量数据，核验草稿 `deliverable.md`
中的每一个数字：

1. 先用 `scripts/recalc.py` 从原始 CSV 重算全部派生量；
2. 再用 `scripts/verify_draft.py` 对草稿做三态数字核验并装配 `result.json`；
3. UNSUPPORTED / UNSUPPORTED-PVALUE 必须删除、改写或标【待确认】。

本示例草稿故意包含四类数字：一个原文数字、一个正确派生数字（百分比变化）、
一个错误派生数字、一个编造的 p 值，用于展示四种判定。
