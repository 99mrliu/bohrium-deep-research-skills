# examples/ —— 合成示例（synthetic），非正式案例结果

本目录仅用于验证 tolerance-court 工具链，所有数值均为人工编造，**不是**任何真实论文、
真实案例或真实运行的结果，不得作为复现证据引用。

- `input/targets.json`：5 个合成指标，覆盖 4 类容差来源——
  - `accuracy`：case_given（案例给定 ±0.01，逐字优先）
  - `latency_ms`：half_ulp 小数（"72.1" → ±0.05）
  - `throughput`：科学计数（"1.2e3" → ±50）
  - `rouge_l`：stochastic 指标（"0.412" → ±0.0005）
  - `ablation_score`：论文未报告（paper_value=null → not_comparable）
- `input/observations.json`：两个合成候选方法，覆盖六种判定——
  - method_a：accuracy / latency_ms / throughput → within_tolerance；
    rouge_l → stochastic_fluctuation（median=0.413 超差 ±0.0005，但 0.4124 等值落在容差内）；
    ablation_score → not_comparable
  - method_b：accuracy / latency_ms → systematic_deviation（聚集但整体偏离）；
    throughput（values 空）→ missing；rouge_l（n=1 的 stochastic）→ insufficient_runs；
    ablation_score → not_comparable
- `run_example.sh [输出目录]`：preregister → touch 合成日志 → adjudicate → 打印 comparison.md。
  因故意包含 systematic_deviation / missing，adjudicate 预期退出码 1。
- `expected/`：预期输出副本。`created_at`、`targets_sha256`（仅当输入逐字一致时吻合）
  与 mtime 相关字段以实际运行为准。
