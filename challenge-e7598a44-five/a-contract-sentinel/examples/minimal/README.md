# 最小调用示例（合成示例，非正式案例结果）

本目录演示 rq-contract-sentinel 的完整接口。**全部数据为合成**：虚构研究问题、
8 条虚构快照记录（`10.0000/synth.*` 为虚构 DOI）、3 篇虚构署名清单文献。

## 输入（input/）

- `case.json`：含 `case_id`、中文研究问题（2020–2024 钙钛矿晶界钝化效率）、
  8 个 `output_contract` 字段、3 篇 `attributed_papers`（AP-3 故意不在快照中，
  用于演示 missing 的诚实报告）。
- `search_export.json`：8 条合成记录，刻意包含——1 条 `synthetic_duplicate`
  夹具（#3）、1 条 `conflict_opinion` 夹具（#8）、1 条年份出窗（2018）、
  1 条 review 类型、1 条主题无关（电池电解液 ML）。
- `task.md`：合成任务说明。

## 运行

```bash
python3 ../../scripts/probe.py    --case input/case.json --input-dir input --work /tmp/ex/work
python3 ../../scripts/pipeline.py --case input/case.json --input-dir input --work /tmp/ex/work --out /tmp/ex/out
python3 ../../scripts/validate.py --case input/case.json --work /tmp/ex/work --out /tmp/ex/out
```

## 期望输出（expected/，由上述命令真实生成）

- `result.json`：`status=partial`（1 篇清单文献 missing + 1 条冲突意见夹具 +
  1 条弱命中 uncertain，均已写入 uncertainty）；`candidates` 4 条；
  `field_notes` 说明空字段原因。
- `validate-report.json`：`gate=pass`，C1–C8 全 PASS。
- `ledger.jsonl` / `screening_summary.json` / `attribution.json`：逐条台账、
  计数与条款、归属核验。

注意：本示例的输出**不是**平台正式案例的结果，仅用于说明接口与流程。
