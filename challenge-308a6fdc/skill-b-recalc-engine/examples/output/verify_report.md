# 数字核验报告（verify_report）

草稿：`deliverable.md`；抽取数字 4 个；相对容差 0.5000%。

| 数字 | 判定 | 依据 / 提示 |
|---|---|---|
| 4.3 | **RAW-SUPPORTED** | experiment_data.csv 第5行原文：control,2,4.3 |
| 12.2% | **DERIVED-SUPPORTED** | 重算值 12.1951（D0017，公式：pct_change = (mean(B) - mean(A)) / mean(A) * 100%；输入：{"column": "response", "group_column": "group", "baseline_group": "control", "baseline_n": 5, "target_group": "treatment", "target_n": 5}） |
| 4.79 | **UNSUPPORTED** | 材料原文与重算派生量均不匹配（已按上下文限定 kind=['mean']）；最接近的重算值为 4.6（mean，公式：mean = sum(x) / n；输入：{"column": "response", "group_column": "group", "group": "treatment", "rows": 5}） |
| 0.032 | **UNSUPPORTED-PVALUE** | 材料中查不到该 p 值字符串；本环境不计算 p 值；材料未给出的 p 值必须删除或标【待确认】 |

UNSUPPORTED / UNSUPPORTED-PVALUE 必须删除、改写为账上数字，或标注【待确认】后方可交付。
