# result.json 字段细则

> 由 `scripts/scaffold_result.py` 生成骨架；**output_contract 中的全部字段会被镜像填充**
> （骨架已占位的核心字段除外），未完成的字段保持占位值并在 `uncertainty` 说明。

## 顶层字段

| 字段 | 类型 | 说明 |
|---|---|---|
| `case_id` | string | 照录 /input/case.json 的 case_id |
| `status` | string | `ok` / `partial` / `failed`，必须诚实；任何一项闸控未过不得为 ok |
| `claims` | array | 结论对象数组（见下） |
| `legal_status` | object | `{records: [...], protocol, note}`，records 为状态台账记录（见 ledger_format.md） |
| `authorization` | object | `{tiers: [...], rules}`，tiers 为 license_tiers 分级结果 |
| `sources` | array | 全部来源：`{name, url?, kind, tier, query_date, locator?}` |
| `uncertainty` | array of string | 不确定性清单：状态未知、OCR 存疑、语料缺口、同族未完整核查、部分完成的界限 |
| `change_records` | array | `{timestamp, action, detail}`，每完成一步管线追加一条 |
| `_contract_mirrored_fields` | array | 已从 output_contract 镜像的字段名清单（审计用） |
| `_evidence_governance` | object | 管线与纪律声明（骨架自带） |

## claims 数组元素

```json
{
  "claim_id": "C1",
  "statement": "论断全文（措辞须与证据强度匹配）",
  "evidence": {
    "ledger": "/app/work/evidence_ledger.jsonl",
    "quote_hash": "sha256:<hex>",
    "quote_audit": {"passed": true, "match_mode": "verbatim|ocr_tolerant"}
  },
  "risk": {
    "grade": "high|medium|low",
    "score": 0,
    "triggered_rules": ["R-G6"]
  },
  "review": "low/medium 时的人工复核建议"
}
```

## status 判定口径

- `ok`：引文回核全过、状态台账 validate 通过、所有结论完成分级且无 R-G7 触发；
- `partial`：任一环节未完成或存在未决 uncertainty（必须逐条说明界限）；
- `failed`：核心材料不可读（如 PDF 既无文本层也无法 OCR）等无法推进的情形。

## 纪律

1. 镜像填充是**机械**的：契约里有的字段一个不少，值可以诚实为空；
2. 部分完成必须在 `uncertainty` 写明"完成到哪一步、剩下什么、为什么"；
3. 每次实质修改都追加 `change_records`（不要改写历史记录）。
