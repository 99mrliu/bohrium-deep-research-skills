# 最小调用示例（合成示例，非正式案例结果）

题材：青藏高原草地样带放牧强度调查（24 个月开题）。全部输入为演示接口而构造的
**合成数据**，前期数据与文献占位均非真实。

- `input/case.json`：合成契约，output_contract 含 proposal_draft、alignment_matrix、
  fact_source_map、risk_register、verification_report 五字段。
- `input/task.md`、`input/prior_survey_2023.csv`：合成开题任务与前期摸底数据。
- `curated/alignment_matrix.json`：真实运行中由 Agent 填写；此处预制，且故意含三类
  违例——OBJ2 无任何 VAL、STEP4（土壤呼吸观测）为孤儿步骤、RSK2 缺 trigger_signal。
- `curated/proposal_draft.md`、`curated/fact_source_map.json`：按矩阵展开的草稿与
  证据映射（草稿中标注了被拦截位置）。
- `run_example.sh`：契约播种 → 对齐裁定（预期退出码 1）→ 组装 result → final 收尾
  （gate 未过强制 partial，预期退出码 1）。
- `expected/alignment_report.json`：逐项 pass/fail 裁定报告与覆盖率统计，可见
  `OBJ-COVER`、`STEP-SERVE`、`RSK-FIELDS` 三条规则的 fail 拦截。
- `expected/result.json`：真实跑出的诚实 partial——五字段齐备但 status 为 partial，
  uncertainty 点名对齐门未过的全部 fail 项。

运行：`bash examples/run_example.sh`（依赖仅 python3 标准库）。
