# 最小调用示例（合成示例，非正式案例结果）

全部输入均为演示接口而构造的**合成数据**，题材为「固态锂电池界面工程」：

- `input/case.json`：合成契约，`output_contract` 含 5 个字段（proposal_draft、
  fact_source_map、risk_register、schedule、expected_outcomes）。
- `input/task.md`、`input/materials/`：合成任务书与两份合成材料（文献笔记 S1–S5、实验条件）。
- `run_example.sh`：端到端演示过程协议——
  1. `checkpoint.py init`（步骤 0，诚实 partial 骨架）；
  2. 两次模拟 checkpoint：要素起草（故意留空 risk_register）与预算 82% 预警后的强制收尾；
  3. `budget_ledger.py add/report` 演示 >80% 用量的超限预警（退出码 2 + 强制收尾指令）；
  4. `contract_guard.py` 对故意缺 risk_register 字段、缺「风险与备选」要素的 result.json
     终检，展示缺项拦截与 partial 强制（退出码 1）。
- `expected/`：`bash examples/run_example.sh` 真实跑出的产物——
  `result.json`（诚实 partial，uncertainty 点名缺项）、`guard_report.json`（逐项 pass/fail）、
  `checkpoint_log.jsonl` 与 `budget_ledger.jsonl`（全程留痕）。

运行：`bash examples/run_example.sh`（依赖仅 python3 标准库与 bash）。
