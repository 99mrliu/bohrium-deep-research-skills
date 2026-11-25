# 最小调用示例（合成示例，非正式案例结果）

本目录是**合成示例（SYNTHETIC EXAMPLE）**：`case.example.json` 中的研究问题、文献、DOI 与期刊名均为演示虚构，`weights.example.json` 是带注释的演示权重。仅用于说明接口与完整流程，不冒充平台正式案例的结果。

示例的 5 条记录是刻意构造的：D1 明显居首（基准 rank 1），D5 明显垫底；中间三条 D2/D3/D4 分数接近，其中 **D3 与 D4 特征画像近乎相同**（标题重叠相同、摘要重叠相差 1 个词元、相邻年份、同档 venue、均无 DOI），用来演示近平分对在扰动下的行为。

## 运行（端到端）

```bash
W=$(mktemp -d)
cp examples/minimal/case.example.json $W/case.json
# 1. 特征化
python3 scripts/stability_engine.py featurize --case $W/case.json --out $W/features.json
# 2. 评分 + 50 次扰动运行（正式运行时可选 --judgments J.json，一次批量模型调用的产物）
python3 scripts/stability_engine.py score --case $W/case.json --features $W/features.json \
  --weights examples/minimal/weights.example.json --runs 50 --out $W/stability.json
# 3. 装配
python3 scripts/stability_engine.py assemble --case $W/case.json \
  --stability $W/stability.json --out $W/result.json
# 4. 交付校验
python3 scripts/stability_engine.py validate --case $W/case.json --result $W/result.json
```

预期输出：

- 第 2 步：`score: case_id=demo-stability-01 records=5 runs=50 W=0.9017 stable=2 watch=2 fragile=1`
- 第 4 步：`VALIDATE PASS: case_id=demo-stability-01 records=5 contract_fields=5 state=complete`

## 预期分类（种子 20261125，runs=50）

| 记录 | 基准 rank | rank 范围 | 分类 | 说明 |
|---|---|---|---|---|
| D1 | 1 | 1–2 | stable | 明显居首，偶被 D3 短暂超越但不离开前二 |
| D3 | 2 | 1–4 | **fragile** | 预期 fragile：扰动下从第 1 荡到第 4 → 移入 pending_review，理由 "rank unstable under perturbation (rank range 3)" |
| D4 | 3 | 2–4 | watch | 与 D3 近乎同画像；一词元之差把它留在 watch 而非 fragile，正好演示阈值边界 |
| D2 | 4 | 2–4 | watch | 中间带另一位成员，保留在正式排序中并标记 |
| D5 | 5 | 5–5 | stable | 明显垫底 |

 Kendall's W ≈ **0.9017**：整体高度一致但显著低于 1——不稳定性集中在 D2/D3/D4 中间带，逐条 rank_range 指明了责任归属。

## 退化路径（诚实 partial）

省略第 2 步直接装配（指向不存在的 stability 文件）：全部记录进入 pending_review，`stability_report: null`，`status.state=partial`，原因写入 `status.incomplete`——validate 仍 PASS（partial 是合法交付态，全记录覆盖与契约字段镜像不被破坏）。

## 确定性自查

同一命令连跑两次第 2 步，`cmp` 两个 stability.json 应逐字节相同（固定种子 + 无墙钟依赖）。
