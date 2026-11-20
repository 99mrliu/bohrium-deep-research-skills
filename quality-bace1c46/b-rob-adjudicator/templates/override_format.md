# 人工复核改判格式（review_overrides.jsonl）

复核者在 `/app/work/review_overrides.jsonl` 中每行写一个 JSON 对象，然后
重跑 `apply_overrides.py` 与 `build_result.py` 即可合并改判并重新推导等级。

## 字段

| 字段 | 必填 | 说明 |
|---|---|---|
| `doc_id` | 是 | 目标文献 |
| `domain` | 是 | 目标领域 id |
| `original` | 建议 | 复核者看到的当前判定；与系统当前值不一致时该条被拒绝并记入 `overrides_rejected`（防止基于过期版本改判） |
| `override` | 是 | 改判后的四级判定 |
| `reason` | 是 | 改判理由（将沉淀为量表改进素材） |
| `reviewer` | 是 | 复核者标识 |
| `quote` / `locator` | 否 | 若改判基于新证据，附逐字摘录与页锚 |

## 示例

```json
{"doc_id": "smith2023", "domain": "attrition", "original": "insufficient", "override": "likely", "reason": "表2注释显示对照组失访18%而试验组7%，仅完整病例分析", "reviewer": "liu", "quote": "Seven patients (7%) in the intervention group and eighteen (18%) in the control group were lost to follow-up", "locator": "p5.¶3"}
```

## 沉淀机制

`apply_overrides.py` 会把改判按领域聚合，与裁决台账中的分歧次数一起写入
`scale_revision_suggestions.md`：反复分歧/被改判的领域应修订信号问题措辞、
补充判定示例或调整阈值——改量表（`scripts/domain_specs.py` + `domains/`）
而不是修补个别结果。
