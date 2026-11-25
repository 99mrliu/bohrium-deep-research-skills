# 最小调用示例（合成示例，非正式案例结果）

本目录是**合成示例**：`case.example.json` 中的研究问题、文献与 DOI 均为演示虚构，`judgments.example.json` 是手写的演示判定。仅用于说明接口与完整流程，不冒充平台正式案例的结果。

## 运行（端到端）

```bash
W=$(mktemp -d); mkdir -p $W/input $W/work $W/output
cp examples/minimal/case.example.json $W/input/case.json
# 1. 契约发现
python3 scripts/contract_engine.py inspect --case $W/input/case.json --out $W/work/plan.json
# 2.（正式运行时由 Agent 批量判定；此处直接使用演示判定）
cp examples/minimal/judgments.example.json $W/work/judgments.json
# 3. 装配
python3 scripts/contract_engine.py assemble --case $W/input/case.json \
  --plan $W/work/plan.json --judgments $W/work/judgments.json --out $W/output/result.json
# 4. 交付校验
python3 scripts/contract_engine.py validate --case $W/input/case.json --result $W/output/result.json
```

预期输出：`VALIDATE PASS: case_id=demo-contract-01 records=4 contract_fields=7 state=complete`。

## 示意输出（合成示例）

`result.json` 中 `screened_records`：S1(keep,92,rank1) → S3(pending,45,rank2) → S4(exclude,90,rank3，理由引用输入 fixture_note 标注其为 S1 的预印本重复导出，仅作 provenance) → S2(exclude,12,rank4)；`omission_note` 由脚本生成有限快照与缺失元数据说明（S3/S4 缺 DOI）；`status.state=complete`。

## 退化路径（诚实 partial）

省略 judgments 重跑第 3 步：全部记录 pending，`status.state=partial`，`incomplete` 列出未判定记录——validate 仍 PASS（partial 是合法交付态）。
