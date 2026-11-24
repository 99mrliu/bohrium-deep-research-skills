# 台账模式（audit_ledger.json）

```json
{
  "ledger_version": "1.0",
  "entries": [
    {
      "seq": 2,
      "stage": "dedup",
      "input_count": 200,
      "output_count": 177,
      "operator": "example-driver",
      "timestamp_utc": "2026-11-24T00:00:00Z",
      "basis": "examples/minimal",
      "notes": "精确重复合并 23 条"
    }
  ]
}
```

## 字段语义

- `seq`：单调递增，由脚本分配，禁止手工指定；
- `stage`：标准阶段 identified/dedup/screened/included/excluded/
  needs_human/unprocessed；自定义阶段（如 fulltext_assessed）允许，
  但闭合规则 C1/C2 只覆盖标准链；
- `input_count` 可空（identified 这类源头阶段通常等于 output_count）；
- `operator`：谁执行——system（脚本）、model:<模型名>、human:<标识>；
- `basis`：计数依据的产物路径，复核者按此重数；
- `timestamp_utc`：默认当前 UTC；示例与复跑演示用固定值保证确定性。

## 记录纪律

- 每个阶段**完成后立即记录**，不留到收尾补账（补账易编数）；
- 阶段重跑时追加新记录而不是改旧记录；validate 取每阶段最后一条，
  历史记录即变更轨迹；
- 台账只经 stage_ledger.py 写入；手改台账会被 C3/闭合规则或
  manifest verify 抓住——这正是设计目的。
