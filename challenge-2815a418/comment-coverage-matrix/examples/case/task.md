# 合成示例任务（非正式案例）

给定 materials/manuscript-baseline.md（组织方基线摘要，虚构短稿）与
materials/reviewer-comments.md（意见摘要，3 条意见），完成：

1. 只修订该指定基线，逐条处理实际给出的意见；
2. 交付可编辑修订稿、回复信草案、修改定位、未到位证据清单；
3. 实质性修改必须真实落在基线中；无法补做的意见须给证据状态与替代说明；
4. result.json 含 case_id 与 output_contract 全部字段、诚实 status、sources、uncertainty、修改记录。

本示例仅演示 comment-coverage-matrix 的端到端调用，**不是正式案例结果**。
