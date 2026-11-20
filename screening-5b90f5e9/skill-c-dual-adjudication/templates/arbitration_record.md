# 仲裁记录格式（arbitrations.json）

模型作为仲裁者，对 `disagreements.json` 中**每一条**分歧写一条仲裁记录，
一次批量请求完成，存为 `/app/work/arbitrations.json`（JSON 列表）。

## 字段

| 字段 | 要求 |
|---|---|
| record_id | 与分歧清单一一对应，不多不少 |
| final_decision | `include` / `exclude` / `uncertain` / `needs_human`（uncertain 与 D3 会被 adjudicate.py 统一升级为 needs_human） |
| disagreement_type | `D1` 标准歧义 / `D2` 证据阅读 / `D3` 元数据缺失 / `D4` 边界情形（见 rules/disagreement_taxonomy.md） |
| arbitration_basis | 非空；必须**引用标题/摘要片段**（可另附 evidence_quote 字段供脚本锚定），或**明确声明缺失的元数据**（含「缺失/未提供/无摘要/missing」等字样） |
| criteria_interpretation | **D1 必填**：对标准条文的明确解释，供全批同类记录一致适用；其他类型可空 |
| evidence_quote | 可选；若给出，必须是该记录 title/abstract 的逐字片段 |
| note | 可选；入门记录建议注明「待复核建议，未经人工复核」 |

## 示例（合成虚构数据）

```json
[
  {
    "record_id": "R0005",
    "final_decision": "include",
    "disagreement_type": "D1",
    "arbitration_basis": "双方均读到同一人群描述，分歧在混合人群标准解释；摘要明示 prespecified subgroup analysis in type 2 diabetes showed HbA1c reduction，T2D 亚组数据可单独提取。",
    "criteria_interpretation": "混合人群研究：若预设亚组提供了可单独提取的目标人群数据，按纳入处理；本批后续同类记录一致适用。",
    "evidence_quote": "prespecified subgroup analysis in type 2 diabetes showed HbA1c reduction",
    "note": ""
  },
  {
    "record_id": "R0007",
    "final_decision": "needs_human",
    "disagreement_type": "D3",
    "arbitration_basis": "该记录摘要缺失（abstract 为空），题录信息不足，无法可靠判定；需人工获取全文后复核确认。",
    "criteria_interpretation": "",
    "evidence_quote": "",
    "note": "待复核建议，未经人工复核"
  }
]
```

## 纪律

- 禁止平均/折中/多数票；每条独立定夺并给出可锚定依据。
- D1 产出的标准解释追加写入 `/app/work/criteria_interpretations.md`，
  并回查同类记录适用一致性（在 audit notes 中说明）。
- `adjudicate.py` 校验失败（exit 3）时按 adjudication_errors.json 补齐后重跑。
