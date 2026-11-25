# 最小调用示例（合成示例，非正式案例结果）

本目录演示 snapshot-forensics 的完整接口。**全部数据为合成**：虚构研究问题、
虚构快照记录（`10.0000/synth.*` 为虚构 DOI）、3 篇虚构署名清单文献。

## 输入（input/）

- `case.json`：含 `case_id`、中文研究问题（2019–2024 锂金属负极/固态电解质
  界面稳定性）、10 个 `output_contract` 字段（含 `integrity_report` 与
  `quarantine_register`，取证结论是一等公民）、3 篇 `attributed_papers`
  （AP-1 与快照一致；AP-2 年份故意写成 2023 而快照为 2022，演示 mismatch；
  AP-3 不在快照中，演示 absent）。
- `search_export.json`：7 条合成记录，刻意包含——1 条 `synthetic_duplicate`
  夹具（#3）、1 条 `conflict_opinion` 夹具（#4）、1 条年份出窗（2016）、
  1 条主题无关（交通流预测）、1 条缺标题的结构残缺记录（#7）。
- `extra_export.jsonl`：2 条正常记录 + 1 条故意写坏的 JSONL 行（演示异常行登记）。
- `task.md`：合成任务说明。

## 运行

```bash
python3 ../../scripts/forensics.py    --case input/case.json --input-dir input --work /tmp/bf/work
python3 ../../scripts/gated_screen.py --case input/case.json --work /tmp/bf/work --out /tmp/bf/out
```

## 期望输出（expected/，由上述命令真实生成）

- `result.json`：`status=partial`；`candidates` 3 条；`integrity_report`
  嵌入全部文件 sha256 指纹与法证结论；`quarantine_register` 3 条
  （合成重复/冲突意见/结构残缺，去向明确）；`uncertainty` 5 条
  （AP-2 mismatch、AP-3 absent、冲突意见待人工、JSONL 坏行、弱命中待复核）。
- `forensics_report.json` / `quarantine.jsonl` / `trusted_records.jsonl` /
  `metadata_forensics.json`：取证环节产物（脚本写入 work 目录，此处为同一次
  运行的真实副本）。
- `ledger.jsonl` / `candidates.json`：信任门后 6 条可信记录的逐条台账与纳入集。

注意：本示例的输出**不是**平台正式案例的结果，仅用于说明接口与流程。
