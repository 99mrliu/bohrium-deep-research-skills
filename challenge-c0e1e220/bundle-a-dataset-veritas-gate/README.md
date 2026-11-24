# dataset-veritas-gate（Bundle A：上游数据真实性与跨源一致性）

Bohrium Playground challenge-c0e1e220（统计分析与结果解读）五方向 Skill bundle 之一。
在计算任何统计量之前先证明三件事：**这份数据是什么**（文件清点 + sha256 + 已知指纹软核对）、
**CSV 与 SQLite 是否同一份数据**（行数闭合 / 列映射 / 逐值比对）、
**每个字段的类型与单位口径**（CSV 嗅探 + SQLite affinity 审计 + numeric-in-text 陷阱识别），
并给出确定性清洗账本与可被机器重放核验的闭合律。随后一键完成假设门控的完整统计推断，
独立交齐 output_contract 全部 9 个字段。

## 文件清单

```
SKILL.md                  # agent 面向的中文工作流（入口文档）
GITHUB_URL.txt            # GitHub 树 URL + SKILL.md
README.md                 # 本文件
scripts/
  statcore_a.py           # stdlib 统计核心（分布函数自写；--selftest 可与 scipy 交叉校验）
  pipeline_a.py           # 一键 baseline：run / decide / finalize
  source_audit.py         # 重心1：来源真实性与跨源一致性审计 → source_audit.json
  ledger_gate.py          # 重心2：清洗账本机器核验门（3 个违例码，exit 0/1）
references/
  cross-source-consistency.md   # 跨源核对层级、结论词汇、指纹软核对纪律
  cleaning-closure-law.md       # 闭合律、规则语义词汇表、确定性要求
  sqlite-type-affinity.md       # affinity 五类映射、numeric-in-text 审计
  unit-and-encoding.md          # 单位来源优先级、编码/分隔符/表头嗅探
examples/
  make_synthetic.py       # 合成数据生成器（plants.csv + plants.db 现场生成）
  run_example.sh          # 端到端自测：好例 exit 0 + 埋雷例 exit 1 命中违例码（11 项断言）
  minimal-example.md      # 合成示例说明（输入/命令/示意输出）
  example_output/         # 真实跑出的文本产物（result.json/report.md/source_audit.json/digest/日志）
```

## 运行环境

Python ≥3.9，仅标准库；scipy 仅用于 `statcore_a.py --selftest` 交叉校验，缺失时自动跳过。
无二进制入库：示例 SQLite 由 `make_synthetic.py` 现场生成。

## 维护信息

- 违例码：`LEDGER_CLOSURE_MISMATCH` / `CLEANED_HASH_MISMATCH` / `RULE_REPLAY_MISMATCH`。
- 清洗默认口径：dedupe_keep_first（drop）+ 缺失 report_and_exclude（不插补）+ 异常 1.5×IQR flag-only。
- bootstrap：B=2000，seed=20240501（百分位 CI，完全可复现）。
- 改动脚本后必须重跑：`python3 scripts/statcore_a.py --selftest` 与 `bash examples/run_example.sh`。
