# 合成示例（SYNTHETIC DEMO）

> **本目录全部内容为合成示例**：案例、论文摘录、审查发现均为虚构，仅用于
> 演示 contract-forge-audit 的工作流与脚本行为，不构成任何真实审查结论。

## 文件说明

| 文件 | 说明 |
| --- | --- |
| `synthetic_case.json` | 虚构案例 `SYNTH-DEMO-001`，含 5 字段的 `output_contract`（含一个 findings 数组字段，声明 `item_required_keys`）。 |
| `findings.jsonl` | 4 条虚构发现：critical×1、major×2、minor×1，其中 F-004 为 `待复核`。 |
| `result_completed.json` | 手工填好的合格 result.json（status=complete），应通过校验。 |
| `broken_result.json` | **故意损坏**的 result.json：case_id 不符、findings 项缺键/非对象、残留 PENDING 哨兵且 status=complete、word_count 类型错误，应被校验器检出（6 项违例）。 |
| `run_example.sh` | 端到端演示：scaffold → render → validate（合格 + 损坏双路径），并与 `expected_output/` 做信息性 diff。 |
| `expected_output/` | 上述流程的**实际运行输出**：`contract_schema.json`、`result.json`（骨架）、`audit_sheet.md`、`audit_sheet.html`、`audit_findings.json`、`validation_report.json`（合格件）、`broken_validation_report.json` 与 `broken_validate_stderr.txt`（损坏件）。 |

## 运行

```bash
bash examples/run_example.sh
```

预期：全部 5 步通过，退出码 0；损坏件校验 exit=1 且 stderr 含 6 条
`VIOLATION`。运行产物写入 `examples/run_output/`（可随时删除）。

注意：`validation_report.json` / `broken_validate_stderr.txt` 内含生成机器的
绝对路径，跨机器 diff 时这两个文件的路径行会不同，属正常现象。
