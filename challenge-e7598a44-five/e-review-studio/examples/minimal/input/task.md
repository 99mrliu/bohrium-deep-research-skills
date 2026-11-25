# 合成示例任务（非正式案例）

围绕 case.json 中的研究问题，对 /input 内快照做轻量筛查，并交付一整套
**人工复核交付物**：ledger.csv（UTF-8-SIG 台账）、report.md（结构化报告）、
review.html（自包含复核台）、flow.svg（PRISMA 式计数流程）、manifest.json
（哈希清单），以及按 output_contract 装配的 result.json；最后用
check_exports.py 独立回读交叉核验。本目录全部内容为合成示例数据，
仅用于演示接口与流程。
