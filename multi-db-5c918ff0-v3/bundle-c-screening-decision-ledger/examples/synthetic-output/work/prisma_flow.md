# PRISMA 风格筛选流量（由 decision_ledger.jsonl 逐行重算）

> 本表为 PRISMA 2020 流量图针对**离线多源候选集**的适配（详见 references/prisma-counting.md）；所有计数由脚本对账本行实际计数得到，非人工断言。

```
识别 identified
  crossref     6
  europepmc    5
  publisher    3
  total        14
    │
    ├─ 去重移除 duplicates_removed: 2
    │    · rec-0005 ← raw-0007 (doi)
    │    · rec-0012 ← raw-0014 (bibliographic)
    ▼
初筛 screened: 12
    ├─ 排除 excluded: 6
    │    · E1: 1
    │    · E2: 1
    │    · I1: 1
    │    · I2: 2
    │    · I3: 1
    ├─ 边界待决 borderline_pending: 0
    ▼
纳入 included: 6
```

## 守恒校验

| 不变量 | 左侧 | 右侧 | 成立 |
|---|---|---|---|
| identified - duplicates_removed == canonical_records | 12 | 12 | ✅ |
| records_screened + unjudged == canonical_records | 12 | 12 | ✅ |
| excluded + included + borderline_pending == records_screened | 12 | 12 | ✅ |
