# 最小调用示例（合成示例，非正式案例结果）

本目录演示 d-query-foundry 的完整接口。**全部数据为合成**：虚构研究问题、
9 条虚构快照记录（`10.0000/synth.*` 为虚构 DOI）、3 篇虚构署名清单文献。

## 输入（input/）

- `case.json`：中文研究问题（2021–2024 钠离子电池硬碳负极首周库伦效率 ICE）、
  9 个 `output_contract` 字段、3 篇 `attributed_papers`（K3 为 2019 年文献，
  故意设计成年份出窗 + 术语缺口，用于演示 missing 的诊断）。
- `search_snapshot.json`：9 条合成记录，刻意包含——1 篇中文标题记录（演示
  CJK 命中）、1 条 review 类型、1 条主题无关、1 条 `synthetic_duplicate`
  夹具、1 条 `conflict_opinion` 夹具、1 篇 2019 年出窗文献（K3）。
- `task.md`：合成任务说明。

## 运行

```bash
python3 ../../scripts/foundry.py --case input/case.json --input-dir input \
    --work /tmp/dqf/work --out /tmp/dqf/out
python3 ../../scripts/known_item_audit.py --case input/case.json --input-dir input \
    --work /tmp/dqf/work --out /tmp/dqf/out --finalize
```

## 期望输出（expected/，由上述命令真实生成）

- `result.json`：`status=partial`；`candidates` 6 条；known-item 召回 2/3，
  K3 missing 且诊断出 `year_gap`（2019 出窗）与 `term_gap`
  （pore/engineered 等未覆盖）；冲突意见夹具 R009 登记入 uncertainty。
- `query-report.json`：逐查询画像（命中数、known-item 命中、噪声估计）。
- `known-item-audit.json`：每篇清单文献的命中查询、排名与诊断。
- `candidates.json` / `query-execution.json` / `screening-ledger.jsonl`。

注意：本示例的输出**不是**平台正式案例的结果，仅用于说明接口与流程。
