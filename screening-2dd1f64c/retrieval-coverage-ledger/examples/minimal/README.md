# 最小调用示例（合成示例，非正式案例结果）

本目录是**合成示例**：`case.example.json` 中的研究问题、查询、文献、DOI 与 fixture 标注均为演示虚构（`example_note` 已标注 "SYNTHETIC EXAMPLE"），`decisions.example.json` 是手写的演示判定。仅用于说明接口与完整流程，不冒充平台正式案例的结果。

示例数据特意覆盖台账的各种情形：S1/S2 带显式来源字段（`source_query` / `retrieved_by`），S3/S4 只能靠词面重叠推断归因，S5 无法归因；S4 是 S1 的预印本重复导出（带 `fixture_note`，仅作 provenance）；S5 缺 year 与 doi。

## 运行（端到端）

```bash
W=$(mktemp -d)
# 1. 建账：来源归因 + 逐查询产出 + 缺失元数据登记
python3 scripts/coverage_engine.py map --case examples/minimal/case.example.json --out $W/coverage.json
# 2.（正式运行时由 Agent 一次批量判定；此处直接使用演示判定）
# 3. 入账：会计恒等式 + 重复登记 + 遗漏说明 + 契约镜像
python3 scripts/coverage_engine.py account --case examples/minimal/case.example.json \
  --coverage $W/coverage.json --decisions examples/minimal/decisions.example.json \
  --out $W/result.json
# 4. 交付校验
python3 scripts/coverage_engine.py validate --case examples/minimal/case.example.json --result $W/result.json
```

预期输出：

```
map: case_id=demo-coverage-01 records=5 queries=2 explicit=2 inferred=2 unattributed=1 missing_meta=1 -> ...
account: state=partial records=5 keep=2 pending=1 exclude=2 merged_groups=1 suspected=0 rejected=0 repairs=0 -> ...
VALIDATE PASS: case_id=demo-coverage-01 records=5 buckets=keep:2/pending:1/exclude:2 contract_fields=6 state=partial
```

`state=partial` 是诚实状态：S3 的演示判定为 `pending`（人群是否纳入需人工复核），故存在未完成部分。

## 示意输出（合成示例）

- `query_coverage.per_query_yield`：查询 1 → [S1, S3, S4]（S1 显式，S3/S4 推断），查询 2 → [S2]（显式）；S5 进入 `unattributed_register`。
- `duplicate_register`：merged 组 canonical=S1、merged_from=[S4]（规范化标题精确匹配；正式发表优先于预印本）；S4 另有 `fixture_declared` 条目逐字引用其 fixture_note。
- `omission_statement`：有限快照免责声明、S5 缺 year/doi、S5 未归因、空的疑似复核队列。

## 退化路径（诚实 partial）

省略 `--decisions` 重跑第 3 步：全部 5 条记录 pending，`status.state=partial`，`incomplete` 说明未判定——validate 仍 PASS（partial 是合法交付态）。
