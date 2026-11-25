# 最小调用示例（合成示例，非正式案例结果）

本目录是**合成示例**：`case.example.json` 中的研究问题（已在 `research_question` 内标注 "SYNTHETIC EXAMPLE"）、文献、作者、期刊与 DOI 均为演示虚构；`matrix.example.json` 是手写的演示判定矩阵，其 quote 均为示例摘要中的逐字子串。仅用于说明接口与完整流程，不冒充平台正式案例的结果。

## 示例设计

4 条候选：S1 为明确相关的成人 RCT（三条判据全 met）；S2 人群错误（青少年，c1 unmet）；S3 缺摘要（全部 unknown → pending）；S4 为 S1 的预印本重复导出（带 `fixture_note`，仅作 provenance；因 c3"经同行评议"判据 unmet 而排除）。标注标准含 3 条纳入判据，位于 `annotation_standard.inclusion`。

## 运行（端到端）

```bash
W=$(mktemp -d); mkdir -p $W/input $W/work $W/output
cp examples/minimal/case.example.json $W/input/case.json
# 1. 判据抽取（脚本）
python3 scripts/criteria_engine.py extract --case $W/input/case.json --out $W/work/criteria.json
# 2.（正式运行时由 Agent 一次批量调用产出矩阵；此处直接使用演示矩阵）
cp examples/minimal/matrix.example.json $W/work/matrix.json
# 3. 决定与装配（脚本）
python3 scripts/criteria_engine.py decide --case $W/input/case.json \
  --criteria $W/work/criteria.json --matrix $W/work/matrix.json --out $W/output/result.json
# 4. 交付校验（脚本）
python3 scripts/criteria_engine.py validate --case $W/input/case.json \
  --criteria $W/work/criteria.json --result $W/output/result.json
```

预期第 4 步输出：

```
VALIDATE PASS: case_id=demo-criteria-01 records=4 criteria=3 unknown_cells=3 state=partial
```

## 示意输出（合成示例）

`screened_records`：S1（keep/direct，100，rank1）→ S3（pending/indirect，0，rank2，缺摘要故全部 unknown）→ S2 与 S4 并列 rank3（exclude/none，均 50，`tie_group=["S2","S4"]`；S2 因人群判据 unmet，S4 因"经同行评议"判据 unmet，quote 引摘要中 "has not been peer reviewed"）。因 S3 存在 3 个 unknown 单元格，`status.state=partial` 且 `status.incomplete` 明示数量——这是诚实状态而非失败。

## 退化路径（诚实 partial）

省略第 2 步、`decide` 不带 `--matrix` 重跑第 3 步：全部记录 pending/unknown，`status.state=partial`，`incomplete` 说明未提供判定矩阵——validate 仍 PASS（partial 是合法交付态），预算耗尽时以此保底。
