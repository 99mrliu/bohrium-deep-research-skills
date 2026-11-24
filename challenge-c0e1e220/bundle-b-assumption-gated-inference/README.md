# bundle-b-assumption-gated-inference

**重心：推断统计决策严谨性**——正态性（D'Agostino K²，n≥8）与方差齐性
（Levene median）门控检验选择，决策链全程结构化留痕（decision_log），并配
备独立重算审计器（decision_audit.py，7 类违例码，exit 1/0 机器可裁决）。

与旧作 bundle1-infer 的实质升级：旧作只把"选了什么检验"写进报告；本 bundle
把**为什么选**（每组 K² p、Levene p、各组 n、reason_codes、被否决候选、每组
取值 sha256）变成可被第三方脚本从原始数据独立重算的审计契约——改一个
chosen_test、改一个 p、翻转一个正态性结论，都会被 exit 1 拦截（见
examples/run_example.sh 的 3 个埋雷自断言）。

## 文件清单

```
SKILL.md                     # agent 面向工作流（中文，SPEC 必备章节）
GITHUB_URL.txt
README.md
scripts/
  statcore_b.py              # 纯 stdlib 统计核心（Lentz 连分式 β、Acklam 逆正态…）
  pipeline_b.py              # run / decide / finalize 一键管线
  decision_audit.py          # 重心：独立重算审计（exit 1 命中违例码）
  crosscheck_scipy.py        # 可选：scipy 交叉校验（无 scipy 优雅跳过）
references/
  decision-tree.md           # 决策树 + decision_log 契约 + 审计口径附录 A
  assumption-checks.md       # n<8 功效、K² vs Shapiro、Levene 变体
  effect-and-ci.md           # 效应量/CI 口径 + bootstrap 确定性协议
  multiplicity.md            # Holm 与家族划分规则
examples/
  make_synthetic.py          # 合成数据生成器（固定种子，标注合成）
  run_example.sh             # 端到端自断言：好例 exit 0，埋雷 exit 1 命中违例码
  minimal-example.md         # 最小调用说明（合成示例）
  example_output/            # 真实跑出的文本产物（result.json / 摘录 / 审计 PASS 日志）
```

## 使用

见 SKILL.md「精确命令工作流」。统计核心零依赖（Python 3.9+ 标准库）；
scipy 仅用于可选交叉校验。

## 维护

- 决策树/阈值/审计口径改动必须同步三处：references/decision-tree.md、
  pipeline_b.gate_and_test、decision_audit.expected_test，否则审计必然报
  TEST_MISMATCH（这是设计特性，不是缺陷）。
- 验证：`bash examples/run_example.sh` 与
  `python3 scripts/crosscheck_scipy.py` 均应 exit 0。
- 版本：v1.0（challenge-c0e1e220，Bundle B）。
