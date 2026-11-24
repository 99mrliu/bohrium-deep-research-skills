# dual-pass-gain-meter

科研选题评估技能的**增益自证**方向：用受控对照 + 机器差分证明"加载技能确有增益"。

- 核心脚本（仅标准库）：
  - `scripts/overclaim_lint.py`：拦截无边界新颖性/空白断言（±60 字符窗口查边界限定词）；
  - `scripts/gain_meter.py`：基线稿 vs 严谨稿的五维指标差分（填充率、锚点、越界断言、
    不确定性、冲突登记），任一判定 ✗ 即不许宣称增益。
- 运行契约：`/input` → `/app/work`（pass0/pass1/gain 报告）→ `/app/output`
  （result.json 含 case_id 与全部 output_contract 字段，诚实 partial；增益证据随附）。
- 公平性规则：`references/baseline_protocol.md`；指标口径：`references/metrics_format.md`。
- 最小示例（合成）：`examples/`，`bash examples/run_example.sh` 一键复跑。

维护：作者随 Playground challenge-041f89c5 提交；Python ≥3.8，无第三方依赖。
