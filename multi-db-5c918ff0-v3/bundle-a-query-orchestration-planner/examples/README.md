# 合成示例说明

> **合成示例:所有文献与响应均为虚构(ZK-7 为虚构化合物,DOI 均为虚构的
> `10.99977/...`,作者、期刊、摘要、引用图均为编造),仅演示接口与流程,
> 非正式案例结果。**

## 目录

- `synthetic-input/` — 合成输入:`case.json`、`task.md`、模型步骤产物
  `facets.json`(示例中手工编写)及 `materials/` 下四份虚构材料。
  **publisher 库材料故意缺席**,用于演练覆盖缺口(gap)声明路径;
  Crossref 响应 `total-results=57 > items=3`,用于演练截断检测。
- `synthetic-output/` — **真实执行** `scripts/query_planner.py run-all`
  得到的产物:`result.json`、`query_plan.json`、`coverage_declaration.json`、
  `query_ledger.jsonl`,以及记录命令与退出码的 `run-record.md`。

## 复现

```bash
SKILL=/skills/weekly-skill   # 或本 bundle 的本地路径
python3 "$SKILL/scripts/query_planner.py" run-all \
  --input  "$SKILL/examples/synthetic-input" \
  --work   /tmp/qo-work \
  --output /tmp/qo-out \
  --facets "$SKILL/examples/synthetic-input/facets.json"
echo "exit=$?"   # 期望 0;result.status 期望为 partial(publisher 缺口已声明)
```

`--facets` 演示显式传入模型产物;也可先 `cp facets.json /tmp/qo-work/` 后省略
该参数(plan 缺省读取 `work/facets.json`)。

## 演练点对照

| 演练点 | 输入设计 | 期望输出表现 |
|---|---|---|
| 缺口声明 | publisher 材料缺席 | `coverage_declaration.json.gaps` 含 publisher;`result.json.uncertainty` 含 absent_db;status=partial |
| 截断检测 | crossref total-results 57 > items 3 | `truncation_flags` 含 crossref;open_questions 提及补采分页 |
| 查询回响核对 | 两库响应均携带回响 | crossref/europepmc `query_echo=matched` |
| 下游边界 | 契约含 evidence_records | 该字段 null + unresolved 登记(不臆造) |
