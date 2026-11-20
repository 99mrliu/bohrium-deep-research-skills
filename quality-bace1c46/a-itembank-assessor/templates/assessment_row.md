# 条目判断记录格式（assessments/<doc_id>.jsonl，每行一个 JSON 对象）

```json
{"item_id": "R-01", "judgment": "met", "quote": "Randomization was performed using a computer-generated random number sequence.", "locator": "p3.¶2", "rationale": "明确描述了随机序列生成方法。"}
```

字段说明：

| 字段 | 必填 | 说明 |
|---|---|---|
| item_id | 是 | 条目库中的条目 ID（如 C-01、R-01） |
| judgment | 是 | 四态之一：met / partial / not_met / not_assessable |
| quote | 三态必填 | 逐字摘录（见 rules/evidence_rules.md），≤400 字符 |
| locator | 三态必填 | 页锚：`p<页>.¶<段>` 或 `p<页>` |
| rationale | 是 | 一句话判断理由（≤80 字） |

校验后（assessments_verified/<doc_id>.jsonl）会增加 `verification` 字段：

```json
{"item_id": "R-01", "judgment": "met", "quote": "...", "locator": "p3.¶2",
 "rationale": "...", "verification": {"status": "ok"}}
```

`verification.status` 取值：`ok` / `wrong_page` / `not_found` / `missing_quote` /
`no_locator` / `skipped_na` / `invalid_judgment`。

## 设计分型修正记录（可选，design_overrides.json）

模型不同意脚本分型时，在 work 目录写：

```json
{"doc_001": {"design_type": "cohort", "reason": "文中无随机化描述，实为前瞻性队列"}}
```

build_result.py 会将其写入 result.json 的 change_records。
