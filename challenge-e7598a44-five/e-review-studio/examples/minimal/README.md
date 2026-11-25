# 最小调用示例（合成示例，非正式案例结果）

本目录演示 e-review-studio 的完整接口。**全部数据为合成**：虚构研究问题、
8 条虚构快照记录（`10.0000/synth.*` 为虚构 DOI）、3 篇虚构署名清单文献。
本示例的输出**不是**平台正式案例的结果，仅用于说明接口与流程。

## 输入（input/）

- `case.json`：`case_id`、中文研究问题（2019–2024 钠离子电池层状氧化物正极
  循环稳定性）、9 个 `output_contract` 字段、3 篇 `attributed_papers`
  （AP-3 故意不在快照中，演示 missing 的诚实报告）。
- `search_export.json`：8 条合成记录，刻意包含——1 条 `synthetic_duplicate`
  夹具（#3）、1 条 `conflict_opinion` 夹具（#8）、1 条年份出窗（2015）、
  1 条 review 类型、1 条弱命中 borderline（#6 日历老化）。
- `task.md`：合成任务说明。

## 运行

```bash
python3 ../../scripts/build_review.py \
    --case input/case.json --input-dir input --work /tmp/ex/work --out /tmp/ex/out
python3 ../../scripts/check_exports.py --case input/case.json --out /tmp/ex/out
```

## 期望输出（expected/，由上述命令真实生成后复制而来）

- `ledger.csv`：8 行台账（UTF-8-SIG），处置分布：纳入 4 / 待复核 1 /
  排除 2 / 重复 1。
- `report.md`：七章节结构化报告，状态 **partial**。
- `review.html`：自包含复核台，状态着色 + 勾选位 + overrides 生成器。
- `flow.svg`：PRISMA 式流程图，计数 8 → 7 → 4（+1 待复核 +2 排除 +1 重复）。
- `manifest.json`：5 件交付物的 sha256 与字节数。
- `result.json`：`status=partial`，uncertainty 如实列出 3 项：冲突意见夹具
  R08 已登记待人工、清单文献 AP-3 在快照中 missing、1 条 borderline 待勾核。
- `export-check.json`：check_exports 核验报告，X1–X6 全 PASS（exit 0）。

## 异常路径演练（不在本目录，命令供复现）

- 零纳入：构造全部出窗/不相关的快照重跑，`flow.svg` 正确渲染 included n=0，
  result.json 写明"筛查后零纳入"，check_exports 仍 PASS（exit 0）。
- 缺 manifest / 篡改 ledger.csv：check_exports 分别 FAIL 于 X1 / X2+X3+X5
  （exit 1）——手工编辑交付物必然被抓。
